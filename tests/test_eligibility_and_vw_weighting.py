"""Regression tests for the 2026-07-28 fourth-pass fixes:

1. Formation universe-eligibility exclusion must propagate to the ACTUAL
   portfolio-assignment/return population (`self.merged`), not only to the
   breakpoint population (`self.formation`). Otherwise a stock excluded from
   DEFINING the breakpoints is still sorted BY those breakpoints and
   contributes returns -- a self-inconsistent state.

2. Value-weighting must use PRIOR-month market equity (`me_{t-1}`), not the
   same month `t` whose return is being weighted (same-month end-of-month
   market cap already reflects that return -- a subtle look-ahead).

See docs/decision-log.md (2026-07-28 fourth-pass entry).
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor


class TestEligibilityPropagatesToAssignment:
    """A stock ineligible at its own formation month must be excluded from
    BOTH the breakpoint population AND the assigned/returning population,
    even if it 'recovers' eligibility (and has valid returns) in later held
    months."""

    def _run(self):
        signal = pd.DataFrame({
            "permno": [1, 2, 3, 4],
            "yyyymm": [200001] * 4,
            "signal": [1.0, 2.0, 3.0, 4.0],
        })
        rows = []
        for p in (1, 2, 3):
            for m in (200001, 200002, 200003, 200004):
                rows.append((p, m, 10))
        # permno 4: ineligible (shrcd=99) AT ITS FORMATION MONTH (200001),
        # but shrcd recovers to 10 in every held month (and it has valid
        # returns throughout).
        rows.append((4, 200001, 99))
        for m in (200002, 200003, 200004):
            rows.append((4, m, 10))
        panel = pd.DataFrame({
            "permno": [r[0] for r in rows],
            "yyyymm": [r[1] for r in rows],
            "shrcd": [r[2] for r in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
        })
        config = {
            "holding_period_months": 3,
            "breakpoint_quantiles": 2,
            "breakpoint_source": "full_sample",
            "weighting_rule": "ew",
            "universe_filters": [{"field": "shrcd", "op": "in", "value": [10, 11]}],
        }
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)
        assigned = engine.form_portfolios(config=config)
        return engine, assigned

    def test_excluded_from_formation_and_merged_and_assignment(self):
        engine, assigned = self._run()
        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3]
        assert sorted(engine.merged["permno"].unique()) == [1, 2, 3]
        assert sorted(assigned["permno"].unique()) == [1, 2, 3]

    def test_ineligible_stock_contributes_no_returns(self):
        engine, assigned = self._run()
        engine.compute_portfolio_returns(config=engine.config or {
            "weighting_rule": "ew", "breakpoint_quantiles": 2,
        })
        # permno 4 never appears in the assigned population, so it can't be in
        # any (yyyymm, portfolio) group's return -- covered by the assignment
        # assertion above; this just double-checks the pipeline runs clean.
        assert 4 not in set(assigned["permno"].unique())


class TestValueWeightingUsesPriorMonthME:
    """VW must weight month-t returns by prior-month-end market equity, not
    same-month-end (which already reflects the return being weighted)."""

    def test_prior_month_equal_weights_net_to_zero(self):
        # Two stocks, equal caps at formation (t-1), returns +10%/-10% in the
        # held month t; same-month me reflects the return (110 vs 90).
        signal = pd.DataFrame({"permno": [1, 2], "yyyymm": [200001, 200001], "signal": [1.0, 1.0]})
        panel = pd.DataFrame({
            "permno": [1, 2, 1, 2],
            "yyyymm": [200001, 200001, 200002, 200002],
            "ret": [0.0, 0.0, 0.10, -0.10],
            "me": [100.0, 100.0, 110.0, 90.0],  # same-month me AFTER the return
            "exchcd": [1, 1, 1, 1],
        })
        config = {"holding_period_months": 1, "breakpoint_quantiles": 1, "weighting_rule": "vw"}
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)
        # Put both stocks in one portfolio.
        engine.portfolios = engine.merged.copy()
        engine.portfolios["portfolio"] = 1
        rets = engine.compute_portfolio_returns(config=config)

        val = rets.loc[rets["yyyymm"] == 200002, "ret"].iloc[0]
        # Prior-month (formation) caps are equal (100/100) -> 0.5*10% + 0.5*(-10%) = 0.
        # The buggy same-month weighting (110/90) would give +1%.
        assert abs(val - 0.0) < 1e-12

    def test_single_stock_portfolio_vw_equals_own_return(self):
        # A single-stock portfolio's VW return is its own return regardless of
        # ME timing -- this is why the single-stock-per-decile golden e2e
        # tests are unaffected by the lagged-ME change.
        signal = pd.DataFrame({"permno": [1], "yyyymm": [200001], "signal": [1.0]})
        panel = pd.DataFrame({
            "permno": [1, 1],
            "yyyymm": [200001, 200002],
            "ret": [0.0, 0.07],
            "me": [100.0, 107.0],
            "exchcd": [1, 1],
        })
        config = {"holding_period_months": 1, "breakpoint_quantiles": 1, "weighting_rule": "vw"}
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)
        engine.portfolios = engine.merged.copy()
        engine.portfolios["portfolio"] = 1
        rets = engine.compute_portfolio_returns(config=config)

        assert rets.loc[rets["yyyymm"] == 200002, "ret"].iloc[0] == 0.07
