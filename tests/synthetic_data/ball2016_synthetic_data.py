"""Synthetic CRSP/Compustat/CCM data for the Ball et al. (2016) cash-based
operating profitability factor (RMW CbOP) MVP end-to-end test.

Unlike the single-sort factors (asset_growth, accruals, AB1998), this factor
is a 2x3 independent double sort (size x profitability) combined as
0.5*(small-robust + big-robust) - 0.5*(small-weak + big-weak) — see
tests/fixtures/plugins/ball2016_cash_based_operating_profitability_factor.py's
compute_breakpoints_hook / assign_portfolios_hook / compute_long_short_hook
(portfolio ids 1=small-weak 2=small-mid 3=small-robust 4=big-weak 5=big-mid
6=big-robust). This exercises the general `compute_long_short` hook point
added to BacktestExecutor for multi-leg long/short combinations.

Design:
- 10 permnos. Profitability signal is evenly spaced by permno rank
  (g_i = 0.02*i - 0.11, i=1..10, same spacing convention as every other
  synthetic-data module in this repo) so weak=deciles{1,2,3}, mid={4,5,6,7},
  robust={8,9,10} (NYSE 30th/70th percentile breakpoints over 10 evenly
  spaced points split 3/4/3, mirroring pd.quantile's linear interpolation —
  see tests/test_mvp_e2e.py's docstring for the general argument).
- Compustat fields are held constant across fiscal years except `revt`,
  which is set directly to `1000 * g_i` (with `at`=1000 constant, all other
  delta-adjustment fields zeroed), so the cash-based operating profitability
  formula evaluates to exactly `g_i` at both June formation dates.
- Size (small/big) is assigned via a fixed permno->group table chosen so all
  four "corner" portfolios needed by the long-short combination (1, 3, 4, 6)
  are non-empty every month: small={1,3,5,7,9}, big={2,4,6,8,10}. me=50 for
  small, me=200 for big (equal me within each group, so VW = plain average).
- Monthly returns are ret[i,t] = base_i * (1 + 0.01*t), base_i = 0.001*i, so
  every cell average (and the final long-short combination) stays a clean
  closed-form function of t (see expected_metrics()).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tests.synthetic_data.asset_growth_synthetic_data import N_STOCKS, build_ccm_link

FIRST_HOLDING_YYYYMM = 199807  # July 1998
N_MONTHS = 24  # Jul 1998 .. Jun 2000

# Profitability signal per permno (index 0 == permno 1): -0.09 .. +0.09
PROFITABILITY = [round(0.02 * i - 0.11, 10) for i in range(1, N_STOCKS + 1)]

# Base monthly return per permno (index 0 == permno 1): 0.001 .. 0.010
BASE_RETURNS = [round(0.001 * i, 10) for i in range(1, N_STOCKS + 1)]

# permno -> size group, chosen so portfolios 1 (small-weak), 3 (small-robust),
# 4 (big-weak), and 6 (big-robust) are all non-empty every month.
SIZE_GROUP = {i: ("small" if i % 2 == 1 else "big") for i in range(1, N_STOCKS + 1)}


def _permno(i: int) -> int:
    """Must match asset_growth_synthetic_data._permno so CCM linking resolves."""
    return 10000 + i


def _gvkey(i: int) -> str:
    """Must match asset_growth_synthetic_data._gvkey so CCM linking resolves."""
    return f"{100000 + i:06d}"


def _add_months(yyyymm: int, months: int) -> int:
    year, month = divmod(yyyymm, 100)
    total = year * 12 + (month - 1) + months
    year, month = divmod(total, 12)
    return year * 100 + month + 1


def build_compustat_funda() -> pd.DataFrame:
    """Fiscal years 1996-1998; only `revt` varies by permno, everything else
    is held constant/zero so the cash-based operating profitability formula
    reduces to `revt_t / at_lag1 == PROFITABILITY[i-1]`.
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        revt = 1000.0 * PROFITABILITY[idx]
        for fyear in (1996, 1997, 1998):
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                "revt": revt,
                "cogs": 0.0,
                "xsga": 0.0,
                "xrd": 0.0,
                "rect": 0.0,
                "invt": 0.0,
                "xpp": 0.0,
                "drc": 0.0,
                "drlt": 0.0,
                "ap": 0.0,
                "xacc": 0.0,
                "at": 1000.0,
            })
    return pd.DataFrame(rows)


def build_crsp_msf() -> pd.DataFrame:
    """24 months (Jul 1998 - Jun 2000): me reflects the small/big group,
    ret follows the same base_i*(1+0.01*t) pattern used elsewhere.
    """
    rows = []
    yyyymm = FIRST_HOLDING_YYYYMM
    for t in range(N_MONTHS):
        for idx in range(N_STOCKS):
            i = idx + 1
            ret = BASE_RETURNS[idx] * (1 + 0.01 * t)
            me = 50.0 if SIZE_GROUP[i] == "small" else 200.0
            rows.append({
                "permno": _permno(i),
                "yyyymm": yyyymm,
                "ret": ret,
                "me": me,
                "shrcd": 10,
                "exchcd": 1,
                "siccd": 2000,
            })
        yyyymm = _add_months(yyyymm, 1)
    return pd.DataFrame(rows)


def expected_long_short_series() -> pd.DataFrame:
    """Independently-derived expected [yyyymm, ls_return] series.

    weak={1,2,3} (small={1,3}, big={2}); robust={8,9,10} (small={9}, big={8,10}).
    robust_avg(t) = 0.5*(avg(base_8,base_10) + avg(base_8,base_10))... see below.
    """
    small_weak = [1, 3]
    big_weak = [2]
    small_robust = [9]
    big_robust = [8, 10]

    def _cell_avg(members: list[int]) -> float:
        return sum(BASE_RETURNS[m - 1] for m in members) / len(members)

    robust_base = 0.5 * (_cell_avg(small_robust) + _cell_avg(big_robust))
    weak_base = 0.5 * (_cell_avg(small_weak) + _cell_avg(big_weak))
    diff = robust_base - weak_base

    yyyymm = FIRST_HOLDING_YYYYMM
    rows = []
    for t in range(N_MONTHS):
        rows.append({"yyyymm": yyyymm, "ls_return": diff * (1 + 0.01 * t)})
        yyyymm = _add_months(yyyymm, 1)
    return pd.DataFrame(rows)


def expected_metrics() -> dict:
    """Golden mean/t-stat computed independently (plain numpy, standard NW formula)."""
    series = expected_long_short_series()["ls_return"].to_numpy()
    n = len(series)
    mean_ret = float(series.mean())

    lags = min(6, n - 1)
    xd = series - mean_ret
    nw_var = float(np.dot(xd, xd)) / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma = float(np.dot(xd[lag:], xd[:-lag])) / n
        nw_var += 2.0 * w * gamma
    t_stat = mean_ret / np.sqrt(nw_var / n)

    return {
        "mean_monthly_return": mean_ret,
        "annualized_return": mean_ret * 12,
        "t_stat": float(t_stat),
        "n_months": n,
    }


__all__ = [
    "PROFITABILITY",
    "BASE_RETURNS",
    "SIZE_GROUP",
    "build_compustat_funda",
    "build_crsp_msf",
    "build_ccm_link",
    "expected_long_short_series",
    "expected_metrics",
]
