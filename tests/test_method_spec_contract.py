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

import hashlib
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.infra.models.method_spec import (
    DISPOSITION_MATRIX,
    AdjustmentModel,
    BreakpointSpec,
    CalculationStep,
    ComparisonDerivation,
    ConstructionType,
    DataAvailability,
    DataSpec,
    Disposition,
    Estimand,
    EstimationMethod,
    EstimationSpec,
    EvidenceCitation,
    EvidenceStatus,
    FieldRole,
    FilterOp,
    FilterSpec,
    Finding,
    FormulaSpec,
    GroupType,
    ImplementationResolution,
    MethodReview,
    MethodSpec,
    MetricStatistic,
    PaperRef,
    Period,
    PortfolioLeg,
    PortfolioSpec,
    ReportedMetric,
    ReportedResults,
    RequiredField,
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
    TimeUnit,
    TimingSpec,
    Unit,
    UniverseSpec,
    WeightingScheme,
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
                name_in_paper="total assets",
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


def _simple_accounting_ratio_spec() -> MethodSpec:
    """Case 1: simple accounting ratio, single characteristic sort."""
    factor_id = MethodSpec.make_factor_id("cooper2008", "asset_growth")
    return MethodSpec(
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
                    mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR),
                    group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR),
                    group_count=10,
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
        reported_results=_minimal_reported_results(),
    )


class TestStrictRejection:
    def test_unknown_top_level_field_rejected(self):
        spec = _simple_accounting_ratio_spec()
        payload = spec.model_dump(mode="json")
        payload["some_unexpected_field"] = "should not survive"
        with pytest.raises(ValidationError):
            MethodSpec.model_validate(payload)

    def test_unknown_nested_field_rejected(self):
        spec = _simple_accounting_ratio_spec()
        payload = spec.model_dump(mode="json")
        payload["signal"]["formula"]["ghost_field"] = 1
        with pytest.raises(ValidationError):
            MethodSpec.model_validate(payload)


