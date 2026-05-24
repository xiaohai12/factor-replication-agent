"""MethodSpec - Structured specification extracted from papers and reference materials.

Matches the nested YAML schema defined in architecture.md Section 4.2.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---


class RebalanceFrequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class WeightingRule(str, Enum):
    EQUAL_WEIGHTED = "ew"
    VALUE_WEIGHTED = "vw"
    CAPPED_VALUE_WEIGHTED = "capped_vw"


class BreakpointSource(str, Enum):
    NYSE = "nyse"
    FULL_SAMPLE = "full_sample"


class MissingAction(str, Enum):
    DROP = "drop"
    FILL_ZERO = "fill_zero"
    FILL_MEDIAN = "fill_median"
    FILL_FORWARD = "fill_forward"
    WINSORIZE = "winsorize"


class EvidenceSource(str, Enum):
    CLEAR = "clear"
    SINGLE = "single"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"


class EmpiricalImpact(str, Enum):
    HIGH = "high"
    LOW = "low"


# --- Sub-models ---


class FieldSource(BaseModel):
    """Source information for a data field."""

    dataset: str = Field(..., description="e.g. compustat, crsp")
    table: str = Field(..., description="e.g. funda, msf")
    description: str = Field(default="")


class SignalTiming(BaseModel):
    """Timing assumptions for signal construction."""

    formation_month: Optional[int] = Field(default=None, description="e.g. 6 for June")
    rebalance_frequency: RebalanceFrequency = Field(default=RebalanceFrequency.ANNUAL)
    holding_period: int = Field(default=12, description="Months")
    accounting_lag: int = Field(default=6, description="Months minimum")
    skip_month: Optional[int] = Field(default=None)


class MissingPolicy(BaseModel):
    """Missing-value handling policy."""

    action: MissingAction = Field(default=MissingAction.DROP)
    threshold: Optional[float] = Field(
        default=None, description="Max missing ratio before dropping firm-year"
    )


class SignalSpec(BaseModel):
    """Signal definition section of MethodSpec."""

    formula: str = Field(..., description="Signal construction formula")
    required_fields: list[str] = Field(default_factory=list)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    timing: SignalTiming = Field(default_factory=SignalTiming)
    missing_policy: MissingPolicy = Field(default_factory=MissingPolicy)


class BreakpointSpec(BaseModel):
    """Breakpoint configuration."""

    source: BreakpointSource = Field(default=BreakpointSource.NYSE)
    quantiles: list[int] = Field(default_factory=lambda: [30, 70])


class PortfolioSpec(BaseModel):
    """Portfolio construction section of MethodSpec."""

    universe: str = Field(default="NYSE + AMEX + NASDAQ, common shares only")
    breakpoints: BreakpointSpec = Field(default_factory=BreakpointSpec)
    weighting: WeightingRule = Field(default=WeightingRule.VALUE_WEIGHTED)
    long_leg: str = Field(default="high")
    short_leg: str = Field(default="low")


class ExtractionSource(BaseModel):
    """Record of where information was extracted from."""

    type: str = Field(..., description="paper | cz_metadata | osap_code | researcher_note")
    ref: str = Field(..., description="Citation or file reference")
    sections: list[str] = Field(default_factory=list)


class AmbiguousField(BaseModel):
    """Record of an ambiguous/uncertain field."""

    field: str
    reason: str = Field(default="")
    source: EvidenceSource = Field(default=EvidenceSource.INFERRED)
    confidence: str = Field(default="medium", description="low | medium | high")


# --- Main MethodSpec ---


class MethodSpec(BaseModel):
    """Structured method specification extracted from paper/reference materials.

    This is the central artifact that flows through the pipeline:
    Semantic Extractor -> Review Gate -> Meta-Coder -> Sandbox -> Engine.

    Matches the nested YAML schema in architecture.md Section 4.2.
    """

    # Identification
    factor_id: str = Field(..., description="Unique factor identifier")
    factor_name: str = Field(..., description="Human-readable factor name")
    paper_ref: str = Field(..., description="Original paper citation")
    version: int = Field(default=1, description="MethodSpec version number")
    economic_intuition: str = Field(default="", description="Brief economic rationale")

    # Signal definition (nested)
    signal: SignalSpec

    # Portfolio construction (nested)
    portfolio: PortfolioSpec = Field(default_factory=PortfolioSpec)

    # Provenance
    extraction_sources: list[ExtractionSource] = Field(default_factory=list)
    ambiguous_fields: list[AmbiguousField] = Field(default_factory=list)

    # Review state
    review_status: str = Field(default="pending", description="pending|approved|rejected|blocked")
    review_notes: list[dict] = Field(default_factory=list, description="Structured review notes")

    # --- Convenience accessors for engine compatibility ---

    @property
    def signal_formula(self) -> str:
        return self.signal.formula

    @property
    def required_fields(self) -> list[str]:
        return self.signal.required_fields

    @property
    def formation_month(self) -> Optional[int]:
        return self.signal.timing.formation_month

    @property
    def rebalance_frequency(self) -> RebalanceFrequency:
        return self.signal.timing.rebalance_frequency

    @property
    def holding_period_months(self) -> int:
        return self.signal.timing.holding_period

    @property
    def accounting_lag_months(self) -> int:
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
