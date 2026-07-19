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


import numpy as np


def apply_missing_policy_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = df.copy()

    numeric_cols = [
        "signal",
        "ret",
        "me",
        "act",
        "lct",
        "che",
        "dlc",
        "dp",
        "at",
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
            out.loc[~np.isfinite(out[col]), col] = np.nan

    missing_action = config.get("missing_action", "drop")
    if missing_action != "winsorize":
        if "ret" in out.columns:
            return out.dropna(subset=["ret"]).copy()
        return out

    lower_q = 0.01
    upper_q = 0.99
    winsor_cols = [col for col in ["act", "lct", "che", "dlc", "dp", "at", "signal"] if col in out.columns]

    def _clip_col(s: pd.Series) -> pd.Series:
        non_missing = s.dropna()
        if non_missing.empty:
            return s
        lower = non_missing.quantile(lower_q)
        upper = non_missing.quantile(upper_q)
        return s.clip(lower=lower, upper=upper)

    if "yyyymm" in out.columns:
        for col in winsor_cols:
            out[col] = out.groupby("yyyymm")[col].transform(_clip_col)
    else:
        for col in winsor_cols:
            out[col] = _clip_col(out[col])

    if "ret" in out.columns:
        out = out.dropna(subset=["ret"]).copy()

    return out