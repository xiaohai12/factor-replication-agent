"""Data Layer - CRSP/Compustat/CCM data access, snapshots, and data dictionary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.infra.data_layer import catalog


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


# --- CCM Linking ---


class CCMLinker:
    """Handles CRSP-Compustat linking via CCM link table.

    Rules (per docs/architecture.md Section 3.2):
    - linktype IN ('LC', 'LU')
    - linkprim IN ('P', 'C')
    - Match by linkdt/linkenddt range (point-in-time)
    - One permno maps to one gvkey at a time (priority: linkprim='P')
    - Duplicate links and link gaps are logged
    """

    def __init__(self):
        self._link_table: Optional[pd.DataFrame] = None
        self.link_issues: list[str] = []

    def load_link_table(self, link_df: pd.DataFrame) -> None:
        """Load CCM link table (ccmxpf_linkhist or equivalent)."""
        # Filter to valid link types
        mask = (
            link_df["linktype"].isin(["LC", "LU"])
            & link_df["linkprim"].isin(["P", "C"])
        )
        self._link_table = link_df[mask].copy()

    def merge(
        self,
        crsp_df: pd.DataFrame,
        compustat_df: pd.DataFrame,
        date_col: str = "date",
    ) -> pd.DataFrame:
        """Merge CRSP and Compustat data using point-in-time CCM links.

        For each Compustat row (gvkey, ``date_col``), finds the permno valid
        at that date via ``linkdt <= date <= linkenddt`` (open-ended
        ``linkenddt`` treated as valid through the present). When multiple
        links are valid at the same date, the ``linkprim == 'P'`` (primary)
        link wins. Rows whose resolved permno is absent from ``crsp_df`` are
        dropped (not present in the CRSP universe). All drops/ambiguities are
        logged to ``self.link_issues``.

        Returns merged DataFrame with both permno and gvkey columns.
        """
        if self._link_table is None:
            raise RuntimeError("Link table not loaded. Call load_link_table first.")

        self.link_issues = []
        link = self._link_table.copy()
        link["linkdt"] = pd.to_datetime(link["linkdt"])
        link["linkenddt"] = pd.to_datetime(link["linkenddt"]).fillna(pd.Timestamp.max)

        comp = compustat_df.copy()
        comp["_dt"] = pd.to_datetime(comp[date_col])

        merged_rows: list[dict] = []
        for _, row in comp.iterrows():
            candidates = link[link["gvkey"] == row["gvkey"]]
            candidates = candidates[
                (candidates["linkdt"] <= row["_dt"]) & (row["_dt"] <= candidates["linkenddt"])
            ]
            if candidates.empty:
                self.link_issues.append(
                    f"No CCM link for gvkey={row['gvkey']} at {row[date_col]}"
                )
                continue
            if len(candidates) > 1 and "linkprim" in candidates.columns:
                primary = candidates[candidates["linkprim"] == "P"]
                if not primary.empty:
                    candidates = primary
                else:
                    self.link_issues.append(
                        f"Multiple non-primary links for gvkey={row['gvkey']} "
                        f"at {row[date_col]}; using first match"
                    )
            link_row = candidates.iloc[0]
            merged_row = row.drop(labels=["_dt"]).to_dict()
            merged_row["permno"] = int(link_row["permno"])
            merged_rows.append(merged_row)

        if not merged_rows:
            return compustat_df.iloc[0:0].assign(permno=pd.Series(dtype="int64"))

        result = pd.DataFrame(merged_rows)
        if crsp_df is not None and "permno" in crsp_df.columns:
            valid_permnos = set(crsp_df["permno"].unique())
            before = len(result)
            result = result[result["permno"].isin(valid_permnos)].copy()
            dropped = before - len(result)
            if dropped:
                self.link_issues.append(
                    f"{dropped} row(s) dropped: linked permno not present in CRSP universe"
                )
        return result.reset_index(drop=True)

    def check_coverage(self, merged_df: pd.DataFrame) -> dict[str, Any]:
        """Check merge coverage and report potential issues."""
        n_rows = len(merged_df)
        n_permno = int(merged_df["permno"].nunique()) if "permno" in merged_df.columns else 0
        return {
            "n_rows": n_rows,
            "n_unique_permno": n_permno,
            "n_link_issues": len(self.link_issues),
            "link_issues": list(self.link_issues),
        }


# --- Main Data Layer Facade ---


class TimeAvailComputer:
    """Computes point-in-time available date (time_avail_m) for accounting data.

    Follows C&Z convention: lag is handled at the data layer so that
    signal plugins only do formula computation on already-lagged data.
    Ablation experiments change lag via config without regenerating plugins.
    """

    def compute_time_avail_m(
        self,
        df: pd.DataFrame,
        date_col: str = "datadate",
        lag_months: int = 6,
    ) -> pd.DataFrame:
        """Add time_avail_m column: earliest month the data is usable.

        Args:
            df: DataFrame with accounting data dates
            date_col: Column containing the fiscal period end date
            lag_months: Minimum months to wait (accounting lag)

        Returns:
            DataFrame with added 'time_avail_m' column (YYYYMM int format)
        """
        df = df.copy()
        dt = pd.to_datetime(df[date_col])
        total_months = dt.dt.year * 12 + (dt.dt.month - 1) + lag_months
        year, month = divmod(total_months, 12)
        df["time_avail_m"] = (year * 100 + month + 1).astype(int)
        return df

    def build_signal_master_table(
        self,
        crsp_df: pd.DataFrame,
        compustat_df: pd.DataFrame,
        ccm_linker: "CCMLinker",
        lag_months: int = 6,
        date_col: str = "datadate",
    ) -> pd.DataFrame:
        """Build merged panel keyed on [permno, time_avail_m].

        This is the intermediate table that signal plugins read from.
        Analogous to C&Z's SignalMasterTable.parquet. Requires ``ccm_linker``
        to already have its link table loaded via ``load_link_table()``.
        """
        merged = ccm_linker.merge(crsp_df, compustat_df, date_col=date_col)
        return self.compute_time_avail_m(merged, date_col=date_col, lag_months=lag_months)


class DataLayer:
    """Unified data access layer for all pipeline modules.

    Provides:
    - Data dictionary for field validation (Extractor, Review Gate)
    - Snapshot management for reproducible data (Engine)
    - CCM linking (Engine)
    - time_avail_m computation (separates lag from signal logic)
    """

    def __init__(self, data_path: str = "./data"):
        self.data_path = Path(data_path)
        self.dictionary = DataDictionary()
        self.snapshots = SnapshotManager(base_path=str(self.data_path / "snapshots"))
        self.ccm_linker = CCMLinker()
        self.time_avail = TimeAvailComputer()

    def load_dictionary(self, yaml_path: str) -> None:
        """Load data dictionary from YAML."""
        self.dictionary.load_from_yaml(yaml_path)

    def get_snapshot_data(self, snapshot_id: str, table: str) -> pd.DataFrame:
        """Load a table from a specific snapshot."""
        return self.snapshots.load_table(snapshot_id, table)

    def get_signal_master_table(
        self, snapshot_id: str, lag_months: int = 6
    ) -> pd.DataFrame:
        """Get the merged panel ready for signal computation.

        Returns DataFrame keyed on [permno, time_avail_m] with all
        Compustat and CRSP fields merged and lag-adjusted.
        """
        crsp = self.get_snapshot_data(snapshot_id, "crsp_msf")
        compustat = self.get_snapshot_data(snapshot_id, "compustat_funda")
        ccm_link = self.get_snapshot_data(snapshot_id, "ccm_link")
        self.ccm_linker.load_link_table(ccm_link)
        return self.time_avail.build_signal_master_table(
            crsp, compustat, self.ccm_linker, lag_months=lag_months
        )


# ---------------------------------------------------------------------------
# Panel assembly from raw WRDS-shaped source tables — DECLARATIVE.
#
# Real vendors ship a firm's data across SEPARATE tables (CRSP: msf returns /
# msenames attributes / msedelist delistings), but the BacktestExecutor wants one
# flat panel keyed [permno, yyyymm]. Rather than a bespoke per-source function,
# each source declares its ROLE in `SOURCE_SCHEMA` and one generic
# `assemble_panel()` interprets it — same declarative spirit as this module's
# DataDictionary/_CONCEPT_MAP and the engine's FilterOp DSL. Adding a source is
# a schema entry, not new imperative code.
#
# This is DETERMINISTIC controlled infrastructure (like C&Z's single
# SignalMasterTable.py shared by every signal), NOT an LLM-generated hook:
# per-AGENTS.md, empirical data construction is never LLM-decided. Paper-to-
# paper differences (which sources/fields, lag, imputation) belong in the
# reviewed MethodSpec, not here.
#
# Roles a source can play:
#   base       — the primary table; supplies `ret`, derives `yyyymm` from a
#                date column and any `derive`d columns (e.g. me = |prc|*shrout).
#   pit_attrs  — attributes joined by key with a point-in-time validity window
#                (namedt<=date<=nameendt), e.g. exchange/share/SIC codes.
#   fold_last  — a value folded onto each key's LAST panel month (CRSP delisting
#                return convention); consumed later by apply_delisting_returns.
# ---------------------------------------------------------------------------

# Named column-derivation ops referenced by a source's `derive` clause.
_DERIVE_OPS = {
    # market equity = |prc| * shrout  (CRSP prc is negative for a bid/ask midpoint)
    "abs_mul": lambda df, cols: df[cols[0]].abs() * df[cols[1]],
}

# Default schema for the standard CRSP monthly returns panel.
SOURCE_SCHEMA: dict[str, dict[str, Any]] = {
    "crsp_msf": {
        "role": "base",
        "date_col": "date",
        "derive": {"me": {"op": "abs_mul", "cols": ["prc", "shrout"]}},
        "keep": ["permno", "yyyymm", "ret", "me"],
    },
    "crsp_msenames": {
        "role": "pit_attrs",
        "on": "permno",
        "window": ["namedt", "nameendt"],
        "attrs": ["shrcd", "exchcd", "siccd"],
    },
    "crsp_msedelist": {
        "role": "fold_last",
        "on": "permno",
        "value": "dlret",
        "order": "yyyymm",
    },
}


def _load_base(d: Path, name: str, spec: dict) -> pd.DataFrame:
    df = pd.read_parquet(d / f"{name}.parquet")
    df["_date"] = pd.to_datetime(df[spec["date_col"]])
    df["yyyymm"] = df["_date"].dt.year * 100 + df["_date"].dt.month
    for new_col, rule in spec.get("derive", {}).items():
        df[new_col] = _DERIVE_OPS[rule["op"]](df, rule["cols"])
    return df


def _apply_pit_attrs(panel: pd.DataFrame, attrs: pd.DataFrame, spec: dict) -> pd.DataFrame:
    on, (lo, hi) = spec["on"], spec["window"]
    merged = panel.merge(attrs[[on, lo, hi, *spec["attrs"]]], on=on, how="left")
    dt = merged["_date"]
    in_window = (pd.to_datetime(merged[lo]) <= dt) & (dt <= pd.to_datetime(merged[hi]))
    # keep the attribute row valid at each date; rows with no matching window
    # (rare edge at a switch boundary) fall back to the first attribute row.
    merged = merged[in_window | merged[lo].isna()].copy()
    return merged.drop_duplicates(subset=[on, "yyyymm"], keep="first")


def _apply_fold_last(panel: pd.DataFrame, tbl: pd.DataFrame, spec: dict) -> pd.DataFrame:
    on, value, order = spec["on"], spec["value"], spec["order"]
    val_by_key = tbl.drop_duplicates(on).set_index(on)[value]
    last = panel.groupby(on)[order].transform("max")
    is_last = panel[order] == last
    # float NaN (not pd.NA) so the column stays float64 — an object-dtype column
    # breaks downstream float writes (e.g. steps.apply_delisting_returns) under
    # pandas 3.x strict setitem.
    panel[value] = float("nan")
    panel.loc[is_last, value] = panel.loc[is_last, on].map(val_by_key).astype(float)
    return panel


def assemble_panel(data_dir: str | Path, schema: dict[str, dict] | None = None) -> pd.DataFrame:
    """Assemble a flat [permno, yyyymm, ...] panel from raw source tables per a
    declarative `schema` (defaults to `SOURCE_SCHEMA`, the standard CRSP panel).

    Reads each source named in `schema` from `data_dir/<name>.parquet` and
    applies it according to its declared `role` (see module comment above).
    Optional sources whose file is absent are simply skipped. Returns the base
    `keep` columns plus each pit_attrs `attrs` and each present fold_last
    `value`.
    """
    schema = schema or SOURCE_SCHEMA
    d = Path(data_dir)

    base_name = next(n for n, s in schema.items() if s["role"] == "base")
    panel = _load_base(d, base_name, schema[base_name])
    keep = list(schema[base_name]["keep"])

    for name, spec in schema.items():
        if spec["role"] == "base":
            continue
        path = d / f"{name}.parquet"
        if not path.exists():
            continue
        tbl = pd.read_parquet(path)
        if spec["role"] == "pit_attrs":
            panel = _apply_pit_attrs(panel, tbl, spec)
            keep += spec["attrs"]
        elif spec["role"] == "fold_last":
            panel = _apply_fold_last(panel, tbl, spec)
            keep.append(spec["value"])

    out = panel[[c for c in keep if c in panel.columns]].copy()
    out["permno"] = out["permno"].astype(int)
    out["yyyymm"] = out["yyyymm"].astype(int)
    return out.reset_index(drop=True)


def build_crsp_monthly_panel(data_dir: str | Path) -> pd.DataFrame:
    """Assemble the standard CRSP monthly returns panel (thin wrapper over the
    declarative `assemble_panel` using `SOURCE_SCHEMA`). Kept as a named entry
    point for `BacktestExecutor._load_data` and tests."""
    return assemble_panel(data_dir, SOURCE_SCHEMA)


# ---------------------------------------------------------------------------
# SIGNAL-INPUT source registry — the maintained "link for join" (plan.md
# data-loader Phase 2). Each signal-input source declares, ONCE, how it links
# to permno and when its data becomes available — a PER-SOURCE property reused
# by every paper, not re-decided per paper. Adding a new data source = adding
# one entry to the declarative catalog (`src/infra/data_layer/catalog.py`), a
# human-reviewed one-time registration; ReviewGate blocks a spec whose mapping
# references a source absent from the catalog.
#
# `SIGNAL_SOURCES` / `LINK_TABLES` below are now DERIVED from that catalog (the
# single source of truth) and kept under their historical names so existing
# callers (`from src.infra.data_layer import SIGNAL_SOURCES`) are unchanged.
#
# Per-source join fields:
#   key   — the source's native identifier column.
#   link  — how to reach permno: None (already permno-keyed), or a key into
#           LINK_TABLES ("ccm"/"ibes_crsp_link"/"optionm_crsp_link").
#   date  — the source's observation-date column (drives point-in-time linking
#           and the availability month); None for already-monthly/permno data.
#   lag   — accounting-availability lag in months: an int, or the name of a
#           MethodSpec field to read it from (e.g. "accounting_lag_months").
# ---------------------------------------------------------------------------

SIGNAL_SOURCES: dict[str, dict[str, Any]] = catalog.signal_sources()

# Physical schema of each link table (how key -> permno with a validity window).
LINK_TABLES: dict[str, dict[str, str]] = catalog.LINK_TABLES


def link_to_permno(
    df: pd.DataFrame,
    source_name: str,
    link_tables: dict[str, pd.DataFrame],
    *,
    date_col: str | None = None,
) -> pd.DataFrame:
    """Resolve a signal-input source's native key to `permno` (plan.md
    data-loader Phase 2), point-in-time.

    Uses `SIGNAL_SOURCES[source_name]` + `LINK_TABLES` to attach a `permno`
    column: `link=None` sources already have one; otherwise the source's `key`
    is joined to the declared link table and filtered to the row valid at the
    source's observation date (`start <= date <= end`, open-ended `end`
    treated as valid through the present). Exactly one output row per input row
    (primary link wins on ties). Rows that resolve to no permno are dropped.
    """
    spec = SIGNAL_SOURCES[source_name]
    if spec.get("link") is None:
        return df

    key = spec["key"]
    ls = LINK_TABLES[spec["link"]]
    link_df = link_tables[spec["link"]][[ls["key"], ls["permno"], ls["start"], ls["end"]]].rename(
        columns={ls["key"]: key, ls["permno"]: "permno"}
    )

    work = df.reset_index(drop=True).copy()
    work["_row"] = range(len(work))
    merged = work.merge(link_df, on=key, how="left")

    dcol = date_col or spec.get("date")
    if dcol and dcol in merged.columns:
        dt = pd.to_datetime(merged[dcol], errors="coerce")
        start = pd.to_datetime(merged[ls["start"]], errors="coerce")
        end = pd.to_datetime(merged[ls["end"]], errors="coerce").fillna(pd.Timestamp.max)
        keep = (start <= dt) & (dt <= end)
        merged = merged[keep | merged["permno"].isna()]

    merged = merged.drop(columns=[ls["start"], ls["end"]])
    merged = merged.dropna(subset=["permno"])
    # one row per original source row (primary link wins on ties)
    merged = merged.sort_values("permno").drop_duplicates("_row", keep="first")
    merged["permno"] = merged["permno"].astype(int)
    return merged.drop(columns=["_row"]).reset_index(drop=True)


# File name of each link table on disk (LINK_TABLES key -> parquet stem).
_LINK_TABLE_FILES = catalog.LINK_TABLE_FILES


def _load_link_tables(d: Path) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for link, stem in _LINK_TABLE_FILES.items():
        p = d / f"{stem}.parquet"
        if p.exists():
            out[link] = pd.read_parquet(p)
    return out


def _resolve_lag(lag: Any, accounting_lag_months: int) -> int:
    """A source's `lag` is either an int (months) or a marker string
    ("accounting_lag_months") meaning "use the spec's accounting lag"."""
    if isinstance(lag, str):
        return int(accounting_lag_months or 0)
    return int(lag or 0)


def _load_source_frame(
    d: Path, source_name: str, cols: list[str], accounting_lag_months: int, link_tables: dict
) -> pd.DataFrame | None:
    """Load one signal-input source, resolved to [permno, time_avail_m, *cols].

    Reads ONLY the needed columns (+ key + date), links to permno, and computes
    the availability month `time_avail_m` = observation month + the source's
    lag. CRSP fields come from the assembled monthly panel (time_avail_m =
    yyyymm)."""
    if source_name not in SIGNAL_SOURCES:
        raise ValueError(
            f"Unknown signal source {source_name!r}: not in SIGNAL_SOURCES. "
            "Register the source once (key/link/date/lag) before use."
        )
    src = SIGNAL_SOURCES[source_name]

    if source_name == "crsp_msf":
        panel = build_crsp_monthly_panel(d)
        keep = ["permno", "yyyymm", *[c for c in cols if c in panel.columns]]
        return panel[keep].rename(columns={"yyyymm": "time_avail_m"})

    path = d / f"{source_name}.parquet"
    if not path.exists():
        return None
    key, date_col = src["key"], src.get("date")
    read_cols = [c for c in {key, *( [date_col] if date_col else [] ), *cols} if c]
    df = pd.read_parquet(path, columns=read_cols)
    df = link_to_permno(df, source_name, link_tables)

    lag = _resolve_lag(src["lag"], accounting_lag_months)
    if date_col and date_col in df.columns:
        dt = pd.to_datetime(df[date_col], errors="coerce")
        total = dt.dt.year * 12 + (dt.dt.month - 1) + lag
        df["time_avail_m"] = (total // 12) * 100 + (total % 12) + 1
    else:
        # no observation-date column -> can't compute availability (e.g. the
        # year-based patents source); documented v1 gap.
        df["time_avail_m"] = pd.NA

    out = df[["permno", "time_avail_m", *cols]].dropna(subset=["time_avail_m"])
    out["time_avail_m"] = out["time_avail_m"].astype(int)
    return out


def signal_input_sources(spec: Any) -> dict[str, list[str]]:
    """Group the SIGNAL-FORMULA fields by physical source: {source: [columns]}.

    Only `spec.signal.required_fields` (falling back to `spec.data.required_fields`)
    are included — universe/weighting CRSP fields stay engine-side. Shared by
    `assemble_signal_master_table` and codegen (which bakes this map into the
    generated standalone script so it needs no MethodSpec at run time)."""
    formula_concepts = set(spec.signal.required_fields) or {f.field for f in spec.data.required_fields}
    out: dict[str, list[str]] = {}
    for source, pairs in spec.resolved_sources().items():
        cols = [col for concept, col in pairs if concept in formula_concepts]
        if cols:
            out[source] = cols
    return out


def assemble_signal_master_table_from_sources(
    data_dir: str | Path,
    by_source: dict[str, list[str]],
    accounting_lag_months: int = 6,
) -> pd.DataFrame:
    """Spec-free core of `assemble_signal_master_table`: build the
    [permno, time_avail_m, ...] table from an explicit {source: [columns]} map.

    Used directly by the generated standalone backtest script (which has no
    MethodSpec object at run time, only baked constants). See
    `assemble_signal_master_table` for the MethodSpec-driven wrapper and the
    v1 as-of-join limitation."""
    d = Path(data_dir)
    link_tables = _load_link_tables(d)
    frames = [
        f for name, cols in by_source.items()
        if (f := _load_source_frame(d, name, cols, accounting_lag_months, link_tables)) is not None
    ]
    if not frames:
        return pd.DataFrame(columns=["permno", "time_avail_m"])

    master = frames[0]
    for f in frames[1:]:
        master = master.merge(f, on=["permno", "time_avail_m"], how="outer")
    return master.sort_values(["permno", "time_avail_m"]).reset_index(drop=True)


def assemble_signal_master_table(spec: Any, data_dir: str | Path) -> pd.DataFrame:
    """Assemble the signal-formula input table keyed [permno, time_avail_m]
    from however many sources the spec's fields span (plan.md data-loader
    Phase 3) — replacing the binary crsp_only/compustat heuristic.

    Only the SIGNAL-FORMULA fields (`spec.signal.required_fields`, falling back
    to `spec.data.required_fields`) are pulled — universe/weighting CRSP fields
    stay engine-side. Each field is resolved to its (source, physical column)
    via `spec.resolved_sources()`; each source is read for ONLY its needed
    columns, linked to permno, given an availability month, and merged on
    [permno, time_avail_m].

    v1 limitation: cross-source alignment is an exact [permno, time_avail_m]
    outer merge, not an as-of join — fine for single-source signals (the common
    case) and same-frequency multi-source; mixing annual+monthly sources in one
    formula would need an as-of join (future).
    """
    return assemble_signal_master_table_from_sources(
        data_dir, signal_input_sources(spec), spec.accounting_lag_months or 6
    )




