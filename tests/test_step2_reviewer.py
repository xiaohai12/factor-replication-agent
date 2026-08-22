"""Phase C tests: deterministic review (`review_method_spec`) and
physical-mapping resolution (`build_implementation_resolution`).

Does NOT touch the live v1 `ReviewGate` / `src.pipeline` -- these tests only
lock the new review/resolution modules' contract (see
docs/methodspec-v2-plan.md section 9, Phase C).
"""

from __future__ import annotations

from src.infra.data_layer import DataDictionary
from src.infra.models.method_spec import (
    AdjustmentModel,
    BreakpointSpec,
    ComparisonDerivation,
    ConstructionType,
    DataAvailability,
    DataSpec,
    Disposition,
    Estimand,
    EvidenceCitation,
    EvidenceStatus,
    FieldRole,
    FilterOp,
    FilterSpec,
    FormulaSpec,
    GroupType,
    MethodSpec,
    MetricStatistic,
    PaperRef,
    Period,
    PortfolioLeg,
    PortfolioSpec,
    ReportedMetric,
    ReportedResults,
    RequiredField,
    SampleSpec,
    SignalCategory,
    SignalDirection,
    SignalSpec,
    SortDimension,
    SortMode,
    SortRole,
    SourceColumn,
    SourcedValue,
    SourceName,
    TableRef,
    TimeUnit,
    TimingSpec,
    Unit,
    UniverseSpec,
    WeightingScheme,
)
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.review import high_impact_sourced_values, review_method_spec


def _period() -> Period:
    return Period(start_year=1968, end_year=2003)


def _base_spec(**portfolio_overrides) -> MethodSpec:
    """A fully-CLEAR spec (every high-impact SourcedValue has status=clear)
    so the baseline review produces zero findings; tests then mutate one
    thing at a time to trigger a specific finding.
    """
    portfolio_kwargs = dict(
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
    )
    portfolio_kwargs.update(portfolio_overrides)

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
            formula=FormulaSpec(paper_expression="(AT_t - AT_t-1) / AT_t-1", inputs=["at"], output_concept="asset_growth"),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[
                RequiredField(
                    concept_id="at", name_in_paper="total assets",
                    paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT],
                    source_table=SourcedValue(value=SourceName.COMPUSTAT_FUNDAMENTAL_ANNUAL, status=EvidenceStatus.CLEAR),
                    source_column=SourcedValue(value="at", status=EvidenceStatus.CLEAR),
                )
            ],
        ),
        # `reported_returns` deliberately differs from `formation` (end_year
        # +1) -- holding_period=12 below means the last formation's returns
        # extend a year past formation.end_year; an IDENTICAL pair here would
        # trip `_reported_returns_holding_period_mismatch_finding` and break
        # this fixture's "fully clear, zero findings" contract.
        sample=SampleSpec(
            data_coverage=_period(), formation=_period(),
            reported_returns=Period(start_year=1968, end_year=2004, status=EvidenceStatus.CLEAR),
        ),
        timing=TimingSpec(
            formation_rule=SourcedValue(value="every June", status=EvidenceStatus.CLEAR),
            rebalance_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            holding_period=SourcedValue(value=12, status=EvidenceStatus.CLEAR),
            data_availability=DataAvailability(lag_value=6),
        ),
        universe=UniverseSpec(description=SourcedValue(value="NYSE/AMEX/NASDAQ", status=EvidenceStatus.CLEAR)),
        portfolio=PortfolioSpec(**portfolio_kwargs),
        reported_results=ReportedResults(
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
        ),
    )


