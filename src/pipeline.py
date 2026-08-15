"""Main pipeline orchestrator - connects all modules in the controlled workflow.

Entry point: `run_from_method_spec()` -- steps 3-5 (generate -> validate ->
execute) off an already-approved `ResolvedMethodSpec`. The original 7-step
`run_full_pipeline()` (extract -> review, via `SemanticExtractor`/
`ReviewGate`) was retired along with `MethodSpec` itself -- extraction/
review for the paper-first schema go through `MethodSpecExtractor`/
`review_method_spec`/`build_implementation_resolution` directly (see
`backend/routers/methodspecs.py`), not this orchestrator.

Every step is also reachable standalone via the sub-component attributes set
in `__init__` (`self.meta_coder`, `self.sandbox`, `self.runner`,
`self.controller`, `self.replication_diff`) for step-by-step testing/
debugging.
"""

from __future__ import annotations

from pathlib import Path

from src.infra.data_layer import DataLayer
from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step6_dual_track_controller import MultiTrackController
from src.steps.step7_replication_diff import ReplicationDiff
from src.steps.step8_diagnosis import ReplicationDiagnoser
from src.infra.evidence import EvidenceStore, RunRegistry
from src.infra.repair import RepairLoop
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.script_generator import pick_signal_input_mode
from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.registry import PluginRegistry
from src.steps.step4_validator import AdversarialSandbox


