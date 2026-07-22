"""Unit tests for the deterministic ResearchDesign steps added in plan.md
Phase 2.5: universe filter DSL, delisting-return handling, and the
neutralization scaffold. These are pure functions in
`src/infra/backtest_engine/steps.py`, tested directly (no MethodSpec/plugin needed).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.backtest_engine import steps


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


class TestFilterUniverseBaseline:
    def test_baseline_screen_unchanged_when_no_extra_filters(self):
        df = _msf_df()
        out = steps.filter_universe(df, config={})
        # baseline: shrcd in (10,11) & exchcd in (1,2,3) & not financial siccd
        assert set(out["permno"]) == {1, 2, 4}


class TestApplyUniverseFiltersDSL:
    def test_eq_filter(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [{"field": "exchcd", "op": "eq", "value": 1}])
        assert set(out["permno"]) == {1, 2}

    def test_in_filter(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [{"field": "exchcd", "op": "in", "value": [1, 2]}])
        assert set(out["permno"]) == {1, 2, 3}

    def test_between_filter(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [{"field": "me", "op": "between", "value": [10, 60]}])
        assert set(out["permno"]) == {2, 3}

    def test_gte_filter(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [{"field": "me", "op": "gte", "value": 50}])
        assert set(out["permno"]) == {1, 2}

    def test_unknown_field_is_skipped_not_raised(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [{"field": "not_a_column", "op": "eq", "value": 1}])
        assert len(out) == len(df)

    def test_empty_filters_is_noop(self):
        df = _msf_df()
        out = steps.apply_universe_filters(df, [])
        assert len(out) == len(df)

    def test_filter_universe_layers_dsl_on_top_of_baseline(self):
        df = _msf_df()
        config = {"universe_filters": [{"field": "me", "op": "gte", "value": 50}]}
        out = steps.filter_universe(df, config)
        # baseline keeps {1, 2, 4}; DSL me>=50 further restricts to {1, 2}
        assert set(out["permno"]) == {1, 2}


class TestApplyDelistingReturns:
    def test_noop_when_no_dlret_column(self):
        df = _msf_df()
        out = steps.apply_delisting_returns(df, config={})
        pd.testing.assert_frame_equal(out, df)

    def test_noop_when_disabled_via_config(self):
        df = _msf_df()
        df["dlret"] = [None, None, -0.3, None]
        out = steps.apply_delisting_returns(df, config={"apply_delisting_returns": False})
        pd.testing.assert_series_equal(out["ret"], df["ret"])

    def test_combines_ret_and_dlret_for_delisted_rows(self):
        df = _msf_df()
        df["dlret"] = [None, None, -0.3, None]
        out = steps.apply_delisting_returns(df, config={})
        expected_row3 = (1 + 0.03) * (1 + -0.3) - 1
        assert out.loc[out["permno"] == 3, "ret"].iloc[0] == pytest.approx(expected_row3)
        # untouched rows keep their original return
        assert out.loc[out["permno"] == 1, "ret"].iloc[0] == pytest.approx(0.01)


class TestNeutralizeSignalScaffold:
    def test_default_none_is_identity(self):
        df = _msf_df()
        out = steps.neutralize_signal(df, config={})
        pd.testing.assert_frame_equal(out, df)

    def test_non_none_without_hook_raises(self):
        df = _msf_df()
        with pytest.raises(NotImplementedError):
            steps.neutralize_signal(df, config={"neutralization": "industry_adjust"})


class TestMicrocapExclude:
    def test_disabled_by_default(self):
        df = _msf_df()
        out = steps.filter_universe(df, config={})
        assert set(out["permno"]) == {1, 2, 4}

    def test_excludes_below_nyse_p20_when_enabled(self):
        df = _msf_df()
        # NYSE (exchcd==1) MEs are 100, 50 -> 20th pct is closer to 50 (low sample size)
        out = steps.filter_universe(df, config={"microcap_exclude": True})
        assert 4 not in set(out["permno"])  # me=5, smallest, should be excluded
