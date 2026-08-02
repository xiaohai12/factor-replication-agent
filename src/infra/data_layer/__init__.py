"""Data Layer - CRSP/Compustat/CCM data access, snapshots, and data dictionary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.infra.data_layer import catalog, sources
from src.infra.data_layer.sources import (
    build_crsp_monthly_panel_ciz as build_crsp_monthly_panel_ciz,
    load_daily_msf_ciz as load_daily_msf_ciz,
)


# --- Data Dictionary ---


@dataclass
class FieldEntry:
    """Single entry in the field registry / data dictionary."""

    field: str
    dataset: str          # crsp | compustat
    table: str            # msf | funda | fundq | msenames | dlret | ccmxpf_linkhist
    description: str = ""
    unit: str = ""
    frequency: str = ""   # monthly | annual | quarterly
    available_from: Optional[int] = None
    notes: str = ""


# Concept-to-column resolution now lives in the declarative data catalog
# (`src/infra/data_layer/catalog.py`), the single source of truth across all
# sources (not just CRSP/Compustat). `DataDictionary.normalize_fields()` reads
# `catalog.concept_map()` + `catalog.source_of_column()`.


class DataDictionary:
    """Field registry for validating MethodSpec field references.

    Used by Semantic Extractor and Review Gate to check that referenced
    fields actually exist in the available datasets.
    """

    def __init__(self):
        self._entries: dict[str, FieldEntry] = {}

    def register(self, entry: FieldEntry) -> None:
        self._entries[entry.field] = entry

    def lookup(self, field_name: str) -> Optional[FieldEntry]:
        return self._entries.get(field_name)

    def exists(self, field_name: str) -> bool:
        return field_name in self._entries

    def list_fields(self, dataset: str | None = None, table: str | None = None) -> list[str]:
        entries = self._entries.values()
        if dataset:
            entries = [e for e in entries if e.dataset == dataset]
        if table:
            entries = [e for e in entries if e.table == table]
        return [e.field for e in entries]

    def load_from_yaml(self, path: str) -> None:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        for item in data:
            self.register(FieldEntry(**item))

    def normalize_fields(self, required_fields: list) -> dict[str, dict[str, str]]:
        """Map paper-concept field names to their physical {source, column} via
        the declarative data catalog (`catalog.py`), the single source of truth
        for which source owns which column.

        Tries three passes in order (exact match on the catalog's concept
        aliases), then a substring fallback:
          1. Exact match on field name (lower-cased)
          2. Exact match on source_detail string
          3. Exact match on concept string
          4. Substring match on source_detail / concept (keys >= 4 chars, to
             avoid false positives like "at" matching inside "compustat")

        Returns {paper_field_name: {"source": <catalog source>, "column":
        <physical column>}} for resolved fields. Unresolved fields are OMITTED
        — the reviewer hard-blocks a spec whose formula field has no resolved
        source, so nothing silently defaults to a data source (e.g. Compustat).
        """
        concept_map = catalog.concept_map()
        mapping: dict[str, dict[str, str]] = {}
        for entry in required_fields:
            field = entry.field if hasattr(entry, "field") else entry.get("field", "")
            source = (
                (entry.source_detail if hasattr(entry, "source_detail")
                 else entry.get("source_detail", "")) or ""
            ).lower()
            concept = (
                (entry.concept if hasattr(entry, "concept")
                 else entry.get("concept", "")) or ""
            ).lower()

            # Only use substring matching for keys >= 4 chars to avoid false positives
            # (e.g. "at" matching inside "compustat")
            col = (
                concept_map.get(field.lower())
                or concept_map.get(source)
                or concept_map.get(concept)
                or next((v for k, v in concept_map.items() if len(k) >= 4 and k in source), None)
                or next((v for k, v in concept_map.items() if len(k) >= 4 and k in concept), None)
            )
            if col:
                src = catalog.source_of_column(col)
                mapping[field] = {"source": src, "column": col}
        return mapping


# --- Data Snapshot ---


@dataclass
class SnapshotMetadata:
    """Metadata for a frozen data snapshot."""

    snapshot_id: str
    pull_date: str
    crsp_end_date: str
    compustat_end_date: str
    storage_path: str
    format: str = "parquet"
    hash: str = ""


class SnapshotManager:
    """Manages versioned data snapshots for reproducible experiments.

    Phase 1: WRDS query + local parquet cache.
    Phase 2+: Frozen snapshots, all runs use same data.
    """

    def __init__(self, base_path: str = "./data/snapshots"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[str, SnapshotMetadata] = {}

    def register_snapshot(self, meta: SnapshotMetadata) -> None:
        self._snapshots[meta.snapshot_id] = meta

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        return self._snapshots.get(snapshot_id)

    def list_snapshots(self) -> list[SnapshotMetadata]:
        """Get every registered snapshot (e.g. for a data-source picker UI)."""
        return list(self._snapshots.values())

    def get_latest(self) -> Optional[SnapshotMetadata]:
        if not self._snapshots:
            return None
        return list(self._snapshots.values())[-1]

    def load_table(self, snapshot_id: str, table_name: str) -> pd.DataFrame:
        """Load a specific table from a snapshot."""
        meta = self._snapshots.get(snapshot_id)
        if not meta:
            raise ValueError(f"Snapshot '{snapshot_id}' not found")
        path = Path(meta.storage_path) / f"{table_name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Table '{table_name}' not found in snapshot")
        return pd.read_parquet(path)


# Signal-input assembly and point-in-time linking live in the declarative
# DataSource registry (`sources.py`). Pipeline and generated scripts share that
# single implementation.


class DataLayer:
    """Unified data access layer for all pipeline modules.

    Provides:
    - Data dictionary for field validation (Extractor, Review Gate)
    - Snapshot management for reproducible data (Engine)
    - Returns-backbone loading via the DataSource registry (`sources.py`)
    """

    def __init__(self, data_path: str = "./data"):
        self.data_path = Path(data_path)
        self.dictionary = DataDictionary()
        self.snapshots = SnapshotManager(base_path=str(self.data_path / "snapshots"))

    def load_dictionary(self, yaml_path: str) -> None:
        """Load data dictionary from YAML."""
        self.dictionary.load_from_yaml(yaml_path)

    # --- Returns backbone facade ---
    # The single public entry the engine's `load_data` uses to obtain the
    # stock-return panel, resolved through the DataSource registry
    # (`sources.py`, the single source of truth) rather than calling a free
    # assembler directly.

    def load_returns(self, universe_name: str, returns_dir: str | Path | None = None) -> pd.DataFrame:
        """Load the returns panel for a MethodSpec `returns_universe` alias
        (e.g. "us_equity_crsp"). Resolves the alias to its registered
        `ReturnsUniverse` via the DataSource registry and loads from
        `returns_dir` (default `self.data_path`). Fails loud on an unregistered
        alias — never a silent default panel."""
        universe = sources.get_returns_universe(universe_name)
        return universe.load(returns_dir or self.data_path)

    def load_returns_by_layout(
        self, returns_layout: str, returns_dir: str | Path | None = None
    ) -> pd.DataFrame:
        """Same as `load_returns` but keyed by the engine-config
        `returns_layout` tag (e.g. "crsp_ciz") that `build_config` bakes into
        the run config — the path `BacktestExecutor.load_data` takes."""
        universe = sources.get_returns_universe_by_layout(returns_layout)
        return universe.load(returns_dir or self.data_path)


# ---------------------------------------------------------------------------
# The CRSP "new CIZ" returns-panel assembler (`build_crsp_monthly_panel_ciz` /
# `load_daily_msf_ciz` / `_ciz_shrcd` + the CIZ column/exchcd constants) lives
# in `src/infra/data_layer/sources.py` with the `CrspReturnsUniverse`
# DataSource. It's re-exported at the top of this module so existing importers
# are unchanged; the engine's `load_data` obtains the panel via
# `DataLayer.load_returns_by_layout` (the registry), not by calling the
# assembler directly.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SIGNAL-INPUT loading (`SIGNAL_SOURCES`/`LINK_TABLES`, `link_to_permno`, the
# link-table + raw-CSV loaders, `_load_source_frame`, `signal_input_sources`,
# `assemble_signal_master_table*`) lives in `src/infra/data_layer/sources.py`,
# reading directly from the DataSource registry (the single source of truth).
# Re-exported here under the same names so every importer
# (`from src.infra.data_layer import SIGNAL_SOURCES / link_to_permno /
# assemble_signal_master_table / _load_source_frame / ...`, incl. the generated
# standalone script) is unchanged. `SIGNAL_SOURCES` / `LINK_TABLES` are the
# catalog-derived views (themselves derived from the registry).
# ---------------------------------------------------------------------------

SIGNAL_SOURCES: dict[str, dict[str, Any]] = catalog.signal_sources()
LINK_TABLES: dict[str, dict[str, Any]] = catalog.LINK_TABLES

from src.infra.data_layer.sources import (  # noqa: E402  (re-export after catalog is built)
    link_to_permno as link_to_permno,
    signal_input_sources as signal_input_sources,
    assemble_signal_master_table as assemble_signal_master_table,
    assemble_signal_master_table_from_sources as assemble_signal_master_table_from_sources,
    _load_link_tables as _load_link_tables,
    _load_source_frame as _load_source_frame,
)


# ---------------------------------------------------------------------------
# Supplementary factor time series (2026-07-30): CRSP's own market index
# (CRSP_INDEX_MONTH.csv/CRSP_INDEX_DAILY.csv) and the Pastor-Stambaugh (2003)
# liquidity factors (liquidity_factors.csv). This is a SEPARATE, non-Ken-
# French factor set -- a supplement to `scripts/fetch_ff_factors.py`'s
# ff_factors.parquet (which already has mktrf/smb/hml/rmw/cma/umd/rf), not a
# replacement for it: neither raw file here carries a risk-free rate, so an
# excess market return can only be derived by joining in an external `rf`
# series (e.g. from ff_factors.parquet).
# ---------------------------------------------------------------------------

def load_crsp_index_factors(data_dir: str | Path, *, frequency: str = "monthly") -> pd.DataFrame:
    """Load CRSP's own market index return series.

    Args:
        frequency: "monthly" (CRSP_INDEX_MONTH.csv, keyed by `yyyymm`) or
            "daily" (CRSP_INDEX_DAILY.csv, keyed by `date`).

    Both real exports already use lower-case columns: vwretd/vwretx
    (value-weighted, with/without dividends), ewretd/ewretx (equal-weighted),
    sprtrn (S&P 500 return), spindx (S&P 500 level).
    """
    d = Path(data_dir) / "local"
    if frequency == "monthly":
        df = pd.read_csv(d / "CRSP_INDEX_MONTH.csv")
        dt = pd.to_datetime(df["mthcaldt"], format="%Y-%m-%d")
        df["yyyymm"] = (dt.dt.year * 100 + dt.dt.month).astype(int)
        return df.drop(columns=["mthcaldt"])
    if frequency == "daily":
        df = pd.read_csv(d / "CRSP_INDEX_DAILY.csv")
        df["date"] = pd.to_datetime(df["dlycaldt"], format="%Y-%m-%d")
        return df.drop(columns=["dlycaldt"])
    raise ValueError(f"Unknown frequency {frequency!r}: expected 'monthly' or 'daily'")


def load_liquidity_factors(data_dir: str | Path) -> pd.DataFrame:
    """Load the Pastor-Stambaugh (2003) liquidity factors (liquidity_factors.csv),
    keyed by `yyyymm`: `ps_level` (level), `ps_innov` (innovation -- the
    standard non-traded PS factor), `ps_vwf` (value-weighted traded PS
    factor). PS's own convention marks unavailable-history months with the
    placeholder value -99; those are converted to NaN here rather than kept
    as a bogus numeric value.
    """
    df = pd.read_csv(Path(data_dir) / "local" / "liquidity_factors.csv")
    dt = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["yyyymm"] = (dt.dt.year * 100 + dt.dt.month).astype(int)
    for col in ("ps_level", "ps_innov", "ps_vwf"):
        df.loc[df[col] <= -99, col] = float("nan")
    return df[["yyyymm", "ps_level", "ps_innov", "ps_vwf"]]


# ---------------------------------------------------------------------------
# Best-effort / lightly-wired loaders (2026-07-30) for the remaining raw WRDS
# exports in data/local/ that no signal plugin in this repo currently
# consumes. Kept OUTSIDE the declarative catalog (`catalog.py`) on purpose --
# registering a full DATA_CATALOG entry (join/physical_columns/columns) for a
# source nothing uses yet would be guessing at a paper's actual needs. Add a
# proper catalog entry (+ point this at `RAW_CSV_SOURCE_FILES`) once a real
# MethodSpec needs one of these.
# ---------------------------------------------------------------------------

def load_institutional_ownership_13f(
    data_dir: str | Path,
    *,
    crsp_cusip_map: pd.DataFrame | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Best-effort loader for the 13F institutional-ownership export
    (data/local/13F.csv).

    KNOWN LIMITATION (see docs/decision-log.md 2026-07-30 entry): this export
    has no `permno` column -- its own key is `cusip` -- and is resolved here
    via a CUSIP match against `CRSP_STOCK_MONTH.csv`'s own (permno, CUSIP)
    pairs using each CUSIP's MOST RECENT observed permno. This is NOT a
    point-in-time link (no validity window, unlike the CCM/IBES-CRSP link
    tables) -- a CUSIP reassigned across permnos at some point in CRSP's
    history could resolve to the wrong one. Do not treat this as production-
    quality until that's replaced with a real point-in-time CUSIP history.

    Args:
        crsp_cusip_map: optional pre-built [cusip, permno] map (e.g. from a
            prior call) to avoid re-reading the multi-GB CRSP monthly file
            for repeated 13F loads.
        nrows: dev/test-only row cap for the 13F export itself.
    """
    d = Path(data_dir) / "local"
    thirteen_f = pd.read_csv(d / "13F.csv", usecols=["rdate", "cusip", "InstOwn_Perc"], nrows=nrows)
    thirteen_f = thirteen_f.rename(columns={"InstOwn_Perc": "instown_perc"})
    thirteen_f["cusip"] = thirteen_f["cusip"].astype(str).str.zfill(8).str[:8]

    if crsp_cusip_map is None:
        crsp_monthly = pd.read_csv(
            d / "CRSP_STOCK_MONTH.csv",
            usecols=["PERMNO", "CUSIP"],
            dtype={"PERMNO": "int64", "CUSIP": "string"},
            low_memory=False,
        )
        crsp_cusip_map = (
            crsp_monthly.rename(columns={"PERMNO": "permno", "CUSIP": "cusip"})
            .dropna(subset=["cusip"])
            .drop_duplicates(subset=["cusip"], keep="last")[["cusip", "permno"]]
        )

    out = thirteen_f.merge(crsp_cusip_map, on="cusip", how="left")
    out["rdate"] = pd.to_datetime(out["rdate"], format="%Y-%m-%d", errors="coerce")
    out = out.dropna(subset=["permno", "rdate"]).copy()
    out["yyyymm"] = (out["rdate"].dt.year * 100 + out["rdate"].dt.month).astype(int)
    out["permno"] = out["permno"].astype(int)
    return out[["permno", "yyyymm", "instown_perc"]].reset_index(drop=True)


