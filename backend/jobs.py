"""Generic background-job manager with SSE-friendly progress events.

Every long-running operation (LLM extraction/review/codegen, backtest
subprocess execution) is submitted as a job: the route handler builds a
small closure `fn(log) -> result` (where `log(message)` reports progress),
`JobManager.create_job(fn)` runs it in a thread (so the asyncio event loop
stays responsive) and returns a `job_id` immediately. Clients can either:
  - GET /api/jobs/{job_id}/stream  -- SSE stream of lifecycle/log events
  - GET /api/jobs/{job_id}         -- snapshot status/result (polling fallback)

This intentionally does NOT hook into `PipelineTracer` (src/infra/trace.py):
that class is in-memory/read-after-fact only with no subscribe API, so
wiring it in would require making it thread-safe/observable for no real
benefit here -- route handlers already know which stage they're running and
can call `log()` directly at the right points.

A job MAY be tagged with `session_id`/`step`/`stage` (Phase 1 of the
session-centric UI redesign): when present, every `log()` call is ALSO
appended to that session's persisted event journal
(`backend.sessions.append_event`) -- existing call sites that only pass
`log` to `create_job` are unaffected; this is purely additive. Jobs are
in-memory ONLY and never survive a backend restart -- `SessionStore.
reconcile_orphaned_running()` (called from `backend.main`'s startup) is the
authoritative place a stuck `running` step gets resolved, not this module.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.serialization import to_jsonable

JobFn = Callable[[Callable[[str], None]], Any]

# How long a TERMINAL (completed/failed) job is kept in memory before
# `JobManager.create_job`'s opportunistic sweep evicts it. Prevents the
# in-process `dict` from growing unbounded over a long-running backend
# process (docs/decision-log.md 2026-08-04 review, point 3).
JOB_TTL_SECONDS = 3600


@dataclass
class JobEvent:
    type: str  # "started" | "log" | "progress" | "completed" | "failed"
    data: Any = None
    at: float = field(default_factory=time.time)


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | completed | failed
    result: Any = None
    error: Optional[str] = None
    log_history: list[str] = field(default_factory=list)
    queue: asyncio.Queue[JobEvent] = field(default_factory=asyncio.Queue)
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # Optional session-plane tag (Phase 1). None for jobs not tied to a
    # session (e.g. the pre-existing /api/codegen, /api/backtest/run routes).
    session_id: Optional[str] = None
    step: Optional[int] = None
    stage: str = ""


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def _sweep_expired(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and (now - job.finished_at) > JOB_TTL_SECONDS
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def create_job(
        self,
        fn: JobFn,
        session_id: Optional[str] = None,
        step: Optional[int] = None,
        stage: str = "",
    ) -> str:
        """Must be called from a coroutine running on the main event loop
        (i.e. from an `async def` route handler) -- FastAPI/Starlette runs
        plain `def` route handlers in a worker thread pool, which has no
        running event loop of its own."""
        self._sweep_expired()
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, session_id=session_id, step=step, stage=stage)
        self._jobs[job_id] = job
        loop = asyncio.get_running_loop()

        def log(message: str) -> None:
            job.log_history.append(message)
            loop.call_soon_threadsafe(job.queue.put_nowait, JobEvent("log", message))
            if job.session_id:
                # Lazy import: backend.sessions has no dependency on jobs.py,
                # so this is safe, but importing at call time (not module
                # top) avoids any accidental import-order coupling.
                from backend.sessions import append_event

                append_event(job.session_id, step=job.step, stage=job.stage or "job", event="log", detail=message)

        def run_blocking() -> Any:
            return fn(log)

        async def runner() -> None:
            job.status = "running"
            await job.queue.put(JobEvent("started"))
            try:
                result = await asyncio.to_thread(run_blocking)
                job.status = "completed"
                job.result = to_jsonable(result)
                job.finished_at = time.time()
                await job.queue.put(JobEvent("completed", job.result))
            except Exception as exc:  # noqa: BLE001 - report any failure to the client
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc()}"
                job.finished_at = time.time()
                await job.queue.put(JobEvent("failed", str(exc)))

        asyncio.ensure_future(runner())
        return job_id

    def snapshot(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job.id,
            "status": job.status,
            "result": job.result,
            "error": job.error,
            "log_history": job.log_history,
            "session_id": job.session_id,
            "step": job.step,
        }


job_manager = JobManager()
