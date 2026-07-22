"""Unit tests for the multi-dimensional (double) sort added in plan.md
Phase 3: `steps.compute_breakpoints_multi` / `assign_portfolios_multi` /
`compute_returns_multi` / `compute_long_short_multi`, plus
`registry.resolve_sort_dims`'s characteristic x size mapping.

Uses a small hand-built panel where the expected 2x2 independent sort
breakpoints/assignments/returns can be verified by hand.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.models.method_spec import MethodSpec, SignalSpec, SortLegSpec
from src.infra.backtest_engine import steps
from src.steps.step3_codegen.registry import resolve_sort_dims


def _two_by_two_panel() -> pd.DataFrame:
    """8 stocks, one month, NYSE-listed (exchcd=1) so breakpoints use the
    full set. `me` (size) and `signal` (characteristic) are independent
    rank orderings so a 2x2 independent sort has a clean, hand-checkable
    split: me median splits {A,B,C,D} (small) vs {E,F,G,H} (big); signal
    median splits {A,C,E,G} (low) vs {B,D,F,H} (high)."""
    return pd.DataFrame({
        "permno":  [1, 2, 3, 4, 5, 6, 7, 8],
        "yyyymm":  [200001] * 8,
        "exchcd":  [1] * 8,
        "shrcd":   [10] * 8,
        "ret":     [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08],
        "me":      [10, 11, 12, 13, 90, 91, 92, 93],       # small: 1-4, big: 5-8
        "signal":  [1, 5, 2, 6, 3, 7, 4, 8],                # low: permno 1,3,5,7 high: 2,4,6,8
    })


_SORT_DIMS_2X2 = [
    {"variable": "size", "column": "me", "quantiles": 2, "source": "nyse", "independent": True},
    {"variable": "characteristic", "column": "signal", "quantiles": 2, "source": "nyse", "independent": True},
]


class TestComputeBreakpointsMulti:
    def test_returns_sort_dims_unchanged(self):
        config = {"sort_dims": _SORT_DIMS_2X2}
        out = steps.compute_breakpoints_multi(pd.DataFrame(), config)
        assert out == _SORT_DIMS_2X2

    def test_empty_when_no_sort_dims(self):
        assert steps.compute_breakpoints_multi(pd.DataFrame(), {}) == []


class TestAssignPortfoliosMultiIndependent:
    def test_assigns_expected_2x2_buckets(self):
        df = _two_by_two_panel()
        bps = steps.compute_breakpoints_multi(df, {"sort_dims": _SORT_DIMS_2X2})
        out = steps.assign_portfolios_multi(df, bps, {})
        by_permno = out.set_index("permno")
        # dim0 = size: permno 1-4 small (bucket 1), 5-8 big (bucket 2)
        assert list(by_permno.loc[[1, 2, 3, 4], "portfolio_0"]) == [1, 1, 1, 1]
        assert list(by_permno.loc[[5, 6, 7, 8], "portfolio_0"]) == [2, 2, 2, 2]
        # dim1 = signal: permno 1,3,5,7 low (bucket 1); 2,4,6,8 high (bucket 2)
        assert by_permno.loc[1, "portfolio_1"] == 1
        assert by_permno.loc[2, "portfolio_1"] == 2

    def test_empty_dims_returns_empty(self):
        df = _two_by_two_panel()
        out = steps.assign_portfolios_multi(df, [], {})
        assert out.empty


class TestComputeReturnsMulti:
    def test_equal_weighted_cell_means(self):
        df = _two_by_two_panel()
        bps = steps.compute_breakpoints_multi(df, {"sort_dims": _SORT_DIMS_2X2})
        assigned = steps.assign_portfolios_multi(df, bps, {})
        rets = steps.compute_returns_multi(assigned, {"weighting_rule": "ew"})
        cell = rets[(rets["portfolio_0"] == 1) & (rets["portfolio_1"] == 1)]
        # small+low bucket = permno 1 (ret 0.01), 3 (ret 0.03) -> mean 0.02
        assert cell["ret"].iloc[0] == pytest.approx(0.02)


class TestComputeLongShortMulti:
    def test_averages_signal_spread_across_size_groups(self):
        df = _two_by_two_panel()
        config = {"sort_dims": _SORT_DIMS_2X2, "weighting_rule": "ew", "long_leg": "low"}
        bps = steps.compute_breakpoints_multi(df, config)
        assigned = steps.assign_portfolios_multi(df, bps, config)
        rets = steps.compute_returns_multi(assigned, config)
        ls = steps.compute_long_short_multi(rets, config)
        # small group: low(1,3)=0.02 mean, high(2,4)=0.03 mean -> spread(low-high)=-0.01
        # big group: low(5,7)=0.06 mean, high(6,8)=0.07 mean -> spread(low-high)=-0.01
        # average of the two = -0.01
        assert ls["ls_return"].iloc[0] == pytest.approx(-0.01)


class TestResolveSortDims:
    def _spec_with_sorts(self, sorts) -> MethodSpec:
        spec = MethodSpec(factor_id="t", factor_name="T", signal=SignalSpec())
        spec.reported_results.return_calculation.portfolio_return.sorts = sorts
        return spec

    def test_characteristic_and_size_resolves(self):
        spec = self._spec_with_sorts([
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
        ])
        dims = resolve_sort_dims(spec)
        assert dims is not None
        assert [d["column"] for d in dims] == ["me", "signal"]

    def test_neither_size_returns_none(self):
        spec = self._spec_with_sorts([
            SortLegSpec(variable="book_to_market"),
            SortLegSpec(variable="momentum"),
        ])
        assert resolve_sort_dims(spec) is None

    def test_both_size_returns_none(self):
        spec = self._spec_with_sorts([
            SortLegSpec(variable="size"),
            SortLegSpec(variable="market_equity"),
        ])
        assert resolve_sort_dims(spec) is None

    def test_three_dims_returns_none(self):
        spec = self._spec_with_sorts([
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
            SortLegSpec(variable="momentum"),
        ])
        assert resolve_sort_dims(spec) is None

    def test_single_sort_returns_none(self):
        spec = self._spec_with_sorts([SortLegSpec(variable="asset_growth")])
        assert resolve_sort_dims(spec) is None
