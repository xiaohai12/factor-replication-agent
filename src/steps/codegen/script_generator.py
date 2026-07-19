"""Backtest Script Generator - Produce standalone runnable backtest scripts.

After MetaCoder generates a plugin, this module combines:
  1. The signal plugin code (compute_signal function + any *_hook functions)
  2. BacktestEngine configuration derived from the resolved MethodSpec
  3. Data loading (CRSP-only or Compustat+CCM), signal computation, portfolio
     formation, hook dispatch, and metrics output

into a single self-contained Python script that can be executed independently.
Mirrors src/steps/engine/BacktestEngine.run()'s exact step order and hook
dispatch mechanism (apply_missing_policy -> filter_universe -> merge_signal ->
compute_breakpoints -> assign_portfolios -> compute_returns -> compute_long_short)
so results match the in-process engine, including for hook-dependent factors
(e.g. sloan_1996_accruals's winsorize hook, ball2016's double-sort hooks).
"""

from __future__ import annotations

from typing import Any

from src.steps.engine import BacktestEngine
from src.infra.models.method_spec import MethodSpec


# Physical columns that CRSP-monthly-only signals need (no Compustat merge
# required). Mirrors the same heuristic used by app.py's dashboard pages.
_CRSP_ONLY_COLUMNS = {"ret", "me", "shrcd", "exchcd", "siccd", "prc", "shrout", "date"}


def _signal_needs_compustat(spec: MethodSpec) -> bool:
    """Best-effort guess: does this spec's signal need Compustat fields (vs CRSP-only)?"""
    mapping = spec.data.normalized_mapping or {}
    if not mapping:
        return True
    return any(col not in _CRSP_ONLY_COLUMNS for col in mapping.values())


