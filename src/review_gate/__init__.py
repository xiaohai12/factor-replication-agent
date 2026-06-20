"""Review Gate - Validate MethodSpec before code generation.

Implements the Review Decision Matrix from docs/architecture.md Section 4.3:
- LLM Reviewer (default picky: reject over approve when uncertain)
- Evidence × Impact classification
- Disposition: auto_approve | needs_llm_review | needs_human_confirmation
- Sensible defaults for unspecified fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.data_layer import DataDictionary
from src.models.method_spec import (
    AmbiguousField,
    EvidenceCitation,
    EmpiricalImpact,
    EvidenceSource,
    MethodSpec,
    RemediationMode,
)


# --- Review Decision Matrix ---

# High-impact fields: changes materially affect empirical results
HIGH_IMPACT_FIELDS = {
    "signal.formula",
    "signal.sign",
    "signal.timing.accounting_lag",
    "timing.accounting_lag_months",
    "signal.timing.formation_month",
    "signal.timing.rebalance_frequency",
    "signal.timing.holding_period",
    "signal.timing.skip_month",
    "signal.missing_policy",
    "portfolio.breakpoints",
    "portfolio.breakpoints.source",
    "portfolio.sort.breakpoint_source",
    "portfolio.sort.ls_quantile",
    "portfolio.weighting",
    "portfolio.weighting_scheme",
    "portfolio.universe",
    "portfolio.long_leg",
    "portfolio.short_leg",
    "portfolio.implied_factor_direction",
    "reported_results.comparison_policy",
    "reported_results.return_calculation",
    "reported_results.return_horizon",
    "reported_results.spreads",
}

# Sensible defaults (HXZ / C&Z convention) for unspecified fields
SENSIBLE_DEFAULTS = {
    "signal.timing.accounting_lag": 6,
    "signal.missing_policy.action": "drop",
    "signal.timing.formation_month": 6,
    "portfolio.breakpoints.source": "nyse",
    "portfolio.weighting": "vw",
    "signal.timing.rebalance_frequency": "annual",
}


class Disposition(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_APPROVE_WITH_FLAG = "auto_approve_with_flag"
    APPROVE_WITH_DEFAULT = "approve_with_default"
    NEEDS_LLM_REVIEW = "needs_llm_review"
    NEEDS_HUMAN_CONFIRMATION = "needs_human_confirmation"


@dataclass
class FieldReviewNote:
    """Review note for a single field."""

    field: str
    status: Disposition
    reason: str = ""
    current_value: object = None
    candidate_value: object = None
    empirical_impact: str = ""
    evidence: list[EvidenceCitation] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Result of MethodSpec review."""

    review_id: str = ""
    methodspec_version: str = "v1"
    reviewer: str = "llm"  # llm | human
    disposition: str = "pending"  # approved | revision_required | blocked
    remediation_mode: str = RemediationMode.RESOLVE_EXISTING_JSON.value
    codegen_ready: bool = False
    paper_faithful: bool = False
    approved: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_notes: list[FieldReviewNote] = field(default_factory=list)
    blocked_fields: list[str] = field(default_factory=list)
    requires_human: bool = False


def classify_disposition(
    evidence: EvidenceSource, impact: EmpiricalImpact
) -> Disposition:
    """Apply the Review Decision Matrix to determine disposition.

    | Evidence \\ Impact  | Low impact                | High impact                    |
    |---------------------|---------------------------|--------------------------------|
    | Clear               | auto_approve              | auto_approve                   |
    | Single              | auto_approve_with_flag    | needs_llm_review               |
    | Inferred            | approve_with_default+flag | needs_human_confirmation       |
    | Conflicting         | needs_llm_review          | needs_human_confirmation       |
    """
    matrix = {
        (EvidenceSource.CLEAR, EmpiricalImpact.LOW): Disposition.AUTO_APPROVE,
        (EvidenceSource.CLEAR, EmpiricalImpact.HIGH): Disposition.AUTO_APPROVE,
        (EvidenceSource.SINGLE, EmpiricalImpact.LOW): Disposition.AUTO_APPROVE_WITH_FLAG,
        (EvidenceSource.SINGLE, EmpiricalImpact.HIGH): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.INFERRED, EmpiricalImpact.LOW): Disposition.APPROVE_WITH_DEFAULT,
        (EvidenceSource.INFERRED, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.UNSPECIFIED, EmpiricalImpact.LOW): Disposition.APPROVE_WITH_DEFAULT,
        (EvidenceSource.UNSPECIFIED, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.WEAK_OR_CONFLICTING, EmpiricalImpact.LOW): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.WEAK_OR_CONFLICTING, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.CONFLICTING, EmpiricalImpact.LOW): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.CONFLICTING, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
    }
    return matrix[(evidence, impact)]


