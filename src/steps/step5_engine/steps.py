"""Standard step implementations for the controlled backtest lifecycle.

Pure, stateless functions: `(df, ..., config) -> df`. No class state — every
step reads only its explicit arguments, so results are fully traceable and a
step can be swapped for an LLM-generated hook of the identical shape (see
`Step` Protocol in `src/steps/step5_engine/__init__.py`) without any special-casing.

Order matches `BacktestEngine.run_with_config()`:
  load_msf -> apply_delisting_returns -> apply_missing_policy ->
  filter_universe -> merge_signal -> neutralize_signal ->
  compute_breakpoints -> assign_portfolios -> compute_returns ->
  compute_long_short -> compute_metrics

`apply_delisting_returns`, `filter_universe`'s universe_filters DSL, and
`neutralize_signal` are the deterministic "ResearchDesign" layer (plan.md
Phase 2.5): sample-construction choices expressed as pure config, never
defaulting to an LLM hook.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def newey_west_var(x: np.ndarray, lags: int) -> float:
    """Newey-West variance estimate for a demeaned series."""
    n = len(x)
    xd = x - x.mean()
    nw = float(np.dot(xd, xd)) / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma = float(np.dot(xd[lag:], xd[:-lag])) / n
        nw += 2.0 * w * gamma
    return max(nw, 0.0)


def load_msf(msf_path: Path) -> pd.DataFrame:
    """Step 1: load the historical monthly stock return data (CRSP)."""
    if not msf_path.exists():
        raise FileNotFoundError(
            f"MSF data not found at {msf_path}. "
            "Export CRSP monthly from WRDS and place it there."
        )
    df = pd.read_parquet(msf_path)
    if "date" in df.columns and "yyyymm" not in df.columns:
        df["yyyymm"] = (
            pd.to_datetime(df["date"]).dt.year * 100
            + pd.to_datetime(df["date"]).dt.month
        )
    for col in ("permno", "yyyymm"):
        df[col] = df[col].astype(int)
    return df


def load_daily_msf(daily_path: Path) -> pd.DataFrame:
    """Load daily CRSP-shaped data (permno, date, ret, prc, shrout, exchcd,
    shrcd, siccd) and compound it into the same monthly-keyed panel the rest
    of the standard pipeline expects (plan.md Phase 6): `ret` becomes the
    compounded monthly return (`prod(1+daily_ret)-1`), `me` is computed from
    the LAST trading day of the month (`|prc|*shrout`), and other identifying
    columns take that last trading day's value. This lets a signal that
    needs daily PRICES as input (e.g. short-term reversal, realized
    volatility, illiquidity) flow through the existing monthly-rebalanced
    engine unchanged, without every other step needing to know about daily
    data at all.

    Documented v1 scope limit: this does NOT implement genuine daily-
    frequency REBALANCING (breakpoints/holding computed at daily
    granularity) -- only "daily source data, monthly output". A full
    daily-rebalanced estimator is out of scope (see plan.md "ext" tier).
    """
    if not daily_path.exists():
        raise FileNotFoundError(
            f"Daily CRSP data not found at {daily_path}. "
            "Export CRSP daily from WRDS and place it there."
        )
    df = pd.read_parquet(daily_path)
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df["permno"] = df["permno"].astype(int)
    df["yyyymm"] = df["date"].dt.year * 100 + df["date"].dt.month
    df = df.sort_values(["permno", "date"])

    monthly_ret = (
        df.groupby(["permno", "yyyymm"])["ret"]
        .apply(lambda g: float((1 + g.fillna(0)).prod() - 1))
        .reset_index(name="ret")
    )

    last_day = df.groupby(["permno", "yyyymm"], as_index=False).tail(1).copy()
    if "prc" in last_day.columns and "shrout" in last_day.columns:
        last_day["me"] = last_day["prc"].abs() * last_day["shrout"]
    keep_cols = [c for c in ("permno", "yyyymm", "me", "exchcd", "shrcd", "siccd") if c in last_day.columns]
    last_day = last_day[keep_cols]

    merged = last_day.merge(monthly_ret, on=["permno", "yyyymm"], how="left")
    for col in ("permno", "yyyymm"):
        merged[col] = merged[col].astype(int)
    return merged


def apply_excess_returns(df: pd.DataFrame, factors: pd.DataFrame | None, config: dict) -> pd.DataFrame:
    """Convert raw returns to excess-of-risk-free returns (plan.md Phase 6),
    when `config["return_basis"] == "excess"` (the canonical v1 default) and
    risk-free-rate data is available via `factors` (the same FF-factor
    DataFrame `compute_factor_alphas` uses -- see
    `scripts/fetch_ff_factors.py`). No-op when `factors` is None/missing an
    `rf` column, or when `config["return_basis"] == "raw"` is explicitly
    requested (e.g. for an ablation). Note: for the standard long-short
    spread this makes no numeric difference (`rf` cancels in `long - short`)
    -- it matters for `single_signal_portfolio_return`/`full_portfolio_return`
    single-leg modes, which do NOT have rf canceled out (see plan.md Phase 2
    "Deferred" note).
    """
    if config.get("return_basis", "excess") != "excess":
        return df
    if factors is None or "rf" not in factors.columns:
        return df
    rf = factors[["yyyymm", "rf"]]
    merged = df.merge(rf, on="yyyymm", how="left")
    merged["ret"] = merged["ret"] - merged["rf"].fillna(0)
    return merged.drop(columns=["rf"])


def apply_delisting_returns(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Deterministic ResearchDesign step (plan.md Phase 2.5): fold CRSP
    delisting returns into `ret` when a `dlret` column is present, via the
    standard convention `ret_adj = (1+ret)*(1+dlret) - 1`.

    Documented simplification: rows where `dlret` is missing/NaN are left as
    plain `ret` (no fixed delisting-return imputation by exchange, unlike the
    fuller Shumway/Johnson convention). No-op when no `dlret` column exists
    (true for all current synthetic test fixtures) or when
    `config["apply_delisting_returns"]` is explicitly set to False (e.g. for
    an ablation run).
    """
    if not config.get("apply_delisting_returns", True):
        return df
    if "dlret" not in df.columns:
        return df
    df = df.copy()
    dlret = df["dlret"]
    has_dlret = dlret.notna()
    df.loc[has_dlret, "ret"] = (
        (1 + df.loc[has_dlret, "ret"].fillna(0)) * (1 + dlret[has_dlret]) - 1
    )
    return df


