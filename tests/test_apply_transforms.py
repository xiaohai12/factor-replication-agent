"""Unit tests for `BacktestExecutor.apply_transforms` -- the engine's single
consumer of `config["transforms"]` (`PortfolioSpec.transforms`, resolved by
`src/steps/step3_codegen/registry.py`'s `_build_config_from_resolved`).

Bug context: `transforms` was a real resolved-spec field (documented in
`src/infra/models/schema_reference.py`) that was extracted/resolved but never
consumed anywhere downstream -- `KNOWN_CONFIG_KEYS` had no `transforms` entry
so `build_config()` silently dropped it, and the engine had no winsorize
code path at all. Five separate extraction attempts for the Dichev 1998
oscore factor declared a `{"kind": "winsorize", "stage": "after_signal",
"bounds": [0.01, 0.99]}` transform that was never applied, letting extreme
un-clipped outliers distort the backtest. These tests cover the fix: the
transform is applied centrally in `BacktestExecutor`, per calendar month,
and any transform the engine doesn't support is never silently dropped.
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor


def _signal_df() -> pd.DataFrame:
    # Two months, 10 observations each, one obvious outlier per month.
    return pd.DataFrame({
        "permno": list(range(1, 11)) + list(range(1, 11)),
        "yyyymm": [200001] * 10 + [200002] * 10,
        "signal": (
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 1000.0]
            + [-500.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
        ),
    })


class TestApplyTransformsWinsorize:
    def test_clips_extreme_values_per_month(self):
        df = _signal_df()
        config = {
            "transforms": [
                {"kind": "winsorize", "stage": "after_signal", "bounds": [0.01, 0.99]}
            ]
        }
        out = BacktestExecutor().apply_transforms(df, config)

        # The extreme 1000.0 in month 1 must have been clipped down.
        jan = out[out["yyyymm"] == 200001]
        assert jan["signal"].max() < 1000.0
        # The extreme -500.0 in month 2 must have been clipped up.
        feb = out[out["yyyymm"] == 200002]
        assert feb["signal"].min() > -500.0

    def test_values_inside_bounds_untouched(self):
        df = _signal_df()
        config = {
            "transforms": [
                {"kind": "winsorize", "stage": "after_signal", "bounds": [0.01, 0.99]}
            ]
        }
        out = BacktestExecutor().apply_transforms(df, config)
        jan = out[out["yyyymm"] == 200001].sort_values("permno")
        # Middle values (2..8) are far from the 1st/99th percentile of a
        # 10-obs sample and should pass through unchanged.
        original_mid = df[(df["yyyymm"] == 200001) & (df["permno"].isin(range(2, 9)))].sort_values("permno")
        clipped_mid = jan[jan["permno"].isin(range(2, 9))]
        pd.testing.assert_series_equal(
            original_mid["signal"].reset_index(drop=True),
            clipped_mid["signal"].reset_index(drop=True),
        )

    def test_months_get_independently_computed_bounds(self):
        """A single global clip would clip based on the whole panel's
        quantiles; per-month clipping must use each month's own
        cross-section. Construct two months with very different scales and
        confirm each month's own outlier gets clipped relative to ITS OWN
        month, not the other month's scale."""
        df = pd.DataFrame({
            "permno": list(range(1, 6)) + list(range(1, 6)),
            "yyyymm": [200001] * 5 + [200002] * 5,
            # Month 1: small-scale signal, month 2: large-scale signal.
            "signal": [1.0, 2.0, 3.0, 4.0, 500.0] + [1000.0, 2000.0, 3000.0, 4000.0, 500000.0],
        })
        config = {
            "transforms": [
                {"kind": "winsorize", "stage": "after_signal", "bounds": [0.0, 0.8]}
            ]
        }
        out = BacktestExecutor().apply_transforms(df, config)
        jan_clipped_max = out[out["yyyymm"] == 200001]["signal"].max()
        feb_clipped_max = out[out["yyyymm"] == 200002]["signal"].max()
        # Each month's clip ceiling should be close to that month's own
        # 80th-percentile value (4.0 for Jan, 4000.0 for Feb), not smeared
        # across months.
        assert jan_clipped_max < 500.0
        assert feb_clipped_max < 500000.0
        assert feb_clipped_max > jan_clipped_max * 100  # scales stayed distinct per month

    def test_empty_transforms_is_noop(self):
        df = _signal_df()
        out = BacktestExecutor().apply_transforms(df, config={"transforms": []})
        pd.testing.assert_frame_equal(out, df)

    def test_missing_transforms_key_is_noop(self):
        df = _signal_df()
        out = BacktestExecutor().apply_transforms(df, config={})
        pd.testing.assert_frame_equal(out, df)


class TestApplyTransformsUnsupportedKindOrStage:
    def test_non_after_signal_stage_not_applied(self):
        df = _signal_df()
        config = {
            "transforms": [
                {"kind": "winsorize", "stage": "before_signal", "bounds": [0.01, 0.99]}
            ]
        }
        out = BacktestExecutor().apply_transforms(df, config)
        pd.testing.assert_frame_equal(out, df)

    def test_non_winsorize_kind_not_applied(self):
        df = _signal_df()
        config = {
            "transforms": [
                {"kind": "truncate", "stage": "after_signal", "bounds": [0.01, 0.99]}
            ]
        }
        out = BacktestExecutor().apply_transforms(df, config)
        pd.testing.assert_frame_equal(out, df)
