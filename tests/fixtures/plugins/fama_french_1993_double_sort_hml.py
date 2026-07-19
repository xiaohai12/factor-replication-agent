import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    preferred_stock = df["pstkl"].where(df["pstkl"].notna(), df["pstkrv"]).fillna(0)
    deferred_taxes = df["txditc"].fillna(0)

    df["be"] = df["ceq"] + deferred_taxes - preferred_stock
    df["signal"] = df["be"] / df["me"]

    mask = (
        df["ceq"].notna()
        & df["me"].notna()
        & (df["me"] != 0)
        & df["signal"].notna()
        & df["signal"].ne(float("inf"))
        & df["signal"].ne(float("-inf"))
    )

    result = df.loc[mask, ["permno", "time_avail_m", "signal"]].rename(
        columns={"time_avail_m": "yyyymm"}
    )
    return result[["permno", "yyyymm", "signal"]]


import pandas as pd
import numpy as np


def _prepare_hml_universe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    txditc = out["txditc"] if "txditc" in out.columns else 0.0
    pstkl = out["pstkl"] if "pstkl" in out.columns else 0.0

    out["book_equity"] = out["ceq"].astype(float) + pd.Series(txditc, index=out.index).fillna(0.0) - pd.Series(pstkl, index=out.index).fillna(0.0)
    out["bm"] = out["book_equity"] / out["me"].astype(float)

    mask = (
        out["me"].notna()
        & (out["me"] > 0)
        & out["book_equity"].notna()
        & (out["book_equity"] > 0)
        & out["bm"].notna()
        & np.isfinite(out["bm"])
    )
    return out.loc[mask].copy()


def compute_breakpoints_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    n = int(config["breakpoint_quantiles"])
    qcols = [f"q{i}" for i in range(n + 1)]

    work = _prepare_hml_universe(df)

    if config.get("breakpoint_source", "nyse") == "nyse":
        bp_universe = work.loc[work["exchcd"] == 1].copy()
    else:
        bp_universe = work.copy()

    records = []
    for yyyymm, grp in bp_universe.groupby("yyyymm", sort=True):
        size_median = grp["me"].median()
        bm30 = grp["bm"].quantile(0.3)
        bm70 = grp["bm"].quantile(0.7)

        row = {col: np.nan for col in qcols}
        if n >= 0:
            row["q0"] = -np.inf
        if n >= 1:
            row["q1"] = size_median
        if n >= 2:
            row["q2"] = bm30
        if n >= 3:
            row["q3"] = bm70
        if n >= 4:
            row["q4"] = np.inf
        if n >= 5:
            row["q5"] = np.inf
        if n >= 6:
            row["q6"] = np.inf

        row["yyyymm"] = yyyymm
        records.append(row)

    if not records:
        return pd.DataFrame(columns=qcols).rename_axis("yyyymm")

    out = pd.DataFrame.from_records(records).set_index("yyyymm").sort_index()
    return out[qcols]


def assign_portfolios_hook(df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict) -> pd.DataFrame:
    work = _prepare_hml_universe(df)

    merged = work.merge(
        breakpoints.reset_index(),
        on="yyyymm",
        how="left",
        validate="many_to_one",
    )

    required_cols = ["q1", "q2", "q3"]
    merged = merged.dropna(subset=required_cols).copy()

    size_small = merged["me"] <= merged["q1"]
    bm_low = merged["bm"] <= merged["q2"]
    bm_mid = (merged["bm"] > merged["q2"]) & (merged["bm"] <= merged["q3"])
    bm_high = merged["bm"] > merged["q3"]

    portfolio = np.select(
        [
            size_small & bm_low,
            size_small & bm_mid,
            size_small & bm_high,
            (~size_small) & bm_low,
            (~size_small) & bm_mid,
            (~size_small) & bm_high,
        ],
        [1, 2, 3, 4, 5, 6],
        default=np.nan,
    )

    merged["portfolio"] = portfolio
    merged = merged.dropna(subset=["portfolio"]).copy()
    merged["portfolio"] = merged["portfolio"].astype(int)

    return merged