"""Tests for the Session control-plane: state machine + SessionStore.

Phase 0 deliverable (docs/decision-log.md 2026-08-04 "Session-centric web UI
redesign"): contracts and state-transition tests come before any endpoint.
"""

from __future__ import annotations

import json
import threading

import pytest

from src.infra.models.session import (
    ConcurrentModificationError,
    IllegalTransitionError,
    SessionState,
    StepStatus,
    validate_transition,
)
from src.infra.session_store import (
    SessionNotFoundError,
    SessionStore,
    UnknownSchemaVersionError,
)

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class TestStateMachine:
    def test_happy_path_forward_step_is_legal(self):
        validate_transition(SessionState.CREATED, SessionState.EXTRACTING)
        validate_transition(SessionState.EXTRACTING, SessionState.AWAITING_REVIEW)
        validate_transition(SessionState.EXECUTING, SessionState.EXPERIMENT_COMPLETE)

    def test_skipping_a_happy_path_step_is_illegal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(SessionState.CREATED, SessionState.READY_FOR_CODEGEN)

    def test_moving_backward_on_happy_path_is_illegal(self):
        # Backward movement isn't a state transition -- it's a NEW ATTEMPT at
        # the same step, recorded via StepAttempt, not a session state change.
        with pytest.raises(IllegalTransitionError):
            validate_transition(SessionState.VALIDATED, SessionState.SCRIPT_BUILT)

    def test_same_state_is_illegal(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(SessionState.CREATED, SessionState.CREATED)

    @pytest.mark.parametrize(
        "start",
        [
            SessionState.CREATED,
            SessionState.EXTRACTING,
            SessionState.AWAITING_REVIEW,
            SessionState.EXECUTING,
            SessionState.EXPERIMENT_COMPLETE,
        ],
    )
    def test_any_non_terminal_state_can_become_exceptional(self, start):
        for target in (
            SessionState.BLOCKED,
            SessionState.FAILED,
            SessionState.INTERRUPTED,
            SessionState.CANCELLED,
        ):
            validate_transition(start, target)

    def test_recovering_from_failed_back_onto_happy_path_is_legal(self):
        validate_transition(SessionState.FAILED, SessionState.SCRIPT_BUILT)

    def test_recovering_from_interrupted_back_onto_happy_path_is_legal(self):
        validate_transition(SessionState.INTERRUPTED, SessionState.EXECUTING)

    def test_archive_is_legal_from_any_non_archived_state(self):
        validate_transition(SessionState.CREATED, SessionState.ARCHIVED)
        validate_transition(SessionState.DIAGNOSIS_COMPLETE, SessionState.ARCHIVED)
        validate_transition(SessionState.FAILED, SessionState.ARCHIVED)

    def test_archived_is_a_true_terminal_state(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(SessionState.ARCHIVED, SessionState.CREATED)
        with pytest.raises(IllegalTransitionError):
            validate_transition(SessionState.ARCHIVED, SessionState.ARCHIVED)


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    return SessionStore(base_path=str(tmp_path / "sessions"))


class TestSessionStoreCrud:
    def test_create_and_get_roundtrip(self, store):
        created = store.create(factor_id="cooper_gulen_schill_2008_asset_growth")
        loaded = store.get(created.session_id)
        assert loaded.session_id == created.session_id
        assert loaded.factor_id == "cooper_gulen_schill_2008_asset_growth"
        assert loaded.state == SessionState.CREATED
        assert loaded.revision == 0
        assert set(loaded.steps.keys()) == set(range(1, 9))

    def test_get_unknown_session_raises(self, store):
        with pytest.raises(SessionNotFoundError):
            store.get("does-not-exist")

    def test_list_all_returns_created_sessions(self, store):
        a = store.create(factor_id="factor_a")
        b = store.create(factor_id="factor_b")
        ids = {s.session_id for s in store.list_all()}
        assert ids == {a.session_id, b.session_id}

    def test_manifest_write_is_atomic_no_leftover_tmp_files(self, store):
        created = store.create(factor_id="factor_a")
        store.transition(created.session_id, created.revision, SessionState.EXTRACTING)
        session_dir = store._session_dir(created.session_id)
        leftover = list(session_dir.glob(".session.*.tmp"))
        assert leftover == [], f"atomic write left temp files: {leftover}"
        # And the manifest itself must be valid JSON, not truncated.
        with open(store._manifest_path(created.session_id)) as f:
            json.load(f)

    def test_unknown_schema_version_is_rejected_not_guessed(self, store):
        created = store.create(factor_id="factor_a")
        path = store._manifest_path(created.session_id)
        data = json.loads(path.read_text())
        data["schema_version"] = 999
        path.write_text(json.dumps(data))
        with pytest.raises(UnknownSchemaVersionError):
            store.get(created.session_id)


class TestConcurrency:
    def test_stale_revision_is_rejected(self, store):
        created = store.create(factor_id="factor_a")
        store.transition(created.session_id, created.revision, SessionState.EXTRACTING)
        # `created.revision` (0) is now stale -- current on-disk revision is 1.
        with pytest.raises(ConcurrentModificationError):
            store.transition(created.session_id, created.revision, SessionState.AWAITING_REVIEW)

    def test_concurrent_writers_neither_silently_drops_the_others_field(self, store):
        created = store.create(factor_id="factor_a")
        rev = created.revision
        results = {"a": None, "b": None}
        barrier = threading.Barrier(2)

        def writer_a():
            barrier.wait()
            try:
                store.start_attempt(created.session_id, rev, step=1)
                results["a"] = "ok"
            except ConcurrentModificationError:
                results["a"] = "conflict"

        def writer_b():
            barrier.wait()
            try:
                store.transition(created.session_id, rev, SessionState.EXTRACTING)
                results["b"] = "ok"
            except ConcurrentModificationError:
                results["b"] = "conflict"

        t1 = threading.Thread(target=writer_a)
        t2 = threading.Thread(target=writer_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one writer must have won against the shared expected_revision;
        # the loser must see a conflict, never a silently-merged/dropped write.
        outcomes = sorted(results.values())
        assert outcomes == ["conflict", "ok"], results

        final = store.get(created.session_id)
        assert final.revision == 1  # only the winner's single update applied


class TestAttemptsAndStaleness:
    def test_rerun_appends_a_new_attempt_never_overwrites(self, store):
        created = store.create(factor_id="factor_a")
        s1 = store.start_attempt(created.session_id, created.revision, step=1)
        s2 = store.complete_attempt(
            created.session_id, s1.revision, step=1, status=StepStatus.SUCCESS,
            output_refs={"methodspec_ref": "spec_v1.json"},
        )
        # Rerun step 1.
        s3 = store.start_attempt(created.session_id, s2.revision, step=1)
        assert len(s3.steps[1].attempts) == 2
        assert s3.steps[1].attempts[0].output_refs == {"methodspec_ref": "spec_v1.json"}
        assert s3.steps[1].attempts[0].status == StepStatus.SUCCESS  # untouched by the rerun

    def test_rerunning_upstream_step_marks_downstream_stale(self, store):
        created = store.create(factor_id="factor_a")
        m = store.start_attempt(created.session_id, created.revision, step=1)
        m = store.complete_attempt(created.session_id, m.revision, step=1, status=StepStatus.SUCCESS)
        m = store.start_attempt(created.session_id, m.revision, step=3)
        m = store.complete_attempt(created.session_id, m.revision, step=3, status=StepStatus.SUCCESS)
        assert m.steps[3].stale is False

        # Rerun step 1 (e.g. re-extraction) -- step3's existing attempt must
        # now be flagged stale since it was built from the OLD spec.
        m = store.start_attempt(created.session_id, m.revision, step=1)
        assert m.steps[3].stale is True
        # The step being rerun itself is not "stale" against itself.
        assert m.steps[1].stale is False

    def test_step_with_no_attempts_is_never_marked_stale(self, store):
        created = store.create(factor_id="factor_a")
        m = store.start_attempt(created.session_id, created.revision, step=1)
        m = store.complete_attempt(created.session_id, m.revision, step=1, status=StepStatus.SUCCESS)
        m = store.start_attempt(created.session_id, m.revision, step=1)
        assert m.steps[5].attempts == []
        assert m.steps[5].stale is False


class TestReconciliation:
    def test_orphaned_running_attempt_is_marked_interrupted_on_reconcile(self, store):
        created = store.create(factor_id="factor_a")
        store.start_attempt(created.session_id, created.revision, step=1)
        # Simulate the process dying mid-step: nothing ever calls complete_attempt.

        touched = store.reconcile_orphaned_running()
        assert created.session_id in touched

        final = store.get(created.session_id)
        assert final.state == SessionState.INTERRUPTED
        assert final.steps[1].attempts[-1].status == StepStatus.FAILED
        assert "interrupted" in final.steps[1].attempts[-1].error

    def test_reconcile_is_a_no_op_when_nothing_is_running(self, store):
        created = store.create(factor_id="factor_a")
        m = store.start_attempt(created.session_id, created.revision, step=1)
        store.complete_attempt(created.session_id, m.revision, step=1, status=StepStatus.SUCCESS)

        touched = store.reconcile_orphaned_running()
        assert touched == []


class TestStepDirOwnership:
    def test_step_dir_allows_step1_through_4(self, store):
        created = store.create(factor_id="factor_a")
        for step in (1, 2, 3, 4):
            d = store.step_dir(created.session_id, step)
            assert d.exists()

    def test_step_dir_rejects_step5_and_beyond_reference_only(self, store):
        created = store.create(factor_id="factor_a")
        for step in (5, 6, 7, 8):
            with pytest.raises(ValueError):
                store.step_dir(created.session_id, step)
