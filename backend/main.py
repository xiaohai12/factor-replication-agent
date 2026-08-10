"""FastAPI app entry point.

Run with:  .venv/bin/python3 -m uvicorn backend.main:app --reload --port 8000

CORS is enabled for the Vite dev server (http://localhost:5173) only --
this is a local-only, single-user development tool with no auth, so CORS is
scoped as narrowly as possible rather than left wide open.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import (
    backtest,
    catalog,
    codegen,
    diagnosis,
    evidence,
    experiments,
    jobs,
    methodspecs,
    papers,
    replication,
    sessions,
)
from backend.sessions import session_store
from backend.state import pipeline


def _sync_run_registry_from_evidence() -> None:
    """`RunRegistry` is in-memory only; repopulate it from the persistent
    `EvidenceStore` on disk (runs/evidence/{factor_id}/{run_id}/metadata.json)
    every time the backend process starts, so past runs still show up in the
    Trace & Logs page after a restart."""
    base_path = pipeline.evidence_store.base_path
    if not base_path.is_dir():
        return
    for factor_dir in base_path.iterdir():
        if not factor_dir.is_dir():
            continue
        for run_dir in factor_dir.iterdir():
            if not (run_dir / "metadata.json").exists():
                continue
            run = pipeline.evidence_store.load_run(factor_dir.name, run_dir.name)
            if run is not None:
                pipeline.run_registry.register(run)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _sync_run_registry_from_evidence()
    # A `Session`'s per-step attempt left `running` means the backend died
    # mid-step (the in-memory JobManager can't know it was restarted --
    # see backend/jobs.py). Reconcile on every startup, never leave a
    # session claiming a step is still in progress after a restart.
    session_store.reconcile_orphaned_running()
    yield


app = FastAPI(title="Factor Replication Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(methodspecs.router)
app.include_router(catalog.router)
app.include_router(codegen.router)
app.include_router(backtest.router)
app.include_router(evidence.router)
app.include_router(jobs.router)
app.include_router(sessions.router)
app.include_router(experiments.router)
app.include_router(replication.router)
app.include_router(diagnosis.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
