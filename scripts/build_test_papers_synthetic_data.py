"""Generate realistic synthetic data mirroring the REAL WRDS schemas used by the
10 test papers (see docs/test_papers_data_sources.xlsx).

Design goals:
- Real column names / formats / value ranges (schemas taken from the actual WRDS
  SQL in `data/CZ code/Signals/pyCode/DataDownloads/*.py`, plus the OptionMetrics
  volatility-surface layout).
- Faithful table SEPARATION: CRSP ships msf / msenames / msedelist as separate
  tables (returns vs. identifying attributes vs. delisting), so we do too — the
  join work is real, not pre-flattened.
- Real independent LINK tables (CCM ccmxpf_lnkhist, IBES-CRSP, OptionMetrics-CRSP)
  with realistic validity windows — identifiers are consistent across sources so
  the real link tables connect them, but nothing is conveniently pre-joined.

Out of scope (BAB international / bond legs): Xpressfeed Global, MSCI indices,
CRSP US Treasury, Ibbotson — those papers' US-equity legs use CRSP/French only.

Deterministic (seeded). Run:  python3 scripts/build_test_papers_synthetic_data.py
Outputs: data/synthetic_data/test_papers_v1/<table>.parquet
"""

from __future__ import annotations

import string
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260720
N_FIRMS = 60
MONTHLY_START, MONTHLY_END = "1990-01", "2015-12"   # covers most paper samples
DAILY_START, DAILY_END = "2005-01-01", "2012-12-31"  # bounded window for daily
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic_data" / "test_papers_v1"

rng = np.random.default_rng(SEED)


# ---------------------------------------------------------------------------
# Shared firm universe: consistent identifiers across every source so the REAL
# link tables (not shortcuts) tie them together.
# ---------------------------------------------------------------------------

def build_universe() -> pd.DataFrame:
    permnos = 10000 + rng.choice(np.arange(1, 90000), size=N_FIRMS, replace=False)
    permnos = np.sort(permnos)
    rows = []
    # A realistic SIC mix: industrials, tech, retail, plus some financials
    # (6000-6999) and a couple of utilities/other to exercise universe filters.
    sic_pool = [2834, 3571, 3674, 5411, 7372, 1311, 2911, 3711,
                6020, 6199, 6798, 4911, 2000, 3826]
    for i, permno in enumerate(permnos):
        base8 = _rand_cusip8()
        # exchcd 1/2/3 = NYSE/AMEX/NASDAQ; a few 0/4 (other) to be filtered out.
        exchcd = int(rng.choice([1, 1, 1, 2, 3, 3, 3, 0], p=[.28, .14, .14, .1, .12, .1, .07, .05]))
        # shrcd 10/11 ordinary common; occasional 12/18/73 (ADR/other) to filter.
        shrcd = int(rng.choice([10, 11, 11, 12, 18, 73], p=[.4, .3, .17, .05, .04, .04]))
        siccd = int(rng.choice(sic_pool))
        has_ibes = bool(rng.random() < 0.75)
        has_options = bool(rng.random() < 0.45)
        rows.append({
            "permno": int(permno),
            "permco": int(20000 + i),
            "gvkey": f"{1001 + i:06d}",          # Compustat gvkey: 6-char string
            "ncusip": base8,                       # CRSP historical 8-char CUSIP
            "cusip9": base8 + _cusip_check(base8), # Compustat 9-char CUSIP
            "crsp_ticker": _rand_ticker(),
            "ibes_ticker": _rand_ticker() if has_ibes else "",
            "secid": int(100000 + i) if has_options else -1,
            "comnam": f"SYNTHETIC CO {i+1:02d}",
            "exchcd": exchcd,
            "shrcd": shrcd,
            "siccd": siccd,
            "has_ibes": has_ibes,
            "has_options": has_options,
            # per-firm price/return process params
            "_p0": float(rng.uniform(5, 120)),
            "_mu": float(rng.normal(0.009, 0.004)),
            "_sig": float(rng.uniform(0.06, 0.16)),
        })
    return pd.DataFrame(rows)


def _rand_cusip8() -> str:
    chars = string.digits + string.ascii_uppercase
    return "".join(rng.choice(list(chars), size=8))