def _dichev_policy_spec(*, use_forbidden_proxy: bool = False) -> MethodSpec:
    spec = _base_spec()
    spec.factor_id = MethodSpec.make_factor_id("Is the risk of bankruptcy a systematic risk.pdf", "Z_score")
    spec.target_name = "Z_score"
    spec.paper.document_id = "Is the risk of bankruptcy a systematic risk.pdf"
    spec.signal.formula.inputs = [
        "at", "crsp_fiscal_year_end_price", "crsp_fiscal_year_end_shares", "total_liabilities"
    ]
    spec.data.fields.extend([
        RequiredField(
            concept_id="crsp_fiscal_year_end_price", name_in_paper="market equity price",
            roles=[FieldRole.SIGNAL_INPUT],
            source_table=SourcedValue(value=SourceName.CRSP_MSF, status=EvidenceStatus.CLEAR),
            source_column=SourcedValue(value="prc", status=EvidenceStatus.CLEAR),
        ),
        RequiredField(
            concept_id="crsp_fiscal_year_end_shares", name_in_paper="market equity shares",
            roles=[FieldRole.SIGNAL_INPUT],
            source_table=SourcedValue(value=SourceName.CRSP_MSF, status=EvidenceStatus.CLEAR),
            source_column=SourcedValue(value="shrout", status=EvidenceStatus.CLEAR),
        ),
        RequiredField(
            concept_id="total_liabilities", name_in_paper="total liabilities",
            roles=[FieldRole.SIGNAL_INPUT],
            source_table=SourcedValue(value=SourceName.COMPUSTAT_FUNDAMENTAL_ANNUAL, status=EvidenceStatus.CLEAR),
            source_column=SourcedValue(value="lt", status=EvidenceStatus.CLEAR),
        ),
    ])
    if use_forbidden_proxy:
        spec.data.fields.append(RequiredField(
            concept_id="market_value_equity", name_in_paper="market value equity",
            roles=[FieldRole.SIGNAL_INPUT],
            source_table=SourcedValue(value=SourceName.COMPUSTAT_FUNDAMENTAL_ANNUAL, status=EvidenceStatus.CLEAR),
            source_column=SourcedValue(value="mkvalt", status=EvidenceStatus.CLEAR),
        ))
    return spec


class TestReviewCleanBaseline:
    def test_fully_clear_spec_has_no_findings(self):
        review = review_method_spec(_base_spec())
        assert review.findings == []

    def test_dichev_policy_flags_compustat_market_value_proxy(self):
        review = review_method_spec(_dichev_policy_spec(use_forbidden_proxy=True))
        policy_findings = [f for f in review.findings if "implementation policy" in f.reason]
        assert policy_findings
        assert any("mkvalt" in f.reason for f in policy_findings)

    def test_fully_clear_spec_still_lists_every_high_impact_field(self):
        # `findings` stays empty (nothing needs attention), but
        # `all_high_impact_fields` unconditionally lists every field
        # `high_impact_sourced_values` checks, all AUTO_APPROVE here --
        # plus `sample.reported_returns.start_year`/`end_year`, which are
        # `Period` fields `high_impact_sourced_values` doesn't cover (see
        # `_reported_returns_year_findings`).
        paper = _base_spec()
        review = review_method_spec(paper)
        expected_paths = {path for path, _ in high_impact_sourced_values(paper)} | {
            "sample.reported_returns.start_year", "sample.reported_returns.end_year",
        }
        actual_paths = {f.field_path for f in review.all_high_impact_fields}
        assert actual_paths == expected_paths
        assert all(f.disposition == Disposition.AUTO_APPROVE for f in review.all_high_impact_fields)

    def test_all_high_impact_fields_includes_needs_human_confirmation_entries(self):
        paper = _base_spec()
        paper.timing.formation_rule.status = EvidenceStatus.INFERRED
        review = review_method_spec(paper)
        matches = [f for f in review.all_high_impact_fields if f.field_path == "timing.formation_rule"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        # still also in `findings`, unchanged behavior
        assert any(f.field_path == "timing.formation_rule" for f in review.findings)


class TestEvidenceStatusFindings:
    def test_inferred_high_impact_field_needs_human_confirmation(self):
        paper = _base_spec()
        paper.timing.formation_rule.status = EvidenceStatus.INFERRED
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "timing.formation_rule"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION

    def test_table_only_high_impact_field_auto_approves(self):
        # (TABLE_ONLY, HIGH) -> AUTO_APPROVE (2026-08-10): clear/table_only
        # both mean "the paper actually states this".
        paper = _base_spec()
        paper.universe.description.status = EvidenceStatus.TABLE_ONLY
        review = review_method_spec(paper)
        assert not any(f.field_path == "universe.description" for f in review.findings)

    def test_conflicting_field_needs_human_confirmation(self):
        paper = _base_spec()
        paper.signal.direction.status = EvidenceStatus.CONFLICTING
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "signal.direction"]
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION


