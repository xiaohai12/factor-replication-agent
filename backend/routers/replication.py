"""Step7 session endpoint: replication-gap comparison.

Deliberately does NOT rebuild `comparison.json`'s evidence bundle --
`BacktestRunner.write_comparison_summary()` (called automatically at the end
of `DualTrackController.run_experiment`/`run_from_matrix`) already calls
`build_evidence_bundle()` once; this endpoint only VALIDATES that a
requested `experiment_batch_id` (or `execution_id`s) resolves to a
consistent, non-invalidated batch whose on-disk `comparison.json` still
matches it, then registers a reference to that file on the session. It never
accepts client-supplied runs/config/metrics (docs/decision-log.md 2026-08-04
review, point 5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.sessions import append_event, session_store
from backend.state import pipeline
from src.evaluation import diagnostics as step_diagnostics
from src.infra.models.session import ConcurrentModificationError, StepStatus
from src.infra.session_store import SessionNotFoundError

router = APIRouter(prefix="/api/sessions", tags=["replication"])


def _get_or_404(session_id: str):
    try:
        return session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"No session '{session_id}'")


class ComparisonRequest(BaseModel):
    expected_revision: int
    experiment_batch_id: Optional[str] = None
    execution_ids: list[str] = []


@router.post("/{session_id}/steps/7/comparison")
def build_step7_comparison(session_id: str, req: ComparisonRequest) -> dict:
    _get_or_404(session_id)
    if not req.experiment_batch_id and not req.execution_ids:
        raise HTTPException(status_code=400, detail="must supply experiment_batch_id or execution_ids")

    records = []
    if req.execution_ids:
        for run_id in req.execution_ids:
            record = pipeline.run_registry.get_by_id(run_id)
            if record is None:
                raise HTTPException(status_code=400, detail=f"unknown execution_id '{run_id}'")
            records.append(record)
        batch_ids = {r.experiment_batch_id for r in records}
        if len(batch_ids) != 1:
            raise HTTPException(status_code=400, detail="execution_ids span more than one experiment_batch_id")
        resolved_batch_id = batch_ids.pop()
        if req.experiment_batch_id and req.experiment_batch_id != resolved_batch_id:
            raise HTTPException(status_code=400, detail="experiment_batch_id does not match execution_ids' batch")
        batch_id = resolved_batch_id
    else:
        batch_id = req.experiment_batch_id
        records = [r for r in pipeline.run_registry.list_all() if r.experiment_batch_id == batch_id]
        if not records:
            raise HTTPException(status_code=404, detail=f"no runs found for experiment_batch_id '{batch_id}'")

    factor_ids = {r.factor_id for r in records}
    if len(factor_ids) != 1:
        raise HTTPException(status_code=400, detail="batch spans more than one factor_id")
    factor_id = factor_ids.pop()

    if any(r.batch_invalidated for r in records):
        raise HTTPException(
            status_code=409,
            detail=f"experiment_batch_id '{batch_id}' is invalidated: {records[0].batch_invalidation_reason}",
        )

    comparison_path = pipeline.scripts_path / "results" / factor_id / "comparison.json"
    if not comparison_path.is_file():
        raise HTTPException(status_code=404, detail=f"no comparison.json for factor '{factor_id}'")
    bundle = json.loads(comparison_path.read_text())
    on_disk_batch_id = (bundle.get("batch") or {}).get("experiment_batch_id")
    if on_disk_batch_id != batch_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"comparison.json on disk belongs to batch '{on_disk_batch_id}', not the "
                f"requested '{batch_id}' -- comparison.json is overwritten per factor (not "
                "versioned per-batch), so a newer batch run has replaced it. Re-run step6 "
                "for this batch to regenerate a matching comparison.json before retrying."
            ),
        )

    try:
        session_store.start_attempt(session_id, req.expected_revision, step=7)
    except ConcurrentModificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    manifest = session_store.get(session_id)
    manifest = session_store.complete_attempt(
        session_id,
        manifest.revision,
        step=7,
        status=StepStatus.SUCCESS,
        output_refs={"comparison_ref": str(comparison_path)},
        diagnostics=step_diagnostics.step7_diagnostics(bundle),
    )
    append_event(session_id, step=7, stage="replication_diff", event="comparison_recorded", detail=batch_id)
    return {"bundle": bundle, "revision": manifest.revision}


@router.get("/{session_id}/steps/7/comparison")
def get_step7_comparison(session_id: str) -> dict:
    manifest = _get_or_404(session_id)
    record = manifest.steps.get(7)
    latest = record.latest if record else None
    comparison_ref = latest.output_refs.get("comparison_ref") if latest else None
    if not comparison_ref:
        raise HTTPException(status_code=404, detail="No comparison recorded yet for this session")
    path = Path(comparison_ref)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Recorded comparison_ref no longer exists on disk")
    return json.loads(path.read_text())
