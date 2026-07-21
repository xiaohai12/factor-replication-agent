"""Tests for reading the realistic multi-source CRSP layout into the engine
panel (data_layer.build_crsp_monthly_panel + BacktestEngine._load_data with
config["returns_layout"]=="crsp_raw").

Uses the synthetic WRDS-shaped data produced by
scripts/build_test_papers_synthetic_data.py (data/synthetic_data/test_papers_v1),
which ships crsp_msf / crsp_msenames / crsp_msedelist as SEPARATE tables like
real CRSP. Skips if that data hasn't been generated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infra.data_layer import build_crsp_monthly_panel
from src.steps.step5_engine import BacktestEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "synthetic_data" / "test_papers_v1"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "crsp_msf.parquet").exists(),
    reason="run scripts/build_test_papers_synthetic_data.py first",
)

REQUIRED_COLS = {"permno", "yyyymm", "ret", "me", "exchcd", "shrcd", "siccd"}


def test_panel_has_engine_columns():
    p = build_crsp_monthly_panel(DATA_DIR)
    assert REQUIRED_COLS.issubset(p.columns)
    assert len(p) > 0
    assert p["me"].notna().all()          # me computed for every row
    assert (p["me"] >= 0).all()           # abs(prc) * shrout


def test_point_in_time_names_join():
    # exchcd/shrcd/siccd come from msenames; values must be in the real domains
    p = build_crsp_monthly_panel(DATA_DIR)
    assert set(p["exchcd"].dropna().unique()).issubset({0, 1, 2, 3, 4})
    assert set(p["shrcd"].dropna().unique()).issubset({10, 11, 12, 18, 73})


def test_delisting_return_folded_into_last_month():
    p = build_crsp_monthly_panel(DATA_DIR)
    assert "dlret" in p.columns
    # at least one delisted firm's dlret should land on a real panel row
    assert int(p["dlret"].notna().sum()) >= 1
    # and only on each firm's last month
    with_dl = p[p["dlret"].notna()]
    last_month = p.groupby("permno")["yyyymm"].transform("max")
    assert (p.loc[with_dl.index, "yyyymm"] == last_month.loc[with_dl.index]).all()


def test_engine_load_data_crsp_raw_layout():
    engine = BacktestEngine(data_path=str(DATA_DIR))
    panel = engine._load_data({"returns_layout": "crsp_raw"})
    assert REQUIRED_COLS.issubset(panel.columns)
    assert len(panel) > 0


def test_returns_dir_override():
    # data_path elsewhere, but returns_dir points at the real tables
    engine = BacktestEngine(data_path=str(REPO_ROOT / "data"))
    panel = engine._load_data(
        {"returns_layout": "crsp_raw", "returns_dir": str(DATA_DIR)}
    )
    assert REQUIRED_COLS.issubset(panel.columns)
    assert len(panel) > 0