class TestMissingMappingFindings:
    """D4 (engine-capability blocking) was removed 2026-08-10 -- menu-vocabulary
    classification (weighting/construction_type/breakpoints.basis/
    missing_policies[].action) now happens in the LLM review loop
    (spec_build.py) and is recorded via `SourcedValue.unsupported_value`,
    never blocked. The one D4-era check that survives is the
    `universe.filters[].concept_id` cross-reference (refiled as
    `missing_mapping`/`NEEDS_HUMAN_CONFIRMATION`, not `BLOCKED`), since an
    unmappable concept is a hard Step3 crash risk, not an engine-capability
    gap."""

    def test_unsupported_weighting_scheme_is_flagged_but_not_blocked(self):
        """docs/resolve-diagnostics-gaps.md problem 2 (2026-08-12): a menu
        field classified `other` now ALWAYS gets a (non-blocking) Finding,
        even when `status=clear` -- D2's evidence-status check alone would
        miss this (CLEAR+HIGH is AUTO_APPROVE), which is exactly the "no
        visibility at all" gap that prompted the fix. Still never `BLOCKED`
        -- `disposition` is `NEEDS_HUMAN_CONFIRMATION`, informational only."""
        paper = _base_spec()
        paper.portfolio.weighting = SourcedValue(value="other", status=EvidenceStatus.CLEAR)
        review = review_method_spec(paper)
        finding = next(f for f in review.findings if f.field_path == "portfolio.weighting")
        assert finding.disposition == Disposition.NEEDS_HUMAN_CONFIRMATION

    def test_universe_filter_concept_not_in_data_fields_needs_human_confirmation(self):
        """docs/known-gaps-paper-first-v2.md gap #3: a universe filter
        concept_id with no matching data.fields entry (e.g. a lag-suffixed
        pseudo-name the extractor invented for a formula step, like
        "total_assets_t_minus_1") can never resolve to a physical column --
        review should flag it instead of letting it surface as a confusing
        step3 'no physical column mapping' 400."""
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(concept_id="total_assets_t_minus_1", op=FilterOp.NONMISSING),
        ]
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "universe.filters[0].concept_id"]
        assert len(matches) == 1
        assert matches[0].kind == "missing_mapping"
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert matches[0].paper_value == "total_assets_t_minus_1"

    def test_universe_filter_concept_already_in_data_fields_not_flagged(self):
        paper = _base_spec()
        paper.universe.filters = [FilterSpec(concept_id="at", op=FilterOp.NONMISSING)]
        review = review_method_spec(paper)
        assert not any(f.field_path == "universe.filters[0].concept_id" for f in review.findings)


