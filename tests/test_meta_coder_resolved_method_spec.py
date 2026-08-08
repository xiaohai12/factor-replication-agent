"""Phase D test: `MetaCoder.generate_plugin`'s `ResolvedMethodSpec` dispatch.

Not yet used by `src.pipeline`/`app.py`/backend routers (see
docs/methodspec-v2-plan.md section 9, Phase D); locks the new
`_build_prompt_from_resolved` prompt-building contract with a fake LLM
client (no real network call).
"""

from __future__ import annotations

from src.infra.models.paper_method_spec import (
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
    PaperMethodSpec,
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
from src.steps.step2_reviewer.paper_review import review_paper_method_spec
from src.steps.step3_codegen import MetaCoder


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = None


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_messages = None

    def create(self, messages, **kwargs):
        self.last_messages = messages
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeLLMClient:
    def __init__(self, content: str = "def compute_signal(df):\n    return df\n") -> None:
        self.chat = _FakeChat(content)


def _period() -> Period:
    return Period(start_year=1968, end_year=2003)


def _resolved_spec() -> ResolvedMethodSpec:
    factor_id = PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
    paper = PaperMethodSpec(
        factor_id=factor_id,
        target_name="asset_growth",
        paper=PaperRef(document_id="cooper2008", title="Asset Growth...", citation="Cooper et al 2008", publication_year=2008),
        signal=SignalSpec(
            definition=SourcedValue(value="(AT_t - AT_t-1) / AT_t-1", status=EvidenceStatus.CLEAR),
            economic_intuition=SourcedValue(value="overinvestment", status=EvidenceStatus.CLEAR),
            direction=SourcedValue(value=SignalDirection.NEGATIVE, status=EvidenceStatus.CLEAR),
            category=SignalCategory.CONTINUOUS,
            formula=FormulaSpec(
                paper_expression="(AT_t - AT_t-1) / AT_t-1",
                steps=[
                    CalculationStep(step_id="s1", description="take total assets and its 1-year lag", expression="at, at_lag1"),
                    CalculationStep(step_id="s2", description="compute the growth ratio", expression="(at - at_lag1) / at_lag1"),
                ],
                inputs=["at"], output_concept="asset_growth",
            ),
        ),
        data=DataSpec(
            signal_frequency=SourcedValue(value=TimeUnit.YEAR, status=EvidenceStatus.CLEAR),
            return_frequency=SourcedValue(value=TimeUnit.MONTH, status=EvidenceStatus.CLEAR),
            fields=[RequiredField(concept_id="at", paper_name="total assets", paper_source_hint="Compustat annual", roles=[FieldRole.SIGNAL_INPUT])],
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
    review = review_paper_method_spec(paper)
    resolution = ImplementationResolution(
        factor_id=paper.factor_id, paper_spec_hash=paper.content_hash(),
        review_hash=review.content_hash(),
        concept_mapping={"at": SourceColumn(source="comp_funda", column="at")},
        returns_source="us_equity_crsp",
    )
    return ResolvedMethodSpec(paper=paper, review=review, resolution=resolution)


class TestGeneratePluginFromResolved:
    def test_generates_plugin_and_records_factor_id(self):
        coder = MetaCoder(llm_client=_FakeLLMClient())
        record = coder.generate_plugin(_resolved_spec())
        assert record.factor_id == PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert "compute_signal" in record.code

    def test_not_ready_spec_rejected(self):
        resolved = _resolved_spec()
        resolved.resolution.concept_mapping = {}  # unmaps "at" -> not ready
        coder = MetaCoder(llm_client=_FakeLLMClient())
        try:
            coder.generate_plugin(resolved)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_prompt_includes_formula_steps_and_column_mapping(self):
        coder = MetaCoder(llm_client=_FakeLLMClient())
        prompt = coder._build_prompt_from_resolved(_resolved_spec())
        assert "compute the growth ratio" in prompt
        assert 'at → df["at"]' in prompt
        assert "Accounting lag: 6 months" in prompt
        assert "Portfolio formation: end of month 6" in prompt
