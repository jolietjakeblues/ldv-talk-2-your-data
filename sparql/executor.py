"""
SPARQL query executor.

Verantwoordelijkheden:
- Query uitvoeren op het RCE SPARQL endpoint
- Resultaten dedupliceren op ?rm (monument URI)
- Foutafhandeling voor timeouts en HTTP-fouten
"""

import logging
import re
from typing import Any

import requests

from config import SPARQL_ENDPOINT, PROVINCIE_NAAM

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


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


def execute(query: str) -> dict[str, Any]:
    """
    Voer een SPARQL query uit op het RCE endpoint.

    Returns:
        SPARQL JSON resultaat als dict, gededupliceerd op ?rm.

    Raises:
        requests.exceptions.Timeout: Bij timeout.
        requests.exceptions.HTTPError: Bij HTTP-fouten.
    """
    _validate_read_query(query)
    logger.info("Query uitvoeren op %s", SPARQL_ENDPOINT)

    response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
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
