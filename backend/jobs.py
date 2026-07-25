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


@dataclass
class JobEvent:
    type: str  # "started" | "log" | "completed" | "failed"
    data: Any = None
    at: float = field(default_factory=time.time)


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | completed | failed
    result: Any = None
    error: Optional[str] = None
    log_history: list[str] = field(default_factory=list)
    queue: "asyncio.Queue[JobEvent]" = field(default_factory=asyncio.Queue)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def create_job(self, fn: JobFn) -> str:
        """Must be called from a coroutine running on the main event loop
        (i.e. from an `async def` route handler) -- FastAPI/Starlette runs
        plain `def` route handlers in a worker thread pool, which has no
        running event loop of its own."""
        job_id = str(uuid.uuid4())
        job = Job(id=job_id)
        self._jobs[job_id] = job
        loop = asyncio.get_running_loop()

        def log(message: str) -> None:
            job.log_history.append(message)
            loop.call_soon_threadsafe(job.queue.put_nowait, JobEvent("log", message))

        def run_blocking() -> Any:
            return fn(log)

        async def runner() -> None:
            job.status = "running"
            await job.queue.put(JobEvent("started"))
            try:
                result = await asyncio.to_thread(run_blocking)
                job.status = "completed"
                job.result = to_jsonable(result)
                await job.queue.put(JobEvent("completed", job.result))
            except Exception as exc:  # noqa: BLE001 - report any failure to the client
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc()}"
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
        }


job_manager = JobManager()
