"""Unit tests for the double sort re-added to `BacktestExecutor` (D4): a
formation-locked (cohort-aware) adaptation of the multi-dimensional sort
removed 2026-07-24 (see docs/decision-log.md) -- re-added because
Hirshleifer/Hsu/Li 2012's independent size x innovation-index sort needs it.

Unlike the original (removed) implementation, breakpoints are keyed by
`cohort` (formation yyyymm) and computed from `self.formation` (never from
the future-return-joined `self.merged`), matching the single-dim path's
formation-locked-breakpoints fix.

Uses a small hand-built 2x2 panel where the expected independent double-sort
breakpoints/assignments/returns can be verified by hand (same economics as
the removed test_multi_sort.py fixture, migrated to the current engine's
apply_signal_holding_period-based flow).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor

_SORT_DIMS_2X2 = [
    {"column": "me", "quantiles": 2, "source": "nyse", "independent": True, "role": "conditioning"},
    {"column": "signal", "quantiles": 2, "source": "nyse", "independent": True, "role": "target"},
]

_CONFIG = {
    "holding_period_months": 1,
    "weighting_rule": "ew",
    "sort_dims": _SORT_DIMS_2X2,
    "long_leg": "low",
}


def _panel() -> pd.DataFrame:
    """8 stocks: a formation-month (200001) row for each (supplies `me`/
    `exchcd` to `self.formation`) and a held-month (200002) row for each
    (supplies `ret`). `me` splits {1,2,3,4} small vs {5,6,7,8} big; `signal`
    (attached via the signal frame, not this panel) splits independently.
    """
    permnos = [1, 2, 3, 4, 5, 6, 7, 8]
    me = [10, 11, 12, 13, 90, 91, 92, 93]
    ret = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]

    formation_rows = pd.DataFrame({
        "permno": permnos, "yyyymm": [200001] * 8, "me": me,
        "exchcd": [1] * 8, "ret": [0.0] * 8,
    })
    held_rows = pd.DataFrame({
        "permno": permnos, "yyyymm": [200002] * 8, "me": me,
        "exchcd": [1] * 8, "ret": ret,
    })
    return pd.concat([formation_rows, held_rows], ignore_index=True)


def _signal() -> pd.DataFrame:
    # low: permno 1,3,5,7 (signal 1,2,3,4); high: permno 2,4,6,8 (signal 5,6,7,8)
    return pd.DataFrame({
        "permno": [1, 2, 3, 4, 5, 6, 7, 8],
        "yyyymm": [200001] * 8,
        "signal": [1.0, 5.0, 2.0, 6.0, 3.0, 7.0, 4.0, 8.0],
    })


def _run() -> BacktestExecutor:
    engine = BacktestExecutor()
    engine.config = _CONFIG
    engine.apply_signal_holding_period(_panel(), _signal(), _CONFIG)
    engine.form_portfolios()
    engine.compute_portfolio_returns()
    engine.combine_portfolio_returns()
    return engine


class TestFormPortfoliosDispatchesToMulti:
    def test_portfolio_columns_are_portfolio_0_and_portfolio_1(self):
        engine = _run()
        assert "portfolio_0" in engine.portfolios.columns
        assert "portfolio_1" in engine.portfolios.columns
        assert "portfolio" not in engine.portfolios.columns

    def test_size_dimension_splits_small_vs_big(self):
        engine = _run()
        by_permno = engine.portfolios.set_index("permno")
        assert list(by_permno.loc[[1, 2, 3, 4], "portfolio_0"]) == [1, 1, 1, 1]
        assert list(by_permno.loc[[5, 6, 7, 8], "portfolio_0"]) == [2, 2, 2, 2]

    def test_signal_dimension_splits_low_vs_high(self):
        engine = _run()
        by_permno = engine.portfolios.set_index("permno")
        assert by_permno.loc[1, "portfolio_1"] == 1
        assert by_permno.loc[2, "portfolio_1"] == 2


class TestComputePortfolioReturnsMulti:
    def test_equal_weighted_cell_means(self):
        engine = _run()
        rets = engine.returns
        cell = rets[(rets["portfolio_0"] == 1) & (rets["portfolio_1"] == 1)]
        # small+low bucket = permno 1 (ret 0.01), 3 (ret 0.03) -> mean 0.02
        assert cell["ret"].iloc[0] == pytest.approx(0.02)


class TestCombinePortfolioReturnsMulti:
    def test_averages_signal_spread_across_size_groups(self):
        engine = _run()
        ls = engine.long_short
        # small group: low(1,3)=0.02, high(2,4)=0.03 -> spread(low-high)=-0.01
        # big group: low(5,7)=0.06, high(6,8)=0.07 -> spread(low-high)=-0.01
        # average of the two = -0.01
        assert ls["ls_return"].iloc[0] == pytest.approx(-0.01)

    def test_output_shape_matches_single_dim_path(self):
        """compute_metrics must be able to consume either path unchanged."""
        engine = _run()
        assert list(engine.long_short.columns) == ["yyyymm", "ls_return"]
        metrics = engine.compute_metrics()
        assert metrics["n_months"] == 1


class TestSingleDimPathUnaffectedByMultiDimCode:
    """The single-sort path must be byte-for-byte unchanged: dispatch only
    triggers when config["sort_dims"] has >= 2 entries."""

    def test_no_sort_dims_uses_single_dim_path(self):
        engine = BacktestExecutor()
        config = {**_CONFIG, "sort_dims": [], "breakpoint_quantiles": 2, "breakpoint_source": "full_sample"}
        engine.config = config
        engine.apply_signal_holding_period(_panel(), _signal(), config)
        engine.form_portfolios()
        assert "portfolio" in engine.portfolios.columns
        assert "portfolio_0" not in engine.portfolios.columns


class TestWithinGroupModeFailsLoud:
    """docs/resolve-diagnostics-gaps.md problem 2: `mode="within_group"` is
    a real, unimplemented engine capability -- `registry.build_config`
    passes it through as-is (never silently coercing to sequential), so the
    engine itself must fail loud rather than silently running the wrong
    (sequential) economics."""

    def test_within_group_mode_raises(self):
        engine = BacktestExecutor()
        engine.config = _CONFIG
        engine.apply_signal_holding_period(_panel(), _signal(), _CONFIG)
        dims_with_within_group = [
            {"column": "me", "quantiles": 2, "source": "nyse", "mode": "within_group", "independent": False, "role": "conditioning"},
            {"column": "signal", "quantiles": 2, "source": "nyse", "mode": "independent", "independent": True, "role": "target"},
        ]
        with pytest.raises(ValueError, match="within_group"):
            engine.assign_portfolios_multi(breakpoints=dims_with_within_group)

