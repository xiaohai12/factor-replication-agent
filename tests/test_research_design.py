"""Unit tests for the deterministic ResearchDesign steps added in plan.md
Phase 2.5: universe filter DSL and delisting-return handling. These are
methods on `BacktestExecutor` in `src/infra/backtest_engine/__init__.py`,
tested directly (no MethodSpec/plugin needed).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import BacktestExecutor


def _msf_df() -> pd.DataFrame:
    return pd.DataFrame({
        "permno": [1, 2, 3, 4],
        "yyyymm": [200001, 200001, 200001, 200001],
        "shrcd": [10, 11, 10, 10],
        "exchcd": [1, 1, 2, 3],
        "siccd": [2000, 2000, 6500, 2000],
        "ret": [0.01, 0.02, 0.03, 0.04],
        "me": [100.0, 50.0, 10.0, 5.0],
    })


class TestFilterUniverseNoBaseline:
    def test_noop_when_no_universe_filters_configured(self):
        """filter_universe no longer applies any hardcoded CRSP-shaped
        (shrcd/exchcd/siccd) screen -- that assumption doesn't hold for a
        non-CRSP returns_universe. With no `universe_filters` configured, it
        is a pure no-op; the paper's actual universe restriction (including
        the common "ordinary common shares, NYSE/AMEX/NASDAQ, ex-financials"
        boilerplate) is expected to come from the MethodSpec's
        `universe_filters`, extracted from the paper like any other
        restriction."""
        df = _msf_df()
        out = BacktestExecutor().filter_universe(df, config={})
        assert set(out["permno"]) == {1, 2, 3, 4}


class TestApplyUniverseFiltersDSL:
    def test_eq_filter(self):
        df = _msf_df()
        out = BacktestExecutor.apply_universe_filters(df, [{"field": "exchcd", "op": "eq", "value": 1}])
        assert set(out["permno"]) == {1, 2}

    def test_in_filter(self):
        df = _msf_df()
        out = BacktestExecutor.apply_universe_filters(df, [{"field": "exchcd", "op": "in", "value": [1, 2]}])
        assert set(out["permno"]) == {1, 2, 3}

    def test_between_filter(self):
        df = _msf_df()
        out = BacktestExecutor.apply_universe_filters(df, [{"field": "me", "op": "between", "value": [10, 60]}])
        assert set(out["permno"]) == {2, 3}

    def test_gte_filter(self):
        df = _msf_df()
        out = BacktestExecutor.apply_universe_filters(df, [{"field": "me", "op": "gte", "value": 50}])
        assert set(out["permno"]) == {1, 2}

    def test_unknown_field_raises_not_skipped(self):
        # Fail loud: a MethodSpec-stated universe filter whose field is absent
        # from the panel must NOT be silently ignored (that would run a
        # different universe than stated while reporting success).
        df = _msf_df()
        with pytest.raises(ValueError, match="not_a_column"):
            BacktestExecutor.apply_universe_filters(df, [{"field": "not_a_column", "op": "eq", "value": 1}])

    def test_empty_filters_is_noop(self):
        df = _msf_df()
        out = BacktestExecutor.apply_universe_filters(df, [])
        assert len(out) == len(df)

    def test_filter_universe_applies_configured_universe_filters(self):
        df = _msf_df()
        config = {"universe_filters": [{"field": "me", "op": "gte", "value": 50}]}
        out = BacktestExecutor().filter_universe(df, config)
        # no baseline anymore -- me>=50 alone restricts {1,2,3,4} to {1,2}
        assert set(out["permno"]) == {1, 2}


class TestApplyDelistingReturns:
    def test_noop_when_no_dlret_column(self):
        df = _msf_df()
        out = BacktestExecutor().apply_delisting_returns(df, config={})
        pd.testing.assert_frame_equal(out, df)

    def test_noop_when_disabled_via_config(self):
        df = _msf_df()
        df["dlret"] = [None, None, -0.3, None]
        out = BacktestExecutor().apply_delisting_returns(df, config={"apply_delisting_returns": False})
        pd.testing.assert_series_equal(out["ret"], df["ret"])

    def test_combines_ret_and_dlret_for_delisted_rows(self):
        df = _msf_df()
        df["dlret"] = [None, None, -0.3, None]
        out = BacktestExecutor().apply_delisting_returns(df, config={})
        expected_row3 = (1 + 0.03) * (1 + -0.3) - 1
        assert out.loc[out["permno"] == 3, "ret"].iloc[0] == pytest.approx(expected_row3)
        # untouched rows keep their original return
        assert out.loc[out["permno"] == 1, "ret"].iloc[0] == pytest.approx(0.01)
