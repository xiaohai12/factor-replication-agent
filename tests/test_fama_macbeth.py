"""Unit tests for `steps.compute_fama_macbeth` (plan.md Phase 7): the
Fama-MacBeth cross-sectional regression estimator via `linearmodels`. Uses a
synthetic balanced panel constructed as `ret = intercept + slope*signal`
(zero noise, same cross-sectional slope every period) so the FM average
slope recovers the exact value -- a hand-checkable, deterministic test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

linearmodels = pytest.importorskip("linearmodels")

from src.infra.backtest_engine import steps  # noqa: E402


def _panel(n_periods=12, n_firms=20, intercept=0.01, slope=0.5) -> pd.DataFrame:
    rows = []
    for t in range(n_periods):
        yyyymm = 200001 + t
        for i in range(n_firms):
            permno = i + 1
            signal = (i - n_firms / 2) / 10.0  # deterministic cross-sectional spread
            ret = intercept + slope * signal
            rows.append({"permno": permno, "yyyymm": yyyymm, "signal": signal, "ret": ret})
    return pd.DataFrame(rows)


class TestComputeFamaMacbethExactRecovery:
    def test_recovers_known_intercept_and_slope(self):
        merged = _panel(intercept=0.01, slope=0.5)
        result = steps.compute_fama_macbeth(merged, config={})
        assert result["fm_intercept"] == pytest.approx(0.01, abs=1e-9)
        assert result["fm_slope"] == pytest.approx(0.5, abs=1e-9)
        assert result["fm_n_periods"] == 12

    def test_negative_slope_recovered(self):
        merged = _panel(intercept=0.0, slope=-0.3)
        result = steps.compute_fama_macbeth(merged, config={})
        assert result["fm_slope"] == pytest.approx(-0.3, abs=1e-9)

    def test_zero_slope_gives_near_zero_slope_estimate(self):
        # Note: a literally zero-variance `ret` (zero slope + zero noise)
        # makes linearmodels' internal R^2 computation divide by zero (an
        # LinearModels edge case, not something compute_fama_macbeth needs to
        # guard against for real return data, which always has some
        # cross-sectional variance) -- add tiny deterministic per-firm noise
        # so `ret` has nonzero variance while keeping the true slope at 0.
        merged = _panel(intercept=0.02, slope=0.0)
        rng = np.random.default_rng(7)
        merged["ret"] = merged["ret"] + rng.normal(0, 1e-4, len(merged))
        result = steps.compute_fama_macbeth(merged, config={})
        assert result["fm_slope"] == pytest.approx(0.0, abs=1e-3)


class TestComputeFamaMacbethWinsorization:
    def test_winsorize_signal_pct_clips_extremes(self):
        merged = _panel(n_firms=20, intercept=0.0, slope=1.0)
        # inject one extreme outlier permno's signal to a huge value while
        # keeping ret consistent with the ORIGINAL (unclipped) signal so a
        # winsorized run's recovered slope differs from an unwinsorized run.
        merged.loc[merged["permno"] == 1, "signal"] = 100.0
        plain = steps.compute_fama_macbeth(merged.copy(), config={})
        winsorized = steps.compute_fama_macbeth(merged.copy(), config={"winsorize_signal_pct": 0.05})
        assert plain["fm_slope"] != pytest.approx(winsorized["fm_slope"])


class TestComputeFamaMacbethDropsMissing:
    def test_drops_rows_with_missing_signal_or_ret(self):
        merged = _panel()
        merged.loc[0, "signal"] = None
        result = steps.compute_fama_macbeth(merged, config={})
        assert result["fm_slope"] == pytest.approx(0.5, abs=1e-6)
