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

from src.infra.session_store import SessionStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = REPO_ROOT / "runs" / "sessions"

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
