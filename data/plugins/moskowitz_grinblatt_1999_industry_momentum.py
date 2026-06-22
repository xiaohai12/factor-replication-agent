import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    sic_str = df["siccd"].astype("string").str.extract(r"(\d+)")[0]
    df["sic2"] = sic_str.str[:2]
    df["ret"] = pd.to_numeric(df["ret"], errors="coerce")

    df = df[df["ret"].notna() & df["sic2"].notna()]

    df["date"] = pd.to_datetime(df["time_avail_m"].astype(str), format="%Y%m", errors="coerce")
    df = df[df["date"].notna()]

    industry_monthly = (
        df.groupby(["sic2", "date"], as_index=False)["ret"]
        .mean()
        .sort_values(["sic2", "date"])
    )

    industry_monthly["signal"] = (
        industry_monthly.groupby("sic2")["ret"]
        .transform(lambda s: (1.0 + s.shift(2)).rolling(window=11, min_periods=11).apply(lambda x: x.prod(), raw=True) - 1.0)
    )

    df = df.merge(
        industry_monthly[["sic2", "date", "signal"]],
        on=["sic2", "date"],
        how="left",
    )

    df = df[df["signal"].notna()]
    df = df[df["signal"].replace([float("inf"), float("-inf")], pd.NA).notna()]

    result = df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})
    return result[["permno", "yyyymm", "signal"]]


import pandas as pd
import numpy as np


def filter_universe_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = df.copy()

    exch_mask = out["exchcd"].isin([1, 2, 3])
    shrcd_mask = out["shrcd"].isin([10, 11]) if "shrcd" in out.columns else True
    sic_mask = out["siccd"].notna()
    me_mask = out["me"].notna() & np.isfinite(out["me"]) & (out["me"] > 0)

    out = out.loc[exch_mask & shrcd_mask & sic_mask & me_mask].copy()
    return out