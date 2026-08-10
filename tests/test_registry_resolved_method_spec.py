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
                RequiredField(concept_id="at", paper_name="total assets", paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT]),
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
                    mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=10,
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
        resolved = _resolved(_single_sort_spec(), {"at": SourceColumn(source="comp_funda", column="at")})
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
        resolved = _resolved(paper, {"at": SourceColumn(source="comp_funda", column="at")})
        with pytest.raises(ValueError, match="listing_exchange"):
            build_config(resolved, None)

    def test_defaults_applied_when_lag_unspecified(self):
        paper = _single_sort_spec()
        paper.timing.data_availability = DataAvailability()
        resolved = _resolved(paper, {"at": SourceColumn(source="comp_funda", column="at")})
        config = build_config(resolved, None)
        assert config["accounting_lag_months"] == 6
        assert any(d["config_key"] == "accounting_lag_months" for d in config.get("defaults_applied", []))


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
        resolved = _resolved(paper, {"at": SourceColumn(source="comp_funda", column="at")})
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
        resolved = _resolved(paper, {"at": SourceColumn(source="comp_funda", column="at")})
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
            "at": SourceColumn(source="comp_funda", column="at"),
            "listing_exchange": SourceColumn(source="crsp_msf", column="exchcd"),
        })
        config = build_config(resolved, None)
        assert config["universe_filters"] == [{"field": "exchcd", "op": "in", "value": [1, 2]}]
        assert len(config["unapplied_universe_filters"]) == 1
        assert config["unapplied_universe_filters"][0]["concept_id"] == "compustat_listing_duration"


def _double_sort_spec() -> MethodSpec:
    paper = _single_sort_spec()
    size_sort = SortDimension(
        sort_id="size", concept_id="me", role=SortRole.CONDITIONING, order=1,
        mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=2,
        breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
    )
    target_sort = SortDimension(
        sort_id="sort1", concept_id="at", role=SortRole.TARGET, order=2,
        mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=2,
        breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
    )
    paper.portfolio.sorts = [size_sort, target_sort]
    paper.portfolio.legs = [
        PortfolioLeg(leg_id="long", side="long", selector={"sort1": 0}),
        PortfolioLeg(leg_id="short", side="short", selector={"sort1": 1}),
    ]
    paper.data.fields.append(
        RequiredField(concept_id="me", paper_name="market equity", paper_source_hint="CRSP", roles=[FieldRole.WEIGHTING_INPUT])
    )
    return paper


class TestBuildConfigDoubleSort:
    def test_resolves_sort_dims_in_order(self):
        resolved = _resolved(
            _double_sort_spec(),
            {"at": SourceColumn(source="comp_funda", column="at"), "me": SourceColumn(source="crsp_msf", column="me")},
        )
        config = build_config(resolved, None)
        assert [d["column"] for d in config["sort_dims"]] == ["me", "signal"]
        assert [d["role"] for d in config["sort_dims"]] == ["conditioning", "target"]
        assert config["long_portfolios"] == [1]
        assert config["short_portfolios"] == [2]


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
        resolved = _resolved(_single_sort_spec(), {"at": SourceColumn(source="comp_funda", column="at")})
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
            {"at": SourceColumn(source="comp_funda", column="at"), "me": SourceColumn(source="crsp_msf", column="me")},
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
