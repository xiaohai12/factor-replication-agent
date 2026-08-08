"""Phase D: same smoke test as tests/test_real_wrds_samples_e2e.py (real
sample WRDS data, not synthetic) but off `asset_growth_resolved_spec`
instead of the v1 fixture -- `assemble_signal_master_table`/
`registry.build_config` are both already dual-dispatch, so this is a
fixture swap with no golden-number risk (this file only asserts "ran
successfully / not NaN", same as the v1 original).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.infra.backtest_engine import BacktestExecutor
from src.infra.data_layer import assemble_signal_master_table, sources
from src.steps.step3_codegen import registry as codegen_registry
from tests._spec_test_helpers import asset_growth_resolved_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "data" / "local" / "validation_sample"
ASSET_GROWTH_PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"

_SAMPLE_FILES = {
    "CRSP_STOCK_MONTH.csv": "CRSP_STOCK_MONTH_sample.csv",
    "CRSP_DELISTING.csv": "CRSP_DELISTING_sample.csv",
    "COMPUSTAT_FUNDAMENTALS_ANNUAL.csv": "COMPUSTAT_FUNDAMENTALS_ANNUAL_sample.csv",
    "CRSP_COMPUSTAT_LINK.csv": "CRSP_COMPUSTAT_LINK_sample.csv",
}

pytestmark = pytest.mark.skipif(
    not all((SAMPLES_DIR / name).exists() for name in _SAMPLE_FILES.values()),
    reason="data/local/validation_sample/*.csv not present (developer-local real-data samples)",
)


@pytest.fixture()
def sample_data_dir(tmp_path) -> Path:
    local = tmp_path / "local"
    local.mkdir()
    for real_name, sample_name in _SAMPLE_FILES.items():
        (local / real_name).symlink_to(SAMPLES_DIR / sample_name)
    return tmp_path


@pytest.fixture()
def asset_growth_spec():
    return asset_growth_resolved_spec()


def test_signal_master_table_loads_from_samples(sample_data_dir, asset_growth_spec):
    master = assemble_signal_master_table(asset_growth_spec, sample_data_dir)
    assert {"permno", "time_avail_m", "at"} <= set(master.columns)
    assert len(master) > 0
    assert master["permno"].nunique() >= 5


def test_full_backtest_runs_on_sample_data(sample_data_dir, asset_growth_spec):
    plugin_spec = importlib.util.spec_from_file_location(
        "asset_growth_plugin_under_test_resolved", ASSET_GROWTH_PLUGIN_PATH
    )
    plugin_mod = importlib.util.module_from_spec(plugin_spec)
    plugin_spec.loader.exec_module(plugin_mod)

    master = assemble_signal_master_table(asset_growth_spec, sample_data_dir)
    signal = plugin_mod.compute_signal(master)
    assert len(signal) > 0

    panel = sources.get_returns_universe("us_equity_crsp").load(sample_data_dir / "local")
    config = codegen_registry.build_config(asset_growth_spec, None)

    engine = BacktestExecutor(data_path=str(sample_data_dir))
    result = engine.run_with_config(signal, config, data=panel)
    metrics = result["metrics"]

    assert metrics["n_months"] > 0
    assert metrics["mean_monthly_return"] == metrics["mean_monthly_return"]
    assert metrics["t_stat"] == metrics["t_stat"]
