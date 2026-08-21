"""Synthetic Compustat data for the sloan_1996_accruals MVP end-to-end test.

Reuses the CRSP monthly panel, CCM link table, and long-short golden numbers
from asset_growth_synthetic_data.py unchanged (same 10 permnos, same base_i
monthly returns -> same decile-to-permno mapping -> same expected long-short
series), since none of that depends on which Compustat fields feed the
signal. Only the Compustat "annual industrial file" fields differ: this
factor's compute_signal() needs act/che/lct/dlc/dp/at (Sloan 1996 accruals
formula) instead of asset_growth's single 'at' field.

Design: accrual_i = 0.02*i - 0.11 for i=1..10 (same evenly-spaced values as
asset_growth's growth rates, so permno i lands in decile i for the same
reason). che/lct/dlc/dp are held constant (=0) across fiscal years for every
stock so their deltas vanish; 'at' (total assets) is held constant at 1000
so avg_at=1000; only 'act' (current assets) grows by a constant increment
every year: act_t = act_{t-1} + 1000*accrual_i, which makes the accruals
formula ((act-che)-(lct-dlc)-dp)/avg_at evaluate to exactly `accrual_i` at
both June formation dates (mirroring asset_growth's "same rate both years"
trick). The plugin's per-formation-date 1%/99% winsorization compresses the
two extreme values slightly but preserves rank order (see docstring in
tests/test_accruals_e2e.py), so decile assignment (and therefore the
long-short series) is unaffected.
"""

from __future__ import annotations

import pandas as pd

from tests.synthetic_data.asset_growth_synthetic_data import (
    N_STOCKS,
    build_ccm_link,
    build_crsp_msf,
    expected_long_short_series,
    expected_metrics,
)

# Accruals value per permno (index 0 == permno 1): -0.09 .. +0.09
ACCRUAL_VALUES = [round(0.02 * i - 0.11, 10) for i in range(1, N_STOCKS + 1)]


def _gvkey(i: int) -> str:
    """Must match asset_growth_synthetic_data._gvkey so CCM linking resolves."""
    return f"{100000 + i:06d}"


def build_compustat_funda() -> pd.DataFrame:
    """Fiscal years 1996-1998 act/che/lct/dlc/dp/at values.

    che/lct/dlc/dp constant (=0) and 'at' constant (=1000) for every
    stock/year so only 'act' drives the accruals signal; 'act' grows by a
    constant 1000*accrual_i increment each year so the signal is identical
    at both the June-1998 and June-1999 formation dates.
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        accrual = ACCRUAL_VALUES[idx]
        act = 500.0
        for fyear in (1996, 1997, 1998):
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                "act": act,
                "che": 0.0,
                "lct": 0.0,
                "dlc": 0.0,
                "dp": 0.0,
                "at": 1000.0,
            })
            act += 1000.0 * accrual
    return pd.DataFrame(rows)


__all__ = [
    "ACCRUAL_VALUES",
    "build_compustat_funda",
    "build_ccm_link",
    "build_crsp_msf",
    "expected_long_short_series",
    "expected_metrics",
]
