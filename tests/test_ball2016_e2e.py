"""MVP end-to-end test for the Ball et al. (2016) cash-based operating
profitability factor — exercises the new general `compute_long_short` hook.

Same pattern as tests/test_mvp_e2e.py / tests/test_accruals_e2e.py, but this
factor is a 2x3 double sort (size x profitability) combined as
0.5*(small-robust + big-robust) - 0.5*(small-weak + big-weak), which the
standard single-variable `_compute_long_short()` cannot express. This test
verifies:
  1. `BacktestEngine._detect_hooks()` correctly flags `compute_long_short` as
     needed for this spec's multi-leg long_leg/short_leg description.
  2. The plugin's `compute_breakpoints_hook`/`assign_portfolios_hook`/
     `compute_long_short_hook` (all hand-written here, mirroring what
     MetaCoder would generate against the new hook signature) run through
     `BacktestEngine.run()` end-to-end via `Pipeline.run_from_method_spec()`.
  3. The resulting metrics match golden numbers derived independently in
     tests/synthetic_data/ball2016_synthetic_data.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infra.data_layer import SnapshotMetadata
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.pipeline import Pipeline
from tests.synthetic_data.ball2016_synthetic_data import (
    build_ccm_link,
    build_compustat_funda,
    build_crsp_msf,
    expected_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVED_SPEC_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "method_specs"
    / "ball2016_cash_based_operating_profitability_factor.resolved.methodspec.json"
)
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "ball2016_cash_based_operating_profitability_factor.py"

SNAPSHOT_ID = "ball2016_synthetic_v1"


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
    build_compustat_funda().to_parquet(snapshot_dir / "compustat_funda.parquet", index=False)
    build_ccm_link().to_parquet(snapshot_dir / "ccm_link.parquet", index=False)

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
def approved_spec() -> MethodSpec:
    text = RESOLVED_SPEC_PATH.read_text(encoding="utf-8")
    return MethodSpec.model_validate(json.loads(text))


@pytest.fixture()
def generated_plugin() -> PluginRecord:
    code = PLUGIN_PATH.read_text(encoding="utf-8")
    return PluginRecord(
        plugin_id="ball2016_cash_based_operating_profitability_factor_v1",
        factor_id="ball2016_cash_based_operating_profitability_factor",
        code=code,
        code_hash="synthetic",
    )


def test_multi_leg_long_short_hook_is_detected(approved_spec):
    """This spec's 2x3 double sort (market_value_of_equity x
    cash_based_operating_profitability) isn't resolved by
    registry.resolve_sort_dims() -- neither variable name is recognized as
    size-like by its narrow v1 heuristic (plan.md Phase 3) -- so
    compute_breakpoints/assign_portfolios are still hooked. Its
    return_combination ("average_leg_spread") is standard as of Phase 4,
    though, so compute_long_short is no longer flagged even though this
    fixture's plugin still supplies a hand-written compute_long_short_hook
    (hooks loaded from a plugin always take priority over the standard
    implementation regardless of what detect_hooks predicts).
    """
    from src.steps.step5_engine import BacktestEngine
    hooks = BacktestEngine._detect_hooks(approved_spec)
    assert "compute_breakpoints" in hooks
    assert "assign_portfolios" in hooks
    assert "compute_long_short" not in hooks


def test_signal_master_table_has_expected_shape(pipeline, approved_spec):
    smt = pipeline.data_layer.get_signal_master_table(
        SNAPSHOT_ID, lag_months=approved_spec.accounting_lag_months
    )
    assert len(smt) == 30
    assert set(smt.columns) >= {"permno", "time_avail_m", "revt", "at"}
    assert pipeline.data_layer.ccm_linker.link_issues == []


def test_mvp_chain_matches_golden_numbers(pipeline, approved_spec, generated_plugin):
    run = pipeline.run_from_method_spec(
        approved_spec, snapshot_id=SNAPSHOT_ID, plugin=generated_plugin
    )

    golden = expected_metrics()

    assert run.status == "success"
    assert run.metrics.n_months == golden["n_months"]
    assert run.metrics.mean_return == pytest.approx(golden["mean_monthly_return"], rel=1e-9)
    assert run.metrics.t_stat == pytest.approx(golden["t_stat"], rel=1e-9)

    stored = pipeline.evidence_store.load_run(run.factor_id, run.run_id)
    assert stored is not None
    assert stored.metrics.mean_return == pytest.approx(golden["mean_monthly_return"], rel=1e-9)
