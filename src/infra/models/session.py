"""Session -- persisted workflow-control-plane state for the step1-8 web UI.

A `Session` is the "workflow control plane": it tracks WHICH step a factor
replication run is currently at, records an append-only history of attempts
per step, and answers "can the UI advance past step N". It deliberately owns
NO empirical artifacts of its own beyond the small step1-4 documents (spec /
review report / resolution / plugin / script / validation report) -- those
are the only artifacts not already owned by an authoritative store elsewhere.

From step5 onward, a `Session` stores REFERENCES ONLY:
- `execution_ids` / `experiment_batch_id` point into `EvidenceStore`
  (`src/infra/evidence/__init__.py`) and `RunRegistry`, which remain the sole
  authority for `RunRecord`s, return/signal series, and logs.
- `comparison_ref` points at an existing `runs/backtest_scripts/results/
  {factor_id}/comparison.json`, which remains the sole authoritative input to
  step7/step8 (see `src/steps/step7_replication_diff/bundle.py`).
- `diagnosis_ref` points at the sibling `diagnosis.json`/`diagnosis.md`.

This split (see docs/decision-log.md, 2026-08-04 "Session-centric web UI
redesign") exists specifically so no artifact ever has two owners.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Bump when SessionManifest's on-disk shape changes in a way old manifests
# can't be read as-is. The loader (session_store.py) is expected to either
# migrate a known older version or refuse to load an unknown one -- never
# silently guess.
SESSION_SCHEMA_VERSION = 1


class SessionState(str, enum.Enum):
    """Overall session-level phase (one active step at a time)."""

    CREATED = "created"
    EXTRACTING = "extracting"
    AWAITING_REVIEW = "awaiting_review"
    READY_FOR_CODEGEN = "ready_for_codegen"
    SCRIPT_BUILT = "script_built"
    VALIDATED = "validated"
    EXECUTING = "executing"
    EXPERIMENT_COMPLETE = "experiment_complete"
    COMPARISON_COMPLETE = "comparison_complete"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    # Exceptional / terminal-ish states, reachable from (in principle) any
    # of the above:
    BLOCKED = "blocked"  # step2 disposition requires human resolution
    FAILED = "failed"  # a step raised / returned a failure
    INTERRUPTED = "interrupted"  # backend restarted mid-step; never resumed automatically
    CANCELLED = "cancelled"  # user-initiated abort
    ARCHIVED = "archived"  # soft-deleted; evidence artifacts are never touched


# The "happy path" linear order. Used to compute default forward transitions
# and to decide which downstream steps become stale after an upstream rerun.
_HAPPY_PATH: list[SessionState] = [
    SessionState.CREATED,
    SessionState.EXTRACTING,
    SessionState.AWAITING_REVIEW,
    SessionState.READY_FOR_CODEGEN,
    SessionState.SCRIPT_BUILT,
    SessionState.VALIDATED,
    SessionState.EXECUTING,
    SessionState.EXPERIMENT_COMPLETE,
    SessionState.COMPARISON_COMPLETE,
    SessionState.DIAGNOSIS_COMPLETE,
]

# States from which a session may be re-entered onto the happy path (i.e.
# rerun-friendly) vs. states that require an explicit human/user action first.
_RERUNNABLE_FROM = {
    SessionState.AWAITING_REVIEW,
    SessionState.READY_FOR_CODEGEN,
    SessionState.SCRIPT_BUILT,
    SessionState.VALIDATED,
    SessionState.EXPERIMENT_COMPLETE,
    SessionState.COMPARISON_COMPLETE,
    SessionState.DIAGNOSIS_COMPLETE,
    SessionState.BLOCKED,
    SessionState.FAILED,
    SessionState.INTERRUPTED,
}

# Exceptional states reachable from ANY non-terminal state (a step can fail,
# a backend can restart, a user can cancel, at any point in the happy path).
_EXCEPTIONAL_TARGETS = {
    SessionState.BLOCKED,
    SessionState.FAILED,
    SessionState.INTERRUPTED,
    SessionState.CANCELLED,
}

# ARCHIVED is reachable from any state (archive is always allowed) except
# from ARCHIVED itself (no-op) -- enforced in validate_transition.


def _forward_pairs() -> set[tuple[SessionState, SessionState]]:
    pairs: set[tuple[SessionState, SessionState]] = set()
    for i in range(len(_HAPPY_PATH) - 1):
        pairs.add((_HAPPY_PATH[i], _HAPPY_PATH[i + 1]))
    return pairs


_FORWARD_PAIRS = _forward_pairs()


class IllegalTransitionError(ValueError):
    """Raised when a session state transition is not permitted."""


def validate_transition(current: SessionState, new: SessionState) -> None:
    """Raise `IllegalTransitionError` unless `current -> new` is a legal edge.

    Legal edges are:
    - any single forward step along the happy path (`_FORWARD_PAIRS`);
    - from a rerunnable state, back to the NEXT happy-path state after a
      fresh attempt (same edge set as forward -- rerun does not invent new
      edges, it just means a *new attempt* was appended for that step,
      which is a manifest-level fact, not a state-machine fact);
    - from any non-terminal state into one of the exceptional targets
      (`BLOCKED`/`FAILED`/`INTERRUPTED`/`CANCELLED`);
    - from `BLOCKED`/`FAILED`/`INTERRUPTED`/`CANCELLED` back onto the happy
      path at the step that raised it (recovery), i.e. treated the same as
      a rerunnable state's forward edge;
    - into `ARCHIVED` from anything except `ARCHIVED` itself.

    Never legal: skipping a happy-path step, moving backward on the happy
    path (that's a rerun -- a new attempt at the SAME step, not a state
    transition to an earlier one), or leaving `ARCHIVED`.
    """
    if current == new:
        raise IllegalTransitionError(f"session is already in state {current.value!r}")

    if current == SessionState.ARCHIVED:
        raise IllegalTransitionError("an archived session cannot change state")

    if new == SessionState.ARCHIVED:
        return  # archiving is always allowed (soft-delete, evidence untouched)

    if new in _EXCEPTIONAL_TARGETS:
        return  # any non-terminal state can fail/block/interrupt/cancel

    if (current, new) in _FORWARD_PAIRS:
        return  # normal forward advance

    if current in _RERUNNABLE_FROM and new in _HAPPY_PATH:
        current_idx = _HAPPY_PATH.index(current) if current in _HAPPY_PATH else -1
        new_idx = _HAPPY_PATH.index(new)
        if current in (
            SessionState.BLOCKED,
            SessionState.FAILED,
            SessionState.INTERRUPTED,
        ):
            return  # recovering from an exceptional state back onto the happy path
        if current_idx >= 0 and new_idx == current_idx + 1:
            return  # covered by _FORWARD_PAIRS already, kept for clarity

    raise IllegalTransitionError(
        f"illegal session transition {current.value!r} -> {new.value!r}"
    )


class StepStatus(str, enum.Enum):
    """Per-step, per-attempt status. Distinct from the session-level `SessionState`."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


