"""Synthetic Compustat data for the 9 Abarbanell & Bushee (1998) fundamental
signals (AB1998_AQ / AR / CAPX / EQ / ETR / GM / INV / LF / SA).

Per-factor ground truth: data/test_method_specs_human_labeled/AB1998_*.methodspec.json

Scope note: this module ONLY generates the raw Compustat annual fields each
factor's formula needs (matching data.required_fields in the ground-truth
specs) — it does not build plugins, resolved MethodSpecs, or golden-number
tests (unlike asset_growth_synthetic_data.py / accruals_synthetic_data.py).
The paper's actual return construction uses daily buy-and-hold abnormal
returns against a size-decile benchmark, which this repo's BacktestExecutor
doesn't implement (it's monthly VW/EW only) — out of scope here.

Reuses the same 10 permnos / CCM link / CRSP monthly panel as
asset_growth_synthetic_data.py so all of this lines up with the same
DataLayer.get_signal_master_table() plumbing already exercised by the other
synthetic-data modules.

Design pattern for the "Delta operator" signals (AR/CAPX/GM/INV/LF/SA all use
Table 1's Delta(x) = (x_t - avg(x_t-1, x_t-2)) / avg(x_t-1, x_t-2)): one field
is held at a constant growth rate across all 10 stocks (so its Delta is the
same for every stock) and the other field's growth rate is evenly spaced
across stocks (-0.09..+0.09, same spacing used by every other synthetic-data
module in this repo), so the resulting signal is itself evenly spaced and
rank-stable across permno.
"""

from __future__ import annotations

import pandas as pd

from tests.synthetic_data.asset_growth_synthetic_data import (
    N_STOCKS,
    build_ccm_link,
    build_crsp_msf,
)

# Evenly spaced across permnos (index 0 == permno 1): -0.09 .. +0.09
RATES = [round(0.02 * i - 0.11, 10) for i in range(1, N_STOCKS + 1)]
FISCAL_YEARS_3 = (1996, 1997, 1998)
FISCAL_YEARS_4 = (1995, 1996, 1997, 1998)


def _gvkey(i: int) -> str:
    """Must match asset_growth_synthetic_data._gvkey so CCM linking resolves."""
    return f"{100000 + i:06d}"


def _growth_pair_funda(
    varying_field: str,
    constant_field: str = "sale",
    varying_base: float = 100.0,
    constant_base: float = 100.0,
    constant_rate: float = 0.05,
) -> pd.DataFrame:
    """Shared builder for the "Delta(sale) - Delta(x)" style signals.

    `constant_field` grows at a fixed `constant_rate` every year for every
    stock (so its Delta is identical across stocks and cancels out of the
    cross-sectional ranking); `varying_field` grows at a per-stock rate drawn
    from RATES, so the resulting Delta(constant) - Delta(varying) signal is
    evenly spaced across permnos (same decile-per-stock property as
    asset_growth_synthetic_data.py).
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        rate = RATES[idx]
        varying_val = varying_base
        constant_val = constant_base
        for fyear in FISCAL_YEARS_3:
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                constant_field: constant_val,
                varying_field: varying_val,
            })
            varying_val *= (1 + rate)
            constant_val *= (1 + constant_rate)
    return pd.DataFrame(rows)


def build_compustat_funda_ar() -> pd.DataFrame:
    """AB1998_AR: Delta(sale) - Delta(receivables)."""
    return _growth_pair_funda(varying_field="receivables")


def build_compustat_funda_gm() -> pd.DataFrame:
    """AB1998_GM: Delta(sale - cogs) - Delta(sale).

    cogs is held so that (sale - cogs) grows at the per-stock varying rate
    while sale itself grows at the constant rate, matching the shared pattern.
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        rate = RATES[idx]
        sale = 100.0
        gm = 40.0  # sale - cogs
        for fyear in FISCAL_YEARS_3:
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                "sale": sale,
                "cogs": sale - gm,
            })
            sale *= 1.05
            gm *= (1 + rate)
    return pd.DataFrame(rows)


def build_compustat_funda_inv() -> pd.DataFrame:
    """AB1998_INV: Delta(sale) - Delta(inventory)."""
    return _growth_pair_funda(varying_field="inventory")


