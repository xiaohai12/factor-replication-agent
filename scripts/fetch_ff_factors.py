#!/usr/bin/env python3
"""Fetch Fama-French factor returns + risk-free rate from the Ken French Data
Library and snapshot them to parquet (plan.md Phase 2).

Build-time only: run this once (or whenever you want to refresh the factor
data), never at backtest run time -- BacktestExecutor only ever reads the
parquet this script writes, so a run's numbers stay reproducible even if
Ken French's site is unreachable later. Requires the `pandas-datareader`
dev dependency (see pyproject.toml) -- NOT a runtime dependency.

Usage:
    python3 scripts/fetch_ff_factors.py [--out data/local/ff_factors.parquet]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def fetch_ff_factors(start: str = "1960-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch monthly FF3 (Mkt-RF, SMB, HML, RF) + momentum (UMD) and merge
    into one DataFrame keyed on `yyyymm`. FF5 (RMW, CMA) is included too when
    available (Ken French's FF5 series starts in 1963).

    Returns columns: yyyymm, mktrf, smb, hml, rmw, cma, umd, rf (values as
    decimals, e.g. 0.0123 for 1.23% -- Ken French publishes these as
    percentages, so this divides by 100).
    """
    import pandas_datareader.data as web

    ff3 = web.DataReader("F-F_Research_Data_Factors", "famafrench", start=start, end=end)[0]
    ff3 = ff3.rename(columns={"Mkt-RF": "mktrf", "SMB": "smb", "HML": "hml", "RF": "rf"})

    ff5 = web.DataReader("F-F_Research_Data_5_Factors_2x3", "famafrench", start=start, end=end)[0]
    ff5 = ff5.rename(columns={"RMW": "rmw", "CMA": "cma"})[["rmw", "cma"]]

    umd = web.DataReader("F-F_Momentum_Factor", "famafrench", start=start, end=end)[0]
    umd.columns = ["umd"]

    merged = ff3.join(ff5, how="left").join(umd, how="left")
    merged = merged / 100.0  # Ken French publishes percentages

    merged = merged.reset_index()
    merged["yyyymm"] = merged["Date"].astype(str).str.replace("-", "").str[:6].astype(int)
    return merged.drop(columns=["Date"])[
        ["yyyymm", "mktrf", "smb", "hml", "rmw", "cma", "umd", "rf"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/local/ff_factors.parquet")
    parser.add_argument("--start", default="1960-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    df = fetch_ff_factors(start=args.start, end=args.end)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df):,} months of FF factor data to {out_path}")
    print(df.head())


if __name__ == "__main__":
    main()
