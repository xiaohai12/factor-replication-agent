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
other. The tradeoff: the generated script now depends on
this repo being installed (`from src...` imports) rather than being fully
self-contained; runtime provenance must therefore include the repository code.

Similarly, Compustat-mode signal-input construction reuses the same declarative
loader the pipeline uses — `src.infra.data_layer.assemble_signal_master_table_from_sources`
(reads `comp_funda.parquet` + `ccm_lnkhist.parquet` and links gvkey->permno
point-in-time). The "compustat" and "multi_source" modes share this one
loader; they differ only in how the RETURNS panel is loaded.
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
    SET, fully driven by the reviewed MethodSpec's
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
    output_path: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    ff_factors_path: str | None = None,
    signal_data_dir: str = "",
    resolved_config: dict[str, Any] | None = None,
    precomputed_signal_path: str | None = None,
) -> str:
    """Generate a standalone backtest script from a MethodSpec and plugin code.

    Args:
        spec: Resolved MethodSpec with all empirical decisions finalized.
        plugin_code: The signal plugin source code (the compute_signal function).
        data_path: Relative path to the CRSP monthly parquet file.
        signal_input_mode: "compustat" / "multi_source" (both build the master
            table [permno, time_avail_m, *cols] from a directory of raw
            WRDS-shaped source tables via the SAME declarative source-driven
            loader; the two modes differ only in how the RETURNS panel is
            loaded, see `main()`), or
            "crsp_only" (alias yyyymm -> time_avail_m and call compute_signal
            directly on CRSP monthly data, for price-based signals like
            momentum). Auto-chosen by `pick_signal_input_mode(spec)` when not given.
        output_path: If given, path where backtest results CSV will be saved.
        config_overrides: Optional per-run config overrides (e.g. for ablation
            experiments), merged into the resolved-spec-derived config.
        ff_factors_path: Optional path to a Fama-French factor + rf parquet
            (see scripts/fetch_ff_factors.py). When given and the file exists
            at run time, the script loads it and passes it to
            `BacktestExecutor.run_with_config(..., factors=...)` so
            `alpha_capm`/`alpha_ff3`/`alpha_ff5` get computed.
            When omitted, no factor-model alphas are computed.
        signal_data_dir: Directory of raw WRDS-shaped source tables
            (crsp_msf/comp_funda/ibes_*/optionm_*/... + link tables);
            required for "multi_source" mode, ignored otherwise.
        resolved_config: If the caller already resolved the config via
            `codegen_registry.build_config(spec, config_overrides)` (e.g.
            `BacktestRunner.build_script`, which needs it pre-execution for
            `config_hash`/`execution_id`), pass it here to reuse that exact
            dict instead of resolving a second, independent copy -- avoids
            computing `build_config` twice per script (and, since an invalid/
            no-op override now warns, emitting the same warning twice).
        precomputed_signal_path: If given, the generated script SKIPS calling
            `compute_signal()` entirely and instead reads this parquet path
            (`[permno, yyyymm, signal]`) directly as the signal fed into
            `BacktestExecutor.run_with_config()`. Used for a C&Z signal
            BRIDGE track (docs/multi-config-evidence-plan.md Phase C/D --
            see `src.infra.reference.cz_bridge`): the SAME resolved config
            runs against a DIFFERENT (externally supplied) signal, isolating
            signal-implementation differences from portfolio-construction
            differences. `plugin_code` is still embedded/exec'd for parity
            with every other generated script (harmless -- its
            `compute_signal` is simply never called), so the script stays
            structurally identical either way.

    Returns:
        Complete Python script as a string.
    """
    from src.infra.data_layer import signal_input_sources

    # Build config from MethodSpec — the SAME resolved config BacktestExecutor.run()
    # would build in-process, embedded here so the script doesn't need to
    # reconstruct/re-parse the full MethodSpec at run time.
    config = resolved_config if resolved_config is not None else codegen_registry.build_config(spec, config_overrides)

    # Format config as a Python dict literal
    config_lines = _format_config(config)

    if signal_input_mode is None:
        signal_input_mode = pick_signal_input_mode(spec)
    if signal_input_mode not in ("compustat", "crsp_only", "multi_source"):
        raise ValueError("signal_input_mode must be 'compustat', 'crsp_only', or 'multi_source'")

    # Baked {source: [columns]} map for the source-driven modes (empty for
    # crsp_only) so the standalone script needs no MethodSpec at run time.
    # "compustat" and "multi_source" share ONE declarative loader
    # (assemble_signal_master_table_from_sources); the mode names remain only as
    # the spec classification (see pick_signal_input_mode) + the returns-loading
    # choice in the generated `main()`.
    signal_sources_map = (
        signal_input_sources(spec)
        if signal_input_mode in ("compustat", "multi_source")
        else {}
    )

    if signal_input_mode in ("compustat", "multi_source"):
        compustat_requirements = (
            f"  - Raw WRDS-shaped source tables under: {signal_data_dir}\n"
            f"    Sources read: {', '.join(signal_sources_map) or '(none)'}"
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
        compustat_requirements=compustat_requirements,
        signal_input_mode=signal_input_mode,
        signal_data_dir=signal_data_dir,
        signal_sources_map=repr(signal_sources_map),
        output_path=output_path,
        config_dict=config_lines,
        plugin_code_literal=repr(plugin_code),
        ff_factors_path=ff_factors_path or "",
        precomputed_signal_path=precomputed_signal_path or "",
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
from pathlib import Path

import pandas as pd

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
# Read from CONFIG (not a separately-baked constant) so a
# config_overrides={{"accounting_lag_months": ...}} experiment actually takes
# effect here -- this used to be an independently-templated
# `spec.accounting_lag_months or 6` that silently ignored any override to the
# CONFIG key of the same name (see docs/multi-config-evidence-plan.md D4 /
# docs/decision-log.md 2026-08-03).
ACCOUNTING_LAG_MONTHS = CONFIG["accounting_lag_months"]
SIGNAL_INPUT_MODE = "{signal_input_mode}"  # "compustat" | "crsp_only" | "multi_source"
SIGNAL_DATA_DIR = "{signal_data_dir}"  # multi_source only: dir of raw WRDS-shaped tables
SIGNAL_INPUT_SOURCES = {signal_sources_map}  # multi_source only: {{source: [columns]}}
OUTPUT_PATH = "{output_path}"
FF_FACTORS_PATH = "{ff_factors_path}"  # optional; empty string if not supplied
PRECOMPUTED_SIGNAL_PATH = "{precomputed_signal_path}"  # optional; when set, skip compute_signal() (C&Z bridge track)


# ===========================================================================
# SIGNAL PLUGIN (generated by MetaCoder) — compute_signal(). Kept as a source
# string (not spliced as raw code) so the exact same text can be exec'd here
# AND passed to BacktestExecutor as a PluginRecord, keeping the in-process
# engine and this script running identical signal code.
# ===========================================================================

PLUGIN_CODE = {plugin_code_literal}

exec(compile(PLUGIN_CODE, "<plugin:{factor_id}>", "exec"), globals())


def load_msf(path: str) -> pd.DataFrame:
    """Load CRSP monthly stock file: the legacy pre-flattened parquet at
    `path` if it exists (kept for existing synthetic-data/golden-number
    fixtures that still ship one), otherwise assembled from the real WRDS
    "new CIZ" raw-table export directory (SIGNAL_DATA_DIR) the same way
    "multi_source" mode's `main()` branch does. Without this fallback, a
    "compustat"/"crsp_only" mode factor run against a real-data-only snapshot
    (data/local/*.csv, no crsp_msf.parquet) fails here with a misleading
    "Data file not found" even though the real data IS present, just not in
    the legacy pre-flattened format."""
    p = Path(path)
    if not p.exists():
        # SIGNAL_DATA_DIR is the PARENT of the raw-CSV "local" folder (the
        # same convention `assemble_signal_master_table_from_sources()` uses
        # -- it appends "/local" itself); `build_crsp_monthly_panel_ciz()`
        # wants the actual CSV directory, so append it here too.
        from src.infra.data_layer import build_crsp_monthly_panel_ciz
        return build_crsp_monthly_panel_ciz(Path(SIGNAL_DATA_DIR) / "local")
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
    """Build the DataFrame passed to compute_signal(): a source-driven
    SignalMasterTable [permno, time_avail_m, *cols] via the declarative
    multi-source loader (both "compustat" and "multi_source" modes share one
    loader), or CRSP-only data with yyyymm aliased to time_avail_m
    ("crsp_only", for price-based signals like momentum)."""
    if SIGNAL_INPUT_MODE in ("multi_source", "compustat"):
        from src.infra.data_layer import assemble_signal_master_table_from_sources
        return assemble_signal_master_table_from_sources(
            SIGNAL_DATA_DIR, SIGNAL_INPUT_SOURCES, ACCOUNTING_LAG_MONTHS
        )
    return msf.rename(columns={{"yyyymm": "time_avail_m"}})


def load_factors() -> pd.DataFrame | None:
    """Load FF factor + rf data if FF_FACTORS_PATH was supplied and the file
    exists at run time -- fetched once, ahead of time, via
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
        # Returns panel + signal inputs both come from the real WRDS "new
        # CIZ" export under SIGNAL_DATA_DIR/local/ (CRSP_STOCK_MONTH.csv +
        # CRSP_DELISTING.csv assembled into the flat panel; other sources
        # joined by the master-table builder). SIGNAL_DATA_DIR itself is the
        # PARENT of the raw-CSV "local" folder -- the SAME convention
        # `assemble_signal_master_table_from_sources()` uses below (it
        # appends "/local" internally for every raw-CSV source, including
        # CRSP-as-signal-source); `build_crsp_monthly_panel_ciz()` itself
        # wants the actual CSV directory, so it must be appended here too.
        # The legacy 3-table crsp_msf/msenames/msedelist assembler was
        # removed 2026-07-31.
        from src.infra.data_layer import build_crsp_monthly_panel_ciz
        msf = build_crsp_monthly_panel_ciz(Path(SIGNAL_DATA_DIR) / "local")
    else:
        msf = load_msf(DATA_PATH)

    if PRECOMPUTED_SIGNAL_PATH:
        # C&Z bridge track (docs/multi-config-evidence-plan.md Phase C/D):
        # the SAME resolved CONFIG below runs against a signal computed
        # OUTSIDE this script (see src.infra.reference.cz_bridge) instead of
        # this factor's own compute_signal() -- isolating signal-
        # implementation differences from portfolio-construction
        # differences. compute_signal() is never called in this branch.
        print(f"Loading precomputed (bridge) signal from: {{PRECOMPUTED_SIGNAL_PATH}}")
        signal = pd.read_parquet(PRECOMPUTED_SIGNAL_PATH)
    else:
        signal_input = build_signal_input(msf)
        print("Computing signal...")
        signal = compute_signal(signal_input)
    print(f"  Signal: {{len(signal):,}} observations, {{signal['permno'].nunique():,}} unique firms")
    print(f"  Date range: {{signal['yyyymm'].min()}} - {{signal['yyyymm'].max()}}")

    # Persist the REALIZED signal series (docs/multi-config-evidence-plan.md
    # Phase A1.1). Captured HERE -- compute_signal's own output (or the
    # bridge signal, loaded as-is above), before any universe filter /
    # breakpoint / portfolio step -- so a "controlled" post-signal config
    # comparison (e.g. weighting_rule only) can assert this file is
    # unchanged across tracks, and a "controlled" pre-signal comparison
    # (e.g. accounting_lag_months) can confirm it DID change.
    signal_path = Path(OUTPUT_PATH).with_name(Path(OUTPUT_PATH).stem + ".signal.parquet")
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal[["permno", "yyyymm", "signal"]].to_parquet(signal_path, index=False)
    print(f"  Signal series saved to: {{signal_path}}")

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
