"""MVP end-to-end test for sloan_1996_accruals — same pattern as test_mvp_e2e.py.

Exercises the full Phase 1 MVP chain from docs/roadmap.md on synthetic data
(no network / LLM calls):

    resolved MethodSpec (sloan_1996_accruals)
    -> DataLayer.get_signal_master_table()   (CCMLinker + TimeAvailComputer)
    -> plugin.compute_signal()               (already-generated plugin, incl.
                                               its own per-formation-date
                                               1%/99% winsorization)
    -> BacktestEngine.run()                  (9-step controlled lifecycle,
                                               dispatching apply_missing_policy
                                               to the plugin's hook since
                                               missing_action='winsorize' is
                                               non-standard)
    -> Pipeline.run_from_method_spec()       (persists a RunRecord to EvidenceStore)

Metrics are checked against the SAME golden numbers as
tests/test_mvp_e2e.py: the CRSP monthly returns and permno<->decile mapping
are identical (imported unchanged from asset_growth_synthetic_data.py), and
this factor's own long_leg/short_leg ("low"/"high") match the same
low-minus-high convention, so the closed-form expected long-short series is
unchanged. Winsorizing the accruals value at the 1%/99% percentile of a
10-point sample compresses the two extreme values towards the center
slightly but cannot change their rank (they stay the smallest/largest), so
the permno->decile assignment — and therefore the resulting long-short
series — is unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infra.data_layer import SnapshotMetadata
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.pipeline import Pipeline
from tests.synthetic_data.accruals_synthetic_data import (
    build_ccm_link,
    build_compustat_funda,
    build_crsp_msf,
    expected_metrics,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVED_SPEC_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "method_specs" / "sloan_1996_accruals.resolved.methodspec.json"
)
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "sloan_1996_accruals.py"

SNAPSHOT_ID = "accruals_synthetic_v1"


@pytest.fixture()
def pipeline(tmp_path) -> Pipeline:
    """A Pipeline wired to a temp data/evidence dir with synthetic-data snapshot tables registered."""
    data_path = tmp_path / "data"
    local_dir = data_path / "local"
    local_dir.mkdir(parents=True)

    crsp = build_crsp_msf()
    # BacktestEngine._load_data reads data_path/local/msf.parquet directly.
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
        plugin_id="sloan_1996_accruals_v1",
        factor_id="sloan_1996_accruals",
        code=code,
        code_hash="synthetic",
    )


def test_signal_master_table_has_expected_shape(pipeline, approved_spec):
    smt = pipeline.data_layer.get_signal_master_table(
        SNAPSHOT_ID, lag_months=approved_spec.accounting_lag_months
    )
    assert len(smt) == 30
    assert set(smt.columns) >= {"permno", "time_avail_m", "act", "che", "lct", "dlc", "dp", "at"}
    assert pipeline.data_layer.ccm_linker.link_issues == []


def test_accruals_hook_is_detected_for_winsorize_missing_action(approved_spec):
    from src.steps.step5_engine import BacktestEngine
    hooks = BacktestEngine._detect_hooks(approved_spec)
    assert "apply_missing_policy" in hooks


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