# Human-readable step registry the backend and frontend both key off of.
STEP_NAMES: dict[int, str] = {
    1: "extract",
    2: "review",
    3: "codegen",
    4: "validate",
    5: "execute",
    6: "experiment",
    7: "replication_diff",
    8: "diagnosis",
}


# Phase 0.4 contract: which manifest ref keys each step reads (`input_refs`)
# and writes (`output_refs`). This is the single source of truth both the
# backend (to check "can step N start" / "what does step N need to read")
# and the frontend `STEP_REGISTRY` are meant to mirror -- do not duplicate
# this list elsewhere. `ref` values below are `SessionManifest`/`StepAttempt.
# output_refs` dict KEYS, not file paths.
STEP_IO_CONTRACT: dict[int, dict[str, list[str]]] = {
    1: {"input_refs": ["paper_id"], "output_refs": ["methodspec_ref"]},
    2: {
        "input_refs": ["methodspec_ref"],
        "output_refs": ["review_report_ref", "resolution_ref"],
    },
    3: {
        "input_refs": ["methodspec_ref", "review_report_ref"],
        "output_refs": ["plugin_ref", "script_ref", "script_sha256"],
    },
    4: {
        "input_refs": ["methodspec_ref", "plugin_ref", "script_ref", "script_sha256"],
        "output_refs": ["validation_ref", "validated_script_sha256"],
    },
    5: {
        "input_refs": ["script_ref", "script_sha256", "validated_script_sha256"],
        "output_refs": ["execution_ids"],
    },
    6: {
        "input_refs": ["methodspec_ref", "plugin_ref"],
        "output_refs": ["experiment_batch_id", "execution_ids"],
    },
    7: {
        "input_refs": ["experiment_batch_id", "execution_ids"],
        "output_refs": ["comparison_ref"],
    },
    8: {"input_refs": ["comparison_ref"], "output_refs": ["diagnosis_ref"]},
}