def _cusip_check(base8: str) -> str:
    return rng.choice(list(string.digits))


def _rand_ticker() -> str:
    n = int(rng.integers(3, 6))
    return "".join(rng.choice(list(string.ascii_uppercase), size=n))


# ---------------------------------------------------------------------------
# CRSP: msf (returns/prices) + msenames (identifying attrs) + msedelist +
# msedist — kept as separate tables exactly like WRDS.
# ---------------------------------------------------------------------------

def build_crsp_msf(u: pd.DataFrame) -> pd.DataFrame:
    months = pd.period_range(MONTHLY_START, MONTHLY_END, freq="M")
    rows = []
    for _, f in u.iterrows():
        # firm enters at a random month, may exit early (delist)
        start = int(rng.integers(0, max(1, len(months) - 60)))
        end = len(months)
        if rng.random() < 0.20:  # 20% delist before sample end
            end = int(rng.integers(start + 48, len(months)))
        price = f["_p0"]
        shrout = float(rng.uniform(2_000, 800_000))  # thousands of shares
        for k in range(start, end):
            m = months[k]
            r = float(rng.normal(f["_mu"], f["_sig"]))
            r = float(np.clip(r, -0.6, 1.5))
            ret = np.nan if rng.random() < 0.015 else r  # occasional missing
            price *= (1 + (r if not np.isnan(ret) else 0))
            price = max(price, 0.10)
            # CRSP prc is negative when it's a bid/ask midpoint (no closing trade)
            prc = -price if rng.random() < 0.05 else price
            div_yield = max(0.0, rng.normal(0.004, 0.003)) if rng.random() < 0.3 else 0.0
            shrout *= (1 + rng.normal(0, 0.01))
            rows.append({
                "permno": f["permno"],
                "permco": f["permco"],
                "date": m.to_timestamp(how="end").normalize(),
                "ret": ret,
                "retx": np.nan if np.isnan(ret) else float(ret - div_yield),
                "prc": round(prc, 3),
                "vol": float(round(rng.uniform(1e3, 5e6))),
                "shrout": round(shrout),
                "cfacshr": 1.0,
                "bidlo": round(abs(prc) * (1 - rng.uniform(0, 0.03)), 3),
                "askhi": round(abs(prc) * (1 + rng.uniform(0, 0.03)), 3),
            })
    df = pd.DataFrame(rows)
    df["permno"] = df["permno"].astype("int64")
    return df


def build_crsp_msenames(u: pd.DataFrame) -> pd.DataFrame:
    """Identifying attributes with validity windows (namedt..nameendt).
    Occasionally a firm changes exchange/ticker mid-life -> two name rows."""
    rows = []
    lo = pd.Timestamp(MONTHLY_START + "-01")
    hi = pd.Timestamp(MONTHLY_END + "-28")
    for _, f in u.iterrows():
        if rng.random() < 0.25:  # one exchange/ticker switch
            switch = lo + (hi - lo) * float(rng.uniform(0.3, 0.7))
            rows.append(_name_row(f, lo, switch, exchcd=3, ticker=f["crsp_ticker"]))
            rows.append(_name_row(f, switch + pd.Timedelta(days=1), hi,
                                  exchcd=f["exchcd"], ticker=_rand_ticker()))
        else:
            rows.append(_name_row(f, lo, hi, exchcd=f["exchcd"], ticker=f["crsp_ticker"]))
    return pd.DataFrame(rows)


def _name_row(f, namedt, nameendt, exchcd, ticker) -> dict:
    return {
        "permno": int(f["permno"]),
        "namedt": pd.Timestamp(namedt).normalize(),
        "nameendt": pd.Timestamp(nameendt).normalize(),
        "shrcd": int(f["shrcd"]),
        "exchcd": int(exchcd),
        "siccd": int(f["siccd"]),
        "ncusip": f["ncusip"],
        "ticker": ticker,
        "comnam": f["comnam"],
        "shrcls": rng.choice(["", "", "A", "B"]),
    }


