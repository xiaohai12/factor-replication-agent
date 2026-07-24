"""Backtest Script Generator - Produce standalone runnable backtest scripts.

After MetaCoder generates a plugin, this module combines:
  1. The signal plugin code (the compute_signal formula function)
  2. BacktestExecutor configuration derived from the resolved MethodSpec
  3. Data loading (CRSP-only or Compustat+CCM) and signal computation

into a single self-contained Python script that can be executed independently.

The generated script is a THIN WRAPPER: it imports `BacktestExecutor` and calls
`BacktestExecutor.run_with_config()` for the 9-step lifecycle (missing policy ->
universe filter -> merge signal -> breakpoints -> portfolios -> returns ->
long-short -> metrics) instead of re-implementing those steps inline. This
means the standalone script and the in-process engine share exactly one
implementation of the lifecycle and can never drift out of sync with each
other (see plan.md Phase 0). The tradeoff: the generated script now depends on
this repo being installed (`from src...` imports) rather than being fully
self-contained; that's an accepted tradeoff (see plan.md "Decisions").

Similarly, Compustat-mode signal input construction reuses
`src.infra.data_layer.CCMLinker` + `TimeAvailComputer` (the same classes
`DataLayer.get_signal_master_table()` uses) instead of a separate inline
CCM-linking implementation.
"""

from __future__ import annotations

from typing import Any

from src.steps.step3_codegen import registry as codegen_registry
from src.infra.models.method_spec import MethodSpec


# Sources the legacy binary crsp_only/compustat generated-script path handles.
# Anything beyond these (IBES/OptionMetrics/13F/...) routes to the source-driven
# "multi_source" mode (data_layer.assemble_signal_master_table_from_sources).
_BINARY_SIGNAL_SOURCES = {"crsp_msf", "comp_funda"}


def pick_signal_input_mode(spec: MethodSpec) -> str:
    """Choose the generated script's signal-input mode from the spec's SOURCE
    SET (plan.md data-loader Phase 3), fully driven by the reviewed MethodSpec's
    `data.normalized_mapping` — never a hardcoded data-source default:

      - raises when the source is UNKNOWN: an empty mapping (no source at all)
        or a column no registered catalog source declares (source==""). The
        signal source must come from the reviewed spec; the pipeline never
        silently defaults to Compustat/CRSP. (The reviewer hard-blocks these
        before codegen — this is the belt-and-suspenders net.)
      - "multi_source": the formula fields span a source beyond CRSP +
        Compustat (e.g. IBES/OptionMetrics) -> declarative multi-source loader.
      - "crsp_only": every field comes from CRSP monthly.
      - "compustat": Compustat is involved (optionally alongside CRSP) — the
        legacy binary case, kept so golden numbers don't move.
    """
    from src.infra.data_layer import signal_input_sources

    sources = set(signal_input_sources(spec))
    if not sources:
        raise ValueError(
            f"Cannot determine the signal input source for factor {spec.factor_id!r}: "
            "data.normalized_mapping is empty / resolves to no registered source. "
            "The signal source must come from the reviewed MethodSpec — map each "
            "formula field to an explicit {source, column} (or a catalog-registered "
            "column). The pipeline never defaults to a data source."
        )
    if "" in sources:
        unresolved = sorted({col for _c, col in spec.unresolved_source_fields()})
        raise ValueError(
            f"Signal input for factor {spec.factor_id!r} has columns with no "
            f"registered data source: {unresolved}. Register them in the data "
            "catalog (src/infra/data_layer/catalog.py) or map them to an explicit "
            "{source, column}; the pipeline never guesses a source."
        )
    if sources - _BINARY_SIGNAL_SOURCES:
        return "multi_source"
    if sources == {"crsp_msf"}:
        return "crsp_only"
    return "compustat"



