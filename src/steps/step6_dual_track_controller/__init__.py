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
(batch/plugin-freeze bookkeeping, `comparison.json` writing) instead of two
divergent ones. `factorial_switches` (declared on `ExperimentPlan` since
early on but never executed) is now implemented as a real full-factorial
expansion (`_factorial_track_specs`). Complete evidence persistence remains
future work, as does a C&Z signal bridge track (removed 2026-08-18 -- it was
never run; see CHANGELOG).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.reference import HXZ_STANDARD_CONFIG as HXZ_STANDARD_CONFIG
from src.infra.repair import RepairLoop
from src.steps.step3_codegen import MetaCoder
from src.steps.step3_codegen.registry import build_config
from src.steps.step4_validator import AdversarialSandbox
from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step7_replication_diff import safe_diff_ablation

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


# Standardized-track config ("C_std" / `standardized_hxz` track). Single
# canonical source is `data/reference/hxz_standard_config.yaml` (see that
# file's header for full field-by-field provenance against the HXZ paper,
# and docs/cz-reference.md §7) -- loaded here via
# `src.infra.reference.HXZ_STANDARD_CONFIG`, re-exported under this name so
# existing `from src.steps.step6_dual_track_controller import
# HXZ_STANDARD_CONFIG` imports keep working unchanged.
#
# Distinct from step2's SENSIBLE_DEFAULTS (a DIFFERENT concept): that fills a
# paper-SILENT field with its field-level convention to keep `original_method`
# faithful to the paper; this deliberately OVERRIDES the paper onto one house
# standard. They legitimately differ — e.g. rebalance is "annual" there (the
# usual default for an unspecified accounting-factor rebalance) vs "monthly"
# here. Do not merge them.

# Shared by `_get_ablation_override` (single-switch flip) and
# `MultiTrackController._factorial_track_specs` (multi-switch cartesian
# expansion) -- one mapping, not two, so a switch name always resolves to
# the same config key in both places.
#
# Deliberately excludes `missing_action`: `apply_missing_policy` never reads
# that config value (unconditional `dropna`, see its docstring), and every
# track this pipeline produces resolves it to the same "drop" regardless of
# the paper/C&Z/HXZ input (`STANDARD["missing_action"]` clamps anything else
# to "drop"; `HXZ_STANDARD_CONFIG` omits the key entirely for the same
# reason; `cz_profile_to_config_override` sets it to "drop" unconditionally).
# So it can never actually surface in `_diff_switches`, and if it somehow
# did, flipping it would be a phantom switch: a config value differs while
# the executed code is byte-identical, which would make a Shapley/OAT
# "zero contribution" for it unreadable as "this dimension doesn't matter"
# vs "this dimension was never actually exercised". 2026-08-19.
_ABLATION_SWITCH_TO_CONFIG_KEY: dict[str, str] = {
    "breakpoint": "breakpoint_source",
    "weighting": "weighting_rule",
    "lag": "accounting_lag_months",
    "rebalance": "rebalance_frequency",
    # config key renamed from "universe" (a display-only string, never read
    # by the engine) to "universe_filters" (the real, enforced key) 2026-08-16.
    "universe": "universe_filters",
}

# A switch's config key sometimes needs a second, non-switch config key
# carried along whenever it's overridden to `target_config`'s value --
# e.g. `universe_filters` referencing a Compustat column (like HXZ's `ceq`
# filter) is meaningless without `universe_filter_join_sources` telling the
# generated script's `join_universe_filter_sources()` how to attach that
# column to the returns panel; overriding one without the other produces a
# runtime `ValueError` ("Universe filter references field 'ceq', which the
# loaded returns panel does not have"), not a config mismatch.
_CONFIG_KEY_COMPANIONS: dict[str, tuple[str, ...]] = {
    "universe_filters": ("universe_filter_join_sources",),
}

# Inverse of `_ABLATION_SWITCH_TO_CONFIG_KEY`, used by `run_from_matrix` to
# derive `RunRecord.switches_flipped` from `ExperimentSpec.resolved_diff`
# (docs/step7-8.md Part V, Q2) -- injective by construction (every switch
# maps to its own distinct config key), so this reverses cleanly.
_CONFIG_KEY_TO_SWITCH: dict[str, str] = {v: k for k, v in _ABLATION_SWITCH_TO_CONFIG_KEY.items()}


