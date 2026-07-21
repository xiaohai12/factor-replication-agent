"""Main pipeline orchestrator - connects all modules in the controlled workflow.

Implements feedback loops (docs/architecture.md Section 3.1):
- Sandbox → Meta-Coder: bounded repair (max 3 retries)
- Sandbox → Review Gate: empirical issues need re-review
- Review Gate → Extractor: re-extraction on conflicts
- Attribution → Review Gate: anomalous results trigger re-review
- Max backtrack depth: 3 per factor
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.steps.step7_attribution import AttributionLayer
from src.steps.step6_dual_track_controller import DualTrackController, ExperimentPlan
from src.infra.data_layer import DataLayer
from src.steps.step5_engine import BacktestEngine
from src.infra.evidence import EvidenceStore, RunRegistry
from src.steps.step1_extractor import SemanticExtractor
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.script_generator import generate_backtest_script, pick_signal_input_mode
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunMetrics, RunRecord
from src.infra.registry import PluginRegistry
from src.steps.step2_reviewer import ReviewGate
from src.steps.step4_validator import AdversarialSandbox


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
        evidence_path: str = "./runs/evidence",
        scripts_path: str = "./runs/backtest_scripts",
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
        self.scripts_path = Path(scripts_path)

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

    def run_from_method_spec(
        self,
        spec: MethodSpec,
        snapshot_id: str,
        plugin: PluginRecord | None = None,
        config_overrides: dict | None = None,
        track: str = "original_method",
    ) -> RunRecord:
        """Run the MVP chain starting from an already-approved MethodSpec.

        This is the curated-MethodSpec path from docs/roadmap.md Phase 1: it
        skips extraction and dual-track orchestration entirely.

            approved MethodSpec -> MetaCoder (if plugin not supplied) -> Sandbox
            -> generate_backtest_script() -> execute via subprocess -> EvidenceStore

        The backtest is NOT run in-process: a standalone Python script is
        generated (see src/steps/step3_codegen/script_generator.py) and saved to
        runs/backtest_scripts/{factor_id}_backtest.py, then executed as a
        subprocess. That script is the actual source of the reported metrics,
        so every run leaves behind an independently re-runnable audit artifact.
        The registered snapshot's data files must already exist on disk
        (crsp_msf.parquet, and for Compustat-based signals also
        compustat_funda.parquet + ccm_link.parquet) — this method does not
        generate data.

        Args:
            spec: Approved MethodSpec (review_status=approved, codegen_ready=True)
            snapshot_id: Data snapshot registered on self.data_layer.snapshots
            plugin: Optional pre-generated + already-validated PluginRecord.
                When omitted, MetaCoder generates one (with bounded repair).
            config_overrides: Optional BacktestEngine config overrides
            track: Track label recorded on the returned RunRecord

        Returns:
            RunRecord with metrics, persisted to the evidence store.
        """
        if plugin is None:
            plugin = self.meta_coder.generate_plugin(spec)
            plugin = self._validate_with_repair(plugin, spec)
        elif plugin.validation_status != "passed":
            plugin = self._validate_with_repair(plugin, spec)

        self.registry.register(plugin)

        result = self._run_backtest_via_script(plugin, spec, snapshot_id, config_overrides)
        metrics = result["metrics"]

        config_hash = hashlib.sha256(
            json.dumps(result["config"], sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        run = RunRecord(
            run_id=f"{spec.factor_id}_{track}_{plugin.code_hash[:8]}",
            factor_id=spec.factor_id,
            plugin_id=plugin.plugin_id,
            track=track,
            method_spec_hash=spec.stable_hash(),
            code_hash=plugin.code_hash,
            config_hash=config_hash,
            metrics=RunMetrics(
                mean_return=metrics.get("mean_monthly_return"),
                t_stat=metrics.get("t_stat"),
                n_months=metrics.get("n_months"),
                # Phase 2 (plan.md): populated when factor data was available
                # for this run (see _run_backtest_via_script); None otherwise.
                sharpe_ratio=metrics.get("sharpe_ratio"),
                alpha_capm=metrics.get("alpha_capm"),
                alpha_ff3=metrics.get("alpha_ff3"),
                alpha_ff5=metrics.get("alpha_ff5"),
            ),
            status="success",
        )
        self.evidence_store.save_run(run)
        self.run_registry.register(run)
        return run

    def _validate_with_repair(self, plugin: PluginRecord, spec: MethodSpec) -> PluginRecord:
        """Run Sandbox validation with bounded MetaCoder repair (technical errors only)."""
        for attempt in range(MAX_REPAIR_RETRIES + 1):
            report = self.sandbox.validate(plugin, spec)
            plugin.validation_report = report
            if report.passed:
                plugin.validation_status = "passed"
                return plugin
            if attempt < MAX_REPAIR_RETRIES:
                plugin = self.meta_coder.repair_plugin(plugin, report.errors)
            else:
                raise RuntimeError(
                    f"Plugin repair failed after {MAX_REPAIR_RETRIES} attempts: {report.errors}"
                )
        return plugin

    def _run_backtest_via_script(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
    ) -> dict:
        """Generate the standalone backtest script and execute it via subprocess.

        The script is written to runs/backtest_scripts/{factor_id}_backtest.py
        (a durable, independently-runnable audit artifact — see
        src/steps/step3_codegen/script_generator.py) and run with the current
        Python interpreter. Results are read back from the CSV/metrics.json
        the script itself writes, rather than computed in-process, so the
        persisted script is always the actual source of the reported numbers.

        Data is NOT auto-generated here: the registered snapshot's
        storage_path must already contain crsp_msf.parquet (and, in
        'compustat' mode, compustat_funda.parquet + ccm_link.parquet).
        """
        snapshot = self.data_layer.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            raise RuntimeError(f"Snapshot '{snapshot_id}' not registered on this Pipeline's DataLayer")
        storage_path = Path(snapshot.storage_path)

        signal_input_mode = pick_signal_input_mode(spec)

        scripts_dir = self.scripts_path
        scripts_dir.mkdir(parents=True, exist_ok=True)
        results_dir = scripts_dir / "results"
        output_csv = results_dir / f"{spec.factor_id}.csv"

        # Phase 2 (plan.md): FF factor + rf data for alpha metrics, if
        # available. Checked per-snapshot first (most reproducible — matches
        # the snapshot's own pull date), falling back to the shared
        # data/local/ff_factors.parquet fetched once via
        # scripts/fetch_ff_factors.py. Neither is required; alphas are simply
        # omitted from metrics when no factor data is found.
        ff_factors_path = None
        for candidate in (storage_path / "ff_factors.parquet", self.data_layer.data_path / "local" / "ff_factors.parquet"):
            if candidate.exists():
                ff_factors_path = str(candidate)
                break

        script = generate_backtest_script(
            spec,
            plugin.code,
            data_path=str(storage_path / "crsp_msf.parquet"),
            signal_input_mode=signal_input_mode,
            compustat_data_path=str(storage_path / "compustat_funda.parquet"),
            ccm_link_path=str(storage_path / "ccm_link.parquet"),
            output_path=str(output_csv),
            config_overrides=config_overrides,
            ff_factors_path=ff_factors_path,
            signal_data_dir=str(storage_path),
        )
        script_path = scripts_dir / f"{spec.factor_id}_backtest.py"
        script_path.write_text(script)

        # The generated script does `from src...` imports (see
        # script_generator.py's module docstring — Phase 0 unification made
        # it a thin wrapper around BacktestEngine instead of a fully
        # self-contained script). This repo's editable install only puts
        # `src/` itself on sys.path (its .pth file points at .../src, not the
        # repo root — see `pip show factor-replication-agent`), and Python
        # puts a *script's own directory* (not the cwd) on sys.path[0], so
        # `from src...` only resolves when the script happens to run with the
        # repo root on sys.path already. Since this script is written to an
        # arbitrary scripts_dir (e.g. a pytest tmp_path), explicitly prepend
        # the repo root to PYTHONPATH for the subprocess.
        repo_root = Path(__file__).resolve().parent.parent
        env = {**os.environ, "PYTHONPATH": f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}

        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Backtest script {script_path} failed (exit {proc.returncode}):\n"
                f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
            )

        metrics_path = output_csv.with_suffix(".metrics.json")
        metrics = json.loads(metrics_path.read_text())
        return_series = pd.read_csv(output_csv)

        config = self.engine._build_config(spec, config_overrides)

        return {
            "metrics": metrics,
            "return_series": return_series,
            "config": config,
            "script_path": str(script_path),
            "stdout": proc.stdout,
        }

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
