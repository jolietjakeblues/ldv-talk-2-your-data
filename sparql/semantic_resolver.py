"""Resolveer labels uit gebruikersvragen naar gezaghebbende OWMS-URI's."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import re
import unicodedata

import requests

import config

logger = logging.getLogger(__name__)

OWMS_GEMEENTE_CLASS = "http://standaarden.overheid.nl/owms/terms/Gemeente"
OWMS_PROVINCIE_CLASS = "http://standaarden.overheid.nl/owms/terms/Provincie"


@dataclass(frozen=True)
class ResolvedTerm:
    kind: str
    label: str
    uri: str


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^\w-]+", " ", value.casefold(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


@lru_cache(maxsize=4)
def _load_owms_terms(class_uri: str) -> tuple[tuple[str, str], ...]:
    query = f"""
PREFIX graph: <https://linkeddata.cultureelerfgoed.nl/graph/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?uri ?label
WHERE {{
  GRAPH graph:owms {{
    ?uri a <{class_uri}> ;
         skos:prefLabel ?label .
  }}
}}
""".strip()
    response = requests.get(
        config.SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=15,
    )
    response.raise_for_status()
    bindings = response.json().get("results", {}).get("bindings", [])
    return tuple(
        (row["label"]["value"], row["uri"]["value"])
        for row in bindings
        if row.get("label", {}).get("value") and row.get("uri", {}).get("value")
    )


def _find_longest(question: str, terms: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
    normalised_question = _normalise(question)
    matches = [
        (label, uri)
        for label, uri in terms
        if re.search(rf"(?<!\w){re.escape(_normalise(label))}(?!\w)", normalised_question)
    ]
    return max(matches, key=lambda item: len(_normalise(item[0]))) if matches else None


def resolve_question(question: str) -> list[ResolvedTerm]:
    """Resolveer een plaatslabel naar een gemeentelijke of provinciale OWMS-URI."""
    q = _normalise(question)
    try:
        matches = {
            "gemeente": _find_longest(question, _load_owms_terms(OWMS_GEMEENTE_CLASS)),
            "provincie": _find_longest(question, _load_owms_terms(OWMS_PROVINCIE_CLASS)),
        }
    except requests.RequestException as exc:
        raise RuntimeError("OWMS-resolutie via het RCE endpoint is mislukt") from exc

    if "provincie" in q:
        kind = "provincie"
    elif "gemeente" in q:
        kind = "gemeente"
    else:
        available = [(candidate, match) for candidate, match in matches.items() if match]
        if not available:
            return []
        kind, _ = max(
            available,
            key=lambda item: (len(_normalise(item[1][0])), item[0] == "gemeente"),
        )

    match = matches[kind]
    if not match:
        return []
    label, uri = match
    return [ResolvedTerm(kind=kind, label=label, uri=uri)]


def build_semantic_context(terms: list[ResolvedTerm]) -> str:
    if not terms:
        return ""
    lines = ["OPGELOSTE BEGRIPPEN. DEZE URI'S ZIJN VERPLICHT:"]
    for term in terms:
        property_name = "ceo:heeftGemeente" if term.kind == "gemeente" else "ceo:heeftProvincie"
        lines.append(
            f'- {term.kind} "{term.label}" = <{term.uri}>; '
            f"gebruik via ceo:heeftBasisregistratieRelatie en {property_name}."
        )
    lines.append("Gebruik geen labeltekst, BRK/gemeentenaam of BAG/woonplaatsnaam als vervanging.")
    return "\n".join(lines)
