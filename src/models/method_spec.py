"""MethodSpec models for the paper-first factor replication workflow.

The current architecture uses ``methodspec.v1`` as an auditable artifact:
it records paper-stated method facts, field-level evidence, ambiguity, and
review state. The legacy ``signal``/``portfolio`` objects are still exposed
because several early modules and tests consume that shape.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Enums ---


class RebalanceFrequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    UNSPECIFIED = "unspecified"


class WeightingRule(str, Enum):
    EQUAL_WEIGHTED = "ew"
    VALUE_WEIGHTED = "vw"
    CAPPED_VALUE_WEIGHTED = "capped_vw"
    UNSPECIFIED = "unspecified"


class BreakpointSource(str, Enum):
    NYSE = "nyse"
    FULL_SAMPLE = "full_sample"
    UNSPECIFIED = "unspecified"


class MissingAction(str, Enum):
    DROP = "drop"
    FILL_ZERO = "fill_zero"
    FILL_MEDIAN = "fill_median"
    FILL_FORWARD = "fill_forward"
    WINSORIZE = "winsorize"
    UNSPECIFIED = "unspecified"


class EvidenceSource(str, Enum):
    CLEAR = "clear"
    SINGLE = "single"
    INFERRED = "inferred"
    UNSPECIFIED = "unspecified"
    WEAK_OR_CONFLICTING = "weak_or_conflicting"
    CONFLICTING = "conflicting"


class EmpiricalImpact(str, Enum):
    HIGH = "high"
    LOW = "low"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVISION_REQUIRED = "revision_required"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class RemediationMode(str, Enum):
    PATCH_EXISTING_JSON = "patch_existing_json"
    TARGETED_REEXTRACTION = "targeted_reextraction"
    FULL_REGENERATION = "full_regeneration"


# --- Evidence and paper-first source models ---


class EvidenceCitation(BaseModel):
    """Field-level source evidence required by methodspec.v1."""

    location: str = Field(default="", description="Paper section/table/page/caption")
    quote: str = Field(default="", description="Short supporting quote from the paper")
    interpretation: str = Field(default="", description="How the quote supports the field")
    source_type: str = Field(default="paper", description="paper | dictionary | note | default")

    @property
    def has_quote(self) -> bool:
        return bool(self.quote.strip())


class ExtractionSource(BaseModel):
    """Document-level provenance for the extraction run."""

    type: str = Field(..., description="paper | data_dictionary | researcher_note")
    ref: str = Field(..., description="Citation, file, or note reference")
    sections: list[str] = Field(default_factory=list)


class DataSourceHint(BaseModel):
    """Paper-stated data source hint.

    ``source_details`` intentionally stays close to the paper wording. It is
    not a physical WRDS table contract; the Data Catalog / Normalizer owns that
    mapping.
    """

    name: str = Field(default="")
    source_details: list[str] = Field(default_factory=list)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class RequiredFieldSpec(BaseModel):
    """Paper-stated variable requirement before physical catalog mapping."""

    field: str
    concept: str = Field(default="")
    source_detail: str = Field(default="")
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class FieldSource(BaseModel):
    """Legacy physical field source used by early codegen experiments."""

    dataset: str = Field(..., description="e.g. compustat, crsp")
    table: str = Field(..., description="e.g. funda, msf")
    description: str = Field(default="")


class DataSpec(BaseModel):
    """Data references extracted from the paper.

    These hints are paper-first and audit-oriented. Codegen should consume a
    normalized implementation config rather than these strings directly.
    """

    sources: list[DataSourceHint] = Field(default_factory=list)
    required_fields: list[RequiredFieldSpec] = Field(default_factory=list)
    normalized_mapping: dict[str, Any] = Field(
        default_factory=dict,
        description="Output from Data Catalog / Normalizer, not extractor-owned.",
    )


# --- Signal, timing, portfolio, and reported-result models ---


class FormulaSpec(BaseModel):
    """Signal expression with separate paper and codegen representations."""

    expression: str = Field(default="", description="Computable expression for codegen")
    paper_expression: str = Field(default="", description="Formula as stated in the paper")
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class SignalTiming(BaseModel):
    formation_month: Optional[int] = Field(default=None)
    rebalance_frequency: RebalanceFrequency = Field(default=RebalanceFrequency.UNSPECIFIED)
    holding_period: Optional[int] = Field(default=None, description="Months")
    accounting_lag: Optional[int] = Field(default=None, description="Months")
    skip_month: Optional[int] = Field(default=None)
    overlapping_portfolios: Optional[bool] = Field(default=None)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class MissingPolicy(BaseModel):
    action: MissingAction = Field(default=MissingAction.UNSPECIFIED)
    threshold: Optional[float] = None
    winsorize_bounds: Optional[tuple[float, float]] = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class SignalSpec(BaseModel):
    """The factor signal definition that the Meta-Coder translates to code."""

    formula: str | FormulaSpec = Field(default_factory=FormulaSpec)
    required_fields: list[str] = Field(default_factory=list)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    timing: SignalTiming = Field(default_factory=SignalTiming)
    missing_policy: MissingPolicy = Field(default_factory=MissingPolicy)
    sign: int = Field(default=1, description="1=high signal is long, -1=low signal is long")

    @property
    def formula_expression(self) -> str:
        if isinstance(self.formula, FormulaSpec):
            return self.formula.expression
        return self.formula

    @property
    def paper_expression(self) -> str:
        if isinstance(self.formula, FormulaSpec):
            return self.formula.paper_expression
        return self.formula


class BreakpointSpec(BaseModel):
    source: BreakpointSource = Field(default=BreakpointSource.UNSPECIFIED)
    quantiles: list[int] = Field(default_factory=list)
    ls_quantile: Optional[float] = Field(default=None)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class PortfolioSortSpec(BaseModel):
    breakpoint_source: BreakpointSource = Field(default=BreakpointSource.UNSPECIFIED)
    ls_quantile: Optional[float] = None
    quantiles: list[int] = Field(default_factory=list)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class PortfolioSpec(BaseModel):
    universe: str = Field(default="unspecified")
    sort: PortfolioSortSpec = Field(default_factory=PortfolioSortSpec)
    breakpoints: BreakpointSpec = Field(default_factory=BreakpointSpec)
    weighting: WeightingRule = Field(default=WeightingRule.UNSPECIFIED)
    weighting_scheme: WeightingRule = Field(default=WeightingRule.UNSPECIFIED)
    long_leg: str = Field(default="high")
    short_leg: str = Field(default="low")
    implied_factor_direction: str = Field(default="")
    filter: str = Field(default="")
    evidence: list[EvidenceCitation] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.sort.breakpoint_source == BreakpointSource.UNSPECIFIED:
            self.sort.breakpoint_source = self.breakpoints.source
        if self.breakpoints.source == BreakpointSource.UNSPECIFIED:
            self.breakpoints.source = self.sort.breakpoint_source
        if not self.sort.quantiles:
            self.sort.quantiles = list(self.breakpoints.quantiles)
        if not self.breakpoints.quantiles:
            self.breakpoints.quantiles = list(self.sort.quantiles)
        if self.sort.ls_quantile is None:
            self.sort.ls_quantile = self.breakpoints.ls_quantile
        if self.breakpoints.ls_quantile is None:
            self.breakpoints.ls_quantile = self.sort.ls_quantile
        if self.weighting_scheme == WeightingRule.UNSPECIFIED:
            self.weighting_scheme = self.weighting
        if self.weighting == WeightingRule.UNSPECIFIED:
            self.weighting = self.weighting_scheme


class ReturnCalculationSpec(BaseModel):
    input_return: str = Field(default="unspecified")
    portfolio_return: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class ReportedResultsSpec(BaseModel):
    return_horizon: str = Field(default="monthly")
    return_type: str = Field(default="long_short_spread")
    comparison_policy: str = Field(default="")
    return_calculation: ReturnCalculationSpec = Field(default_factory=ReturnCalculationSpec)
    spreads: list[float] = Field(default_factory=list)
    t_stats: list[float] = Field(default_factory=list)
    main_spread: Optional[float] = None
    main_t_stat: Optional[float] = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class AmbiguousField(BaseModel):
    field: str
    reason: str = Field(default="")
    source: EvidenceSource = Field(default=EvidenceSource.INFERRED)
    confidence: str = Field(default="medium", description="low | medium | high")
    candidate_value: Any = None
    empirical_impact: EmpiricalImpact = Field(default=EmpiricalImpact.HIGH)
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class ReviewNote(BaseModel):
    field: str
    status: str
    reason: str = Field(default="")
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class PatchLogEntry(BaseModel):
    field_path: str
    old_value: Any = None
    new_value: Any = None
    reason: str = Field(default="")
    reviewer: str = Field(default="")


# --- Main MethodSpec ---


class MethodSpec(BaseModel):
    """Paper-first method specification for a single executable factor target."""

    model_config = ConfigDict(use_enum_values=False)

    schema_version: str = Field(default="methodspec.v1")
    factor_id: str
    factor_name: str
    paper_ref: str = Field(default="")
    version: int = Field(default=1)

    economic_intuition: str = Field(default="")
    detailed_definition: str = Field(default="")
    cat_form: str = Field(default="continuous")
    sign: int = Field(default=1)
    sample_start_year: Optional[int] = None
    sample_end_year: Optional[int] = None
    cz_acronym: Optional[str] = Field(default=None)

    data: DataSpec = Field(default_factory=DataSpec)
    signal: SignalSpec
    portfolio: PortfolioSpec = Field(default_factory=PortfolioSpec)
    reported_results: ReportedResultsSpec = Field(default_factory=ReportedResultsSpec)

    extraction_sources: list[ExtractionSource] = Field(default_factory=list)
    ambiguous_fields: list[AmbiguousField] = Field(default_factory=list)

    review_status: ReviewStatus | str = Field(default=ReviewStatus.PENDING)
    remediation_mode: Optional[RemediationMode | str] = None
    codegen_ready: bool = False
    paper_faithful: bool = False
    review_notes: list[ReviewNote | dict[str, Any]] = Field(default_factory=list)
    patch_log: list[PatchLogEntry] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self.signal.sign = self.sign
        if not self.data.required_fields and self.signal.required_fields:
            self.data.required_fields = [
                RequiredFieldSpec(
                    field=field,
                    source_detail=(
                        f"{src.dataset}.{src.table}"
                        if (src := self.signal.field_sources.get(field))
                        and src.dataset
                        and src.table
                        else ""
                    ),
                    concept=(
                        self.signal.field_sources[field].description
                        if field in self.signal.field_sources
                        else ""
                    ),
                )
                for field in self.signal.required_fields
            ]

    # --- Backward-compatible flat result properties ---

    @property
    def reported_return_spread(self) -> Optional[float]:
        return self.reported_results.main_spread

    @property
    def reported_t_stat(self) -> Optional[float]:
        return self.reported_results.main_t_stat

    @property
    def return_horizon(self) -> str:
        return self.reported_results.return_horizon

    @property
    def signal_formula(self) -> str:
        return self.signal.formula_expression

    @property
    def required_fields(self) -> list[str]:
        if self.signal.required_fields:
            return self.signal.required_fields
        return [f.field for f in self.data.required_fields]

    @property
    def formation_month(self) -> Optional[int]:
        return self.signal.timing.formation_month

    @property
    def rebalance_frequency(self) -> RebalanceFrequency:
        return self.signal.timing.rebalance_frequency

    @property
    def holding_period_months(self) -> Optional[int]:
        return self.signal.timing.holding_period

    @property
    def accounting_lag_months(self) -> Optional[int]:
        return self.signal.timing.accounting_lag

    @property
    def skip_month(self) -> Optional[int]:
        return self.signal.timing.skip_month

    @property
    def missing_action(self) -> MissingAction:
        return self.signal.missing_policy.action

    @property
    def breakpoint_source(self) -> BreakpointSource:
        return self.portfolio.breakpoints.source

    @property
    def weighting_rule(self) -> WeightingRule:
        return self.portfolio.weighting

    @property
    def universe_description(self) -> str:
        return self.portfolio.universe

    def stable_hash(self) -> str:
        """Hash the audit-relevant MethodSpec content for registry provenance."""
        payload = self.model_dump(mode="json", exclude={"review_notes", "patch_log"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
