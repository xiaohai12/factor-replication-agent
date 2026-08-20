"""Tests for the real WRDS raw-CSV data loaders added 2026-07-30
(data/local/*.csv -- CRSP "new CIZ" export, Compustat, CCM link, IBES,
13F, CRSP index, Pastor-Stambaugh liquidity factors).

`data/local/` is gitignored (developer-local real data, not committed) --
every test here skips gracefully when the underlying file isn't present, the
same pattern `test_crsp_raw_panel.py` uses for its synthetic-data fixtures.

Large files (CRSP_STOCK_MONTH.csv ~2.6GB, CRSP_STOCK_DAILY.csv ~60GB,
COMPUSTAT_FUNDAMENTALS_QUATER.csv ~4GB, IBES_UNADJUSTED_SUMMARY.csv ~8GB) are
always read here with a small `nrows` sample -- see docs/decision-log.md
(2026-07-30 entry) for why a full-file run isn't exercised by this suite.
Only genuinely small files (CCM link ~51MB, IBES-CRSP link ~1.5MB, Compustat
annual ~570K rows, CRSP index, liquidity factors) are read in full.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infra.backtest_engine import BacktestExecutor
from src.infra.data_layer import (
    _load_link_tables,
    _load_source_frame,
    build_crsp_monthly_panel_ciz,
    load_crsp_index_factors,
    load_daily_msf_ciz,
    load_ibes_recommendation_detail,
    load_ibes_unadjusted_actual,
    load_institutional_ownership_13f,
    load_liquidity_factors,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
LOCAL_DIR = DATA_DIR / "local"

requires_crsp_monthly = pytest.mark.skipif(
    not (LOCAL_DIR / "CRSP_STOCK_MONTH.csv").exists(),
    reason="real data/local/CRSP_STOCK_MONTH.csv not present",
)
requires_crsp_daily = pytest.mark.skipif(
    not (LOCAL_DIR / "CRSP_STOCK_DAILY.csv").exists(),
    reason="real data/local/CRSP_STOCK_DAILY.csv not present",
)
requires_link_tables = pytest.mark.skipif(
    not (LOCAL_DIR / "CRSP_COMPUSTAT_LINK.csv").exists()
    or not (LOCAL_DIR / "IBES_CRSP_Link.csv").exists(),
    reason="real CCM/IBES-CRSP link CSVs not present",
)
requires_compustat_fundamental_annual = pytest.mark.skipif(
    not (LOCAL_DIR / "COMPUSTAT_FUNDAMENTALS_ANNUAL.csv").exists(),
    reason="real data/local/COMPUSTAT_FUNDAMENTALS_ANNUAL.csv not present",
)
requires_index_liquidity = pytest.mark.skipif(
    not (LOCAL_DIR / "CRSP_INDEX_MONTH.csv").exists()
    or not (LOCAL_DIR / "liquidity_factors.csv").exists(),
    reason="real CRSP index / liquidity_factors CSVs not present",
)
requires_13f = pytest.mark.skipif(
    not (LOCAL_DIR / "13F.csv").exists(), reason="real data/local/13F.csv not present"
)
requires_ibes_detail = pytest.mark.skipif(
    not (LOCAL_DIR / "IBES_RECOMMENDATION_DETAIL.csv").exists()
    or not (LOCAL_DIR / "IBES_UNADJUSTED_ACTURAL.csv").exists(),
    reason="real IBES recommendation-detail/actual CSVs not present",
)

REQUIRED_MONTHLY_COLS = {"permno", "yyyymm", "ret", "me", "exchcd", "shrcd", "siccd", "dlret"}
REQUIRED_DAILY_COLS = {"permno", "date", "ret", "prc", "shrout", "exchcd", "shrcd", "siccd"}


@requires_crsp_monthly
def test_build_crsp_monthly_panel_ciz_schema():
    df = build_crsp_monthly_panel_ciz(LOCAL_DIR, nrows=20_000)
    assert REQUIRED_MONTHLY_COLS.issubset(df.columns)
    assert len(df) > 0
    assert set(df["exchcd"].unique()).issubset({0, 1, 2, 3})
    assert (df["me"].dropna() >= 0).all()


@requires_crsp_monthly
def test_engine_load_data_crsp_ciz_layout():
    engine = BacktestExecutor(data_path=str(DATA_DIR))
    # NOTE: this dispatches to a FULL read of CRSP_STOCK_MONTH.csv (no nrows
    # hook on BacktestExecutor.load_data) -- only exercised when the real
    # (large, gitignored) file is present on the developer's own machine.
    panel = engine.load_data(config={"returns_layout": "crsp_ciz", "returns_dir": str(LOCAL_DIR)})
    assert REQUIRED_MONTHLY_COLS.issubset(panel.columns)
    assert len(panel) > 0


@requires_crsp_daily
def test_load_daily_msf_ciz_schema():
    df = load_daily_msf_ciz(LOCAL_DIR / "CRSP_STOCK_DAILY.csv", nrows=5_000)
    assert REQUIRED_DAILY_COLS.issubset(df.columns)
    assert len(df) > 0


@requires_link_tables
def test_raw_csv_link_tables_load_and_join():
    links = _load_link_tables(DATA_DIR)
    assert "ccm" in links and "ibes_crsp_link" in links
    assert {"gvkey", "lpermno", "linkdt", "linkenddt"}.issubset(links["ccm"].columns)
    assert {"ticker", "permno", "sdate", "edate"}.issubset(links["ibes_crsp_link"].columns)


@requires_compustat_fundamental_annual
@requires_link_tables
def test_raw_csv_compustat_fundamental_annual_resolves_permno():
    links = _load_link_tables(DATA_DIR)
    out = _load_source_frame(DATA_DIR, "compustat_fundamental_annual", ["at", "ceq"], 6, links)
    assert out is not None
    assert {"permno", "time_avail_m", "at", "ceq"}.issubset(out.columns)
    assert len(out) > 0
    assert out["permno"].dtype.kind == "i"


@requires_index_liquidity
def test_crsp_index_and_liquidity_factors():
    idx = load_crsp_index_factors(DATA_DIR, frequency="monthly")
    assert {"yyyymm", "vwretd", "sprtrn"}.issubset(idx.columns)
    assert len(idx) > 0

    liq = load_liquidity_factors(DATA_DIR)
    assert {"yyyymm", "ps_level", "ps_innov", "ps_vwf"}.issubset(liq.columns)
    assert len(liq) > 0
    # The -99 PS missing-data placeholder must never survive as a real value.
    assert not (liq[["ps_level", "ps_innov", "ps_vwf"]] <= -99).any().any()


@requires_13f
def test_institutional_ownership_13f_best_effort():
    out = load_institutional_ownership_13f(DATA_DIR, nrows=5_000)
    assert {"permno", "yyyymm", "instown_perc"}.issubset(out.columns)
    # Some rows may fail to resolve a permno via the cusip match and are
    # dropped -- just confirm the loader runs end-to-end without error.


@requires_ibes_detail
def test_ibes_recommendation_and_actual_pass_through():
    rec = load_ibes_recommendation_detail(DATA_DIR, nrows=1_000)
    assert "anndats" in rec.columns
    assert len(rec) > 0

    act = load_ibes_unadjusted_actual(DATA_DIR, nrows=1_000)
    assert "ticker" in act.columns
    assert len(act) > 0
