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

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Enums ---


class RebalanceFrequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    UNSPECIFIED = "unspecified"


class WeightingRule(str, Enum):
    EQUAL_WEIGHTED = "ew"
    VALUE_WEIGHTED = "vw"
    UNSPECIFIED = "unspecified"


class BreakpointSource(str, Enum):
    NYSE = "nyse"
    FULL_SAMPLE = "full_sample"
    UNSPECIFIED = "unspecified"


class PortfolioConstructionType(str, Enum):
    """Mirrors prompts/extractor/methodspec_extractor.md Allowed Values for
    portfolio.construction_type. Keep this vocabulary in sync with that
    prompt file.

    Only `characteristic_sort` has a standard engine implementation
    (portfolio-sort estimator) -- the Fama-MacBeth cross-sectional-regression
    estimator (`regression_weighted`) was removed to keep the engine to one
    standard path (see docs/decision-log.md); an unrecognized/other value is
    clamped to `characteristic_sort` by `registry.build_config`.
    """

    CHARACTERISTIC_SORT = "characteristic_sort"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


class ReturnCombinationType(str, Enum):
    """Mirrors prompts/extractor/methodspec_extractor.md Allowed Values for
    return_combination.type. Keep this vocabulary in sync with that prompt file."""

    EXTREME_GROUP_SPREAD = "extreme_group_spread"
    AVERAGE_LEG_SPREAD = "average_leg_spread"
    SINGLE_SIGNAL_PORTFOLIO_RETURN = "single_signal_portfolio_return"
    FULL_PORTFOLIO_RETURN = "full_portfolio_return"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


class FilterOp(str, Enum):
    """Mirrors prompts/extractor/methodspec_extractor.md Allowed Values for
    universe.filters[].op. Keep this vocabulary in sync with that prompt file."""

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


class MissingAction(str, Enum):
    DROP = "drop"
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
    RESOLVE_EXISTING_JSON = "resolve_existing_json"
    TARGETED_REEXTRACTION = "targeted_reextraction"
    FULL_REGENERATION = "full_regeneration"


def _coerce_enum_field(data: Any, field_name: str, enum_cls: type[Enum]) -> Any:
    """Tolerantly map an unexpected raw value to "other"/"unspecified" before
    Pydantic validation runs, so an LLM-produced value that doesn't match the
    allowed vocabulary (prompts/extractor/methodspec_extractor.md Allowed
    Values) degrades gracefully instead of raising a hard ValidationError.
    """
    if not isinstance(data, dict) or field_name not in data:
        return data
    value = data.get(field_name)
    if value is None or isinstance(value, enum_cls):
        return data
    valid_values = {member.value for member in enum_cls}
    if value not in valid_values:
        data = dict(data)
        data[field_name] = "other" if "other" in valid_values else "unspecified"
    return data


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


class DataSpec(BaseModel):
    """Data references extracted from the paper.

    These hints are paper-first and audit-oriented. Codegen should consume a
    normalized implementation config rather than these strings directly.
    """

    sources: list[DataSourceHint] = Field(default_factory=list)
    required_fields: list[RequiredFieldSpec] = Field(default_factory=list)
    normalized_mapping: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Output from Data Catalog / Normalizer, not extractor-owned. "
            "Maps a paper concept to its physical source+column. Two forms are "
            "accepted: the richer {concept: {'source': 'comp_funda', 'column': "
            "'act'}} (records WHICH source each field comes from, so the loader "
            "knows what to read and how to join), or the legacy {concept: "
            "'act'} plain-column form (source looked up in the data catalog by "
            "physical column; an UNKNOWN column resolves to no source and is "
            "hard-blocked at review — never silently guessed). See "
            "MethodSpec.resolved_sources()."
        ),
    )


