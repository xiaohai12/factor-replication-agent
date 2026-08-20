"""HXZ (Hou-Xue-Zhang) external reference for the `standardized_hxz` track's
"Reported (reference)" column -- mirrors what `cz_bridge.py`/`CZReferenceProfile`
do for C&Z, but for HXZ's own published testing-portfolio data instead of
SignalDoc metadata.

Scope: HXZ never published per-factor signal CODE (see docs/step6.md's "H is
not a signal source" note) -- but their public data library
(global-q.org/testingportfolios.html) DOES publish the actual decile-sorted,
NYSE-breakpoint, value-weighted MONTHLY portfolio returns their own paper's
t-stats were computed from. This module reads one such downloaded file
(`data/hxz/return_ref/portf_ia_monthly_2025.csv`, the Investment-to-Assets /
"asset growth" anomaly -- HXZ's `ia` acronym) and recomputes a long-short
mean return + Newey-West t-stat from it, restricted to a given in-sample
window, using the SAME `_series_metrics` the engine's own backtests use.

Asset Growth (`ia`) and Gross Profitability (`GP`, HXZ's `gpa` acronym) are
wired up today, one HXZ testing-portfolio file per factor under
`data/hxz/return_ref/`. Extending to another factor means dropping its
`portf_<acronym>_monthly_2025.csv` next to them and adding an entry to
`HXZ_REPORTED_FACTORS` below -- not writing a new function.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_RETURN_REF_DIR = Path(__file__).resolve().parents[3] / "data" / "hxz" / "return_ref"

# HXZ's own "Replicating Anomalies" (2020, RFS) paper's in-sample window --
# a SEPARATE reference point from the replicated factor's own paper window,
# never used as a default (see `compute_hxz_reported`'s docstring). Confirmed
# via the paper's own slides (slides_replication_2021may.pdf) and full text
# ("Updating Fama and French (2008, Table I) in our 1967-2016 sample").
HXZ_PAPER_SAMPLE_START_YEAR = 1967
HXZ_PAPER_SAMPLE_END_YEAR = 2016


@dataclass(frozen=True)
class HxzReportedFactor:
    """One HXZ testing-portfolio file wired up for the reference column.

    `low_rank`/`high_rank` pick the two deciles that make up the long-short
    spread (1 = lowest signal decile, 10 = highest); `long_rank` is which of
    the two is the LONG leg, so the sign matches how the anomaly is
    conventionally reported (asset growth predicts returns negatively, so
    low I/A is long, high I/A is short)."""

    csv_filename: str
    rank_column: str
    long_rank: int
    short_rank: int
    label: str


HXZ_REPORTED_FACTORS: dict[str, HxzReportedFactor] = {
    "AssetGrowth": HxzReportedFactor(
        csv_filename="portf_ia_monthly_2025.csv",
        rank_column="rank_IA",
        long_rank=1,
        short_rank=10,
        label="HXZ (low I/A − high I/A)",
    ),
    "GP": HxzReportedFactor(
        csv_filename="portf_gpa_monthly_2025.csv",
        rank_column="rank_GPA",
        long_rank=10,
        short_rank=1,
        label="HXZ (high GP/A − low GP/A)",
    ),
    "Mom6m": HxzReportedFactor(
        csv_filename="portf_r6_6_monthly_2025.csv",
        rank_column="rank_R6_6",
        long_rank=10,
        short_rank=1,
        label="HXZ (high R6_6 − low R6_6)",
    ),
}


def _manual_hxz_fallback(
    acronym: str, sample_start_year: int | None, sample_end_year: int | None
) -> dict[str, float | int | str | None] | None:
    fallback = MANUAL_HXZ_REPORTED_FALLBACK.get(acronym)
    if fallback is None:
        return None
    return {
        "mean_return": fallback["mean_return"],
        "t_stat": fallback["t_stat"],
        "n_months": None,
        "start_year": sample_start_year,
        "end_year": sample_end_year,
        "label": fallback["label"],
    }


def _load_decile_returns(csv_path: Path, rank_column: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"year", "month", rank_column, "ret_vw"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing expected column(s): {sorted(missing)}")
    return df


# Manual paper-reported fallback for a factor with no HXZ testing-portfolio
# CSV under `data/hxz/return_ref/` -- filled in from the paper's own stated
# HXZ-protocol result, one factor at a time, never guessed. Used by
# `compute_hxz_reported` only when no CSV-derived number is available, so a
# real recomputed CSV number always wins over this fallback.
MANUAL_HXZ_REPORTED_FALLBACK: dict[str, dict[str, float | str]] = {
    "PS": {"mean_return": 0.0029, "t_stat": 1.11, "label": "HXZ (paper-reported, no testing-portfolio CSV)"},
}


def compute_hxz_reported(
    acronym: str,
    sample_start_year: int | None = None,
    sample_end_year: int | None = None,
    return_ref_dir: Path | None = None,
) -> dict[str, float | int | str | None] | None:
    """Long-short mean return + Newey-West t-stat for `acronym`'s HXZ
    testing-portfolio decile spread, restricted to
    `[sample_start_year, sample_end_year]` inclusive. Pass the REPLICATED
    factor's OWN paper sample window here (`MethodSpec.sample.reported_
    returns.start_year/end_year` -- the SAME window ①'s `paperReported`
    number is scoped to), NOT HXZ's own paper's window -- the point of this
    number is comparing HXZ's protocol against the paper's own result on
    the paper's own dates, not HXZ's. `None`/`None` = the full downloaded
    CSV range (1967 through whatever global-q.org's latest update covers).
    Returns `None` if `acronym` isn't wired up (see `HXZ_REPORTED_FACTORS`)
    or its CSV file isn't present on disk.

    Mirrors `BacktestExecutor._series_metrics` (Newey-West, up to 6 lags) so
    this number sits on the same statistical basis as every other track's
    `t_stat` in the step6 comparison table -- imported lazily to avoid a
    hard dependency from this reference module onto the backtest engine.
    """
    factor = HXZ_REPORTED_FACTORS.get(acronym)
    if factor is None:
        return _manual_hxz_fallback(acronym, sample_start_year, sample_end_year)
    csv_path = (return_ref_dir or _RETURN_REF_DIR) / factor.csv_filename
    if not csv_path.is_file():
        return _manual_hxz_fallback(acronym, sample_start_year, sample_end_year)

    df = _load_decile_returns(csv_path, factor.rank_column)
    if sample_start_year is not None:
        df = df[df["year"] >= sample_start_year]
    if sample_end_year is not None:
        df = df[df["year"] <= sample_end_year]
    if df.empty:
        return {"mean_return": None, "t_stat": None, "n_months": 0, "start_year": sample_start_year, "end_year": sample_end_year, "label": factor.label}
    # Echo the ACTUAL data-derived bounds when the caller passed `None`
    # (full-range request) -- so the UI always shows a concrete window,
    # not a blank one.
    actual_start_year = sample_start_year if sample_start_year is not None else int(df["year"].min())
    actual_end_year = sample_end_year if sample_end_year is not None else int(df["year"].max())

    long_leg = df[df[factor.rank_column] == factor.long_rank].set_index(["year", "month"])["ret_vw"]
    short_leg = df[df[factor.rank_column] == factor.short_rank].set_index(["year", "month"])["ret_vw"]
    spread = (long_leg - short_leg).dropna() / 100.0  # HXZ reports ret_vw in percent
    if spread.empty:
        return {"mean_return": None, "t_stat": None, "n_months": 0, "start_year": actual_start_year, "end_year": actual_end_year, "label": factor.label}

    from src.infra.backtest_engine import BacktestExecutor

    metrics = BacktestExecutor._series_metrics(spread)
    return {
        "mean_return": metrics["mean_monthly_return"],
        "t_stat": metrics["t_stat"],
        "n_months": metrics["n_months"],
        "start_year": actual_start_year,
        "end_year": actual_end_year,
        "label": factor.label,
    }


def compute_hxz_reported_both_windows(
    acronym: str,
    paper_sample_start_year: int | None,
    paper_sample_end_year: int | None,
    return_ref_dir: Path | None = None,
) -> dict[str, dict | None] | None:
    """Convenience wrapper for the step6 UI: one call returns BOTH the
    replicated factor's own paper window (`original_insample`, using
    `paper_sample_start_year`/`paper_sample_end_year` -- `None`/`None` falls
    back to the full downloaded CSV range) AND HXZ's own "Replicating
    Anomalies" paper window (`hxz_paper_sample`, always
    `HXZ_PAPER_SAMPLE_START_YEAR`-`HXZ_PAPER_SAMPLE_END_YEAR`, regardless of
    what was passed in). Returns `None` if `acronym` isn't wired up.
    """
    if HXZ_REPORTED_FACTORS.get(acronym) is None and acronym not in MANUAL_HXZ_REPORTED_FALLBACK:
        return None
    return {
        "original_insample": compute_hxz_reported(
            acronym, paper_sample_start_year, paper_sample_end_year, return_ref_dir
        ),
        "hxz_paper_sample": compute_hxz_reported(
            acronym, HXZ_PAPER_SAMPLE_START_YEAR, HXZ_PAPER_SAMPLE_END_YEAR, return_ref_dir
        ),
    }
