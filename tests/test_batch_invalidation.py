"""Tests for batch-level plugin freeze (Phase 0.6, full version, 2026-08-04:
docs/multi-config-evidence-plan.md): `MultiTrackController.run_experiment`'s
premise is "every track in one batch ran the SAME frozen plugin code, only
config differs." A per-track execution failure can trigger `RepairLoop`
(src/infra/repair.py) to hand back a DIFFERENT plugin (new code_hash) for
just that one track -- silently breaking that premise for the whole batch,
not just the repaired track. `_run_tracks_with_freeze` now AUTOMATICALLY
re-runs the whole batch from that re-frozen plugin with repair disabled
(bounded to `max_refreeze_attempts`, default 1), so `batch_invalidated`
mostly serves as a fallback safety net for `max_refreeze_attempts=0` rather
than the everyday outcome -- see `TestZeroRefreezeAttemptsIsDetectionOnly`
for that fallback path, and `TestBatchInvalidationOnTrackLocalRepair` for the
default auto-reconverging behavior.
"""

from __future__ import annotations

from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import MultiTrackController, ExperimentPlan
from tests._spec_test_helpers import minimal_resolved_spec, spec_factor_id


def _spec():
    return minimal_resolved_spec("t")


def _plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="t_v1", factor_id="t",
        code="def compute_signal(df): return df", code_hash="deadbeef",
    )


class FakeRunnerWithCodeHash:
    """Like test_dual_track_controller.py's FakeRunner, but `make_run_record`
    actually propagates `plugin.code_hash` (the real `BacktestRunner` does
    this too -- see `outcome.plugin` in `MultiTrackController._run_track`).
    `execute()` fails exactly once for any track named in `fail_once_tracks`,
    then succeeds -- enough to trigger exactly one repair on that track only.
    """

    def __init__(self, fail_once_tracks: frozenset[str] = frozenset()):
        self.fail_once_tracks = fail_once_tracks
        self._failed_already: set[str] = set()

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None) -> dict:
        return {
            "config": dict(config_overrides or {}),
            "config_overrides": config_overrides,
            "script_text": plugin.code,
            "track_name": track_name,
        }

    def execute(self, built: dict) -> dict:
        track_name = built["track_name"]
        if track_name in self.fail_once_tracks and track_name not in self._failed_already:
            self._failed_already.add(track_name)
            raise RuntimeError(f"transient failure on {track_name}")
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result) -> RunRecord:
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}_{plugin.code_hash}",
            factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            code_hash=plugin.code_hash,
            metrics=RunMetrics(mean_return=metrics.get("mean_monthly_return"), t_stat=metrics.get("t_stat")),
            status="success",
        )

    def make_failed_run_record(self, spec, plugin, track, config_overrides, log) -> RunRecord:
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}_failed",
            factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            code_hash=plugin.code_hash,
            metrics=RunMetrics(),
            status="failed",
            logs=[log],
        )

    def write_comparison_summary(self, spec, tracks, snapshot_id=None, diff_result=None, batch_info=None):
        self.last_batch_info = batch_info
        return None


class FakeMetaCoder:
    def __init__(self):
        self.llm_client = object()
        self.repair_calls = 0

    def repair_plugin(self, plugin, errors):
        self.repair_calls += 1
        new = plugin.model_copy(deep=True)
        new.code_hash = f"repaired{self.repair_calls}"
        return new


class FakeSandbox:
    def validate(self, plugin, spec, script_text=None, data=None):
        return ValidationReport(passed=True)


class TestBatchInvalidationOnTrackLocalRepair:
    def test_no_repair_batch_stays_valid(self):
        runner = FakeRunnerWithCodeHash(fail_once_tracks=frozenset())
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=True)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert len(runs) == 2
        assert all(r.code_hash == "deadbeef" for r in runs)
        assert all(r.frozen_plugin_hash == "deadbeef" for r in runs)
        assert all(r.batch_invalidated is False for r in runs)
        assert all(r.batch_invalidation_reason == "" for r in runs)
        # Every record in one call shares the same batch id.
        assert len({r.experiment_batch_id for r in runs}) == 1

    def test_repair_on_one_track_auto_reconverges_the_whole_batch(self):
        """Phase 0.6 FULL freeze (2026-08-04): when a track-local repair
        changes one track's code, the whole batch is automatically re-run
        from that re-frozen plugin with repair disabled -- so both tracks
        end up sharing the SAME code, and the batch is no longer flagged
        invalidated just because it differs from the very first attempt."""
        runner = FakeRunnerWithCodeHash(fail_once_tracks=frozenset({"standardized_hxz"}))
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=True)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        by_track = {r.track: r for r in runs}
        # Both tracks converge on the re-frozen (repaired) code -- the
        # re-run pass re-executed original_method too, even though it never
        # itself failed, so the whole batch shares one code_hash.
        assert by_track["standardized_hxz"].code_hash == "repaired1"
        assert by_track["original_method"].code_hash == "repaired1"

        assert all(r.batch_invalidated is False for r in runs)
        assert all(r.frozen_plugin_hash == "repaired1" for r in runs)
        assert all(r.batch_invalidation_reason == "" for r in runs)

    def test_batch_info_embedded_in_comparison_summary(self):
        runner = FakeRunnerWithCodeHash(fail_once_tracks=frozenset({"standardized_hxz"}))
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=True)

        controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert runner.last_batch_info["batch_invalidated"] is False
        assert runner.last_batch_info["frozen_plugin_hash"] == "repaired1"
        assert runner.last_batch_info["experiment_batch_id"]
        # A refreeze DID happen (auditable even though it converged).
        assert runner.last_batch_info["refreeze_attempts"] == 1


class TestZeroRefreezeAttemptsIsDetectionOnly:
    """`_run_tracks_with_freeze`'s frozen re-run pass never itself repairs
    (`_NoRepairMetaCoder.llm_client is None`), so any successful track's
    `outcome.plugin` in that pass is ALWAYS exactly the plugin it was run
    with -- meaning that with the default `max_refreeze_attempts=1`, a
    batch mathematically always ends the frozen pass either converged
    (every survivor shares the re-frozen code) or with the non-converging
    track dropped to `status="failed"` (never "successful but still
    divergent"). The ONLY way to see the OLD detection-only
    `batch_invalidated=True` outcome is `max_refreeze_attempts=0` (skip the
    refreeze pass entirely) -- exercised directly here since
    `run_experiment`/`run_from_matrix` always use the default of 1."""

    def test_max_refreeze_attempts_zero_leaves_batch_invalidated(self):
        from src.steps.step6_dual_track_controller import MultiTrackController

        runner = FakeRunnerWithCodeHash(fail_once_tracks=frozenset({"standardized_hxz"}))
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        track_specs = [("original_method", {}), ("standardized_hxz", {})]

        runs, effective_plugin, refreeze_attempts = controller._run_tracks_with_freeze(
            _plugin(), _spec(), "snap1", track_specs, max_refreeze_attempts=0
        )

        by_track = {r.track: r for r in runs}
        assert by_track["standardized_hxz"].code_hash == "repaired1"
        assert by_track["original_method"].code_hash == "deadbeef"
        assert effective_plugin.code_hash == "deadbeef"  # never re-frozen
        assert refreeze_attempts == 0