def generate_backtest_script(
    spec: MethodSpec,
    plugin_code: str,
    data_path: str = "data/local/msf.parquet",
    signal_input_mode: str | None = None,
    compustat_data_path: str = "data/local/compustat_funda.parquet",
    ccm_link_path: str = "data/local/ccm_link.parquet",
    output_path: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    ff_factors_path: str | None = None,
    signal_data_dir: str = "",
) -> str:
    """Generate a standalone backtest script from a MethodSpec and plugin code.

    Args:
        spec: Resolved MethodSpec with all empirical decisions finalized.
        plugin_code: The signal plugin source code (the compute_signal function).
        data_path: Relative path to the CRSP monthly parquet file.
        signal_input_mode: "compustat" (build a SignalMasterTable via CCM
            linking + accounting lag before calling compute_signal),
            "crsp_only" (alias yyyymm -> time_avail_m and call compute_signal
            directly on CRSP monthly data, for price-based signals like
            momentum), or "multi_source" (build the master table from a
            directory of raw WRDS-shaped source tables via the declarative
            multi-source loader — for signals spanning IBES/OptionMetrics/etc).
            Auto-chosen by `pick_signal_input_mode(spec)` when not given.
        compustat_data_path: Compustat annual parquet path (compustat mode only).
        ccm_link_path: CCM link table parquet path (compustat mode only).
        output_path: If given, path where backtest results CSV will be saved.
        config_overrides: Optional per-run config overrides (e.g. for ablation
            experiments), merged into the resolved-spec-derived config.
        ff_factors_path: Optional path to a Fama-French factor + rf parquet
            (see scripts/fetch_ff_factors.py). When given and the file exists
            at run time, the script loads it and passes it to
            `BacktestExecutor.run_with_config(..., factors=...)` so
            `alpha_capm`/`alpha_ff3`/`alpha_ff5` get computed (plan.md Phase 2).
            When omitted, no factor-model alphas are computed.
        signal_data_dir: Directory of raw WRDS-shaped source tables
            (crsp_msf/comp_funda/ibes_*/optionm_*/... + link tables);
            required for "multi_source" mode, ignored otherwise.

    Returns:
        Complete Python script as a string.
    """
    from src.infra.data_layer import signal_input_sources

    # Build config from MethodSpec — the SAME resolved config BacktestExecutor.run()
    # would build in-process, embedded here so the script doesn't need to
    # reconstruct/re-parse the full MethodSpec at run time.
    config = codegen_registry.build_config(spec, config_overrides)

    # Format config as a Python dict literal
    config_lines = _format_config(config)

    if signal_input_mode is None:
        signal_input_mode = pick_signal_input_mode(spec)
    if signal_input_mode not in ("compustat", "crsp_only", "multi_source"):
        raise ValueError("signal_input_mode must be 'compustat', 'crsp_only', or 'multi_source'")

    # Baked {source: [columns]} map for multi_source mode (empty otherwise) so
    # the standalone script needs no MethodSpec at run time.
    signal_sources_map = signal_input_sources(spec) if signal_input_mode == "multi_source" else {}

    if signal_input_mode == "multi_source":
        compustat_requirements = (
            f"  - Raw WRDS-shaped source tables under: {signal_data_dir}\n"
            f"    Sources read: {', '.join(signal_sources_map) or '(none)'}"
        )
    elif signal_input_mode == "compustat":
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
        signal_data_dir=signal_data_dir,
        signal_sources_map=repr(signal_sources_map),
        output_path=output_path,
        config_dict=config_lines,
        plugin_code_literal=repr(plugin_code),
        ff_factors_path=ff_factors_path or "",
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