def build_crsp_msedelist(u: pd.DataFrame, msf: pd.DataFrame) -> pd.DataFrame:
    """Delisting events for firms whose msf history ends before sample end."""
    last_month = msf.groupby("permno")["date"].max()
    sample_end = pd.Timestamp(MONTHLY_END + "-28")
    rows = []
    for permno, last in last_month.items():
        if last < sample_end - pd.Timedelta(days=40):
            code = int(rng.choice([100, 233, 331, 574, 580, 584]))  # active/merger/perf
            perf_related = code >= 500
            # performance-related delistings often have a large negative dlret
            if perf_related:
                dlret = float(rng.uniform(-0.6, -0.1))
            elif rng.random() < 0.5:
                dlret = float(rng.uniform(-0.1, 0.05))
            else:
                dlret = np.nan  # missing -> downstream imputes per Shumway 1997
            rows.append({
                "permno": int(permno),
                "dlstdt": (last + pd.Timedelta(days=20)).normalize(),
                "dlstcd": code,
                "dlret": dlret,
            })
    return pd.DataFrame(rows)


def build_crsp_msedist(u: pd.DataFrame) -> pd.DataFrame:
    """Cash/stock distributions (crsp.msedist): dividends & splits."""
    rows = []
    for _, f in u.iterrows():
        n = int(rng.poisson(6))
        for _ in range(n):
            yr = int(rng.integers(1990, 2016))
            mo = int(rng.integers(1, 13))
            exdt = pd.Timestamp(year=yr, month=mo, day=int(rng.integers(1, 28)))
            is_split = rng.random() < 0.15
            rows.append({
                "permno": int(f["permno"]),
                "divamt": 0.0 if is_split else round(float(rng.uniform(0.05, 1.2)), 3),
                "distcd": 5523 if is_split else 1232,
                "facshr": round(float(rng.choice([0.5, 1.0, 2.0])), 4) if is_split else 0.0,
                "rcrddt": (exdt + pd.Timedelta(days=2)).normalize(),
                "exdt": exdt.normalize(),
                "paydt": (exdt + pd.Timedelta(days=20)).normalize(),
            })
    return pd.DataFrame(rows).sort_values(["permno", "exdt"]).reset_index(drop=True)


def build_crsp_dsf(u: pd.DataFrame) -> pd.DataFrame:
    """Daily stock file (bounded window) for beta / idio-vol / options papers."""
    days = pd.bdate_range(DAILY_START, DAILY_END)
    rows = []
    for _, f in u.iterrows():
        if rng.random() < 0.3:   # not every firm needs daily coverage
            continue
        price = f["_p0"] * float(rng.uniform(0.8, 1.5))
        shrout = float(rng.uniform(2_000, 800_000))
        daily_sig = f["_sig"] / np.sqrt(21)
        for d in days:
            r = float(np.clip(rng.normal(f["_mu"] / 21, daily_sig), -0.3, 0.3))
            price = max(price * (1 + r), 0.10)
            prc = -price if rng.random() < 0.03 else price
            rows.append({
                "permno": int(f["permno"]),
                "date": d.normalize(),
                "ret": np.nan if rng.random() < 0.01 else round(r, 6),
                "prc": round(prc, 3),
                "vol": float(round(rng.uniform(1e2, 5e5))),
                "shrout": round(shrout),
                "cfacpr": 1.0,
            })
    df = pd.DataFrame(rows)
    df["permno"] = df["permno"].astype("int64")
    return df


# ---------------------------------------------------------------------------
# Compustat annual (comp.funda) + quarterly (comp.fundq).
# ---------------------------------------------------------------------------

_FUNDA_ITEMS = ["at", "act", "che", "lct", "dlc", "dltt", "dp", "txp", "sale",
                "revt", "cogs", "xsga", "xrd", "rect", "invt", "xpp", "drc",
                "drlt", "ap", "xacc", "ceq", "ib", "csho", "ni", "dm", "dcvt",
                "dcpstk", "pstk", "seq", "prcc_f", "prcc_c"]