def _normalize_mapping_entry(value: Any) -> tuple[str, str]:
    """Return (source, column) for a single normalized_mapping value.

    Accepts the richer form {"source": ..., "column": ...} or a legacy plain
    column string. For the plain form the source is looked up in the data
    catalog by physical column (`catalog.source_of_column`): only a REGISTERED
    source that actually declares the column resolves it; an unknown column
    returns source="" (unresolved). We deliberately do NOT fall back to
    "comp_funda" — that old binary guess silently misattributed
    IBES/OptionMetrics/etc. columns to Compustat. Unresolved-source formula
    fields are hard-blocked by the reviewer (see
    ReviewGate._check_source_mapping_resolved)."""
    if isinstance(value, dict):
        return str(value.get("source", "") or ""), str(value.get("column", "") or "")
    col = str(value)
    from src.infra.data_layer import catalog

    return catalog.source_of_column(col), col


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
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class MissingPolicy(BaseModel):
    action: MissingAction = Field(default=MissingAction.UNSPECIFIED)
    threshold: Optional[float] = None
    winsorize_bounds: Optional[tuple[float, float]] = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _tolerate_legacy_action(cls, data: Any) -> Any:
        # The engine is standardized to drop NaNs; legacy fill_*/winsorize
        # actions are no longer distinct enum members. Map any unknown action
        # to "unspecified" (build_config then clamps it to "drop").
        return _coerce_enum_field(data, "action", MissingAction)


class SignalSpec(BaseModel):
    """The factor signal definition that the Meta-Coder translates to code."""

    formula: str | FormulaSpec = Field(default_factory=FormulaSpec)
    required_fields: list[str] = Field(default_factory=list)
    timing: SignalTiming = Field(default_factory=SignalTiming)
    missing_policy: MissingPolicy = Field(default_factory=MissingPolicy)
    sign: Optional[int] = Field(
        default=None,
        description="1=high signal is long, -1=low signal is long",
    )

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