def build_compustat_funda_sa() -> pd.DataFrame:
    """AB1998_SA: Delta(sale) - Delta(xsga)."""
    return _growth_pair_funda(varying_field="xsga")


def build_compustat_funda_capx() -> pd.DataFrame:
    """AB1998_CAPX: Delta(firm_capx) - Delta(industry_capx)."""
    return _growth_pair_funda(
        varying_field="firm_capx", constant_field="industry_capx",
        varying_base=20.0, constant_base=20.0,
    )


def build_compustat_funda_lf() -> pd.DataFrame:
    """AB1998_LF: change in sales-per-employee vs its prior 2-year average.

    emp held constant per stock so sale/emp growth == sale growth; sale grows
    at the per-stock varying rate (unlike the shared pattern, LF has no
    second field to cancel out, so the varying rate alone drives the signal).
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        rate = RATES[idx]
        sale = 100.0
        emp = 50.0
        for fyear in FISCAL_YEARS_3:
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                "sale": sale,
                "emp": emp,
            })
            sale *= (1 + rate)
    return pd.DataFrame(rows)


def build_compustat_funda_etr() -> pd.DataFrame:
    """AB1998_ETR: -(etr_t - avg(etr_t-1..t-3)) * chgeps_t.

    Needs 4 fiscal years (1995-1998) for the 3-year trailing average. etr is
    held at a constant base for years t-3..t-1 and shifted by a per-stock
    RATES offset only in the final year t, so `etr_t - avg(...)` is exactly
    the per-stock rate; chgeps is a constant across stocks so it doesn't
    change the cross-sectional ranking.
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        rate = RATES[idx]
        base_etr = 0.30
        for fyear in FISCAL_YEARS_4:
            etr = base_etr + rate if fyear == FISCAL_YEARS_4[-1] else base_etr
            rows.append({
                "gvkey": gvkey,
                "datadate": f"{fyear}-12-31",
                "etr": etr,
                "chgeps": 1.0,
            })
    return pd.DataFrame(rows)


def build_compustat_funda_aq() -> pd.DataFrame:
    """AB1998_AQ: binary audit-opinion indicator (1=unqualified, 0=qualified/other).

    Half the permnos get 'unqualified', half 'qualified' (no natural
    evenly-spaced ranking for a binary field).
    """
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        opinion = "unqualified" if i <= N_STOCKS // 2 else "qualified"
        for fyear in FISCAL_YEARS_3:
            rows.append({"gvkey": gvkey, "datadate": f"{fyear}-12-31", "audit_opinion": opinion})
    return pd.DataFrame(rows)


def build_compustat_funda_eq() -> pd.DataFrame:
    """AB1998_EQ: binary inventory-method indicator (1=LIFO, 0=FIFO/other)."""
    rows = []
    for idx in range(N_STOCKS):
        i = idx + 1
        gvkey = _gvkey(i)
        method = "LIFO" if i <= N_STOCKS // 2 else "FIFO"
        for fyear in FISCAL_YEARS_3:
            rows.append({"gvkey": gvkey, "datadate": f"{fyear}-12-31", "inventory_method": method})
    return pd.DataFrame(rows)


# factor_id -> builder, matching data/test_method_specs_human_labeled/AB1998_*.methodspec.json
BUILDERS = {
    "AB1998_AQ": build_compustat_funda_aq,
    "AB1998_AR": build_compustat_funda_ar,
    "AB1998_CAPX": build_compustat_funda_capx,
    "AB1998_EQ": build_compustat_funda_eq,
    "AB1998_ETR": build_compustat_funda_etr,
    "AB1998_GM": build_compustat_funda_gm,
    "AB1998_INV": build_compustat_funda_inv,
    "AB1998_LF": build_compustat_funda_lf,
    "AB1998_SA": build_compustat_funda_sa,
}


__all__ = [
    "RATES",
    "BUILDERS",
    "build_ccm_link",
    "build_crsp_msf",
    "build_compustat_funda_aq",
    "build_compustat_funda_ar",
    "build_compustat_funda_capx",
    "build_compustat_funda_eq",
    "build_compustat_funda_etr",
    "build_compustat_funda_gm",
    "build_compustat_funda_inv",
    "build_compustat_funda_lf",
    "build_compustat_funda_sa",
]
