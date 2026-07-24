"""Unit tests for formation-locked breakpoints/portfolio assignment (the
standard "form-once, hold-fixed" factor-replication convention, matching
Fama-French / Ken French Data Library / AQR-style construction).

`BacktestExecutor.apply_signal_holding_period` tags every expanded row with a
`cohort` column (the signal's original, pre-shift formation yyyymm).
`BacktestExecutor.compute_breakpoints`/`BacktestExecutor.assign_portfolios`
group/look up by that `cohort` instead of the
current `yyyymm`, so a stock's portfolio membership is computed ONCE from
its own formation cross-section and held fixed for its entire holding
period -- it is never re-derived from a later month's (possibly different)
cross-section.

Before this fix, breakpoints/assignment were re-derived fresh every current
month, which meant (a) a stock's portfolio membership could drift within its
own nominal holding period if the concurrent cross-section composition
changed (e.g. other cohorts entering/exiting, or a stock temporarily
dropping out due to missing returns), and (b) mixing multiple staggered
formation cohorts in the same current month could corrupt everyone's
breakpoints. See docs/decision-log.md for the full writeup.
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


def _msf(rows: list[tuple[int, int]]) -> pd.DataFrame:
    """rows: (permno, yyyymm) -> a returns-panel-shaped DataFrame (ret/me
    values are irrelevant to breakpoint/assignment mechanics, so kept simple)."""
    return pd.DataFrame(
        {
            "permno": [p for p, _ in rows],
            "yyyymm": [m for _, m in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
        }
    )


class TestFormationLockedAcrossCohorts:
    """Two staggered formation cohorts (very different signal scales) are
    concurrently held in some current months. Each cohort's breakpoints must
    come from ITS OWN formation cross-section only, never a pooled
    across-cohort cross-section for the current month."""

    def _signal(self) -> pd.DataFrame:
        return pd.DataFrame({
            "permno": [1, 2, 3, 4, 5, 6],
            # cohort 1 forms 200001 (signals 1..4); cohort 2 forms 200002
            # (signals 100/200, a completely different scale).
            "yyyymm": [200001, 200001, 200001, 200001, 200002, 200002],
            "signal": [1.0, 2.0, 3.0, 4.0, 100.0, 200.0],
        })

    def _panel(self) -> pd.DataFrame:
        # cohort 1 (permno 1-4) held 200002-200004; cohort 2 (permno 5-6)
        # held 200003-200005 -- 200003/200004 have BOTH cohorts concurrently
        # active.
        rows = [(p, m) for p in (1, 2, 3, 4) for m in (200002, 200003, 200004)]
        rows += [(p, m) for p in (5, 6) for m in (200003, 200004, 200005)]
        return _msf(rows)

    def test_breakpoints_are_keyed_by_cohort_not_current_month(self):
        merged = BacktestExecutor().apply_signal_holding_period(self._panel(), self._signal(), _CONFIG)
        bp = BacktestExecutor().compute_breakpoints(merged, _CONFIG)
        assert set(bp.index) == {200001, 200002}

    def test_cohort_1_portfolio_assignment_unaffected_by_cohort_2(self):
        merged = BacktestExecutor().apply_signal_holding_period(self._panel(), self._signal(), _CONFIG)
        bp = BacktestExecutor().compute_breakpoints(merged, _CONFIG)
        assigned = BacktestExecutor().assign_portfolios(merged, bp, _CONFIG)

        port_of = dict(zip(
            zip(assigned["permno"], assigned["yyyymm"]), assigned["portfolio"]
        ))
        # Cohort 1's own median split (signals 1,2,3,4 -> median 2.5):
        # permno 1,2 (low) -> portfolio 1; permno 3,4 (high) -> portfolio 2.
        # This must hold in EVERY held month, including 200003/200004 where
        # cohort 2 (signals 100/200) is also concurrently active -- if
        # breakpoints were pooled across cohorts for the current month, the
        # much larger cohort-2 values would corrupt cohort 1's split.
        for m in (200002, 200003, 200004):
            assert port_of[(1, m)] == 1
            assert port_of[(2, m)] == 1
            assert port_of[(3, m)] == 2
            assert port_of[(4, m)] == 2

    def test_portfolio_membership_constant_across_whole_holding_period(self):
        """The core form-once-hold-fixed guarantee: a stock's portfolio
        number never changes across the months it's held, regardless of
        which other stocks/cohorts are concurrently active."""
        merged = BacktestExecutor().apply_signal_holding_period(self._panel(), self._signal(), _CONFIG)
        bp = BacktestExecutor().compute_breakpoints(merged, _CONFIG)
        assigned = BacktestExecutor().assign_portfolios(merged, bp, _CONFIG)

        for permno in (1, 2, 3, 4, 5, 6):
            ports = assigned.loc[assigned["permno"] == permno, "portfolio"].unique()
            assert len(ports) == 1, f"permno {permno} changed portfolios across its holding period: {ports}"


class TestFormationLockedRobustToMidHoldingMissingData:
    """A stock missing its return for ONE month in the middle of its holding
    period must not corrupt its own cohort's breakpoints -- as long as at
    least one of its held months survives `apply_missing_policy`'s drop, the
    cohort-level `drop_duplicates(subset=["permno","cohort"])` in
    `compute_breakpoints` still picks up its (constant, formation-time)
    signal value."""

    def _signal(self) -> pd.DataFrame:
        return pd.DataFrame({
            "permno": [1, 2, 3],
            "yyyymm": [200001, 200001, 200001],
            "signal": [1.0, 2.0, 3.0],
        })

    def test_cohort_breakpoints_unaffected_by_a_stocks_missing_month(self):
        # permno 2 is simply ABSENT from yyyymm 200003 (simulating that its
        # return row was already dropped upstream by apply_missing_policy),
        # but present in 200002 and 200004.
        rows = [
            (1, 200002), (1, 200003), (1, 200004),
            (2, 200002),              (2, 200004),
            (3, 200002), (3, 200003), (3, 200004),
        ]
        panel = _msf(rows)
        merged = BacktestExecutor().apply_signal_holding_period(panel, self._signal(), _CONFIG)
        bp = BacktestExecutor().compute_breakpoints(merged, _CONFIG)
        assigned = BacktestExecutor().assign_portfolios(merged, bp, _CONFIG)

        # Cohort 200001's breakpoints must reflect all three stocks'
        # signals (1, 2, 3), not just whichever happened to survive a given
        # month -- median split -> permno 1 low, permno 2 mid->high leg,
        # permno 3 high (n=2 -> permno 1 = portfolio 1, permno 2 & 3 = 2).
        port_of_permno = dict(zip(assigned["permno"], assigned["portfolio"]))
        # (only need one row per permno since assignment is cohort-constant;
        # de-duplicate defensively in case of multiple held months)
        for permno, group in assigned.groupby("permno"):
            assert group["portfolio"].nunique() == 1
        assert port_of_permno[1] == 1
        assert port_of_permno[3] == 2
        # permno 2 present in 200002 and 200004 -- both months must agree
        p2_ports = assigned.loc[assigned["permno"] == 2, "portfolio"].unique()
        assert len(p2_ports) == 1