def apply_missing_policy(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step 2: what to do when the return/signal is missing (default: drop)."""
    action = config.get("missing_action", "drop")
    if action in ("drop", "unspecified"):
        return df.dropna(subset=["ret"]).copy()
    # winsorize / fill_* handled by hook
    return df


def _apply_filter_op(series: pd.Series, op: str, value: Any) -> pd.Series:
    """Evaluate one FilterOp (src/infra/models/method_spec.py FilterOp enum)
    against a column. Mirrors the vocabulary 1:1 so the deterministic DSL
    covers every value the extraction schema can produce."""
    if op == "eq":
        return series == value
    if op == "neq":
        return series != value
    if op == "in":
        return series.isin(value)
    if op == "not_in":
        return ~series.isin(value)
    if op == "between":
        lo, hi = value
        return series.between(lo, hi)
    if op == "not_between":
        lo, hi = value
        return ~series.between(lo, hi)
    if op == "gt":
        return series > value
    if op == "gte":
        return series >= value
    if op == "lt":
        return series < value
    if op == "lte":
        return series <= value
    if op == "nonmissing":
        return series.notna()
    if op == "nonzero":
        return series != 0
    if op == "is_true":
        return series.astype(bool)
    if op == "is_false":
        return ~series.astype(bool)
    raise ValueError(f"Unknown FilterOp: {op!r}")


def apply_universe_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    """Apply a list of {field, op, value} universe filters (the deterministic
    DSL behind `UniverseFilterSpec`/`FilterOp` in method_spec.py) to `df`.

    Point-in-time by construction: filters are evaluated row-wise on the
    already-point-in-time monthly panel (each row is one stock-month
    snapshot), so applying them here introduces no look-ahead. A filter
    field absent from the loaded data is skipped rather than raising, since
    `detect_hooks()` can't validate column availability at spec-review time.
    """
    if not filters:
        return df
    mask = pd.Series(True, index=df.index)
    for f in filters:
        field_name = f.get("field")
        if field_name not in df.columns:
            continue
        op = f.get("op", "nonmissing")
        mask &= _apply_filter_op(df[field_name], op, f.get("value"))
    return df[mask].copy()


def filter_universe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step 3: which stocks count. Deterministic ResearchDesign step (plan.md
    Phase 2.5): baseline common-stock / major-exchange / ex-financials screen
    (the canonical v1 default), layered with any additional structured
    `universe_filters` resolved from the MethodSpec's
    `portfolio.universe_filters` (applied via the FilterOp DSL in
    `apply_universe_filters`). This replaced an earlier design where
    filter_universe was unconditionally routed to an LLM-generated hook (see
    CHANGELOG 2026-07-20 Phase 2.5) — a plugin-supplied `filter_universe_hook`
    still overrides this entirely when present (e.g. for a genuinely
    idiosyncratic universe rule the DSL can't express), via `_dispatch()`.

    Optionally excludes microcaps (stocks below the NYSE 20th percentile of
    market equity that month) when `config["microcap_exclude"]` is True —
    off by default; the canonical default is to *report* microcap exposure
    as a diagnostic (see `compute_metrics`), not silently exclude it.
    """
    mask = (
        df["shrcd"].isin([10, 11])
        & df["exchcd"].isin([1, 2, 3])
    )
    if "siccd" in df.columns:
        mask &= ~df["siccd"].between(6000, 6999)
    out = df[mask].copy()
    out = apply_universe_filters(out, config.get("universe_filters") or [])

    if config.get("microcap_exclude") and "me" in out.columns and "exchcd" in out.columns:
        nyse_p20 = (
            out[out["exchcd"] == 1]
            .groupby("yyyymm")["me"]
            .quantile(0.2)
        )
        threshold = out["yyyymm"].map(nyse_p20)
        out = out[out["me"] >= threshold.fillna(-float("inf"))].copy()
    return out


def neutralize_signal(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Deterministic ResearchDesign scaffold (plan.md Phase 2.5): extension
    point for cross-sectional signal neutralization (industry-adjust,
    residualize against another characteristic, beta-neutralize). No-op
    identity by default (`config["neutralization"] == "none"`, the canonical
    v1 default — no MethodSpec field currently drives this; adding one is
    deferred until a concrete neutralization scheme is implemented). A
    plugin-supplied `neutralize_signal_hook` can implement an actual
    transform via `_dispatch()` without this function needing to change.
    """
    if config.get("neutralization", "none") == "none":
        return df
    raise NotImplementedError(
        f"neutralization={config['neutralization']!r} has no standard implementation; "
        "provide a neutralize_signal_hook in the plugin."
    )


def merge_signal(df: pd.DataFrame, signal: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Data-prep step: expand annual signal to monthly holding period and
    join with msf (not one of the numbered questions, just plumbing to line
    up the yearly signal with monthly returns).

    Assumes non-overlapping ("clean calendar hold") portfolios: the most
    recently formed signal value is held flat until the next formation, then
    replaced. Each signal row already sits at its own formation month, so
    holding it forward from that row supports any formation/start month for
    free (the "rebalance calendar" is encoded in the signal rows themselves).

    Rebalance-frequency-aware hold (plan.md CZ-import Phase C, mirrors CZ's
    hold-until-next-rebalance stale-fill): in a non-overlapping design you
    never hold a formation longer than one rebalance interval, so the hold
    window is capped at the rebalance step derived from
    `config["rebalance_frequency"]` (annual=12, quarterly=3, monthly=1) when
    specified -- so a quarterly-rebalanced factor holds 3 months, not a
    stale 12. Annual factors are unchanged (min(12, 12) = 12), keeping golden
    numbers byte-identical. `rebalance_frequency="unspecified"` falls back to
    `holding_period_months` verbatim (prior behavior).

    For papers with overlapping portfolios (e.g. Jegadeesh-Titman 1993
    momentum, which forms a new cohort every month and averages across the
    still-open cohorts), see `merge_signal_overlap` + friends below (plan.md
    Phase 5) — standard now, dispatched automatically when
    `config["overlapping"]` is true.
    """
    hp = int(config.get("holding_period_months", 12))
    step = _rebalance_step_months(config)
    hold = min(hp, step) if step is not None else hp
    rows: list[dict] = []
    for _, row in signal.iterrows():
        yyyymm = int(row["yyyymm"])
        year, month = divmod(yyyymm, 100)
        for h in range(1, hold + 1):
            m = month + h
            y = year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            rows.append({
                "permno": int(row["permno"]),
                "yyyymm": y * 100 + m,
                "signal": float(row["signal"]),
            })
    expanded = pd.DataFrame(rows)
    return df.merge(expanded, on=["permno", "yyyymm"], how="inner")


def _rebalance_step_months(config: dict) -> int | None:
    """Number of months between rebalances implied by
    `config["rebalance_frequency"]`, or None when unspecified/unknown (caller
    falls back to `holding_period_months`). See `merge_signal`."""
    freq = str(config.get("rebalance_frequency", "unspecified")).lower()
    return {"annual": 12, "quarterly": 3, "monthly": 1}.get(freq)



# ---------------------------------------------------------------------------
# Overlapping-cohort holding model (plan.md Phase 5). Standard for
# momentum/reversal-style factors (`signal.timing.overlapping_portfolios`).
# Dispatched instead of the non-overlapping merge_signal/compute_breakpoints/
# assign_portfolios/compute_returns/compute_long_short above when
# `config["overlapping"]` is true (see `BacktestEngine._dispatch()`'s
# `_OVERLAP_STEPS` name-mangling). Not combined with the multi-dim sort in
# this v1 (a plugin hook is still needed for that combination).
#
# Convention (Jegadeesh-Titman 1993): each formation month starts a new
# "cohort" that is held for `holding_period_months` months (after an
# optional `skip_month` lag); several cohorts are open simultaneously in any
# given current month. Each cohort forms its OWN portfolios from ITS OWN
# formation-date breakpoints (computed once per cohort, since a cohort's
# signal doesn't change across its holding window); the strategy's return in
# a given current month is the equal-weighted AVERAGE of the still-open
# cohorts' long-short spreads that month.
# ---------------------------------------------------------------------------

def merge_signal_overlap(df: pd.DataFrame, signal: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Overlapping counterpart of `merge_signal`. Output has one row per
    (permno, current holding yyyymm, cohort) -- `cohort` is the signal's
    original formation yyyymm -- rather than collapsing to one row per
    (permno, yyyymm), since multiple cohorts can hold the same stock in the
    same current month simultaneously.
    """
    hp = int(config.get("holding_period_months", 12))
    skip = int(config.get("skip_month", 0))
    rows: list[dict] = []
    for _, row in signal.iterrows():
        yyyymm = int(row["yyyymm"])
        year, month = divmod(yyyymm, 100)
        for h in range(1 + skip, hp + skip + 1):
            m = month + h
            y = year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            rows.append({
                "permno": int(row["permno"]),
                "cohort": yyyymm,
                "yyyymm": y * 100 + m,
                "signal": float(row["signal"]),
            })
    expanded = pd.DataFrame(rows)
    return df.merge(expanded, on=["permno", "yyyymm"], how="inner")


def compute_breakpoints_overlap(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Breakpoints computed per formation `cohort` (not per current
    `yyyymm`): a cohort's signal cross-section is fixed at formation, so
    de-duplicating to one row per (permno, cohort) before quantiling is
    equivalent to computing breakpoints once at formation time."""
    n = int(config.get("breakpoint_quantiles", 10))
    src = config.get("breakpoint_source", "full_sample")

    bp_df = df[df["exchcd"] == 1].copy() if src == "nyse" else df.copy()
    bp_df = bp_df.drop_duplicates(subset=["permno", "cohort"]).dropna(subset=["signal"])

    quantile_vals = np.linspace(0, 1, n + 1)
    bp = bp_df.groupby("cohort")["signal"].quantile(quantile_vals).unstack()
    bp.columns = [f"q{i}" for i in range(n + 1)]
    return bp


def assign_portfolios_overlap(df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Overlapping counterpart of `assign_portfolios`: looks up breakpoints
    by `cohort` instead of `yyyymm`, so every row for a given cohort (across
    however many current months it's held) uses that cohort's own
    formation-date breakpoints."""
    n = int(config.get("breakpoint_quantiles", 10))
    chunks: list[pd.DataFrame] = []
    for cohort, group in df.groupby("cohort"):
        if cohort not in breakpoints.index:
            continue
        bp = breakpoints.loc[cohort]
        bins = [bp[f"q{i}"] for i in range(n + 1)]
        bins[0] = -np.inf
        bins[-1] = np.inf
        g = group.copy()
        g["portfolio"] = pd.cut(
            g["signal"], bins=bins, labels=range(1, n + 1), include_lowest=True
        )
        chunks.append(g)
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks)
    return out.dropna(subset=["portfolio"]).copy()


def compute_returns_overlap(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Overlapping counterpart of `compute_returns`: VW/EW return for each
    (current yyyymm, cohort, portfolio) cell -- i.e. each still-open
    cohort's own sub-portfolio return in the current month."""
    wt = config.get("weighting_rule", "vw")
    df = df.copy()
    df["portfolio"] = df["portfolio"].astype(int)
    group_cols = ["yyyymm", "cohort", "portfolio"]

    if wt == "vw":
        def _vw(g: pd.DataFrame) -> float:
            w = g["me"].clip(lower=0)
            s = w.sum()
            return float((g["ret"] * w).sum() / s) if s > 0 else float("nan")

        rets = df.groupby(group_cols).apply(_vw).reset_index(name="ret")
    else:
        rets = df.groupby(group_cols)["ret"].mean().reset_index()
    return rets


def compute_long_short_overlap(rets: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Overlapping counterpart of `compute_long_short`: each still-open
    cohort's long-short spread in the current month, averaged across every
    cohort held that month (the standard JT-style overlapping-portfolio
    convention)."""
    n = int(config.get("breakpoint_quantiles", 10))
    long_leg = config.get("long_leg", "low")
    long_port  = 1 if long_leg == "low" else n
    short_port = n if long_leg == "low" else 1

    rows: list[dict] = []
    for yyyymm, month_g in rets.groupby("yyyymm"):
        cohort_spreads: list[float] = []
        for _, g in month_g.groupby("cohort"):
            port_map = dict(zip(g["portfolio"], g["ret"]))
            if long_port in port_map and short_port in port_map:
                cohort_spreads.append(port_map[long_port] - port_map[short_port])
        if cohort_spreads:
            rows.append({"yyyymm": yyyymm, "ls_return": float(np.mean(cohort_spreads))})
    return pd.DataFrame(rows)


def compute_breakpoints(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step: the numeric cutoffs used to sort stocks into groups each month.

    Sort form (plan.md CZ-import Phase B, mirrors CZ Cat.Form): only the
    `continuous` form needs quantile breakpoints. `discrete` (one portfolio
    per distinct signal value) does its assignment directly in
    `assign_portfolios` and needs no numeric cutoffs, so this returns an empty
    frame for it.
    """
    if config.get("cat_form", "continuous") == "discrete":
        return pd.DataFrame()

    n = int(config.get("breakpoint_quantiles", 10))
    src = config.get("breakpoint_source", "full_sample")

    bp_df = df[df["exchcd"] == 1].copy() if src == "nyse" else df.copy()
    bp_df = bp_df.dropna(subset=["signal"])

    quantile_vals = np.linspace(0, 1, n + 1)
    bp = (
        bp_df.groupby("yyyymm")["signal"]
        .quantile(quantile_vals)
        .unstack()
    )
    bp.columns = [f"q{i}" for i in range(n + 1)]
    return bp


def assign_portfolios(df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step: which group each stock falls into, given the breakpoints.

    Sort form (plan.md CZ-import Phase B, mirrors CZ Cat.Form):
      - continuous: quantile cut against `breakpoints` (the original path).
      - discrete: each distinct signal value maps to its own portfolio, ranked
        1..K by the GLOBALLY sorted support of signal values (as in CZ's
        `support = sort(unique(signal))`), so a given categorical score always
        maps to the same portfolio number regardless of month.
    """
    cat_form = config.get("cat_form", "continuous")

    if cat_form == "discrete":
        g = df.dropna(subset=["signal"]).copy()
        support = np.sort(g["signal"].unique())
        value_to_port = {v: i + 1 for i, v in enumerate(support)}
        g["portfolio"] = g["signal"].map(value_to_port).astype(int)
        return g

    n = int(config.get("breakpoint_quantiles", 10))
    chunks: list[pd.DataFrame] = []
    for yyyymm, group in df.groupby("yyyymm"):
        if yyyymm not in breakpoints.index:
            continue
        bp = breakpoints.loc[yyyymm]
        bins = [bp[f"q{i}"] for i in range(n + 1)]
        bins[0] = -np.inf
        bins[-1] = np.inf
        g = group.copy()
        g["portfolio"] = pd.cut(
            g["signal"], bins=bins, labels=range(1, n + 1), include_lowest=True
        )
        chunks.append(g)
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks)
    return out.dropna(subset=["portfolio"]).copy()



def compute_returns(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step: each group's monthly return — value-weighted (by `me`) or
    equal-weighted."""
    wt = config.get("weighting_rule", "vw")
    df = df.copy()
    df["portfolio"] = df["portfolio"].astype(int)

    if wt == "vw":
        def _vw(g: pd.DataFrame) -> float:
            w = g["me"].clip(lower=0)
            s = w.sum()
            return float((g["ret"] * w).sum() / s) if s > 0 else float("nan")

        rets = (
            df.groupby(["yyyymm", "portfolio"])
            .apply(_vw)
            .reset_index(name="ret")
        )
    else:
        rets = (
            df.groupby(["yyyymm", "portfolio"])["ret"]
            .mean()
            .reset_index()
        )
    return rets


def compute_long_short(rets: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Step: combine per-portfolio returns into the reported series (plan.md
    Phase 4 generalized this from a single hardcoded extreme-decile spread
    into all four standard `return_combination` types; kept the
    `compute_long_short`/`compute_long_short_hook` name for hook-contract
    backward compatibility — see CHANGELOG 2026-07-20 Phase 4 — a rename to
    `combine_returns` is deferred to Phase 8's hook-contract cleanup).

    Selected via `config["return_combination_type"]`
    (default `"extreme_group_spread"`):
      - `extreme_group_spread` (default): single top portfolio minus single
        bottom portfolio (the original, only-ever-implemented behavior).
      - `average_leg_spread`: average of `config["long_portfolios"]` minus
        average of `config["short_portfolios"]` (explicit portfolio-number
        lists) -- defaults to the same single top/bottom pair as
        extreme_group_spread when those aren't given (free-text leg
        descriptions like "average of deciles 8-10" aren't auto-parsed; an
        explicit config override is required to actually average multiple
        portfolios per leg).
      - `single_signal_portfolio_return`: report one portfolio's return
        as-is (`config["single_portfolio"]`, default: the "long" extreme),
        no spread. **Bug fix (Phase 4):** previously this type was already
        marked STANDARD but the implementation always computed a spread
        regardless -- any single_signal_portfolio_return factor run through
        the standard path got a silently wrong (spread, not single-leg)
        result. Fixed here.
      - `full_portfolio_return`: report every portfolio's return untouched,
        no combination -- consumed differently by `compute_metrics` (no
        single `ls_return`/t-stat; see there).
    """
    combo = config.get("return_combination_type", "extreme_group_spread")
    n = int(config.get("breakpoint_quantiles", 10))
    long_leg = config.get("long_leg", "low")

    # For the discrete sort form (plan.md CZ-import Phase B) the number of
    # portfolios isn't `breakpoint_quantiles` -- it's however many distinct
    # groups the signal produced -- so the extreme legs are the min/max
    # portfolio actually present, not 1 and n. Continuous keeps the original
    # 1..n convention exactly (golden-number stable).
    if config.get("cat_form", "continuous") == "discrete" and not rets.empty:
        ports_present = sorted(int(p) for p in rets["portfolio"].dropna().unique())
        lo_port, hi_port = ports_present[0], ports_present[-1]
        default_long_port  = lo_port if long_leg == "low" else hi_port
        default_short_port = hi_port if long_leg == "low" else lo_port
    else:
        default_long_port  = 1 if long_leg == "low" else n
        default_short_port = n if long_leg == "low" else 1


    if combo == "full_portfolio_return":
        return rets.copy()

    if combo == "single_signal_portfolio_return":
        single = config.get("single_portfolio", default_long_port)
        rows: list[dict] = []
        for yyyymm, g in rets.groupby("yyyymm"):
            port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
            if single in port_map:
                rows.append({"yyyymm": yyyymm, "ls_return": port_map[single]})
        return pd.DataFrame(rows)

    # extreme_group_spread / average_leg_spread: both are "average(long legs)
    # - average(short legs)"; extreme_group_spread is just the 1-leg case.
    long_ports = config.get("long_portfolios") or [default_long_port]
    short_ports = config.get("short_portfolios") or [default_short_port]

    rows = []
    for yyyymm, g in rets.groupby("yyyymm"):
        port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
        long_vals = [port_map[p] for p in long_ports if p in port_map]
        short_vals = [port_map[p] for p in short_ports if p in port_map]
        if long_vals and short_vals:
            rows.append({
                "yyyymm": yyyymm,
                "ls_return": float(np.mean(long_vals)) - float(np.mean(short_vals)),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Multi-dimensional sort (plan.md Phase 3). Used instead of the single-dim
# compute_breakpoints/assign_portfolios/compute_returns/compute_long_short
# above when `config["sort_dims"]` has 2+ dimensions (see
# `registry.resolve_sort_dims` for how a MethodSpec's
# `portfolio_return.sorts[]` maps onto this — deliberately narrow v1: only
# a characteristic x size double sort is resolved as standard; anything else
# still routes to a hook). Dispatched via `BacktestEngine._dispatch()`'s
# `_MULTI_DIM_STEPS` name-mangling (`compute_breakpoints` -> `..._multi`).
# ---------------------------------------------------------------------------

def _dimension_breakpoints(df_for_bp: pd.DataFrame, column: str, quantiles: int) -> pd.Series:
    """One month's (or one bucket's) breakpoint cutoffs for one dimension."""
    qs = np.linspace(0, 1, quantiles + 1)
    return df_for_bp[column].quantile(qs)


def _assign_bucket(values: pd.Series, breakpoints: pd.Series, quantiles: int) -> pd.Series:
    bins = list(breakpoints.values)
    bins[0] = -np.inf
    bins[-1] = np.inf
    return pd.cut(values, bins=bins, labels=range(1, quantiles + 1), include_lowest=True)


def compute_breakpoints_multi(df: pd.DataFrame, config: dict):
    """Multi-dim counterpart of `compute_breakpoints`. Dependent (conditional)
    sort dimensions need breakpoints computed *within* the prior dimension's
    bucket, which requires per-row assignment data the plain
    compute_breakpoints -> assign_portfolios split doesn't have at this
    stage. So this function just returns the resolved `sort_dims` list
    unchanged, and `assign_portfolios_multi` does the real per-dimension
    breakpoint + assignment work together — this still satisfies the
    `Step` contract (`compute_breakpoints(df, config) -> breakpoints`,
    `assign_portfolios(df, breakpoints, config) -> df`) without duplicating
    logic between the two functions.
    """
    return config.get("sort_dims") or []


def assign_portfolios_multi(df: pd.DataFrame, breakpoints, config: dict) -> pd.DataFrame:
    """N-dimensional sort assignment, independent or dependent breakpoints.

    `breakpoints` is the resolved `sort_dims` list from
    `compute_breakpoints_multi` (each: {variable, column, quantiles, source,
    independent}), in the paper's specified dimension order — dimension 0's
    breakpoints are always computed on its own configured universe (nyse/
    full_sample); dimension i>0 is either independent (its own breakpoints on
    its own universe) or dependent/conditional (breakpoints computed
    separately within each dimension-0 bucket — the standard convention for
    e.g. a size-then-value dependent double sort). Deliberately v1-scoped to
    condition only on dimension 0 (not on the running intersection of all
    prior dimensions), which covers the common 2-way double sort; deeper
    dependent chains are out of scope.

    Output columns: `portfolio_0`, `portfolio_1`, ... (one per dimension),
    alongside the original columns. No combined string label is produced;
    `compute_returns_multi`/`compute_long_short_multi` group on the
    `portfolio_i` columns directly.
    """
    dims = breakpoints
    if not dims:
        return pd.DataFrame()

    chunks: list[pd.DataFrame] = []
    for yyyymm, month_df in df.groupby("yyyymm"):
        month_df = month_df.copy()

        dim0 = dims[0]
        bp_universe = month_df[month_df["exchcd"] == 1] if dim0.get("source") == "nyse" else month_df
        bp_universe = bp_universe.dropna(subset=[dim0["column"]])
        if bp_universe.empty:
            continue
        bp0 = _dimension_breakpoints(bp_universe, dim0["column"], dim0["quantiles"])
        month_df["portfolio_0"] = _assign_bucket(month_df[dim0["column"]], bp0, dim0["quantiles"])

        for i, dim in enumerate(dims[1:], start=1):
            col = dim["column"]
            nq = dim["quantiles"]
            src = dim.get("source", "full_sample")
            independent = dim.get("independent", True)

            if independent:
                bp_universe_i = month_df[month_df["exchcd"] == 1] if src == "nyse" else month_df
                bp_universe_i = bp_universe_i.dropna(subset=[col])
                if bp_universe_i.empty:
                    month_df[f"portfolio_{i}"] = np.nan
                    continue
                bp_i = _dimension_breakpoints(bp_universe_i, col, nq)
                month_df[f"portfolio_{i}"] = _assign_bucket(month_df[col], bp_i, nq)
            else:
                assigned = pd.Series(index=month_df.index, dtype="float64")
                for _, bucket_df in month_df.groupby("portfolio_0", observed=True):
                    bp_universe_i = bucket_df[bucket_df["exchcd"] == 1] if src == "nyse" else bucket_df
                    bp_universe_i = bp_universe_i.dropna(subset=[col])
                    if bp_universe_i.empty:
                        continue
                    bp_i = _dimension_breakpoints(bp_universe_i, col, nq)
                    assigned.loc[bucket_df.index] = _assign_bucket(bucket_df[col], bp_i, nq).astype(float)
                month_df[f"portfolio_{i}"] = assigned

        chunks.append(month_df)

    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks)
    portfolio_cols = [f"portfolio_{i}" for i in range(len(dims))]
    return out.dropna(subset=portfolio_cols).copy()


def compute_returns_multi(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Multi-dim counterpart of `compute_returns`: VW/EW return for each
    joint (yyyymm, portfolio_0, portfolio_1, ...) cell."""
    wt = config.get("weighting_rule", "vw")
    df = df.copy()
    portfolio_cols = [c for c in df.columns if c.startswith("portfolio_")]
    for c in portfolio_cols:
        df[c] = df[c].astype(int)
    group_cols = ["yyyymm"] + portfolio_cols

    if wt == "vw":
        def _vw(g: pd.DataFrame) -> float:
            w = g["me"].clip(lower=0)
            s = w.sum()
            return float((g["ret"] * w).sum() / s) if s > 0 else float("nan")

        rets = df.groupby(group_cols).apply(_vw).reset_index(name="ret")
    else:
        rets = df.groupby(group_cols)["ret"].mean().reset_index()
    return rets


def compute_long_short_multi(rets: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Multi-dim counterpart of `compute_long_short`: the standard "average
    across control-dimension groups" double-sort convention. Finds whichever
    dimension holds the paper's own characteristic (`column == "signal"`),
    computes its extreme-decile spread separately within every combination of
    the other ("control") dimensions, then averages those spreads — e.g. for
    a characteristic x size sort, this is "average the characteristic
    spread across size groups", the standard construction in the literature.
    """
    dims = config.get("sort_dims") or []
    if not dims:
        return pd.DataFrame()
    signal_idx = next((i for i, d in enumerate(dims) if d["column"] == "signal"), 0)
    signal_col = f"portfolio_{signal_idx}"
    n_signal = dims[signal_idx]["quantiles"]
    other_cols = [f"portfolio_{i}" for i in range(len(dims)) if i != signal_idx]

    long_leg = config.get("long_leg", "low")
    long_b  = 1 if long_leg == "low" else n_signal
    short_b = n_signal if long_leg == "low" else 1

    rows: list[dict] = []
    for yyyymm, g in rets.groupby("yyyymm"):
        spreads: list[float] = []
        if other_cols:
            for _, sub in g.groupby(other_cols):
                port_map = dict(zip(sub[signal_col], sub["ret"]))
                if long_b in port_map and short_b in port_map:
                    spreads.append(port_map[long_b] - port_map[short_b])
        else:
            port_map = dict(zip(g[signal_col], g["ret"]))
            if long_b in port_map and short_b in port_map:
                spreads.append(port_map[long_b] - port_map[short_b])
        if spreads:
            rows.append({"yyyymm": yyyymm, "ls_return": float(np.mean(spreads))})
    return pd.DataFrame(rows)


def compute_metrics(ls: pd.DataFrame, config: dict) -> dict[str, Any]:
    """Step: summary statistics — mean monthly return, Newey-West t-stat (is
    the return statistically distinguishable from zero, given that monthly
    returns are autocorrelated), and how many months of data went into it.

    `full_portfolio_return` combination (plan.md Phase 4) has no single
    `ls_return` spread to summarize this way -- `ls` is the full per-portfolio
    grid instead, so this reports basic coverage diagnostics for it rather
    than a mean/t-stat (a fuller per-portfolio metrics breakdown is left to
    a future Evaluator enhancement; the full grid itself is always available
    in `return_series`).

    Sample-period segmentation (plan.md CZ-import Phase A): when
    `config` carries `sample_start_year`/`sample_end_year`/`publication_year`,
    a nested `by_sample_period` dict is added with the same mean/t-stat
    computed separately over the paper's in-sample window, the
    sample-end-to-publication gap, and the post-publication period (mirrors
    CZ's `sumportmonth` insamp/between/postpub tags). The top-level keys are
    left untouched so existing golden numbers are unaffected.
    """
    if "ls_return" not in ls.columns:
        if ls.empty:
            return {"n_months": 0, "portfolios": [], "note": "full_portfolio_return: empty result"}
        return {
            "n_months": int(ls["yyyymm"].nunique()),
            "portfolios": sorted(ls["portfolio"].dropna().astype(int).unique().tolist()),
            "note": (
                "full_portfolio_return: no single long-short spread computed; "
                "see return_series for per-portfolio returns"
            ),
        }

    series = ls["ls_return"].dropna()
    metrics = _series_metrics(series)

    by_period = _sample_period_metrics(ls, config)
    if by_period is not None:
        metrics["by_sample_period"] = by_period

    return metrics


def _series_metrics(series: pd.Series) -> dict[str, Any]:
    """Mean / Newey-West t-stat / Sharpe / n_months for one return series.

    Factored out of `compute_metrics` so the whole-sample series and each
    sample-period segment share one implementation."""
    n = len(series)
    if n < 2:
        return {"mean_monthly_return": float("nan"), "t_stat": float("nan"), "n_months": n}

    mean_ret = float(series.mean())
    std_ret = float(series.std())
    lags = min(6, n - 1)
    nw_var = newey_west_var(series.values, lags)
    t_stat = mean_ret / np.sqrt(nw_var / n) if nw_var > 0 else float("nan")
    # Guard against floating-point noise on a (near-)constant series producing
    # a tiny-but-nonzero std that blows up the ratio instead of dividing by
    # the intended zero.
    sharpe = (mean_ret / std_ret * np.sqrt(12)) if std_ret > 1e-12 else float("nan")

    return {
        "mean_monthly_return": mean_ret,
        "annualized_return":   mean_ret * 12,
        "t_stat":              float(t_stat),
        "n_months":            n,
        # Phase 2 (plan.md): Sharpe needs no new dependency, so it's always
        # computed here. Factor-model alphas (CAPM/FF3/FF5) need FF factor
        # data, which isn't always available -- see compute_factor_alphas(),
        # called separately (not from here) when factor data is supplied.
        "sharpe_ratio":        float(sharpe),
    }


def _sample_period_metrics(ls: pd.DataFrame, config: dict) -> dict[str, Any] | None:
    """Split the long-short series into in-sample / between / post-publication
    segments and compute `_series_metrics` for each (plan.md CZ-import Phase A,
    mirroring CZ's `sumportmonth`).

    Segments (by calendar year of each month), following CZ's convention:
      - insamp:  sample_start_year <= year <= sample_end_year
      - between: sample_end_year   <  year <= publication_year
      - postpub: year > publication_year

    Returns None (so `compute_metrics` omits the nested dict entirely) when no
    sample window is configured. `between`/`postpub` are omitted individually
    when `publication_year` isn't known. Segments with no months are skipped.
    """
    start = config.get("sample_start_year")
    end = config.get("sample_end_year")
    pub = config.get("publication_year")
    if start is None and end is None and pub is None:
        return None

    df = ls.dropna(subset=["ls_return"]).copy()
    if df.empty:
        return None
    year = (df["yyyymm"] // 100).astype(int)

    segments: dict[str, pd.Series] = {}
    if start is not None or end is not None:
        lo = start if start is not None else -np.inf
        hi = end if end is not None else np.inf
        segments["insamp"] = df.loc[(year >= lo) & (year <= hi), "ls_return"]
    if end is not None and pub is not None:
        segments["between"] = df.loc[(year > end) & (year <= pub), "ls_return"]
    if pub is not None:
        segments["postpub"] = df.loc[year > pub, "ls_return"]

    out: dict[str, Any] = {}
    for name, seg in segments.items():
        if len(seg) > 0:
            out[name] = _series_metrics(seg)
    return out or None



def compute_factor_alphas(ls: pd.DataFrame, factors: pd.DataFrame, config: dict) -> dict[str, Any]:
    """Regress the combined return series on factor returns for CAPM/FF3/FF5
    alpha estimates (plan.md Phase 2), using `statsmodels` OLS with
    Newey-West (HAC) standard errors -- independent of the hand-rolled
    Newey-West t-stat `compute_metrics` uses for the primary spread (kept
    unchanged there for golden-number stability; see `newey_west_var`).

    Args:
        ls: the combined return series from `compute_long_short` (must have
            an `ls_return` column -- returns {} for the `full_portfolio_return`
            shape, which has no single series to regress).
        factors: DataFrame with a `yyyymm` column plus whichever of
            `mktrf`/`smb`/`hml`/`rmw`/`cma` are available (see
            `scripts/fetch_ff_factors.py`). CAPM needs `mktrf`; FF3 needs
            `mktrf`+`smb`+`hml`; FF5 adds `rmw`+`cma`. An alpha is silently
            omitted if its required columns aren't present.

    Returns {} (no error) if `statsmodels` isn't installed -- it's an
    optional `research` dependency (see pyproject.toml), not a core one, so
    the rest of the engine works without it.
    """
    if "ls_return" not in ls.columns or factors is None or factors.empty:
        return {}
    try:
        import statsmodels.api as sm
    except ImportError:
        return {}

    merged = ls.merge(factors, on="yyyymm", how="inner")
    n = len(merged)
    if n < 3:
        return {}

    y = merged["ls_return"].to_numpy()
    lags = min(6, n - 2)
    results: dict[str, Any] = {}

    factor_specs = {
        "capm": ["mktrf"],
        "ff3": ["mktrf", "smb", "hml"],
        "ff5": ["mktrf", "smb", "hml", "rmw", "cma"],
    }
    for name, cols in factor_specs.items():
        if not all(c in merged.columns for c in cols):
            continue
        x = sm.add_constant(merged[cols].to_numpy())
        model = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        results[f"alpha_{name}"] = float(model.params[0])
        results[f"alpha_{name}_tstat"] = float(model.tvalues[0])
        for i, col in enumerate(cols, start=1):
            results[f"beta_{name}_{col}"] = float(model.params[i])

    return results


# ---------------------------------------------------------------------------
# Fama-MacBeth regression estimator (plan.md Phase 7). A genuinely different
# ESTIMATOR from the portfolio-sort pipeline above (not a variant of it):
# routed via `config["estimator"] == "fama_macbeth"` (set in
# registry.build_config() from `construction_type == "regression_weighted"`),
# `BacktestEngine.run_with_config()` branches to this INSTEAD of the sort/
# breakpoints/assign/returns/combine chain entirely, right after
# merge_signal.
# ---------------------------------------------------------------------------

def compute_fama_macbeth(merged: pd.DataFrame, config: dict) -> dict[str, Any]:
    """Fama-MacBeth (1973) cross-sectional regression estimator: regresses
    `ret` on `signal` (+ a constant) period-by-period, then averages the
    per-period slope over time with Fama-MacBeth standard errors, via
    `linearmodels.panel.FamaMacBeth` (cross-sectional controls beyond
    `signal` aren't supported in this v1 -- a single-characteristic FM
    regression covers the common case of "what's the average monthly
    premium on this characteristic").

    Winsorizes `signal` at `config["winsorize_signal_pct"]` (e.g. 0.01 for
    1%/99%) if given -- this is deterministic ResearchDesign-layer trimming
    (plan.md Phase 2.5 philosophy), not a plugin hook.

    Returns a metrics dict with `fm_intercept`, `fm_slope`,
    `fm_slope_tstat`, `fm_n_periods` -- NOT a long-short spread; there is no
    portfolio-level `return_series` for this estimator (the caller returns
    an empty DataFrame for that key).

    Raises RuntimeError (not silently degrading) if `linearmodels` isn't
    installed, since Fama-MacBeth IS the requested estimator here (unlike
    `compute_factor_alphas`, which is an optional enrichment of the default
    portfolio-sort path) -- `linearmodels` is the optional `research`
    dependency (see pyproject.toml); install it to use this estimator.
    """
    try:
        from linearmodels.panel import FamaMacBeth
    except ImportError as e:
        raise RuntimeError(
            "The Fama-MacBeth estimator (construction_type=regression_weighted) "
            "requires the 'linearmodels' package (optional 'research' extra; "
            "see pyproject.toml)."
        ) from e

    df = merged.dropna(subset=["signal", "ret"]).copy()

    pct = config.get("winsorize_signal_pct")
    if pct:
        lo, hi = df["signal"].quantile([pct, 1 - pct])
        df["signal"] = df["signal"].clip(lo, hi)

    df = df.set_index(["permno", "yyyymm"])
    exog = pd.DataFrame({"const": 1.0, "signal": df["signal"]}, index=df.index)
    result = FamaMacBeth(df["ret"], exog).fit()

    n_periods = int(df.index.get_level_values("yyyymm").nunique())
    return {
        "fm_intercept": float(result.params["const"]),
        "fm_slope": float(result.params["signal"]),
        "fm_slope_tstat": float(result.tstats["signal"]),
        "fm_n_periods": n_periods,
    }
