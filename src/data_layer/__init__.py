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
        """List available field names, optionally filtered by dataset/table."""
        entries = self._entries.values()
        if dataset:
            entries = [e for e in entries if e.dataset == dataset]
        if table:
            entries = [e for e in entries if e.table == table]
        return [e.field for e in entries]

    def load_from_yaml(self, path: str) -> None:
        """Load field definitions from a YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        for item in data:
            self.register(FieldEntry(**item))


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

    Rules (per architecture.md Section 3.2):
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

        Returns merged DataFrame with both permno and gvkey columns.
        """
        if self._link_table is None:
            raise RuntimeError("Link table not loaded. Call load_link_table first.")
        # TODO: Implement point-in-time merge with linkdt/linkenddt range matching
        raise NotImplementedError

    def check_coverage(self, merged_df: pd.DataFrame) -> dict[str, Any]:
        """Check merge coverage and report potential issues."""
        # TODO: Compute coverage stats and flag anomalies
        raise NotImplementedError


# --- Main Data Layer Facade ---


class DataLayer:
    """Unified data access layer for all pipeline modules.

    Provides:
    - Data dictionary for field validation (Extractor, Review Gate)
    - Snapshot management for reproducible data (Engine)
    - CCM linking (Engine)
    """

    def __init__(self, data_path: str = "./data"):
        self.data_path = Path(data_path)
        self.dictionary = DataDictionary()
        self.snapshots = SnapshotManager(base_path=str(self.data_path / "snapshots"))
        self.ccm_linker = CCMLinker()

    def load_dictionary(self, yaml_path: str) -> None:
        """Load data dictionary from YAML."""
        self.dictionary.load_from_yaml(yaml_path)

    def get_snapshot_data(self, snapshot_id: str, table: str) -> pd.DataFrame:
        """Load a table from a specific snapshot."""
        return self.snapshots.load_table(snapshot_id, table)
