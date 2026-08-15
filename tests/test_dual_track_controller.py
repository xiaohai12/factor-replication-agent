"""Unit tests for the current basic multi-track/OAT controller.

It delegates Step 5 (build+execute) to `BacktestRunner` and, on an execution failure, loops back to Step 3
(`MetaCoder.repair_plugin`) with a quick Step 4 re-validate, bounded by
`MAX_REPAIR_RETRIES` — mirroring `Pipeline.run_from_method_spec`'s
run-with-repair loop, applied per track.

Uses fake `runner`/`meta_coder`/`sandbox` collaborators (no real subprocess,
no real data, no LLM) so these tests exercise pure control flow:
- happy path: one track, build+execute succeeds first try.
- multi-track: original + standardized + one ablation -> 3 tracks, 3 configs.
- repair-then-succeed: execute() raises once, repair_plugin() is called,
  re-validate happens, second execute() succeeds.
- repair-exhausted: execute() always raises -> a status="failed" RunRecord
  comes back instead of an unhandled exception.
"""

from __future__ import annotations

import pytest

from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import MultiTrackController, ExperimentPlan
from tests._spec_test_helpers import minimal_resolved_spec, spec_factor_id


def _spec():
    return minimal_resolved_spec("t")


def _plugin() -> PluginRecord:
    return PluginRecord(plugin_id="t_v1", factor_id="t", code="def compute_signal(df): return df", code_hash="deadbeef")


class FakeRunner:
    """Records every build_script/execute call; `execute` raises for the
    first `fail_times` calls per track, then succeeds."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.build_calls: list[dict] = []
        self.execute_calls = 0
        self._attempts_by_track: dict[str, int] = {}
        self.comparison_calls: list[dict] = []
        self.comparison_path = None

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None) -> dict:
        self.build_calls.append({"snapshot_id": snapshot_id, "config_overrides": dict(config_overrides or {}), "track_name": track_name})
        return {"config": dict(config_overrides or {}), "config_overrides": config_overrides, "script_text": plugin.code}

    def execute(self, built: dict) -> dict:
        self.execute_calls += 1
        track_key = str(built["config_overrides"])
        attempts = self._attempts_by_track.get(track_key, 0) + 1
        self._attempts_by_track[track_key] = attempts
        if attempts <= self.fail_times:
            raise RuntimeError(f"attempt {attempts} failed")
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result) -> RunRecord:
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}",
            factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            metrics=RunMetrics(mean_return=metrics.get("mean_monthly_return"), t_stat=metrics.get("t_stat")),
            status="success",
        )

    def make_failed_run_record(self, spec, plugin, track, config_overrides, log) -> RunRecord:
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}_failed",
            factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            metrics=RunMetrics(),
            status="failed",
            logs=[log],
        )

    def write_comparison_summary(self, spec, tracks, snapshot_id=None, diff_result=None, batch_info=None):
        self.comparison_calls.append(
            {
                "factor_id": spec_factor_id(spec),
                "tracks": tracks,
                "snapshot_id": snapshot_id,
                "diff_result": diff_result,
                "batch_info": batch_info,
            }
        )
        return self.comparison_path


class FakeMetaCoder:
    def __init__(self):
        self.llm_client = object()  # truthy: repair is "available"
        self.repair_calls = 0

    def repair_plugin(self, plugin, errors):
        self.repair_calls += 1
        new = plugin.model_copy(deep=True)
        new.code_hash = f"repaired{self.repair_calls}"
        return new


class FakeSandbox:
    def __init__(self, passes: bool = True):
        self.passes = passes
        self.validate_calls = 0

    def validate(self, plugin, spec, script_text=None, data=None):
        self.validate_calls += 1
        return ValidationReport(passed=self.passes)


class TestRunExperiment:
    def test_single_track_happy_path(self):
        runner = FakeRunner(fail_times=0)
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert len(runs) == 1
        assert runs[0].track == "original_method"
        assert runs[0].status == "success"
        assert runner.build_calls[0]["snapshot_id"] == "snap1"

    def test_multi_track_produces_one_run_per_track(self):
        runner = FakeRunner(fail_times=0)
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=True, run_standardized=True, ablation_switches=["weighting"]
        )

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        tracks = [r.track for r in runs]
        assert tracks == ["original_method", "standardized_hxz", "ablation_weighting"]
        assert all(r.status == "success" for r in runs)
        # 3 distinct config_overrides were used to build 3 distinct scripts
        assert len(runner.build_calls) == 3
        # Each track's build_script call carries its own track_name (used to
        # disambiguate the on-disk script/output filenames -- see
        # BacktestRunner.build_script's file_stem) matching the track it
        # belongs to, not a shared/blank name that would collide on disk.
        assert [c["track_name"] for c in runner.build_calls] == tracks
        # run_experiment writes one aggregate comparison.json (via
        # BacktestRunner.write_comparison_summary) covering every successful
        # track after all tracks finish -- each entry includes both the
        # resolved config actually used AND the metrics, so the file is
        # self-contained enough to hand to an LLM without the config.
        assert len(runner.comparison_calls) == 1
        summary_tracks = runner.comparison_calls[0]["tracks"]
        assert set(summary_tracks) == set(tracks)
        assert all({"config", "metrics"} <= set(v) for v in summary_tracks.values())


class TestRepairLoop:
    def test_execute_failure_repairs_then_succeeds(self):
        runner = FakeRunner(fail_times=1)  # fails once, then succeeds
        meta_coder = FakeMetaCoder()
        sandbox = FakeSandbox(passes=True)
        controller = MultiTrackController(runner=runner, meta_coder=meta_coder, sandbox=sandbox)
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert runs[0].status == "success"
        assert meta_coder.repair_calls == 1
        assert sandbox.validate_calls == 1
        assert runner.execute_calls == 2  # first fails, second succeeds

    def test_execute_failure_exhausts_repair_returns_failed_run_record(self):
        runner = FakeRunner(fail_times=999)  # always fails
        meta_coder = FakeMetaCoder()
        controller = MultiTrackController(runner=runner, meta_coder=meta_coder, sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=True, run_standardized=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert runs[0].status == "failed"
        assert runs[0].logs  # captured the last run_error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