class Pipeline:
    """End-to-end factor replication pipeline (steps 3-6; see AGENTS.md's
    Module Map for the full pipeline including extraction/review).

    `run_from_method_spec()` runs steps 3-5 only, in this order exactly:
    MetaCoder generates the plugin and BacktestRunner builds the script from
    it (3) -> AdversarialSandbox validates that exact built script, including
    the execution smoke test (4) -> only once validation passes does
    BacktestRunner execute the script (5). A technical failure (syntax/
    schema/future-leak/execution crash) loops back to step 3 for a bounded
    Meta-Coder repair via the shared `RepairLoop` (src/infra/repair.py),
    every entry point (`run_from_method_spec`, `MultiTrackController.
    _run_track()`) uses the same one.
    """

    def __init__(
        self,
        llm_client=None,
        data_path: str = "./data",
        evidence_path: str = "./runs/evidence",
        scripts_path: str = "./runs/backtest_scripts",
        run_diagnosis: bool = False,
        check_faithfulness: bool = False,
    ):
        self.data_layer = DataLayer(data_path=data_path)
        self.meta_coder = MetaCoder(llm_client=llm_client)
        # Faithfulness check (code-vs-approved-formula, see step4_validator's
        # class docstring) is opt-in like Step 8: it costs an extra LLM call
        # per validate attempt, so it only runs when both requested and an
        # llm_client is actually available.
        self.sandbox = AdversarialSandbox(
            llm_client=llm_client if check_faithfulness and llm_client is not None else None
        )
        self.registry = PluginRegistry()
        self.scripts_path = Path(scripts_path)
        self.runner = BacktestRunner(self.data_layer, self.scripts_path)
        self.repair_loop = RepairLoop(self.runner, self.sandbox, self.meta_coder)
        # Step 8 is opt-in: the empirical artifacts are complete without it,
        # and it costs an extra LLM call per experiment.
        self.diagnoser = (
            ReplicationDiagnoser(llm_client=llm_client)
            if run_diagnosis and llm_client is not None
            else None
        )
        self.controller = MultiTrackController(
            runner=self.runner,
            meta_coder=self.meta_coder,
            sandbox=self.sandbox,
            diagnoser=self.diagnoser,
        )
        self.evidence_store = EvidenceStore(base_path=evidence_path)
        self.run_registry = RunRegistry()
        self.replication_diff = ReplicationDiff()

    def run_from_method_spec(
        self,
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        plugin: PluginRecord | None = None,
        config_overrides: dict | None = None,
        track: str = "original_method",
    ) -> RunRecord:
        """Run the pipeline starting from an already-approved MethodSpec,
        skipping extraction and multi-track orchestration entirely:

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
        re-validated before anything executes it again -- see the shared
        `RepairLoop` (src/infra/repair.py).

        The script is written to runs/backtest_scripts/{factor_id}_backtest.py
        (a durable, independently-runnable audit artifact — see
        src/steps/step3_codegen/script_generator.py). The registered
        snapshot's data files must already exist on disk (crsp_msf.parquet,
        and for Compustat-based signals also comp_funda.parquet +
        ccm_lnkhist.parquet) — this method does not generate data.

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

        repair_history = []
        if plugin is None:
            plugin = self.meta_coder.generate_plugin(spec)
            validated = self.repair_loop.build_validate_repair(
                plugin, spec, snapshot_id, config_overrides, data=validation_slice
            )
            plugin, built = validated.plugin, validated.built
            repair_history.extend(validated.history)
        elif plugin.validation_status != "passed":
            validated = self.repair_loop.build_validate_repair(
                plugin, spec, snapshot_id, config_overrides, data=validation_slice
            )
            plugin, built = validated.plugin, validated.built
            repair_history.extend(validated.history)
        else:
            # Caller already validated this exact plugin — still need the one
            # script artifact to execute (built fresh from this plugin's code,
            # not re-validated since validation_status is already "passed").
            built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides)

        self.registry.register(plugin)

        # Run via the shared RepairLoop: on a Step-5 execution failure it feeds
        # the run's stderr back to MetaCoder (same technical repair loop as
        # validation errors) and rebuilds+re-validates before retrying, so what
        # gets executed is always what was validated. On exhaustion the loop
        # returns an outcome with `error` set (rather than raising), and we
        # persist a status="failed" RunRecord so the failure has an audit trail
        # before re-raising.
        outcome = self.repair_loop.execute_with_repair(
            plugin, built, spec, snapshot_id, config_overrides, data=validation_slice
        )
        plugin = outcome.plugin
        repair_history.extend(outcome.history)
        self.registry.register(plugin)

        if outcome.error is not None:
            failed = self.runner.make_failed_run_record(
                spec, plugin, track, config_overrides, outcome.error
            )
            failed.repair_history = repair_history
            self.evidence_store.save_run(
                failed,
                artifacts={"script.py": str(built["script_path"])} if built.get("script_path") else None,
                inline_content={"plugin.py": plugin.code, "method_spec.json": spec.model_dump_json(indent=2)},
            )
            self.run_registry.register(failed)
            raise RuntimeError(outcome.error)

        run = self.runner.make_run_record(spec, plugin, track, outcome.result)
        run.repair_history = repair_history
        self.evidence_store.save_run(
            run,
            artifacts={"script.py": str(built["script_path"])} if built.get("script_path") else None,
            inline_content={"plugin.py": plugin.code, "method_spec.json": spec.model_dump_json(indent=2)},
        )
        self.run_registry.register(run)
        return run

    #: How many distinct permnos the compute_signal execution smoke-test slice
    #: keeps (full month history each). Enough cross-section to be meaningful,
    #: small enough to stay cheap; the check is lenient regardless (see
    #: AdversarialSandbox._check_executes).
    _VALIDATION_SLICE_PERMNOS = 40

    def _build_validation_slice(self, spec: ResolvedMethodSpec, snapshot_id: str):
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
            import pandas as pd

            from src.infra.data_layer import assemble_signal_master_table

            mode = pick_signal_input_mode(spec)
            snapshot = self.data_layer.snapshots.get_snapshot(snapshot_id)
            if snapshot is None:
                return None
            storage_path = Path(snapshot.storage_path)
            if mode == "compustat":
                # Same declarative loader the generated script uses
                # (assemble_signal_master_table), reading comp_funda.parquet +
                # ccm_lnkhist.parquet from the snapshot dir.
                si = assemble_signal_master_table(spec, storage_path)
            elif mode == "crsp_only":
                crsp = pd.read_parquet(storage_path / "crsp_msf.parquet")
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
                return v if isinstance(v, str) else getattr(v, "column", None)

            required_cols = [
                c for c in (_col_name(v) for v in spec.resolution.concept_mapping.values())
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
