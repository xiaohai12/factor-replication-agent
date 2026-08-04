"""Tests for `DualTrackController._run_bridge_track`/`run_from_matrix`'s
`signal_input_ref: "cz_bridge"` handling (Phase C/D, docs/multi-config-
evidence-plan.md): running a real C&Z bridge signal as an executable track,
under the same resolved config as every other track.
"""

from __future__ import annotations

from src.infra.models.method_spec import MethodSpec, SignalSpec
from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import DualTrackController
from src.steps.step6_dual_track_controller.experiment_spec import load_experiment_matrix


def _spec(factor_id: str = "cooper_gulen_schill_2008_asset_growth") -> MethodSpec:
    return MethodSpec(factor_id=factor_id, factor_name="Test", signal=SignalSpec())


def _plugin() -> PluginRecord:
    return PluginRecord(plugin_id="t_v1", factor_id="cooper_gulen_schill_2008_asset_growth",
                         code="def compute_signal(df): return df", code_hash="deadbeef")


class FakeSnapshot:
    storage_path = "/fake/storage/path"


class FakeSnapshots:
    def get_snapshot(self, snapshot_id):
        return FakeSnapshot()


class FakeDataLayer:
    snapshots = FakeSnapshots()


class FakeRunner:
    """Records build_script calls (including precomputed_signal_path) and
    always succeeds on execute()."""

    def __init__(self):
        self.data_layer = FakeDataLayer()
        self.scripts_path = None  # set per-test via tmp_path
        self.build_calls: list[dict] = []
        self.comparison_calls: list[dict] = []
        self.comparison_path = None

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None, precomputed_signal_path=None):
        self.build_calls.append({
            "track_name": track_name,
            "precomputed_signal_path": precomputed_signal_path,
        })
        return {"config": dict(config_overrides or {}), "script_text": plugin.code}

    def execute(self, built):
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result):
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec.factor_id}_{track}", factor_id=spec.factor_id,
            plugin_id=plugin.plugin_id, track=track, code_hash=plugin.code_hash,
            metrics=RunMetrics(mean_return=metrics.get("mean_monthly_return"), t_stat=metrics.get("t_stat")),
            status="success",
        )

    def make_failed_run_record(self, spec, plugin, track, config_overrides, log):
        return RunRecord(
            run_id=f"{spec.factor_id}_{track}_failed", factor_id=spec.factor_id,
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


class TestRunBridgeTrack:
    def test_registered_factor_produces_a_bridge_run(self, tmp_path, monkeypatch):
        import pandas as pd

        def fake_compute(factor_id, data_dir):
            assert factor_id == "cooper_gulen_schill_2008_asset_growth"
            return pd.DataFrame({"permno": [1], "yyyymm": [200001], "signal": [0.05]})

        monkeypatch.setattr(
            "src.infra.reference.cz_bridge.compute_cz_bridge_signal", fake_compute
        )

        runner = FakeRunner()
        runner.scripts_path = tmp_path
        controller = DualTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        record = controller._run_bridge_track(
            _plugin(), _spec(), "snap1", "bridge_cz_signal",
            "cooper_gulen_schill_2008_asset_growth",
        )

        assert record is not None
        assert record.status == "success"
        assert record.is_bridge_track is True
        assert record.code_hash == "cz_bridge:cooper_gulen_schill_2008_asset_growth"
        assert runner.build_calls[0]["precomputed_signal_path"] is not None
        # The bridge signal was actually persisted to disk for the script to load.
        assert (tmp_path / "results" / "cooper_gulen_schill_2008_asset_growth"
                / "bridge_cz_signal.cz_bridge_input.parquet").exists()

    def test_unregistered_factor_returns_none(self, tmp_path):
        runner = FakeRunner()
        runner.scripts_path = tmp_path
        controller = DualTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        record = controller._run_bridge_track(
            _plugin(), _spec("no_such_factor"), "snap1", "bridge_cz_signal", "no_such_factor",
        )
        assert record is None


class TestRunFromMatrixWithCzBridgeExperiment:
    def _write_matrix(self, tmp_path, text: str):
        p = tmp_path / "t.experiments.yaml"
        p.write_text(text)
        return p

    def test_cz_bridge_experiment_runs_as_a_real_track(self, tmp_path, monkeypatch):
        import pandas as pd

        monkeypatch.setattr(
            "src.infra.reference.cz_bridge.compute_cz_bridge_signal",
            lambda factor_id, data_dir: pd.DataFrame(
                {"permno": [1], "yyyymm": [200001], "signal": [0.05]}
            ),
        )

        path = self._write_matrix(
            tmp_path,
            """
factor_id: cooper_gulen_schill_2008_asset_growth
experiments:
  - name: bridge_cz_signal
    signal_input_ref: cz_bridge
""",
        )
        matrix = load_experiment_matrix(path, _spec())

        runner = FakeRunner()
        runner.scripts_path = tmp_path / "scripts"
        controller = DualTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        tracks = {r.track: r for r in runs}
        assert "bridge_cz_signal" in tracks
        assert tracks["bridge_cz_signal"].is_bridge_track is True
        assert tracks["bridge_cz_signal"].status == "success"
        # A bridge track's own code_hash never matches the frozen plugin --
        # it must NOT invalidate the batch.
        assert all(r.batch_invalidated is False for r in runs)

        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["skipped_experiments"] == []

    def test_unregistered_cz_bridge_factor_is_skipped_not_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.infra.reference.cz_bridge.compute_cz_bridge_signal",
            lambda factor_id, data_dir: None,
        )
        path = self._write_matrix(
            tmp_path,
            """
factor_id: cooper_gulen_schill_2008_asset_growth
experiments:
  - name: bridge_cz_signal
    signal_input_ref: cz_bridge
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        runner.scripts_path = tmp_path / "scripts"
        controller = DualTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        tracks = [r.track for r in runs]
        assert "bridge_cz_signal" not in tracks
        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["skipped_experiments"] == ["bridge_cz_signal"]

    def test_unrecognized_signal_input_ref_is_skipped(self, tmp_path):
        path = self._write_matrix(
            tmp_path,
            """
factor_id: cooper_gulen_schill_2008_asset_growth
experiments:
  - name: some_other_bridge
    signal_input_ref: "some_other_adapter:XYZ"
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        runner = FakeRunner()
        runner.scripts_path = tmp_path / "scripts"
        controller = DualTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())

        runs = controller.run_from_matrix(_plugin(), _spec(), matrix, snapshot_id="snap1")

        tracks = [r.track for r in runs]
        assert "some_other_bridge" not in tracks
        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["skipped_experiments"] == ["some_other_bridge"]
