"""Phase D tests: `registry.build_config`'s `ResolvedMethodSpec` dispatch
(`_build_config_from_resolved`) -- the first concrete piece of wiring
Step3+ up to the paper-first models. Not yet used by `src.pipeline`/
`MetaCoder`/`step6_dual_track_controller` (see docs/methodspec-v2-plan.md
section 9, Phase D); this only locks the new resolution function's
contract, including a real end-to-end run through `BacktestExecutor` for
both the single-sort and double-sort cases.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor
from src.infra.models.method_spec import (
    AdjustmentModel,
    BreakpointSpec,
    ConstructionType,
    DataAvailability,
    DataSpec,
    Estimand,
    EvidenceStatus,
    FieldRole,
    FilterOp,
    FilterSpec,
    FormulaSpec,
    GroupType,
    ImplementationResolution,
    MethodReview,
    Period,
    MethodSpec,
    PaperRef,
    PortfolioLeg,
    PortfolioSpec,
    ReportedMetric,
    ReportedResults,
    RequiredField,
    ResolvedMethodSpec,
    SampleSpec,
    SignalCategory,
    SignalDirection,
    SignalSpec,
    SortDimension,
    SortMode,
    SortRole,
    SourceColumn,
    SourcedValue,
    MetricStatistic,
    TableRef,
    EvidenceCitation,
    TimeUnit,
    TimingSpec,
    TransformKind,
    TransformSpec,
    TransformStage,
    Unit,
    UniverseSpec,
)
from src.steps.step2_reviewer.review import review_method_spec
from src.steps.step3_codegen.registry import build_config


def _period() -> Period:
    return Period(start_year=1968, end_year=2003)


def _reported_results() -> ReportedResults:
    return ReportedResults(
        primary_metric_id="m1",
        metrics=[
            ReportedMetric(
                metric_id="m1", label="L-H spread", estimand=Estimand.SPREAD,
                adjustment_model=AdjustmentModel.RAW, estimate=0.0045, unit=Unit.DECIMAL,
                frequency=TimeUnit.MONTH, statistic=MetricStatistic(kind="t_stat", value=3.2),
                sample_period=_period(), status=EvidenceStatus.TABLE_ONLY,
                evidence=[EvidenceCitation(table_ref=TableRef(table="Table 3", row="L-H"))],
            )
        ],
    )


def _single_sort_spec() -> MethodSpec:
    factor_id = MethodSpec.make_factor_id("cooper2008", "asset_growth")
    return MethodSpec(
        factor_id=factor_id,
        target_name="asset_growth",
        paper=PaperRef(document_id="cooper2008", title="Asset Growth...", citation="Cooper et al 2008", publication_year=2008),
        signal=SignalSpec(
            definition=SourcedValue(value="(AT_t - AT_t-1) / AT_t-1", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="overinvestment", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.NEGATIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(paper_expression="(AT_t - AT_t-1) / AT_t-1", inputs=["at"], output_concept="asset_growth"),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[
                RequiredField(concept_id="at", name_in_paper="total assets", paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT]),
            ],
        ),
        sample=SampleSpec(data_coverage=_period(), formation=_period(), reported_returns=_period()),
        timing=TimingSpec(
            formation_rule=SourcedValue(value="every June", status=EvidenceStatus.CLEAR),
            formation_month=SourcedValue(value=6, status=EvidenceStatus.CLEAR),
            rebalance_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            holding_period=SourcedValue(value=12, status=EvidenceStatus.CLEAR),
            data_availability=DataAvailability(lag_value=6, lag_unit=TimeUnit.MONTH),
        ),
        universe=UniverseSpec(description=SourcedValue(value="NYSE/AMEX/NASDAQ", status=EvidenceStatus.CLEAR)),
        portfolio=PortfolioSpec(
            construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT, status=EvidenceStatus.CLEAR),
            sorts=[
                SortDimension(
                    sort_id="sort1", concept_id="at", role=SortRole.TARGET, order=1,
                    mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=10,
                    breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
                )
            ],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"sort1": 0}),
                PortfolioLeg(leg_id="short", side="short", selector={"sort1": 9}),
            ],
            weighting=SourcedValue(value="vw", status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="extreme_group_spread", status=EvidenceStatus.CLEAR),
        ),
        reported_results=_reported_results(),
    )


def _resolved(paper: MethodSpec, concept_mapping: dict[str, SourceColumn], returns_source: str = "us_equity_crsp") -> ResolvedMethodSpec:
    review = review_method_spec(paper)
    resolution = ImplementationResolution(
        factor_id=paper.factor_id, concept_mapping=concept_mapping,
        returns_source=returns_source,
    )
    return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


class TestBuildConfigSingleSort:
    def test_resolves_expected_keys(self):
        resolved = _resolved(_single_sort_spec(), {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)

        assert config["breakpoint_source"] == "nyse"
        assert config["breakpoint_quantiles"] == 10
        assert config["weighting_rule"] == "vw"
        assert config["rebalance_frequency"] == "annual"
        assert config["holding_period_months"] == 12
        assert config["accounting_lag_months"] == 6
        assert config["formation_month"] == 6
        assert config["formation_month_explicit"] is True
        assert config["return_combination_type"] == "extreme_group_spread"
        assert config["long_leg"] == "low"
        assert config["long_portfolios"] == [1]
        assert config["short_portfolios"] == [10]
        assert "sort_dims" not in config

    def test_unmapped_universe_filter_concept_fails_loudly(self):
        """Formula-input concepts (e.g. `at`) are only needed by codegen, not
        by build_config -- but a universe_filter concept IS resolved here
        (`_resolved_column`), so use that to exercise the fail-loud path."""
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=[1, 2])
        )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        with pytest.raises(ValueError, match="listing_exchange"):
            build_config(resolved, None)

    def test_defaults_applied_when_lag_unspecified(self):
        paper = _single_sort_spec()
        paper.timing.data_availability = DataAvailability()
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["accounting_lag_months"] == 6
        assert any(d["config_key"] == "accounting_lag_months" for d in config.get("defaults_applied", []))


class TestBuildConfigTransforms:
    """`PortfolioSpec.transforms` -> `config["transforms"]`/
    `config["unapplied_transforms"]`. Regression coverage for the bug where
    `transforms` was resolved onto the spec but had no `KNOWN_CONFIG_KEYS`
    entry, so `build_config` silently dropped it and the engine never
    applied the 5 Dichev-1998-oscore winsorize transforms extraction
    actually produced."""

    def test_supported_winsorize_after_signal_lands_in_transforms(self):
        paper = _single_sort_spec()
        paper.portfolio.transforms.append(
            TransformSpec(kind=TransformKind.WINSORIZE, stage=TransformStage.AFTER_SIGNAL, bounds=(0.01, 0.99))
        )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["transforms"] == [
            {"kind": "winsorize", "stage": "after_signal", "bounds": [0.01, 0.99]}
        ]
        assert config["unapplied_transforms"] == []

    def test_unsupported_kind_lands_in_unapplied_not_silently_dropped(self):
        paper = _single_sort_spec()
        paper.portfolio.transforms.append(
            TransformSpec(kind=TransformKind.STANDARDIZE, stage=TransformStage.AFTER_SIGNAL, bounds=None)
        )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["transforms"] == []
        assert config["unapplied_transforms"] == [
            {
                "kind": "standardize",
                "stage": "after_signal",
                "bounds": None,
                "reason": "engine has no implementation for this transform kind/stage combination",
            }
        ]

    def test_unsupported_stage_lands_in_unapplied_not_silently_dropped(self):
        paper = _single_sort_spec()
        paper.portfolio.transforms.append(
            TransformSpec(kind=TransformKind.WINSORIZE, stage=TransformStage.BEFORE_SIGNAL, bounds=(0.01, 0.99))
        )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["transforms"] == []
        assert len(config["unapplied_transforms"]) == 1
        assert config["unapplied_transforms"][0]["stage"] == "before_signal"

    def test_no_transforms_declared_yields_empty_lists(self):
        resolved = _resolved(_single_sort_spec(), {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["transforms"] == []
        assert config["unapplied_transforms"] == []


class TestUniverseFilterValueEncodingTranslation:
    """docs/resolve-diagnostics-gaps.md problem 3: a universe filter's
    physical column may be a registered `RETURNS_PANEL_NATIVE_COLUMNS`
    member but its `value` is still the paper's own wording (e.g.
    "NYSE"/"Amex"/"NASDAQ" against numeric `exchcd`) -- translated via
    `FILTER_VALUE_ENCODINGS`, never silently passed through as-is."""

    def _resolved_with_exchange_filter(self, value):
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=value)
        )
        return _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "listing_exchange": SourceColumn(source="crsp_msf", column="exchcd"),
        })

    def test_paper_vocabulary_translated_to_physical_codes(self):
        resolved = self._resolved_with_exchange_filter(["NYSE", "Amex", "NASDAQ"])
        config = build_config(resolved, None)
        assert config["universe_filters"] == [{"field": "exchcd", "op": "in", "value": [1, 2, 3]}]

    def test_translation_is_case_insensitive(self):
        resolved = self._resolved_with_exchange_filter(["nyse", "AMEX"])
        config = build_config(resolved, None)
        assert config["universe_filters"][0]["value"] == [1, 2]

    def test_already_numeric_value_passes_through_unchanged(self):
        resolved = self._resolved_with_exchange_filter([1, 2, 3])
        config = build_config(resolved, None)
        assert config["universe_filters"][0]["value"] == [1, 2, 3]

    def test_unregistered_label_fails_loud_not_silently_all_false(self):
        resolved = self._resolved_with_exchange_filter(["NYSE", "Some Regional Exchange"])
        with pytest.raises(ValueError, match="Some Regional Exchange"):
            build_config(resolved, None)

    def test_column_without_registered_encoding_passes_value_through(self):
        """`me` (market equity) has no registered encoding -- values pass
        through unchanged, whatever they are (numeric filters on it are
        already unambiguous)."""
        paper = _single_sort_spec()
        paper.universe.filters.append(FilterSpec(concept_id="size_floor", op=FilterOp.GTE, value=100))
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "size_floor": SourceColumn(source="crsp_msf", column="me"),
        })
        config = build_config(resolved, None)
        assert config["universe_filters"][0] == {"field": "me", "op": "gte", "value": 100}

    def test_intervals_passes_through_to_runtime_config(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(concept_id="sic", op=FilterOp.INTERVALS, value=[[1, 3999], [5000, 5999]])
        )
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "sic": SourceColumn(source="crsp_msf", column="siccd"),
        })
        config = build_config(resolved, None)
        assert config["universe_filters"] == [
            {"field": "siccd", "op": "intervals", "value": [[1, 3999], [5000, 5999]]}
        ]


class TestAcceptedUnappliedUniverseFilter:
    """`FilterSpec.accepted_unapplied` -- the "other" escape hatch: a human
    explicitly records that a stated universe restriction is NOT applied,
    instead of it crashing `build_config`/the engine. Never set implicitly."""

    def test_unapplied_filter_needs_no_concept_mapping_and_never_crashes(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(
                concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2,
                accepted_unapplied=True, unapplied_reason="no eligibility-panel wiring yet",
            )
        )
        # No concept_mapping entry at all for compustat_listing_duration --
        # would fail loudly if this filter were treated as applied.
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["universe_filters"] == []
        assert config["unapplied_universe_filters"] == [
            {
                "concept_id": "compustat_listing_duration", "op": "gte", "value": 2,
                "reason": "no eligibility-panel wiring yet",
            }
        ]

    def test_unapplied_filter_concept_is_not_required_by_is_ready(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(
                concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2,
                accepted_unapplied=True, unapplied_reason="no eligibility-panel wiring yet",
            )
        )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        assert "compustat_listing_duration" not in resolved.unmapped_concepts()

    def test_mixed_applied_and_unapplied_filters(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(
            FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=[1, 2])
        )
        paper.universe.filters.append(
            FilterSpec(
                concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2,
                accepted_unapplied=True, unapplied_reason="no eligibility-panel wiring yet",
            )
        )
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "listing_exchange": SourceColumn(source="crsp_msf", column="exchcd"),
        })
        config = build_config(resolved, None)
        assert config["universe_filters"] == [{"field": "exchcd", "op": "in", "value": [1, 2]}]
        assert len(config["unapplied_universe_filters"]) == 1
        assert config["unapplied_universe_filters"][0]["concept_id"] == "compustat_listing_duration"


class TestUniverseFilterJoinSources:
    """A universe filter resolved to a REAL registered non-native column
    (e.g. compustat_fundamental_annual.at) is joined onto the returns panel by the generated
    script (2026-08-13) instead of being blocked -- `build_config` records
    which {source: [columns]} the script needs to join."""

    def test_registered_non_native_column_recorded_for_join(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(FilterSpec(concept_id="total_assets", op=FilterOp.GTE, value=0))
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "total_assets": SourceColumn(source="compustat_fundamental_annual", column="at"),
        })
        config = build_config(resolved, None)
        assert config["universe_filter_join_sources"] == {"compustat_fundamental_annual": ["at"]}

    def test_native_column_needs_no_join(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=[1, 2]))
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "listing_exchange": SourceColumn(source="crsp_msf", column="exchcd"),
        })
        config = build_config(resolved, None)
        assert config["universe_filter_join_sources"] == {}

    def test_unregistered_column_is_not_recorded_for_join(self):
        paper = _single_sort_spec()
        paper.universe.filters.append(FilterSpec(concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2))
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "compustat_listing_duration": SourceColumn(source="compustat_fundamental_annual", column="listing_duration_years"),
        })
        config = build_config(resolved, None)
        assert config["universe_filter_join_sources"] == {}


def _double_sort_spec() -> MethodSpec:
    paper = _single_sort_spec()
    size_sort = SortDimension(
        sort_id="size", concept_id="me", role=SortRole.CONDITIONING, order=1,
        mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
        breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
    )
    target_sort = SortDimension(
        sort_id="sort1", concept_id="at", role=SortRole.TARGET, order=2,
        mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
        breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
    )
    paper.portfolio.sorts = [size_sort, target_sort]
    paper.portfolio.legs = [
        PortfolioLeg(leg_id="long", side="long", selector={"sort1": 0}),
        PortfolioLeg(leg_id="short", side="short", selector={"sort1": 1}),
    ]
    paper.data.fields.append(
        RequiredField(concept_id="me", name_in_paper="market equity", paper_source_hint="CRSP", roles=[FieldRole.WEIGHTING_INPUT])
    )
    return paper


class TestEngineMenuAutoClamp:
    """docs/resolve-diagnostics-gaps.md problem 2: every engine-menu field
    (group_type, sort.mode, rebalance_frequency, lag_unit, sort-dimension
    count) auto-clamps to a documented default when off-menu, recorded in
    `defaults_applied`, never blocking `is_ready`/`build_config`."""

    def test_non_quantile_group_type_is_recorded_not_executed_differently(self):
        paper = _single_sort_spec()
        paper.portfolio.sorts[0].group_type = SourcedValue(value=GroupType.CATEGORICAL, status=EvidenceStatus.CLEAR)
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert any(
            d["config_key"] == "sorts[0].group_type" and d["value"] == "quantile"
            for d in config.get("defaults_applied", [])
        )

    def test_within_group_mode_passed_through_not_defaulted(self):
        paper = _single_sort_spec()
        size_sort = SortDimension(
            sort_id="size", concept_id="me", role=SortRole.CONDITIONING, order=2,
            mode=SourcedValue(value=SortMode.WITHIN_GROUP, status=EvidenceStatus.CLEAR),
            group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
            breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
        )
        paper.portfolio.sorts.append(size_sort)
        paper.data.fields.append(
            RequiredField(concept_id="me", name_in_paper="market equity", paper_source_hint="CRSP", roles=[FieldRole.WEIGHTING_INPUT])
        )
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "me": SourceColumn(source="crsp_msf", column="me"),
        })
        config = build_config(resolved, None)
        conditioning_dim = next(d for d in config["sort_dims"] if d["role"] == "conditioning")
        assert conditioning_dim["mode"] == "within_group"
        # never silently coerced to sequential/independent, no defaults_applied entry
        assert not any(d["config_key"].endswith(".mode") for d in config.get("defaults_applied", []))

    def test_other_mode_clamped_to_independent_and_recorded(self):
        """`sort_dims` is only built when there are >=2 sorts -- add a second
        dimension so the clamped `mode` is actually observable in config."""
        paper = _single_sort_spec()
        paper.portfolio.sorts[0].mode = SourcedValue(
            value=SortMode.OTHER, unsupported_value="some novel relationship", status=EvidenceStatus.CLEAR,
        )
        paper.portfolio.sorts.append(
            SortDimension(
                sort_id="size", concept_id="me", role=SortRole.CONDITIONING, order=2,
                mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR),
                group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
                breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
            )
        )
        paper.data.fields.append(
            RequiredField(concept_id="me", name_in_paper="market equity", paper_source_hint="CRSP", roles=[FieldRole.WEIGHTING_INPUT])
        )
        resolved = _resolved(paper, {
            "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
            "me": SourceColumn(source="crsp_msf", column="me"),
        })
        config = build_config(resolved, None)
        target_dim = next(d for d in config["sort_dims"] if d["role"] == "target")
        assert target_dim["mode"] == "independent"
        assert target_dim["independent"] is True
        assert any(d["config_key"] == "sorts[0].mode" for d in config.get("defaults_applied", []))

    def test_daily_rebalance_frequency_clamps_to_monthly_and_is_recorded(self):
        paper = _single_sort_spec()
        paper.timing.rebalance_frequency = SourcedValue(value=TimeUnit.DAY, status=EvidenceStatus.CLEAR)
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["rebalance_frequency"] == "monthly"
        assert any(d["config_key"] == "rebalance_frequency" for d in config.get("defaults_applied", []))

    def test_daily_lag_unit_defaults_to_6_months_with_honest_reason(self):
        paper = _single_sort_spec()
        paper.timing.data_availability = DataAvailability(lag_value=5, lag_unit=TimeUnit.DAY)
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        assert config["accounting_lag_months"] == 6
        entry = next(d for d in config["defaults_applied"] if d["config_key"] == "accounting_lag_months")
        assert "5" in entry["reason"] and "day" in entry["reason"]
        assert "unspecified" not in entry["reason"]

    def test_excess_sort_dimensions_are_clamped_to_max_keeping_target(self):
        paper = _single_sort_spec()
        for i in range(2):
            paper.portfolio.sorts.append(
                SortDimension(
                    sort_id=f"extra{i}", concept_id="at", role=SortRole.CONTROL, order=i + 2,
                    mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR),
                    group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
                    breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
                )
            )
        resolved = _resolved(paper, {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        assert resolved.is_ready
        config = build_config(resolved, None)
        assert len(config["sort_dims"]) == 2
        assert any(d["config_key"] == "sort_dims" for d in config.get("defaults_applied", []))


class TestBuildConfigDoubleSort:
    def test_resolves_sort_dims_in_order(self):
        resolved = _resolved(
            _double_sort_spec(),
            {"at": SourceColumn(source="compustat_fundamental_annual", column="at"), "me": SourceColumn(source="crsp_msf", column="me")},
        )
        config = build_config(resolved, None)
        assert [d["column"] for d in config["sort_dims"]] == ["me", "signal"]
        assert [d["role"] for d in config["sort_dims"]] == ["conditioning", "target"]
        assert config["long_portfolios"] == [1]
        assert config["short_portfolios"] == [2]

    def test_breakpoint_quantiles_override_remaps_target_sort_dim(self):
        """`sort_dims`'s target entry (`quantiles: 2`, from `_double_sort_
        spec`'s target `group_count`) is built once at resolution time from
        the paper's OWN `breakpoint_quantiles` -- must be re-derived
        alongside `long_portfolios`/`short_portfolios` when an override
        changes it, or the engine would sort the target dimension into the
        OLD bucket count while the (correctly remapped) short leg asks for a
        bucket number that only exists under the NEW count -- same
        empty-result failure as the single-sort case, for double-sort
        factors. The `conditioning` dim (`me`, unrelated to
        `breakpoint_quantiles`) must NOT change. See docs/decision-log.md
        2026-08-22."""
        resolved = _resolved(
            _double_sort_spec(),
            {"at": SourceColumn(source="compustat_fundamental_annual", column="at"), "me": SourceColumn(source="crsp_msf", column="me")},
        )
        config = build_config(resolved, overrides={"breakpoint_quantiles": 4})
        assert config["long_portfolios"] == [1]
        assert config["short_portfolios"] == [4]
        by_role = {d["role"]: d for d in config["sort_dims"]}
        assert by_role["target"]["quantiles"] == 4
        assert by_role["conditioning"]["quantiles"] == 2


class TestBuildConfigEndToEnd:
    """A real BacktestExecutor.run_with_config() call, config built entirely
    from a ResolvedMethodSpec -- proves the dispatch actually produces a
    config the engine can execute, not just the right dict shape."""

    def _panel(self) -> pd.DataFrame:
        permnos = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        return pd.concat([
            pd.DataFrame({
                "permno": permnos, "yyyymm": [200106] * 10,
                "me": [float(100 + p) for p in permnos], "exchcd": [1] * 10, "ret": [0.0] * 10,
            }),
            pd.DataFrame({
                "permno": permnos, "yyyymm": [200107] * 10,
                "me": [float(100 + p) for p in permnos], "exchcd": [1] * 10,
                "ret": [0.01 * p for p in permnos],
            }),
        ], ignore_index=True)

    def _signal(self) -> pd.DataFrame:
        return pd.DataFrame({
            "permno": list(range(1, 11)), "yyyymm": [200106] * 10,
            "signal": [float(p) for p in range(1, 11)],
        })

    def test_single_sort_end_to_end(self):
        resolved = _resolved(_single_sort_spec(), {"at": SourceColumn(source="compustat_fundamental_annual", column="at")})
        config = build_config(resolved, None)
        config["weighting_rule"] = "ew"

        engine = BacktestExecutor()
        result = engine.run_with_config(self._signal(), config, data=self._panel())
        assert result["metrics"]["n_months"] == 1

    def test_double_sort_end_to_end(self):
        """`me` and `signal` must be decorrelated within each other's
        buckets, or the double-sort combine step has no within-size-group
        signal spread to average (see docs/decision-log.md 2026-08-07 --
        same mechanics as tests/test_double_sort_engine.py's 2x2 fixture)."""
        resolved = _resolved(
            _double_sort_spec(),
            {"at": SourceColumn(source="compustat_fundamental_annual", column="at"), "me": SourceColumn(source="crsp_msf", column="me")},
        )
        config = build_config(resolved, None)
        config["weighting_rule"] = "ew"

        permnos = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        me = [10, 11, 12, 13, 14, 90, 91, 92, 93, 94]
        signal_vals = [1.0, 6.0, 2.0, 7.0, 3.0, 8.0, 4.0, 9.0, 5.0, 10.0]
        panel = pd.concat([
            pd.DataFrame({"permno": permnos, "yyyymm": [200106] * 10, "me": [float(m) for m in me], "exchcd": [1] * 10, "ret": [0.0] * 10}),
            pd.DataFrame({"permno": permnos, "yyyymm": [200107] * 10, "me": [float(m) for m in me], "exchcd": [1] * 10, "ret": [0.01 * p for p in permnos]}),
        ], ignore_index=True)
        signal = pd.DataFrame({"permno": permnos, "yyyymm": [200106] * 10, "signal": signal_vals})

        engine = BacktestExecutor()
        result = engine.run_with_config(signal, config, data=panel)
        assert result["metrics"]["n_months"] == 1
