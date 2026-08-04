"""SessionStore -- the workflow-control-plane persistence layer.

Deliberately NOT a copy of `EvidenceStore.save_run`'s pattern
(`src/infra/evidence/__init__.py`): that method is a whole-directory
`rmtree()` + `rename()` swap designed for a SINGLE writer producing a
complete, self-contained run directory once. A `SessionManifest` is instead
updated incrementally, from possibly-concurrent request handlers (e.g. two
browser tabs, or a background job and a foreground poll), so it needs:

- a real lock around the read-modify-write cycle (`_locked()`), and
- a compare-and-set `revision` check even inside that lock, so a caller that
  read a stale manifest and computed its update from it is rejected instead
  of silently clobbering a field somebody else already changed.

Only step1-4 artifacts (small text/JSON documents) are physically written
under the session directory. Everything from step5 on is reference-only --
see `src/infra/models/session.py`'s module docstring for the ownership
rationale.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from src.infra.models.session import (
    ConcurrentModificationError,
    SessionManifest,
    SessionState,
    StepAttempt,
    StepStatus,
    validate_transition,
)

# Step numbers whose artifacts are small enough, and not already owned by
# EvidenceStore, to live physically inside the session directory. Kept as a
# named constant (not a magic "<=4") so the ownership boundary is
# self-documenting at the one place that enforces it.
SESSION_OWNED_STEPS = frozenset({1, 2, 3, 4})


class SessionNotFoundError(LookupError):
    pass


class UnknownSchemaVersionError(ValueError):
    """Raised when a manifest on disk declares a schema_version this code
    doesn't know how to read. Refusing to load beats silently guessing.
    """


class SessionStore:
    def __init__(self, base_path: str = "./runs/sessions"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        return self.base_path / session_id

    def _manifest_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def _lock_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / ".lock"

    def step_dir(self, session_id: str, step: int) -> Path:
        """Directory for a SESSION_OWNED_STEPS artifact. Callers for step5+
        must not call this -- they only ever store a reference string.
        """
        if step not in SESSION_OWNED_STEPS:
            raise ValueError(
                f"step {step} is reference-only (owned by EvidenceStore/comparison.json); "
                "SessionStore does not persist its artifacts"
            )
        d = self._session_dir(session_id) / "steps" / f"step{step}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- locking -----------------------------------------------------------

    @contextmanager
    def _locked(self, session_id: str) -> Iterator[None]:
        lock_path = self._lock_path(session_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    # -- atomic single-file write -----------------------------------------

    def _write_manifest_atomic(self, session_id: str, manifest: SessionManifest) -> None:
        path = self._manifest_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".session.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(manifest.model_dump(mode="json"), indent=2, default=str))
            os.replace(tmp_name, path)  # atomic on POSIX
        except BaseException:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise

    # -- CRUD ---------------------------------------------------------------

    def create(self, factor_id: str, paper_id: Optional[str] = None) -> SessionManifest:
        session_id = uuid4().hex
        manifest = SessionManifest(session_id=session_id, factor_id=factor_id, paper_id=paper_id)
        with self._locked(session_id):
            self._write_manifest_atomic(session_id, manifest)
        return manifest

    def get(self, session_id: str) -> SessionManifest:
        path = self._manifest_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(session_id)
        with open(path) as f:
            data = json.load(f)
        version = data.get("schema_version")
        if version != SessionManifest.model_fields["schema_version"].default:
            raise UnknownSchemaVersionError(
                f"session {session_id!r} has schema_version={version!r}, "
                f"this code only reads {SessionManifest.model_fields['schema_version'].default!r}"
            )
        return SessionManifest(**data)

    def list_all(self) -> list[SessionManifest]:
        out = []
        if not self.base_path.exists():
            return out
        for child in sorted(self.base_path.iterdir()):
            if (child / "session.json").exists():
                try:
                    out.append(self.get(child.name))
                except (SessionNotFoundError, UnknownSchemaVersionError):
                    continue
        return out

    def update(
        self,
        session_id: str,
        expected_revision: int,
        mutate: Callable[[SessionManifest], None],
    ) -> SessionManifest:
        """Compare-and-set update: read-modify-write under the session lock.

        `mutate` is called with the freshly-loaded manifest and must mutate
        it in place (setting `.state`, appending to `.steps[n].attempts`,
        etc.) -- it must NOT touch `.revision`/`.updated_at`, which this
        method owns. If `expected_revision` doesn't match what's currently on
        disk, raises `ConcurrentModificationError` instead of applying the
        mutation -- the caller re-reads and retries rather than silently
        overwriting a concurrent change.
        """
        with self._locked(session_id):
            current = self.get(session_id)
            if current.revision != expected_revision:
                raise ConcurrentModificationError(
                    f"session {session_id!r}: expected revision {expected_revision}, "
                    f"found {current.revision}"
                )
            mutate(current)
            current.revision += 1
            current.updated_at = datetime.now()
            self._write_manifest_atomic(session_id, current)
            return current

    def transition(
        self,
        session_id: str,
        expected_revision: int,
        new_state: SessionState,
        reason: str = "",
    ) -> SessionManifest:
        def _mutate(manifest: SessionManifest) -> None:
            validate_transition(manifest.state, new_state)
            manifest.transition_log.append(
                {
                    "at": datetime.now().isoformat(),
                    "from": manifest.state.value,
                    "to": new_state.value,
                    "reason": reason,
                }
            )
            manifest.state = new_state

        return self.update(session_id, expected_revision, _mutate)

    def start_attempt(self, session_id: str, expected_revision: int, step: int) -> SessionManifest:
        """Append a new (not_started->running) attempt for `step`, and mark
        every step AFTER it stale (this pipeline's step dependency is a
        strict chain -- a finer per-ref dependency graph is future work)."""

        def _mutate(manifest: SessionManifest) -> None:
            record = manifest.steps[step]
            attempt = StepAttempt(
                attempt_index=len(record.attempts),
                status=StepStatus.RUNNING,
                started_at=datetime.now(),
            )
            record.attempts.append(attempt)
            record.stale = False
            for later_step in range(step + 1, 9):
                if later_step in manifest.steps and manifest.steps[later_step].attempts:
                    manifest.steps[later_step].stale = True

        return self.update(session_id, expected_revision, _mutate)

    def complete_attempt(
        self,
        session_id: str,
        expected_revision: int,
        step: int,
        status: StepStatus,
        output_refs: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> SessionManifest:
        def _mutate(manifest: SessionManifest) -> None:
            record = manifest.steps[step]
            if not record.attempts:
                raise ValueError(f"no attempt in progress for step {step}")
            attempt = record.attempts[-1]
            attempt.status = status
            attempt.completed_at = datetime.now()
            if output_refs:
                attempt.output_refs.update(output_refs)
            if error:
                attempt.error = error

        return self.update(session_id, expected_revision, _mutate)

    def reconcile_orphaned_running(self) -> list[str]:
        """Called once on backend startup: any attempt left `running` (the
        process died mid-step, e.g. a backend restart) is marked `failed`
        with an explanatory error and the session's overall state is moved
        to INTERRUPTED. Returns the list of session_ids touched.

        This is the ONLY place a `running` status is ever changed without an
        explicit step action -- `backend/jobs.py`'s in-memory JobManager
        cannot itself know it was restarted.
        """
        touched: list[str] = []
        for manifest in self.list_all():
            running_steps = [
                n for n, rec in manifest.steps.items() if rec.latest and rec.latest.status == StepStatus.RUNNING
            ]
            if not running_steps:
                continue

            def _mutate(m: SessionManifest, _running_steps=running_steps) -> None:
                for n in _running_steps:
                    attempt = m.steps[n].latest
                    attempt.status = StepStatus.FAILED
                    attempt.completed_at = datetime.now()
                    attempt.error = "interrupted: backend restarted while this step was running"
                if m.state not in (SessionState.ARCHIVED, SessionState.INTERRUPTED):
                    validate_transition(m.state, SessionState.INTERRUPTED)
                    m.transition_log.append(
                        {
                            "at": datetime.now().isoformat(),
                            "from": m.state.value,
                            "to": SessionState.INTERRUPTED.value,
                            "reason": "backend restart reconciliation",
                        }
                    )
                    m.state = SessionState.INTERRUPTED

            self.update(manifest.session_id, manifest.revision, _mutate)
            touched.append(manifest.session_id)
        return touched

    def archive(self, session_id: str, expected_revision: int) -> SessionManifest:
        """Soft delete: mark ARCHIVED. Never deletes the session directory or
        any evidence artifact -- see module docstring / decision-log."""
        return self.transition(session_id, expected_revision, SessionState.ARCHIVED, reason="archived")
