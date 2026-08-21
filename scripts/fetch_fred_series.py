#!/usr/bin/env python3
"""Fetch a FRED macro series and snapshot it to parquet for reproducible use
as a "time_only" (non-permno-keyed, market-wide) SIGNAL_INPUT -- see
`src.infra.data_layer.sources.MacroSignalSource`.

Build-time only: run this once (or whenever you want to refresh the series),
never at backtest run time -- `MacroSignalSource.load()` only ever reads the
parquet this script writes, so a run's numbers stay reproducible even if
FRED is unreachable later. Requires the `pandas-datareader` dev dependency
(see pyproject.toml) -- NOT a runtime dependency, same as `fetch_ff_factors.py`.

Default series: GDPDEF (GDP Implicit Price Deflator), registered as the
`fred_gdp_deflator` data source (substitute for Ohlson's O-score GNP
price-level index -- see that source's `description`).

Usage:
    python3 scripts/fetch_fred_series.py [--series GDPDEF] [--out data/local/gdp_deflator.parquet]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def fetch_fred_series(series: str = "GDPDEF", start: str = "1947-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch a FRED series and expand it to monthly `[yyyymm, value]`.

    GDPDEF (and most FRED national-accounts series) is published quarterly.
    Expanding to monthly by forward-filling each quarter's value across its
    3 months is the simplest sane choice for a plain deflator index (it
    changes slowly and isn't itself the signal, just a scaling denominator)
    -- the tradeoff is that the same value repeats for 3 months rather than
    interpolating a smoother monthly path.
    """
    import pandas_datareader.data as web

    raw = web.DataReader(series, "fred", start=start, end=end)
    raw = raw.rename(columns={series: "value"}).dropna()

    monthly = raw.resample("MS").ffill()
    # A quarterly series left-stamped at quarter-start needs 2 extra monthly
    # rows forward-filled per quarter (resample("MS") alone only inserts the
    # start-of-quarter month already present in `raw`).
    monthly = monthly.reindex(
        pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    ).ffill()

    out = monthly.reset_index().rename(columns={"index": "date", "DATE": "date"})
    out["yyyymm"] = out["date"].dt.year * 100 + out["date"].dt.month
    return out[["yyyymm", "value"]].astype({"yyyymm": int})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default="GDPDEF")
    parser.add_argument("--out", default="data/local/gdp_deflator.parquet")
    parser.add_argument("--start", default="1947-01-01")
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    df = fetch_fred_series(args.series, start=args.start, end=args.end)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df):,} months of {args.series} to {out_path}")
    print(df.head())


if __name__ == "__main__":
    main()