class TestUniverseEvidenceCoverage:
    def test_uncovered_universe_citation_needs_human_confirmation(self):
        paper = _base_spec()
        citation = EvidenceCitation(location="p. 1", quote="Eligible firms must meet the stated sample screen.")
        paper.universe.description.evidence = [citation]

        review = review_method_spec(paper)

        finding = next(f for f in review.findings if f.field_path == "universe.description.evidence[0]")
        assert finding.kind == "incomplete"
        assert finding.disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert finding.evidence == [citation]

    def test_filter_reusing_universe_citation_covers_it(self):
        paper = _base_spec()
        citation = EvidenceCitation(location="p. 1", quote="Eligible firms must meet the stated sample screen.")
        paper.universe.description.evidence = [citation]
        paper.universe.filters = [FilterSpec(concept_id="at", op=FilterOp.GT, value=0, evidence=[citation])]

        review = review_method_spec(paper)

        assert not any(f.kind == "incomplete" for f in review.findings)

    def test_unsupported_filter_field_does_not_cover_universe_citation(self):
        paper = _base_spec()
        citation = EvidenceCitation(location="p. 1", quote="Eligible firms must meet the stated sample screen.")
        paper.universe.description.evidence = [citation]
        paper.universe.filters = [FilterSpec(concept_id="at", op=FilterOp.GT, value=0, evidence=[citation])]
        paper.data.fields[0].source_table = SourcedValue(
            value=SourceName.OTHER,
            unsupported_value="invented eligibility condition",
            status=EvidenceStatus.CLEAR,
        )

        review = review_method_spec(paper)

        assert any(f.kind == "incomplete" for f in review.findings)

    def test_every_universe_filter_is_shown_as_high_impact(self):
        paper = _base_spec()
        paper.universe.filters = [FilterSpec(concept_id="at", op=FilterOp.GT, value=0)]

        review = review_method_spec(paper)

        finding = next(f for f in review.all_high_impact_fields if f.field_path == "universe.filters[0]")
        assert finding.kind == "universe_filter"
        assert finding.disposition == Disposition.NEEDS_HUMAN_CONFIRMATION


class TestUniverseFilterPanelMismatch:
    """`_universe_filter_panel_mismatch_findings` -- a filter's own cited
    table must agree with the table `reported_results.metrics` was read
    from. Deliberately field-agnostic: `_base_spec`'s primary metric always
    cites "Table 3" (see `_base_spec`'s `reported_results`), regardless of
    which concept_id the filter under test restricts.
    """

    def test_filter_cited_from_a_different_table_is_flagged(self):
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(
                concept_id="at", op=FilterOp.GT, value=0,
                evidence=[EvidenceCitation(table_ref=TableRef(table="Table 1", row="Sample"))],
            )
        ]

        review = review_method_spec(paper)

        finding = next(f for f in review.findings if f.field_path == "universe.filters[0].evidence" and f.kind == "inconsistent")
        assert finding.disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert "table 1" in finding.reason.lower()
        assert "table 3" in finding.reason.lower()

    def test_filter_cited_from_the_same_table_is_not_flagged(self):
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(
                concept_id="at", op=FilterOp.GT, value=0,
                evidence=[EvidenceCitation(table_ref=TableRef(table="Table 3", row="Sample"))],
            )
        ]

        review = review_method_spec(paper)

        assert not any(f.kind == "inconsistent" and f.field_path == "universe.filters[0].evidence" for f in review.findings)

    def test_filter_cited_only_by_prose_is_not_flagged(self):
        # A narrative (quote-only) universe citation is normal even for a
        # single-panel paper -- this check has no way to tell that apart
        # from a genuine mismatch, so it must not fire here.
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(
                concept_id="at", op=FilterOp.GT, value=0,
                evidence=[EvidenceCitation(quote="Eligible firms must meet the stated sample screen.")],
            )
        ]

        review = review_method_spec(paper)

        assert not any(f.kind == "inconsistent" and f.field_path == "universe.filters[0].evidence" for f in review.findings)

    def test_accepted_unapplied_filter_is_not_flagged(self):
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(
                concept_id="at", op=FilterOp.GT, value=0,
                evidence=[EvidenceCitation(table_ref=TableRef(table="Table 1", row="Sample"))],
                accepted_unapplied=True, unapplied_reason="not resolvable against the returns panel",
            )
        ]

        review = review_method_spec(paper)

        assert not any(f.kind == "inconsistent" and f.field_path == "universe.filters[0].evidence" for f in review.findings)


