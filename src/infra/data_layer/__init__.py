"""Data Layer - CRSP/Compustat/CCM data access, snapshots, and data dictionary."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd


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


# Concept-to-column: paper field names / source descriptions → physical column names.
# Keys are lower-cased for matching.
_CONCEPT_MAP: dict[str, str] = {
    "total_assets": "at", "at": "at", "compustat data item 6": "at",
    "data6": "at", "data item 6": "at",
    "monthly_return": "ret", "ret": "ret", "monthly stock return": "ret",
    "monthly return": "ret", "stock return": "ret",
    "market_equity": "me", "me": "me", "market_equity_june": "me",
    "market value": "me", "market capitalization": "me",
    "market value of equity": "me", "market cap": "me",
    "listing_exchange": "exchcd", "exchcd": "exchcd",
    "exchange": "exchcd", "exchange code": "exchcd",
    "sic_code": "siccd", "siccd": "siccd", "sic": "siccd",
    "four-digit sic": "siccd", "industry code": "siccd",
    "shrcd": "shrcd", "share code": "shrcd", "share_code": "shrcd",
    "shrout": "shrout", "shares outstanding": "shrout",
    "prc": "prc", "price": "prc", "closing price": "prc",
    "book_equity": "ceq", "ceq": "ceq", "common equity": "ceq",
    "sales": "sale", "sale": "sale", "revenue": "sale",
    "net_income": "ib", "ib": "ib", "income before extraordinary": "ib",
    "long_term_debt": "dltt", "dltt": "dltt", "long term debt": "dltt",
    "current_assets": "act", "act": "act",
    "current_liabilities": "lct", "lct": "lct",
    "depreciation": "dp", "dp": "dp",
    "capital_expenditure": "capx", "capx": "capx",
}


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

    def normalize_fields(self, required_fields: list) -> dict[str, str]:
        """Map paper-concept field names to physical parquet column names.

        Tries three passes in order:
          1. Exact match on field name (lower-cased)
          2. Substring match on source_detail string
          3. Substring match on concept string

        Returns {paper_field_name: physical_column_name} for resolved fields.
        Unresolved fields are omitted.
        """
        mapping: dict[str, str] = {}
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
                _CONCEPT_MAP.get(field.lower())
                or _CONCEPT_MAP.get(source)
                or next((v for k, v in _CONCEPT_MAP.items() if len(k) >= 4 and k in source), None)
                or next((v for k, v in _CONCEPT_MAP.items() if len(k) >= 4 and k in concept), None)
            )
            if col:
                mapping[field] = col
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
