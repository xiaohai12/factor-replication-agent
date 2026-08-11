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
    ConstructionType,
    DataAvailability,
    DataSpec,
    Disposition,
    Estimand,
    EvidenceStatus,
    FieldRole,
    FilterOp,
    FilterSpec,
    FormulaSpec,
    GroupType,
    Period,
    MethodSpec,
    PaperRef,
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
    SourcedValue,
    MetricStatistic,
    TableRef,
    EvidenceCitation,
    TimeUnit,
    TimingSpec,
    Unit,
    UniverseSpec,
)
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.review import review_method_spec


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
                    concept_id="at", paper_name="total assets",
                    paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT],
                )
            ],
        ),
        sample=SampleSpec(data_coverage=_period(), formation=_period(), reported_returns=_period()),
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


class TestReviewCleanBaseline:
    def test_fully_clear_spec_has_no_findings(self):
        review = review_method_spec(_base_spec())
        assert review.findings == []


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

    def test_unsupported_weighting_scheme_not_flagged(self):
        paper = _base_spec()
        paper.portfolio.weighting = SourcedValue(value="other", status=EvidenceStatus.CLEAR)
        review = review_method_spec(paper)
        assert not any(f.field_path == "portfolio.weighting" for f in review.findings)

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
                concept_id="totally_made_up_concept_xyz", paper_name="nonsense",
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
