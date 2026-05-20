"""MethodSpec - Structured specification extracted from papers and reference materials."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RebalanceFrequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class WeightingRule(str, Enum):
    EQUAL_WEIGHTED = "ew"
    VALUE_WEIGHTED = "vw"
    CAPPED_VALUE_WEIGHTED = "capped_vw"


class BreakpointRule(str, Enum):
    NYSE = "nyse"
    FULL_SAMPLE = "full_sample"


class MissingPolicy(str, Enum):
    DROP = "drop"
    FILL_ZERO = "fill_zero"
    FILL_MEDIAN = "fill_median"
    FILL_FORWARD = "fill_forward"


class MethodSpec(BaseModel):
    """Structured method specification extracted from paper/reference materials.

    This is the central artifact that flows through the pipeline:
    Semantic Extractor -> Review Gate -> Meta-Coder -> Sandbox -> Engine.
    """

    # Identification
    factor_id: str = Field(..., description="Unique factor identifier")
    paper_citation: str = Field(..., description="Original paper citation")
    version: int = Field(default=1, description="MethodSpec version number")

    # Factor definition
    factor_name: str = Field(..., description="Human-readable factor name")
    economic_intuition: str = Field(default="", description="Brief economic rationale")
    signal_formula: str = Field(..., description="Signal construction formula description")
    long_short_direction: str = Field(
        ..., description="Which portfolio is long, which is short"
    )

    # Data requirements
    required_fields: list[str] = Field(default_factory=list, description="Required data fields")
    data_source: str = Field(default="", description="Primary data source (CRSP/Compustat/etc)")

    # Timing
    formation_month: Optional[int] = Field(default=None, description="Portfolio formation month")
    rebalance_frequency: RebalanceFrequency = Field(default=RebalanceFrequency.ANNUAL)
    holding_period_months: int = Field(default=12)
    accounting_lag_months: int = Field(default=4)
    skip_month: int = Field(default=0, description="Months to skip after formation")

    # Portfolio construction
    breakpoint_rule: BreakpointRule = Field(default=BreakpointRule.NYSE)
    weighting_rule: WeightingRule = Field(default=WeightingRule.VALUE_WEIGHTED)
    n_quantiles: int = Field(default=10, description="Number of quantile portfolios")

    # Data handling
    missing_policy: MissingPolicy = Field(default=MissingPolicy.DROP)
    winsorize_pcts: Optional[tuple[float, float]] = Field(
        default=None, description="Winsorization percentiles (lower, upper)"
    )
    universe_filters: list[str] = Field(
        default_factory=list, description="Universe restriction rules"
    )

    # Provenance
    source_citations: list[str] = Field(
        default_factory=list, description="Citations for key assumptions"
    )
    ambiguous_fields: list[str] = Field(
        default_factory=list, description="Fields with uncertain/ambiguous definitions"
    )
    review_status: str = Field(default="pending", description="pending|approved|rejected")
    review_notes: str = Field(default="")
