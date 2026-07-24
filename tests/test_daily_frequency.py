"""Unit tests for the daily-source-data + excess-return support added in
plan.md Phase 6: `BacktestExecutor.load_daily_msf` (compounds daily
CRSP-shaped data into the standard monthly-keyed panel) and
`BacktestExecutor.apply_excess_returns` (subtracts rf when factor data is
supplied).

Documented v1 scope: `load_daily_msf` produces "daily source data, monthly
output" -- not a genuine daily-frequency rebalancing engine (see its
docstring / plan.md Phase 6 for the boundary).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor


def _write_daily_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "daily.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


class TestLoadDailyMsf:
    def test_compounds_daily_returns_into_monthly(self, tmp_path):
        # permno 1, January 2020: three trading days with known returns.
        # Compounded monthly return = (1.01 * 0.99 * 1.02) - 1
        rows = [
            {"permno": 1, "date": "2020-01-02", "ret": 0.01, "prc": 10.0, "shrout": 100, "exchcd": 1, "shrcd": 10, "siccd": 2000},
            {"permno": 1, "date": "2020-01-03", "ret": -0.01, "prc": 9.9, "shrout": 100, "exchcd": 1, "shrcd": 10, "siccd": 2000},
            {"permno": 1, "date": "2020-01-06", "ret": 0.02, "prc": 10.1, "shrout": 100, "exchcd": 1, "shrcd": 10, "siccd": 2000},
        ]
        path = _write_daily_parquet(tmp_path, rows)
        out = BacktestExecutor.load_daily_msf(path)
        assert len(out) == 1
        row = out.iloc[0]
        assert row["permno"] == 1
        assert row["yyyymm"] == 202001
        expected_ret = (1.01 * 0.99 * 1.02) - 1
        assert row["ret"] == pytest.approx(expected_ret)
        # me computed from the LAST trading day's price/shrout
        assert row["me"] == pytest.approx(10.1 * 100)

    def test_multiple_permnos_and_months(self, tmp_path):
        rows = [
            {"permno": 1, "date": "2020-01-15", "ret": 0.05, "prc": 20.0, "shrout": 50, "exchcd": 1, "shrcd": 10, "siccd": 2000},
            {"permno": 1, "date": "2020-02-15", "ret": -0.03, "prc": 19.0, "shrout": 50, "exchcd": 1, "shrcd": 10, "siccd": 2000},
            {"permno": 2, "date": "2020-01-15", "ret": 0.01, "prc": 5.0, "shrout": 200, "exchcd": 2, "shrcd": 11, "siccd": 3000},
        ]
        path = _write_daily_parquet(tmp_path, rows)
        out = BacktestExecutor.load_daily_msf(path)
        assert len(out) == 3
        assert set(zip(out["permno"], out["yyyymm"])) == {(1, 202001), (1, 202002), (2, 202001)}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            BacktestExecutor.load_daily_msf(tmp_path / "nope.parquet")


class TestApplyExcessReturns:
    def _msf(self) -> pd.DataFrame:
        return pd.DataFrame({
            "permno": [1, 2],
            "yyyymm": [200001, 200001],
            "ret": [0.05, 0.03],
        })

    def _factors(self) -> pd.DataFrame:
        return pd.DataFrame({"yyyymm": [200001], "rf": [0.01]})

    def test_subtracts_rf_when_excess_and_factors_available(self):
        out = BacktestExecutor().apply_excess_returns(self._msf(), self._factors(), config={"return_basis": "excess"})
        assert out["ret"].tolist() == pytest.approx([0.04, 0.02])

    def test_defaults_to_excess_when_return_basis_unset(self):
        out = BacktestExecutor().apply_excess_returns(self._msf(), self._factors(), config={})
        assert out["ret"].tolist() == pytest.approx([0.04, 0.02])

    def test_noop_when_return_basis_raw(self):
        out = BacktestExecutor().apply_excess_returns(self._msf(), self._factors(), config={"return_basis": "raw"})
        pd.testing.assert_series_equal(out["ret"], self._msf()["ret"])

    def test_noop_when_no_factors(self):
        out = BacktestExecutor().apply_excess_returns(self._msf(), None, config={"return_basis": "excess"})
        pd.testing.assert_series_equal(out["ret"], self._msf()["ret"])

    def test_noop_when_factors_missing_rf_column(self):
        factors = pd.DataFrame({"yyyymm": [200001], "mktrf": [0.02]})
        out = BacktestExecutor().apply_excess_returns(self._msf(), factors, config={"return_basis": "excess"})
        pd.testing.assert_series_equal(out["ret"], self._msf()["ret"])
