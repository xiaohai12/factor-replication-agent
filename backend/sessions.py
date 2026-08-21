"""Shared backend state for the Session control plane: one process-wide
`SessionStore` (mirrors `backend/state.py`'s single `Pipeline` instance) plus
a tiny append-only structured event journal per session.

The event journal is a deliberate wrapper AROUND the idea in
`src/infra/trace.py`'s `PipelineTracer` (same `stage`/`event`/`detail`/`level`
shape), not a modification of it -- `app.py` still constructs its own
in-memory `PipelineTracer` per session and that must keep working unchanged.
This journal is the persisted, session-scoped, multi-reader-safe version the
backend needs instead.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.state import RUNS_DIR
from src.infra.models.session import ConcurrentModificationError, StepStatus
from src.infra.session_store import SessionStore

SESSIONS_DIR = RUNS_DIR / "sessions"

session_store = SessionStore(base_path=str(SESSIONS_DIR))


def _events_path(session_id: str) -> Path:
    d = SESSIONS_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "events.jsonl"


def append_event(
    session_id: str,
    step: Optional[int],
    stage: str,
    event: str,
    detail: str = "",
    level: str = "info",
) -> dict:
    """Append one structured event to `runs/sessions/{sid}/events.jsonl`.

    Appending a single line to an already-open file in append mode is an
    atomic-enough operation for this tool's local-only, no-concurrent-writer-
    across-processes use case (a single backend process owns this file); the
    `SessionManifest` itself is what needs the stronger CAS guarantee since
    multiple request handlers race to mutate shared fields on it.
    """
    path = _events_path(session_id)
    if path.exists():
        with open(path) as f:
            seq = sum(1 for _ in f)
    else:
        seq = 0
    record = {
        "seq": seq,
        "at": datetime.now().isoformat(),
        "step": step,
        "stage": stage,
        "event": event,
        "detail": detail,
        "level": level,
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_events(session_id: str, since_seq: int = -1) -> list[dict]:
    path = _events_path(session_id)
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record["seq"] > since_seq:
                out.append(record)
    return out


def start_attempt_with_retry(
    session_id: str,
    step: int,
    job_id: Optional[str] = None,
    max_attempts: int = 5,
):
    """Like `SessionStore.start_attempt`, but for callers (e.g.
    `backend/routers/methodspecs.py`'s Step1/2 job-creation endpoints) that
    don't want to make the caller track/pass the manifest's current
    `revision` just to kick off a step attempt -- unlike steps 3-5
    (`backend/routers/sessions.py`), which gate this on a client-supplied
    `expected_revision` because they're building on top of a specific prior
    artifact the client just looked at. Re-reads the manifest and retries on
    `ConcurrentModificationError`, same reasoning as
    `complete_attempt_with_retry`.
    """
    last_exc: Optional[ConcurrentModificationError] = None
    for _ in range(max_attempts):
        current = session_store.get(session_id)
        try:
            return session_store.start_attempt(session_id, current.revision, step=step, job_id=job_id)
        except ConcurrentModificationError as exc:
            last_exc = exc
    raise last_exc  # pragma: no cover -- only reachable under genuine concurrent writers


def complete_attempt_with_retry(
    session_id: str,
    step: int,
    status: StepStatus,
    output_refs: Optional[dict] = None,
    error: Optional[str] = None,
    diagnostics: Optional[dict] = None,
    max_attempts: int = 5,
):
    """Like `SessionStore.complete_attempt`, but for callers that don't know
    the manifest's CURRENT revision at the moment a background job finishes
    (the request handler that called `start_attempt` returned long ago).
    Re-reads the manifest and retries on `ConcurrentModificationError` --
    safe here because nothing else is expected to be racing to complete THIS
    SAME step's in-progress attempt; a genuine collision (e.g. two jobs for
    the same step) should still eventually surface as an error once
    `max_attempts` is exhausted rather than looping forever.
    """
    last_exc: Optional[ConcurrentModificationError] = None
    for _ in range(max_attempts):
        current = session_store.get(session_id)
        try:
            return session_store.complete_attempt(
                session_id, current.revision, step=step, status=status,
                output_refs=output_refs, error=error, diagnostics=diagnostics,
            )
        except ConcurrentModificationError as exc:
            last_exc = exc
    raise last_exc  # pragma: no cover -- only reachable under genuine concurrent writers
