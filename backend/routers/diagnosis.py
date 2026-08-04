"""Step8 session endpoint: opt-in, LLM-assisted (never LLM-controlled)
explanation layer over an already-recorded `comparison.json` bundle. Must
NEVER be triggered automatically by any other step, and its outcome must
never change the success/failure status of steps 1-7 (docs/decision-log.md
2026-08-04 review, point 6/AGENTS.md hard constraints).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.sessions import append_event, complete_attempt_with_retry, session_store
from backend.state import build_llm_client
from src.infra.models.session import ConcurrentModificationError, StepStatus
from src.infra.session_store import SessionNotFoundError
from src.steps.step8_diagnosis import ReplicationDiagnoser
from src.steps.step8_diagnosis.render import write_diagnosis

router = APIRouter(prefix="/api/sessions", tags=["diagnosis"])


class DiagnosisRequest(BaseModel):
    expected_revision: int
    llm_provider: str = "codex"
    llm_model: str | None = None


@router.post("/{session_id}/steps/8/diagnosis")
async def run_step8_diagnosis(session_id: str, req: DiagnosisRequest) -> dict:
    try:
        manifest = session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"No session '{session_id}'")

    step7 = manifest.steps.get(7)
    latest7 = step7.latest if step7 else None
    comparison_ref = latest7.output_refs.get("comparison_ref") if latest7 else None
    if not comparison_ref or not Path(comparison_ref).is_file():
        raise HTTPException(
            status_code=400,
            detail="step7 has not recorded a comparison_ref for this session yet",
        )

    try:
        session_store.start_attempt(session_id, req.expected_revision, step=8)
    except ConcurrentModificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    def run(log):
        bundle = json.loads(Path(comparison_ref).read_text())
        log(f"Building {req.llm_provider} LLM client...")
        client = build_llm_client(req.llm_provider, req.llm_model)
        diagnoser = ReplicationDiagnoser(llm_client=client, model=req.llm_model)
        log("Running step8 diagnosis (opt-in, read-only over the deterministic bundle)...")
        try:
            report = diagnoser.diagnose(bundle)
        except Exception as exc:
            complete_attempt_with_retry(session_id, step=8, status=StepStatus.FAILED, error=str(exc))
            append_event(session_id, step=8, stage="diagnosis", event="failed", detail=str(exc), level="error")
            raise

        results_dir = Path(comparison_ref).parent
        json_path, md_path = write_diagnosis(report, bundle, results_dir)
        complete_attempt_with_retry(
            session_id, step=8, status=StepStatus.SUCCESS,
            output_refs={"diagnosis_ref": str(json_path)},
        )
        append_event(
            session_id, step=8, stage="diagnosis", event="diagnosed",
            detail=f"accepted={len(report.claims)} rejected={len(report.rejected_claims)}",
        )
        return {"report": to_jsonable(report), "diagnosis_json_path": str(json_path), "diagnosis_md_path": str(md_path)}

    job_id = job_manager.create_job(run, session_id=session_id, step=8, stage="diagnosis")
    return {"job_id": job_id}
