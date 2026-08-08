"""Phase D: `Pipeline.run_from_method_spec`'s `ResolvedMethodSpec` dispatch,
same golden numbers as tests/test_mvp_e2e.py but off the paper-first schema
(tests/_spec_test_helpers.asset_growth_resolved_spec) instead of the v1
fixture -- same synthetic data, same plugin (compute_signal is spec-
agnostic), same BacktestExecutor. Proves the ResolvedMethodSpec path through
Pipeline reproduces byte-identical economics to the v1 path.
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
    expected_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"

SNAPSHOT_ID = "mvp_synthetic_resolved_v1"


@pytest.fixture()
def pipeline(tmp_path) -> Pipeline:
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


@pytest.fixture()
def resolved_spec():
    return asset_growth_resolved_spec()


@pytest.fixture()
def generated_plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="cooper_gulen_schill_2008_asset_growth_resolved",
        factor_id="cooper_gulen_schill_2008_asset_growth",
        code=PLUGIN_PATH.read_text(encoding="utf-8"),
        code_hash="synthetic",
    )


def test_signal_master_table_has_expected_shape(pipeline, resolved_spec):
    from src.infra.data_layer import assemble_signal_master_table

    storage_path = pipeline.data_layer.snapshots.get_snapshot(SNAPSHOT_ID).storage_path
    smt = assemble_signal_master_table(resolved_spec, storage_path)
    assert len(smt) == 30
    assert set(smt.columns) >= {"permno", "time_avail_m", "at"}


def test_mvp_chain_matches_golden_numbers(pipeline, resolved_spec, generated_plugin):
    run = pipeline.run_from_method_spec(
        resolved_spec, snapshot_id=SNAPSHOT_ID, plugin=generated_plugin
    )

    golden = expected_metrics()

    assert run.status == "success"
    assert run.metrics.n_months == golden["n_months"]
    assert run.metrics.mean_return == pytest.approx(golden["mean_monthly_return"], rel=1e-9)
    assert run.metrics.t_stat == pytest.approx(golden["t_stat"], rel=1e-9)

    stored = pipeline.evidence_store.load_run(run.factor_id, run.run_id)
    assert stored is not None
    assert stored.metrics.mean_return == pytest.approx(golden["mean_monthly_return"], rel=1e-9)
