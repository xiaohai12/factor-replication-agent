"""Unit tests for the overlapping-cohort holding model added in plan.md
Phase 5: `steps.merge_signal_overlap` / `compute_breakpoints_overlap` /
`assign_portfolios_overlap` / `compute_returns_overlap` /
`compute_long_short_overlap`.

Uses a small hand-built scenario with 2 stocks, 3 formation cohorts (months
200001-200003, each held for 3 months), where cohort 200002's signal ranking
is deliberately SWAPPED relative to cohorts 200001/200003 -- so months with
multiple simultaneously-active cohorts (e.g. 200004, with all three cohorts
open) genuinely exercise per-cohort breakpoints/assignment and averaging
across DIFFERING cohort compositions, not just repeated identical values.
Every expected `ls_return` below is hand-computed in the test docstring.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.steps.step5_engine import steps


def _signal() -> pd.DataFrame:
    return pd.DataFrame({
        "permno": [1, 2, 1, 2, 1, 2],
        "yyyymm": [200001, 200001, 200002, 200002, 200003, 200003],
        # cohort 200002 is swapped: permno 1 becomes the HIGH-signal stock.
        "signal": [1, 2, 2, 1, 1, 2],
    })


def _msf() -> pd.DataFrame:
    rets = {
        (1, 200002): 0.02, (2, 200002): 0.01,
        (1, 200003): 0.03, (2, 200003): 0.01,
        (1, 200004): 0.05, (2, 200004): 0.02,
        (1, 200005): 0.04, (2, 200005): 0.02,
        (1, 200006): 0.06, (2, 200006): 0.01,
    }
    rows = [
        {"permno": p, "yyyymm": m, "ret": r, "me": 1.0, "exchcd": 1}
        for (p, m), r in rets.items()
    ]
    return pd.DataFrame(rows)


_CONFIG = {
    "holding_period_months": 3,
    "skip_month": 0,
    "breakpoint_quantiles": 2,
    "breakpoint_source": "full_sample",
    "weighting_rule": "ew",
    "long_leg": "low",
}


def _run_overlap_chain() -> pd.DataFrame:
    msf = _msf()
    signal = _signal()
    merged = steps.merge_signal_overlap(msf, signal, _CONFIG)
    bps = steps.compute_breakpoints_overlap(merged, _CONFIG)
    assigned = steps.assign_portfolios_overlap(merged, bps, _CONFIG)
    rets = steps.compute_returns_overlap(assigned, _CONFIG)
    return steps.compute_long_short_overlap(rets, _CONFIG)


class TestMergeSignalOverlap:
    def test_produces_one_row_per_permno_current_month_cohort(self):
        merged = steps.merge_signal_overlap(_msf(), _signal(), _CONFIG)
        # cohort 200001 holds 200002-200004; cohort 200002 holds 200003-200005;
        # cohort 200003 holds 200004-200006. permno 1's row at yyyymm=200004
        # should appear once per active cohort (200001, 200002, 200003) = 3x.
        rows = merged[(merged["permno"] == 1) & (merged["yyyymm"] == 200004)]
        assert len(rows) == 3
        assert set(rows["cohort"]) == {200001, 200002, 200003}

    def test_respects_skip_month(self):
        config = dict(_CONFIG, skip_month=1)
        merged = steps.merge_signal_overlap(_msf(), _signal(), config)
        # cohort 200001 with skip=1 now holds 200003-200005, not 200002
        cohort1_months = set(merged[merged["cohort"] == 200001]["yyyymm"])
        assert 200002 not in cohort1_months
        assert cohort1_months == {200003, 200004, 200005}


class TestOverlappingHoldingEndToEnd:
    """Hand-computed expected ls_return per month -- see module docstring."""

    def test_month_200002_single_cohort(self):
        ls = _run_overlap_chain()
        row = ls[ls["yyyymm"] == 200002]
        assert row["ls_return"].iloc[0] == pytest.approx(0.01)

    def test_month_200003_two_cohorts_offsetting(self):
        ls = _run_overlap_chain()
        row = ls[ls["yyyymm"] == 200003]
        assert row["ls_return"].iloc[0] == pytest.approx(0.0)

    def test_month_200004_three_cohorts(self):
        ls = _run_overlap_chain()
        row = ls[ls["yyyymm"] == 200004]
        assert row["ls_return"].iloc[0] == pytest.approx(0.01)

    def test_month_200005_two_cohorts(self):
        ls = _run_overlap_chain()
        row = ls[ls["yyyymm"] == 200005]
        assert row["ls_return"].iloc[0] == pytest.approx(0.0)

    def test_month_200006_single_cohort(self):
        ls = _run_overlap_chain()
        row = ls[ls["yyyymm"] == 200006]
        assert row["ls_return"].iloc[0] == pytest.approx(0.05)

    def test_all_six_months_present(self):
        ls = _run_overlap_chain()
        assert sorted(ls["yyyymm"].tolist()) == [200002, 200003, 200004, 200005, 200006]
