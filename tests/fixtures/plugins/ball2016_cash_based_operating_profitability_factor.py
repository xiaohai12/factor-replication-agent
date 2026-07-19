import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["permno", "time_avail_m"])

    for col in ["xrd", "xpp", "drc", "drlt", "xacc"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    df["drc_drlt"] = df["drc"] + df["drlt"]

    grouped = df.groupby("permno", sort=False)
    df["delta_rect"] = grouped["rect"].diff(1)
    df["delta_invt"] = grouped["invt"].diff(1)
    df["delta_xpp"] = grouped["xpp"].diff(1)
    df["delta_drc_drlt"] = grouped["drc_drlt"].diff(1)
    df["delta_ap"] = grouped["ap"].diff(1)
    df["delta_xacc"] = grouped["xacc"].diff(1)
    df["at_lag1"] = grouped["at"].shift(1)

    numerator = (
        df["revt"]
        - df["cogs"]
        - (df["xsga"] - df["xrd"])
        - df["delta_rect"]
        - df["delta_invt"]
        - df["delta_xpp"]
        + df["delta_drc_drlt"]
        + df["delta_ap"]
        + df["delta_xacc"]
    )

    df["signal"] = numerator / df["at_lag1"]
    df["signal"] = df["signal"].replace([pd.NA, pd.NaT, float("inf"), float("-inf")], pd.NA)

    result = df.loc[df["signal"].notna(), ["permno", "time_avail_m", "signal"]].rename(
        columns={"time_avail_m": "yyyymm"}
    )
    return result[["permno", "yyyymm", "signal"]]


import numpy as np


def compute_breakpoints_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """2x3 independent sort: size (median NYSE) x cash-based operating
    profitability (30th/70th NYSE percentile), per Ball et al. (2016) Section 5.

    Portfolio numbering (matches assign_portfolios_hook below):
      1=small-weak 2=small-mid 3=small-robust 4=big-weak 5=big-mid 6=big-robust
    """
    n = int(config["breakpoint_quantiles"])
    qcols = [f"q{i}" for i in range(n + 1)]

    work = df.dropna(subset=["me", "signal"]).copy()
    nyse = work.loc[work["exchcd"] == 1]

    records = []
    for yyyymm, grp in nyse.groupby("yyyymm", sort=True):
        size_median = grp["me"].median()
        prof_30 = grp["signal"].quantile(0.30)
        prof_70 = grp["signal"].quantile(0.70)

        row = {col: np.nan for col in qcols}
        if n >= 0:
            row["q0"] = -np.inf
        if n >= 1:
            row["q1"] = size_median
        if n >= 2:
            row["q2"] = prof_30
        if n >= 3:
            row["q3"] = prof_70
        for extra in range(4, n + 1):
            row[f"q{extra}"] = np.inf
        row["yyyymm"] = yyyymm
        records.append(row)

    if not records:
        return pd.DataFrame(columns=qcols).rename_axis("yyyymm")

    out = pd.DataFrame.from_records(records).set_index("yyyymm").sort_index()
    return out[qcols]


def assign_portfolios_hook(df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict) -> pd.DataFrame:
    work = df.dropna(subset=["me", "signal"]).copy()

    merged = work.merge(
        breakpoints.reset_index(),
        on="yyyymm",
        how="left",
        validate="many_to_one",
    )
    merged = merged.dropna(subset=["q1", "q2", "q3"]).copy()

    size_small = merged["me"] <= merged["q1"]
    weak = merged["signal"] <= merged["q2"]
    mid = (merged["signal"] > merged["q2"]) & (merged["signal"] <= merged["q3"])
    robust = merged["signal"] > merged["q3"]

    portfolio = np.select(
        [
            size_small & weak,
            size_small & mid,
            size_small & robust,
            (~size_small) & weak,
            (~size_small) & mid,
            (~size_small) & robust,
        ],
        [1, 2, 3, 4, 5, 6],
        default=np.nan,
    )

    merged["portfolio"] = portfolio
    merged = merged.dropna(subset=["portfolio"]).copy()
    merged["portfolio"] = merged["portfolio"].astype(int)
    return merged


def compute_long_short_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """RMW_CbOP = 0.5*(small-robust + big-robust) - 0.5*(small-weak + big-weak).

    Middle-profitability portfolios (2, 5) are computed for VW returns but not
    used in the factor spread, matching the paper's robust-minus-weak
    construction (Section 5).
    """
    rows = []
    for yyyymm, g in df.groupby("yyyymm"):
        port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
        required = (1, 3, 4, 6)
        if all(p in port_map for p in required):
            robust_avg = 0.5 * (port_map[3] + port_map[6])
            weak_avg = 0.5 * (port_map[1] + port_map[4])
            rows.append({"yyyymm": yyyymm, "ls_return": robust_avg - weak_avg})
    return pd.DataFrame(rows)