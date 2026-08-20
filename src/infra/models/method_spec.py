"""Paper-first MethodSpec models (Phase A -- contract freeze, no pipeline
consumers yet).

Implements the four-artifact boundary from docs/methodspec-v2-plan.md section 5:

    MethodSpec          Step 1, immutable paper-first facts only.
    MethodReview              Step 2 findings.
    ImplementationResolution  Physical mappings + human decisions, append-only.
    ResolvedMethodSpec        Rebuilt-on-read aggregate (D1); never persisted as input.

None of this is wired into src/steps/* yet. See plan section 9 (migration
phases) -- Phase A only freezes the contract and adds round-trip tests.

Naming/semantics follow the plan's section 6 decisions (D1-D8); see
docs/decision-log.md for the approval record. NOTE: the plan's D1
paper/review/resolution hash-binding staleness check
(`paper_spec_hash`/`review_hash`/`_hashes_current`) was removed 2026-08-09 --
see that date's decision-log entry. `MethodSpec.content_hash()` itself is
kept (still used elsewhere, e.g. plugin/script naming), but `MethodReview`/
`ImplementationResolution` no longer bind to it and `ResolvedMethodSpec.
is_ready` no longer checks staleness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.infra.data_layer import catalog
from src.infra.models.source_enum import SourceName

T = TypeVar("T")


# --- 6.0 Shared building blocks -------------------------------------------


class EvidenceStatus(str, Enum):
    CLEAR = "clear"  # Prose states it; quote is auto-verifiable via substring search.
    TABLE_ONLY = "table_only"  # Number comes from a table cell; no prose quote (the common case).
    INFERRED = "inferred"  # LLM inferred from domain convention; paper doesn't say.
    CONFLICTING = "conflicting"  # Paper contradicts itself.
    UNSPECIFIED = "unspecified"  # Paper doesn't address this at all.


class TableRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    row: str = ""
    column: str = ""


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = ""
    quote: str = ""
    table_ref: TableRef | None = None
    interpretation: str = ""

    @model_validator(mode="after")
    def _quote_xor_table_ref_for_clear_vs_table_only(self) -> EvidenceCitation:
        # Not a hard error here -- EvidenceStatus is what actually branches
        # verification behavior (Step2 automation vs human review path).
        # This citation shape only records what evidence looks like.
        return self


class SourcedValue(BaseModel, Generic[T]):
    """Wraps a scalar/text value extracted from the paper with its evidence."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED
    #: Paper's literal description of the value, filled only when `value`
    #: was classified as the `other` menu member (weighting/construction_type/
    #: breakpoints.basis/missing_policies[].action -- see review.py's LLM
    #: review contract). `None` for every other field; never populated
    #: alongside a real menu token, since that would make it look like an
    #: unresolved gap when the field actually classified cleanly.
    unsupported_value: str | None = None

    @model_validator(mode="after")
    def _unsupported_value_only_with_other(self) -> SourcedValue:
        is_other = self.value is not None and str(getattr(self.value, "value", self.value)) == "other"
        if self.unsupported_value is not None and not is_other:
            raise ValueError(
                "unsupported_value is set but value != 'other' -- "
                f"got value={self.value!r}, unsupported_value={self.unsupported_value!r}"
            )
        return self


# --- 6.1 Top-level identity ------------------------------------------------


class PaperRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str = ""
    citation: str = ""
    publication_year: int | None = None


# --- 6.2 Signal & formula ---------------------------------------------------


class SignalCategory(str, Enum):
    CONTINUOUS = "continuous"
    CATEGORICAL = "categorical"
    INDICATOR = "indicator"
    ESTIMATED = "estimated"


class SignalDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NON_MONOTONIC = "non_monotonic"
    UNSPECIFIED = "unspecified"


class CalculationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    description: str
    expression: str = ""
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class FormulaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_expression: str = ""
    steps: list[CalculationStep] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)  # concept_id refs into DataSpec.fields
    constants: dict[str, float] = Field(default_factory=dict)
    output_concept: str = ""
    evidence: list[EvidenceCitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _step_ids_unique(self) -> FormulaSpec:
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError(f"FormulaSpec.steps has duplicate step_id values: {ids}")
        return self


# --- 6.3 Estimation & windows -----------------------------------------------


class TimeUnit(str, Enum):
    DAY = "day"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class WindowAnchor(str, Enum):
    FORMATION_DATE = "formation_date"
    FISCAL_PERIOD_END = "fiscal_period_end"
    REPORT_DATE = "report_date"
    OBSERVATION_DATE = "observation_date"


class WindowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_offset: int
    end_offset: int
    unit: TimeUnit
    anchor: WindowAnchor
    is_expanding: bool = False


class EstimationMethod(str, Enum):
    TIME_SERIES_REGRESSION = "time_series_regression"
    CROSS_SECTIONAL_REGRESSION = "cross_sectional_regression"
    ROLLING_STATISTIC = "rolling_statistic"
    RESIDUALIZATION = "residualization"
    OTHER = "other"


class EstimationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: EstimationMethod
    model_expression: str = ""
    estimation_window: WindowSpec
    measurement_window: WindowSpec | None = None
    minimum_observations: int | None = None
    residual_definition: str = ""
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class SignalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: SourcedValue[str]
    economic_intuition: SourcedValue[str]
    direction: SourcedValue[SignalDirection]
    category: SignalCategory = SignalCategory.CONTINUOUS
    formula: FormulaSpec
    estimation: EstimationSpec | None = None

    @model_validator(mode="after")
    def _estimated_category_requires_estimation(self) -> SignalSpec:
        if self.category == SignalCategory.ESTIMATED and self.estimation is None:
            raise ValueError("signal.category == 'estimated' requires signal.estimation to be set")
        return self


# --- 6.4 Data requirements ---------------------------------------------------


class FieldRole(str, Enum):
    SIGNAL_INPUT = "signal_input"
    UNIVERSE_FILTER = "universe_filter"
    WEIGHTING_INPUT = "weighting_input"
    BENCHMARK_INPUT = "benchmark_input"
    ESTIMATION_INPUT = "estimation_input"


class RequiredField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    name_in_paper: str
    description: str = ""
    paper_source_hint: str = ""
    roles: list[FieldRole] = Field(default_factory=list)
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    #: Which registered `DataSource` this concept physically comes from
    #: (dynamic `SourceName` enum, one member per `sources.py` registration
    #: + `OTHER`). `value=None` means not yet chosen (backward-compatible
    #: default for specs written before this field existed). `OTHER` means
    #: "the paper names a data source with no registered match" -- pairs
    #: with `SourcedValue.unsupported_value` (the paper's own wording), same
    #: escape-hatch pattern as `WeightingScheme.OTHER`. See docs/decision-log.md
    #: 2026-08-13 for why this now lives on `MethodSpec` instead of being
    #: deferred entirely to `ImplementationResolution`.
    source_table: SourcedValue[SourceName] = Field(default_factory=SourcedValue)
    #: Physical column name within `source_table`. Only meaningful when
    #: `source_table.value` is a real registered source (not `None`/`OTHER`);
    #: cross-validated below against that source's actual `physical_columns`.
    source_column: SourcedValue[str] = Field(default_factory=SourcedValue)

    @model_validator(mode="after")
    def _source_column_belongs_to_source_table(self) -> RequiredField:
        table = self.source_table.value
        if table is None or str(table.value) == "other":
            return self
        column = self.source_column.value
        if column is None:
            return self
        registered = catalog.DATA_CATALOG.get(table.value, {}).get("physical_columns", set())
        if column not in registered:
            raise ValueError(
                f"source_column {column!r} is not a registered physical column of "
                f"source_table {table.value!r} (has: {sorted(registered)})"
            )
        return self


class DataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_frequency: SourcedValue[TimeUnit]
    return_frequency: SourcedValue[TimeUnit]
    sources: list[SourcedValue[str]] = Field(default_factory=list)
    fields: list[RequiredField] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _concept_ids_unique(self) -> DataSpec:
        ids = [f.concept_id for f in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError(f"DataSpec.fields has duplicate concept_id values: {ids}")
        return self


# --- 6.5 Sample period (three independent periods) --------------------------


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_year: int | None = None
    end_year: int | None = None
    start_month: int | None = None
    end_month: int | None = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED


class SampleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_coverage: Period
    formation: Period
    reported_returns: Period


# --- 6.6 Timing --------------------------------------------------------------


class LagBasis(str, Enum):
    FIXED_CALENDAR_LAG = "fixed_calendar_lag"
    REPORT_DATE = "report_date"
    POINT_IN_TIME = "point_in_time"


class DataAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lag_value: int | None = None
    lag_unit: TimeUnit = TimeUnit.MONTH
    anchor: WindowAnchor = WindowAnchor.FISCAL_PERIOD_END
    basis: LagBasis = LagBasis.FIXED_CALENDAR_LAG
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class TimingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formation_rule: SourcedValue[str]
    #: Structured calendar month (1-12) portfolios form on, e.g. 6 for June --
    #: distinct from `formation_rule`'s free text (needed for prose/quote
    #: evidence). None when the paper doesn't state an explicit month (e.g.
    #: monthly-rebalanced factors, where every month is a formation month).
    #: Found missing during Phase D registry wiring -- v1's MethodSpec had a
    #: structured `formation_month: int`, which this replaces.
    formation_month: SourcedValue[int] | None = None
    rebalance_frequency: SourcedValue[TimeUnit]
    #: ALWAYS in months, regardless of `rebalance_frequency`'s unit (e.g. a
    #: paper stating "held for 1 year" must be written as 12, not 1) --
    #: `registry.build_config` passes this straight through as
    #: `holding_period_months` with no unit conversion of its own.
    holding_period: SourcedValue[int]
    return_window: WindowSpec | None = None
    data_availability: DataAvailability


# --- 6.7 Universe & missing-data handling ------------------------------------


class FilterOp(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    NONMISSING = "nonmissing"
    NONZERO = "nonzero"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    op: FilterOp = FilterOp.NONMISSING
    value: Any = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    #: How to derive this filter's value from `concept_id`'s underlying
    #: physical column, when the paper's vocabulary doesn't match the
    #: column's raw encoding (e.g. "NYSE/Amex/NASDAQ" -> exchcd 1/2/3) or the
    #: concept itself must be computed (e.g. "listing duration >= 2 years"
    #: from an ipodate column) -- same shape as `SignalSpec.formula`
    #: (`inputs` references abstract concept_ids, never physical columns) so
    #: it can be reviewed at Step2 without waiting for resolve, and later
    #: codegen'd by Step3 the same way `compute_signal` is (paper-side
    #: formula + resolution-side `concept_mapping`, combined at codegen
    #: time). `None` means the concept's `concept_mapping` column is used
    #: as-is, no transform needed.
    derivation: FormulaSpec | None = None
    #: Human-approved escape hatch: this stated universe restriction is NOT
    #: applied at runtime (e.g. its field can't yet be resolved against any
    #: registered data source/panel). Never set by `build_config` itself --
    #: only a human decision, always paired with `unapplied_reason` -- so the
    #: deviation is explicitly recorded rather than silently dropped (see
    #: AGENTS.md: "never silently ignore a stated universe restriction").
    #: Excluded from `concept_mapping` resolution requirements (see
    #: `ResolvedMethodSpec.unmapped_concepts`) and from the engine's
    #: `universe_filters` -- it plays no runtime role, it's purely a
    #: recorded, reviewable gap (see `registry._unapplied_universe_filters`).
    accepted_unapplied: bool = False
    unapplied_reason: str = ""


class UniverseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: SourcedValue[str]
    filters: list[FilterSpec] = Field(default_factory=list)


class MissingStage(str, Enum):
    INPUT = "input"
    SIGNAL = "signal"
    PORTFOLIO = "portfolio"


class TransformStage(str, Enum):
    BEFORE_SIGNAL = "before_signal"
    AFTER_SIGNAL = "after_signal"


class MissingActionScheme(str, Enum):
    """Mirrors `ENGINE_MISSING_ACTION_MENU` (src/steps/step2_reviewer/review.py):
    same pattern as `WeightingScheme` -- `OTHER` is the escape hatch for a
    paper-stated policy the engine can't run (e.g. imputation/interpolation),
    with the paper's own free-text description still surviving in this
    field's `evidence[]` citations.
    """

    DROP = "drop"
    OTHER = "other"


class MissingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: MissingStage
    action: SourcedValue[MissingActionScheme]
    threshold: float | None = None


class TransformKind(str, Enum):
    WINSORIZE = "winsorize"
    TRUNCATE = "truncate"
    STANDARDIZE = "standardize"
    RANK = "rank"
    LOG = "log"
    OTHER = "other"


class TransformSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TransformKind
    stage: TransformStage
    bounds: tuple[float, float] | None = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


# --- 6.8 Portfolio construction ----------------------------------------------


class ConstructionType(str, Enum):
    CHARACTERISTIC_SORT = "characteristic_sort"
    FAMA_MACBETH = "fama_macbeth"
    DIRECT_PORTFOLIO = "direct_portfolio"
    OTHER = "other"


class SortRole(str, Enum):
    TARGET = "target"
    CONTROL = "control"
    CONDITIONING = "conditioning"


class SortMode(str, Enum):
    """`WITHIN_GROUP` is a known, specific engine capability gap (see
    `docs/resolve-diagnostics-gaps.md` problem 2) -- not yet implemented by
    `BacktestExecutor.assign_portfolios_multi` (independent/sequential only).
    Unlike `WeightingScheme.OTHER` etc., it is NOT a free-text escape hatch;
    it's passed through to the engine as-is, which fails loud rather than
    silently treating it as sequential. `OTHER` is the genuine free-text
    escape hatch, for a paper-stated dimension relationship that isn't any
    of the three named modes -- registry.py clamps only `OTHER` to a default.
    """

    INDEPENDENT = "independent"
    SEQUENTIAL = "sequential"
    WITHIN_GROUP = "within_group"
    OTHER = "other"


class GroupType(str, Enum):
    """`CATEGORICAL`/`THRESHOLD` are known, specific engine capability gaps
    (see docs/resolve-diagnostics-gaps.md problem 2) -- the engine only
    implements quantile grouping. `OTHER` is the genuine free-text escape
    hatch for a grouping scheme that's neither of those two named ones.
    """

    QUANTILE = "quantile"
    CATEGORICAL = "categorical"
    THRESHOLD = "threshold"
    OTHER = "other"


class ReturnCombinationScheme(str, Enum):
    """Mirrors `ENGINE_RETURN_COMBINATION_MENU` (src/steps/step2_reviewer/
    review.py) -- same OTHER-escape-hatch pattern as `WeightingScheme`.
    Promoted from a bare `SourcedValue[str]` (docs/resolve-diagnostics-gaps.md
    problem 2) so an out-of-menu choice is recorded via `unsupported_value`
    like every other engine-menu field, instead of silently accepted as any
    string.
    """

    EXTREME_GROUP_SPREAD = "extreme_group_spread"
    AVERAGE_LEG_SPREAD = "average_leg_spread"
    SINGLE_SIGNAL_PORTFOLIO_RETURN = "single_signal_portfolio_return"
    FULL_PORTFOLIO_RETURN = "full_portfolio_return"
    OTHER = "other"


class WeightingScheme(str, Enum):
    """Mirrors `ENGINE_WEIGHTING_MENU` (src/steps/step2_reviewer/review.py):
    `OTHER` is the escape hatch for a paper-stated scheme the engine can't run
    (same D4-block-via-enum pattern as `ConstructionType.OTHER`) -- the paper's
    own free-text description still survives in this field's `evidence[]`
    citations, only the categorical `.value` is constrained.
    """

    VW = "vw"
    EW = "ew"
    OTHER = "other"


class BreakpointBasis(str, Enum):
    """Mirrors `ENGINE_BREAKPOINT_SOURCE_MENU` (src/steps/step2_reviewer/
    review.py) -- same OTHER-escape-hatch pattern as `WeightingScheme`.
    `FULL_SAMPLE` covers any "all stocks"/"all eligible stocks"/"entire
    universe" wording; `NYSE` covers "NYSE-only"/"NYSE breakpoints" wording.
    """

    FULL_SAMPLE = "full_sample"
    NYSE = "nyse"
    OTHER = "other"


class BreakpointSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: SourcedValue[BreakpointBasis]
    values: list[float] = Field(default_factory=list)


class SortDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort_id: str
    concept_id: str
    role: SortRole
    order: int
    mode: SourcedValue[SortMode]
    group_type: SourcedValue[GroupType]
    group_count: int | None = None
    breakpoints: BreakpointSpec
    condition_on_sort_id: str | None = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class PortfolioLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leg_id: str
    side: Literal["long", "short"]
    selector: dict[str, Any] = Field(default_factory=dict)  # {sort_id: group_index}
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class PortfolioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    construction_type: SourcedValue[ConstructionType]
    sorts: list[SortDimension] = Field(default_factory=list)
    legs: list[PortfolioLeg] = Field(default_factory=list)
    weighting: SourcedValue[WeightingScheme]
    return_combination: SourcedValue[ReturnCombinationScheme]
    missing_policies: list[MissingPolicy] = Field(default_factory=list)
    transforms: list[TransformSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sort_and_leg_ids_unique(self) -> PortfolioSpec:
        sort_ids = [s.sort_id for s in self.sorts]
        if len(sort_ids) != len(set(sort_ids)):
            raise ValueError(f"PortfolioSpec.sorts has duplicate sort_id values: {sort_ids}")
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            raise ValueError(f"PortfolioSpec.legs has duplicate leg_id values: {leg_ids}")

        known_sort_ids = set(sort_ids)
        for s in self.sorts:
            if s.condition_on_sort_id and s.condition_on_sort_id not in known_sort_ids:
                raise ValueError(
                    f"SortDimension {s.sort_id!r} conditions on unknown sort_id "
                    f"{s.condition_on_sort_id!r}"
                )
        for leg in self.legs:
            for referenced_sort_id in leg.selector:
                if referenced_sort_id not in known_sort_ids:
                    raise ValueError(
                        f"PortfolioLeg {leg.leg_id!r} selector references unknown "
                        f"sort_id {referenced_sort_id!r}"
                    )
        return self


# --- 6.9 Reported results -----------------------------------------------------


class Estimand(str, Enum):
    MEAN_RETURN = "mean_return"
    SPREAD = "spread"
    ALPHA = "alpha"
    COEFFICIENT = "coefficient"
    SHARPE = "sharpe"
    OTHER = "other"


class AdjustmentModel(str, Enum):
    """Must line up 1:1 with backtest engine output names (D5)."""

    RAW = "raw"
    CAPM = "capm"
    FF3 = "ff3"
    FF5 = "ff5"
    FF6 = "ff6"
    OTHER = "other"  # Engine doesn't produce this -- Step7 marks as non-comparable.


class Unit(str, Enum):
    DECIMAL = "decimal"
    PERCENT = "percent"
    BASIS_POINTS = "basis_points"


class MetricStatistic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["t_stat", "standard_error", "p_value"]
    value: float


class ReportedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    label: str
    estimand: Estimand
    adjustment_model: AdjustmentModel
    #: Which weighting the paper's own table column this number comes from
    #: (ew/vw), so Step2 review can catch `primary_metric_id` pointing at a
    #: number computed under a DIFFERENT weighting than `portfolio.weighting`
    #: (Step7 would otherwise compare our track against the wrong column).
    #: `None` = paper doesn't distinguish or the extractor couldn't tell --
    #: never guess.
    weighting: WeightingScheme | None = None
    estimate: float
    unit: Unit
    frequency: TimeUnit
    statistic: MetricStatistic | None = None
    sample_period: Period
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.UNSPECIFIED

    @model_validator(mode="after")
    def _table_only_has_table_ref(self) -> ReportedMetric:
        if self.status == EvidenceStatus.TABLE_ONLY:
            has_table_ref = any(e.table_ref is not None for e in self.evidence)
            if not has_table_ref:
                raise ValueError(
                    f"ReportedMetric {self.metric_id!r} has status=table_only but no "
                    "evidence entry carries a table_ref"
                )
        return self


class ReportedResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric_id: str
    metrics: list[ReportedMetric] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _primary_metric_exists(self) -> ReportedResults:
        ids = [m.metric_id for m in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError(f"ReportedResults.metrics has duplicate metric_id values: {ids}")
        if self.metrics and self.primary_metric_id not in ids:
            raise ValueError(
                f"primary_metric_id {self.primary_metric_id!r} not found in metrics {ids}"
            )
        return self


# --- 6.1 (cont'd) Top-level MethodSpec ----------------------------------


class MethodSpec(BaseModel):
    """Step 1 output. Immutable paper facts only -- no physical mappings, no
    review state, no engine defaults. See plan section 6.10 for the full
    field audit vs methodspec.v1.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["methodspec.v2"] = "methodspec.v2"
    factor_id: str
    target_name: str

    paper: PaperRef
    signal: SignalSpec
    data: DataSpec
    sample: SampleSpec
    timing: TimingSpec
    universe: UniverseSpec
    portfolio: PortfolioSpec
    reported_results: ReportedResults
    notes: str = ""

    def content_hash(self) -> str:
        """Deterministic hash of paper-fact content, used by MethodReview /
        ImplementationResolution to detect staleness (D1, D2).
        """
        payload = self.model_dump(mode="json", exclude={"notes"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def make_factor_id(document_id: str, target_name: str) -> str:
        """D7: factor_id = sha256(paper_ref + "::" + target_name)[:16]."""
        digest = hashlib.sha256(f"{document_id}::{target_name}".encode()).hexdigest()
        return digest[:16]


# --- 6.11 MethodReview --------------------------------------------------------


class Disposition(str, Enum):
    # `BLOCKED` was removed 2026-08-10 along with D4 (engine-capability
    # blocking, see docs/decision-log.md) -- no finding-producing code path
    # can reach it anymore; an out-of-menu choice is now recorded via
    # `SourcedValue.unsupported_value` instead of being blocked.
    AUTO_APPROVE = "auto_approve"
    APPROVE_WITH_DEFAULT = "approve_with_default"
    NEEDS_LLM_REVIEW = "needs_llm_review"
    NEEDS_HUMAN_CONFIRMATION = "needs_human_confirmation"


# D2: 5x2 disposition matrix (EvidenceStatus x EmpiricalImpact), replacing
# v1's 6x2 matrix (SINGLE and WEAK_OR_CONFLICTING removed -- see plan 6.0).
EMPIRICAL_IMPACT_HIGH = "high"
EMPIRICAL_IMPACT_LOW = "low"

DISPOSITION_MATRIX: dict[tuple[EvidenceStatus, str], Disposition] = {
    (EvidenceStatus.CLEAR, EMPIRICAL_IMPACT_LOW): Disposition.AUTO_APPROVE,
    (EvidenceStatus.CLEAR, EMPIRICAL_IMPACT_HIGH): Disposition.AUTO_APPROVE,
    (EvidenceStatus.TABLE_ONLY, EMPIRICAL_IMPACT_LOW): Disposition.AUTO_APPROVE,
    (EvidenceStatus.TABLE_ONLY, EMPIRICAL_IMPACT_HIGH): Disposition.AUTO_APPROVE,
    (EvidenceStatus.INFERRED, EMPIRICAL_IMPACT_LOW): Disposition.APPROVE_WITH_DEFAULT,
    (EvidenceStatus.INFERRED, EMPIRICAL_IMPACT_HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
    (EvidenceStatus.UNSPECIFIED, EMPIRICAL_IMPACT_LOW): Disposition.APPROVE_WITH_DEFAULT,
    (EvidenceStatus.UNSPECIFIED, EMPIRICAL_IMPACT_HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
    (EvidenceStatus.CONFLICTING, EMPIRICAL_IMPACT_LOW): Disposition.NEEDS_LLM_REVIEW,
    (EvidenceStatus.CONFLICTING, EMPIRICAL_IMPACT_HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    kind: Literal["ambiguous", "unsupported", "missing_mapping", "inconsistent"]
    reason: str = ""
    empirical_impact: Literal["high", "low"]
    disposition: Disposition
    paper_value: Any = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class MethodReview(BaseModel):
    """Step 2 output."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["methodreview.v2"] = "methodreview.v2"
    factor_id: str
    capability_version: str
    findings: list[Finding] = Field(default_factory=list)
    #: One `Finding` per `high_impact_sourced_values` field, UNCONDITIONALLY
    #: (including `AUTO_APPROVE` ones, which `findings` above omits) -- lets
    #: the review UI show every high-impact field's current value, gating
    #: editability on `disposition` rather than on "did it produce a
    #: finding". Purely additive: `findings` keeps meaning "needs your
    #: attention" for existing badge/blocking logic.
    all_high_impact_fields: list[Finding] = Field(default_factory=list)
    status_overrides: dict[str, EvidenceStatus] = Field(default_factory=dict)
    reextraction_attempts: int = 0


# --- 6.11 ImplementationResolution --------------------------------------------


class SourceColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    column: str


class ResolutionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    expected_old_value: Any = None
    new_value: Any = None
    reason: str = ""
    reviewer: str = ""
    resolved_at: datetime


class Substitution(BaseModel):
    """An explicitly-approved standard-engine approximation for a paper
    method the engine cannot execute as stated (D4). `original_method`
    itself stays blocked; this records the parallel approximated track.
    """

    model_config = ConfigDict(extra="forbid")

    field_path: str
    paper_value: str
    substituted_value: str
    reason: str
    approved_by: str


class ImplementationResolution(BaseModel):
    """Physical mappings + human decisions. Append-only entries list;
    never mutates MethodSpec or MethodReview in place.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["resolution.v2"] = "resolution.v2"
    factor_id: str

    concept_mapping: dict[str, SourceColumn] = Field(default_factory=dict)
    returns_source: str = ""
    cz_acronym: str | None = None
    #: concept_ids in `concept_mapping` that the deterministic exact/substring
    #: matcher (`DataDictionary.normalize_fields`) could NOT resolve on its
    #: own -- only an LLM catalog-menu match (`normalize_fields_with_llm`,
    #: hard-validated against real registered sources/columns) filled them
    #: in. Surfaced so a human can specifically re-check these picks instead
    #: of trusting every entry in `concept_mapping` equally.
    llm_matched_concepts: list[str] = Field(default_factory=list)

    entries: list[ResolutionEntry] = Field(default_factory=list)
    approved_substitutions: list[Substitution] = Field(default_factory=list)


# --- 6.11 (cont'd) ResolvedMethodSpec (D1: rebuilt on read, never persisted) --


# Capability matrix version string for the initial engine capability set
# (D4: characteristic sort, up to 2 quantile-grouped sort dimensions --
# matches BacktestExecutor.assign_portfolios_multi's actual implementation
# in src/infra/backtest_engine/__init__.py, which supports exactly 2
# dimensions, dimension-0-conditional sequential or independent; see
# docs/decision-log.md 2026-08-07 entry. Raise this only after the engine
# itself executes a 3rd dimension -- otherwise ResolvedMethodSpec.is_ready
# would pass a MethodSpec the engine can't actually run.)
CAPABILITY_VERSION_V1 = "engine_capability.v1"

MAX_SUPPORTED_SORT_DIMENSIONS = 2

#: Columns the (only) supported returns panel (`CrspReturnsUniverse`/
#: `build_crsp_monthly_panel_ciz`) actually supplies, i.e. what
#: `BacktestExecutor.filter_universe` can evaluate a universe filter against
#: today. A filter resolving to any OTHER column (e.g. a Compustat-only
#: field like a listing-duration screen) is `kind="unsupported"` -- the
#: engine has no eligibility-panel join to bring it in yet -- and blocks
#: `is_ready` unless a human explicitly records `FilterSpec.
#: accepted_unapplied` (the same "paper vocabulary vs engine menu"
#: escape-hatch pattern as `WeightingScheme.OTHER` etc.). This is
#: deliberately a small static list, not a data-layer lookup -- adding real
#: eligibility-panel support (loading+joining other sources here) is
#: out of scope for now; this constant only decides what CAN'T run yet.
RETURNS_PANEL_NATIVE_COLUMNS: frozenset[str] = frozenset(
    {"permno", "yyyymm", "ret", "me", "exchcd", "shrcd", "siccd", "dlret"}
)

#: Paper vocabulary -> CRSP physical code, for a universe filter whose
#: resolved column IS a `RETURNS_PANEL_NATIVE_COLUMNS` member but whose
#: `FilterSpec.value` is still the paper's own wording (e.g. `["NYSE",
#: "Amex", "NASDAQ"]` against the numeric `exchcd` column) -- see
#: docs/resolve-diagnostics-gaps.md problem 3. Keys are matched case-
#: insensitively by `registry._translate_filter_value`. Hand-registered
#: once per physical column and reused across every paper -- deliberately
#: NOT LLM-inferred (see docs/decision-log.md 2026-08-12 "value-encoding
#: mapping" entry): this is an external data-vendor coding convention, not
#: something extractable/verifiable from the paper's own text. `siccd` is
#: deliberately excluded -- industry exclusions are usually SIC *ranges*
#: (e.g. financials = 6000-6999), a different shape than a single-code
#: label map, and need a real industry-to-range table, not this.
FILTER_VALUE_ENCODINGS: dict[str, dict[str, int]] = {
    "exchcd": {"nyse": 1, "amex": 2, "nasdaq": 3},
    "shrcd": {"common stock": 10, "common shares": 10, "ordinary common shares": 11},
}


class ResolvedMethodSpec(BaseModel):
    """Deterministic aggregate view of the three source artifacts (D1).

    Rebuilt in memory on every use -- Step3/Step4/Step5 never read a cached
    "resolved" file from disk. Callers MAY write this out as an audit
    snapshot (e.g. runs/resolved/<timestamp>_<factor>.json) for debugging,
    but that snapshot is an output artifact, never read back in.
    """

    model_config = ConfigDict(extra="forbid")

    paper: MethodSpec
    review: MethodReview
    resolution: ImplementationResolution

    @model_validator(mode="after")
    def _factor_ids_consistent(self) -> ResolvedMethodSpec:
        ids = {self.paper.factor_id, self.review.factor_id, self.resolution.factor_id}
        if len(ids) != 1:
            raise ValueError(f"factor_id mismatch across paper/review/resolution: {ids}")
        return self

    def unmapped_concepts(self) -> list[str]:
        """Concept ids that `registry._resolved_column` will need at
        build_config time but that `resolution.concept_mapping` has no entry
        for -- surfaced so the resolve UI can tell a human exactly what's
        blocking `is_ready`, instead of a bare boolean.
        """
        signal_input_concepts = {
            f.concept_id for f in self.paper.data.fields if FieldRole.SIGNAL_INPUT in f.roles
        }
        universe_filter_concepts = {
            f.concept_id for f in self.paper.universe.filters if not f.accepted_unapplied
        }
        non_target_sort_concepts = {
            s.concept_id for s in self.paper.portfolio.sorts if s.role != SortRole.TARGET
        }
        required = signal_input_concepts | universe_filter_concepts | non_target_sort_concepts
        return sorted(required - self.resolution.concept_mapping.keys())

    def unsupported_universe_filters(self) -> list[str]:
        """Concept ids of every APPLIED (not `accepted_unapplied`) universe
        filter that DOES resolve to a physical column (so it's not already
        caught by `unmapped_concepts`), but whose column can't actually be
        supplied to `filter_universe` at runtime -- either it's a
        CRSP-native column (`RETURNS_PANEL_NATIVE_COLUMNS`, already on the
        panel, trivially fine) or a REAL registered physical column of its
        source (2026-08-13: the generated script now point-in-time joins
        any such column onto the returns panel BEFORE `filter_universe`
        runs -- see `registry._universe_filter_join_sources`/
        `script_generator.join_universe_filter_sources` -- the same
        mechanism `compute_signal`'s own input already used). What remains
        genuinely unsupported is a `SourceColumn` naming a column that isn't
        even registered in `catalog.DATA_CATALOG` for its source -- there is
        no way to load it at all. Same posture as a D4 engine-capability
        finding either way: register the missing catalog column, or
        explicitly mark the filter `accepted_unapplied=True` with a reason.
        """
        out = []
        for f in self.paper.universe.filters:
            if f.accepted_unapplied:
                continue
            mapping = self.resolution.concept_mapping.get(f.concept_id)
            if mapping is None or mapping.column in RETURNS_PANEL_NATIVE_COLUMNS:
                continue
            registered_columns = catalog.DATA_CATALOG.get(mapping.source, {}).get("physical_columns", set())
            if mapping.column not in registered_columns:
                out.append(f.concept_id)
        return out

    def _universe_filters_supported(self) -> bool:
        return not self.unsupported_universe_filters()

    def _all_concepts_mapped(self) -> bool:
        # Universe filters and non-target sort dimensions also go through
        # `registry._resolved_column(resolution, concept_id)` at build_config
        # time -- an unmapped concept there previously slipped past is_ready
        # (only signal-input concepts were checked) and only surfaced as a
        # confusing step3 "no physical column mapping" 400 later. Require
        # these to be mapped too, so a genuinely-unresolvable concept (e.g. a
        # derived eligibility rule with no physical column at all) blocks
        # resolution at the source instead.
        return not self.unmapped_concepts()

    @property
    def is_ready(self) -> bool:
        """Replaces v1's `codegen_ready` boolean flag -- derived, not stored.
        No longer checks a paper/review/resolution hash-binding (staleness
        detection was removed 2026-08-09 -- see docs/decision-log.md); a
        review/resolution computed against an EARLIER version of the paper
        is silently treated as still valid here.

        Construction capability (sort dimension count, `group_type`,
        `sort.mode`, `rebalance_frequency`, `lag_unit`) is deliberately NOT
        checked here anymore (`_construction_within_capability` removed
        2026-08-12, see docs/resolve-diagnostics-gaps.md problem 2): an
        out-of-menu value for any of those is auto-clamped to a documented
        default by `registry.build_config`, recorded in `defaults_applied`,
        and surfaced as a non-blocking Finding -- the same "record, don't
        block" posture the weighting/return_combination/breakpoints.basis/
        missing_action menu fields already had since the 2026-08-10 D4
        removal.
        """
        return (
            self._all_concepts_mapped()
            and self._universe_filters_supported()
        )

