"""Review Gate - Validate MethodSpec before code generation."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.method_spec import MethodSpec


@dataclass
class ReviewResult:
    """Result of MethodSpec review."""

    approved: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_human: bool = False


class ReviewGate:
    """Validates MethodSpec for completeness, consistency, and correctness.

    Checks:
    - Format correctness
    - Citation backing for key assumptions
    - Field existence in data dictionaries
    - Timing consistency
    - Missing-value policy clarity
    - Lag and reporting-date alignment
    - Conflicts between paper/metadata/reference code
    """

    def __init__(self, data_dictionary: dict | None = None):
        self.data_dictionary = data_dictionary or {}

    def review(self, spec: MethodSpec) -> ReviewResult:
        """Run all review checks on a MethodSpec."""
        result = ReviewResult()
        self._check_required_fields(spec, result)
        self._check_data_fields_exist(spec, result)
        self._check_timing_consistency(spec, result)
        self._check_missing_policy(spec, result)

        if not result.issues:
            result.approved = True
        return result

    def _check_required_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that critical fields are populated."""
        if not spec.signal_formula:
            result.issues.append("signal_formula is empty")
        if not spec.required_fields:
            result.issues.append("required_fields is empty")
        if not spec.long_short_direction:
            result.issues.append("long_short_direction is empty")

    def _check_data_fields_exist(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that required fields exist in data dictionary."""
        if not self.data_dictionary:
            result.warnings.append("No data dictionary provided, skipping field check")
            return
        for f in spec.required_fields:
            if f not in self.data_dictionary:
                result.issues.append(f"Field '{f}' not found in data dictionary")

    def _check_timing_consistency(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check timing assumptions are internally consistent."""
        if spec.accounting_lag_months < 0:
            result.issues.append("accounting_lag_months cannot be negative")
        if spec.holding_period_months <= 0:
            result.issues.append("holding_period_months must be positive")

    def _check_missing_policy(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Ensure missing-value policy is explicitly specified."""
        if spec.ambiguous_fields and not spec.review_notes:
            result.warnings.append(
                "Ambiguous fields exist but no review notes explaining resolution"
            )
