"""Phase D: `BacktestRunner.build_script`/`execute`'s data-path override
mechanism, same golden numbers as tests/test_execute_data_path_override.py
but off the paper-first `ResolvedMethodSpec` schema (asset_growth_resolved_spec)
instead of the v1 fixture -- neither `build_script` nor `execute` touch
`Pipeline.run_full_pipeline`/`run_from_method_spec` at all, so this only
needed a spec swap.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.infra.data_layer import SnapshotMetadata
from src.infra.models.plugin import PluginRecord
from src.pipeline import Pipeline
from tests._spec_test_helpers import asset_growth_resolved_spec
from tests.synthetic_data.asset_growth_synthetic_data import (
    build_ccm_link,
    build_compustat_funda,
    build_crsp_msf,
    expected_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"


def _register_snapshot(pipe: Pipeline, snapshot_id: str, snapshot_dir: Path, funda: pd.DataFrame) -> None:
    snapshot_dir.mkdir(parents=True)
    build_crsp_msf().to_parquet(snapshot_dir / "crsp_msf.parquet", index=False)
    funda.to_parquet(snapshot_dir / "comp_funda.parquet", index=False)
    build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
        snapshot_dir / "ccm_lnkhist.parquet", index=False
    )
    pipe.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=snapshot_id,
            pull_date="2026-01-01",
            crsp_end_date="2026-01-01",
            compustat_end_date="2026-01-01",
            storage_path=str(snapshot_dir),
        )
    )


@pytest.fixture()
def pipe(tmp_path) -> Pipeline:
    data_path = tmp_path / "data"
    (data_path / "local").mkdir(parents=True)
    return Pipeline(
        data_path=str(data_path),
        evidence_path=str(tmp_path / "evidence"),
        scripts_path=str(tmp_path / "backtest_scripts"),
    )


@pytest.fixture()
def spec():
    return asset_growth_resolved_spec()


@pytest.fixture()
def plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="cooper_gulen_schill_2008_asset_growth_resolved",
        factor_id="cooper_gulen_schill_2008_asset_growth",
        code=PLUGIN_PATH.read_text(encoding="utf-8"),
        code_hash="test",
    )


def test_execute_override_reads_a_genuinely_different_data_source(tmp_path, pipe, spec, plugin):
    golden_funda = build_compustat_funda()
    perturbed_funda = golden_funda.copy()
    perturbed_funda["at"] = perturbed_funda["at"] + pd.Series(range(len(perturbed_funda))) * 7.0

    _register_snapshot(pipe, "snap_a", tmp_path / "data" / "snapshots" / "snap_a", golden_funda)
    _register_snapshot(pipe, "snap_b", tmp_path / "data" / "snapshots" / "snap_b", perturbed_funda)

    built = pipe.runner.build_script(plugin, spec, "snap_a", None)

    result_a = pipe.runner.execute(built)
    golden = expected_metrics()
    assert result_a["metrics"]["n_months"] == golden["n_months"]
    assert result_a["metrics"]["mean_monthly_return"] == pytest.approx(golden["mean_monthly_return"], rel=1e-9)
    signal_a = pd.read_parquet(result_a["signal_path"]).sort_values(["permno", "yyyymm"]).reset_index(drop=True)

    snap_b_dir = tmp_path / "data" / "snapshots" / "snap_b"
    result_b = pipe.runner.execute(
        built,
        data_path_override=str(snap_b_dir / "crsp_msf.parquet"),
        signal_data_dir_override=str(snap_b_dir),
    )

    signal_b = pd.read_parquet(result_b["signal_path"]).sort_values(["permno", "yyyymm"]).reset_index(drop=True)
    assert not signal_a["signal"].equals(signal_b["signal"])
