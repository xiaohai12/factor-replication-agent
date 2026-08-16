"""Basic multi-track controller for original, standardized, and OAT runs.

The module/directory retain their historical name for API compatibility.
Batch-level plugin freeze is IMPLEMENTED as of 2026-08-04 (Phase 0.6):
`run_experiment`/`run_from_matrix` run once with repair allowed, and if any
track's execution repair changed its code away from the batch's frozen
plugin, the WHOLE batch is automatically re-run from that newly-repaired
plugin with repair DISABLED (bounded to one re-freeze attempt by default) --
see `_run_tracks_with_freeze`. Because that re-run pass never itself
repairs, a track that still can't run under the shared re-frozen plugin
simply becomes `status="failed"` rather than "successful but still
divergent" -- with the default 1 re-freeze attempt, `batch_invalidated`
therefore only ever fires in practice when the caller explicitly passes
`max_refreeze_attempts=0` (skip the freeze/re-run entirely), which
`run_experiment`/`run_from_matrix` don't do. `run_from_matrix`
(2026-08-03, Phase A2) executes a declarative
`experiment_spec.ExperimentMatrix` loaded from an
`experiments/<factor_id>.experiments.yaml` file. `run_experiment` (the
legacy `ExperimentPlan` entry point) is now a THIN ADAPTER over
`run_from_matrix` (2026-08-04): `_plan_to_matrix` converts a plan's
`ablation_switches`/`factorial_switches` into resolved `ExperimentSpec`
entries via the SAME `experiment_spec.build_experiment_spec` derivation the
yaml path uses, so both entry points share one execution implementation
(batch/plugin-freeze bookkeeping, `comparison.json` writing, bridge-track
handling) instead of two divergent ones. `factorial_switches` (declared on
`ExperimentPlan` since early on but never executed) is now implemented as a
real full-factorial expansion (`_factorial_track_specs`). Complete evidence
persistence and further external C&Z reference bridge factors (Phase B/C&D)
remain future work.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.registry import build_config
from src.steps.step4_validator import AdversarialSandbox
from src.steps.step7_replication_diff import safe_diff_ablation
from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.repair import RepairLoop

if TYPE_CHECKING:
    from src.steps.step6_dual_track_controller.experiment_spec import ExperimentMatrix
    from src.steps.step8_diagnosis import ReplicationDiagnoser


def _spec_factor_id(spec: ResolvedMethodSpec) -> str:
    return spec.paper.factor_id


class _NoRepairMetaCoder:
    """A `MetaCoder` stand-in with `llm_client=None` -- `RepairLoop` checks
    exactly this attribute to decide whether repair is even attempted
    (`can_repair = attempt < max_retries and meta_coder.llm_client is not
    None` in `src/infra/repair.py`), so a `RepairLoop` built with this object
    ends its bounded loop on the FIRST execution failure instead of ever
    calling `repair_plugin`. Used for the frozen re-run pass in
    `_run_tracks_with_freeze`: once a plugin has been re-frozen after a
    repair, no further per-track drift is allowed for the rest of that
    batch attempt."""

    llm_client = None

    def repair_plugin(self, plugin, errors):  # pragma: no cover -- never called
        raise RuntimeError("repair_plugin() must never be called with llm_client=None")


# Standardized-track config: force EVERY factor onto one uniform "house
# standard" so cross-factor results are comparable and any original-vs-standard
# gap is attributable to a known set of switches. This is NOT auto-derived from
# any dataset — it is a hand-curated convention. Provenance per field (cited so
# the "standard" is defensible in the paper — see docs/cz-reference.md §7):
#
#   breakpoint_source="nyse"      Hou, Xue & Zhang (2020, RFS) "Replicating
#   breakpoint_quantiles=deciles   Anomalies" — NYSE breakpoints + value weights
#   weighting_rule="vw"            + decile sorts are their core protocol for
#                                  damping microcap influence.
#   rebalance_frequency="monthly"  HXZ q-factor protocol (monthly VW rebalance).
#   holding_period_months=1        1-month holding (standard monthly-rebalanced).
#   universe (exchcd 1/2/3,        Common CRSP ordinary-common-stock universe
#     shrcd 10/11)                 (Fama-French / HXZ shared convention).
#   accounting_lag_months=6        Fama-French (1992) 6-month accounting lag,
#                                  NOT HXZ (HXZ match most-recent quarterly
#                                  earnings monthly). Kept here as the
#                                  conservative FF-style default; the "HXZ"
#                                  label is therefore approximate for THIS field.
#   missing_action="drop"          Drop firm-months with a missing signal input.
#
# Distinct from step2's SENSIBLE_DEFAULTS (a DIFFERENT concept): that fills a
# paper-SILENT field with its field-level convention to keep `original_method`
# faithful to the paper; this deliberately OVERRIDES the paper onto one house
# standard. They legitimately differ — e.g. rebalance is "annual" there (the
# usual default for an unspecified accounting-factor rebalance) vs "monthly"
# here (the HXZ standardized protocol). Do not merge them.
HXZ_STANDARD_CONFIG = {
    "breakpoint_source": "nyse",
    # Decile sort: the engine's `breakpoint_quantiles` is the GROUP COUNT
    # (see `BacktestExecutor.compute_breakpoints`, `int(config.get(
    # "breakpoint_quantiles", 10))`), not a list of percentile cutpoints.
    # This was previously the literal percentile list [10, 20, ..., 90] (9
    # decile cutpoints), which `int(...)` on a list raises TypeError on --
    # the standardized_hxz track has never actually been runnable. See
    # docs/decision-log.md 2026-08-02 entry and docs/roadmap.md Immediate
    # Correctness Work #1.
    "breakpoint_quantiles": 10,
    "weighting_rule": "vw",
    "rebalance_frequency": "monthly",
    "holding_period_months": 1,
    "accounting_lag_months": 6,
    "missing_action": "drop",
    "universe": "NYSE + AMEX + NASDAQ, exchcd in (1,2,3), shrcd in (10,11)",
}

# Shared by `_get_ablation_override` (single-switch flip) and
# `MultiTrackController._factorial_track_specs` (multi-switch cartesian
# expansion) -- one mapping, not two, so a switch name always resolves to
# the same config key in both places.
_ABLATION_SWITCH_TO_CONFIG_KEY: dict[str, str] = {
    "breakpoint": "breakpoint_source",
    "weighting": "weighting_rule",
    "lag": "accounting_lag_months",
    "missing": "missing_action",
    "rebalance": "rebalance_frequency",
    "universe": "universe",
}


@dataclass
class ExperimentPlan:
    """Defines which tracks and ablations to run for a factor."""

    factor_id: str
    run_original: bool = True
    run_standardized: bool = True
    ablation_switches: list[str] = field(default_factory=list)
    factorial_switches: list[str] = field(default_factory=list)
    # `C_cz` as a runnable config override (docs/step6.md gap #1,
    # `src.infra.reference.cz_profile_to_config_override`) -- a human-
    # reviewed dict from the step6 UI's C&Z-config preview, not derived
    # here; None means no `cz_actual_config` track is added.
    cz_config_override: dict[str, Any] | None = None


class MultiTrackController:
    """Controls multi-track experiments for implementation-gap analysis.

    Tracks:
    - original_method: Faithful to paper/C&Z/OSAP settings
    - standardized_hxz: Uniform HXZ-style standardized settings
    - ablation_*: Change one implementation choice at a time
    - factorial_*: Full-factorial combinations

    Each track is Step 5 (build script -> execute) run once per config
    override, with a bounded repair loop on execution failure — the same
    Step-5-fails-loop-to-Step-3 pattern `Pipeline.run_from_method_spec` uses
    for the single-track path, so a factor with an ablation plan gets the same
    self-debugging safety net as a plain single-track run.
    """

    def __init__(
        self,
        runner: BacktestRunner,
        meta_coder: MetaCoder,
        sandbox: AdversarialSandbox,
        diagnoser: "ReplicationDiagnoser | None" = None,
    ):
        self.runner = runner
        self.meta_coder = meta_coder
        self.sandbox = sandbox
        # Optional step-8 LLM explanation layer. Opt-in by construction (None
        # by default) so batch runs and tests never spend an LLM call, and so
        # the empirical artifacts are complete without it -- per AGENTS.md the
        # diagnosis is commentary on numbers that already exist.
        self.diagnoser = diagnoser
        # The one shared technical repair loop — same object type Pipeline uses,
        # so per-track execute failures get the identical bounded
        # repair -> rebuild -> re-validate behavior (see src/infra/repair.py).
        self.repair_loop = RepairLoop(runner, sandbox, meta_coder)
        # A second repair loop with repair disabled, used only for the
        # frozen re-run pass in `_run_tracks_with_freeze` (Phase 0.6) --
        # once a plugin has been re-frozen after a repair, no further
        # per-track code drift is allowed for the rest of that attempt.
        self._frozen_repair_loop = RepairLoop(runner, sandbox, _NoRepairMetaCoder())

    def run_experiment(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        plan: ExperimentPlan,
        snapshot_id: str,
        reuse_original_run: RunRecord | None = None,
    ) -> list[RunRecord]:
        """Run all planned tracks for a factor.

        Thin adapter over `run_from_matrix`: `plan` is converted to an
        `experiment_spec.ExperimentMatrix` (`_plan_to_matrix`) so the legacy
        Python-constructed `ExperimentPlan` path and the declarative yaml
        path share ONE execution implementation (batch/plugin-freeze
        bookkeeping, `comparison.json` writing, bridge-track handling) --
        see docs/decision-log.md for why these were merged. `plan`'s
        `ablation_switches` and (newly-implemented; see docs/multi-config-
        evidence-plan.md's "don't leave two half-finished interfaces" note)
        `factorial_switches` both become resolved `ExperimentSpec` entries
        with the SAME `family`/`identification_level` derivation the yaml
        path uses.

        `reuse_original_run`: an already-persisted `original_method` run
        (e.g. step5's own execution) to reuse for \u2460 instead of re-running
        it -- no matching/validation against this call's plugin/spec/
        snapshot, the caller is trusted to only pass a genuinely equivalent
        run.

        `plugin` is assumed already validated (Step4, done once before this
        is called — every track shares the same signal formula, only
        `config_overrides` differs per track, so re-running the compute_signal
        smoke test per track would be redundant). A per-track execution
        failure still gets its own bounded repair loop (see `_run_track`).
        """
        matrix = self._plan_to_matrix(plan, spec)
        return self.run_from_matrix(
            plugin, spec, matrix, snapshot_id, run_baseline=plan.run_original,
            reused_baseline_run=reuse_original_run,
        )

    def _plan_to_matrix(self, plan: ExperimentPlan, spec: ResolvedMethodSpec) -> "ExperimentMatrix":
        """Convert a legacy `ExperimentPlan` into an
        `experiment_spec.ExperimentMatrix` with the exact same
        `family`/`identification_level` derivation the declarative yaml path
        uses (`experiment_spec.build_experiment_spec`) -- see
        `run_experiment`'s docstring. The `original_method` baseline itself
        is NOT included here (`run_from_matrix` always runs it separately,
        gated by its own `run_baseline` param); this only builds the
        `standardized_hxz`, `ablation_*`, and `factorial_*` entries.
        """
        from src.steps.step6_dual_track_controller.experiment_spec import (
            ExperimentMatrix,
            build_experiment_spec,
        )

        baseline_config = build_config(spec, None)
        specs = []

        if plan.run_standardized:
            specs.append(
                build_experiment_spec("standardized_hxz", spec, baseline_config, HXZ_STANDARD_CONFIG)
            )

        if plan.cz_config_override:
            specs.append(
                build_experiment_spec("cz_actual_config", spec, baseline_config, plan.cz_config_override)
            )

        for switch in plan.ablation_switches:
            override = self._get_ablation_override(switch, spec)
            specs.append(
                build_experiment_spec(f"ablation_{switch}", spec, baseline_config, override)
            )

        for name, overrides in self._factorial_track_specs(plan.factorial_switches, baseline_config):
            specs.append(build_experiment_spec(name, spec, baseline_config, overrides))

        # The plan's own declared shape is itself part of a run's
        # reproducible identity, matching the yaml matrix's
        # `experiment_spec_hash` -- same principle, applied to a
        # Python-constructed plan instead of a yaml file's text.
        plan_repr = json.dumps(
            {
                "factor_id": plan.factor_id,
                "run_original": plan.run_original,
                "run_standardized": plan.run_standardized,
                "ablation_switches": sorted(plan.ablation_switches),
                "factorial_switches": sorted(plan.factorial_switches),
                "cz_config_override": plan.cz_config_override or {},
            },
            sort_keys=True,
        )
        experiment_spec_hash = hashlib.sha256(plan_repr.encode("utf-8")).hexdigest()

        return ExperimentMatrix(
            factor_id=_spec_factor_id(spec),
            baseline="original_method",
            experiments=specs,
            experiment_spec_hash=experiment_spec_hash,
        )

    def _factorial_track_specs(
        self, switches: list[str], baseline_config: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Full-factorial expansion of `ExperimentPlan.factorial_switches`
        (docs/multi-config-evidence-plan.md's previously-declared-but-never-
        executed field -- see docs/decision-log.md for this implementation):
        the cartesian product of {baseline value, HXZ-standardized value}
        for EACH given switch simultaneously (2^n combinations), excluding
        the all-baseline corner (redundant with `original_method` itself).

        A single-switch factorial (`len(switches) == 1`) is intentionally
        NOT the same as `ablation_switches`' single-switch flip: this
        function always names its output `factorial_*` regardless of switch
        count, so a factorial declaration's tracks are never confused with
        an ablation declaration's, even if a caller only lists one switch.
        """
        if not switches:
            return []

        keys = [k for s in switches if (k := _ABLATION_SWITCH_TO_CONFIG_KEY.get(s)) is not None]
        if not keys:
            return []

        value_options = [(baseline_config[k], HXZ_STANDARD_CONFIG[k]) for k in keys]
        baseline_combo = tuple(baseline_config[k] for k in keys)

        # De-duplicated by NAME (not just position in the cartesian product):
        # when a switch's baseline value happens to coincide with its own
        # HXZ-standardized value (e.g. the paper's own weighting is already
        # "vw", HXZ's default too), `itertools.product` yields the SAME
        # resulting override dict from more than one input position --
        # without dedup this would produce two `RunRecord`s with an
        # IDENTICAL track name, silently colliding on the same on-disk
        # script/output path (the second overwrites the first) and losing
        # one entry from `comparison.json`'s `tracks` dict (a plain
        # `{name: ...}` mapping) with no error.
        results: list[tuple[str, dict[str, Any]]] = []
        seen_names: set[str] = set()
        for combo in itertools.product(*value_options):
            if combo == baseline_combo:
                continue
            overrides = dict(zip(keys, combo))
            suffix = "_".join(f"{k}={v}" for k, v in overrides.items())
            name = f"factorial_{suffix}"
            if name in seen_names:
                continue
            seen_names.add(name)
            results.append((name, overrides))
        return results

    def run_from_matrix(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        matrix: "ExperimentMatrix",
        snapshot_id: str,
        run_baseline: bool = True,
        reused_baseline_run: RunRecord | None = None,
    ) -> list[RunRecord]:
        """Run every experiment in a loaded, validated
        `experiment_spec.ExperimentMatrix` (Phase A2,
        docs/multi-config-evidence-plan.md) as its own track, plus the
        implicit `original_method` baseline (no overrides) when
        `run_baseline` is True (the default -- set False by
        `run_experiment` when the caller's `ExperimentPlan.run_original` is
        False).

        `reused_baseline_run`: reuse this ALREADY-persisted `original_method`
        run for ① instead of re-executing it (e.g. step5's own execution).
        Deep-copied with a NEW `run_id` before being included in `runs` --
        it must never share persistence identity with the run it was copied
        from (that run's own evidence-store artifact must not be
        overwritten by this batch's bookkeeping).

        Each `RunRecord`'s `logs` gets one line recording that experiment's
        derived `family`/`identification_level` (computed by
        `load_experiment_matrix`, never re-derived here) so a human/LLM
        reading the run doesn't need the yaml file re-loaded to know how it
        was classified. `comparison.json`'s `"batch"` key additionally
        carries the whole matrix's `experiment_spec_hash` -- "this batch
        declared exactly these experiments" is itself part of a run's
        reproducible identity.

        An experiment with `signal_input_ref: "cz_bridge"` (optionally
        `"cz_bridge:<factor_id>"` to reference a DIFFERENT registered
        factor_id than this spec's own) is run as a real C&Z bridge track
        via `_run_bridge_track` -- see `src.infra.reference.cz_bridge` for
        which factors have a registered bridge. Any OTHER
        `signal_input_ref` value, or a `snapshot_ref` (data-vintage tracks),
        is recorded but SKIPPED with a log line -- no adapter exists yet for
        those (still pending real external data work); running only the
        config-override experiments here would otherwise silently
        under-report what the matrix declared.
        """
        batch_id = uuid.uuid4().hex[:12]
        track_overrides: dict[str, dict[str, Any]] = {}
        track_specs: list[tuple[str, dict[str, Any]]] = []
        reused_runs: list[RunRecord] = []
        if run_baseline:
            track_overrides["original_method"] = {}
            if reused_baseline_run is None:
                track_specs.append(("original_method", {}))
            else:
                reused_runs.append(self._copy_reused_baseline_run(reused_baseline_run))
        identification_by_track: dict[str, tuple[str, str]] = {}
        skipped: list[str] = []
        bridge_runs: list[RunRecord] = []

        for exp in matrix.experiments:
            if exp.signal_input_ref:
                if exp.signal_input_ref == "cz_bridge" or exp.signal_input_ref.startswith("cz_bridge:"):
                    cz_factor_id = (
                        exp.signal_input_ref.split(":", 1)[1]
                        if ":" in exp.signal_input_ref
                        else _spec_factor_id(spec)
                    )
                    bridge_run = self._run_bridge_track(
                        plugin, spec, snapshot_id, exp.name, cz_factor_id, exp.config_overrides
                    )
                    if bridge_run is None:
                        skipped.append(exp.name)
                        continue
                    track_overrides[exp.name] = exp.config_overrides
                    bridge_runs.append(bridge_run)
                    # A bridge track moves the signal axis (and possibly a
                    # config axis too, via exp.config_overrides) -- it must
                    # get the same family/identification_level labeling as
                    # any other track (docs/step6.md \u00a723.3: previously
                    # skipped entirely, so a bridge track that ALSO changed
                    # a config key was silently never flagged `unidentified`).
                    identification_by_track[exp.name] = (exp.family, exp.identification_level)
                else:
                    skipped.append(exp.name)
                continue
            if exp.snapshot_ref:
                skipped.append(exp.name)
                continue
            track_overrides[exp.name] = exp.config_overrides
            track_specs.append((exp.name, exp.config_overrides))
            identification_by_track[exp.name] = (exp.family, exp.identification_level)

        runs, effective_plugin, refreeze_attempts = self._run_tracks_with_freeze(
            plugin, spec, snapshot_id, track_specs
        )
        runs.extend(bridge_runs)
        runs.extend(reused_runs)
        for run in runs:
            if run.track in identification_by_track:
                family, identification_level = identification_by_track[run.track]
                run.logs = list(run.logs) + [
                    f"experiment_matrix: family={family!r} "
                    f"identification_level={identification_level!r}"
                ]

        batch_info = {
            "experiment_spec_hash": matrix.experiment_spec_hash,
            "skipped_experiments": skipped,
        }
        if refreeze_attempts:
            batch_info["refreeze_attempts"] = refreeze_attempts
        return self._finalize_batch(
            effective_plugin, spec, snapshot_id, runs, track_overrides, batch_id,
            extra_batch_info=batch_info,
        )

    def _finalize_batch(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        runs: list[RunRecord],
        track_overrides: dict[str, dict[str, Any]],
        batch_id: str,
        extra_batch_info: dict[str, Any] | None = None,
    ) -> list[RunRecord]:
        """Shared tail for `run_experiment`/`run_from_matrix`: batch/plugin-
        freeze bookkeeping (Phase 0.6) + the aggregate `comparison.json`
        write (+ optional step-8 diagnosis). `plugin.code_hash` here is the
        frozen hash as it was BEFORE any track ran -- see `run_experiment`'s
        docstring for the full invalidation rationale.

        Bridge tracks (`RunRecord.is_bridge_track=True`, see
        `_run_bridge_track`) are EXCLUDED from the "every track ran
        identical code" consistency check below -- a bridge track's whole
        point is a different signal source under the same config, which is
        never expected to share the agent plugin's `code_hash`.
        """
        frozen_plugin_hash = plugin.code_hash

        divergent_tracks = sorted(
            r.track for r in runs
            if r.status == "success" and not r.is_bridge_track and r.code_hash != frozen_plugin_hash
        )
        batch_invalidated = bool(divergent_tracks)
        batch_invalidation_reason = (
            "A track-local repair changed the plugin code (code_hash) away "
            f"from this batch's frozen hash {frozen_plugin_hash[:8]!r} on "
            f"track(s): {', '.join(divergent_tracks)}. Cross-track config "
            "comparisons in this batch are no longer attributable to config "
            "alone -- see docs/multi-config-evidence-plan.md Phase 0.6."
            if batch_invalidated
            else ""
        )
        for r in runs:
            r.experiment_batch_id = batch_id
            r.frozen_plugin_hash = frozen_plugin_hash
            r.batch_invalidated = batch_invalidated
            r.batch_invalidation_reason = batch_invalidation_reason

        tracks_summary = {
            r.track: {
                "config": build_config(spec, track_overrides.get(r.track)),
                "metrics": r.metrics.model_dump(),
                "is_bridge_track": r.is_bridge_track,
            }
            for r in runs
            if r.status == "success"
        }
        if tracks_summary:
            batch_info = {
                "experiment_batch_id": batch_id,
                "frozen_plugin_hash": frozen_plugin_hash,
                "batch_invalidated": batch_invalidated,
                "batch_invalidation_reason": batch_invalidation_reason,
            }
            batch_info.update(extra_batch_info or {})
            comparison_path = self.runner.write_comparison_summary(
                spec,
                tracks_summary,
                snapshot_id=snapshot_id,
                diff_result=safe_diff_ablation(runs),
                batch_info=batch_info,
            )
            if self.diagnoser is not None:
                self._write_diagnosis(comparison_path)

        return runs

    def _write_diagnosis(self, comparison_path: Path) -> None:
        """Run the optional step-8 LLM explanation layer over the bundle just
        written, emitting `diagnosis.json` + `diagnosis.md` alongside it.

        A diagnosis failure must never invalidate the empirical artifacts, so
        the call is best-effort: the tracks already ran and comparison.json is
        already on disk.
        """
        from src.steps.step8_diagnosis.render import write_diagnosis

        bundle = json.loads(comparison_path.read_text())
        report = self.diagnoser.diagnose(bundle)
        write_diagnosis(report, bundle, comparison_path.parent)

    def _run_bridge_track(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        track_name: str,
        cz_signal_factor_id: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> RunRecord | None:
        """Run a C&Z signal BRIDGE track (Phase C/D,
        docs/multi-config-evidence-plan.md): `compute_cz_bridge_signal`'s
        output for `cz_signal_factor_id`, fed into the SAME resolved config
        as every other track, bypassing this factor's own `compute_signal()`
        entirely (`BacktestRunner.build_script`'s `precomputed_signal_path`
        param -> `script_generator`'s `PRECOMPUTED_SIGNAL_PATH` branch). This
        isolates signal-implementation differences from portfolio-
        construction differences -- the actual point of a "bridge"
        experiment: same engine, same config, only the signal source
        differs.

        Returns `None` if no bridge is registered for `cz_signal_factor_id`
        (see `src.infra.reference.cz_bridge.CZ_BRIDGE_SIGNALS`) -- callers
        should skip the track / log a note when this happens, not treat it
        as a failed run (a registration gap is not a runtime failure).

        Does NOT go through the shared bounded `RepairLoop`: a bridge
        track's entire content is an externally-supplied signal, not
        agent-generated code, so there is nothing for
        `MetaCoder.repair_plugin` to meaningfully fix here -- an execution
        failure is reported as-is (`status="failed"`).

        The returned `RunRecord` has `is_bridge_track=True` and a
        descriptive (non-agent) `code_hash` -- see `RunRecord.
        is_bridge_track`'s docstring for why it's excluded from
        `_finalize_batch`'s "every track ran identical code" check.
        """
        from src.infra.reference.cz_bridge import compute_cz_bridge_signal

        snapshot = self.runner.data_layer.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            raise RuntimeError(f"Snapshot '{snapshot_id}' not registered on this DataLayer")
        storage_path = Path(snapshot.storage_path)

        cz_signal = compute_cz_bridge_signal(cz_signal_factor_id, storage_path)
        if cz_signal is None:
            return None

        # Persist the bridge signal to a real file the generated script can
        # load directly (see build_script's precomputed_signal_path param).
        bridge_dir = self.runner.scripts_path / "results" / _spec_factor_id(spec)
        bridge_dir.mkdir(parents=True, exist_ok=True)
        bridge_signal_path = bridge_dir / f"{track_name}.cz_bridge_input.parquet"
        cz_signal.to_parquet(bridge_signal_path, index=False)

        built = self.runner.build_script(
            plugin, spec, snapshot_id, config_overrides, track_name,
            precomputed_signal_path=str(bridge_signal_path),
        )
        try:
            result = self.runner.execute(built)
        except RuntimeError as exc:
            record = self.runner.make_failed_run_record(
                spec, plugin, track_name, config_overrides, str(exc)
            )
        else:
            record = self.runner.make_run_record(spec, plugin, track_name, result)
            # NOT the agent plugin's code_hash -- this track's signal came
            # from cz_signal_factor_id, not compute_signal(). See
            # RunRecord.is_bridge_track's docstring.
            record.code_hash = f"cz_bridge:{cz_signal_factor_id}"
        record.is_bridge_track = True
        return record

    def _copy_reused_baseline_run(self, run: RunRecord) -> RunRecord:
        """Deep-copies a reused baseline `RunRecord` under a NEW `run_id` --
        it must never share persistence identity with the run it was copied
        from (`backend`'s `evidence_store.save_run`/`run_registry.register`
        key off `run_id`; reusing the original id would silently overwrite
        that run's own evidence-store artifact with THIS batch's
        bookkeeping fields)."""
        reused = run.model_copy(deep=True)
        reused.run_id = f"{run.run_id}__reused_{uuid.uuid4().hex[:8]}"
        reused.logs = list(reused.logs) + [f"reused run {run.run_id!r} for track 'original_method'"]
        return reused

    def _run_track(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        track_name: str,
        config_overrides: dict[str, Any],
        repair_loop: RepairLoop | None = None,
    ) -> tuple[RunRecord, PluginRecord]:
        """Build this track's script (from an already-validated plugin) and
        execute it via a `RepairLoop` (Step 5) -- `self.repair_loop` by
        default, or the caller-supplied `repair_loop` (used by
        `_run_tracks_with_freeze`'s no-repair re-run pass). On an execution
        failure the loop feeds back to Step 3 (`MetaCoder.repair_plugin`)
        with a Step 4 re-validate, bounded by `MAX_REPAIR_RETRIES`. On
        exhaustion a status="failed" RunRecord is returned instead of
        raising. The repair history is attached to the RunRecord for audit.

        Returns `(record, plugin_used)` -- the plugin actually used for
        THIS track (identical to the input `plugin` unless a repair changed
        it), so callers can detect/act on per-track code drift without
        re-deriving it from `record.code_hash`.

        `track_name` is threaded into `build_script`/`execute_with_repair` so
        each track writes to its own `{factor_id}__{track_name}` script/output
        path -- multiple tracks for the same factor no longer overwrite each
        other's on-disk artifact (see docs/decision-log.md).
        """
        loop = repair_loop or self.repair_loop
        built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides, track_name)
        outcome = loop.execute_with_repair(
            plugin, built, spec, snapshot_id, config_overrides, track_name=track_name
        )
        if outcome.error is not None:
            record = self.runner.make_failed_run_record(
                spec, outcome.plugin, track_name, config_overrides, outcome.error
            )
        else:
            record = self.runner.make_run_record(
                spec, outcome.plugin, track_name, outcome.result
            )
        record.repair_history = outcome.history
        return record, outcome.plugin

    def _run_tracks_with_freeze(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        track_specs: list[tuple[str, dict[str, Any]]],
        max_refreeze_attempts: int = 1,
    ) -> tuple[list[RunRecord], PluginRecord, int]:
        """Run every `(track_name, config_overrides)` in `track_specs`,
        automatically re-running the WHOLE batch from a re-frozen plugin if
        any track's repair changed its code (Phase 0.6 full freeze,
        docs/multi-config-evidence-plan.md).

        Pass 1 runs every track with repair allowed (`self.repair_loop`). If
        every successful track's code matches the ORIGINAL `plugin.code_hash`
        (no repair fired, or every repair coincidentally reproduced the same
        code), the batch is internally consistent and this returns
        immediately. Otherwise: pick the plugin actually used by the FIRST
        track (in `track_specs` order) whose code diverged, and re-run EVERY
        track in the batch (including ones that already succeeded) against
        that single re-frozen plugin, with repair DISABLED
        (`self._frozen_repair_loop`) -- so this pass either converges (every
        successful track now shares the same code) or fails outright rather
        than silently drifting further. Bounded to `max_refreeze_attempts`
        re-runs (default 1).

        Returns `(runs, effective_frozen_plugin, refreeze_attempts)` --
        `effective_frozen_plugin` is `current_plugin` as of the LAST pass
        actually run (the original `plugin` if no refreeze happened), which
        the caller (`_finalize_batch`) uses as the invalidation baseline
        instead of the stale original -- if the batch DID converge after a
        refreeze, it's correctly no longer flagged invalidated just because
        it differs from the very first attempt. `refreeze_attempts` (0 if no
        repair ever fired) is recorded on the batch for auditability even
        when it converged.

        A single-track "batch" (`len(track_specs) <= 1`) never triggers a
        refreeze pass regardless of whether its one track's repair changed
        its code -- consistency is a CROSS-track property; a lone track has
        no other track to be consistent with, so a second confirmation pass
        would only waste an execution with no comparability benefit.
        """
        if len(track_specs) <= 1:
            runs = []
            for track_name, overrides in track_specs:
                record, _used_plugin = self._run_track(plugin, spec, snapshot_id, track_name, overrides)
                runs.append(record)
            return runs, plugin, 0

        current_plugin = plugin
        attempt = 0
        while True:
            runs: list[RunRecord] = []
            used_plugins: dict[str, PluginRecord] = {}
            loop = self.repair_loop if attempt == 0 else self._frozen_repair_loop
            for track_name, overrides in track_specs:
                record, used_plugin = self._run_track(
                    current_plugin, spec, snapshot_id, track_name, overrides, repair_loop=loop
                )
                runs.append(record)
                used_plugins[track_name] = used_plugin

            divergent = [
                (name, used_plugins[name])
                for name, _ in track_specs
                if next(r for r in runs if r.track == name).status == "success"
                and used_plugins[name].code_hash != current_plugin.code_hash
            ]
            if not divergent or attempt >= max_refreeze_attempts:
                return runs, current_plugin, attempt

            attempt += 1
            current_plugin = divergent[0][1]

    def _get_ablation_override(self, switch: str, spec: ResolvedMethodSpec) -> dict[str, Any]:
        """Get config override for a single ablation switch."""
        # Flip one setting from original to standardized (or vice versa)
        key = _ABLATION_SWITCH_TO_CONFIG_KEY.get(switch)
        return {key: HXZ_STANDARD_CONFIG[key]} if key else {}