def build_comp_funda(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in u.iterrows():
        # fiscal year end: mostly December, some other months
        fye_month = int(rng.choice([12, 12, 12, 12, 6, 9, 3], p=[.55, .1, .05, .05, .1, .1, .05]))
        assets = float(rng.uniform(50, 40_000))     # $ millions
        for fyear in range(1988, 2015):
            assets *= (1 + rng.normal(0.06, 0.18))
            assets = max(assets, 5.0)
            at = assets
            sale = at * float(rng.uniform(0.4, 1.6))
            cogs = sale * float(rng.uniform(0.5, 0.8))
            xsga = sale * float(rng.uniform(0.05, 0.25))
            ib = sale * float(rng.uniform(-0.05, 0.15))
            ceq = at * float(rng.uniform(0.2, 0.6))
            act = at * float(rng.uniform(0.2, 0.6))
            lct = at * float(rng.uniform(0.1, 0.4))
            csho = float(rng.uniform(5, 2000))       # millions of shares
            vals = {
                "at": at, "act": act, "che": at * rng.uniform(0.02, 0.2),
                "lct": lct, "dlc": lct * rng.uniform(0.1, 0.5),
                "dltt": at * rng.uniform(0.0, 0.4), "dp": at * rng.uniform(0.02, 0.1),
                "txp": at * rng.uniform(0.0, 0.05), "sale": sale, "revt": sale,
                "cogs": cogs, "xsga": xsga,
                "xrd": (sale * rng.uniform(0.0, 0.15)) if rng.random() < 0.5 else np.nan,
                "rect": act * rng.uniform(0.1, 0.5), "invt": act * rng.uniform(0.1, 0.5),
                "xpp": act * rng.uniform(0.0, 0.05),
                "drc": (at * rng.uniform(0.0, 0.03)) if rng.random() < 0.3 else np.nan,
                "drlt": (at * rng.uniform(0.0, 0.03)) if rng.random() < 0.3 else np.nan,
                "ap": lct * rng.uniform(0.1, 0.5), "xacc": lct * rng.uniform(0.0, 0.1),
                "ceq": ceq, "ib": ib, "csho": csho, "ni": ib * rng.uniform(0.8, 1.1),
                "dm": (at * rng.uniform(0, 0.05)) if rng.random() < 0.2 else np.nan,
                "dcvt": (at * rng.uniform(0, 0.05)) if rng.random() < 0.15 else np.nan,
                "dcpstk": np.nan, "pstk": (at * rng.uniform(0, 0.03)) if rng.random() < 0.1 else np.nan,
                "seq": ceq * rng.uniform(1.0, 1.2),
                "prcc_f": max(0.5, f["_p0"] * rng.uniform(0.5, 2.0)),
                "prcc_c": max(0.5, f["_p0"] * rng.uniform(0.5, 2.0)),
            }
            rows.append({
                "gvkey": f["gvkey"],
                "datadate": pd.Timestamp(year=fyear, month=fye_month, day=1)
                              + pd.offsets.MonthEnd(0),
                "conm": f["comnam"],
                "fyear": fyear,
                "tic": f["crsp_ticker"],
                "cusip": f["cusip9"],
                "naicsh": int(rng.choice([325412, 334111, 511210, 452210, 211111])),
                "sich": int(f["siccd"]),
                **{k: (round(v, 3) if isinstance(v, float) and not np.isnan(v) else v)
                   for k, v in vals.items()},
            })
    df = pd.DataFrame(rows)
    # WRDS funda standard filter flags (all rows already "standard")
    df["indfmt"], df["consol"], df["popsrc"], df["datafmt"], df["curcd"] = \
        "INDL", "C", "D", "STD", "USD"
    return df


def build_comp_fundq(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in u.iterrows():
        if rng.random() < 0.25:   # not every firm has quarterly coverage in sample
            continue
        atq = float(rng.uniform(50, 40_000))
        for year in range(1990, 2015):
            for q in range(1, 5):
                atq *= (1 + rng.normal(0.015, 0.06))
                atq = max(atq, 5.0)
                saleq = atq * float(rng.uniform(0.1, 0.4))
                eps = float(rng.normal(0.4, 0.6))
                month = q * 3
                rows.append({
                    "gvkey": f["gvkey"],
                    "datadate": pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0),
                    "fyearq": year, "fqtr": q,
                    "datacqtr": f"{year}Q{q}",
                    "atq": round(atq, 3),
                    "actq": round(atq * rng.uniform(0.2, 0.6), 3),
                    "cheq": round(atq * rng.uniform(0.02, 0.2), 3),
                    "lctq": round(atq * rng.uniform(0.1, 0.4), 3),
                    "dlcq": round(atq * rng.uniform(0.0, 0.1), 3),
                    "dlttq": round(atq * rng.uniform(0.0, 0.4), 3),
                    "dpq": round(atq * rng.uniform(0.005, 0.03), 3),
                    "epspxq": round(eps, 3),
                    "epspiq": round(eps * rng.uniform(0.9, 1.1), 3),
                    "ibq": round(saleq * rng.uniform(-0.05, 0.15), 3),
                    "saleq": round(saleq, 3), "revtq": round(saleq, 3),
                    "cogsq": round(saleq * rng.uniform(0.5, 0.8), 3),
                    "rdq": pd.Timestamp(year=year, month=month, day=1)
                             + pd.offsets.MonthEnd(0) + pd.Timedelta(days=int(rng.integers(25, 60))),
                    "prccq": round(max(0.5, f["_p0"] * rng.uniform(0.5, 2.0)), 3),
                    "cshoq": round(float(rng.uniform(5, 2000)), 3),
                })
    df = pd.DataFrame(rows)
    df["indfmt"], df["consol"], df["popsrc"], df["datafmt"], df["curcdq"] = \
        "INDL", "C", "D", "STD", "USD"
    return df


# ---------------------------------------------------------------------------
# CCM link (crsp.ccmxpf_lnkhist joined to comp.names) — real link table.
# ---------------------------------------------------------------------------

def build_ccm_lnkhist(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    lo = pd.Timestamp("1985-01-01")
    for _, f in u.iterrows():
        # link valid from a firm-specific start; open-ended (NaT) for survivors
        linkdt = lo + pd.Timedelta(days=int(rng.integers(0, 3650)))
        linkenddt = pd.NaT if rng.random() < 0.6 else \
            linkdt + pd.Timedelta(days=int(rng.integers(2000, 9000)))
        rows.append({
            "gvkey": f["gvkey"],
            "conm": f["comnam"],
            "tic": f["crsp_ticker"],
            "cusip": f["cusip9"],
            "cik": f"{int(rng.integers(1, 1_600_000)):010d}",
            "sic": int(f["siccd"]),
            "naics": str(int(rng.choice([325412, 334111, 511210, 452210, 211111]))),
            "linkprim": rng.choice(["P", "P", "P", "C"]),
            "linktype": rng.choice(["LC", "LC", "LU"]),
            "liid": rng.choice(["01", "01", "02", "90"]),
            "lpermno": int(f["permno"]),
            "lpermco": int(f["permco"]),
            "linkdt": linkdt.normalize(),
            "linkenddt": linkenddt if pd.isna(linkenddt) else linkenddt.normalize(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# IBES: unadjusted summary (statsumu_epsus), actuals, and IBES-CRSP link.
# ---------------------------------------------------------------------------

def build_ibes_statsumu(u: pd.DataFrame) -> pd.DataFrame:
    months = pd.period_range("1984-01", "2015-12", freq="M")
    rows = []
    for _, f in u.iterrows():
        if not f["has_ibes"]:
            continue
        start = int(rng.integers(0, len(months) - 120))
        level = float(rng.normal(1.5, 1.0))
        for k in range(start, len(months), 1):
            if rng.random() < 0.15:   # not every month has a summary
                continue
            statpers = months[k].to_timestamp(how="start") + pd.Timedelta(days=17)  # IBES 3rd Thursday-ish
            level += float(rng.normal(0.01, 0.15))
            # forecast period end date ~ next fiscal year end
            fpedats = statpers + pd.offsets.MonthEnd(int(rng.integers(1, 14)))
            for fpi in ["0", "1", "2", "6"]:
                numest = int(rng.integers(1, 35))
                meanest = round(level + float(rng.normal(0, 0.2)), 4)
                rows.append({
                    "ticker": f["ibes_ticker"],
                    "statpers": statpers.normalize(),
                    "measure": "EPS",
                    "fpi": fpi,
                    "numest": numest,
                    "medest": round(meanest + float(rng.normal(0, 0.05)), 4),
                    "meanest": meanest,
                    "stdev": round(abs(float(rng.normal(0.1, 0.08))), 4),
                    "fpedats": fpedats.normalize(),
                })
    return pd.DataFrame(rows)


def build_ibes_actu(u: pd.DataFrame) -> pd.DataFrame:
    """Reported actual EPS (ibes.actu_epsus), quarterly, with announce date."""
    rows = []
    for _, f in u.iterrows():
        if not f["has_ibes"]:
            continue
        for year in range(1984, 2016):
            for q in range(1, 5):
                pends = pd.Timestamp(year=year, month=q * 3, day=1) + pd.offsets.MonthEnd(0)
                anndats = pends + pd.Timedelta(days=int(rng.integers(20, 55)))
                rows.append({
                    "ticker": f["ibes_ticker"],
                    "measure": "EPS",
                    "pends": pends.normalize(),
                    "pdicity": "QTR",
                    "value": round(float(rng.normal(0.4, 0.6)), 4),
                    "anndats": anndats.normalize(),
                })
    return pd.DataFrame(rows)


def build_ibes_crsp_link(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in u.iterrows():
        if not f["has_ibes"]:
            continue
        rows.append({
            "ticker": f["ibes_ticker"],
            "permno": int(f["permno"]),
            "ncusip": f["ncusip"],
            "sdate": pd.Timestamp("1984-01-31"),
            "edate": pd.Timestamp("2015-12-31"),
            "score": int(rng.choice([1, 1, 1, 2, 3])),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# OptionMetrics: standardized volatility surface (optionm.vsurfd) + OM-CRSP link.
# ---------------------------------------------------------------------------

def build_optionm_vsurf(u: pd.DataFrame) -> pd.DataFrame:
    """Standardized volatility surface: per secid/date, a grid over
    (days, delta, cp_flag) of interpolated implied vols. OptionMetrics US
    coverage starts 1996. We emit month-end snapshots to bound size while
    keeping the real column layout."""
    dates = pd.date_range("1996-01-31", "2012-12-31", freq="ME")
    grid_days = [30, 60, 91, 182]
    grid_delta = [-50, -25, 25, 50]   # OM signs: puts negative, calls positive
    rows = []
    for _, f in u.iterrows():
        if not f["has_options"]:
            continue
        base_iv = float(rng.uniform(0.2, 0.5))
        for d in dates:
            if rng.random() < 0.1:
                continue
            base_iv += float(rng.normal(0, 0.02))
            base_iv = float(np.clip(base_iv, 0.08, 1.2))
            for days in grid_days:
                for delta in grid_delta:
                    cp = "C" if delta > 0 else "P"
                    # smile/term-structure shape
                    iv = base_iv + 0.08 * (abs(delta) < 40) + 0.02 * (days / 91)
                    iv += float(rng.normal(0, 0.01))
                    rows.append({
                        "secid": int(f["secid"]),
                        "date": d.normalize(),
                        "days": days,
                        "delta": delta,
                        "cp_flag": cp,
                        "impl_volatility": round(max(iv, 0.05), 6),
                        "impl_strike": round(abs(f["_p0"]) * float(rng.uniform(0.7, 1.3)), 4),
                        "impl_premium": round(float(rng.uniform(0.2, 8.0)), 4),
                        "dispersion": round(abs(float(rng.normal(0.02, 0.01))), 6),
                    })
    return pd.DataFrame(rows)


def build_optionm_crsp_link(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in u.iterrows():
        if not f["has_options"]:
            continue
        rows.append({
            "secid": int(f["secid"]),
            "permno": int(f["permno"]),
            "sdate": pd.Timestamp("1996-01-01"),
            "edate": pd.Timestamp("2012-12-31"),
            "score": int(rng.choice([1, 1, 2, 6])),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Thomson Reuters 13F institutional holdings (tr_13f-style, permno-keyed).
# ---------------------------------------------------------------------------

def build_tr_13f(u: pd.DataFrame) -> pd.DataFrame:
    quarters = pd.date_range("1990-03-31", "2015-12-31", freq="QE")
    rows = []
    for _, f in u.iterrows():
        level = float(np.clip(rng.normal(0.45, 0.25), 0.0, 0.99))
        for rdate in quarters:
            if rng.random() < 0.1:
                continue
            level = float(np.clip(level + rng.normal(0, 0.05), 0.0, 0.999))
            rows.append({
                "permno": int(f["permno"]),
                "rdate": rdate.normalize(),
                "instown_perc": round(level * 100, 4),
                "maxinstown_perc": round(min(level * 100 + rng.uniform(0, 10), 100), 4),
                "numinstown": int(rng.integers(0, 800)),
                "dbreadth": int(rng.integers(0, 800)),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# NBER patent citations (Hall-Jaffe-Trajtenberg / Bessen), aggregated to
# gvkey-year like the CZ PatentCitations output, plus a raw grant-level table.
# ---------------------------------------------------------------------------

def build_patents_nber(u: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, f in u.iterrows():
        # only innovative firms hold patents
        if rng.random() < 0.5:
            continue
        for gyear in range(1976, 2007):
            npat = int(rng.poisson(3))
            if npat == 0:
                continue
            rows.append({
                "gvkey": f["gvkey"],
                "year": gyear,               # patent GRANT year (not application)
                "npat": npat,
                "ncites": int(rng.poisson(npat * 4)),
                "ncitscale": round(float(rng.uniform(0.5, 3.0)), 4),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Ken French factors (monthly), same layout as scripts/fetch_ff_factors.py.
# ---------------------------------------------------------------------------

def build_ff_factors() -> pd.DataFrame:
    months = pd.period_range(MONTHLY_START, MONTHLY_END, freq="M")
    rows = []
    for m in months:
        rows.append({
            "yyyymm": int(m.strftime("%Y%m")),
            "mktrf": round(float(rng.normal(0.006, 0.045)), 5),
            "smb": round(float(rng.normal(0.002, 0.03)), 5),
            "hml": round(float(rng.normal(0.003, 0.03)), 5),
            "rmw": round(float(rng.normal(0.002, 0.02)), 5),
            "cma": round(float(rng.normal(0.002, 0.02)), 5),
            "umd": round(float(rng.normal(0.006, 0.04)), 5),
            "rf": round(float(abs(rng.normal(0.003, 0.0015))), 5),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    u = build_universe()

    msf = build_crsp_msf(u)
    tables: dict[str, pd.DataFrame] = {
        "crsp_msf":          msf,
        "crsp_msenames":     build_crsp_msenames(u),
        "crsp_msedelist":    build_crsp_msedelist(u, msf),
        "crsp_msedist":      build_crsp_msedist(u),
        "crsp_dsf":          build_crsp_dsf(u),
        "comp_funda":        build_comp_funda(u),
        "comp_fundq":        build_comp_fundq(u),
        "ccm_lnkhist":       build_ccm_lnkhist(u),
        "ibes_statsumu":     build_ibes_statsumu(u),
        "ibes_actu":         build_ibes_actu(u),
        "ibes_crsp_link":    build_ibes_crsp_link(u),
        "optionm_vsurf":     build_optionm_vsurf(u),
        "optionm_crsp_link": build_optionm_crsp_link(u),
        "tr_13f":            build_tr_13f(u),
        "patents_nber":      build_patents_nber(u),
        "ff_factors":        build_ff_factors(),
    }

    # A firm-identifier crosswalk is handy for inspection but is NOT a shortcut
    # for joins — the real link tables above are what code should use.
    u.drop(columns=[c for c in u.columns if c.startswith("_")]).to_parquet(
        OUT_DIR / "_universe_crosswalk.parquet", index=False
    )

    print(f"Wrote synthetic WRDS-style tables to {OUT_DIR}\n")
    for name, df in tables.items():
        df.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
        print(f"  {name:20s} {len(df):>8,d} rows  cols={list(df.columns)}")


if __name__ == "__main__":
    main()
