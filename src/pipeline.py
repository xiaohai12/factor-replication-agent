"""Main pipeline orchestrator - connects all modules in the controlled workflow.

Two entry points:
- `run_from_method_spec()` -- starts from an already-approved MethodSpec and
  runs steps 3-5 only (generate -> validate -> execute).
- `run_full_pipeline()` -- all 7 steps end-to-end (extract -> review ->
  generate -> validate -> execute -> dual-track/ablations -> attribute).
  Fails fast at whichever stage rejects the factor (see `PipelineStatus`);
  it does not backtrack across stages. Real cross-stage backtrack
  (Review<->Extractor, Attribution<->ReviewGate per docs/architecture.md
  Section 3.1) is unimplemented -- Phase 2 scope (docs/roadmap.md).

Both share one real feedback loop: Sandbox/Step-5 technical error ->
Meta-Coder bounded repair (max `MAX_REPAIR_RETRIES` retries), implemented in
`_validate_with_repair()`. Every step is also reachable standalone via the
sub-component attributes set in `__init__` (`self.extractor`,
`self.review_gate`, `self.meta_coder`, `self.sandbox`, `self.runner`,
`self.controller`, `self.attribution`) for step-by-step testing/debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.infra.data_layer import DataLayer
from src.steps.step1_extractor import SemanticExtractor
from src.steps.step2_reviewer import ReviewGate
from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step6_dual_track_controller import DualTrackController, ExperimentPlan
from src.steps.step7_attribution import AttributionLayer
from src.infra.evidence import EvidenceStore, RunRegistry
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.script_generator import pick_signal_input_mode
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.registry import PluginRegistry
from src.steps.step4_validator import AdversarialSandbox


MAX_REPAIR_RETRIES = 3


@dataclass
class PipelineStatus:
    """Status of a `run_full_pipeline()` call for a single factor."""

    factor_id: str
    stage: str = "pending"  # extract|review|generate|validate|run|attribute|done|failed
    error: str = ""
    needs_manual: bool = False


class Pipeline:
    """End-to-end factor replication pipeline.

    Workflow (module numbers match AGENTS.md's Module Map by responsibility):
    1. Extract MethodSpec from paper/reference (SemanticExtractor)
    2. Review and approve MethodSpec (ReviewGate)
    3. Generate signal + hook plugin code, then assemble the one standalone
       backtest script from it (MetaCoder; script assembly is exposed as
       `BacktestRunner.build_script()` but is conceptually step3's output --
       see AGENTS.md's Module Map)
    4. Validate that built script -- static checks + a compute_signal
       execution smoke test on the real script from step 3 (AdversarialSandbox)
    5. Execute the backtest script via subprocess (`BacktestRunner.execute()`)
    6. Run controlled backtest across tracks/ablations (DualTrackController, using BacktestRunner)
    7. Attribute replication gap (AttributionLayer)

    `run_from_method_spec()` runs steps 3-5 only, in this order exactly:
    MetaCoder generates the plugin and BacktestRunner builds the script from
    it (3) -> AdversarialSandbox validates that exact built script, including
    the execution smoke test (4) -> only once validation passes does
    BacktestRunner execute the script (5).

    `run_full_pipeline()` runs all 7 steps in order, reusing
    `_validate_with_repair()` for steps 3-4 and `self.controller` for steps
    5-6 (each track builds+executes its own config variant, with its own
    bounded repair loop -- see `DualTrackController._run_track`).

    Feedback loop:
    - Sandbox/Step-5 technical error → Meta-Coder repair (≤`MAX_REPAIR_RETRIES`
      retries) -- implemented in `_validate_with_repair()`, reused by both
      entry points; `DualTrackController._run_track()` has its own analogous
      per-track repair loop for step 5/6 execution failures.
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
        self.scripts_path = Path(scripts_path)
        self.runner = BacktestRunner(self.data_layer, self.scripts_path)
        self.controller = DualTrackController(
            runner=self.runner, meta_coder=self.meta_coder, sandbox=self.sandbox
        )
        self.evidence_store = EvidenceStore(base_path=evidence_path)
        self.run_registry = RunRegistry()
        self.attribution = AttributionLayer()

    def run_full_pipeline(
        self,
        factor_id: str,
        snapshot_id: str,
        paper_text: str,
        plan: ExperimentPlan | None = None,
        config_overrides: dict | None = None,
    ) -> tuple[list[RunRecord], PipelineStatus]:
        """Run all 7 steps end-to-end for a single factor: extract -> review
        -> generate -> validate -> execute -> dual-track/ablations -> attribute.

        Fails fast: the first stage that rejects the factor stops the run and
        is reported on the returned `PipelineStatus` (`.stage` says which
        step failed, `.error` says why). To retry, fix the underlying issue
        and call this again, or drive the failing stage directly for a
        tighter debug loop (e.g. `pipeline.extractor.extract(...)` with
        edited `paper_text`, or `pipeline.review_gate.review(spec)` on a
        hand-patched spec).

        Args:
            factor_id: Unique factor identifier
            snapshot_id: Data snapshot registered on self.data_layer.snapshots
                (needed once the script is built -- see step 3 -- so
                `BacktestRunner.build_script` can locate
                crsp_msf.parquet/compustat_funda.parquet/ccm_link.parquet
                for every track `DualTrackController` runs).
            paper_text: Raw paper text handed to the extractor.
            plan: Experiment plan for steps 5-6 (defaults to original +
                standardized, matching `ExperimentPlan`'s own defaults).
            config_overrides: Optional BacktestExecutor config overrides
                applied to the *original_method* track's build during
                step 3-4 validation (steps 5-6 apply each track's own
                overrides on top when `self.controller` builds per track).

        Returns:
            Tuple of (RunRecords produced by steps 5-6, PipelineStatus).
            RunRecords is empty for any failure before step 5.
        """
        status = PipelineStatus(factor_id=factor_id)

        # --- 1. Extract ---
        status.stage = "extract"
        extraction = self.extractor.extract(factor_id=factor_id, paper_text=paper_text)
        spec = extraction.spec
        if spec is None:
            status.stage = "failed"
            status.error = extraction.error or "Extraction produced no MethodSpec"
            return [], status

        # --- 2. Review ---
        status.stage = "review"
        review_result = self.review_gate.review(spec)

        if review_result.requires_human:
            status.needs_manual = True
            status.stage = "failed"
            status.error = f"Blocked fields: {review_result.blocked_fields}"
            return [], status

        if not review_result.approved:
            status.stage = "failed"
            status.error = f"Review not approved: {review_result.issues}"
            return [], status

        spec.review_status = "approved"
        spec.codegen_ready = review_result.codegen_ready
        spec.paper_faithful = review_result.paper_faithful
        spec.remediation_mode = review_result.remediation_mode

        # --- 3-4. Generate plugin, then build+validate the script (bounded
        # Sandbox->Meta-Coder technical repair reused from
        # `_validate_with_repair`, the same helper `run_from_method_spec` uses,
        # so the "validated == executed" invariant holds here too) ---
        status.stage = "generate"
        plugin = self.meta_coder.generate_plugin(spec)

        status.stage = "validate"
        try:
            plugin, _built = self._validate_with_repair(
                plugin, spec, snapshot_id, config_overrides
            )
        except RuntimeError as validation_error:
            status.stage = "failed"
            status.error = str(validation_error)
            return [], status

        self.registry.register(plugin)

        # --- 5-6. Run experiments across tracks/ablations ---
        status.stage = "run"
        if plan is None:
            plan = ExperimentPlan(factor_id=factor_id)

        runs = self.controller.run_experiment(plugin, spec, plan, snapshot_id)

        for run in runs:
            self.evidence_store.save_run(run)
            self.run_registry.register(run)

        # --- 7. Attribution ---
        status.stage = "attribute"
        if plan.run_original and plan.run_standardized and len(runs) >= 2:
            self.attribution.attribute_ablation(runs)

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
        """Run the pipeline starting from an already-approved MethodSpec,
        skipping extraction and dual-track orchestration entirely:

            approved MethodSpec -> MetaCoder generates plugin.code -> Step3
            assembles the ONE complete standalone script (BacktestRunner.build_script) ->
            Step4 validates THAT SAME script (static checks + a compute_signal
            import-and-call smoke test on a small data slice) -> Step5 executes
            THAT SAME script (unchanged bytes) via subprocess -> EvidenceStore

        There's a single script artifact from generation onward — Step4 never
        re-derives or hand-rolls a separate "how do I run this plugin" runner,
        and Step5 never regenerates the script it validated. Whenever repair
        produces new plugin code (either from a validation failure or a Step-5
        run failure), the script is rebuilt from that new code and
        re-validated before anything executes it again — see
        `_validate_with_repair`.

        The script is written to runs/backtest_scripts/{factor_id}_backtest.py
        (a durable, independently-runnable audit artifact — see
        src/steps/step3_codegen/script_generator.py). The registered
        snapshot's data files must already exist on disk (crsp_msf.parquet,
        and for Compustat-based signals also compustat_funda.parquet +
        ccm_link.parquet) — this method does not generate data.

        Args:
            spec: Approved MethodSpec (review_status=approved, codegen_ready=True)
            snapshot_id: Data snapshot registered on self.data_layer.snapshots
            plugin: Optional pre-generated + already-validated PluginRecord.
                When omitted, MetaCoder generates one (with bounded repair).
            config_overrides: Optional BacktestExecutor config overrides
            track: Track label recorded on the returned RunRecord

        Returns:
            RunRecord with metrics, persisted to the evidence store.
        """
        # A small real-data slice for the sandbox's compute_signal execution
        # smoke test (step4). Best-effort: None when it can't be built, which
        # just skips the smoke test (the Step-5 run below is the guaranteed net).
        validation_slice = self._build_validation_slice(spec, snapshot_id)

        if plugin is None:
            plugin = self.meta_coder.generate_plugin(spec)
            plugin, built = self._validate_with_repair(
                plugin, spec, snapshot_id, config_overrides, data=validation_slice
            )
        elif plugin.validation_status != "passed":
            plugin, built = self._validate_with_repair(
                plugin, spec, snapshot_id, config_overrides, data=validation_slice
            )
        else:
            # Caller already validated this exact plugin — still need the one
            # script artifact to execute (built fresh from this plugin's code,
            # not re-validated since validation_status is already "passed").
            built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides)

        self.registry.register(plugin)

        # Run with bounded repair on a Step-5 execution failure. The step4
        # execution smoke test runs compute_signal only, on a small slice, so
        # it catches most formula bugs before this point; this net additionally
        # covers hook runtime bugs and anything that only surfaces on full data,
        # by feeding the run's stderr back to MetaCoder (the same repair loop
        # used for validation errors) and persisting a status="failed"
        # RunRecord on exhaustion so the failure has an audit trail. A repair
        # here rebuilds AND re-validates the script via `_validate_with_repair`
        # before the next execution attempt, so what's validated is always
        # what gets executed.
        result = None
        for attempt in range(MAX_REPAIR_RETRIES + 1):
            try:
                result = self.runner.execute(built)
                break
            except RuntimeError as run_error:
                can_repair = attempt < MAX_REPAIR_RETRIES and self.meta_coder.llm_client is not None
                if not can_repair:
                    failed = self.runner.make_failed_run_record(
                        spec, plugin, track, config_overrides, str(run_error)
                    )
                    self.evidence_store.save_run(failed)
                    self.run_registry.register(failed)
                    raise
                plugin = self.meta_coder.repair_plugin(plugin, [str(run_error)])
                plugin, built = self._validate_with_repair(
                    plugin, spec, snapshot_id, config_overrides, data=validation_slice
                )
                self.registry.register(plugin)

        run = self.runner.make_run_record(spec, plugin, track, result)
        self.evidence_store.save_run(run)
        self.run_registry.register(run)
        return run

    def _validate_with_repair(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
        data=None,
    ) -> tuple[PluginRecord, dict]:
        """Run Sandbox validation with bounded MetaCoder repair (technical errors only).

        Builds the ONE complete standalone script (`BacktestRunner.build_script`)
        fresh on every attempt — including after a repair produces new plugin
        code — and validates THAT script (not a separate hand-rolled runner),
        so whatever script comes back validated is byte-for-byte what
        `run_from_method_spec` goes on to execute.

        `data`, when supplied, is a small real-data slice passed through to the
        sandbox's compute_signal execution smoke test (see
        AdversarialSandbox.validate / _check_executes).

        Returns:
            (validated plugin, build dict from `BacktestRunner.build_script` for that plugin)
        """
        for attempt in range(MAX_REPAIR_RETRIES + 1):
            built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides)
            report = self.sandbox.validate(plugin, spec, script_text=built["script_text"], data=data)
            plugin.validation_report = report
            if report.passed:
                plugin.validation_status = "passed"
                return plugin, built
            if attempt < MAX_REPAIR_RETRIES:
                plugin = self.meta_coder.repair_plugin(plugin, report.errors)
            else:
                raise RuntimeError(
                    f"Plugin repair failed after {MAX_REPAIR_RETRIES} attempts: {report.errors}"
                )
        return plugin, built

    #: How many distinct permnos the compute_signal execution smoke-test slice
    #: keeps (full month history each). Enough cross-section to be meaningful,
    #: small enough to stay cheap; the check is lenient regardless (see
    #: AdversarialSandbox._check_executes).
    _VALIDATION_SLICE_PERMNOS = 40

    def _build_validation_slice(self, spec: MethodSpec, snapshot_id: str):
        """Best-effort small real-data slice for step4's compute_signal
        execution smoke test.

        Sliced BY PERMNO keeping each permno's FULL month history, so
        time-series lookbacks (momentum, year-over-year accounting change)
        stay intact -- never sliced by row/month. Prefers permnos with
        non-null coverage in the signal's required physical columns so the
        slice is likely to produce a non-empty result.

        Returns None on any problem (unknown/multi-source signal input, missing
        snapshot tables, empty data): the smoke test is best-effort and the
        Step-5 run is the guaranteed net, so a slice-build issue must never
        block validation.
        """
        try:
            mode = pick_signal_input_mode(spec)
            if mode == "compustat":
                si = self.data_layer.get_signal_master_table(
                    snapshot_id, lag_months=spec.accounting_lag_months or 6
                )
            elif mode == "crsp_only":
                crsp = self.data_layer.get_snapshot_data(snapshot_id, "crsp_msf")
                si = crsp.rename(columns={"yyyymm": "time_avail_m"})
            else:
                # multi_source (IBES/OptionMetrics/...) — assembling it in-process
                # here would duplicate the generated script's loader; defer to
                # the Step-5 net instead.
                return None

            if si is None or si.empty or "permno" not in si.columns:
                return None

            def _col_name(v):
                if isinstance(v, dict):
                    return v.get("column")
                return v if isinstance(v, str) else None

            required_cols = [
                c for c in (_col_name(v) for v in (spec.data.normalized_mapping or {}).values())
                if c and c in si.columns
            ]
            covered = si
            for col in required_cols:
                if not covered.empty:
                    covered = covered[covered[col].notna()]
            pool = covered if not covered.empty else si
            permnos = pool["permno"].drop_duplicates().head(self._VALIDATION_SLICE_PERMNOS)
            return si[si["permno"].isin(permnos)].copy()
        except Exception:
            return None
