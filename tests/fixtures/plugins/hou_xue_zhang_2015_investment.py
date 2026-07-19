import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["permno", "time_avail_m"])
    df["at_lag1"] = df.groupby("permno")["at"].shift(1)
    df["signal"] = (df["at"] - df["at_lag1"]) / df["at_lag1"]
    df = df[df["at"].notna() & df["at_lag1"].notna() & (df["at_lag1"] != 0)]
    df["signal"] = df["signal"].replace([float("inf"), float("-inf")], pd.NA)
    df = df[df["signal"].notna()]
    return df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})


import pandas as pd
import numpy as np

def filter_universe_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = df.copy()

    is_common = out["shrcd"].isin([10, 11])
    is_major_exchange = out["exchcd"].isin([1, 2, 3])
    sic = out["siccd"]
    is_nonfinancial = sic.isna() | ~sic.between(6000, 6999)
    has_me = out["me"].notna() & np.isfinite(out["me"]) & (out["me"] > 0)

    base = out.loc[is_common & is_major_exchange & is_nonfinancial & has_me].copy()

    nyse_mask = base["exchcd"] == 1
    nyse_breakpoints = (
        base.loc[nyse_mask]
        .groupby("yyyymm")["me"]
        .quantile(0.20)
        .rename("nyse_microcap_cutoff")
    )

    base = base.merge(nyse_breakpoints, on="yyyymm", how="left")
    keep_microcap_screen = base["nyse_microcap_cutoff"].isna() | (base["me"] >= base["nyse_microcap_cutoff"])
    base = base.loc[keep_microcap_screen].drop(columns=["nyse_microcap_cutoff"])

    return base