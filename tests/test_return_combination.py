"""Unit tests for the generalized `compute_long_short` (plan.md Phase 4):
extreme_group_spread / average_leg_spread / single_signal_portfolio_return /
full_portfolio_return combination modes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.steps.step5_engine import steps


def _rets_df() -> pd.DataFrame:
    """3 months, deciles 1..10, portfolio i's return = i/100 for simplicity."""
    rows = []
    for yyyymm in (200001, 200002, 200003):
        for p in range(1, 11):
            rows.append({"yyyymm": yyyymm, "portfolio": p, "ret": p / 100})
    return pd.DataFrame(rows)


class TestExtremeGroupSpread:
    def test_default_is_extreme_group_spread(self):
        rets = _rets_df()
        out = steps.compute_long_short(rets, config={"breakpoint_quantiles": 10, "long_leg": "low"})
        # long=1 (0.01), short=10 (0.10) -> -0.09
        assert out["ls_return"].iloc[0] == pytest.approx(-0.09)

    def test_high_long_leg(self):
        rets = _rets_df()
        out = steps.compute_long_short(rets, config={"breakpoint_quantiles": 10, "long_leg": "high"})
        # long=10 (0.10), short=1 (0.01) -> 0.09
        assert out["ls_return"].iloc[0] == pytest.approx(0.09)


class TestAverageLegSpread:
    def test_without_explicit_legs_matches_extreme_group_spread(self):
        rets = _rets_df()
        config = {"breakpoint_quantiles": 10, "long_leg": "low", "return_combination_type": "average_leg_spread"}
        out = steps.compute_long_short(rets, config)
        assert out["ls_return"].iloc[0] == pytest.approx(-0.09)

    def test_with_explicit_multi_portfolio_legs(self):
        rets = _rets_df()
        config = {
            "return_combination_type": "average_leg_spread",
            "long_portfolios": [1, 2, 3],
            "short_portfolios": [8, 9, 10],
        }
        out = steps.compute_long_short(rets, config)
        # long avg = (0.01+0.02+0.03)/3 = 0.02; short avg = (0.08+0.09+0.10)/3 = 0.09
        assert out["ls_return"].iloc[0] == pytest.approx(0.02 - 0.09)


class TestSingleSignalPortfolioReturn:
    def test_reports_single_portfolio_return_not_a_spread(self):
        rets = _rets_df()
        config = {
            "breakpoint_quantiles": 10,
            "long_leg": "low",
            "return_combination_type": "single_signal_portfolio_return",
        }
        out = steps.compute_long_short(rets, config)
        # default single_portfolio = long extreme = portfolio 1 -> 0.01
        assert out["ls_return"].iloc[0] == pytest.approx(0.01)

    def test_explicit_single_portfolio_override(self):
        rets = _rets_df()
        config = {"return_combination_type": "single_signal_portfolio_return", "single_portfolio": 5}
        out = steps.compute_long_short(rets, config)
        assert out["ls_return"].iloc[0] == pytest.approx(0.05)


class TestFullPortfolioReturn:
    def test_returns_full_grid_unchanged(self):
        rets = _rets_df()
        out = steps.compute_long_short(rets, config={"return_combination_type": "full_portfolio_return"})
        pd.testing.assert_frame_equal(out.reset_index(drop=True), rets.reset_index(drop=True))

    def test_compute_metrics_handles_full_portfolio_return_shape(self):
        rets = _rets_df()
        out = steps.compute_long_short(rets, config={"return_combination_type": "full_portfolio_return"})
        metrics = steps.compute_metrics(out, config={})
        assert "ls_return" not in metrics
        assert metrics["n_months"] == 3
        assert metrics["portfolios"] == list(range(1, 11))
