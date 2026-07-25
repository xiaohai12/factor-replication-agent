"""Run registry + evidence browser: read-only views over
`pipeline.run_registry` (in-memory, repopulated at startup from
`pipeline.evidence_store`'s on-disk `runs/evidence/` tree -- see
`backend.main`'s startup hook) and the evidence files themselves.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.serialization import to_jsonable
from backend.state import pipeline

router = APIRouter(prefix="/api", tags=["evidence"])


@router.get("/runs")
def list_runs() -> dict:
    return {
        "summary": pipeline.run_registry.get_summary(),
        "runs": [to_jsonable(r) for r in pipeline.run_registry.list_all()],
    }


@router.get("/runs/{factor_id}")
def get_runs_for_factor(factor_id: str) -> list[dict]:
    return [to_jsonable(r) for r in pipeline.run_registry.get_by_factor(factor_id)]


def _run_dir(factor_id: str, run_id: str) -> Path:
    return pipeline.evidence_store.base_path / factor_id / run_id


@router.get("/evidence/{factor_id}/{run_id}")
def browse_evidence(factor_id: str, run_id: str) -> dict:
    run_dir = _run_dir(factor_id, run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No evidence directory for {factor_id}/{run_id}")
    files = sorted(p.name for p in run_dir.iterdir() if p.is_file())
    return {"factor_id": factor_id, "run_id": run_id, "files": files}


@router.get("/evidence/{factor_id}/{run_id}/download/{filename}")
def download_evidence_file(factor_id: str, run_id: str, filename: str) -> FileResponse:
    run_dir = _run_dir(factor_id, run_id).resolve()
    file_path = (run_dir / filename).resolve()
    # Reject path traversal (e.g. "../../etc/passwd") -- the resolved file
    # must stay inside this run's own evidence directory.
    if not file_path.is_relative_to(run_dir) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
