"""Regression test for the 2026-07-28 fix: `compute_breakpoints` must use the
formation cross-section (`self.formation`), not the post-holding-period-join
`self.merged`, so a stock with a valid formation-time signal but NO valid
return in any of its held months (e.g. delisted immediately after formation)
is not silently excluded from its own cohort's breakpoint population.

Before the fix: `apply_signal_holding_period` inner-joins the expanded signal
with the returns panel, so a permno absent from every held month is dropped
before `compute_breakpoints` ever sees it -- a future-return-availability /
survivorship leak into a formation-time statistic. See docs/decision-log.md.
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor

_CONFIG = {
    "holding_period_months": 3,
    "breakpoint_quantiles": 2,  # median split: portfolio 1 (low) / 2 (high)
    "breakpoint_source": "full_sample",
    "weighting_rule": "ew",
}


def _signal() -> pd.DataFrame:
    # Formation cross-section (200001): signals 1, 2, 3, 4 -> true median 2.5.
    return pd.DataFrame({
        "permno": [1, 2, 3, 4],
        "yyyymm": [200001, 200001, 200001, 200001],
        "signal": [1.0, 2.0, 3.0, 4.0],
    })


def _panel_with_one_delisted_stock() -> pd.DataFrame:
    """permno 4 (the highest-signal stock) has NO return in ANY held month
    (200002-200004) -- e.g. delisted the month after formation. Permnos 1-3
    have returns in all three held months."""
    rows = [(p, m) for p in (1, 2, 3) for m in (200002, 200003, 200004)]
    return pd.DataFrame({
        "permno": [p for p, _ in rows],
        "yyyymm": [m for _, m in rows],
        "ret": [0.01] * len(rows),
        "me": [100.0] * len(rows),
        "exchcd": [1] * len(rows),
    })


class TestBreakpointPopulationIndependentOfFutureReturnAvailability:
    def test_formation_cross_section_keeps_all_four_signals(self):
        """self.formation must retain permno 4 even though it has zero
        surviving rows in self.merged."""
        engine = BacktestExecutor()
        engine.apply_signal_holding_period(_panel_with_one_delisted_stock(), _signal(), _CONFIG)

        assert set(engine.formation["permno"]) == {1, 2, 3, 4}
        # permno 4 has NO row in the return-availability-filtered panel.
        assert 4 not in set(engine.merged["permno"])

    def test_breakpoint_uses_full_formation_population_not_merged(self):
        """The median breakpoint must reflect all 4 signals (1,2,3,4 ->
        median 2.5), not just the 3 that happen to survive the future-return
        join (1,2,3 -> median 2.0, the biased number the review reproduced)."""
        engine = BacktestExecutor()
        engine.apply_signal_holding_period(_panel_with_one_delisted_stock(), _signal(), _CONFIG)
        bp = engine.compute_breakpoints(config=_CONFIG)

        assert bp.loc[200001, "q1"] == 2.5

    def test_form_portfolios_end_to_end_uses_unbiased_breakpoint(self):
        """Via the normal Step 7 entry point (form_portfolios), permnos 1-3
        (the only ones with surviving returns) must be split using the TRUE
        4-stock median (2.5) -> permno 1,2 low (portfolio 1); permno 3 high
        (portfolio 2). Under the old bug, the 3-stock median (2.0) would put
        permno 2 (signal 2.0) on the boundary/high side instead."""
        engine = BacktestExecutor()
        engine.apply_signal_holding_period(_panel_with_one_delisted_stock(), _signal(), _CONFIG)
        portfolios = engine.form_portfolios(config=_CONFIG)

        port_of = dict(zip(portfolios["permno"], portfolios["portfolio"]))
        assert port_of[1] == 1
        assert port_of[2] == 1
        assert port_of[3] == 2
