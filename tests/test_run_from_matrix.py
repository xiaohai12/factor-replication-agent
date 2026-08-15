"""Tests for `MultiTrackController.run_from_matrix` (Phase A2,
docs/multi-config-evidence-plan.md): executing a loaded/validated
`experiment_spec.ExperimentMatrix` as tracks, alongside the implicit
`original_method` baseline. Reuses the FakeRunner/FakeMetaCoder/FakeSandbox
pattern from tests/test_dual_track_controller.py.
"""

from __future__ import annotations

from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import MultiTrackController
from src.steps.step6_dual_track_controller.experiment_spec import load_experiment_matrix
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
        self.build_calls.append({"track_name": track_name, "config_overrides": dict(config_overrides or {})})
        return {"config": dict(config_overrides or {}), "config_overrides": config_overrides, "script_text": plugin.code}

    def execute(self, built: dict) -> dict:
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result) -> RunRecord:
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}",
            factor_id=spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            code_hash=plugin.code_hash,
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
    def __init__(self):
        self.llm_client = object()


class FakeSandbox:
    def validate(self, plugin, spec, script_text=None, data=None):
        return ValidationReport(passed=True)


def _write_matrix(tmp_path, text: str):
    p = tmp_path / "t.experiments.yaml"
    p.write_text(text)
    return p


class TestRunFromMatrix:
    def test_baseline_plus_each_experiment_becomes_a_track(self, tmp_path):
        path = _write_matrix(
            tmp_path,
            """
factor_id: t
experiments:
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
  - name: ablation_breakpoint_full_sample
    config_overrides: {breakpoint_source: full_sample}
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        tracks = [r.track for r in runs]
        assert tracks == ["original_method", "ablation_weighting_ew", "ablation_breakpoint_full_sample"]
        assert all(r.status == "success" for r in runs)
        assert all(r.experiment_batch_id for r in runs)
        assert all(r.experiment_batch_id == runs[0].experiment_batch_id for r in runs)

    def test_experiment_spec_hash_embedded_in_comparison_batch_info(self, tmp_path):
        path = _write_matrix(
            tmp_path,
            """
factor_id: t
experiments:
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["experiment_spec_hash"] == matrix.experiment_spec_hash

    def test_family_and_identification_level_logged_on_each_run(self, tmp_path):
        path = _write_matrix(
            tmp_path,
            """
factor_id: t
experiments:
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        exp_run = next(r for r in runs if r.track == "ablation_weighting_ew")
        assert any("family='portfolio_ablation'" in log for log in exp_run.logs)
        assert any("identification_level='controlled'" in log for log in exp_run.logs)

    def test_bridge_and_vintage_experiments_are_skipped_not_run(self, tmp_path):
        path = _write_matrix(
            tmp_path,
            """
factor_id: t
experiments:
  - name: bridge_cz_signal
    signal_input_ref: "cz:Test"
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        tracks = [r.track for r in runs]
        assert "bridge_cz_signal" not in tracks
        assert "ablation_weighting_ew" in tracks

        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["skipped_experiments"] == ["bridge_cz_signal"]
