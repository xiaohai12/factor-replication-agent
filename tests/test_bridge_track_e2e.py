"""Phase D: `DualTrackController._run_bridge_track` off the paper-first
`ResolvedMethodSpec` schema, mirrors tests/test_bridge_track_e2e.py (which
covers the v1 path) -- proves the C&Z bridge track executes via real
subprocess for a ResolvedMethodSpec too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infra.data_layer import SnapshotMetadata
from src.infra.models.plugin import PluginRecord
from src.pipeline import Pipeline
from tests._spec_test_helpers import asset_growth_resolved_spec
from tests.synthetic_data.asset_growth_synthetic_data import (
    build_ccm_link,
    build_compustat_funda,
    build_crsp_msf,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"
SNAPSHOT_ID = "bridge_e2e_resolved_v1"
FACTOR_ID = "cooper_gulen_schill_2008_asset_growth"


@pytest.fixture()
def pipeline_with_bridge_data(tmp_path) -> Pipeline:
    data_path = tmp_path / "data"
    local_dir = data_path / "local"
    local_dir.mkdir(parents=True)

    crsp = build_crsp_msf()
    crsp.to_parquet(local_dir / "msf.parquet", index=False)

    pipe = Pipeline(
        data_path=str(data_path),
        evidence_path=str(tmp_path / "evidence"),
        scripts_path=str(tmp_path / "backtest_scripts"),
    )

    snapshot_dir = data_path / "snapshots" / SNAPSHOT_ID
    snapshot_dir.mkdir(parents=True)
    crsp.to_parquet(snapshot_dir / "crsp_msf.parquet", index=False)
    build_compustat_funda().to_parquet(snapshot_dir / "comp_funda.parquet", index=False)
    build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
        snapshot_dir / "ccm_lnkhist.parquet", index=False
    )

    pipe.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=SNAPSHOT_ID,
            pull_date="2026-01-01",
            crsp_end_date="2000-06-30",
            compustat_end_date="1998-12-31",
            storage_path=str(snapshot_dir),
        )
    )
    return pipe


def test_asset_growth_bridge_track_executes_via_real_subprocess(pipeline_with_bridge_data):
    spec = asset_growth_resolved_spec()
    plugin = PluginRecord(
        plugin_id=f"{FACTOR_ID}_resolved", factor_id=FACTOR_ID,
        code=PLUGIN_PATH.read_text(encoding="utf-8"), code_hash="synthetic",
    )

    record = pipeline_with_bridge_data.controller._run_bridge_track(
        plugin, spec, SNAPSHOT_ID, "bridge_cz_signal", FACTOR_ID,
    )

    assert record is not None
    assert record.is_bridge_track is True
    assert record.code_hash == f"cz_bridge:{FACTOR_ID}"
    assert record.status == "success", record.logs
    assert record.metrics.n_months is not None
    assert record.signal_series_path
    assert Path(record.signal_series_path).exists()
