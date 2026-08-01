"""End-to-end smoke test: does a REAL resolved MethodSpec's data actually load
and backtest correctly from the small, ID-aligned sample CSVs
(data/local/samples/), through the exact same public entry points production
code uses?

Chain exercised: DataSource registry (`sources.get_returns_universe` /
`assemble_signal_master_table`) -> the real generated plugin's compute_signal()
(tests/fixtures/plugins/) -> BacktestExecutor.run_with_config().

`data/local/samples/` is gitignored (developer-local) -- every test here skips
gracefully when it isn't present, same pattern as
tests/test_real_wrds_csv_loaders.py. Unlike that file (which points straight at
the real, full-size WRDS exports), this file works with the samples/ subset,
which is small enough to load in full and fast enough to run in the normal
test suite.

The sample CSVs use the real raw filenames of `WRDS's own exports (just
smaller row counts) EXCEPT for one thing: they're named `<STEM>_sample.csv`
instead of `<STEM>.csv`. `_sample_data_dir` symlinks them to the real names
under a temp `local/` dir so the DataSource registry's raw-file fallback
(`SourceSpec.raw_file` / `LinkTableSpec.raw_file`) finds them unmodified.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infra.backtest_engine import BacktestExecutor
from src.infra.data_layer import assemble_signal_master_table, sources
from src.infra.models.method_spec import MethodSpec
from src.steps.step3_codegen import registry as codegen_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "data" / "local" / "samples"

# stem (real WRDS filename, no "_sample") -> sample filename under SAMPLES_DIR
_SAMPLE_FILES = {
    "CRSP_STOCK_MONTH.csv": "CRSP_STOCK_MONTH_sample.csv",
    "CRSP_DELISTING.csv": "CRSP_DELISTING_sample.csv",
    "COMPUSTAT_FUNDAMENTALS_ANNUAL.csv": "COMPUSTAT_FUNDAMENTALS_ANNUAL_sample.csv",
    "CRSP_COMPUSTAT_LINK.csv": "CRSP_COMPUSTAT_LINK_sample.csv",
}

pytestmark = pytest.mark.skipif(
    not all((SAMPLES_DIR / name).exists() for name in _SAMPLE_FILES.values()),
    reason="data/local/samples/*.csv not present (developer-local real-data samples)",
)

ASSET_GROWTH_SPEC_PATH = (
    REPO_ROOT / "runs" / "method_specs" / "resolved"
    / "cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json"
)
ASSET_GROWTH_PLUGIN_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"
)


@pytest.fixture()
def sample_data_dir(tmp_path) -> Path:
    """A temp dir with a `local/` subfolder symlinking the sample CSVs to the
    real WRDS filenames the DataSource registry's raw-file fallback expects."""
    local = tmp_path / "local"
    local.mkdir()
    for real_name, sample_name in _SAMPLE_FILES.items():
        (local / real_name).symlink_to(SAMPLES_DIR / sample_name)
    return tmp_path


@pytest.fixture()
def asset_growth_spec() -> MethodSpec:
    import json
    return MethodSpec.model_validate(json.loads(ASSET_GROWTH_SPEC_PATH.read_text()))


def test_returns_panel_loads_from_samples(sample_data_dir):
    universe = sources.get_returns_universe("us_equity_crsp")
    panel = universe.load(sample_data_dir / "local")
    assert {"permno", "yyyymm", "ret", "me", "exchcd", "shrcd", "siccd", "dlret"} <= set(panel.columns)
    assert len(panel) > 0
    assert panel["permno"].nunique() >= 5  # the sample fixture covers ~9 aligned entities


def test_signal_master_table_loads_from_samples(sample_data_dir, asset_growth_spec):
    master = assemble_signal_master_table(asset_growth_spec, sample_data_dir)
    assert {"permno", "time_avail_m", "at"} <= set(master.columns)
    assert len(master) > 0
    assert master["permno"].nunique() >= 5


def test_full_backtest_runs_on_sample_data(sample_data_dir, asset_growth_spec):
    """The real generated plugin + the real BacktestExecutor, run against the
    sample-derived signal + returns data -- not synthetic fixtures."""
    import importlib.util

    plugin_spec = importlib.util.spec_from_file_location(
        "asset_growth_plugin_under_test", ASSET_GROWTH_PLUGIN_PATH
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
    assert metrics["mean_monthly_return"] == metrics["mean_monthly_return"]  # not NaN
    assert metrics["t_stat"] == metrics["t_stat"]  # not NaN