def _switches_flipped_from_diff(resolved_diff: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Which of the known attribution switches `resolved_diff` (an
    `ExperimentSpec`'s config-key-level diff against baseline) touched, and
    what value each took -- e.g. `{"weighting": "vw"}`. Keys in `resolved_diff`
    that aren't one of the known switches (e.g. a companion key like
    `universe_filter_join_sources`, or an arbitrary yaml-authored override)
    are silently ignored here, not an error: this is a best-effort label for
    attribution, not a completeness check on the diff itself."""
    return {
        _CONFIG_KEY_TO_SWITCH[key]: details["track_value"]
        for key, details in resolved_diff.items()
        if key in _CONFIG_KEY_TO_SWITCH
    }

# docs/step6.md §4a's decision (2026-08-16, threshold lowered 5->4 on
# 2026-08-17 after adding Shapley-value attribution -- see docs/step7-8.md
# Part V): <=4 differing fields -> full factorial (exact, residual always
# 0, cheap at this size: 2^4=16 runs); >4 -> OAT fallback (linear cost,
# assumes no interaction between fields). Used by `_plan_to_matrix`'s
# auto-attribution default -- see that method. Also the ceiling for
# `attribution.compute_shapley_effects`'s "is the factorial grid complete"
# check, since Shapley needs the exact same 2^n grid.
MAX_FACTORIAL_SWITCHES = 4


def _diff_switches(baseline_config: dict[str, Any], target_config: dict[str, Any]) -> list[str]:
    """Which of the known `_ABLATION_SWITCH_TO_CONFIG_KEY` switches actually
    differ between `baseline_config` and `target_config` -- the input to
    auto-selecting factorial vs OAT (see `MAX_FACTORIAL_SWITCHES`). A switch
    whose config key isn't present in `target_config` at all (e.g. a
    `cz_config_override` that never touches `accounting_lag_months`) is
    never counted as differing."""
    return [
        switch
        for switch, key in _ABLATION_SWITCH_TO_CONFIG_KEY.items()
        if key in target_config and baseline_config.get(key) != target_config.get(key)
    ]


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
    # When True (the default) AND `ablation_switches`/`factorial_switches`
    # are both left empty -- the step6 UI's own default since the 2026-08-16
    # simplification removed the manual switch pickers -- `_plan_to_matrix`
    # auto-derives field-level attribution tracks for BOTH ①→③ and (when
    # `cz_config_override` is set) ①→②, per docs/step6.md §4a: <=5 differing
    # fields -> factorial (exact), >5 -> OAT fallback. Set False to get the
    # old behavior (no attribution tracks unless explicitly requested via
    # `ablation_switches`/`factorial_switches`).
    auto_attribution: bool = True


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
        progress: Callable[[str], None] | None = None,
    ) -> list[RunRecord]:
        """Run all planned tracks for a factor.

        Thin adapter over `run_from_matrix`: `plan` is converted to an
        `experiment_spec.ExperimentMatrix` (`_plan_to_matrix`) so the legacy
        Python-constructed `ExperimentPlan` path and the declarative yaml
        path share ONE execution implementation (batch/plugin-freeze
        bookkeeping, `comparison.json` writing) --
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
            reused_baseline_run=reuse_original_run, progress=progress,
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
            override = self._get_ablation_override(switch, HXZ_STANDARD_CONFIG)
            specs.append(
                build_experiment_spec(f"ablation_{switch}", spec, baseline_config, override)
            )

        for name, overrides in self._factorial_track_specs(plan.factorial_switches, baseline_config, HXZ_STANDARD_CONFIG):
            specs.append(build_experiment_spec(name, spec, baseline_config, overrides))

        # Auto-attribution (docs/step6.md §4a): only when the caller left
        # BOTH manual switch lists empty (never overrides an explicit
        # request) -- <=5 differing fields gets an exact factorial
        # expansion, >5 falls back to one-at-a-time. Runs once for ①→③
        # (only if `run_standardized`) and once for ①→② (only if
        # `cz_config_override` is set) -- the two comparisons can have
        # different field counts and therefore different modes.
        if plan.auto_attribution and not plan.ablation_switches and not plan.factorial_switches:
            if plan.run_standardized:
                specs.extend(
                    self._auto_attribution_specs(
                        spec, baseline_config, HXZ_STANDARD_CONFIG,
                        factorial_prefix="factorial", ablation_prefix="ablation",
                    )
                )
            if plan.cz_config_override:
                specs.extend(
                    self._auto_attribution_specs(
                        spec, baseline_config, plan.cz_config_override,
                        factorial_prefix="cz_factorial", ablation_prefix="cz_ablation",
                    )
                )

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
        self,
        switches: list[str],
        baseline_config: dict[str, Any],
        target_config: dict[str, Any],
        name_prefix: str = "factorial",
        exclude_combos: "set[frozenset[str]] | None" = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Full-factorial expansion of a set of switches: the cartesian
        product of {baseline value, `target_config`'s value} for EACH given
        switch simultaneously (2^n combinations), excluding the
        all-baseline corner (redundant with `original_method` itself).
        `target_config` is `HXZ_STANDARD_CONFIG` for `ExperimentPlan.
        factorial_switches`/the ①→③ auto-attribution path, or a
        `cz_config_override` for the ①→② auto-attribution path -- this
        function itself is target-agnostic (docs/decision-log.md 2026-08-16:
        generalized from an HXZ-only implementation so the same expansion
        logic serves both comparisons instead of a second copy).

        A single-switch factorial (`len(switches) == 1`) is intentionally
        NOT the same as `ablation_switches`' single-switch flip: this
        function always names its output `{name_prefix}_*` regardless of
        switch count, so a factorial declaration's tracks are never confused
        with an ablation declaration's, even if a caller only lists one switch.

        Track names are built from the switch NAMES that took `target_config`'s
        value in that combo (e.g. `factorial_breakpoint_weighting`), not from
        the raw config values -- a value like `universe_filters` is a list of
        dicts and embedding its repr in a name/file path is unreadable and
        unsafe. If two combos happen to produce the same flipped-switch name
        (e.g. a switch's baseline value already equals its target value, so
        "took the target value" is a no-op for that switch), a running
        `_1`/`_2`/... suffix is appended to every combo sharing that name
        instead of silently dropping the duplicate.

        `exclude_combos` skips specific switch subsets entirely (by the set
        of switch NAMES that combo flips) -- used by `_auto_attribution_specs`
        to drop the all-switches-flipped corner, which is always identical
        to the endpoint track it builds separately (`cz_actual_config`/
        `standardized_hxz`) regardless of how many switches there are, not
        just the `len(switches) == 1` case (docs/step7-8.md Part V, real
        production bug: `attribution.py` correctly refuses two tracks that
        map to the same switch subset rather than silently picking one, so
        the redundant corner must never be generated in the first place).
        A caller building a MANUAL `factorial_switches` list (no separate
        endpoint track involved) must leave this `None`.
        """
        if not switches:
            return []

        pairs = [(s, k) for s in switches if (k := _ABLATION_SWITCH_TO_CONFIG_KEY.get(s)) is not None]
        pairs = [(s, k) for s, k in pairs if k in target_config]
        if not pairs:
            return []
        switch_names = [s for s, _ in pairs]
        keys = [k for _, k in pairs]

        value_options = [(baseline_config[k], target_config[k]) for k in keys]
        baseline_combo = tuple(baseline_config[k] for k in keys)

        combos: list[tuple[str, dict[str, Any]]] = []
        for combo in itertools.product(*value_options):
            if combo == baseline_combo:
                continue
            flipped = [switch_names[i] for i, v in enumerate(combo) if v != baseline_combo[i]]
            if exclude_combos and frozenset(flipped) in exclude_combos:
                continue
            overrides = dict(zip(keys, combo))
            for i, k in enumerate(keys):
                if combo[i] == baseline_combo[i]:
                    continue
                for companion in _CONFIG_KEY_COMPANIONS.get(k, ()):
                    if companion in target_config:
                        overrides[companion] = target_config[companion]
            base_name = "_".join([name_prefix, *flipped])
            combos.append((base_name, overrides))

        name_counts = Counter(base_name for base_name, _ in combos)
        running_index: dict[str, int] = {}
        results: list[tuple[str, dict[str, Any]]] = []
        for base_name, overrides in combos:
            if name_counts[base_name] > 1:
                running_index[base_name] = running_index.get(base_name, 0) + 1
                name = f"{base_name}_{running_index[base_name]}"
            else:
                name = base_name
            results.append((name, overrides))
        return results

    def _auto_attribution_specs(
        self,
        spec: ResolvedMethodSpec,
        baseline_config: dict[str, Any],
        target_config: dict[str, Any],
        factorial_prefix: str,
        ablation_prefix: str,
    ) -> list["ExperimentSpec"]:
        """docs/step6.md §4a's default attribution policy, applied to ONE
        baseline-vs-target comparison: find which known switches actually
        differ (`_diff_switches`), then <=`MAX_FACTORIAL_SWITCHES` gets an
        exact full-factorial expansion (residual always 0), otherwise falls
        back to one-at-a-time (each switch flipped alone, assumes no
        interaction). Returns an empty list when nothing differs (e.g. a
        `cz_config_override` that happens to match the baseline on every
        known switch). The full-factorial expansion always excludes the
        all-switches-flipped corner (`exclude_combos={frozenset(switches)}`):
        that corner is, for ANY n (not just n==1), identical to the endpoint
        track built separately by `_plan_to_matrix`/the declarative yaml path
        (`cz_actual_config`/`standardized_hxz`) -- both would otherwise report
        the exact same `switches_flipped`, which `attribution.py`'s
        `_single_switch_track_map`/`compute_shapley_effects` correctly refuse
        as an ambiguous duplicate subset rather than silently picking one
        (docs/step7-8.md Part V, real production bug). The endpoint track
        alone already covers that corner; `compute_shapley_effects` reads it
        from `tracks` regardless of its track name, not from this list."""
        from src.steps.step6_dual_track_controller.experiment_spec import build_experiment_spec

        switches = _diff_switches(baseline_config, target_config)
        if not switches:
            return []
        if len(switches) <= MAX_FACTORIAL_SWITCHES:
            return [
                build_experiment_spec(name, spec, baseline_config, overrides)
                for name, overrides in self._factorial_track_specs(
                    switches, baseline_config, target_config, name_prefix=factorial_prefix,
                    exclude_combos={frozenset(switches)},
                )
            ]
        return [
            build_experiment_spec(
                f"{ablation_prefix}_{switch}", spec, baseline_config,
                self._get_ablation_override(switch, target_config),
            )
            for switch in switches
        ]

    def run_from_matrix(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        matrix: "ExperimentMatrix",
        snapshot_id: str,
        run_baseline: bool = True,
        reused_baseline_run: RunRecord | None = None,
        progress: Callable[[str], None] | None = None,
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

        An experiment with a `snapshot_ref` (data-vintage tracks) is
        recorded but SKIPPED with a log line -- no adapter exists for
        those; running only the config-override experiments here would
        otherwise silently under-report what the matrix declared.
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
        switches_by_track: dict[str, dict[str, Any]] = {}
        skipped: list[str] = []

        for exp in matrix.experiments:
            if exp.snapshot_ref:
                skipped.append(exp.name)
                continue
            track_overrides[exp.name] = exp.config_overrides
            track_specs.append((exp.name, exp.config_overrides))
            identification_by_track[exp.name] = (exp.family, exp.identification_level)
            switches_by_track[exp.name] = _switches_flipped_from_diff(exp.resolved_diff)

        total_tracks = len(track_specs) + len(reused_runs)
        if progress:
            execution_count = len(track_specs)
            reused_count = len(reused_runs)
            progress(
                f"Experiment plan: {total_tracks} track(s) total "
                f"({execution_count} to execute, {reused_count} reused baseline)."
            )
            for index, run in enumerate(reused_runs, start=1):
                progress(
                    f"Track {index}/{total_tracks} reused: {run.track} "
                    f"(Step 5 execution {run.run_id})."
                )

        runs, effective_plugin, refreeze_attempts = self._run_tracks_with_freeze(
            plugin, spec, snapshot_id, track_specs,
            progress=progress,
            total_tracks=total_tracks,
            completed_before_execution=len(reused_runs),
        )
        runs.extend(reused_runs)
        for run in runs:
            if run.track in identification_by_track:
                family, identification_level = identification_by_track[run.track]
                run.logs = list(run.logs) + [
                    f"experiment_matrix: family={family!r} "
                    f"identification_level={identification_level!r}"
                ]
            if switches_by_track.get(run.track):
                run.switches_flipped = switches_by_track[run.track]

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
        """
        frozen_plugin_hash = plugin.code_hash

        divergent_tracks = sorted(
            r.track for r in runs
            if r.status == "success" and r.code_hash != frozen_plugin_hash
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
                "switches_flipped": r.switches_flipped,
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
        progress: Callable[[str], None] | None = None,
        total_tracks: int | None = None,
        completed_before_execution: int = 0,
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
            for offset, (track_name, overrides) in enumerate(track_specs, start=1):
                track_index = completed_before_execution + offset
                if progress:
                    progress(f"Track {track_index}/{total_tracks or len(track_specs)} started: {track_name}.")
                record, _used_plugin = self._run_track(plugin, spec, snapshot_id, track_name, overrides)
                runs.append(record)
                if progress:
                    progress(self._track_completed_message(track_index, total_tracks or len(track_specs), record))
            return runs, plugin, 0

        current_plugin = plugin
        attempt = 0
        while True:
            runs: list[RunRecord] = []
            used_plugins: dict[str, PluginRecord] = {}
            loop = self.repair_loop if attempt == 0 else self._frozen_repair_loop
            for offset, (track_name, overrides) in enumerate(track_specs, start=1):
                track_index = completed_before_execution + offset
                track_total = total_tracks or (completed_before_execution + len(track_specs))
                if progress:
                    prefix = "Re-freeze pass: " if attempt else ""
                    progress(f"{prefix}Track {track_index}/{track_total} started: {track_name}.")
                record, used_plugin = self._run_track(
                    current_plugin, spec, snapshot_id, track_name, overrides, repair_loop=loop
                )
                runs.append(record)
                used_plugins[track_name] = used_plugin
                if progress:
                    progress(self._track_completed_message(track_index, track_total, record, refreeze=bool(attempt)))

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
            if progress:
                progress(
                    "A technical repair changed the plugin code; re-running every executable "
                    "track once with the repaired code to keep the batch comparable."
                )

    @staticmethod
    def _track_completed_message(
        track_index: int,
        total_tracks: int,
        record: RunRecord,
        refreeze: bool = False,
    ) -> str:
        """Human-readable, SSE-safe completion line for one Step 6 track."""
        prefix = "Re-freeze pass: " if refreeze else ""
        details = [f"status={record.status}"]
        if record.metrics.mean_return is not None:
            details.append(f"mean_monthly_return={record.metrics.mean_return:.3%}")
        if record.metrics.t_stat is not None:
            details.append(f"t_stat={record.metrics.t_stat:.2f}")
        return f"{prefix}Track {track_index}/{total_tracks} completed: {record.track} ({', '.join(details)})."

    def _get_ablation_override(self, switch: str, target_config: dict[str, Any]) -> dict[str, Any]:
        """Get a single-switch config override: flip just this one setting
        from the baseline to `target_config`'s value (`HXZ_STANDARD_CONFIG`
        for the ①→③ path, a `cz_config_override` for the ①→② path --
        generalized 2026-08-16, was HXZ-only). Also carries along any
        `_CONFIG_KEY_COMPANIONS` for that key (e.g. `universe_filters` ->
        `universe_filter_join_sources`) so the override is self-consistent."""
        key = _ABLATION_SWITCH_TO_CONFIG_KEY.get(switch)
        if not key or key not in target_config:
            return {}
        override = {key: target_config[key]}
        for companion in _CONFIG_KEY_COMPANIONS.get(key, ()):
            if companion in target_config:
                override[companion] = target_config[companion]
        return override
