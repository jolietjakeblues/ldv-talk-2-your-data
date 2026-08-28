"""Semantische controles op door een taalmodel gegenereerde SPARQL."""

from __future__ import annotations

import re

from sparql.semantic_resolver import ResolvedTerm


def requested_limit(question: str) -> int | None:
    match = re.search(
        r"\b(?:geef|toon|laat(?:\s+mij)?\s+zien|noem)\s+(\d{1,3})\b",
        question,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def validate_semantics(question: str, query: str, terms: list[ResolvedTerm]) -> list[str]:
    errors: list[str] = []
    lowered = query.lower()
    for term in terms:
        if f"<{term.uri}>" not in query:
            errors.append(f'Gebruik de opgeloste {term.kind}-URI <{term.uri}>.')
        required = "ceo:heeftGemeente" if term.kind == "gemeente" else "ceo:heeftProvincie"
        if required.lower() not in lowered:
            errors.append(f"Gebruik {required} via ceo:heeftBasisregistratieRelatie.")
        if term.kind == "gemeente" and (
            "ceo:gemeentenaam" in lowered or "ceo:heeftbrkrelatie" in lowered
        ):
            errors.append("Gebruik voor gemeente geen BRKRelatie of ceo:gemeentenaam.")

    limit = requested_limit(question)
    if limit is not None and not re.search(rf"\bLIMIT\s+{limit}\b", query, re.IGNORECASE):
        errors.append(f"De gebruiker vraagt exact {limit} resultaten; gebruik LIMIT {limit}.")
    return errors


# Onderwerpen die, als de vraag ze noemt, een herkenbaar querypatroon moeten
# opleveren. Dit vangt het geval waarin het LLM een deel van een
# meerledige vraag (bv. gemeente + functie + gezicht) stilzwijgend laat
# vallen in plaats van te combineren.
FUNCTIE_KEYWORDS = (
    "functie", "kerk", "kerkhof", "begraafplaats", "molen", "kasteel",
    "boerderij", "school", "fabriek", "toren", "klooster", "gemaal", "sluis",
)
FUNCTIE_PATHS = ("heeftoorspronkelijkefunctie", "heefthuidigefunctie", "heefttype")

GEZICHT_KEYWORDS = ("gezicht", "stadsgezicht", "dorpsgezicht")
SPATIAL_FUNCTIONS = ("geof:sfwithin", "geof:sfintersects")


def validate_completeness(question: str, query: str) -> list[str]:
    """Controleer of onderdelen die letterlijk in de vraag staan ook in de query terugkomen."""
    q = question.lower()
    lowered = query.lower()
    errors: list[str] = []

    if any(keyword in q for keyword in FUNCTIE_KEYWORDS):
        if not any(path in lowered for path in FUNCTIE_PATHS):
            errors.append(
                "De vraag noemt een functie of type (bv. kerk, molen, school, "
                "of het woord 'functie'), maar de query bevat geen "
                "functie/type-patroon. Voeg ceo:heeftOorspronkelijkeFunctie, "
                "ceo:heeftHuidigeFunctie en/of ceo:heeftType toe (zie FUNCTIE EN "
                "TYPE BIJ RIJKSMONUMENTEN in datamodel_rules.txt)."
            )

    if any(keyword in q for keyword in GEZICHT_KEYWORDS):
        has_gezicht_class = "ceo:gezicht" in lowered
        has_spatial = any(fn in lowered for fn in SPATIAL_FUNCTIONS)
        if not (has_gezicht_class and has_spatial):
            errors.append(
                "De vraag noemt een (beschermd) gezicht, maar de query mist "
                "ceo:Gezicht en/of de ruimtelijke relatie. Voeg ceo:Gezicht toe "
                "en filter met geof:sfWithin of geof:sfIntersects op beide "
                "WKT-geometrieën (zie RIJKSMONUMENTEN BINNEN EEN GEZICHT in "
                "datamodel_rules.txt)."
            )

    return errors
