"""Explicit implementation policies for market-equity construction.

These policies are deliberately narrow.  They record a human-approved
implementation choice and must not be mistaken for a claim about what every
paper, or even the original paper, necessarily used.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infra.models.method_spec import MethodSpec, ResolvedMethodSpec


DICHEV_Z_SCORE_DOCUMENT_ID = "is the risk of bankruptcy a systematic risk.pdf"
FORBIDDEN_COMPUSTAT_MARKET_EQUITY_COLUMNS = frozenset({
    "mkvalt", "prcc_f", "prcc_c", "prccm", "csho",
})
CRSP_MARKET_EQUITY_COLUMNS = ("prc", "shrout")


def requires_crsp_fiscal_year_end_market_equity(spec: MethodSpec | ResolvedMethodSpec) -> bool:
    """Whether the user-approved Dichev Z-score implementation policy applies."""
    paper = spec.paper if hasattr(getattr(spec, "paper", None), "paper") else spec
    document_id = paper.paper.document_id.strip().lower()
    target = re.sub(r"[^a-z0-9]+", "", paper.target_name.lower())
    return document_id == DICHEV_Z_SCORE_DOCUMENT_ID and target == "zscore"


def market_equity_contract_errors(spec: MethodSpec | ResolvedMethodSpec) -> list[str]:
    """Return deterministic MethodSpec/resolution violations for this policy."""
    paper = spec.paper if hasattr(getattr(spec, "paper", None), "paper") else spec
    if not requires_crsp_fiscal_year_end_market_equity(paper):
        return []

    inputs = set(paper.signal.formula.inputs)
    fields = {field.concept_id: field for field in paper.data.fields}

    def physical(concept_id: str) -> tuple[str | None, str | None]:
        field = fields.get(concept_id)
        if field is None:
            return None, None
        source = field.source_table.value
        return (getattr(source, "value", source), field.source_column.value)

    errors: list[str] = []
    required = {
        "crsp_fiscal_year_end_price": ("crsp_msf", "prc"),
        "crsp_fiscal_year_end_shares": ("crsp_msf", "shrout"),
        "total_liabilities": ("compustat_fundamental_annual", "lt"),
    }
    for concept_id, expected in required.items():
        actual = physical(concept_id)
        if concept_id not in inputs or actual != expected:
            errors.append(
                f"requires formula input {concept_id!r} mapped to {expected[0]}.{expected[1]} "
                f"(found input={concept_id in inputs}, mapping={actual[0]}.{actual[1]})"
            )

    resolution = getattr(spec, "resolution", None)
    if resolution is not None:
        for concept_id, expected in required.items():
            mapped = resolution.concept_mapping.get(concept_id)
            actual = (mapped.source, mapped.column) if mapped is not None else (None, None)
            if actual != expected:
                errors.append(
                    f"requires resolved mapping {concept_id!r} -> {expected[0]}.{expected[1]} "
                    f"(found {actual[0]}.{actual[1]})"
                )

    for field in paper.data.fields:
        source = getattr(field.source_table.value, "value", field.source_table.value)
        column = field.source_column.value
        if source == "compustat_fundamental_annual" and column in FORBIDDEN_COMPUSTAT_MARKET_EQUITY_COLUMNS:
            errors.append(
                f"forbids Compustat market-equity proxy {source}.{column} ({field.concept_id!r})"
            )
    return errors


def assert_market_equity_contract(spec: MethodSpec | ResolvedMethodSpec) -> None:
    errors = market_equity_contract_errors(spec)
    if errors:
        raise ValueError(
            "Dichev Z-score is configured by the approved implementation policy to use "
            "CRSP fiscal-year-end market equity via CCM: abs(prc) * shrout / 1000, "
            "with Compustat lt. " + "; ".join(errors)
        )