class PortfolioSortSpec(BaseModel):
    breakpoint_source: BreakpointSource = Field(default=BreakpointSource.UNSPECIFIED)
    ls_quantile: Optional[float] = None
    quantiles: list[int] = Field(default_factory=list)
    evidence: list[EvidenceCitation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _tolerate_legacy_breakpoint_source(cls, data: Any) -> Any:
        # Legacy conditional/paper_specific breakpoint sources are no longer
        # menu members; map any unknown value to "unspecified" (build_config
        # clamps it to the default).
        return _coerce_enum_field(data, "breakpoint_source", BreakpointSource)


class UniverseFilterSpec(BaseModel):
    """Row-level sample restriction, mirrors universe.filters[] from the
    extraction prompt schema (prompts/extractor/methodspec_extractor.md).

    Applied deterministically by the standardized engine's universe filter step
    (`steps.apply_universe_filters`) via the FilterOp DSL.
    """

    field: str
    op: FilterOp = Field(default=FilterOp.NONMISSING)
    value: Any = None
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class ReturnCombinationSpec(BaseModel):
    """How per-portfolio returns combine into the reported factor return.

    Lives under `portfolio.return_combination`. `type` is clamped to the
    standard menu by `registry.build_config`.
    """

    type: ReturnCombinationType = Field(default=ReturnCombinationType.UNSPECIFIED)
    expression: str = Field(default="")
    long_leg: str = Field(default="")
    short_leg: str = Field(default="")
    note: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_unknown_type(cls, data: Any) -> Any:
        data = _coerce_enum_field(data, "type", ReturnCombinationType)
        # Some curated specs store long_leg/short_leg/expression/note as null;
        # these are plain strings here, so coerce None -> "".
        if isinstance(data, dict):
            data = dict(data)
            for k in ("expression", "long_leg", "short_leg", "note"):
                if data.get(k) is None and k in data:
                    data[k] = ""
        return data


class PortfolioSpec(BaseModel):
    universe: str = Field(default="unspecified")
    universe_filters: list[UniverseFilterSpec] = Field(default_factory=list)
    sort: PortfolioSortSpec = Field(default_factory=PortfolioSortSpec)
    weighting: WeightingRule = Field(default=WeightingRule.UNSPECIFIED)
    long_leg: str = Field(default="high")
    short_leg: str = Field(default="low")
    implied_factor_direction: str | dict[str, Any] = Field(default="")

    #: Portfolio-return construction (flattened from the former
    #: reported_results.return_calculation.portfolio_return). Drives the
    #: engine's estimator/sort/combine selection via registry.build_config.
    construction_type: PortfolioConstructionType = Field(
        default=PortfolioConstructionType.UNSPECIFIED
    )
    return_combination: ReturnCombinationSpec = Field(default_factory=ReturnCombinationSpec)

    evidence: list[EvidenceCitation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _tolerate_unknown_construction_type(cls, data: Any) -> Any:
        return _coerce_enum_field(data, "construction_type", PortfolioConstructionType)


class ReportedResultsSpec(BaseModel):
    """Paper-reported results, kept for validation against the backtest.

    Portfolio-construction fields (sorts, return_combination, construction_type)
    now live on `PortfolioSpec`; this model records only what the paper *reported*.
    """

    return_horizon: str = Field(default="monthly")
    return_type: str = Field(default="long_short_spread")
    spreads: list[float] | dict[str, Any] = Field(default_factory=list)
    t_stats: list[float] | dict[str, Any] = Field(default_factory=list)
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


class ResolutionLogEntry(BaseModel):
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
    sign: Optional[int] = Field(default=None)
    sample_start_year: Optional[int] = None
    sample_end_year: Optional[int] = None
    publication_year: Optional[int] = None
    cz_acronym: Optional[str] = Field(default=None)

    #: Which stock-return universe the portfolio-construction/return side runs
    #: on. Must name an entry registered in
    #: `src.infra.data_layer.catalog.RETURNS_UNIVERSES` (e.g. "us_equity_crsp").
    #: There is deliberately NO default: the returns universe comes from the
    #: reviewed spec, never a hardcoded CRSP fallback — the reviewer hard-blocks
    #: a spec that leaves this unset or names an unregistered universe.
    returns_universe: Optional[str] = None

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
    resolution_log: list[ResolutionLogEntry] = Field(default_factory=list)

    #: How many times this spec has been targeted-re-extracted by the
    #: Review -> Extractor loop (bounded; see src/pipeline.py run_full_pipeline).
    reextraction_attempts: int = 0

    @model_validator(mode="before")
    @classmethod
    def normalize_curated_schema(cls, data: Any) -> Any:
        """Accept the richer curated annotation schema as MethodSpec input."""
        if not isinstance(data, dict):
            return data

        data = dict(data)
        paper = data.get("paper") if isinstance(data.get("paper"), dict) else {}
        raw_signal = data.get("signal") if isinstance(data.get("signal"), dict) else {}
        raw_timing = data.get("timing") if isinstance(data.get("timing"), dict) else {}
        raw_universe = data.get("universe") if isinstance(data.get("universe"), dict) else {}
        raw_portfolio = data.get("portfolio") if isinstance(data.get("portfolio"), dict) else {}

        # Back-compat: portfolio-return construction (construction_type / sorts /
        # return_combination) used to live nested under
        # reported_results.return_calculation.portfolio_return; it now lives flat
        # on `portfolio`. Lift the legacy nested fields onto raw_portfolio (never
        # overwriting a value already set flat) so old JSON keeps loading.
        rr = data.get("reported_results")
        rc = rr.get("return_calculation") if isinstance(rr, dict) else None
        pr = rc.get("portfolio_return") if isinstance(rc, dict) else None
        if isinstance(pr, dict):
            raw_portfolio = dict(raw_portfolio)
            if raw_portfolio.get("construction_type") is None and pr.get("construction_type") is not None:
                raw_portfolio["construction_type"] = pr.get("construction_type")
            if not raw_portfolio.get("return_combination") and pr.get("return_combination"):
                raw_portfolio["return_combination"] = pr.get("return_combination")
            data["portfolio"] = raw_portfolio

        data.setdefault("factor_name", raw_signal.get("factor_name") or data.get("factor_id", ""))
        data.setdefault("paper_ref", paper.get("citation", ""))

        definition = raw_signal.get("definition")
        if isinstance(definition, dict):
            data.setdefault("detailed_definition", definition.get("value", ""))
        elif isinstance(definition, str):
            data.setdefault("detailed_definition", definition)

        intuition = raw_signal.get("economic_intuition")
        if isinstance(intuition, dict):
            data.setdefault("economic_intuition", intuition.get("value", ""))
        elif isinstance(intuition, str):
            data.setdefault("economic_intuition", intuition)

        sign = raw_signal.get("sign")
        if isinstance(sign, dict):
            data.setdefault("sign", cls._normalize_sign(sign.get("value")))
        elif sign is not None:
            data.setdefault("sign", cls._normalize_sign(sign))

        sample = data.get("sample") if isinstance(data.get("sample"), dict) else {}
        formation_years = sample.get("formation_years")
        if isinstance(formation_years, dict):
            data.setdefault("sample_start_year", formation_years.get("start"))
            data.setdefault("sample_end_year", formation_years.get("end"))

        if raw_signal and "timing" not in raw_signal:
            formula = raw_signal.get("formula")
            if isinstance(formula, dict) and "source" in formula and "evidence" not in formula:
                formula = dict(formula)
                formula["evidence"] = [formula["source"]]

            missing_policy = raw_universe.get("missing_policy")
            if isinstance(missing_policy, dict) and "source" in missing_policy:
                missing_policy = dict(missing_policy)
                missing_policy["evidence"] = [missing_policy["source"]]

            raw_signal["formula"] = formula
            raw_signal["timing"] = {
                "formation_month": (
                    raw_timing.get("formation", {}).get("month")
                    if isinstance(raw_timing.get("formation"), dict)
                    else None
                ),
                "rebalance_frequency": cls._normalize_rebalance_frequency(
                    raw_timing.get("rebalance_frequency", "unspecified")
                ),
                "holding_period": raw_timing.get("holding_period_months"),
                "accounting_lag": raw_timing.get("accounting_lag_months"),
                "evidence": [raw_timing["source"]] if isinstance(raw_timing.get("source"), dict) else [],
            }
            raw_signal["missing_policy"] = missing_policy or {}
            if isinstance(raw_signal["missing_policy"], dict):
                raw_signal["missing_policy"]["action"] = cls._normalize_missing_action(
                    raw_signal["missing_policy"].get("action", "unspecified")
                )
            if isinstance(sign, dict):
                raw_signal["sign"] = cls._normalize_sign(sign.get("value"))
            elif sign is not None:
                raw_signal["sign"] = cls._normalize_sign(sign)

            inputs = formula.get("inputs", []) if isinstance(formula, dict) else []
            if inputs and not raw_signal.get("required_fields"):
                raw_signal["required_fields"] = inputs

            data["signal"] = raw_signal

        if raw_portfolio:
            sort = raw_portfolio.get("sort") if isinstance(raw_portfolio.get("sort"), dict) else {}
            implied_direction = raw_portfolio.get("implied_factor_direction")
            long_leg = raw_portfolio.get("long_leg")
            short_leg = raw_portfolio.get("short_leg")
            if isinstance(implied_direction, dict):
                long_leg = long_leg or implied_direction.get("long_leg", "high")
                short_leg = short_leg or implied_direction.get("short_leg", "low")

            weights = raw_portfolio.get("weights")
            weighting = raw_portfolio.get("weighting") or raw_portfolio.get("weighting_scheme")
            if not weighting and isinstance(weights, list) and weights:
                weighting = weights[0]

            raw_universe_filters = raw_universe.get("filters", [])
            derived_universe_filters = []
            if isinstance(raw_universe_filters, list):
                for f in raw_universe_filters:
                    if not isinstance(f, dict):
                        continue
                    derived_universe_filters.append({
                        "field": f.get("field", ""),
                        "op": f.get("op", "nonmissing"),
                        "value": f.get("value"),
                        "evidence": [f["source"]] if isinstance(f.get("source"), dict) else [],
                    })
            # Prefer universe_filters already stored directly under portfolio
            # (e.g. resolved/curated specs) over the raw top-level
            # universe.filters[] (e.g. fresh extractor output); don't let an
            # empty top-level universe.filters[] silently wipe out
            # already-resolved data.
            universe_filters = raw_portfolio.get("universe_filters") or derived_universe_filters

            data["portfolio"] = {
                **raw_portfolio,
                "universe": raw_universe.get("description", raw_portfolio.get("universe", "unspecified")),
                "universe_filters": universe_filters,
                "sort": {
                    "breakpoint_source": cls._normalize_breakpoint_source(
                        sort.get("breakpoint_source", "unspecified")
                    ),
                    "ls_quantile": cls._normalize_ls_quantile(sort.get("ls_quantile")),
                    "quantiles": sort.get("quantiles", []),
                    "evidence": [sort["source"]] if isinstance(sort.get("source"), dict) else [],
                },
                "weighting": cls._normalize_weighting(weighting or "unspecified"),
                "long_leg": long_leg or "high",
                "short_leg": short_leg or "low",
                "implied_factor_direction": implied_direction or "",
            }

        raw_data = data.get("data")
        if isinstance(raw_data, dict):
            normalized_fields = []
            for item in raw_data.get("required_fields", []):
                if not isinstance(item, dict):
                    normalized_fields.append(item)
                    continue
                normalized_fields.append({
                    **item,
                    "concept": item.get("concept") or item.get("description", ""),
                })
            raw_data["required_fields"] = normalized_fields
            data["data"] = raw_data

        extraction_sources = data.get("extraction_sources")
        if not extraction_sources and paper:
            data["extraction_sources"] = [
                {
                    "type": "paper",
                    "ref": paper.get("pdf_file") or paper.get("title") or data.get("paper_ref", ""),
                    "sections": paper.get("evidence_sections") or paper.get("paper_sections") or [],
                }
            ]

        ambiguous_fields = data.get("ambiguous_fields")
        if isinstance(ambiguous_fields, list):
            normalized_ambiguous = []
            for item in ambiguous_fields:
                if not isinstance(item, dict):
                    normalized_ambiguous.append(item)
                    continue
                source = item.get("source")
                status = cls._normalize_evidence_source(item.get("status"))
                impact = item.get("impact", item.get("empirical_impact", "high"))
                normalized_ambiguous.append({
                    **item,
                    "source": status if isinstance(status, str) else item.get("source_status", "inferred"),
                    "empirical_impact": "high" if impact == "medium" else impact,
                    "evidence": [source] if isinstance(source, dict) else item.get("evidence", []),
                })
            data["ambiguous_fields"] = normalized_ambiguous

        return data

    @staticmethod
    def _normalize_breakpoint_source(value: Any) -> Any:
        if value in {"nyse", "nyse_only"}:
            return "nyse"
        if value in {"full_sample", "all_stocks", "all_eligible"}:
            return "full_sample"
        # conditional/paper_specific are no longer menu members -> unspecified
        # (build_config clamps to the default).
        return "unspecified"

    @staticmethod
    def _normalize_weighting(value: Any) -> Any:
        if isinstance(value, dict):
            value = value.get("type") or value.get("value") or value.get("name") or "unspecified"
        if value in {"ew", "equal_weight", "equal_weighted", "equal-weighted"}:
            return "ew"
        if value in {"vw", "value_weight", "value_weighted", "value-weighted"}:
            return "vw"
        # capped_vw / other custom schemes are not menu members -> unspecified
        # (build_config clamps to the default).
        return "unspecified"

    @staticmethod
    def _normalize_missing_action(value: Any) -> Any:
        if value in {"drop", "exclude", "omit"}:
            return "drop"
        # fill_*/winsorize are no longer menu members: the engine is
        # standardized to drop NaNs -> unspecified (build_config clamps to drop).
        return "unspecified"

    @staticmethod
    def _normalize_evidence_source(value: Any) -> Any:
        if value == "explicit":
            return "clear"
        if value == "ambiguous":
            return "weak_or_conflicting"
        if value in {"inferred_for_backtest_not_paper_stated", "not_main_spec"}:
            return "inferred"
        return value

    @staticmethod
    def _normalize_rebalance_frequency(value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized.startswith("monthly"):
                return "monthly"
            if normalized.startswith("quarterly"):
                return "quarterly"
            if normalized.startswith("annual") or normalized.startswith("yearly"):
                return "annual"
        return value

    @staticmethod
    def _normalize_sign(value: Any) -> Any:
        if value in {"positive", "+", "+1"}:
            return 1
        if value in {"negative", "-", "-1"}:
            return -1
        return value

    @staticmethod
    def _normalize_ls_quantile(value: Any) -> Any:
        if isinstance(value, str):
            if "-" not in value:
                try:
                    return float(value)
                except ValueError:
                    return None
            first = value.split("-", 1)[0]
            try:
                n_groups = float(first)
            except ValueError:
                return None
            if n_groups > 0:
                return 1.0 / n_groups
            return None
        return value

    def model_post_init(self, __context: Any) -> None:
        self.signal.sign = self.sign
        if not self.data.required_fields and self.signal.required_fields:
            self.data.required_fields = [
                RequiredFieldSpec(field=field)
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

    def resolved_sources(self) -> dict[str, list[tuple[str, str]]]:
        """Group `data.normalized_mapping` by physical source.

        Returns {source_name: [(concept, column), ...]} for every mapped field,
        supporting both the richer {concept: {"source","column"}} form and the
        legacy {concept: "column"} form (source inferred, see
        `_normalize_mapping_entry`).

        The data loader uses this to read ONLY the needed columns from each
        source and join each source into the CRSP backbone; ReviewGate uses it
        to verify every source is one the loader knows how to join (see
        `SIGNAL_SOURCES`)."""
        groups: dict[str, list[tuple[str, str]]] = {}
        for concept, value in (self.data.normalized_mapping or {}).items():
            source, column = _normalize_mapping_entry(value)
            if not column:
                continue
            groups.setdefault(source, []).append((concept, column))
        return groups

    def unresolved_source_fields(self) -> list[tuple[str, str]]:
        """Formula-mapping entries whose SOURCE could not be resolved from the
        data catalog (source==""), i.e. a physical column no registered source
        declares. Returns [(concept, column), ...].

        These are exactly the fields the reviewer must HARD-BLOCK: the source
        of every signal input must come from the reviewed spec / registered
        catalog, never a silent default. An empty list means every mapped
        field resolved to a known source (or the mapping is empty)."""
        return self.resolved_sources().get("", [])

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
    def missing_action(self) -> MissingAction:
        return self.signal.missing_policy.action

    @property
    def breakpoint_source(self) -> BreakpointSource:
        return self.portfolio.sort.breakpoint_source

    @property
    def weighting_rule(self) -> WeightingRule:
        return self.portfolio.weighting

    @property
    def universe_description(self) -> str:
        return self.portfolio.universe

    def stable_hash(self) -> str:
        """Hash the audit-relevant MethodSpec content for registry provenance."""
        payload = self.model_dump(mode="json", exclude={"review_notes", "resolution_log"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
