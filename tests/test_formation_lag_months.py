"""Unit tests for `config["formation_lag_months"]` (docs/step6.md gap #2):
C&Z's global, undocumented 1-month portfolio-formation lag
(`signal[, yyyymm := yyyymm + 1]`). Default 0 must be a no-op -- see
`test_default_zero_matches_existing_calendar_rebalance_golden_numbers`, which
locks the same golden numbers as `tests/test_calendar_rebalance.py`.
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor


def _signal_one_row() -> pd.DataFrame:
    # one formation at 2000-06 (June)
    return pd.DataFrame({"permno": [1], "yyyymm": [200006], "signal": [0.5]})


def _msf_full_year() -> pd.DataFrame:
    months = [200006 + i for i in range(7)] + [200101 + i for i in range(12)]
    return pd.DataFrame(
        {"permno": 1, "yyyymm": months, "ret": 0.01, "me": 100.0, "exchcd": 1}
    )


def test_default_zero_matches_existing_calendar_rebalance_golden_numbers():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "annual"},
    )
    assert len(merged) == 12
    assert merged["yyyymm"].min() == 200007
    assert merged["yyyymm"].max() == 200106


def test_lag_one_shifts_hold_window_by_one_month():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "annual", "formation_lag_months": 1},
    )
    # signal yyyymm shifted 200006 -> 200007, then held August(200008)..July(200107)
    assert len(merged) == 12
    assert merged["yyyymm"].min() == 200008
    assert merged["yyyymm"].max() == 200107


def test_lag_crosses_year_boundary():
    signal = pd.DataFrame({"permno": [1], "yyyymm": [200012], "signal": [0.5]})
    msf = pd.DataFrame(
        {"permno": 1, "yyyymm": [200012 + i for i in range(1, 4)] + [200101, 200102], "ret": 0.01, "me": 100.0, "exchcd": 1}
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        msf, signal, {"holding_period_months": 1, "rebalance_frequency": "monthly", "formation_lag_months": 1},
    )
    # 200012 -> lag 1 -> 200101, held month = 200102
    assert sorted(merged["yyyymm"]) == [200102]


def test_formation_cohort_reflects_lagged_month():
    engine = BacktestExecutor()
    engine.apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "annual", "formation_lag_months": 1},
    )
    assert sorted(engine.formation["cohort"].unique().tolist()) == [200007]
