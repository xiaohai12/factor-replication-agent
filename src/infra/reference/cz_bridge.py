"""C&Z signal bridge (Phase C/D, docs/multi-config-evidence-plan.md) --
a REAL, working, EXTENSIBLE adapter registry: `CZ_BRIDGE_SIGNALS` maps
factor_id -> a ported C&Z formula, and grows by adding one verified entry at
a time, not by a single one-off script.

Scope, stated precisely: C&Z's own predictor scripts
(`data/CZ code/Signals/pyCode/Predictors/*.py`) import `polars`, which is NOT
a project dependency (see `docs/decision-log.md`/session memory on why
`polars` stays out of this repo) -- so this module does NOT subprocess-execute
their script. Instead, for factors simple enough that their C&Z formula is a
short, fully-specified transformation of ONE already-registered data source
(see e.g. `data/CZ code/Signals/pyCode/Predictors/AssetGrowth.py`'s
docstring: input is exactly `[gvkey, permno, time_avail_m, at]`), this module
PORTS their published formula verbatim and runs it against OUR OWN
DataLayer-assembled panel of the SAME real data. This is a real, working
bridge signal for those factors -- not a placeholder -- but it is not "run
their code"; it is "recompute their documented method on the same inputs".

WHY THIS ISN'T (and can't safely be) FULLY GENERAL FOR ALL ~200 C&Z
predictors: some are this simple (single-source, a short algebraic formula,
a lag that's a clean multiple of 12 months); many are NOT -- they merge
multiple sources (e.g. `BM.py` needs both `m_aCompustat.parquet` AND
`SignalMasterTable.parquet`'s monthly market equity, matched via a
date-period comparison, not a plain row-shift), apply discretionary
edge-case handling, or use PIT logic beyond what a short docstring states.
Automating a generic port across ALL of them without individually reading
and verifying each script would risk silently WRONG bridge signals -- worse
than no bridge at all, since a fabricated-but-wrong comparison would
undermine the very research question this project exists to answer. Each
entry in `CZ_BRIDGE_SIGNALS` is therefore added only after reading and
verifying the ACTUAL source file, the same way `asset_growth_from_panel`/
`accruals_from_panel` below were.

Also note: several of these predictors' own `m_aCompustat.parquet` is a
MONTHLY, forward-filled panel (hence their literal `.shift(12)`), while our
own DataLayer produces one row per firm-FISCAL-YEAR-OBSERVATION -- the
per-function docstrings below explain the resulting (deliberate, documented)
shift-count adaptation (12 months -> 1 row) for each one.

`compute_cz_bridge_signal(factor_id, data_dir)` is the one public entry
point `MultiTrackController`/analysis scripts should call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


def asset_growth_from_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Direct port of `data/CZ code/Signals/pyCode/Predictors/AssetGrowth.py`'s
    formula: `AssetGrowth = (at - l12.at) / l12.at`, division-by-zero treated
    as missing (verbatim from their `np.where` line).

    IMPORTANT SHIFT-COUNT DIFFERENCE FROM THEIR LITERAL SCRIPT: their own
    `m_aCompustat.parquet` is a MONTHLY, forward-filled panel (one row per
    firm-MONTH), so their `.shift(12)` means "12 months ago" = the prior
    fiscal year's `at`. Our own `assemble_signal_master_table_from_sources`
    (this module's real-data entry point) instead produces one row per
    firm-FISCAL-YEAR-OBSERVATION (annual frequency, not forward-filled to
    every month) -- see `src/infra/data_layer/sources.py::
    _load_generic_signal_frame`. On THAT shape, shifting by 1 ROW already
    means "the prior fiscal year's `at`", the same economic quantity their
    12-MONTH shift computes on their monthly panel. Shifting by 12 rows here
    would incorrectly look back 12 FISCAL YEARS. This function therefore
    shifts by 1, not 12 -- a deliberate adaptation to this repo's panel
    shape, not a deviation from C&Z's actual formula.

    `panel` must have columns `[permno, time_avail_m, at]`, one row per
    firm-fiscal-year-observation, sorted or sortable by
    `[permno, time_avail_m]`. Returns `[permno, yyyymm, signal]`, NaN rows
    dropped (matching their `save_predictor`'s behavior of dropping missing
    values before saving).
    """
    df = panel[["permno", "time_avail_m", "at"]].copy()
    df = df.sort_values(["permno", "time_avail_m"])
    df["l_at"] = df.groupby("permno")["at"].shift(1)
    df["signal"] = np.where(
        df["l_at"] == 0,
        np.nan,
        (df["at"] - df["l_at"]) / df["l_at"],
    )
    out = df.rename(columns={"time_avail_m": "yyyymm"})[["permno", "yyyymm", "signal"]]
    return out.dropna(subset=["signal"]).reset_index(drop=True)


