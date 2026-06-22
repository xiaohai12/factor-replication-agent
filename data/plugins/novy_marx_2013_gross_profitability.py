import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["signal"] = (df["revt"] - df["cogs"]) / df["at"]
    df["signal"] = df["signal"].replace([float("inf"), float("-inf")], pd.NA)

    lower = df["signal"].quantile(0.005)
    upper = df["signal"].quantile(0.995)
    df["signal"] = df["signal"].clip(lower=lower, upper=upper)

    df = df[df["signal"].notna()]

    return df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})


import pandas as pd
import numpy as np


def apply_missing_policy_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = df.copy()

    if "signal" not in out.columns:
        raise ValueError("apply_missing_policy_hook requires a 'signal' column.")

    lower_q = float(config.get("winsorize_lower", 0.01))
    upper_q = float(config.get("winsorize_upper", 0.99))

    if not 0.0 <= lower_q < upper_q <= 1.0:
        raise ValueError("winsorize quantiles must satisfy 0 <= lower < upper <= 1.")

    valid = out["signal"].notna() & np.isfinite(out["signal"])
    out = out.loc[valid].copy()

    if "yyyymm" in out.columns:
        def _clip_group(s: pd.Series) -> pd.Series:
            if s.empty:
                return s
            lo = s.quantile(lower_q)
            hi = s.quantile(upper_q)
            return s.clip(lower=lo, upper=hi)

        out["signal"] = out.groupby("yyyymm", group_keys=False)["signal"].apply(_clip_group)
    else:
        lo = out["signal"].quantile(lower_q)
        hi = out["signal"].quantile(upper_q)
        out["signal"] = out["signal"].clip(lower=lo, upper=hi)

    return out


def compute_returns_hook(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    required = {"yyyymm", "portfolio", "ret", "me"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_returns_hook missing required columns: {sorted(missing)}")

    out = df.copy()
    out = out.loc[
        out["yyyymm"].notna()
        & out["portfolio"].notna()
        & out["ret"].notna()
        & np.isfinite(out["ret"])
    ].copy()

    cap = float(config.get("weight_cap", 0.05))
    if cap <= 0:
        raise ValueError("weight_cap must be positive for capped_vw weighting.")

    def _portfolio_return(g: pd.DataFrame) -> float:
        weights = pd.to_numeric(g["me"], errors="coerce").to_numpy(dtype=float)
        rets = pd.to_numeric(g["ret"], errors="coerce").to_numpy(dtype=float)

        valid = np.isfinite(weights) & (weights > 0) & np.isfinite(rets)
        if not valid.any():
            return float(np.nan)

        weights = weights[valid]
        rets = rets[valid]

        weights = weights / weights.sum()
        weights = np.minimum(weights, cap)

        total = weights.sum()
        if total <= 0:
            weights = np.repeat(1.0 / len(rets), len(rets))
        else:
            weights = weights / total

        return float(np.dot(weights, rets))

    result = (
        out.groupby(["yyyymm", "portfolio"], as_index=False)
        .apply(lambda g: pd.Series({"ret": _portfolio_return(g)}))
        .reset_index(drop=True)
    )

    return result[["yyyymm", "portfolio", "ret"]]