def load_ibes_recommendation_detail(data_dir: str | Path, *, nrows: int | None = None) -> pd.DataFrame:
    """Light pass-through loader for the raw IBES recommendation-detail
    export (data/local/IBES_RECOMMENDATION_DETAIL.csv): lower-cases columns
    and parses the date columns, but does NOT link to permno or resolve an
    availability month (`time_avail_m`) -- see this module's section comment
    above. `nrows=None` reads the full ~3.2M-row export; pass a small `nrows`
    for a cheap sample/dev check.
    """
    df = pd.read_csv(Path(data_dir) / "local" / "IBES_RECOMMENDATION_DETAIL.csv", nrows=nrows)
    df.columns = [c.lower() for c in df.columns]
    for col in ("actdats", "revdats", "anndats"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
    return df


def load_ibes_unadjusted_actual(data_dir: str | Path, *, nrows: int | None = None) -> pd.DataFrame:
    """Light pass-through loader for the raw IBES unadjusted-actual export
    (data/local/IBES_UNADJUSTED_ACTURAL.csv) -- see
    `load_ibes_recommendation_detail`'s docstring for the same caveat (no
    permno link / `time_avail_m` resolution yet). `nrows=None` reads the
    full ~25M-row export; pass a small `nrows` for a cheap sample/dev check.
    """
    df = pd.read_csv(Path(data_dir) / "local" / "IBES_UNADJUSTED_ACTURAL.csv", nrows=nrows)
    df.columns = [c.lower() for c in df.columns]
    for col in ("statpers", "fy0edats", "int0dats"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
    return df




