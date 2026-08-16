"""Tests for reusing an already-persisted `original_method` RunRecord (e.g.
step5's own execution) for track \u2460 instead of re-running it
(`MultiTrackController.run_experiment(..., reuse_original_run=...)`). No
matching/validation against the current plugin/spec/snapshot -- the caller
is trusted to only pass a genuinely equivalent run.
"""

from __future__ import annotations

from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import ExperimentPlan, MultiTrackController
from tests._spec_test_helpers import minimal_resolved_spec, spec_factor_id


def _spec():
    return minimal_resolved_spec("t")


def _plugin() -> PluginRecord:
    return PluginRecord(plugin_id="t_v1", factor_id="t", code="def compute_signal(df): return df", code_hash="deadbeef")


class FakeRunner:
    def __init__(self):
        self.build_calls: list[dict] = []
        self.comparison_calls: list[dict] = []
        self.comparison_path = None

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None) -> dict:
        self.build_calls.append({"config_overrides": dict(config_overrides or {}), "track_name": track_name})
        return {"config": dict(config_overrides or {}), "config_overrides": config_overrides, "script_text": plugin.code}

    def execute(self, built: dict) -> dict:
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result) -> RunRecord:
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}", factor_id=spec_factor_id(spec), plugin_id=plugin.plugin_id,
            track=track, code_hash=plugin.code_hash,
            metrics=RunMetrics(mean_return=metrics.get("mean_monthly_return"), t_stat=metrics.get("t_stat")),
            status="success",
        )

    def make_failed_run_record(self, spec, plugin, track, config_overrides, log) -> RunRecord:
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}_failed", factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id, track=track, metrics=RunMetrics(), status="failed", logs=[log],
        )

    def write_comparison_summary(self, spec, tracks, snapshot_id=None, diff_result=None, batch_info=None):
        self.comparison_calls.append({"tracks": tracks, "batch_info": batch_info})
        return self.comparison_path


class FakeMetaCoder:
    llm_client = object()


class FakeSandbox:
    def validate(self, plugin, spec, script_text=None, data=None):
        return ValidationReport(passed=True)


def _prior_run(spec, plugin) -> RunRecord:
    return RunRecord(
        run_id="prior_step5_run", factor_id=spec_factor_id(spec), plugin_id=plugin.plugin_id,
        track="original_method", code_hash=plugin.code_hash,
        metrics=RunMetrics(mean_return=0.02, t_stat=3.0), status="success",
    )


class TestBaselineReuse:
    def test_reused_run_is_included_without_rerunning(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        spec, plugin = _spec(), _plugin()
        prior = _prior_run(spec, plugin)
        plan = ExperimentPlan(factor_id="t", run_standardized=False)

        runs = controller.run_experiment(plugin, spec, plan, snapshot_id="snap1", reuse_original_run=prior)

        assert len(runs) == 1
        reused = runs[0]
        assert reused.track == "original_method"
        assert reused.run_id != prior.run_id  # new identity, never overwrites the original artifact
        assert reused.metrics.mean_return == 0.02
        assert any("reused run" in log for log in reused.logs)
        # \u2460 was never actually executed -- no build_script call for it.
        assert all(c["track_name"] != "original_method" for c in runner.build_calls)

    def test_no_reuse_supplied_runs_fresh_as_before(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_standardized=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert runs[0].run_id == "t_original_method"
        assert not any("reused run" in log for log in runs[0].logs)

