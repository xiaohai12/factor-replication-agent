"""Evidence Store + Run Registry - Persist and query experiment results."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from src.infra.hashing import artifact_sha256
from src.infra.models.run_record import RunRecord


class EvidenceStore:
    """Persists all experiment artifacts for auditability.

    Stores:
    - Run configs and hashes
    - Return series
    - Signal series
    - Logs
    - Metrics
    """

    def __init__(self, base_path: str = "./evidence"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_run(
        self,
        run: RunRecord,
        artifacts: dict[str, str] | None = None,
        inline_content: dict[str, str] | None = None,
    ) -> None:
        """Save a run record and (optionally) its file artifacts.

        `artifacts`, when given, is `{filename: source_path}` for whatever
        else the caller wants persisted alongside the metadata (e.g.
        `{"script.py": ...}` -- a file that already exists on disk); missing
        source files are silently skipped (a failed run may not have every
        artifact). `inline_content` is `{filename: text}` for content the
        caller only has in memory (e.g. the plugin code string, or a
        `json.dumps(...)` of the resolved config/MethodSpec) -- written
        directly, no source file needed. The run's own
        `return_series_path`/`signal_series_path` -- already written to a
        transient `scripts_path` by `BacktestRunner` -- are copied in too
        when the files still exist, and the persisted `RunRecord`'s path
        fields are rewritten to point at these evidence-root-local copies
        (plus their `artifact_sha256`, appended into `run.logs` as a plain
        audit line) so a `load_run()` later doesn't depend on that transient
        directory still existing.

        Written atomically: everything is staged in a sibling `.staging`
        directory first, then the whole directory is swapped into place with
        one `rename()` -- a crash or exception mid-copy never leaves a
        `metadata.json` claiming artifacts exist that don't (docs/
        multi-config-evidence-plan.md Phase A1.6).
        """
        run_dir = self.base_path / run.factor_id / run.run_id
        staging_dir = run_dir.parent / f"{run_dir.name}.staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)

        run = run.model_copy(deep=True)
        artifact_hashes: dict[str, str] = {}

        for filename, source_path in (artifacts or {}).items():
            src = Path(source_path)
            if not src.exists():
                continue
            dest = staging_dir / filename
            shutil.copy2(src, dest)
            artifact_hashes[filename] = artifact_sha256(dest)

        for filename, content in (inline_content or {}).items():
            dest = staging_dir / filename
            dest.write_text(content)
            artifact_hashes[filename] = artifact_sha256(dest)

        for attr, filename in (
            ("return_series_path", "return_series.csv"),
            ("signal_series_path", "signal_series.parquet"),
        ):
            src_path = getattr(run, attr)
            if not src_path or not Path(src_path).exists():
                continue
            dest = staging_dir / filename
            shutil.copy2(src_path, dest)
            artifact_hashes[filename] = artifact_sha256(dest)
            setattr(run, attr, str(run_dir / filename))

        if artifact_hashes:
            run.logs = list(run.logs) + [
                f"artifact_sha256: {json.dumps(artifact_hashes, sort_keys=True)}"
            ]

        with open(staging_dir / "metadata.json", "w") as f:
            json.dump(run.model_dump(mode="json"), f, indent=2, default=str)

        if run_dir.exists():
            shutil.rmtree(run_dir)
        staging_dir.rename(run_dir)

    def load_run(self, factor_id: str, run_id: str) -> Optional[RunRecord]:
        """Load a run record by IDs."""
        meta_path = self.base_path / factor_id / run_id / "metadata.json"
        if not meta_path.exists():
            return None
        with open(meta_path) as f:
            data = json.load(f)
        return RunRecord(**data)


class RunRegistry:
    """Tracks status of all factor × variant experiments."""

    def __init__(self):
        self._runs: dict[str, RunRecord] = {}

    def register(self, run: RunRecord) -> None:
        """Register a new run."""
        self._runs[run.run_id] = run

    def get_by_id(self, run_id: str) -> Optional[RunRecord]:
        """Look up one run by its `run_id`. Used by the session control
        plane's step7 endpoint to resolve caller-supplied `execution_id`s
        against the in-memory registry WITHOUT trusting any run/config/
        metrics payload the caller might otherwise try to supply directly
        (see docs/decision-log.md 2026-08-04 review, point 5)."""
        return self._runs.get(run_id)

    def update_status(self, run_id: str, status: str) -> None:
        """Update run status."""
        if run_id in self._runs:
            self._runs[run_id].status = status

    def get_by_factor(self, factor_id: str) -> list[RunRecord]:
        """Get all runs for a factor."""
        return [r for r in self._runs.values() if r.factor_id == factor_id]

    def list_all(self) -> list[RunRecord]:
        """Get every registered run (e.g. for a run-registry table UI)."""
        return list(self._runs.values())

    def get_pending(self) -> list[RunRecord]:
        """Get all pending runs."""
        return [r for r in self._runs.values() if r.status == "pending"]

    def get_summary(self) -> dict[str, int]:
        """Get status summary across all runs."""
        summary: dict[str, int] = {}
        for r in self._runs.values():
            summary[r.status] = summary.get(r.status, 0) + 1
        return summary
