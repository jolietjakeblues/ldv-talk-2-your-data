"""
SPARQL query executor.

Verantwoordelijkheden:
- Query uitvoeren op het RCE SPARQL endpoint
- Resultaten dedupliceren op ?rm (monument URI)
- Foutafhandeling voor timeouts en HTTP-fouten
- Fallback op een lokale ruimtelijke join (Shapely) als een
  geof:sfWithin/sfIntersects-query faalt op het endpoint
"""

import logging
import re
from typing import Any

import requests

from config import SPARQL_ENDPOINT, PROVINCIE_NAAM
from sparql import spatial

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30

# Endpointfouten die duiden op een probleem met de ruimtelijke berekening
# zelf (ongeldige geometrie, JTS-topologiefout) in plaats van een fout in
# de query. Bij zo'n fout is een lokale Shapely-fallback zinvol.
SPATIAL_ERROR_MARKERS = ("topologyexception", "jts", "invalid geometry")


def _validate_read_query(query: str) -> None:
    """Sta alleen SPARQL-leesqueries toe."""
    without_comments = re.sub(r"(?m)^\s*#[^\r\n]*", "", query)
    without_prefixes = re.sub(
        r"^\s*(?:PREFIX\s+\w*:\s*<[^>]+>\s*)+",
        "",
        without_comments,
        flags=re.IGNORECASE,
    )
    if not re.match(r"^\s*(SELECT|ASK)\b", without_prefixes, re.IGNORECASE):
        raise ValueError("Alleen SELECT- en ASK-queries zijn toegestaan")


def _run(query: str) -> dict[str, Any]:
    """Voer een kale SPARQL query uit en geef het ruwe JSON-resultaat terug."""
    response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def has_spatial_filter(query: str) -> bool:
    """Bevat de query een geof:sfWithin/sfIntersects-filter?"""
    return spatial.has_spatial_filter(query)


def is_spatial_error(exc: Exception) -> bool:
    """Wijst deze fout op een probleem met de ruimtelijke berekening zelf?"""
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        body = exc.response.text.lower()
        return any(marker in body for marker in SPATIAL_ERROR_MARKERS)
    return False


def execute(query: str) -> dict[str, Any]:
    """
    Voer een SPARQL query uit op het RCE endpoint.

    Bevat een geof:sfWithin/sfIntersects-filter en faalt die aanroep met een
    timeout of een fout die op een topologieprobleem wijst, dan wordt de
    query herhaald zonder de ruimtelijke FILTER en wordt de ruimtelijke
    relatie lokaal met Shapely berekend (zie sparql/spatial.py). Kapotte of
    onherstelbare geometrie wordt daarbij overgeslagen in plaats van de hele
    aanvraag te laten mislukken.

    Returns:
        SPARQL JSON resultaat als dict, gededupliceerd op ?rm.

    Raises:
        requests.exceptions.Timeout: Bij timeout (als de fallback niet van
            toepassing is of ook faalt).
        requests.exceptions.HTTPError: Bij HTTP-fouten (idem).
    """
    _validate_read_query(query)
    logger.info("Query uitvoeren op %s", SPARQL_ENDPOINT)

    spatial_filter = spatial.extract_spatial_filter(query)

    try:
        data = _run(query)
    except (requests.exceptions.Timeout, requests.exceptions.HTTPError) as exc:
        if not spatial_filter or not is_spatial_error(exc):
            raise

        relation, obj_var, gebied_var = spatial_filter
        logger.warning(
            "Ruimtelijke query faalde op het endpoint (%s); val terug op "
            "lokale berekening met Shapely.",
            exc,
        )

        simplified_query = spatial.strip_spatial_filter(query)
        data = _run(simplified_query)
        data = spatial.apply_spatial_filter(data, relation, obj_var, gebied_var)

    data = _translate_provincie_uris(data)

    original = len(data.get("results", {}).get("bindings", []))
    data = _deduplicate(data)
    deduped = len(data.get("results", {}).get("bindings", []))

    if original != deduped:
        logger.info("Deduplicatie: %d → %d rijen", original, deduped)

    return data


def _translate_provincie_uris(data: dict) -> dict:
    """Vertaal ?provURI waarden naar leesbare provincienamen."""
    bindings = data.get("results", {}).get("bindings", [])
    for row in bindings:
        if "provURI" in row:
            uri = row["provURI"].get("value", "")
            naam = PROVINCIE_NAAM.get(uri)
            if naam:
                row["provincie"] = {"type": "literal", "value": naam}
            else:
                # Gebruik het laatste deel van de URI als fallback
                row["provincie"] = {"type": "literal", "value": uri.split("/")[-1]}
    # Voeg provincie toe aan vars als provURI aanwezig is
    vars_ = data.get("head", {}).get("vars", [])
    if "provURI" in vars_ and "provincie" not in vars_:
        idx = vars_.index("provURI")
        vars_.insert(idx, "provincie")
    return data


def _deduplicate(data: dict[str, Any]) -> dict[str, Any]:
    """
    Dedupliceert resultaten op ?rm (monument URI).

    Als ?rm aanwezig is in de resultaten, bewaar dan alleen de eerste
    rij per monument URI. Bij queries zonder ?rm (bijv. COUNT) wordt
    niets aangepast.
    """
    bindings = data.get("results", {}).get("bindings", [])
    vars_ = data.get("head", {}).get("vars", [])

    if "rm" not in vars_ or not bindings:
        return data

    seen: set[str] = set()
    deduped = []

    for row in bindings:
        rm_val = row.get("rm", {}).get("value", "")
        if rm_val and rm_val not in seen:
            seen.add(rm_val)
            deduped.append(row)
        elif not rm_val:
            deduped.append(row)

    data["results"]["bindings"] = deduped
    return data
