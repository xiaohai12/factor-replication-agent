"""Artifact hashing utilities (docs/multi-config-evidence-plan.md Phase A1.3):
two DIFFERENT hash kinds, deliberately not conflated.

- `artifact_sha256`: raw file-byte integrity. Two files with this hash equal
  are byte-identical. Sensitive to writer version, compression, metadata,
  and row-group layout -- NOT suitable for asserting "the same data" across
  two independently-written files.
- `series_semantic_hash`: canonicalized CONTENT equality for a firm-month (or
  similar) panel. Column selection, dtype, missing-value representation, row
  order, and float representation are all normalized first, so two files
  with identical logical content hash equal even if written by different
  pandas/pyarrow versions or with different compression.

Per docs/multi-config-evidence-plan.md Decision 2: a "controlled" post-signal
identification level requires asserting the realized signal series is
UNCHANGED across two runs -- that assertion must use `series_semantic_hash`,
never `artifact_sha256` (which would spuriously fail on harmless
writer/compression differences and give false "signal changed" alarms).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def artifact_sha256(path: str | Path) -> str:
    """sha256 of a file's raw bytes -- integrity only, not content equality."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def series_semantic_hash(
    df: pd.DataFrame,
    key_cols: list[str],
    value_cols: list[str],
    float_decimals: int = 10,
) -> str:
    """Canonicalized content hash of a firm-month-like panel.

    Normalization steps (see module docstring): select exactly `key_cols +
    value_cols` (drop everything else -- an extra incidental column must not
    change the hash); sort by `key_cols` (row order is not meaningful);
    reject duplicate keys (an ambiguous/malformed panel must fail loudly, not
    hash silently); round float columns to `float_decimals` (writer/platform
    float repr noise must not change the hash); represent missing values
    with a single canonical sentinel string (NaN reads back inconsistently
    across parquet engines/dtypes).

    Raises ValueError on a duplicate key combination -- callers comparing two
    "controlled" runs need to know their signal series is well-formed, not
    silently hash whichever duplicate row happened to sort first.
    """
    cols = list(key_cols) + list(value_cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"series_semantic_hash: missing expected column(s) {missing}")

    working = df[cols].copy()

    dup_mask = working.duplicated(subset=key_cols, keep=False)
    if dup_mask.any():
        dup_keys = working.loc[dup_mask, key_cols].drop_duplicates()
        raise ValueError(
            f"series_semantic_hash: duplicate key(s) in {key_cols}, e.g. "
            f"{dup_keys.iloc[0].to_dict()} -- refusing to hash an ambiguous panel"
        )

    working = working.sort_values(by=key_cols).reset_index(drop=True)

    for col in value_cols:
        if pd.api.types.is_float_dtype(working[col]):
            working[col] = working[col].round(float_decimals)

    # Canonical missing-value sentinel: NaN's string repr differs across
    # pandas versions/dtypes (float NaN vs pd.NA vs None), so normalize before
    # hashing rather than relying on to_csv's own NaN formatting.
    working = working.astype(object).where(working.notna(), "__NULL__")

    canonical = working.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_manifest_hash(storage_path: str | Path) -> str | None:
    """Best-effort, coarse-grained `RunRecord.data_snapshot_hash`.

    APPROXIMATION, not the full design (docs/multi-config-evidence-plan.md
    A1.4 wants a manifest of the files a run ACTUALLY consumed, e.g. via
    `signal_input_sources(spec)` mapped through the data catalog's registered
    filenames, each with its own content hash). Computing that precisely
    requires per-source file-path resolution this function deliberately
    doesn't attempt yet. Instead, this hashes `(relative_path, size_bytes)`
    for every regular file directly under `storage_path` and
    `storage_path/local` (one level of raw-CSV convention, non-recursive) --
    cheap (no full-file content hashing of potentially multi-GB WRDS CSVs)
    and still changes whenever a file in the snapshot is added, removed, or
    resized. Two real limitations to keep in mind: (1) a file edited
    in-place without changing its size would NOT change this hash; (2) it
    includes every file present, not just the ones this specific run
    actually read. Returns None if `storage_path` doesn't exist.
    """
    root = Path(storage_path)
    if not root.exists():
        return None

    entries: dict[str, int] = {}
    for base in (root, root / "local"):
        if not base.is_dir():
            continue
        for f in sorted(base.iterdir()):
            if f.is_file():
                entries[str(f.relative_to(root))] = f.stat().st_size

    canonical = json.dumps(entries, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
