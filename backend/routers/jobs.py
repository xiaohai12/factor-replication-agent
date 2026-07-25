"""Generic job status/SSE-stream endpoints, shared by every long-running
operation submitted via `backend.jobs.job_manager` (extraction, LLM review,
codegen, backtest execution).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.jobs import job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    snapshot = job_manager.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No job '{job_id}'")
    return snapshot


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job '{job_id}'")

    async def event_source():
        # Replay history first so a client that connects late still sees
        # earlier log lines, then keep streaming new events.
        for message in list(job.log_history):
            yield f"event: log\ndata: {json.dumps(message)}\n\n"
        if job.status in ("completed", "failed"):
            event_type = job.status
            data = job.result if job.status == "completed" else job.error
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            return
        while True:
            event = await job.queue.get()
            yield f"event: {event.type}\ndata: {json.dumps(event.data)}\n\n"
            if event.type in ("completed", "failed"):
                break

    return StreamingResponse(event_source(), media_type="text/event-stream")
