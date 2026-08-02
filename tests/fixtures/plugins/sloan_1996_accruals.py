import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["permno", "time_avail_m"])

    for col in ["act", "che", "lct", "dlc", "at"]:
        df[f"{col}_lag"] = df.groupby("permno")[col].shift(1)

    delta_ca_ex_cash = (df["act"] - df["act_lag"]) - (df["che"] - df["che_lag"])
    delta_cl_ex_std = (df["lct"] - df["lct_lag"]) - (df["dlc"] - df["dlc_lag"])
    avg_at = (df["at"] + df["at_lag"]) / 2.0

    df["signal"] = (delta_ca_ex_cash - delta_cl_ex_std - df["dp"]) / avg_at

    df["signal"] = df.groupby("time_avail_m")["signal"].transform(
        lambda s: s.clip(lower=s.quantile(0.01), upper=s.quantile(0.99))
    )

    df["signal"] = df["signal"].replace([float("inf"), float("-inf")], pd.NA)
    df = df[df["signal"].notna()]

    return df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})