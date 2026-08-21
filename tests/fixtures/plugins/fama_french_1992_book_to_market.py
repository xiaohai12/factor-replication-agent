import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal"] = df["ceq"] / df["me"]
    df["signal"] = df["signal"].replace([float("inf"), float("-inf")], pd.NA)
    df = df[
        df["ceq"].notna()
        & df["me"].notna()
        & (df["ceq"] > 0)
        & (df["me"] > 0)
        & df["signal"].notna()
    ]
    return df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})