"""Step6 session endpoint: multi-track/OAT experiment orchestration
(`DualTrackController.run_experiment`), tagged onto a session as a job
(subprocess-heavy, one execution per track).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.sessions import append_event, complete_attempt_with_retry, session_store
from backend.spec_parsing import parse_spec, spec_factor_id
from backend.state import pipeline
from src.evaluation import diagnostics as step_diagnostics
from src.infra.models.plugin import PluginRecord
from src.infra.models.session import ConcurrentModificationError, StepStatus
from src.infra.session_store import SessionNotFoundError
from src.steps.step6_dual_track_controller import ExperimentPlan

router = APIRouter(prefix="/api/sessions", tags=["experiments"])


class ExperimentRequest(BaseModel):
    expected_revision: int
    spec: dict
    plugin: dict
    snapshot_id: str
    run_original: bool = True
    run_standardized: bool = True
    ablation_switches: list[str] = []
    factorial_switches: list[str] = []


@router.post("/{session_id}/steps/6/experiment")
async def run_step6_experiment(session_id: str, req: ExperimentRequest) -> dict:
    try:
        session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"No session '{session_id}'")

    def run(log):
        spec = parse_spec(req.spec)
        plugin = PluginRecord.model_validate(req.plugin)
        plan = ExperimentPlan(
            factor_id=spec_factor_id(spec),
            run_original=req.run_original,
            run_standardized=req.run_standardized,
            ablation_switches=req.ablation_switches,
            factorial_switches=req.factorial_switches,
        )
        log(f"Running experiment batch for '{spec_factor_id(spec)}' ({req.snapshot_id})...")
        try:
            runs = pipeline.controller.run_experiment(plugin, spec, plan, req.snapshot_id)
        except Exception as exc:
            complete_attempt_with_retry(session_id, step=6, status=StepStatus.FAILED, error=str(exc))
            append_event(session_id, step=6, stage="experiment", event="failed", detail=str(exc), level="error")
            raise

        for run in runs:
            pipeline.evidence_store.save_run(run)
            pipeline.run_registry.register(run)

        batch_id = runs[0].experiment_batch_id if runs else ""
        batch_invalidated = any(r.batch_invalidated for r in runs)
        log(
            f"Batch '{batch_id}' finished: {len(runs)} track(s), "
            f"batch_invalidated={batch_invalidated}."
        )
        complete_attempt_with_retry(
            session_id,
            step=6,
            status=StepStatus.SUCCESS,
            output_refs={
                "experiment_batch_id": batch_id,
                "execution_ids": json.dumps([r.run_id for r in runs]),
            },
            diagnostics=step_diagnostics.step6_diagnostics(runs),
        )
        append_event(
            session_id, step=6, stage="experiment", event="batch_complete",
            detail=f"batch_id={batch_id} tracks={len(runs)}",
            level="warning" if batch_invalidated else "info",
        )
        return {
            "runs": [to_jsonable(r) for r in runs],
            "experiment_batch_id": batch_id,
            "batch_invalidated": batch_invalidated,
        }

    job_id = job_manager.create_job(run, session_id=session_id, step=6, stage="experiment")
    try:
        session_store.start_attempt(session_id, req.expected_revision, step=6, job_id=job_id)
    except ConcurrentModificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"job_id": job_id}
