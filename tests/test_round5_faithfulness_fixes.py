"""Regression tests for the 2026-07-28 fifth-pass faithfulness fixes:

1. Fail loud on a missing universe-filter field. A MethodSpec-stated universe
   restriction whose field is absent from the loaded panel must RAISE, not be
   silently skipped (silently skipping runs a different universe than stated
   while reporting success). Enforced at BOTH filter sites:
   `apply_universe_filters` (returns panel) and the formation-cross-section
   filter loop in `apply_signal_holding_period`.

2. Annual cohort vs. formation_month consistency. An annual-rebalanced strategy
   whose signal forms in a month other than the MethodSpec's EXPLICIT
   `formation_month` is a silent formation-calendar disagreement -> raise.
   Only annual + explicit formation_month is validated (quarterly/monthly
   cohort-month sets are convention-dependent; a defaulted formation_month is
   not authoritative over the signal's own cohorts).

3. Value-weighting excludes (not fabricates) missing prior-month ME. When
   `me_{t-1}` is unavailable for a held stock-month, that row is dropped from
   the VW average (weight 0) instead of falling back to same-month ME, and the
   missing fraction is surfaced as `vw_lagged_me_missing_frac`.

See docs/decision-log.md (2026-07-28 fifth-pass entry).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor


class TestFailLoudOnMissingFilterField:
    def _panel(self):
        return pd.DataFrame({
            "permno": [1, 2],
            "yyyymm": [200001, 200001],
            "ret": [0.01, 0.02],
            "me": [100.0, 100.0],
            "exchcd": [1, 1],
        })

    def test_apply_universe_filters_raises(self):
        with pytest.raises(ValueError, match="shrcd"):
            BacktestExecutor.apply_universe_filters(
                self._panel(), [{"field": "shrcd", "op": "in", "value": [10, 11]}]
            )

    def test_formation_filter_loop_raises(self):
        # The formation cross-section built inside apply_signal_holding_period
        # must apply the SAME fail-loud rule when a filter field is absent.
        # (filter_universe is skipped here so the formation loop is exercised
        # in isolation -- filter_universe would raise on the same field first.)
        signal = pd.DataFrame({"permno": [1, 2], "yyyymm": [200001, 200001], "signal": [1.0, 2.0]})
        panel = pd.DataFrame({
            "permno": [1, 2, 1, 2],
            "yyyymm": [200001, 200001, 200002, 200002],
            "ret": [0.0, 0.0, 0.01, 0.02],
            "me": [100.0, 100.0, 100.0, 100.0],
            "exchcd": [1, 1, 1, 1],
        })
        config = {
            "holding_period_months": 1,
            "universe_filters": [{"field": "shrcd", "op": "in", "value": [10, 11]}],
        }
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        with pytest.raises(ValueError, match="shrcd"):
            engine.apply_signal_holding_period(signal=signal, config=config)


class TestAnnualFormationMonthValidation:
    def _make(self, signal_month, *, freq="annual", explicit=True, formation_month=6):
        signal = pd.DataFrame({
            "permno": [1, 2],
            "yyyymm": [200000 + signal_month, 200000 + signal_month],
            "signal": [1.0, 2.0],
        })
        # Held months follow the cohort; keep them simple.
        cohort = 200000 + signal_month
        held = []
        for h in (1, 2):
            y, m = divmod(cohort, 100)
            m2 = m + h
            y += (m2 - 1) // 12
            m2 = (m2 - 1) % 12 + 1
            held.append(y * 100 + m2)
        rows = []
        for p in (1, 2):
            for ym in held:
                rows.append((p, ym))
        panel = pd.DataFrame({
            "permno": [r[0] for r in rows],
            "yyyymm": [r[1] for r in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
        })
        config = {
            "holding_period_months": 2,
            "rebalance_frequency": freq,
            "formation_month": formation_month,
            "formation_month_explicit": explicit,
        }
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        return engine, signal, config

    def test_matching_cohort_passes(self):
        engine, signal, config = self._make(6)  # June cohort, formation_month=6
        engine.apply_signal_holding_period(signal=signal, config=config)  # no raise

    def test_mismatched_cohort_resamples_to_explicit_formation_month(self):
        # March data availability is valid for a June annual formation under
        # the calendar-lag/as-of convention: the engine samples the latest
        # already-available signal as of the reviewed formation month instead
        # of treating the raw availability month as the portfolio cohort.
        signal = pd.DataFrame({"permno": [1, 2], "yyyymm": [200003, 200003], "signal": [1.0, 2.0]})
        panel = pd.DataFrame({
            "permno": [1, 2, 1, 2, 1, 2],
            "yyyymm": [200006, 200006, 200007, 200007, 200008, 200008],
            "ret": [0.01] * 6,
            "me": [100.0] * 6,
            "exchcd": [1] * 6,
        })
        config = {
            "holding_period_months": 2,
            "rebalance_frequency": "annual",
            "formation_month": 6,
            "formation_month_explicit": True,
            "signal_max_staleness_months": 11,
        }
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)

        merged = engine.apply_signal_holding_period(signal=signal, config=config)
        assert set(merged["cohort"]) == {200006}
        assert sorted(merged["yyyymm"].unique()) == [200007, 200008]

    def test_defaulted_formation_month_does_not_trigger(self):
        # formation_month present but NOT explicit -> signal cohorts are
        # authoritative, no validation.
        engine, signal, config = self._make(3, explicit=False)
        engine.apply_signal_holding_period(signal=signal, config=config)  # no raise

    def test_quarterly_not_validated(self):
        engine, signal, config = self._make(3, freq="quarterly")
        engine.apply_signal_holding_period(signal=signal, config=config)  # no raise


class TestVWExcludesMissingLaggedME:
    def test_missing_prior_month_me_excluded_and_reported(self):
        # Two stocks in one portfolio. Stock 1 has a formation-month (t-1) row
        # so me_lag resolves; stock 2 has NO formation-month row, so its me_lag
        # is NaN and it must be EXCLUDED from the VW average (not fall back to
        # same-month ME). With stock 2 dropped, the VW return == stock 1's own
        # return, and the missing fraction is reported.
        signal = pd.DataFrame({"permno": [1, 2], "yyyymm": [200001, 200001], "signal": [1.0, 1.0]})
        panel = pd.DataFrame({
            "permno": [1, 2, 1],  # stock 2 has NO 200001 formation-month row
            "yyyymm": [200001, 200002, 200002],
            "ret": [0.0, -0.5, 0.10],
            "me": [100.0, 100.0, 100.0],
            "exchcd": [1, 1, 1],
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

        val = rets.loc[rets["yyyymm"] == 200002, "ret"].iloc[0]
        # Stock 2 excluded (NaN me_lag) -> VW return is stock 1's own +10%.
        assert abs(val - 0.10) < 1e-12
        assert engine._vw_lag_me_missing_frac is not None
        assert engine._vw_lag_me_missing_frac > 0.0

    def test_ew_reports_none_missing_frac(self):
        signal = pd.DataFrame({"permno": [1], "yyyymm": [200001], "signal": [1.0]})
        panel = pd.DataFrame({
            "permno": [1, 1],
            "yyyymm": [200001, 200002],
            "ret": [0.0, 0.05],
            "me": [100.0, 100.0],
            "exchcd": [1, 1],
        })
        config = {"holding_period_months": 1, "breakpoint_quantiles": 1, "weighting_rule": "ew"}
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)
        engine.portfolios = engine.merged.copy()
        engine.portfolios["portfolio"] = 1
        engine.compute_portfolio_returns(config=config)
        assert engine._vw_lag_me_missing_frac is None
