"""Unit tests for `steps.compute_factor_alphas` (plan.md Phase 2): CAPM/FF3/
FF5 alpha regressions via `statsmodels`. Uses a synthetic return series
constructed as `ls_return = alpha + beta*mktrf` (zero noise) so OLS recovers
the exact alpha/beta -- a hand-checkable, network-free correctness test
(the real Ken French fetch lives in scripts/fetch_ff_factors.py and is
exercised manually/at build time, not in this test suite).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.steps.step5_engine import steps

statsmodels = pytest.importorskip("statsmodels")


def _factors(n=36) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    yyyymm = [200001 + (i // 12) * 100 + (i % 12) for i in range(n)]
    return pd.DataFrame({
        "yyyymm": yyyymm,
        "mktrf": rng.normal(0.01, 0.04, n),
        "smb": rng.normal(0.0, 0.02, n),
        "hml": rng.normal(0.0, 0.02, n),
        "rmw": rng.normal(0.0, 0.015, n),
        "cma": rng.normal(0.0, 0.015, n),
    })


class TestComputeFactorAlphasCAPM:
    def test_recovers_known_alpha_and_beta_exactly(self):
        factors = _factors()
        true_alpha, true_beta = 0.005, 1.2
        ls = pd.DataFrame({
            "yyyymm": factors["yyyymm"],
            "ls_return": true_alpha + true_beta * factors["mktrf"],
        })
        result = steps.compute_factor_alphas(ls, factors, config={})
        assert result["alpha_capm"] == pytest.approx(true_alpha, abs=1e-9)
        assert result["beta_capm_mktrf"] == pytest.approx(true_beta, abs=1e-9)

    def test_zero_alpha_recovered_as_zero(self):
        factors = _factors()
        ls = pd.DataFrame({
            "yyyymm": factors["yyyymm"],
            "ls_return": 0.8 * factors["mktrf"],
        })
        result = steps.compute_factor_alphas(ls, factors, config={})
        assert result["alpha_capm"] == pytest.approx(0.0, abs=1e-9)


class TestComputeFactorAlphasFF3AndFF5:
    def test_ff3_recovers_known_coefficients(self):
        factors = _factors()
        ls = pd.DataFrame({
            "yyyymm": factors["yyyymm"],
            "ls_return": 0.003 + 0.9 * factors["mktrf"] + 0.3 * factors["smb"] - 0.2 * factors["hml"],
        })
        result = steps.compute_factor_alphas(ls, factors, config={})
        assert result["alpha_ff3"] == pytest.approx(0.003, abs=1e-9)
        assert result["beta_ff3_mktrf"] == pytest.approx(0.9, abs=1e-9)
        assert result["beta_ff3_smb"] == pytest.approx(0.3, abs=1e-9)
        assert result["beta_ff3_hml"] == pytest.approx(-0.2, abs=1e-9)

    def test_ff5_present_when_rmw_cma_available(self):
        factors = _factors()
        ls = pd.DataFrame({"yyyymm": factors["yyyymm"], "ls_return": factors["mktrf"]})
        result = steps.compute_factor_alphas(ls, factors, config={})
        assert "alpha_ff5" in result

    def test_ff5_omitted_when_rmw_cma_missing(self):
        factors = _factors().drop(columns=["rmw", "cma"])
        ls = pd.DataFrame({"yyyymm": factors["yyyymm"], "ls_return": factors["mktrf"]})
        result = steps.compute_factor_alphas(ls, factors, config={})
        assert "alpha_ff5" not in result
        assert "alpha_ff3" in result
        assert "alpha_capm" in result


class TestComputeFactorAlphasEdgeCases:
    def test_full_portfolio_return_shape_returns_empty(self):
        factors = _factors()
        ls = pd.DataFrame({"yyyymm": [200001, 200001], "portfolio": [1, 2], "ret": [0.01, 0.02]})
        assert steps.compute_factor_alphas(ls, factors, config={}) == {}

    def test_none_factors_returns_empty(self):
        ls = pd.DataFrame({"yyyymm": [200001], "ls_return": [0.01]})
        assert steps.compute_factor_alphas(ls, None, config={}) == {}

    def test_too_few_overlapping_months_returns_empty(self):
        factors = _factors()
        ls = pd.DataFrame({"yyyymm": [200001, 200002], "ls_return": [0.01, 0.02]})
        assert steps.compute_factor_alphas(ls, factors, config={}) == {}


class TestComputeMetricsSharpeRatio:
    def test_sharpe_ratio_present_and_correct(self):
        series = pd.DataFrame({"yyyymm": list(range(200001, 200013)), "ls_return": [0.01] * 12})
        metrics = steps.compute_metrics(series, config={})
        assert "sharpe_ratio" in metrics
        # zero variance -> nan (guarded div-by-zero), matches existing t_stat convention
        assert np.isnan(metrics["sharpe_ratio"])

    def test_sharpe_ratio_positive_for_varying_positive_mean_series(self):
        rng = np.random.default_rng(1)
        vals = 0.01 + rng.normal(0, 0.02, 24)
        series = pd.DataFrame({"yyyymm": list(range(200001, 200025)), "ls_return": vals})
        metrics = steps.compute_metrics(series, config={})
        # pandas Series.std() (used by compute_metrics) defaults to ddof=1
        # (sample std), unlike numpy's ndarray.std() default of ddof=0.
        expected = (vals.mean() / vals.std(ddof=1)) * np.sqrt(12)
        assert metrics["sharpe_ratio"] == pytest.approx(expected)