_TEMPLATE = '''\
#!/usr/bin/env python3
"""Backtest Script — {factor_name}

Factor ID: {factor_id}
Paper: {paper_ref}

Auto-generated by factor-replication-agent.
This is a standalone script: run it with `python3 <filename>.py`

Signal input mode: {signal_input_mode}

This script is a thin wrapper around `BacktestExecutor.run_with_config()` — it
does not re-implement the 9-step backtest lifecycle. Requires this repo to be
installed / importable (e.g. `pip install -e .`).

Requirements:
  - pandas, numpy
  - CRSP monthly data at: {data_path}
    Expected columns: permno, yyyymm (or date), ret, me, shrcd, exchcd, siccd
{compustat_requirements}
"""

import json
import sys
from pathlib import Path

import pandas as pd

from src.infra.data_layer import CCMLinker, TimeAvailComputer
from src.infra.models.plugin import PluginRecord
from src.infra.backtest_engine import BacktestExecutor


# ===========================================================================
# CONFIGURATION (derived from resolved MethodSpec)
# ===========================================================================

CONFIG = {{
{config_dict}
}}

FACTOR_ID = "{factor_id}"
DATA_PATH = "{data_path}"
COMPUSTAT_DATA_PATH = "{compustat_data_path}"
CCM_LINK_PATH = "{ccm_link_path}"
ACCOUNTING_LAG_MONTHS = {accounting_lag_months}
SIGNAL_INPUT_MODE = "{signal_input_mode}"  # "compustat" | "crsp_only" | "multi_source"
SIGNAL_DATA_DIR = "{signal_data_dir}"  # multi_source only: dir of raw WRDS-shaped tables
SIGNAL_INPUT_SOURCES = {signal_sources_map}  # multi_source only: {{source: [columns]}}
OUTPUT_PATH = "{output_path}"
FF_FACTORS_PATH = "{ff_factors_path}"  # optional; empty string if not supplied


# ===========================================================================
# SIGNAL PLUGIN (generated by MetaCoder) — compute_signal(). Kept as a source
# string (not spliced as raw code) so the exact same text can be exec'd here
# AND passed to BacktestExecutor as a PluginRecord, keeping the in-process
# engine and this script running identical signal code.
# ===========================================================================

PLUGIN_CODE = {plugin_code_literal}

exec(compile(PLUGIN_CODE, "<plugin:{factor_id}>", "exec"), globals())


def load_msf(path: str) -> pd.DataFrame:
    """Load CRSP monthly stock file."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Data file not found: {{p}}")
        sys.exit(1)
    df = pd.read_parquet(p)
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


def build_signal_input(msf: pd.DataFrame) -> pd.DataFrame:
    """Build the DataFrame passed to compute_signal(): either a Compustat-merged
    SignalMasterTable (via CCMLinker + TimeAvailComputer, same as
    DataLayer.get_signal_master_table()), a multi-source master table (via the
    declarative source-driven loader), or CRSP-only data with yyyymm aliased to
    time_avail_m."""
    if SIGNAL_INPUT_MODE == "multi_source":
        from src.infra.data_layer import assemble_signal_master_table_from_sources
        return assemble_signal_master_table_from_sources(
            SIGNAL_DATA_DIR, SIGNAL_INPUT_SOURCES, ACCOUNTING_LAG_MONTHS
        )
    if SIGNAL_INPUT_MODE == "compustat":
        compustat = pd.read_parquet(COMPUSTAT_DATA_PATH)
        ccm_link = pd.read_parquet(CCM_LINK_PATH)
        linker = CCMLinker()
        linker.load_link_table(ccm_link)
        return TimeAvailComputer().build_signal_master_table(
            msf, compustat, linker, lag_months=ACCOUNTING_LAG_MONTHS
        )
    return msf.rename(columns={{"yyyymm": "time_avail_m"}})


def load_factors() -> pd.DataFrame | None:
    """Load FF factor + rf data if FF_FACTORS_PATH was supplied and the file
    exists at run time (plan.md Phase 2) -- fetched once, ahead of time, via
    scripts/fetch_ff_factors.py; never fetched here. Returns None (no
    factor-model alphas computed) if not supplied/not found."""
    if not FF_FACTORS_PATH:
        return None
    p = Path(FF_FACTORS_PATH)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def main():
    print(f"=== Backtest: {{FACTOR_ID}} ===")
    print(f"Signal input mode: {{SIGNAL_INPUT_MODE}}")
    print()

    if SIGNAL_INPUT_MODE == "multi_source":
        # Returns panel + signal inputs both come from the raw WRDS-shaped
        # tables in SIGNAL_DATA_DIR (crsp_msf/msenames/msedelist assembled into
        # the flat panel; other sources joined by the master-table builder).
        from src.infra.data_layer import build_crsp_monthly_panel
        msf = build_crsp_monthly_panel(SIGNAL_DATA_DIR)
    else:
        msf = load_msf(DATA_PATH)

    signal_input = build_signal_input(msf)
    print("Computing signal...")
    signal = compute_signal(signal_input)
    print(f"  Signal: {{len(signal):,}} observations, {{signal['permno'].nunique():,}} unique firms")
    print(f"  Date range: {{signal['yyyymm'].min()}} - {{signal['yyyymm'].max()}}")

    plugin = PluginRecord(plugin_id=f"{{FACTOR_ID}}_script", factor_id=FACTOR_ID, code=PLUGIN_CODE)
    factors = load_factors()

    print("Running BacktestExecutor...")
    engine = BacktestExecutor()
    result = engine.run_with_config(signal, CONFIG, plugin=plugin, data=msf, factors=factors)
    metrics = result["metrics"]
    ls_returns = result["return_series"]

    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"  Mean monthly return:  {{metrics.get('mean_monthly_return', float('nan'))*100:.3f}}%")
    print(f"  Annualized return:    {{metrics.get('annualized_return', 0)*100:.2f}}%")
    print(f"  t-stat (Newey-West):  {{metrics.get('t_stat', float('nan')):.2f}}")
    print(f"  Sharpe ratio:         {{metrics.get('sharpe_ratio', float('nan')):.2f}}")
    if "alpha_capm" in metrics:
        print(f"  Alpha (CAPM):         {{metrics['alpha_capm']*100:.3f}}% (t={{metrics['alpha_capm_tstat']:.2f}})")
    if "alpha_ff3" in metrics:
        print(f"  Alpha (FF3):          {{metrics['alpha_ff3']*100:.3f}}% (t={{metrics['alpha_ff3_tstat']:.2f}})")
    if "alpha_ff5" in metrics:
        print(f"  Alpha (FF5):          {{metrics['alpha_ff5']*100:.3f}}% (t={{metrics['alpha_ff5_tstat']:.2f}})")
    print(f"  N months:             {{metrics.get('n_months')}}")
    print("=" * 50)

    output_path = Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ls_returns.to_csv(output_path, index=False)
    print(f"\\nReturn series saved to: {{output_path}}")

    metrics_path = output_path.with_suffix(".metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to: {{metrics_path}}")


if __name__ == "__main__":
    main()
'''
