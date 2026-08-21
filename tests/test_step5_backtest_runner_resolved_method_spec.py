"""Phase D test: `BacktestRunner.build_script`/`write_comparison_summary`/
`make_run_record`/`make_failed_run_record`'s `ResolvedMethodSpec` dispatch.
Not yet used by `src.pipeline`/`MultiTrackController` (see
docs/methodspec-v2-plan.md section 9, Phase D).
"""

from __future__ import annotations

from src.infra.data_layer import DataLayer, SnapshotMetadata
from src.infra.models.plugin import PluginRecord
from src.steps.step5_backtest_runner import BacktestRunner
from tests.test_meta_coder_resolved_method_spec import _resolved_spec

SNAPSHOT_ID = "test_snapshot"


def _runner(tmp_path) -> BacktestRunner:
    data_layer = DataLayer(data_path=str(tmp_path / "data"))
    snapshot_dir = tmp_path / "data" / "snapshots" / SNAPSHOT_ID
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "crsp_msf.parquet").write_bytes(b"")
    data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=SNAPSHOT_ID, pull_date="2026-01-01",
            crsp_end_date="2000-06-30", compustat_end_date="1998-12-31",
            storage_path=str(snapshot_dir),
        )
    )
    return BacktestRunner(data_layer=data_layer, scripts_path=str(tmp_path / "scripts"))


def _plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="asset_growth", factor_id="asset_growth",
        code="def compute_signal(df):\n    return df\n", code_hash="abc123",
    )


class TestBuildScriptResolved:
    def test_build_script_uses_paper_factor_id(self, tmp_path):
        resolved = _resolved_spec()
        runner = _runner(tmp_path)
        built = runner.build_script(_plugin(), resolved, SNAPSHOT_ID, None)
        assert resolved.paper.factor_id in str(built["script_path"])
        assert "config" in built

    def test_write_comparison_summary_flattens_reported_results(self, tmp_path):
        resolved = _resolved_spec()
        runner = _runner(tmp_path)
        path = runner.write_comparison_summary(resolved, tracks={})
        payload = path.read_text()
        assert resolved.paper.factor_id in payload
        assert '"main_spread": 0.0045' in payload

    def test_make_run_record_uses_paper_factor_id(self, tmp_path):
        resolved = _resolved_spec()
        runner = _runner(tmp_path)
        record = runner.make_run_record(
            resolved, _plugin(), "original_method",
            {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0, "n_months": 12}, "config": {}},
        )
        assert record.factor_id == resolved.paper.factor_id
