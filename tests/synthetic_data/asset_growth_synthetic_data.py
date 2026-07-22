"""Synthetic CRSP/Compustat/CCM data for the AssetGrowth MVP end-to-end test.

Design (see docs/roadmap.md Phase 1 "Synthetic data requirements"):

- 10 permnos, each with a distinct, evenly-spaced annual asset-growth rate
  ``g_i = 0.02*i - 0.11`` for i=1..10 (i.e. -0.09, -0.07, ..., +0.09). Compustat
  ``at`` grows at exactly ``g_i`` in both fiscal 1997 and fiscal 1998, so the
  Cooper-Gulen-Schill asset-growth signal (computed by the real generated
  plugin) is identical and rank-stable at both June formation dates.
- Monthly CRSP returns are ``ret[i, t] = base_i * (1 + 0.01*t)`` where
  ``base_i = 0.011 - 0.001*(i-1)`` and ``t`` is the month index (0-based) over
  the 24 consecutive months from July 1998 through June 2000. Because there
  are exactly 10 permnos and 10 deciles, each decile holds exactly one stock,
  so the long-short (decile 1 minus decile 10) series is a deterministic,
  closed-form function of ``t`` that can be verified independently of the
  BacktestExecutor implementation (see ``expected_long_short_series`` below).
- One open-ended, primary CCM link per permno/gvkey pair.

All stocks share shrcd=10, exchcd=1, siccd=2000 (non-financial, NYSE) so the
universe filter never drops a row and breakpoint_source='full_sample' and
'nyse' would behave identically.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_STOCKS = 10
FIRST_HOLDING_YYYYMM = 199807  # July 1998
N_MONTHS = 24  # Jul 1998 .. Jun 2000

# Annual asset-growth rate per permno (index 0 == permno 1): -0.09 .. +0.09
GROWTH_RATES = [round(0.02 * i - 0.11, 10) for i in range(1, N_STOCKS + 1)]

# Base monthly return per permno (index 0 == permno 1): 0.011 .. 0.002
BASE_RETURNS = [round(0.011 - 0.001 * (i - 1), 10) for i in range(1, N_STOCKS + 1)]


def _permno(i: int) -> int:
    """1-indexed stock number -> synthetic permno."""
    return 10000 + i


def _gvkey(i: int) -> str:
    return f"{100000 + i:06d}"
 

def _add_months(yyyymm: int, months: int) -> int:
    year, month = divmod(yyyymm, 100)
    total = year * 12 + (month - 1) + months
    year, month = divmod(total, 12)
    return year * 100 + month + 1


def build_compustat_funda() -> pd.DataFrame:
    """Fiscal years 1996-1998 'at' values growing at each permno's fixed rate."""
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        g = GROWTH_RATES[idx]
        at = 100.0
        for fyear in (1996, 1997, 1998):
            rows.append({"gvkey": gvkey, "datadate": f"{fyear}-12-31", "at": at})
            at = at * (1 + g)
    return pd.DataFrame(rows)


def build_ccm_link() -> pd.DataFrame:
    """One open-ended, primary link per permno/gvkey pair."""
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        rows.append({
            "gvkey": _gvkey(i),
            "permno": _permno(i),
            "linktype": "LU",
            "linkprim": "P",
            "linkdt": "1990-01-01",
            "linkenddt": None,
        })
    return pd.DataFrame(rows)


def build_crsp_msf() -> pd.DataFrame:
    """24 months (Jul 1998 - Jun 2000) of monthly data for all 10 permnos."""
    rows = []
    yyyymm = FIRST_HOLDING_YYYYMM
    for t in range(N_MONTHS):
        for idx in range(N_STOCKS):
            i = idx + 1
            ret = BASE_RETURNS[idx] * (1 + 0.01 * t)
            rows.append({
                "permno": _permno(i),
                "yyyymm": yyyymm,
                "ret": ret,
                "me": 100.0,
                "shrcd": 10,
                "exchcd": 1,
                "siccd": 2000,
            })
        yyyymm = _add_months(yyyymm, 1)
    return pd.DataFrame(rows)


def expected_long_short_series() -> pd.DataFrame:
    """Independently-derived expected [yyyymm, ls_return] series.

    decile 1 (long leg, lowest asset growth) == permno 1 (highest base return)
    decile 10 (short leg, highest asset growth) == permno 10 (lowest base return)
    ls_return(t) = (BASE_RETURNS[0] - BASE_RETURNS[-1]) * (1 + 0.01*t)
    """
    diff = BASE_RETURNS[0] - BASE_RETURNS[-1]
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