class TestRoundTrip:
    def test_lossless_round_trip(self):
        spec = _simple_accounting_ratio_spec()
        dumped = spec.model_dump(mode="json")
        reloaded = MethodSpec.model_validate(dumped)
        assert reloaded == spec

    def test_content_hash_stable_across_round_trip(self):
        spec = _simple_accounting_ratio_spec()
        reloaded = MethodSpec.model_validate(spec.model_dump(mode="json"))
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
        id1 = MethodSpec.make_factor_id("cooper2008", "asset_growth")
        id2 = MethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert id1 == id2

    def test_different_target_different_id(self):
        id1 = MethodSpec.make_factor_id("hirshleifer2012", "patent_emi")
        id2 = MethodSpec.make_factor_id("hirshleifer2012", "citations_emi")
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
                        mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR),
                        breakpoints=BreakpointSpec(basis=SourcedValue()),
                    ),
                    SortDimension(
                        sort_id="dup", concept_id="b", role=SortRole.CONTROL, order=2,
                        mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR),
                        breakpoints=BreakpointSpec(basis=SourcedValue()),
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
                        mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR),
                        breakpoints=BreakpointSpec(basis=SourcedValue()),
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

    def test_opted_in_endpoint_spread_is_derived_deterministically(self):
        low = _minimal_reported_results().metrics[0].model_copy(
            update={"metric_id": "port1", "label": "Port 1", "estimate": 0.48, "unit": Unit.PERCENT,
                    "portfolio_selector": {"z": 0}}
        )
        high = low.model_copy(
            update={"metric_id": "port10", "label": "Port 10", "estimate": 1.07,
                    "portfolio_selector": {"z": 9}}
        )
        results = ReportedResults(
            primary_metric_id="port1",
            metrics=[low, high],
            comparison_derivation=ComparisonDerivation(
                metric_id="port10_minus_port1", label="Port 10 − Port 1",
                operation="high_minus_low", high_metric_id="port10", low_metric_id="port1",
                use_as_primary_comparison=True,
            ),
        )
        derived = results.primary_comparison_metric()
        assert derived is not None
        assert derived.estimand == Estimand.SPREAD
        assert derived.estimate == pytest.approx(0.59)

    def test_unset_derivation_does_not_change_content_hash(self):
        spec = _simple_accounting_ratio_spec()
        legacy_payload = spec.model_dump(mode="json")
        legacy_payload["reported_results"].pop("comparison_derivation")
        for metric in legacy_payload["reported_results"]["metrics"]:
            metric.pop("portfolio_selector")
        legacy_payload.pop("notes")
        expected = hashlib.sha256(
            json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert MethodSpec.model_validate(legacy_payload).content_hash() == expected


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
            mode=SourcedValue(value=SortMode.SEQUENTIAL, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
            breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
        )
        value_sort = SortDimension(
            sort_id="value", concept_id="bm", role=SortRole.TARGET, order=2,
            mode=SourcedValue(value=SortMode.SEQUENTIAL, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=3,
            breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
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

        The `Substitution` model records the paper's original value against
        an engine-approved replacement, never silently coercing it. (D4's
        `BLOCKED` disposition -- which used to gate this -- was removed
        2026-08-10; an out-of-menu choice is now recorded via
        `SourcedValue.unsupported_value` and clamped, not blocked -- see
        docs/decision-log.md.)
        """
        paper = _simple_accounting_ratio_spec()
        paper.portfolio.weighting = SourcedValue(value="capped_vw_at_5pct", status=EvidenceStatus.CLEAR)

        review = MethodReview(
            factor_id=paper.factor_id,
            capability_version="engine_capability.v1",
            findings=[
                Finding(
                    field_path="portfolio.weighting",
                    kind="ambiguous",
                    reason="engine only supports ew/vw, not capped-VW",
                    empirical_impact="high",
                    disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                    paper_value="capped_vw_at_5pct",
                )
            ],
        )
        assert review.findings[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION

        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
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


class TestUnsupportedValueConsistency:
    def test_unsupported_value_allowed_when_value_is_other(self):
        sv = SourcedValue(value="other", unsupported_value="capped VW at 5% per stock", status=EvidenceStatus.CLEAR)
        assert sv.unsupported_value == "capped VW at 5% per stock"

    def test_unsupported_value_allowed_when_enum_value_is_other(self):
        sv = SourcedValue(value=WeightingScheme.OTHER, unsupported_value="capped VW at 5% per stock")
        assert sv.value == WeightingScheme.OTHER

    def test_unsupported_value_rejected_when_value_is_not_other(self):
        with pytest.raises(ValidationError):
            SourcedValue(value=WeightingScheme.VW, unsupported_value="capped VW at 5% per stock")

    def test_unsupported_value_defaults_to_none(self):
        sv = SourcedValue(value=WeightingScheme.VW, status=EvidenceStatus.CLEAR)
        assert sv.unsupported_value is None


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

    def test_table_only_high_impact_auto_approves(self):
        # (TABLE_ONLY, HIGH) changed to AUTO_APPROVE -- clear/table_only both
        # mean "the paper actually states this", just prose vs table; only
        # inferred/unspecified/conflicting need a human (2026-08 refactor).
        assert DISPOSITION_MATRIX[(EvidenceStatus.TABLE_ONLY, "high")] == Disposition.AUTO_APPROVE

    def test_inferred_low_impact_auto_defaults(self):
        assert DISPOSITION_MATRIX[(EvidenceStatus.INFERRED, "low")] == Disposition.APPROVE_WITH_DEFAULT


class TestResolvedMethodSpecReadiness:
    def _build_ready_resolved_spec(self) -> ResolvedMethodSpec:
        paper = _simple_accounting_ratio_spec()
        review = MethodReview(
            factor_id=paper.factor_id,
            capability_version="engine_capability.v1",
        )
        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
            concept_mapping={"at": SourceColumn(source="compustat_fundamental_annual", column="at")},
            returns_source="us_equity_crsp",
        )
        return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)

    def test_ready_when_no_blocks(self):
        resolved = self._build_ready_resolved_spec()
        assert resolved.is_ready

    def test_not_ready_when_concept_mapping_missing(self):
        resolved = self._build_ready_resolved_spec()
        resolved.resolution.concept_mapping = {}
        assert not resolved.is_ready

    def test_ready_even_when_sort_dimensions_exceed_capability(self):
        """docs/resolve-diagnostics-gaps.md problem 2 (2026-08-12): sort-
        dimension-count/construction capability no longer blocks `is_ready`
        -- `registry.build_config` auto-clamps to `MAX_SUPPORTED_SORT_
        DIMENSIONS`, recorded in `defaults_applied`, never blocking."""
        resolved = self._build_ready_resolved_spec()
        extra_sorts = [
            SortDimension(
                sort_id=f"extra{i}", concept_id="at", role=SortRole.CONTROL, order=i + 2,
                mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR), group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR),
                breakpoints=BreakpointSpec(basis=SourcedValue()),
            )
            for i in range(3)
        ]
        resolved.paper.portfolio.sorts.extend(extra_sorts)
        assert resolved.is_ready

    def test_factor_id_mismatch_rejected(self):
        paper = _simple_accounting_ratio_spec()
        review = MethodReview(
            factor_id="different_id",
            capability_version="engine_capability.v1",
        )
        resolution = ImplementationResolution(factor_id=paper.factor_id)
        with pytest.raises(ValidationError):
            ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


class TestUnsupportedUniverseFilter:
    """A universe filter that resolves to a physical column not on the
    returns panel (`RETURNS_PANEL_NATIVE_COLUMNS`) is `unsupported` only if
    that column isn't even registered in `catalog.DATA_CATALOG` for its
    source -- there's no way to load it at all. A filter resolved to a REAL
    registered non-native column (e.g. compustat_fundamental_annual.at) is supported: the
    generated script joins it onto the returns panel before
    filter_universe runs (2026-08-13, `registry._universe_filter_join_
    sources`/`script_generator.join_universe_filter_sources`). Either way, a
    human can still explicitly record `FilterSpec.accepted_unapplied` (the
    same "paper vocabulary vs engine menu" escape hatch as
    `WeightingScheme.OTHER`)."""

    def _resolved_with_filter(self, filter_spec: FilterSpec, filter_column: str = "listing_duration_years") -> ResolvedMethodSpec:
        paper = _simple_accounting_ratio_spec()
        paper.universe.filters.append(filter_spec)
        review = MethodReview(factor_id=paper.factor_id, capability_version="engine_capability.v1")
        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
            concept_mapping={
                "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
                filter_spec.concept_id: SourceColumn(source="compustat_fundamental_annual", column=filter_column),
            },
            returns_source="us_equity_crsp",
        )
        return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)

    def test_non_returns_panel_filter_is_unsupported_and_blocks_is_ready(self):
        # "listing_duration_years" is NOT a real registered compustat_fundamental_annual
        # physical column -- there's no way to load it, so it stays blocked.
        resolved = self._resolved_with_filter(
            FilterSpec(concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2)
        )
        assert resolved.unsupported_universe_filters() == ["compustat_listing_duration"]
        assert not resolved.is_ready

    def test_registered_non_native_filter_is_supported_via_join(self):
        # "at" IS a real registered compustat_fundamental_annual physical column -- the
        # generated script can join it onto the returns panel, so it's no
        # longer "unsupported" even though it's not CRSP-native.
        resolved = self._resolved_with_filter(
            FilterSpec(concept_id="total_assets", op=FilterOp.GTE, value=0), filter_column="at"
        )
        assert resolved.unsupported_universe_filters() == []
        assert resolved.is_ready

    def test_accepted_unapplied_filter_is_not_unsupported_and_does_not_block(self):
        resolved = self._resolved_with_filter(
            FilterSpec(
                concept_id="compustat_listing_duration", op=FilterOp.GTE, value=2,
                accepted_unapplied=True, unapplied_reason="no eligibility-panel support yet",
            )
        )
        assert resolved.unsupported_universe_filters() == []
        assert resolved.is_ready

    def test_returns_panel_filter_is_supported(self):
        paper = _simple_accounting_ratio_spec()
        paper.universe.filters.append(FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=[1, 2]))
        review = MethodReview(factor_id=paper.factor_id, capability_version="engine_capability.v1")
        resolution = ImplementationResolution(
            factor_id=paper.factor_id,
            concept_mapping={
                "at": SourceColumn(source="compustat_fundamental_annual", column="at"),
                "listing_exchange": SourceColumn(source="crsp_msf", column="exchcd"),
            },
            returns_source="us_equity_crsp",
        )
        resolved = ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)
        assert resolved.unsupported_universe_filters() == []
        assert resolved.is_ready


class TestFilterDerivation:
    """`FilterSpec.derivation` (docs/resolve-diagnostics-gaps.md problem 1/3):
    optional, same shape as `SignalSpec.formula` -- `None` by default
    (backward compatible with every existing MethodSpec), reviewable
    independent of any physical column (`inputs` references concept_ids,
    never a `SourceColumn`)."""

    def test_defaults_to_none(self):
        filt = FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=["NYSE"])
        assert filt.derivation is None

    def test_round_trips_through_json(self):
        filt = FilterSpec(
            concept_id="listing_exchange",
            op=FilterOp.IN,
            value=["NYSE", "Amex", "NASDAQ"],
            derivation=FormulaSpec(
                paper_expression='"NYSE"/"Amex"/"NASDAQ" -> exchcd 1/2/3',
                steps=[
                    CalculationStep(
                        step_id="map_label_to_code",
                        description="Map paper's exchange label to CRSP numeric exchcd",
                        expression='{"NYSE": 1, "Amex": 2, "NASDAQ": 3}',
                    ),
                ],
                inputs=["listing_exchange"],
            ),
        )
        reloaded = FilterSpec.model_validate_json(filt.model_dump_json())
        assert reloaded.derivation is not None
        assert reloaded.derivation.paper_expression == '"NYSE"/"Amex"/"NASDAQ" -> exchcd 1/2/3'
        assert reloaded.derivation.steps[0].step_id == "map_label_to_code"

    def test_old_filter_json_without_derivation_still_validates(self):
        # Simulates a pre-existing persisted MethodSpec JSON (no "derivation"
        # key at all) -- must still load, `derivation` defaulting to None.
        old_json = (
            '{"concept_id": "listing_exchange", "op": "in", "value": ["NYSE"], '
            '"evidence": [], "accepted_unapplied": false, "unapplied_reason": ""}'
        )
        filt = FilterSpec.model_validate_json(old_json)
        assert filt.derivation is None


class TestHumanConfirmedApplied:
    """`FilterSpec.human_confirmed_applied`/`applied_reason` -- symmetric
    audit-trail escape hatch to `accepted_unapplied`/`unapplied_reason`:
    records a human's confirmation that a filter SHOULD be enforced at
    runtime (does not change runtime behavior, only records the review)."""

    def test_defaults_to_false(self):
        filt = FilterSpec(concept_id="listing_exchange", op=FilterOp.IN, value=["NYSE"])
        assert filt.human_confirmed_applied is False
        assert filt.applied_reason == ""

    def test_round_trips_through_json(self):
        filt = FilterSpec(
            concept_id="listing_exchange",
            op=FilterOp.IN,
            value=["NYSE"],
            human_confirmed_applied=True,
            applied_reason="reviewed inferred evidence, confirmed correct",
        )
        reloaded = FilterSpec.model_validate_json(filt.model_dump_json())
        assert reloaded.human_confirmed_applied is True
        assert reloaded.applied_reason == "reviewed inferred evidence, confirmed correct"

    def test_mutually_exclusive_with_accepted_unapplied(self):
        with pytest.raises(ValueError, match="cannot be both"):
            FilterSpec(
                concept_id="listing_exchange",
                op=FilterOp.IN,
                value=["NYSE"],
                accepted_unapplied=True,
                unapplied_reason="not resolvable",
                human_confirmed_applied=True,
                applied_reason="reviewed and confirmed",
            )


class TestInRangesFilter:
    def test_accepts_numeric_range_union(self):
        filt = FilterSpec(concept_id="sic", op=FilterOp.INTERVALS, value=[[1, 3999], [5000, 5999]])
        assert filt.op == FilterOp.INTERVALS

    def test_rejects_reversed_range(self):
        with pytest.raises(ValueError, match="intervals"):
            FilterSpec(concept_id="sic", op=FilterOp.INTERVALS, value=[[3999, 1]])

    def test_rejects_nested_ranges_under_in(self):
        with pytest.raises(ValueError, match="flat list"):
            FilterSpec(concept_id="sic", op=FilterOp.IN, value=[[1, 3999], [5000, 5999]])


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
