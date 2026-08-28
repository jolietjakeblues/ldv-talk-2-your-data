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
    return re.sub(r"\s+", " ", value.casefold()).strip()


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
    normalised_question = f" {_normalise(question)} "
    matches = [
        (label, uri)
        for label, uri in terms
        if f" {_normalise(label)} " in normalised_question
    ]
    return max(matches, key=lambda item: len(_normalise(item[0]))) if matches else None


def resolve_question(question: str) -> list[ResolvedTerm]:
    """Resolveer gemeente of provincie uit de vraag; faal veilig bij endpointproblemen."""
    q = _normalise(question)
    kind, class_uri = (
        ("provincie", OWMS_PROVINCIE_CLASS)
        if "provincie" in q
        else ("gemeente", OWMS_GEMEENTE_CLASS)
    )
    try:
        match = _find_longest(question, _load_owms_terms(class_uri))
    except requests.RequestException as exc:
        logger.warning("OWMS-resolutie mislukt voor %s: %s", kind, exc)
        return []
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
