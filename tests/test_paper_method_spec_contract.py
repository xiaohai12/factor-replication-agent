"""Phase A contract tests for the paper-first MethodSpec models (docs/methodspec-v2-plan.md).

Covers: strict extra="forbid" rejection, lossless round-trip, factor_id
hashing (D7), disposition matrix shape (D2), and the representative schema
cases called for by plan section 9 Phase A item 4:
  - simple accounting ratio (single sort, continuous signal)
  - rolling residual signal (estimated category)
  - sequential double sort
  - unsupported custom weighting (recorded via Substitution, D4)

None of these fixtures are wired into the live pipeline (src/steps/*) --
this file only locks the contract itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.infra.models.paper_method_spec import (
    AdjustmentModel,
    BreakpointSpec,
    CalculationStep,
    ConstructionType,
    DataAvailability,
    DataSpec,
    Disposition,
    DISPOSITION_MATRIX,
    Estimand,
    EstimationMethod,
    EstimationSpec,
    EvidenceCitation,
    EvidenceStatus,
    Finding,
    FormulaSpec,
    GroupType,
    ImplementationResolution,
    MethodReview,
    Period,
    PaperMethodSpec,
    PaperRef,
    PortfolioLeg,
    PortfolioSpec,
    ReportedMetric,
    ReportedResults,
    RequiredField,
    FieldRole,
    ResolutionEntry,
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
    Substitution,
    TableRef,
    MetricStatistic,
    TimeUnit,
    TimingSpec,
    Unit,
    UniverseSpec,
    WindowAnchor,
    WindowSpec,
)


def _minimal_period() -> Period:
    return Period(start_year=1968, end_year=2003)


def _minimal_data_spec(concept_id: str = "at") -> DataSpec:
    return DataSpec(
        signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
        return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
        sources=[SourcedValue(value="Compustat", status=EvidenceStatus.CLEAR)],
        fields=[
            RequiredField(
                concept_id=concept_id,
                paper_name="total assets",
                paper_source_hint="Compustat annual",
                roles=[FieldRole.SIGNAL_INPUT],
            )
        ],
    )


def _minimal_timing() -> TimingSpec:
    return TimingSpec(
        formation_rule=SourcedValue(value="every June", status=EvidenceStatus.CLEAR),
        rebalance_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
        holding_period=SourcedValue(value=12, status=EvidenceStatus.CLEAR),
        data_availability=DataAvailability(lag_value=6),
    )


def _minimal_universe() -> UniverseSpec:
    return UniverseSpec(description=SourcedValue(value="NYSE/AMEX/NASDAQ", status=EvidenceStatus.CLEAR))


def _minimal_reported_results() -> ReportedResults:
    return ReportedResults(
        primary_metric_id="m1",
        metrics=[
            ReportedMetric(
                metric_id="m1",
                label="L-H spread",
                estimand=Estimand.SPREAD,
                adjustment_model=AdjustmentModel.RAW,
                estimate=0.0045,
                unit=Unit.DECIMAL,
                frequency=TimeUnit.MONTH,
                statistic=MetricStatistic(kind="t_stat", value=3.2),
                sample_period=_minimal_period(),
                status=EvidenceStatus.TABLE_ONLY,
                evidence=[EvidenceCitation(table_ref=TableRef(table="Table 3", row="L-H"))],
            )
        ],
    )


def _simple_accounting_ratio_spec() -> PaperMethodSpec:
    """Case 1: simple accounting ratio, single characteristic sort."""
    factor_id = PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
    return PaperMethodSpec(
        factor_id=factor_id,
        target_name="asset_growth",
        paper=PaperRef(document_id="cooper2008", title="Asset Growth...", citation="Cooper et al 2008"),
        signal=SignalSpec(
            definition=SourcedValue(value="(AT_t - AT_t-1) / AT_t-1", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="overinvestment", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.NEGATIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(
                paper_expression="(AT_t - AT_t-1) / AT_t-1",
                steps=[
                    CalculationStep(step_id="s1", description="take at, at_lag1", expression="at, at_lag1"),
                    CalculationStep(step_id="s2", description="compute ratio", expression="(at - at_lag1) / at_lag1"),
                ],
                inputs=["at"],
                output_concept="asset_growth",
            ),
        ),
        data=_minimal_data_spec(),
        sample=SampleSpec(data_coverage=_minimal_period(), formation=_minimal_period(), reported_returns=_minimal_period()),
        timing=_minimal_timing(),
        universe=_minimal_universe(),
        portfolio=PortfolioSpec(
            construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT, status=EvidenceStatus.CLEAR),
            sorts=[
                SortDimension(
                    sort_id="sort1",
                    concept_id="at",
                    role=SortRole.TARGET,
                    order=1,
                    mode=SortMode.INDEPENDENT,
                    group_type=GroupType.QUANTILE,
                    group_count=10,
                    breakpoints=BreakpointSpec(population=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
                )
            ],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"sort1": 0}),
                PortfolioLeg(leg_id="short", side="short", selector={"sort1": 9}),
            ],
            weighting=SourcedValue(value="vw", status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="extreme_group_spread", status=EvidenceStatus.CLEAR),
        ),
        reported_results=_minimal_reported_results(),
    )


class TestStrictRejection:
    def test_unknown_top_level_field_rejected(self):
        spec = _simple_accounting_ratio_spec()
        payload = spec.model_dump(mode="json")
        payload["some_unexpected_field"] = "should not survive"
        with pytest.raises(ValidationError):
            PaperMethodSpec.model_validate(payload)

    def test_unknown_nested_field_rejected(self):
        spec = _simple_accounting_ratio_spec()
        payload = spec.model_dump(mode="json")
        payload["signal"]["formula"]["ghost_field"] = 1
        with pytest.raises(ValidationError):
            PaperMethodSpec.model_validate(payload)


class TestRoundTrip:
    def test_lossless_round_trip(self):
        spec = _simple_accounting_ratio_spec()
        dumped = spec.model_dump(mode="json")
        reloaded = PaperMethodSpec.model_validate(dumped)
        assert reloaded == spec

    def test_content_hash_stable_across_round_trip(self):
        spec = _simple_accounting_ratio_spec()
        reloaded = PaperMethodSpec.model_validate(spec.model_dump(mode="json"))
        assert spec.content_hash() == reloaded.content_hash()

    def test_content_hash_changes_on_value_change(self):
        spec = _simple_accounting_ratio_spec()
        h1 = spec.content_hash()
        spec.portfolio.weighting.value = "ew"
        h2 = spec.content_hash()
        assert h1 != h2

    def test_notes_excluded_from_hash(self):
        spec = _simple_accounting_ratio_spec()
        h1 = spec.content_hash()
        spec.notes = "some free-text remark that shouldn't affect the hash"
        assert spec.content_hash() == h1


class TestFactorIdHashing:
    def test_same_paper_and_target_same_id(self):
        id1 = PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
        id2 = PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert id1 == id2

    def test_different_target_different_id(self):
        id1 = PaperMethodSpec.make_factor_id("hirshleifer2012", "patent_emi")
        id2 = PaperMethodSpec.make_factor_id("hirshleifer2012", "citations_emi")
        assert id1 != id2


class TestUniqueIdValidators:
    def test_duplicate_formula_step_ids_rejected(self):
        spec = _simple_accounting_ratio_spec()
        with pytest.raises(ValidationError):
            spec.signal.formula.steps.append(
                CalculationStep(step_id="s1", description="duplicate")
            )
            FormulaSpec.model_validate(spec.signal.formula.model_dump())

    def test_duplicate_sort_ids_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioSpec(
                construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT),
                sorts=[
                    SortDimension(
                        sort_id="dup", concept_id="a", role=SortRole.TARGET, order=1,
                        mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE,
                        breakpoints=BreakpointSpec(population=SourcedValue()),
                    ),
                    SortDimension(
                        sort_id="dup", concept_id="b", role=SortRole.CONTROL, order=2,
                        mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE,
                        breakpoints=BreakpointSpec(population=SourcedValue()),
                    ),
                ],
                legs=[],
                weighting=SourcedValue(),
                return_combination=SourcedValue(),
            )

    def test_leg_selector_referencing_unknown_sort_id_rejected(self):
        with pytest.raises(ValidationError):
            PortfolioSpec(
                construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT),
                sorts=[
                    SortDimension(
                        sort_id="sort1", concept_id="a", role=SortRole.TARGET, order=1,
                        mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE,
                        breakpoints=BreakpointSpec(population=SourcedValue()),
                    ),
                ],
                legs=[PortfolioLeg(leg_id="long", side="long", selector={"nonexistent_sort": 0})],
                weighting=SourcedValue(),
                return_combination=SourcedValue(),
            )


class TestReportedMetrics:
    def test_table_only_requires_table_ref(self):
        with pytest.raises(ValidationError):
            ReportedMetric(
                metric_id="m1", label="x", estimand=Estimand.SPREAD,
                adjustment_model=AdjustmentModel.RAW, estimate=0.01, unit=Unit.DECIMAL,
                frequency=TimeUnit.MONTH, sample_period=_minimal_period(),
                status=EvidenceStatus.TABLE_ONLY, evidence=[EvidenceCitation(quote="no table ref here")],
            )

    def test_primary_metric_must_exist_in_metrics(self):
        with pytest.raises(ValidationError):
            ReportedResults(primary_metric_id="missing", metrics=[])
            ReportedResults.model_validate(
                {"primary_metric_id": "missing", "metrics": [_minimal_reported_results().metrics[0].model_dump()]}
            )

    def test_at_most_four_metrics(self):
        metric = _minimal_reported_results().metrics[0]
        metrics = []
        for i in range(5):
            m = metric.model_copy(update={"metric_id": f"m{i}"})
            metrics.append(m)
        with pytest.raises(ValidationError):
            ReportedResults(primary_metric_id="m0", metrics=metrics)


class TestEstimatedSignalRequiresEstimation:
    def test_estimated_category_without_estimation_rejected(self):
        with pytest.raises(ValidationError):
            SignalSpec(
                definition=SourcedValue(value="rolling FF3 residual"),
                economic_intuition=SourcedValue(value="mispricing persistence"),
                direction=SourcedValue(value=SignalDirection.POSITIVE),
                category=SignalCategory.ESTIMATED,
                formula=FormulaSpec(paper_expression="residual momentum"),
                estimation=None,
            )

    def test_rolling_residual_signal_case(self):
        """Case 2: rolling residual signal (estimated category)."""
        spec = SignalSpec(
            definition=SourcedValue(value="12m cumulative FF3 residual return", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="underreaction to firm-specific news", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.POSITIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.ESTIMATED,
            formula=FormulaSpec(paper_expression="sum of monthly FF3 residuals over t-12..t-2"),
            estimation=EstimationSpec(
                method=EstimationMethod.TIME_SERIES_REGRESSION,
                model_expression="r_i - rf = a + b*MKT + s*SMB + h*HML + e",
                estimation_window=WindowSpec(start_offset=-36, end_offset=-1, unit=TimeUnit.MONTH, anchor=WindowAnchor.FORMATION_DATE),
                measurement_window=WindowSpec(start_offset=-12, end_offset=-2, unit=TimeUnit.MONTH, anchor=WindowAnchor.FORMATION_DATE),
                minimum_observations=24,
                residual_definition="monthly residual from the 36-month rolling FF3 regression",
            ),
        )
        assert spec.estimation is not None


class TestSequentialDoubleSort:
    def test_sequential_double_sort_case(self):
        """Case 3: sequential double sort (size then value), within engine capability (<=3 dims)."""
        size_sort = SortDimension(
            sort_id="size", concept_id="me", role=SortRole.CONDITIONING, order=1,
            mode=SortMode.SEQUENTIAL, group_type=GroupType.QUANTILE, group_count=2,
            breakpoints=BreakpointSpec(population=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
        )
        value_sort = SortDimension(
            sort_id="value", concept_id="bm", role=SortRole.TARGET, order=2,
            mode=SortMode.SEQUENTIAL, group_type=GroupType.QUANTILE, group_count=3,
            breakpoints=BreakpointSpec(population=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
            condition_on_sort_id="size",
        )
        portfolio = PortfolioSpec(
            construction_type=SourcedValue(value=ConstructionType.CHARACTERISTIC_SORT, status=EvidenceStatus.CLEAR),
            sorts=[size_sort, value_sort],
            legs=[
                PortfolioLeg(leg_id="long", side="long", selector={"size": 0, "value": 2}),
                PortfolioLeg(leg_id="short", side="short", selector={"size": 0, "value": 0}),
            ],
            weighting=SourcedValue(value="vw", status=EvidenceStatus.CLEAR),
            return_combination=SourcedValue(value="average_leg_spread", status=EvidenceStatus.CLEAR),
        )
        assert len(portfolio.sorts) == 2


class TestUnsupportedCustomWeighting:
    def test_custom_weighting_recorded_as_substitution_not_silently_dropped(self):
        """Case 4: paper states a capped-VW scheme the engine doesn't implement.

        D4: original_method stays blocked; the paper value survives via
        Substitution on ImplementationResolution, never silently coerced.
        """
        paper = _simple_accounting_ratio_spec()
        paper.portfolio.weighting = SourcedValue(value="capped_vw_at_5pct", status=EvidenceStatus.CLEAR)

        review = MethodReview(
            factor_id=paper.factor_id,
            paper_spec_hash=paper.content_hash(),
            capability_version="engine_capability.v1",
            findings=[
                Finding(
                    field_path="portfolio.weighting",
                    kind="unsupported",
                    reason="engine only supports ew/vw, not capped-VW",
                    empirical_impact="high",
                    disposition=Disposition.BLOCKED,
                    paper_value="capped_vw_at_5pct",
                )
            ],
        )
        assert review.is_blocked

        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
            paper_spec_hash=paper.content_hash(),
            review_hash="dummy_review_hash",
            approved_substitutions=[
                Substitution(
                    field_path="portfolio.weighting",
                    paper_value="capped_vw_at_5pct",
                    substituted_value="vw",
                    reason="engine capability v1 has no capped-VW menu member",
                    approved_by="reviewer_x",
                )
            ],
        )
        assert resolution.approved_substitutions[0].paper_value == "capped_vw_at_5pct"


class TestDispositionMatrix:
    def test_matrix_has_no_single_or_weak_or_conflicting_members(self):
        # D2: v1's SINGLE / WEAK_OR_CONFLICTING removed; only 5 statuses remain.
        statuses_in_matrix = {status for status, _ in DISPOSITION_MATRIX}
        assert statuses_in_matrix == {
            EvidenceStatus.CLEAR,
            EvidenceStatus.TABLE_ONLY,
            EvidenceStatus.INFERRED,
            EvidenceStatus.UNSPECIFIED,
            EvidenceStatus.CONFLICTING,
        }

    def test_clear_high_impact_auto_approves(self):
        assert DISPOSITION_MATRIX[(EvidenceStatus.CLEAR, "high")] == Disposition.AUTO_APPROVE

    def test_table_only_high_impact_needs_human(self):
        assert DISPOSITION_MATRIX[(EvidenceStatus.TABLE_ONLY, "high")] == Disposition.NEEDS_HUMAN_CONFIRMATION

    def test_inferred_low_impact_auto_defaults(self):
        assert DISPOSITION_MATRIX[(EvidenceStatus.INFERRED, "low")] == Disposition.APPROVE_WITH_DEFAULT


class TestResolvedMethodSpecReadiness:
    def _build_ready_resolved_spec(self) -> ResolvedMethodSpec:
        paper = _simple_accounting_ratio_spec()
        review = MethodReview(
            factor_id=paper.factor_id,
            paper_spec_hash=paper.content_hash(),
            capability_version="engine_capability.v1",
        )
        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
            paper_spec_hash=paper.content_hash(),
            review_hash=review.content_hash(),
            concept_mapping={"at": SourceColumn(source="comp_funda", column="at")},
            returns_source="us_equity_crsp",
        )
        return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)

    def test_ready_when_hashes_match_and_no_blocks(self):
        resolved = self._build_ready_resolved_spec()
        assert resolved.is_ready

    def test_not_ready_when_paper_hash_stale(self):
        resolved = self._build_ready_resolved_spec()
        resolved.paper.portfolio.weighting.value = "ew"  # mutate paper after review was bound
        assert not resolved.is_ready

    def test_not_ready_when_review_blocked(self):
        resolved = self._build_ready_resolved_spec()
        resolved.review.findings.append(
            Finding(
                field_path="portfolio.weighting", kind="unsupported", empirical_impact="high",
                disposition=Disposition.BLOCKED,
            )
        )
        assert not resolved.is_ready

    def test_not_ready_when_concept_mapping_missing(self):
        resolved = self._build_ready_resolved_spec()
        resolved.resolution.concept_mapping = {}
        assert not resolved.is_ready

    def test_not_ready_when_sort_dimensions_exceed_capability(self):
        resolved = self._build_ready_resolved_spec()
        extra_sorts = [
            SortDimension(
                sort_id=f"extra{i}", concept_id="at", role=SortRole.CONTROL, order=i + 2,
                mode=SortMode.INDEPENDENT, group_type=GroupType.QUANTILE,
                breakpoints=BreakpointSpec(population=SourcedValue()),
            )
            for i in range(3)
        ]
        resolved.paper.portfolio.sorts.extend(extra_sorts)
        assert not resolved.is_ready

    def test_factor_id_mismatch_rejected(self):
        paper = _simple_accounting_ratio_spec()
        review = MethodReview(
            factor_id="different_id", paper_spec_hash=paper.content_hash(),
            capability_version="engine_capability.v1",
        )
        resolution = ImplementationResolution(
            factor_id=paper.factor_id, paper_spec_hash=paper.content_hash(), review_hash=review.content_hash(),
        )
        with pytest.raises(ValidationError):
            ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


class TestResolutionEntryAppendOnly:
    def test_resolution_entry_records_reviewer_and_timestamp(self):
        entry = ResolutionEntry(
            field_path="data.fields[0].concept_id",
            expected_old_value=None,
            new_value="at",
            reason="mapped to Compustat annual",
            reviewer="reviewer_x",
            resolved_at=datetime.now(timezone.utc),
        )
        assert entry.reviewer == "reviewer_x"