def missing_input_refs(manifest: SessionManifest, step: int) -> list[str]:
    """Which of step N's required input refs are not yet present anywhere
    upstream in the manifest's recorded output_refs. Used to gate whether a
    step may start standalone (Phase 1's "run any step alone from a stored
    upstream artifact" requirement)."""
    contract = STEP_IO_CONTRACT.get(step, {"input_refs": [], "output_refs": []})
    available: set[str] = {"paper_id"} if manifest.paper_id else set()
    for record in manifest.steps.values():
        if record.latest and record.latest.status == StepStatus.SUCCESS:
            available.update(record.latest.output_refs.keys())
    return [ref for ref in contract["input_refs"] if ref not in available]


class StepAttempt(BaseModel):
    """One immutable attempt at a step. Rerunning a step APPENDS a new attempt;

    it never overwrites a prior one -- this is the audit trail a re-run needs
    (docs/decision-log.md 2026-08-04 entry).
    """

    attempt_index: int = Field(..., description="0-based attempt number for this step")
    status: StepStatus = StepStatus.NOT_STARTED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    job_id: Optional[str] = Field(
        default=None,
        description=(
            "In-process job id active for this attempt, if any. Purely a "
            "realtime hint for SSE re-attachment after a browser reload -- "
            "NEVER trusted as a source of truth after a backend restart "
            "(job_manager is in-memory; see backend/jobs.py). On backend "
            "startup, any attempt left `running` is reconciled to `interrupted`."
        ),
    )
    error: Optional[str] = None

    # Reference-only outputs. Which keys are populated depends on the step;
    # step1-4 keys point at small artifacts physically stored under this
    # session's directory, step5+ keys point into EvidenceStore/
    # comparison.json and are never copied.
    output_refs: dict[str, str] = Field(default_factory=dict)

    # Deterministic readiness/counters/flags from `src.evaluation.diagnostics`
    # -- NEVER a unified quality score (see that module's docstring for why).
    # Optional: not every attempt (e.g. a still-`running` one) has these yet.
    diagnostics: dict = Field(default_factory=dict)

    # Hash of the upstream refs this attempt actually consumed, so staleness
    # can be detected precisely (an attempt is stale iff any upstream ref it
    # used no longer matches the session's CURRENT ref for that dependency).
    input_ref_snapshot: dict[str, str] = Field(default_factory=dict)


class StepRecord(BaseModel):
    """All attempts for one step (1-8), plus the derived "latest" view."""

    step: int
    name: str = ""
    attempts: list[StepAttempt] = Field(default_factory=list)
    stale: bool = Field(
        default=False,
        description="True when an upstream step produced a new attempt after this step's latest attempt was recorded.",
    )

    def model_post_init(self, context: object, /) -> None:
        if not self.name:
            self.name = STEP_NAMES.get(self.step, f"step{self.step}")

    @property
    def latest(self) -> Optional[StepAttempt]:
        return self.attempts[-1] if self.attempts else None


class SessionManifest(BaseModel):
    """The single persisted source of truth for one factor-replication session.

    Written atomically (temp-file + os.replace) by `SessionStore`, guarded by
    an on-disk lock plus this `revision` field for compare-and-set updates
    (see src/infra/session_store.py) -- two concurrent writers must not be
    able to silently drop each other's field.
    """

    schema_version: int = SESSION_SCHEMA_VERSION
    session_id: str
    factor_id: str
    paper_id: Optional[str] = None
    state: SessionState = SessionState.CREATED
    revision: int = Field(
        default=0,
        description="Monotonically incremented on every successful write; used for compare-and-set.",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    steps: dict[int, StepRecord] = Field(
        default_factory=lambda: {n: StepRecord(step=n) for n in STEP_NAMES}
    )

    # Session-level transition audit (lightweight; the FULL structured event
    # journal is a separate append-only file per Phase 1, not duplicated
    # here -- this list is just enough to answer "how did we get here"
    # without reading the journal).
    transition_log: list[dict] = Field(default_factory=list)


class ConcurrentModificationError(RuntimeError):
    """Raised when a compare-and-set write loses a race (stale `revision`)."""
