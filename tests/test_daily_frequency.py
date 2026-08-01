"""Unit tests for the excess-return support added in plan.md Phase 6:
`BacktestExecutor.apply_excess_returns` (subtracts rf when factor data is
supplied).

NOTE (2026-07-31): `BacktestExecutor.load_daily_msf` (+ its `TestLoadDailyMsf`
tests that lived here) was removed along with `load_msf`/the "panel"
returns_layout -- see docs/decision-log.md same date. Daily-frequency source
data is now read via `data_layer.load_daily_msf_ciz` instead.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor


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
