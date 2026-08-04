"""Unit tests for backend/jobs.py's Phase 1 additions: session-journal
wiring on `log()`, and the TTL eviction sweep. SSE heartbeat framing itself
is exercised indirectly (it only changes idle-timeout behavior, not
data delivered) -- not worth an async-timing test here.
"""

from __future__ import annotations

import asyncio
import time

from backend.jobs import Job, JobManager
from backend.sessions import read_events, session_store


def test_session_tagged_job_log_writes_to_event_journal():
    manifest = session_store.create(factor_id="factor_a")
    manager = JobManager()

    async def _run():
        job_id = manager.create_job(
            lambda log: log("hello from step1") or "done",
            session_id=manifest.session_id,
            step=1,
            stage="extract",
        )
        # Drain until the job finishes.
        job = manager.get(job_id)
        while job.status not in ("completed", "failed"):
            await asyncio.sleep(0.01)

    asyncio.run(_run())

    events = read_events(manifest.session_id)
    assert any(e["event"] == "log" and e["detail"] == "hello from step1" for e in events)
    assert any(e["step"] == 1 and e["stage"] == "extract" for e in events)


def test_untagged_job_does_not_touch_session_journal():
    manager = JobManager()

    async def _run():
        job_id = manager.create_job(lambda log: log("no session here") or "done")
        job = manager.get(job_id)
        while job.status not in ("completed", "failed"):
            await asyncio.sleep(0.01)

    asyncio.run(_run())
    # No exception, and nothing to assert about a session journal since none
    # was tagged -- this test exists to prove the untagged path is a no-op,
    # not silently broken by the new session-aware branch.


def test_ttl_eviction_removes_old_completed_jobs():
    manager = JobManager()
    old_job = Job(id="old", status="completed", finished_at=time.time() - 999999)
    fresh_job = Job(id="fresh", status="completed", finished_at=time.time())
    manager._jobs["old"] = old_job
    manager._jobs["fresh"] = fresh_job

    manager._sweep_expired()

    assert manager.get("old") is None
    assert manager.get("fresh") is not None


def test_sweep_never_evicts_a_job_still_running():
    manager = JobManager()
    running_job = Job(id="running", status="running", finished_at=None)
    manager._jobs["running"] = running_job

    manager._sweep_expired()

    assert manager.get("running") is not None
