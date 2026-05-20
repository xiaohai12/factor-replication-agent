"""Evidence Store + Run Registry - Persist and query experiment results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.models.run_record import RunRecord


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

    def save_run(self, run: RunRecord) -> None:
        """Save a run record and its artifacts."""
        run_dir = self.base_path / run.factor_id / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        with open(run_dir / "metadata.json", "w") as f:
            json.dump(run.model_dump(mode="json"), f, indent=2, default=str)

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

    def update_status(self, run_id: str, status: str) -> None:
        """Update run status."""
        if run_id in self._runs:
            self._runs[run_id].status = status

    def get_by_factor(self, factor_id: str) -> list[RunRecord]:
        """Get all runs for a factor."""
        return [r for r in self._runs.values() if r.factor_id == factor_id]

    def get_pending(self) -> list[RunRecord]:
        """Get all pending runs."""
        return [r for r in self._runs.values() if r.status == "pending"]

    def get_summary(self) -> dict[str, int]:
        """Get status summary across all runs."""
        summary: dict[str, int] = {}
        for r in self._runs.values():
            summary[r.status] = summary.get(r.status, 0) + 1
        return summary
