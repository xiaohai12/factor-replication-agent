"""Shared test-only helper for dual-dispatch spec field access (not a
test_*.py file, so pytest won't collect it as a test module)."""

from __future__ import annotations

from src.infra.models.method_spec import (
    ConstructionType,
    DataAvailability,
    DataSpec,
    Estimand,
    AdjustmentModel,
    BreakpointSpec,
    EvidenceStatus,
    FieldRole,
    FormulaSpec,
    CalculationStep,
    GroupType,
    ImplementationResolution,
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


def spec_factor_id(spec) -> str:
    return spec.paper.factor_id if isinstance(spec, ResolvedMethodSpec) else spec.factor_id


def minimal_resolved_spec(
    factor_id: str = "t", weighting: str = "vw", breakpoint_source: str = "nyse",
    concept_source: str = "comp_funda", concept_column: str = "x",
) -> ResolvedMethodSpec:
    """A generic, fully-`is_ready` minimal `ResolvedMethodSpec` for tests that
    just need SOME valid spec-agnostic-infra fixture (dual-track controller,
    repair loop, sandbox, script generator, etc.) -- mirrors
    `test_meta_coder_resolved_method_spec._resolved_spec()` but with an
    explicit, arbitrary `factor_id` (not derived via `make_factor_id`)."""
    period = Period(start_year=1968, end_year=2003)
    paper = MethodSpec(
        factor_id=factor_id,
        target_name=factor_id,
        paper=PaperRef(document_id="doc", title="Test Paper", citation="Test 2020", publication_year=2020),
        signal=SignalSpec(
            definition=SourcedValue(value="(x_t - x_t-1) / x_t-1", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="test", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.POSITIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(
                paper_expression="(x_t - x_t-1) / x_t-1",
                steps=[CalculationStep(step_id="s1", description="compute ratio", expression="(x - x_lag1) / x_lag1")],
                inputs=["x"], output_concept=factor_id,
            ),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[RequiredField(concept_id="x", paper_name="test field", paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT])],
        ),
        sample=SampleSpec(data_coverage=period, formation=period, reported_returns=period),
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
                    sort_id="sort1", concept_id="x", role=SortRole.TARGET, order=1,
                    mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=10,
                    breakpoints=BreakpointSpec(basis=SourcedValue(value=breakpoint_source, status=EvidenceStatus.CLEAR)),
                )
            ],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"sort1": 9}),
                PortfolioLeg(leg_id="short", side="short", selector={"sort1": 0}),
            ],
            weighting=SourcedValue(value=weighting, status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="extreme_group_spread", status=EvidenceStatus.CLEAR),
        ),
        reported_results=ReportedResults(
            primary_metric_id="m1",
            metrics=[
                ReportedMetric(
                    metric_id="m1", label="L-H spread", estimand=Estimand.SPREAD,
                    adjustment_model=AdjustmentModel.RAW, estimate=0.005, unit=Unit.DECIMAL,
                    frequency=TimeUnit.MONTH, statistic=MetricStatistic(kind="t_stat", value=3.0),
                    sample_period=period, status=EvidenceStatus.TABLE_ONLY,
                    evidence=[EvidenceCitation(table_ref=TableRef(table="Table 1", row="L-H"))],
                )
            ],
        ),
    )
    review = review_method_spec(paper)
    resolution = ImplementationResolution(
        factor_id=paper.factor_id,
        concept_mapping={"x": SourceColumn(source=concept_source, column=concept_column)},
        returns_source="us_equity_crsp",
    )
    return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


def asset_growth_resolved_spec(factor_id: str = "cooper_gulen_schill_2008_asset_growth") -> ResolvedMethodSpec:
    """Paper-first equivalent of `tests/fixtures/method_specs/
    cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json` -- same
    economics (formation month 6, annual rebalance, 6-month accounting lag,
    VW, 10 deciles, long=lowest/short=highest asset-growth decile), so it
    resolves to the same `registry.build_config` dict and reproduces the
    same golden numbers from `asset_growth_synthetic_data.expected_metrics()`
    against the SAME plugin (`tests/fixtures/plugins/
    cooper_gulen_schill_2008_asset_growth.py`, spec-agnostic compute_signal
    code)."""
    period = Period(start_year=1968, end_year=2002)
    paper = MethodSpec(
        factor_id=factor_id,
        target_name="asset_growth",
        paper=PaperRef(
            document_id="cooper_gulen_schill_2008", title="Asset Growth and the Cross Section of Stock Returns",
            citation="Cooper, Gulen, and Schill 2008, JF 63(4)", publication_year=2008,
        ),
        signal=SignalSpec(
            definition=SourcedValue(value="ASSETG(t) = [Data6(t-1) - Data6(t-2)] / Data6(t-2)", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="overextrapolation of past asset growth", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.NEGATIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(
                paper_expression="ASSETG(t) = [Data6(t-1) - Data6(t-2)] / Data6(t-2)",
                steps=[CalculationStep(step_id="s1", description="asset growth ratio", expression="(at_t_minus_1 - at_t_minus_2) / at_t_minus_2")],
                inputs=["total_assets"], output_concept="asset_growth",
            ),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[RequiredField(concept_id="total_assets", paper_name="Total assets", paper_source_hint="Compustat data item 6", roles=[FieldRole.SIGNAL_INPUT])],
        ),
        sample=SampleSpec(data_coverage=period, formation=period, reported_returns=period),
        timing=TimingSpec(
            formation_rule=SourcedValue(value="end of June each year", status=EvidenceStatus.CLEAR),
            formation_month=SourcedValue(value=6, status=EvidenceStatus.CLEAR),
            rebalance_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            holding_period=SourcedValue(value=12, status=EvidenceStatus.CLEAR),
            data_availability=DataAvailability(lag_value=6, lag_unit=TimeUnit.MONTH),
        ),
        universe=UniverseSpec(description=SourcedValue(value="NYSE/Amex/NASDAQ nonfinancial firms", status=EvidenceStatus.CLEAR)),
        portfolio=PortfolioSpec(
            construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT, status=EvidenceStatus.CLEAR),
            sorts=[
                SortDimension(
                    sort_id="assetg", concept_id="total_assets", role=SortRole.TARGET, order=1,
                    mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=10,
                    breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
                )
            ],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"assetg": 0}),
                PortfolioLeg(leg_id="short", side="short", selector={"assetg": 9}),
            ],
            weighting=SourcedValue(value="vw", status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="extreme_group_spread", status=EvidenceStatus.CLEAR),
        ),
        reported_results=ReportedResults(
            primary_metric_id="m1",
            metrics=[
                ReportedMetric(
                    metric_id="m1", label="low-high spread", estimand=Estimand.SPREAD,
                    adjustment_model=AdjustmentModel.RAW, estimate=0.0045, unit=Unit.DECIMAL,
                    frequency=TimeUnit.MONTH, statistic=MetricStatistic(kind="t_stat", value=3.2),
                    sample_period=period, status=EvidenceStatus.TABLE_ONLY,
                    evidence=[EvidenceCitation(table_ref=TableRef(table="Table II", row="1-10"))],
                )
            ],
        ),
    )
    review = review_method_spec(paper)
    resolution = ImplementationResolution(
        factor_id=paper.factor_id,
        concept_mapping={"total_assets": SourceColumn(source="comp_funda", column="at")},
        returns_source="us_equity_crsp",
    )
    return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