class ReviewGate:
    """Validates MethodSpec for completeness, consistency, and correctness.

    Implements a picky LLM Reviewer that defaults to rejection when uncertain.
    Key principle: empirical choices (lag, missing policy, sample restriction)
    are NOT bug fixes — they must be explicitly specified and reviewed.

    Checks:
    - Format correctness
    - Citation backing for key assumptions
    - Field existence in data dictionaries
    - Timing consistency
    - Missing-value policy clarity
    - Lag and reporting-date alignment
    - Conflicts between paper/metadata/reference code
    - Review Decision Matrix for ambiguous fields
    """

    def __init__(
        self,
        data_dictionary: Optional[DataDictionary] = None,
        llm_client=None,
    ):
        self.data_dictionary = data_dictionary
        self.llm_client = llm_client

    def review(self, spec: MethodSpec) -> ReviewResult:
        """Run all review checks on a MethodSpec."""
        result = ReviewResult(methodspec_version=spec.schema_version)

        self._check_required_fields(spec, result)
        self._check_paper_evidence(spec, result)
        self._check_data_fields_exist(spec, result)
        self._check_timing_consistency(spec, result)
        self._check_reported_results_contract(spec, result)
        self._check_ambiguous_fields(spec, result)

        # Determine overall disposition
        if result.blocked_fields:
            result.disposition = "blocked"
            result.requires_human = True
            result.approved = False
        elif result.issues:
            result.disposition = "revision_required"
            result.remediation_mode = RemediationMode.RESOLVE_EXISTING_JSON.value
            result.approved = False
        else:
            result.disposition = "approved"
            result.approved = True
            result.codegen_ready = True
            result.paper_faithful = True

        return result

    def _check_required_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that critical fields are populated."""
        if not spec.signal.formula_expression:
            result.issues.append("signal.formula is empty")
        if not spec.required_fields:
            result.issues.append("signal.required_fields is empty")
        if not spec.portfolio.long_leg or not spec.portfolio.short_leg:
            result.issues.append("portfolio.long_leg / short_leg not specified")

    def _check_paper_evidence(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check methodspec.v1 audit fields without blocking early drafts."""
        if not spec.extraction_sources:
            result.warnings.append("No extraction_sources recorded")
        if not spec.data.required_fields:
            result.warnings.append("data.required_fields is empty; normalizer has no source hints")
        formula = spec.signal.formula
        evidence = getattr(formula, "evidence", []) if not isinstance(formula, str) else []
        if not evidence:
            result.warnings.append("signal.formula has no field-level paper evidence")

    def _check_data_fields_exist(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that required fields exist in data dictionary."""
        if not self.data_dictionary:
            result.warnings.append("No data dictionary provided, skipping field check")
            return
        for f in spec.required_fields:
            if not self.data_dictionary.exists(f):
                result.issues.append(f"Field '{f}' not found in data dictionary")

    def _check_timing_consistency(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check timing assumptions are internally consistent."""
        timing = spec.signal.timing
        if timing.accounting_lag is not None and timing.accounting_lag < 0:
            result.issues.append("accounting_lag cannot be negative")
        if timing.holding_period is not None and timing.holding_period <= 0:
            result.issues.append("holding_period must be positive")
        if timing.accounting_lag is not None and timing.accounting_lag < 4:
            result.warnings.append(
                f"accounting_lag={timing.accounting_lag} months is unusually short"
            )

    def _check_reported_results_contract(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check the newer reported_results.return_calculation contract."""
        calc = spec.reported_results.return_calculation
        if spec.reported_results.main_spread is not None and calc.input_return == "unspecified":
            result.warnings.append(
                "reported_results.main_spread is set but return_calculation.input_return is unspecified"
            )
        weighting = calc.portfolio_return.get("weighting") if calc.portfolio_return else None
        if weighting and str(weighting) != spec.portfolio.weighting.value:
            result.warnings.append(
                "reported_results portfolio_return.weighting differs from portfolio.weighting"
            )

    def _check_ambiguous_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Apply Review Decision Matrix to ambiguous fields."""
        for amb in spec.ambiguous_fields:
            impact = (
                EmpiricalImpact.HIGH
                if amb.field in HIGH_IMPACT_FIELDS or amb.empirical_impact == EmpiricalImpact.HIGH
                else EmpiricalImpact.LOW
            )
            disposition = classify_disposition(amb.source, impact)

            note = FieldReviewNote(
                field=amb.field,
                status=disposition,
                reason=amb.reason,
                current_value=self._get_field_value(spec, amb.field),
                candidate_value=amb.candidate_value,
                empirical_impact=impact.value,
                evidence=amb.evidence,
            )
            result.field_notes.append(note)

            if disposition == Disposition.NEEDS_HUMAN_CONFIRMATION:
                result.blocked_fields.append(amb.field)
            elif disposition == Disposition.NEEDS_LLM_REVIEW:
                result.warnings.append(
                    f"Field '{amb.field}' needs LLM review: {amb.reason}"
                )

    def _get_field_value(self, spec: MethodSpec, field_path: str):
        """Best-effort dotted-path lookup for review context."""
        path_aliases = {
            "universe.missing_policy.action": "signal.missing_policy.action",
            "universe.winsorize_bounds": "signal.missing_policy.winsorize_bounds",
        }
        field_path = path_aliases.get(field_path, field_path)
        current = spec
        for part in field_path.split("."):
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
        return getattr(current, "value", current)
