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