class TestEngineMenuUnconditionalFindings:
    """docs/resolve-diagnostics-gaps.md problem 2: engine-menu fields
    classified `other` get an unconditional Finding regardless of
    `EvidenceStatus` (replacing, not duplicating, the D2 evidence-status
    check for that same field_path)."""

    def test_return_combination_other_is_flagged(self):
        paper = _base_spec()
        paper.portfolio.return_combination = SourcedValue(
            value="other", unsupported_value="a novel spread definition", status=EvidenceStatus.CLEAR,
        )
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "portfolio.return_combination"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert matches[0].paper_value == "a novel spread definition"

    def test_group_type_other_is_flagged(self):
        paper = _base_spec()
        paper.portfolio.sorts[0].group_type = SourcedValue(value="other", unsupported_value="ad-hoc buckets", status=EvidenceStatus.CLEAR)
        review = review_method_spec(paper)
        assert any(f.field_path == "portfolio.sorts[0].group_type" for f in review.findings)

    def test_categorical_group_type_is_not_flagged_by_the_other_check(self):
        """`categorical`/`threshold` are known, named, unsupported values --
        not the free-text `other` bucket -- so the unconditional check does
        NOT fire for them (they're handled by registry.build_config's
        auto-clamp + defaults_applied instead, not a review-time Finding)."""
        paper = _base_spec()
        paper.portfolio.sorts[0].group_type = SourcedValue(value=GroupType.CATEGORICAL, status=EvidenceStatus.CLEAR)
        review = review_method_spec(paper)
        assert not any(f.field_path == "portfolio.sorts[0].group_type" for f in review.findings)

    def test_engine_menu_other_replaces_not_duplicates_d2_finding(self):
        """A field that's BOTH `value=="other"` and `status=inferred` must
        produce exactly ONE Finding for that field_path, not two."""
        paper = _base_spec()
        paper.portfolio.weighting = SourcedValue(
            value="other", unsupported_value="capped VW at 5%", status=EvidenceStatus.INFERRED,
        )
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "portfolio.weighting"]
        assert len(matches) == 1
        assert matches[0].paper_value == "capped VW at 5%"

    def test_daily_rebalance_frequency_is_flagged(self):
        paper = _base_spec()
        paper.timing.rebalance_frequency = SourcedValue(value=TimeUnit.DAY, status=EvidenceStatus.CLEAR)
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "timing.rebalance_frequency"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION

    def test_daily_lag_unit_is_flagged(self):
        paper = _base_spec()
        paper.timing.data_availability = DataAvailability(lag_value=5, lag_unit=TimeUnit.DAY)
        review = review_method_spec(paper)
        assert any(f.field_path == "timing.data_availability.lag_unit" for f in review.findings)

    def test_excess_sort_dimension_count_is_flagged(self):
        paper = _base_spec()
        paper.portfolio.sorts.append(
            SortDimension(
                sort_id="s2", concept_id="at", role=SortRole.CONTROL, order=2,
                mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR),
                group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
                breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
            )
        )
        paper.portfolio.sorts.append(
            SortDimension(
                sort_id="s3", concept_id="at", role=SortRole.CONTROL, order=3,
                mode=SourcedValue(value=SortMode.INDEPENDENT, status=EvidenceStatus.CLEAR),
                group_type=SourcedValue(value=GroupType.QUANTILE, status=EvidenceStatus.CLEAR), group_count=2,
                breakpoints=BreakpointSpec(basis=SourcedValue(value="nyse", status=EvidenceStatus.CLEAR)),
            )
        )
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "portfolio.sorts"]
        assert len(matches) == 1
        assert matches[0].paper_value == 3

    def test_primary_metric_weighting_mismatch_is_flagged(self):
        paper = _base_spec()  # portfolio.weighting="vw"
        paper.reported_results.metrics[0].weighting = WeightingScheme.EW
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.field_path == "reported_results.primary_metric_id"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert matches[0].paper_value == "ew"

    def test_primary_metric_weighting_match_is_not_flagged(self):
        paper = _base_spec()  # portfolio.weighting="vw"
        paper.reported_results.metrics[0].weighting = WeightingScheme.VW
        review = review_method_spec(paper)
        assert not any(f.field_path == "reported_results.primary_metric_id" for f in review.findings)

    def test_primary_metric_weighting_unset_is_not_flagged(self):
        # _base_spec() leaves ReportedMetric.weighting unset (None) -- never guess.
        review = review_method_spec(_base_spec())
        assert not any(f.field_path == "reported_results.primary_metric_id" for f in review.findings)

    def test_endpoint_derivation_requires_matching_spread_legs(self):
        paper = _base_spec()
        low = paper.reported_results.metrics[0].model_copy(
            update={"metric_id": "low", "estimate": 0.48, "portfolio_selector": {"sort1": 0}}
        )
        high = low.model_copy(
            update={"metric_id": "high", "estimate": 1.07, "portfolio_selector": {"sort1": 9}}
        )
        paper.reported_results = ReportedResults(
            primary_metric_id="low", metrics=[low, high],
            comparison_derivation=ComparisonDerivation(
                metric_id="high_minus_low", label="High − low", operation="high_minus_low",
                high_metric_id="high", low_metric_id="low", use_as_primary_comparison=True,
            ),
        )
        paper.portfolio.legs = [
            PortfolioLeg(leg_id="long", side="long", selector={"sort1": 9}),
            PortfolioLeg(leg_id="short", side="short", selector={"sort1": 0}),
        ]
        assert not any(
            finding.field_path == "reported_results.comparison_derivation"
            for finding in review_method_spec(paper).findings
        )
        paper.portfolio.legs[0].selector = {"sort1": 8}
        assert any(
            finding.field_path == "reported_results.comparison_derivation"
            for finding in review_method_spec(paper).findings
        )

    def test_disjoint_same_field_between_filters_require_confirmation(self):
        paper = _base_spec()
        paper.universe.filters = [
            FilterSpec(concept_id="at", op=FilterOp.BETWEEN, value=[1, 3999]),
            FilterSpec(concept_id="at", op=FilterOp.BETWEEN, value=[5000, 5999]),
        ]
        review = review_method_spec(paper)
        matches = [f for f in review.findings if f.kind == "inconsistent"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert "intervals" in matches[0].reason


class TestReportedReturnsHoldingPeriodMismatch:
    """Deterministic cross-check (docs/decision-log.md 2026-08-22): a
    >=12-month holding period means the last formation's returns extend past
    `formation.end_year`, so an IDENTICAL `formation`/`reported_returns`
    window is suspicious -- likely a step1 extraction that copied a table
    caption's FORMATION-period range into `reported_returns` unchanged
    (real example: Lakonishok/Shleifer/Vishny 1994's MeanRankRevGrowth)."""

    def test_identical_windows_with_annual_hold_is_flagged(self):
        paper = _base_spec()
        paper.sample.formation = Period(start_year=1968, end_year=1989, status=EvidenceStatus.CLEAR)
        paper.sample.reported_returns = Period(start_year=1968, end_year=1989, status=EvidenceStatus.CLEAR)
        paper.timing.holding_period.value = 12

        review = review_method_spec(paper)

        matches = [f for f in review.findings if f.field_path == "sample.reported_returns"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert matches[0].kind == "inconsistent"
        assert "1968-1989" in matches[0].reason

    def test_differing_windows_not_flagged(self):
        # _base_spec()'s own reported_returns already differs from formation
        # by design (see _base_spec's comment) -- this is the "fully clear,
        # zero findings" baseline itself, not a special case.
        review = review_method_spec(_base_spec())
        assert not any(f.field_path == "sample.reported_returns" for f in review.findings)

    def test_short_holding_period_not_flagged_even_if_identical(self):
        """A holding period < 12 months doesn't guarantee the return window
        crosses a calendar-year boundary -- identical windows here are NOT
        necessarily suspicious (e.g. monthly rebalance), so this must NOT
        false-positive."""
        paper = _base_spec()
        paper.sample.formation = Period(start_year=1968, end_year=1989, status=EvidenceStatus.CLEAR)
        paper.sample.reported_returns = Period(start_year=1968, end_year=1989, status=EvidenceStatus.CLEAR)
        paper.timing.holding_period.value = 1

        review = review_method_spec(paper)

        assert not any(f.field_path == "sample.reported_returns" for f in review.findings)

    def test_missing_years_not_flagged(self):
        paper = _base_spec()
        paper.sample.formation = Period(status=EvidenceStatus.CLEAR)
        paper.sample.reported_returns = Period(status=EvidenceStatus.CLEAR)
        paper.timing.holding_period.value = 12

        review = review_method_spec(paper)

        assert not any(f.field_path == "sample.reported_returns" for f in review.findings)


class TestResolutionBuilder:
    def test_resolves_known_concept_binds_factor_id(self):
        paper = _base_spec()
        review = review_method_spec(paper)
        resolution = build_implementation_resolution(paper, review, data_dictionary=DataDictionary())

        assert resolution.factor_id == paper.factor_id

    def test_unresolved_concept_omitted_not_guessed(self):
        paper = _base_spec()
        paper.data.fields.append(
            RequiredField(
                concept_id="totally_made_up_concept_xyz", name_in_paper="nonsense",
                paper_source_hint="", roles=[FieldRole.SIGNAL_INPUT],
            )
        )
        review = review_method_spec(paper)
        resolution = build_implementation_resolution(paper, review, data_dictionary=DataDictionary())
        assert "totally_made_up_concept_xyz" not in resolution.concept_mapping

    def test_universe_filter_concept_is_resolved_even_when_not_a_data_field(self):
        """A `universe.filters[].concept_id` (e.g. "exchange") is a separate
        namespace from `data.fields` -- it must still get a concept_mapping
        entry so `build_config` can resolve its physical column, even though
        it's never listed as a required data field (real gap found via a
        live end-to-end run against a real paper: 2026-08-07)."""
        paper = _base_spec()
        paper.universe.filters.append(FilterSpec(concept_id="exchange", op=FilterOp.IN, value=["NYSE", "Amex"]))
        review = review_method_spec(paper)
        resolution = build_implementation_resolution(paper, review, data_dictionary=DataDictionary())
        assert resolution.concept_mapping["exchange"].column == "exchcd"

    def test_explicit_source_table_and_column_win_over_string_matching(self):
        """2026-08-13: a field's own `source_table`/`source_column` (set by
        the extractor/reviewed by the LLM against the live catalog) is used
        directly, bypassing `normalize_fields()` entirely -- proven here
        with a deliberately unmatchable `paper_source_hint` ("xyz123", which
        the string matcher can't resolve to anything) that still resolves
        correctly because `source_table`/`source_column` are set."""
        paper = _base_spec()
        paper.data.fields.append(
            RequiredField(
                concept_id="book_equity", name_in_paper="xyz123", paper_source_hint="xyz123",
                roles=[FieldRole.SIGNAL_INPUT],
                source_table=SourcedValue(value=SourceName.COMPUSTAT_FUNDAMENTAL_ANNUAL, status=EvidenceStatus.CLEAR),
                source_column=SourcedValue(value="ceq", status=EvidenceStatus.CLEAR),
            )
        )
        review = review_method_spec(paper)
        resolution = build_implementation_resolution(paper, review, data_dictionary=DataDictionary())
        assert resolution.concept_mapping["book_equity"] == SourceColumn(source="compustat_fundamental_annual", column="ceq")
