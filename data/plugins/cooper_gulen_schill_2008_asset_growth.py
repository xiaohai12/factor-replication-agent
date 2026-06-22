import numpy as np
import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    annual = (
        df.loc[df["at"].notna(), ["permno", "time_avail_m", "at"]]
        .sort_values(["permno", "time_avail_m"])
        .drop_duplicates(subset=["permno", "time_avail_m"], keep="last")
    )

    annual["at_t_minus_1"] = annual.groupby("permno")["at"].shift(0)
    annual["at_t_minus_2"] = annual.groupby("permno")["at"].shift(1)

    annual["signal"] = (
        (annual["at_t_minus_1"] - annual["at_t_minus_2"]) / annual["at_t_minus_2"]
    )

    annual = annual[
        annual["at_t_minus_1"].notna()
        & annual["at_t_minus_2"].notna()
        & (annual["at_t_minus_1"] != 0)
        & (annual["at_t_minus_2"] != 0)
    ].copy()

    annual["month"] = annual["time_avail_m"] % 100
    annual = annual[annual["month"] == 6].copy()

    annual = annual.replace([np.inf, -np.inf], np.nan)
    annual = annual[annual["signal"].notna()]

    result = annual[["permno", "time_avail_m", "signal"]].rename(
        columns={"time_avail_m": "yyyymm"}
    )
    return result[["permno", "yyyymm", "signal"]]