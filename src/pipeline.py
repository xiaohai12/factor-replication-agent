"""Main pipeline orchestrator - connects all modules in the controlled workflow.

Implements feedback loops (docs/architecture.md Section 3.1):
- Sandbox → Meta-Coder: bounded repair (max 3 retries)
- Sandbox → Review Gate: empirical issues need re-review
- Review Gate → Extractor: re-extraction on conflicts
- Attribution → Review Gate: anomalous results trigger re-review
- Max backtrack depth: 3 per factor
"""

from __future__ import annotations

from dataclasses import dataclass

from src.steps.attribution import AttributionLayer
from src.steps.controller import DualTrackController, ExperimentPlan
from src.infra.data_layer import DataLayer
from src.steps.engine import BacktestEngine
from src.infra.evidence import EvidenceStore, RunRegistry
from src.steps.extractor import SemanticExtractor
from src.steps.codegen import MetaCoder
from src.infra.models.method_spec import MethodSpec
from src.infra.models.run_record import RunRecord
from src.infra.registry import PluginRegistry
from src.steps.reviewer import ReviewGate
from src.steps.validator import AdversarialSandbox


MAX_REPAIR_RETRIES = 3
MAX_BACKTRACK_DEPTH = 3


@dataclass
class PipelineStatus:
    """Status of a factor's pipeline execution."""

    factor_id: str
    stage: str = "pending"  # extract|review|generate|validate|run|attribute|done|failed
    backtrack_count: int = 0
    error: str = ""
    needs_manual: bool = False