def accruals_from_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Direct port of `data/CZ code/Signals/pyCode/Predictors/Accruals.py`'s
    formula (Sloan 1996 working-capital accruals, scaled by average total
    assets):

        Accruals = ((act - l.act) - (che - l.che)
                    - ((lct - l.lct) - (dlc - l.dlc) - (tempTXP - l.tempTXP))
                    - dp) / ((at + l.at) / 2)

    where `tempTXP = txp.fillna(0)` (verbatim from their script -- missing
    tax payable treated as zero, not as missing).

    Same shift-count adaptation as `asset_growth_from_panel`: their
    `.shift(12)` (12 MONTHS on their monthly panel) becomes a 1-ROW shift on
    our own annual (one-row-per-fiscal-year) panel -- the same economic
    quantity ("prior fiscal year's value"), not a deviation from their
    formula.

    `panel` must have columns `[permno, time_avail_m, act, che, lct, dlc,
    at, dp]` plus optionally `txp` (treated as entirely missing -- i.e. 0 --
    if the column isn't present at all, matching `fillna(0)`'s effect).
    Duplicate `[permno, time_avail_m]` rows are dropped (keep first),
    matching their own `drop_duplicates` call. Returns
    `[permno, yyyymm, signal]`, NaN/inf rows dropped.
    """
    cols = ["permno", "time_avail_m", "act", "che", "lct", "dlc", "at", "dp"]
    df = panel[cols + (["txp"] if "txp" in panel.columns else [])].copy()
    if "txp" not in df.columns:
        df["txp"] = np.nan

    df = df.drop_duplicates(subset=["permno", "time_avail_m"], keep="first")
    df = df.sort_values(["permno", "time_avail_m"])

    df["temp_txp"] = df["txp"].fillna(0)
    for col in ("act", "che", "lct", "dlc", "temp_txp", "at"):
        df[f"l_{col}"] = df.groupby("permno")[col].shift(1)

    df["signal"] = (
        (df["act"] - df["l_act"])
        - (df["che"] - df["l_che"])
        - (
            (df["lct"] - df["l_lct"])
            - (df["dlc"] - df["l_dlc"])
            - (df["temp_txp"] - df["l_temp_txp"])
        )
        - df["dp"]
    ) / ((df["at"] + df["l_at"]) / 2)

    out = df.rename(columns={"time_avail_m": "yyyymm"})[["permno", "yyyymm", "signal"]]
    out = out.replace([np.inf, -np.inf], np.nan)
    return out.dropna(subset=["signal"]).reset_index(drop=True)


def convdebt_from_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Direct port of `data/CZ code/Signals/pyCode/Predictors/ConvDebt.py`'s
    formula (Valta's convertible-debt indicator, Table 4 "DCONV"):

        ConvDebt = 1 if (dc not missing and dc != 0)
                      or (cshrc not missing and cshrc != 0)
                   else 0

    where `dc` is deferred charges and `cshrc` is common shares reserved for
    conversion. Contemporaneous -- NO lag/shift at all (unlike
    `asset_growth_from_panel`/`accruals_from_panel`), matching their script
    exactly; this is the simplest of the three ported factors.

    `panel` must have columns `[permno, time_avail_m, dc, cshrc]`. Duplicate
    `[permno, time_avail_m]` rows are dropped (keep first), matching their
    own `drop_duplicates` call. Returns `[permno, yyyymm, signal]` with
    `signal` in `{0, 1}` -- never NaN/dropped (0 is itself a valid,
    meaningful signal value here, not a missing-data sentinel).
    """
    df = panel[["permno", "time_avail_m", "dc", "cshrc"]].copy()
    df = df.drop_duplicates(subset=["permno", "time_avail_m"], keep="first")
    df = df.sort_values(["permno", "time_avail_m"])

    df["signal"] = 0
    df.loc[
        ((df["dc"].notna()) & (df["dc"] != 0))
        | ((df["cshrc"].notna()) & (df["cshrc"] != 0)),
        "signal",
    ] = 1

    return df.rename(columns={"time_avail_m": "yyyymm"})[
        ["permno", "yyyymm", "signal"]
    ].reset_index(drop=True)


# factor_id -> (source columns needed for assemble_signal_master_table_from_sources,
#               accounting_lag_months C&Z's own script's time_avail_m convention
#               assumes, pure computation function taking that assembled panel).
CZ_BRIDGE_SIGNALS: dict[str, tuple[dict[str, list[str]], int, Callable[[pd.DataFrame], pd.DataFrame]]] = {
    "cooper_gulen_schill_2008_asset_growth": (
        {"comp_funda": ["at"]}, 6, asset_growth_from_panel,
    ),
    "sloan_1996_accruals": (
        {"comp_funda": ["act", "che", "lct", "dlc", "at", "dp", "txp"]}, 6, accruals_from_panel,
    ),
    "Valta_StrategicDefault_ConvertibleDebt": (
        {"comp_funda": ["dc", "cshrc"]}, 6, convdebt_from_panel,
    ),
}


def compute_cz_bridge_signal(factor_id: str, data_dir: str | Path) -> pd.DataFrame | None:
    """Compute the C&Z bridge signal for `factor_id` against the real data
    under `data_dir` (the same snapshot `storage_path` convention used
    elsewhere -- see `assemble_signal_master_table_from_sources`). Returns
    `None` if `factor_id` has no registered bridge (see module docstring for
    why most factors don't -- this is not a general-purpose C&Z re-
    implementation)."""
    entry = CZ_BRIDGE_SIGNALS.get(factor_id)
    if entry is None:
        return None
    sources, lag_months, compute_fn = entry

    from src.infra.data_layer.sources import assemble_signal_master_table_from_sources

    panel = assemble_signal_master_table_from_sources(data_dir, sources, lag_months)
    return compute_fn(panel)
