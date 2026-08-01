"""Main pipeline orchestrator - connects all modules in the controlled workflow.

Two entry points -- see `Pipeline`'s class docstring for the full workflow
and feedback loop:
- `run_from_method_spec()` -- steps 3-5 only (generate -> validate -> execute).
- `run_full_pipeline()` -- all 7 steps end-to-end.

Every step is also reachable standalone via the sub-component attributes set
in `__init__` (`self.extractor`, `self.review_gate`, `self.meta_coder`,
`self.sandbox`, `self.runner`, `self.controller`, `self.replication_diff`) for
step-by-step testing/debugging.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.infra.data_layer import DataLayer
from src.steps.step1_extractor import SemanticExtractor
from src.steps.step2_reviewer import ReviewGate
from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step6_dual_track_controller import DualTrackController, ExperimentPlan
from src.steps.step7_replication_diff import ReplicationDiff
from src.infra.evidence import EvidenceStore, RunRegistry
from src.infra.repair import RepairLoop
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.script_generator import pick_signal_input_mode
from src.infra.models.method_spec import MethodSpec, RemediationMode
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.registry import PluginRegistry
from src.steps.step4_validator import AdversarialSandbox


#: Bounded budget for the Review -> Extractor targeted re-extraction loop
#: (see `Pipeline.run_full_pipeline`). After this many targeted re-extractions
#: still fail review, the factor escalates to a human.
MAX_REEXTRACT = 2


@dataclass
class PipelineStatus:
    """Status of a `run_full_pipeline()` call for a single factor."""

    factor_id: str
    stage: str = "pending"  # extract|review|reextract|generate|validate|run|replication_diff|done|failed
    error: str = ""
    needs_manual: bool = False


class Pipeline:
    """End-to-end factor replication pipeline.

    Workflow (module numbers match AGENTS.md's Module Map by responsibility):
    1. Extract MethodSpec from paper/reference (SemanticExtractor)
    2. Review and approve MethodSpec (ReviewGate).
       **Feedback loop (Review -> Extractor):** when the LLM reviewer judges a
       high-impact field was likely MIS-extracted (in the paper but read
       wrong -- remediation_mode == TARGETED_REEXTRACTION), the factor loops
       back to step 1 for a bounded targeted re-extraction (≤`MAX_REEXTRACT`),
       feeding the extractor the reviewer's paper-quote for each flagged field.
       Empirical values are never auto-edited -- the extractor re-reads the
       paper and the reviewer re-judges. Paper-silent fields, an exhausted
       budget, or FULL_REGENERATION escalate to a human (needs_manual).
    3. Generate the signal plugin code (the `compute_signal` formula only),
       then assemble the one standalone backtest script from it (MetaCoder;
       script assembly is exposed as `BacktestRunner.build_script()` but is
       conceptually step3's output -- see AGENTS.md's Module Map)
    4. Validate that built script -- static checks + a compute_signal
       execution smoke test on the real script from step 3 (AdversarialSandbox).
       **Feedback loop (technical repair):** on a technical failure this loops
       back to step 3 for a bounded Meta-Coder repair (≤`MAX_REPAIR_RETRIES`
       retries), the one shared `RepairLoop` (src/infra/repair.py) every entry
       point uses.
    5. Execute the backtest script via subprocess (`BacktestRunner.execute()`).
       An execution failure loops back to step 3 the same way, via the same
       `RepairLoop` (per track, inside `DualTrackController._run_track()` when
       step 6 is involved).
    6. Run controlled backtest across tracks/ablations (DualTrackController, using BacktestRunner)
    7. Analyze the replication gap vs reference (ReplicationDiff) -- terminal
       reporting step, not a loop trigger

    Two automatic feedback loops exist, both bounded: the Review->Extractor
    targeted re-extraction (step 2, empirical-faithfulness, human-gated on
    exhaustion) and the technical repair loop (steps 4/5, code-only, never
    touches empirical parameters). There is deliberately NO automatic
    empirical backtrack from later stages (ReplicationDiff is terminal); the
    replication gap is reported, not auto-corrected. See docs/decision-log.md.

    `run_from_method_spec()` runs steps 3-5 only, in this order exactly:
    MetaCoder generates the plugin and BacktestRunner builds the script from
    it (3) -> AdversarialSandbox validates that exact built script, including
    the execution smoke test (4) -> only once validation passes does
    BacktestRunner execute the script (5).

    `run_full_pipeline()` runs all 7 steps in order, reusing
    `RepairLoop.build_validate_repair()` for steps 3-4 and `self.controller`
    for steps 5-6. It fails fast (escalating to a human via
    `PipelineStatus.needs_manual`) at whichever stage rejects the factor once
    its bounded loop is exhausted.
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
        self.repair_loop = RepairLoop(self.runner, self.sandbox, self.meta_coder)
        self.controller = DualTrackController(
            runner=self.runner, meta_coder=self.meta_coder, sandbox=self.sandbox
        )
        self.evidence_store = EvidenceStore(base_path=evidence_path)
        self.run_registry = RunRegistry()
        self.replication_diff = ReplicationDiff()

    def run_full_pipeline(
        self,
        factor_id: str,
        snapshot_id: str,
        paper_text: str,
        plan: ExperimentPlan | None = None,
        config_overrides: dict | None = None,
    ) -> tuple[list[RunRecord], PipelineStatus]:
        """Run all 7 steps end-to-end for a single factor: extract -> review
        -> generate -> validate -> execute -> dual-track/ablations ->
        replication-diff.
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
                crsp_msf.parquet/comp_funda.parquet/ccm_lnkhist.parquet
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

        # --- 2. Review (+ bounded Review -> Extractor targeted re-extraction) ---
        # If the reviewer judges a high-impact field was likely MIS-extracted
        # (in the paper but read wrong) it returns remediation_mode ==
        # TARGETED_REEXTRACTION; we then re-extract JUST those fields with the
        # reviewer's paper-quote feedback and re-review, bounded by
        # MAX_REEXTRACT. We never auto-edit empirical values here -- the
        # extractor re-reads the paper and the reviewer re-judges. Anything the
        # loop can't resolve (paper genuinely silent, budget exhausted,
        # FULL_REGENERATION, or blocked fields) escalates to a human.
        status.stage = "review"
        review_result = self._review(spec, paper_text)

        while True:
            if review_result.requires_human:
                status.needs_manual = True
                status.stage = "failed"
                status.error = f"Blocked fields: {review_result.blocked_fields}"
                return [], status

            if review_result.approved:
                break

            remediation = getattr(
                review_result.remediation_mode, "value", review_result.remediation_mode
            )

            if remediation == RemediationMode.TARGETED_REEXTRACTION.value:
                feedback = self._build_reextract_feedback(review_result, spec)
                # Only fields the reviewer backed with a paper quote are
                # re-extractable (the extractor can re-read that passage). No
                # citations -> the paper is likely silent -> a human, not a
                # re-read, is needed.
                if not feedback or spec.reextraction_attempts >= MAX_REEXTRACT:
                    status.needs_manual = True
                    status.stage = "failed"
                    status.error = (
                        "Targeted re-extraction exhausted or not actionable; "
                        f"needs human review. Issues: {review_result.issues}"
                    )
                    return [], status

                status.stage = "reextract"
                prior_attempts = spec.reextraction_attempts
                extraction = self.extractor.extract(
                    factor_id=factor_id,
                    paper_text=paper_text,
                    reextract_feedback=feedback,
                )
                if extraction.spec is None:
                    status.needs_manual = True
                    status.stage = "failed"
                    status.error = extraction.error or "Re-extraction produced no MethodSpec"
                    return [], status
                spec = extraction.spec
                spec.reextraction_attempts = prior_attempts + 1

                status.stage = "review"
                review_result = self._review(spec, paper_text)
                continue

            # FULL_REGENERATION or RESOLVE_EXISTING_JSON with unresolved issues:
            # not something this loop auto-fixes -> escalate to a human.
            status.needs_manual = remediation == RemediationMode.FULL_REGENERATION.value
            status.stage = "failed"
            status.error = f"Review not approved ({remediation}): {review_result.issues}"
            return [], status

        spec.review_status = "approved"
        spec.codegen_ready = review_result.codegen_ready
        spec.paper_faithful = review_result.paper_faithful
        spec.remediation_mode = review_result.remediation_mode

        # --- 3-4. Generate plugin, then build+validate the script via the
        # shared RepairLoop (bounded Sandbox->Meta-Coder technical repair, the
        # same loop `run_from_method_spec` and `DualTrackController` use), so
        # the "validated == executed" invariant holds here too ---
        status.stage = "generate"
        plugin = self.meta_coder.generate_plugin(spec)

        status.stage = "validate"
        try:
            validated = self.repair_loop.build_validate_repair(
                plugin, spec, snapshot_id, config_overrides
            )
            plugin = validated.plugin
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

        # --- 7. Replication-diff analysis ---
        status.stage = "replication_diff"
        if plan.run_original and plan.run_standardized and len(runs) >= 2:
            self.replication_diff.diff_ablation(runs)

        status.stage = "done"
        return runs, status

    def _review(self, spec: MethodSpec, paper_text: str):
        """Review a spec, preferring the LLM auditor (which can call for a
        targeted re-extraction via `remediation_mode`) when an LLM client is
        available, falling back to the deterministic rule-based review
        otherwise. Returns a ReviewResult.
        """
        if getattr(self.review_gate, "llm_client", None) is not None and paper_text:
            review_result, _raw = self.review_gate.review_with_llm(spec, paper_text)
            return review_result
        return self.review_gate.review(spec)

    def _build_reextract_feedback(self, review_result, spec: MethodSpec) -> list[dict]:
        """Build targeted re-extraction feedback from a ReviewResult.

        Only fields the reviewer backed with a paper QUOTE are actionable: a
        citation means the paper states it and the extractor just misread it
        (re-readable), whereas no citation means the paper is likely silent
        (re-reading nothing won't help -> a human, not a re-extract). So this
        returns one feedback item per flagged, non-approved field note that
        carries at least one evidence citation; an empty list means "nothing
        the extractor can act on -> escalate to human".
        """
        feedback: list[dict] = []
        for note in getattr(review_result, "field_notes", []):
            status_val = getattr(note.status, "value", note.status)
            if status_val in ("auto_approve", "auto_approve_with_flag", "approve_with_default"):
                continue
            evidence = getattr(note, "evidence", []) or []
            if not evidence:
                continue
            feedback.append({
                "field": note.field,
                "reason": note.reason,
                "prior_value": getattr(note, "current_value", None),
                "paper_evidence": [
                    (e.model_dump() if hasattr(e, "model_dump") else e) for e in evidence
                ],
            })
        return feedback

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
            self.evidence_store.save_run(failed)
            self.run_registry.register(failed)
            raise RuntimeError(outcome.error)

        run = self.runner.make_run_record(spec, plugin, track, outcome.result)
        run.repair_history = repair_history
        self.evidence_store.save_run(run)
        self.run_registry.register(run)
        return run

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
