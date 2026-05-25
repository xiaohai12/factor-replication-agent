"""MethodSpec - Structured specification extracted from papers and reference materials.

Matches the nested YAML schema defined in architecture.md Section 4.2.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---


class RebalanceFrequency(str, Enum):
    """How often the portfolio is reformed.

    - MONTHLY: portfolio reformed every month (holding_period=1)
    - QUARTERLY: reformed every 3 months
    - ANNUAL: reformed once per year, typically in June (most common in literature)
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class WeightingRule(str, Enum):
    """How stocks within a portfolio are weighted.

    - EW: equal-weighted — each stock gets 1/N weight (most common in SignalDoc: 210/242)
    - VW: value-weighted — weight proportional to market cap
    - CAPPED_VW: value-weighted with max weight cap to limit concentration
    """

    EQUAL_WEIGHTED = "ew"
    VALUE_WEIGHTED = "vw"
    CAPPED_VALUE_WEIGHTED = "capped_vw"


class BreakpointSource(str, Enum):
    """Universe used to compute portfolio breakpoints (quantile cutoffs).

    - NYSE: only NYSE stocks determine the cutoff values (avoids micro-cap influence)
    - FULL_SAMPLE: all stocks in the universe determine breakpoints
    """

    NYSE = "nyse"
    FULL_SAMPLE = "full_sample"


class MissingAction(str, Enum):
    """How missing signal values are handled before portfolio formation.

    - DROP: exclude firm-month with missing signal (most common default)
    - FILL_ZERO: treat missing as zero
    - FILL_MEDIAN: impute cross-sectional median
    - FILL_FORWARD: carry forward last available value
    - WINSORIZE: cap extreme values at percentile boundaries
    """

    DROP = "drop"
    FILL_ZERO = "fill_zero"
    FILL_MEDIAN = "fill_median"
    FILL_FORWARD = "fill_forward"
    WINSORIZE = "winsorize"


class EvidenceSource(str, Enum):
    """Confidence level of extracted information.

    - CLEAR: explicitly stated in the paper with no ambiguity
    - SINGLE: mentioned once, reasonable confidence
    - INFERRED: not stated directly — inferred from context or common practice
    - CONFLICTING: multiple sources disagree on this field
    """

    CLEAR = "clear"
    SINGLE = "single"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"


class EmpiricalImpact(str, Enum):
    """Whether an ambiguous field choice materially affects the replication result.

    - HIGH: different choices lead to meaningfully different returns/t-stats
    - LOW: result is robust to this choice
    """

    HIGH = "high"
    LOW = "low"


# --- Sub-models ---


class FieldSource(BaseModel):
    """Source information for a data field.

    Maps each required_field to its database location (Compustat/CRSP).
    Example: ceq → compustat.funda (Common Equity)
    """

    dataset: str = Field(..., description="e.g. compustat, crsp")
    table: str = Field(..., description="e.g. funda, msf")
    description: str = Field(default="")


class SignalTiming(BaseModel):
    """Timing assumptions for signal construction.

    Controls when portfolios are formed and how long they are held.
    SignalDoc stats: Start Month is June for 190/250 factors, Portfolio Period
    is 1 month (121) or 12 months (110).

    Example (BM factor):
      formation_month=6 (June), holding_period=12, accounting_lag=6
      → Use fiscal year-end data from Dec t-1, form portfolios June t,
        hold July t to June t+1.
    """

    formation_month: Optional[int] = Field(default=None, description="e.g. 6 for June")
    rebalance_frequency: RebalanceFrequency = Field(default=RebalanceFrequency.ANNUAL)
    holding_period: int = Field(default=12, description="Months")
    accounting_lag: int = Field(default=6, description="Months minimum")
    skip_month: Optional[int] = Field(default=None)


class MissingPolicy(BaseModel):
    """Missing-value handling policy.

    Determines how the pipeline handles firms with missing signal values.
    Most papers simply drop firms with missing data (default).
    """

    action: MissingAction = Field(default=MissingAction.DROP)
    threshold: Optional[float] = Field(
        default=None, description="Max missing ratio before dropping firm-year"
    )


class SignalSpec(BaseModel):
    """Signal definition — the core "what to compute" specification.

    Contains the formula (e.g. 'ceq / (csho * prcc_f)' for BM),
    the list of required Compustat/CRSP fields, timing rules, and
    missing-value policy. This is what the Meta-Coder translates into
    executable Python code.
    """

    formula: str = Field(..., description="Signal construction formula")
    required_fields: list[str] = Field(default_factory=list)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    timing: SignalTiming = Field(default_factory=SignalTiming)
    missing_policy: MissingPolicy = Field(default_factory=MissingPolicy)


class BreakpointSpec(BaseModel):
    """Breakpoint configuration for portfolio sorting.

    Determines how stocks are sorted into quantile portfolios.
    - source: which stocks define the cutoff values (NYSE-only avoids micro-caps)
    - ls_quantile: the fraction used for long-short (0.1=deciles, 0.2=quintiles, 0.3=terciles)
    - quantiles: derived percentile boundaries [low_pct, high_pct]

    SignalDoc stats: LS Quantile is 0.1 (61 factors), 0.2 (66 factors), 0.3 (4).
    """

    source: BreakpointSource = Field(default=BreakpointSource.NYSE)
    quantiles: list[int] = Field(default_factory=lambda: [30, 70])
    ls_quantile: Optional[float] = Field(default=None, description="Long-short cutoff fraction (0.1=decile, 0.2=quintile)")


class PortfolioSpec(BaseModel):
    """Portfolio construction — how to form long-short portfolios from the signal.

    Specifies the investment universe, sorting methodology, weighting scheme,
    and which quantile is long vs short. The long-short return is:
      LS = return(long_leg quantile) - return(short_leg quantile)

    SignalDoc stats: 210/242 are EW, 141 have sign=+1 (high→high returns),
    most use NYSE+AMEX+NASDAQ common shares.
    """

    universe: str = Field(default="NYSE + AMEX + NASDAQ, common shares only")
    breakpoints: BreakpointSpec = Field(default_factory=BreakpointSpec)
    weighting: WeightingRule = Field(default=WeightingRule.VALUE_WEIGHTED)
    long_leg: str = Field(default="high")
    short_leg: str = Field(default="low")
    filter: str = Field(default="", description="Stock-level filters, e.g. abs(prc)>5, exchcd%in%c(1,2)")


class ExtractionSource(BaseModel):
    """Record of where information was extracted from.

    Tracks provenance for each piece of the MethodSpec — which paper section,
    which C&Z metadata field, or which OSAP predictor code file provided the info.
    """

    type: str = Field(..., description="paper | cz_metadata | osap_code | researcher_note")
    ref: str = Field(..., description="Citation or file reference")
    sections: list[str] = Field(default_factory=list)


class AmbiguousField(BaseModel):
    """Record of an ambiguous/uncertain field.

    When the LLM cannot determine a field from the paper (returns "unspecified"),
    it gets tagged here. The Review Gate uses these to decide whether the
    MethodSpec needs human input before proceeding to code generation.
    """

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
    detailed_definition: str = Field(default="", description="Detailed signal definition in words")
    cat_form: str = Field(default="continuous", description="continuous or discrete")
    sign: int = Field(default=1, description="1=high→high returns, -1=high→low returns")
    sample_start_year: Optional[int] = Field(default=None)
    sample_end_year: Optional[int] = Field(default=None)

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
