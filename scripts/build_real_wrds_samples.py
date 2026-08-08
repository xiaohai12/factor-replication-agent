"""Regenerate the ID-aligned real-data samples used for Step4 validation from
the actual full-size WRDS exports in `data/local/` (gitignored,
developer-local -- see tests/test_real_wrds_samples_e2e.py).

Writes EVERYTHING this script produces into `data/local/validation_sample/`
-- CRSP_STOCK_MONTH, CRSP_DELISTING, CRSP_COMPUSTAT_LINK,
COMPUSTAT_FUNDAMENTALS_ANNUAL, IBES_CRSP_Link, plus IBES
(summary/actual/recommendation-detail) and 13F, all aligned to the SAME
50-PERMNO set (IBES via IBES_CRSP_Link's direct PERMNO<->TICKER mapping,
13F via the PERMNOs' own CRSP CUSIP column). This directory is the ONE
place validation-purpose sample data lives.

ALSO materializes `crsp_msf.parquet`/`comp_funda.parquet`/
`ccm_lnkhist.parquet` directly in this same directory (no nested `local/`
subfolder needed at all -- every real consumer checks for
`<storage_path>/<name>.parquet` BEFORE any raw-CSV fallback), so a snapshot
registered with `storage_path=data/local/validation_sample` works exactly
like the existing `synthetic_demo_v1` snapshot -- the OFFICIALLY documented
"frozen parquet snapshot" layout (docs/architecture.md), just built from
real (sampled) WRDS data instead of synthetic data.

`data/local/samples/` is a SEPARATE, older directory left completely
untouched by this script -- it holds reference/exploratory data ("what does
this data source look like") the user keeps around for that purpose, not
for driving any validation/test path. Do not write into it here.

Selection: picks `--n-ids` (default 50) PERMNOs with the LONGEST real
monthly-return time span (max YYYYMM - min YYYYMM) that also have at least
`--min-months` (default 60, i.e. 5 years) of actual observations, so the
sample genuinely covers a long, non-sparse history -- not just a wide but
mostly-empty date range. Link/lookup tables (CRSP_COMPUSTAT_LINK,
IBES_CRSP_Link) are copied in FULL, not filtered -- they're small ID-mapping
tables (tens of MB, not GB), so trimming them buys negligible load-time
savings while limiting which PERMNO/GVKEY pairs are resolvable if the
sample set is ever extended later.

Usage:
    .venv/bin/python3 scripts/build_real_wrds_samples.py --n-ids 50
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
LOCAL_DIR = REPO_ROOT / "data" / "local"

VALIDATION_SAMPLE_DIR = LOCAL_DIR / "validation_sample"

CRSP_MONTH = LOCAL_DIR / "CRSP_STOCK_MONTH.csv"
CRSP_DELISTING = LOCAL_DIR / "CRSP_DELISTING.csv"
CRSP_LINK = LOCAL_DIR / "CRSP_COMPUSTAT_LINK.csv"
IBES_CRSP_LINK = LOCAL_DIR / "IBES_CRSP_Link.csv"
COMPUSTAT_ANNUAL = LOCAL_DIR / "COMPUSTAT_FUNDAMENTALS_ANNUAL.csv"
IBES_SUMMARY = LOCAL_DIR / "IBES_UNADJUSTED_SUMMARY.csv"
IBES_ACTUAL = LOCAL_DIR / "IBES_UNADJUSTED_ACTURAL.csv"
IBES_RECOMMENDATION = LOCAL_DIR / "IBES_RECOMMENDATION_DETAIL.csv"
THIRTEEN_F = LOCAL_DIR / "13F.csv"

CHUNK_ROWS = 500_000


def select_long_history_permnos(n_ids: int, min_months: int) -> list[int]:
    """First pass over CRSP_STOCK_MONTH.csv (PERMNO, YYYYMM only) to find the
    `n_ids` PERMNOs with the longest real time span and enough actual monthly
    observations to be a genuinely long, non-sparse history."""
    counts: dict[int, int] = {}
    mins: dict[int, int] = {}
    maxs: dict[int, int] = {}
    for chunk in pd.read_csv(CRSP_MONTH, usecols=["PERMNO", "YYYYMM"], chunksize=CHUNK_ROWS):
        for permno, grp in chunk.groupby("PERMNO"):
            n = len(grp)
            lo, hi = int(grp["YYYYMM"].min()), int(grp["YYYYMM"].max())
            counts[permno] = counts.get(permno, 0) + n
            mins[permno] = min(mins.get(permno, lo), lo)
            maxs[permno] = max(maxs.get(permno, hi), hi)

    def yyyymm_span(lo: int, hi: int) -> int:
        return (hi // 100 - lo // 100) * 12 + (hi % 100 - lo % 100)

    candidates = [
        (permno, yyyymm_span(mins[permno], maxs[permno]))
        for permno, n in counts.items()
        if n >= min_months
    ]
    candidates.sort(key=lambda t: t[1], reverse=True)
    selected = [permno for permno, _span in candidates[:n_ids]]
    print(f"Selected {len(selected)} PERMNOs (of {len(counts)} candidates with >= {min_months} months)")
    if selected:
        top_span = dict(candidates[: len(selected)])
        print(f"  span range: {min(top_span.values())} - {max(top_span.values())} months")
    return selected


def filter_large_csv_by_column(src: Path, dst: Path, column: str, keep_values: set) -> int:
    """Streams `src` in chunks, keeping only rows whose `column` value is in
    `keep_values`, writing the header once then appending matching rows."""
    total = 0
    wrote_header = False
    dst.parent.mkdir(parents=True, exist_ok=True)
    for chunk in pd.read_csv(src, dtype={column: str}, chunksize=CHUNK_ROWS):
        matched = chunk[chunk[column].isin(keep_values)]
        if matched.empty:
            continue
        matched.to_csv(dst, mode="a" if wrote_header else "w", header=not wrote_header, index=False)
        wrote_header = True
        total += len(matched)
    if not wrote_header:
        # No rows matched anything -- still write an empty file with the header.
        pd.read_csv(src, nrows=0).to_csv(dst, index=False)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-ids", type=int, default=50)
    parser.add_argument("--min-months", type=int, default=60)
    args = parser.parse_args()

    for required in (CRSP_MONTH, CRSP_DELISTING, CRSP_LINK, COMPUSTAT_ANNUAL):
        if not required.exists():
            print(f"Missing required real WRDS export: {required} -- aborting.")
            return 1
    VALIDATION_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Pass 1: selecting long-history PERMNOs from CRSP_STOCK_MONTH.csv ===")
    permnos = select_long_history_permnos(args.n_ids, args.min_months)
    if not permnos:
        print("No PERMNOs met the selection criteria -- aborting.")
        return 1
    permno_strs = {str(p) for p in permnos}

    print("=== Pass 2: CRSP_STOCK_MONTH_sample.csv ===")
    n = filter_large_csv_by_column(
        CRSP_MONTH, VALIDATION_SAMPLE_DIR / "CRSP_STOCK_MONTH_sample.csv", "PERMNO", permno_strs
    )
    print(f"  wrote {n:,} rows")

    print("=== CRSP_DELISTING_sample.csv ===")
    n = filter_large_csv_by_column(
        CRSP_DELISTING, VALIDATION_SAMPLE_DIR / "CRSP_DELISTING_sample.csv", "PERMNO", permno_strs
    )
    print(f"  wrote {n:,} rows")

    print("=== CRSP_COMPUSTAT_LINK_sample.csv ===")
    # Link/lookup tables (ID mappings, not per-company time series) are small
    # enough already (49MB / 110k rows here) that filtering them down buys
    # essentially nothing in load time, but DOES limit which PERMNO/GVKEY
    # pairs are resolvable if the sample set is ever extended later. Copy
    # the FULL table instead of a filtered subset.
    link_df = pd.read_csv(CRSP_LINK, dtype={"LPERMNO": str, "gvkey": str}, low_memory=False)
    link_df.to_csv(VALIDATION_SAMPLE_DIR / "CRSP_COMPUSTAT_LINK_sample.csv", index=False)
    print(f"  wrote full table ({len(link_df):,} rows, unfiltered)")
    gvkeys = set(link_df.loc[link_df["LPERMNO"].isin(permno_strs), "gvkey"].dropna().unique())
    print(f"  {len(gvkeys)} distinct GVKEYs linked to the selected PERMNOs")

    print("=== IBES_CRSP_Link_sample.csv ===")
    if IBES_CRSP_LINK.exists():
        ibes_link_df = pd.read_csv(IBES_CRSP_LINK, dtype=str, low_memory=False)
        ibes_link_df.to_csv(VALIDATION_SAMPLE_DIR / "IBES_CRSP_Link_sample.csv", index=False)
        print(f"  wrote full table ({len(ibes_link_df):,} rows, unfiltered)")
    else:
        print(f"  skipped: {IBES_CRSP_LINK} not found")

    print("=== COMPUSTAT_FUNDAMENTALS_ANNUAL_sample.csv ===")
    n = filter_large_csv_by_column(
        COMPUSTAT_ANNUAL, VALIDATION_SAMPLE_DIR / "COMPUSTAT_FUNDAMENTALS_ANNUAL_sample.csv", "gvkey", gvkeys
    )
    print(f"  wrote {n:,} rows")

    # --- IBES / 13F: freshly aligned to the SAME 50 PERMNOs. ---

    print("=== IBES: resolving IBES TICKERs for the selected PERMNOs ===")
    ibes_tickers: set[str] = set()
    if IBES_CRSP_LINK.exists():
        ibes_link_df = pd.read_csv(IBES_CRSP_LINK, dtype=str, low_memory=False)
        ibes_tickers = set(ibes_link_df.loc[ibes_link_df["PERMNO"].isin(permno_strs), "TICKER"].dropna().unique())
        print(f"  {len(ibes_tickers)} distinct IBES TICKERs linked to the selected PERMNOs")
    else:
        print(f"  skipped: {IBES_CRSP_LINK} not found")

    for label, src in (
        ("IBES_UNADJUSTED_SUMMARY_sample.csv", IBES_SUMMARY),
        ("IBES_UNADJUSTED_ACTURAL_sample.csv", IBES_ACTUAL),
        ("IBES_RECOMMENDATION_DETAIL_sample.csv", IBES_RECOMMENDATION),
    ):
        print(f"=== {label} ===")
        if not src.exists():
            print(f"  skipped: {src} not found")
            continue
        if not ibes_tickers:
            print("  skipped: no IBES TICKERs resolved")
            continue
        n = filter_large_csv_by_column(src, VALIDATION_SAMPLE_DIR / label, "TICKER", ibes_tickers)
        print(f"  wrote {n:,} rows")

    print("=== 13F: resolving CUSIPs for the selected PERMNOs (from CRSP_STOCK_MONTH's own CUSIP column) ===")
    crsp_sample = pd.read_csv(VALIDATION_SAMPLE_DIR / "CRSP_STOCK_MONTH_sample.csv", usecols=["CUSIP"], dtype=str)
    cusips = set(crsp_sample["CUSIP"].dropna().unique())
    print(f"  {len(cusips)} distinct CUSIPs")
    print("=== 13F_sample.csv ===")
    if THIRTEEN_F.exists() and cusips:
        n = filter_large_csv_by_column(THIRTEEN_F, VALIDATION_SAMPLE_DIR / "13F_sample.csv", "cusip", cusips)
        print(f"  wrote {n:,} rows")
    else:
        print(f"  skipped: {THIRTEEN_F} not found or no CUSIPs resolved")

    materialize_parquet_snapshot()

    print("Done.")
    return 0


def materialize_parquet_snapshot() -> None:
    """Materializes `crsp_msf.parquet` / `comp_funda.parquet` /
    `ccm_lnkhist.parquet` directly under `VALIDATION_SAMPLE_DIR` -- the
    OFFICIALLY documented "frozen parquet snapshot" layout (see
    docs/architecture.md's "快照布局"), needing NO nested `local/` raw-CSV
    fallback folder at all. Every real consumer already checks for
    `<storage_path>/<name>.parquet` BEFORE falling back to the raw-CSV
    convention (`_load_generic_signal_frame`, `_load_link_tables`, the
    generated backtest script's `load_msf()`), so once these 3 files exist
    here, a snapshot whose storage_path IS `VALIDATION_SAMPLE_DIR` just
    works -- exactly like `synthetic_demo_v1`."""
    from src.infra.data_layer.sources import build_crsp_monthly_panel_ciz

    print("=== Materializing crsp_msf.parquet (frozen parquet snapshot) ===")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "CRSP_STOCK_MONTH.csv").symlink_to(
            (VALIDATION_SAMPLE_DIR / "CRSP_STOCK_MONTH_sample.csv").resolve()
        )
        (tmp_path / "CRSP_DELISTING.csv").symlink_to(
            (VALIDATION_SAMPLE_DIR / "CRSP_DELISTING_sample.csv").resolve()
        )
        panel = build_crsp_monthly_panel_ciz(tmp_path)
    panel.to_parquet(VALIDATION_SAMPLE_DIR / "crsp_msf.parquet", index=False)
    print(f"  wrote {len(panel):,} rows")

    print("=== Materializing comp_funda.parquet ===")
    # Kept in the SAME raw, gvkey-keyed shape a fresh CSV read would produce
    # (lower-cased columns, parsed datadate) -- `_load_generic_signal_frame`'s
    # parquet-first branch still calls `link_to_permno` on it afterward, so
    # this must NOT be pre-linked to permno.
    funda = pd.read_csv(
        VALIDATION_SAMPLE_DIR / "COMPUSTAT_FUNDAMENTALS_ANNUAL_sample.csv", dtype={"gvkey": str}, low_memory=False
    )
    funda.columns = [c.lower() for c in funda.columns]
    funda["datadate"] = pd.to_datetime(funda["datadate"], format="%Y-%m-%d", errors="coerce")
    funda.to_parquet(VALIDATION_SAMPLE_DIR / "comp_funda.parquet", index=False)
    print(f"  wrote {len(funda):,} rows")

    print("=== Materializing ccm_lnkhist.parquet ===")
    link = pd.read_csv(
        VALIDATION_SAMPLE_DIR / "CRSP_COMPUSTAT_LINK_sample.csv", dtype={"gvkey": str}, low_memory=False
    )
    link.columns = [c.lower() for c in link.columns]
    for col in ("linkdt", "linkenddt"):
        link[col] = pd.to_datetime(link[col], format="%Y-%m-%d", errors="coerce")
    link.to_parquet(VALIDATION_SAMPLE_DIR / "ccm_lnkhist.parquet", index=False)
    print(f"  wrote {len(link):,} rows")


if __name__ == "__main__":
    raise SystemExit(main())