class Pipeline:
    """End-to-end factor replication pipeline with feedback loops.

    Workflow:
    1. Extract MethodSpec from paper/reference (SemanticExtractor)
    2. Review and approve MethodSpec (ReviewGate)
    3. Generate signal plugin (MetaCoder)
    4. Validate plugin (AdversarialSandbox)
    5. Register plugin (PluginRegistry)
    6. Run controlled backtest (BacktestEngine via DualTrackController)
    7. Store evidence (EvidenceStore)
    8. Attribute replication gap (AttributionLayer)

    Feedback loops:
    - Sandbox technical error → Meta-Coder repair (≤3 retries)
    - Sandbox empirical issue → Review Gate re-review
    - Review Gate blocked → Extractor re-extraction
    - Attribution anomaly → Review Gate re-review
    - Max backtrack depth: 3 per factor → needs_manual_intervention
    """

    def __init__(
        self,
        llm_client=None,
        data_path: str = "./data",
        evidence_path: str = "./evidence",
    ):
        self.data_layer = DataLayer(data_path=data_path)
        self.extractor = SemanticExtractor(
            llm_client=llm_client,
            data_dictionary=self.data_layer.dictionary,
        )
        self.review_gate = ReviewGate(
            data_dictionary=self.data_layer.dictionary,
            llm_client=llm_client,
        )
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
        factor_id: str,
        paper_text: str | None = None,
        cz_metadata: dict | None = None,
        osap_code: str | None = None,
        plan: ExperimentPlan | None = None,
    ) -> tuple[list[RunRecord], PipelineStatus]:
        """Run the full pipeline for a single factor with backtrack support.

        Args:
            factor_id: Unique factor identifier
            paper_text: Raw paper text
            cz_metadata: C&Z metadata dict
            osap_code: OSAP reference code
            plan: Experiment plan (defaults to original + standardized)

        Returns:
            Tuple of (RunRecords, PipelineStatus)
        """
        status = PipelineStatus(factor_id=factor_id)

        # --- 1. Extract ---
        status.stage = "extract"
        extraction = self.extractor.extract(
            factor_id=factor_id,
            paper_text=paper_text,
        )
        spec = extraction.spec
        if spec is None:
            status.stage = "failed"
            status.error = "Extraction produced no MethodSpec"
            return [], status

        # --- 2. Review (with backtrack loop) ---
        status.stage = "review"
        review_result = self.review_gate.review(spec)

        if review_result.requires_human:
            status.needs_manual = True
            status.stage = "failed"
            status.error = f"Blocked fields: {review_result.blocked_fields}"
            return [], status

        if not review_result.approved:
            # Backtrack: Review → Extractor
            if status.backtrack_count < MAX_BACKTRACK_DEPTH:
                status.backtrack_count += 1
                # TODO: Re-extract with feedback from review issues
                status.stage = "failed"
                status.error = f"Review failed: {review_result.issues}"
                return [], status
            else:
                status.needs_manual = True
                status.stage = "failed"
                status.error = "Max backtrack depth reached at review"
                return [], status

        spec.review_status = "approved"
        spec.codegen_ready = review_result.codegen_ready
        spec.paper_faithful = review_result.paper_faithful
        spec.remediation_mode = review_result.remediation_mode

        # --- 3. Generate plugin ---
        status.stage = "generate"
        plugin = self.meta_coder.generate_plugin(spec)

        # --- 4. Validate (with repair loop) ---
        status.stage = "validate"
        for attempt in range(MAX_REPAIR_RETRIES + 1):
            report = self.sandbox.validate(plugin, spec)
            plugin.validation_report = report

            if report.passed:
                break

            # Check if errors are technical (repairable) or empirical (backtrack)
            if self._has_empirical_issues(report):
                # Backtrack: Sandbox → Review Gate
                if status.backtrack_count < MAX_BACKTRACK_DEPTH:
                    status.backtrack_count += 1
                    status.stage = "failed"
                    status.error = f"Empirical issues in sandbox: {report.errors}"
                    return [], status
                else:
                    status.needs_manual = True
                    status.stage = "failed"
                    status.error = "Max backtrack depth at sandbox empirical"
                    return [], status

            # Technical error → bounded repair
            if attempt < MAX_REPAIR_RETRIES:
                plugin = self.meta_coder.repair_plugin(plugin, report.errors)
            else:
                status.stage = "failed"
                status.error = f"Plugin repair failed after {MAX_REPAIR_RETRIES} attempts"
                return [], status

        plugin.validation_status = "passed"

        # --- 5. Register ---
        self.registry.register(plugin)

        # --- 6. Run experiments ---
        status.stage = "run"
        if plan is None:
            plan = ExperimentPlan(factor_id=factor_id)

        runs = self.controller.run_experiment(plugin, spec, plan)

        # --- 7. Store evidence ---
        for run in runs:
            self.evidence_store.save_run(run)
            self.run_registry.register(run)

        # --- 8. Attribution ---
        status.stage = "attribute"
        if plan.run_original and plan.run_standardized and len(runs) >= 2:
            attr_result = self.attribution.attribute_ablation(runs)

            # Check for anomalies → backtrack to Review Gate
            if self._is_anomalous(attr_result, spec):
                if status.backtrack_count < MAX_BACKTRACK_DEPTH:
                    status.backtrack_count += 1
                    # TODO: Trigger re-review with anomaly info
                    status.stage = "failed"
                    status.error = "Attribution anomaly detected"
                    return runs, status

        status.stage = "done"
        return runs, status

    def _has_empirical_issues(self, report) -> bool:
        """Check if validation errors involve empirical assumptions."""
        empirical_keywords = ["temporal leakage", "lag violation", "future", "missing policy"]
        for error in report.errors:
            if any(kw in error.lower() for kw in empirical_keywords):
                return True
        return False

    def _is_anomalous(self, attr_result, spec: MethodSpec) -> bool:
        """Check if attribution results are anomalous (>50% gap or sign flip)."""
        if attr_result.original_tstat is None or attr_result.standardized_tstat is None:
            return False
        # Sign flip
        if (attr_result.original_tstat > 0) != (attr_result.standardized_tstat > 0):
            return True
        # >50% relative gap
        if attr_result.original_tstat != 0:
            gap_pct = abs(attr_result.total_gap or 0) / abs(attr_result.original_tstat)
            if gap_pct > 0.5:
                return True
        return False
