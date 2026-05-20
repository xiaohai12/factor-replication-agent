"""Main pipeline orchestrator - connects all modules in the controlled workflow."""

from __future__ import annotations

from src.attribution import AttributionLayer
from src.controller import DualTrackController, ExperimentPlan
from src.engine import BacktestEngine
from src.evidence import EvidenceStore, RunRegistry
from src.extractor import SemanticExtractor
from src.meta_coder import MetaCoder
from src.models.method_spec import MethodSpec
from src.models.run_record import RunRecord
from src.registry import PluginRegistry
from src.review_gate import ReviewGate
from src.sandbox import AdversarialSandbox


class Pipeline:
    """End-to-end factor replication pipeline.

    Workflow:
    1. Extract MethodSpec from paper/reference (SemanticExtractor)
    2. Review and approve MethodSpec (ReviewGate)
    3. Generate signal plugin (MetaCoder)
    4. Validate plugin (AdversarialSandbox)
    5. Register plugin (PluginRegistry)
    6. Run controlled backtest (BacktestEngine via DualTrackController)
    7. Store evidence (EvidenceStore)
    8. Attribute replication gap (AttributionLayer)
    """

    def __init__(
        self,
        llm_client=None,
        data_path: str | None = None,
        evidence_path: str = "./evidence",
    ):
        self.extractor = SemanticExtractor(llm_client=llm_client)
        self.review_gate = ReviewGate()
        self.meta_coder = MetaCoder(llm_client=llm_client)
        self.sandbox = AdversarialSandbox()
        self.registry = PluginRegistry()
        self.engine = BacktestEngine(data_path=data_path)
        self.controller = DualTrackController(engine=self.engine)
        self.evidence_store = EvidenceStore(base_path=evidence_path)
        self.run_registry = RunRegistry()
        self.attribution = AttributionLayer()

    def run_factor(
        self,
        paper_text: str,
        factor_id: str,
        plan: ExperimentPlan | None = None,
    ) -> list[RunRecord]:
        """Run the full pipeline for a single factor.

        Args:
            paper_text: Raw paper text for extraction
            factor_id: Unique factor identifier
            plan: Experiment plan (defaults to original + standardized)

        Returns:
            List of completed RunRecords
        """
        # 1. Extract MethodSpec
        spec = self.extractor.extract_from_paper(paper_text, factor_id)

        # 2. Review
        review_result = self.review_gate.review(spec)
        if not review_result.approved:
            raise RuntimeError(
                f"MethodSpec review failed: {review_result.issues}"
            )
        spec.review_status = "approved"

        # 3. Generate plugin
        plugin = self.meta_coder.generate_plugin(spec)

        # 4. Validate
        report = self.sandbox.validate(plugin, spec)
        plugin.validation_report = report

        if not report.passed:
            # Attempt bounded repair for technical errors
            plugin = self.meta_coder.repair_plugin(plugin, report.errors)
            report = self.sandbox.validate(plugin, spec)
            if not report.passed:
                raise RuntimeError(f"Plugin validation failed: {report.errors}")

        plugin.validation_status = "passed"

        # 5. Register
        self.registry.register(plugin)

        # 6. Run experiments
        if plan is None:
            plan = ExperimentPlan(factor_id=factor_id)

        runs = self.controller.run_experiment(plugin, spec, plan)

        # 7. Store evidence
        for run in runs:
            self.evidence_store.save_run(run)
            self.run_registry.register(run)

        # 8. Attribution (if we have both tracks)
        if plan.run_original and plan.run_standardized:
            attr_result = self.attribution.attribute_ablation(runs)
            report_text = self.attribution.generate_report(attr_result)
            # TODO: Save attribution report

        return runs