def accruals_resolved_spec() -> ResolvedMethodSpec:
    """Paper-first equivalent of `tests/fixtures/method_specs/
    sloan_1996_accruals.resolved.methodspec.json` -- same economics as
    `asset_growth_resolved_spec` (formation month 6, annual rebalance,
    6-month lag, VW, 10 deciles, long=low/short=high), just a 6-concept
    signal formula, so it reuses the SAME golden numbers from
    `asset_growth_synthetic_data.expected_metrics()` (see
    `tests/synthetic_data/accruals_synthetic_data.py`'s docstring)."""
    period = Period(start_year=1962, end_year=1991)
    concepts = ["current_assets", "current_liabilities", "cash", "short_term_debt", "depreciation", "total_assets"]
    columns = {"current_assets": "act", "current_liabilities": "lct", "cash": "che",
               "short_term_debt": "dlc", "depreciation": "dp", "total_assets": "at"}
    paper = MethodSpec(
        factor_id="sloan_1996_accruals",
        target_name="accruals",
        paper=PaperRef(
            document_id="sloan_1996", title="Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?",
            citation="Sloan 1996, The Accounting Review 71(3)", publication_year=1996,
        ),
        signal=SignalSpec(
            definition=SourcedValue(value="accruals scaled by average total assets", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="earnings driven by accruals are less persistent", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.NEGATIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(
                paper_expression="((ΔCA - ΔCash) - (ΔCL - ΔSTD) - Dep) / avg(AT)",
                steps=[CalculationStep(step_id="s1", description="accruals ratio", expression="((act-che)-(lct-dlc)-dp)/((at+at_lag)/2)")],
                inputs=concepts, output_concept="accruals",
            ),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[
                RequiredField(concept_id=c, paper_name=c, paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT])
                for c in concepts
            ],
        ),
        sample=SampleSpec(data_coverage=period, formation=period, reported_returns=period),
        timing=TimingSpec(
            formation_rule=SourcedValue(value="annually in July", status=EvidenceStatus.CLEAR),
            formation_month=SourcedValue(value=6, status=EvidenceStatus.CLEAR),
            rebalance_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            holding_period=SourcedValue(value=12, status=EvidenceStatus.CLEAR),
            data_availability=DataAvailability(lag_value=6, lag_unit=TimeUnit.MONTH),
        ),
        universe=UniverseSpec(description=SourcedValue(value="NYSE/Amex/NASDAQ nonfinancial firms", status=EvidenceStatus.CLEAR)),
        portfolio=PortfolioSpec(
            construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT, status=EvidenceStatus.CLEAR),
            sorts=[
                SortDimension(
                    sort_id="accruals", concept_id="total_assets", role=SortRole.TARGET, order=1,
                    mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE, group_count=10,
                    breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
                )
            ],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"accruals": 0}),
                PortfolioLeg(leg_id="short", side="short", selector={"accruals": 9}),
            ],
            weighting=SourcedValue(value="vw", status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="extreme_group_spread", status=EvidenceStatus.CLEAR),
        ),
        reported_results=ReportedResults(
            primary_metric_id="m1",
            metrics=[
                ReportedMetric(
                    metric_id="m1", label="low-high accruals spread", estimand=Estimand.SPREAD,
                    adjustment_model=AdjustmentModel.RAW, estimate=0.0055, unit=Unit.DECIMAL,
                    frequency=TimeUnit.MONTH, statistic=MetricStatistic(kind="t_stat", value=2.71),
                    sample_period=period, status=EvidenceStatus.TABLE_ONLY,
                    evidence=[EvidenceCitation(table_ref=TableRef(table="Table", row="1-10"))],
                )
            ],
        ),
    )
    review = review_method_spec(paper)
    resolution = ImplementationResolution(
        factor_id=paper.factor_id,
        concept_mapping={c: SourceColumn(source="comp_funda", column=columns[c]) for c in concepts},
        returns_source="us_equity_crsp",
    )
    return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)
