import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["permno", "time_avail_m"])

    gross_ret = 1.0 + df["ret"]
    df["signal"] = (
        gross_ret.groupby(df["permno"])
        .shift(2)
        .groupby(df["permno"])
        .rolling(window=11, min_periods=11)
        .apply(lambda x: x.prod(), raw=False)
        .reset_index(level=0, drop=True)
        - 1.0
    )

    result = df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})
    result = result[result["signal"].notna()]
    result = result[~result["signal"].isin([float("inf"), float("-inf")])]
    return result[["permno", "yyyymm", "signal"]]