def generate_backtest_script(
    spec: MethodSpec,
    plugin_code: str,
    data_path: str = "data/local/msf.parquet",
    signal_input_mode: str | None = None,
    compustat_data_path: str = "data/local/compustat_funda.parquet",
    ccm_link_path: str = "data/local/ccm_link.parquet",
    output_path: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> str:
    """Generate a standalone backtest script from a MethodSpec and plugin code.

    Args:
        spec: Resolved MethodSpec with all empirical decisions finalized.
        plugin_code: The signal plugin source code (compute_signal + any hooks).
        data_path: Relative path to the CRSP monthly parquet file.
        signal_input_mode: "compustat" (build a SignalMasterTable via inline CCM
            linking + accounting lag before calling compute_signal) or
            "crsp_only" (alias yyyymm -> time_avail_m and call compute_signal
            directly on CRSP monthly data, for price-based signals like
            momentum). Auto-guessed from spec.data.normalized_mapping when
            not given.
        compustat_data_path: Compustat annual parquet path (compustat mode only).
        ccm_link_path: CCM link table parquet path (compustat mode only).
        output_path: If given, path where backtest results CSV will be saved.
        config_overrides: Optional per-run config overrides (e.g. for ablation
            experiments), merged into the resolved-spec-derived config.

    Returns:
        Complete Python script as a string.
    """
    # Build config from MethodSpec (same logic as BacktestEngine._build_config)
    engine = BacktestEngine()
    config = engine._build_config(spec, config_overrides)

    # Format config as a Python dict literal
    config_lines = _format_config(config)

    if signal_input_mode is None:
        signal_input_mode = "compustat" if _signal_needs_compustat(spec) else "crsp_only"
    if signal_input_mode not in ("compustat", "crsp_only"):
        raise ValueError("signal_input_mode must be 'compustat' or 'crsp_only'")

    if signal_input_mode == "compustat":
        compustat_requirements = (
            f"  - Compustat annual data at: {compustat_data_path}\n"
            f"    Expected columns: gvkey, datadate, plus whatever fields compute_signal() uses\n"
            f"  - CCM link table at: {ccm_link_path}\n"
            f"    Expected columns: gvkey, permno, linktype, linkprim, linkdt, linkenddt"
        )
    else:
        compustat_requirements = ""

    # Determine output filename
    factor_id = spec.factor_id or "factor"
    if output_path is None:
        output_path = f"results/{factor_id}_backtest_results.csv"

    script = _TEMPLATE.format(
        factor_id=factor_id,
        factor_name=spec.factor_name,
        paper_ref=spec.paper_ref or "",
        data_path=data_path,
        compustat_data_path=compustat_data_path,
        ccm_link_path=ccm_link_path,
        compustat_requirements=compustat_requirements,
        accounting_lag_months=spec.accounting_lag_months or 6,
        signal_input_mode=signal_input_mode,
        output_path=output_path,
        config_dict=config_lines,
        plugin_code=_indent_plugin(plugin_code),
    )

    return script


def _format_config(config: dict[str, Any]) -> str:
    """Format config dict as indented Python dict literal."""
    lines = []
    for key, val in config.items():
        if isinstance(val, str):
            lines.append(f'    "{key}": "{val}",')
        elif isinstance(val, bool):
            lines.append(f'    "{key}": {val},')
        elif val is None:
            lines.append(f'    "{key}": None,')
        else:
            lines.append(f'    "{key}": {val},')
    return "\n".join(lines)


def _indent_plugin(code: str) -> str:
    """Return plugin code without modification (top-level functions)."""
    return code.strip()


_TEMPLATE = '''\
#!/usr/bin/env python3
"""Backtest Script — {factor_name}

Factor ID: {factor_id}
Paper: {paper_ref}

Auto-generated by factor-replication-agent.
This is a standalone script: run it with `python3 <filename>.py`

Signal input mode: {signal_input_mode}

Requirements:
  - pandas, numpy
  - CRSP monthly data at: {data_path}
    Expected columns: permno, yyyymm (or date), ret, me, shrcd, exchcd, siccd
{compustat_requirements}
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ===========================================================================
# CONFIGURATION (derived from resolved MethodSpec)
# ===========================================================================

CONFIG = {{
{config_dict}
}}

DATA_PATH = "{data_path}"
COMPUSTAT_DATA_PATH = "{compustat_data_path}"
CCM_LINK_PATH = "{ccm_link_path}"
ACCOUNTING_LAG_MONTHS = {accounting_lag_months}
SIGNAL_INPUT_MODE = "{signal_input_mode}"  # "compustat" or "crsp_only"


# ===========================================================================
# SIGNAL PLUGIN (generated by MetaCoder) — compute_signal() + any *_hook functions
# ===========================================================================

{plugin_code}


# ===========================================================================
# BACKTEST ENGINE (inline implementation, mirrors src/steps/engine/BacktestEngine)
# ===========================================================================

def _dispatch(hook_name: str, fallback, *args):
    """Call the plugin's hook function if it's defined above, else the standard fallback."""
    hook_fn = globals().get(hook_name)
    if callable(hook_fn):
        return hook_fn(*args)
    return fallback(*args)


def load_data(data_path: str) -> pd.DataFrame:
    """Load CRSP monthly stock file."""
    path = Path(data_path)
    if not path.exists():
        print(f"ERROR: Data file not found: {{path}}")
        sys.exit(1)

    df = pd.read_parquet(path)
    # Standardize column names
    df.columns = [c.lower() for c in df.columns]

    if "date" in df.columns and "yyyymm" not in df.columns:
        df["yyyymm"] = (
            pd.to_datetime(df["date"]).dt.year * 100
            + pd.to_datetime(df["date"]).dt.month
        )

    for col in ("permno", "yyyymm"):
        if col in df.columns:
            df[col] = df[col].astype(int)

    return df


def build_signal_master_table(
    crsp_path: str, compustat_path: str, ccm_link_path: str, lag_months: int
) -> pd.DataFrame:
    """Merge Compustat annual data to permno via CCM link, then add
    time_avail_m = fiscal period end + lag_months, converted to YYYYMM.

    Inline equivalent of src/infra/data_layer.CCMLinker.merge() +
    TimeAvailComputer.compute_time_avail_m() so this script has no dependency
    on the rest of the repo.
    """
    crsp = pd.read_parquet(crsp_path)
    crsp.columns = [c.lower() for c in crsp.columns]
    compustat = pd.read_parquet(compustat_path)

    link = pd.read_parquet(ccm_link_path)
    link = link.copy()
    link["linkdt"] = pd.to_datetime(link["linkdt"])
    link["linkenddt"] = pd.to_datetime(link["linkenddt"]).fillna(pd.Timestamp.max)

    comp = compustat.copy()
    comp["_dt"] = pd.to_datetime(comp["datadate"])

    merged_rows = []
    for _, row in comp.iterrows():
        candidates = link[link["gvkey"] == row["gvkey"]]
        candidates = candidates[
            (candidates["linkdt"] <= row["_dt"]) & (row["_dt"] <= candidates["linkenddt"])
        ]
        if candidates.empty:
            continue
        if len(candidates) > 1 and "linkprim" in candidates.columns:
            primary = candidates[candidates["linkprim"] == "P"]
            if not primary.empty:
                candidates = primary
        link_row = candidates.iloc[0]
        merged_row = row.drop(labels=["_dt"]).to_dict()
        merged_row["permno"] = int(link_row["permno"])
        merged_rows.append(merged_row)

    result = pd.DataFrame(merged_rows)
    if not result.empty and "permno" in crsp.columns:
        valid_permnos = set(crsp["permno"].unique())
        result = result[result["permno"].isin(valid_permnos)].copy()

    dt = pd.to_datetime(result["datadate"])
    total_months = dt.dt.year * 12 + (dt.dt.month - 1) + lag_months
    year, month = divmod(total_months, 12)
    result["time_avail_m"] = (year * 100 + month + 1).astype(int)
    return result


def apply_missing_policy(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Standard missing-value policy: drop rows with missing return."""
    if config.get("missing_action", "drop") in ("drop", "unspecified"):
        return df.dropna(subset=["ret"]).copy()
    return df


def filter_universe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Filter to common stocks on major exchanges."""
    mask = df["shrcd"].isin([10, 11]) & df["exchcd"].isin([1, 2, 3])
    if "siccd" in df.columns:
        mask &= ~df["siccd"].between(6000, 6999)
    return df[mask].copy()


def expand_signal_to_holding(signal: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Expand annual signal to monthly holding period."""
    hp = int(config.get("holding_period_months", 12))
    rows = []
    for _, row in signal.iterrows():
        yyyymm = int(row["yyyymm"])
        year, month = divmod(yyyymm, 100)
        for h in range(1, hp + 1):
            m = month + h
            y = year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            rows.append({{
                "permno": int(row["permno"]),
                "yyyymm": y * 100 + m,
                "signal": float(row["signal"]),
            }})
    return pd.DataFrame(rows)


def compute_breakpoints(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute quantile breakpoints per month."""
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
    bp.columns = [f"q{{i}}" for i in range(n + 1)]
    return bp


def assign_portfolios(df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Assign stocks to quantile portfolios."""
    n = int(config.get("breakpoint_quantiles", 10))
    chunks = []
    for yyyymm, group in df.groupby("yyyymm"):
        if yyyymm not in breakpoints.index:
            continue
        bp = breakpoints.loc[yyyymm]
        bins = [bp[f"q{{i}}"] for i in range(n + 1)]
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


def compute_portfolio_returns(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute portfolio returns (VW or EW)."""
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
    """Compute long-short spread returns (config['long_leg']/['short_leg']
    are already resolved to 'low'/'high' tokens by BacktestEngine._build_config)."""
    n = int(config.get("breakpoint_quantiles", 10))
    long_leg = config.get("long_leg", "low")
    long_port = 1 if long_leg == "low" else n
    short_port = n if long_leg == "low" else 1

    rows = []
    for yyyymm, g in rets.groupby("yyyymm"):
        port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
        if long_port in port_map and short_port in port_map:
            rows.append({{
                "yyyymm": yyyymm,
                "ret_long": port_map[long_port],
                "ret_short": port_map[short_port],
                "ls_return": port_map[long_port] - port_map[short_port],
            }})
    return pd.DataFrame(rows)


def newey_west_tstat(series: np.ndarray, lags: int = 6) -> float:
    """Newey-West t-statistic."""
    n = len(series)
    if n < 2:
        return float("nan")
    mean_ret = series.mean()
    xd = series - mean_ret
    nw = float(np.dot(xd, xd)) / n
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1)
        gamma = float(np.dot(xd[lag:], xd[:-lag])) / n
        nw += 2.0 * w * gamma
    nw = max(nw, 0.0)
    return mean_ret / np.sqrt(nw / n) if nw > 0 else float("nan")


def compute_metrics(ls: pd.DataFrame) -> dict:
    """Compute summary performance metrics."""
    series = ls["ls_return"].dropna().values
    n = len(series)
    if n < 2:
        return {{"mean_monthly_return": float("nan"), "t_stat": float("nan"), "n_months": n}}

    mean_ret = float(series.mean())
    t_stat = newey_west_tstat(series)

    return {{
        "mean_monthly_return": mean_ret,
        "annualized_return": mean_ret * 12,
        "t_stat": float(t_stat),
        "n_months": n,
        "std_monthly": float(series.std()),
        "sharpe_annual": float(mean_ret / series.std() * np.sqrt(12)) if series.std() > 0 else float("nan"),
    }}


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    print(f"=== Backtest: {{CONFIG.get('factor_id', '{factor_id}')}} ===")
    print(f"Signal input mode: {{SIGNAL_INPUT_MODE}}")
    print()

    # 1. Build signal input and compute signal
    if SIGNAL_INPUT_MODE == "compustat":
        print(f"Building SignalMasterTable (CCM link + {{ACCOUNTING_LAG_MONTHS}}mo lag)...")
        signal_input = build_signal_master_table(
            DATA_PATH, COMPUSTAT_DATA_PATH, CCM_LINK_PATH, ACCOUNTING_LAG_MONTHS
        )
        print(f"  SignalMasterTable: {{len(signal_input):,}} rows")
    else:
        raw = load_data(DATA_PATH)
        signal_input = raw.rename(columns={{"yyyymm": "time_avail_m"}})

    print("Computing signal...")
    signal = compute_signal(signal_input)
    print(f"  Signal: {{len(signal):,}} observations, {{signal['permno'].nunique():,}} unique firms")
    print(f"  Date range: {{signal['yyyymm'].min()}} - {{signal['yyyymm'].max()}}")

    # 2. Load CRSP monthly returns, apply missing-value policy + universe filter
    msf = load_data(DATA_PATH)
    msf = _dispatch("apply_missing_policy_hook", apply_missing_policy, msf, CONFIG)
    msf = _dispatch("filter_universe_hook", filter_universe, msf, CONFIG)
    print(f"  CRSP rows after missing/universe policy: {{len(msf):,}}")

    # 3. Expand signal to holding period, merge with returns
    expanded = expand_signal_to_holding(signal, CONFIG)
    merged = msf.merge(expanded, on=["permno", "yyyymm"], how="inner")
    print(f"  Merged with returns: {{len(merged):,}} stock-months")

    # 4. Breakpoints -> portfolios -> portfolio returns -> long-short
    print("Computing breakpoints...")
    breakpoints = _dispatch("compute_breakpoints_hook", compute_breakpoints, merged, CONFIG)
    print(f"  Breakpoints computed for {{len(breakpoints)}} months")

    portfolios = _dispatch("assign_portfolios_hook", assign_portfolios, merged, breakpoints, CONFIG)
    print(f"  Assigned to portfolios: {{len(portfolios):,}} stock-months")

    port_returns = _dispatch("compute_returns_hook", compute_portfolio_returns, portfolios, CONFIG)
    print(f"  Portfolio returns: {{len(port_returns)}} portfolio-months")

    ls_returns = _dispatch("compute_long_short_hook", compute_long_short, port_returns, CONFIG)
    print(f"  Long-short series: {{len(ls_returns)}} months")

    # 5. Metrics
    metrics = compute_metrics(ls_returns)
    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"  Mean monthly return:  {{metrics['mean_monthly_return']*100:.3f}}%")
    print(f"  Annualized return:    {{metrics['annualized_return']*100:.2f}}%")
    print(f"  t-stat (Newey-West):  {{metrics['t_stat']:.2f}}")
    print(f"  Monthly std:          {{metrics.get('std_monthly', 0)*100:.3f}}%")
    print(f"  Sharpe (annual):      {{metrics.get('sharpe_annual', 0):.2f}}")
    print(f"  N months:             {{metrics['n_months']}}")
    print("=" * 50)

    # Save results
    output_path = Path("{output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ls_returns.to_csv(output_path, index=False)
    print(f"\\nReturn series saved to: {{output_path}}")

    # Save metrics
    import json
    metrics_path = output_path.with_suffix(".metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to: {{metrics_path}}")


if __name__ == "__main__":
    main()
'''
