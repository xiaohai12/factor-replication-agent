"""Integration tests for the Session control-plane HTTP surface
(backend/routers/sessions.py) -- Phase 1 of the session-centric UI redesign
(docs/decision-log.md 2026-08-04). Uses the same deterministic synthetic
fixture as tests/test_backend_api.py so the step3->4->5 artifact-identity
chain is verified against real golden numbers, not just fakes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests._spec_test_helpers import asset_growth_resolved_spec
from tests.synthetic_data.asset_growth_synthetic_data import expected_metrics

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"


def _poll_job(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    """Polls `GET /api/jobs/{job_id}` until it's completed/failed (or
    `timeout` elapses) and returns the job snapshot. Step5 execute (and any
    other job-backed step endpoint) returns only `{"job_id": ...}`
    synchronously -- the actual result/error lives on the job, streamed via
    SSE in the real frontend but polled here for test simplicity."""
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] in ("completed", "failed"):
            return snapshot
        time.sleep(0.05)
    return snapshot


def _ensure_session_snapshots(client: TestClient) -> None:
    """Session step3/4/5 endpoints hardcode `REAL_WRDS_SNAPSHOT_ID`/
    `VALIDATION_SAMPLE_SNAPSHOT_ID` internally now (no user-facing
    `snapshot_id` field anymore -- see docs/decision-log.md 2026-08-05).
    Tests still need something registered under those EXACT names so the
    deterministic synthetic golden-number fixture keeps working without
    depending on gitignored real WRDS data. FORCE-overwrites (not
    register-once) so an earlier test that already registered these ids
    against real dev-machine data can never leak into a later test's
    golden-number assertions."""
    client.get("/api/backtest/snapshots")
    from src.infra.data_layer import SnapshotMetadata
    from backend.state import REAL_WRDS_SNAPSHOT_ID, VALIDATION_SAMPLE_SNAPSHOT_ID, pipeline

    synthetic = pipeline.data_layer.snapshots.get_snapshot("synthetic_demo_v1")
    for sid in (REAL_WRDS_SNAPSHOT_ID, VALIDATION_SAMPLE_SNAPSHOT_ID):
        pipeline.data_layer.snapshots.register_snapshot(
            SnapshotMetadata(
                snapshot_id=sid,
                pull_date="test",
                crsp_end_date="test",
                compustat_end_date="test",
                storage_path=synthetic.storage_path,
            )
        )


def _load_fixture_spec() -> dict:
    return json.loads(asset_growth_resolved_spec().model_dump_json())


def _load_fixture_plugin(spec: dict) -> dict:
    return {
        "plugin_id": f"{spec['paper']['factor_id']}_v1",
        "factor_id": spec["paper"]["factor_id"],
        "code": PLUGIN_PATH.read_text(encoding="utf-8"),
        "code_hash": "synthetic",
    }


def test_create_get_list_session():
    with TestClient(app) as client:
        resp = client.post("/api/sessions", json={"factor_id": "factor_a"})
        assert resp.status_code == 200
        manifest = resp.json()
        sid = manifest["session_id"]
        assert manifest["state"] == "created"
        assert manifest["revision"] == 0

        got = client.get(f"/api/sessions/{sid}")
        assert got.status_code == 200
        assert got.json()["session_id"] == sid

        listed = client.get("/api/sessions").json()
        assert any(m["session_id"] == sid for m in listed)


def test_get_unknown_session_404():
    with TestClient(app) as client:
        resp = client.get("/api/sessions/does-not-exist")
        assert resp.status_code == 404


def test_get_step_reports_missing_input_refs():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
        step3 = client.get(f"/api/sessions/{sid}/steps/3").json()
        assert "methodspec_ref" in step3["missing_input_refs"]
        assert step3["contract"]["output_refs"] == ["plugin_ref", "script_ref", "script_sha256", "config_ref"]


def test_events_journal_records_session_creation():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
        events = client.get(f"/api/sessions/{sid}/events").json()
        assert any(e["event"] == "created" for e in events)


def test_archive_is_soft_and_final():
    with TestClient(app) as client:
        created = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()
        sid = created["session_id"]
        resp = client.post(f"/api/sessions/{sid}/archive", json={"expected_revision": 0})
        assert resp.status_code == 200
        assert resp.json()["state"] == "archived"

        # Stale-revision archive attempt (or any further mutation) must be
        # rejected -- and the session directory must still exist on disk.
        again = client.post(f"/api/sessions/{sid}/archive", json={"expected_revision": 0})
        assert again.status_code == 409

        from backend.sessions import SESSIONS_DIR

        assert (SESSIONS_DIR / sid / "session.json").exists()


class TestHardDelete:
    def test_hard_delete_requires_explicit_confirm(self):
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
            resp = client.request(
                "DELETE", f"/api/sessions/{sid}", json={"expected_revision": 0, "confirm": False}
            )
            assert resp.status_code == 400

            from backend.sessions import SESSIONS_DIR

            assert (SESSIONS_DIR / sid / "session.json").exists()

    def test_hard_delete_removes_the_session_directory_and_writes_a_tombstone(self):
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
            resp = client.request(
                "DELETE", f"/api/sessions/{sid}", json={"expected_revision": 0, "confirm": True}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["deleted"] is True

            from backend.sessions import SESSIONS_DIR

            assert not (SESSIONS_DIR / sid).exists()
            tombstone_path = SESSIONS_DIR / "_tombstones" / f"{sid}.json"
            assert tombstone_path.exists()
            tombstone = json.loads(tombstone_path.read_text())
            assert tombstone["session_id"] == sid
            assert tombstone["factor_id"] == "factor_a"

            # The session is gone -- a normal GET now 404s.
            assert client.get(f"/api/sessions/{sid}").status_code == 404

    def test_hard_delete_never_touches_evidence(self):
        """A hard-deleted session's step5 execution_ids reference RunRecords
        that must remain fully intact in EvidenceStore/RunRegistry -- the
        session only ever held a reference to them."""
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)
            built = client.post(
                f"/api/sessions/{sid}/steps/3/script",
                json={"expected_revision": 0, "spec": spec, "plugin": plugin, "snapshot_id": "synthetic_demo_v1"},
            ).json()
            sha, rev = built["sha256"], built["revision"]
            validate_resp = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={"expected_revision": rev, "spec": spec, "plugin": plugin, "script_sha256": sha},
            )
            validate_job = _poll_job(client, validate_resp.json()["job_id"])
            assert validate_job["status"] == "completed", validate_job.get("error")
            rev = validate_job["result"]["revision"]
            executed = client.post(
                f"/api/sessions/{sid}/steps/5/execute",
                json={
                    "expected_revision": rev, "spec": spec, "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1", "script_sha256": sha,
                },
            ).json()
            job = _poll_job(client, executed["job_id"])
            assert job["status"] == "completed", job.get("error")
            run_id = job["result"]["run_record"]["run_id"]
            factor_id = spec["paper"]["factor_id"]

            manifest = client.get(f"/api/sessions/{sid}").json()
            resp = client.request(
                "DELETE", f"/api/sessions/{sid}", json={"expected_revision": manifest["revision"], "confirm": True}
            )
            assert resp.status_code == 200

            evidence_resp = client.get(f"/api/evidence/{factor_id}/{run_id}")
            assert evidence_resp.status_code == 200
            assert "metadata.json" in evidence_resp.json()["files"]

    def _new_session_with_snapshot(self, client: TestClient) -> tuple[str, dict, dict]:
        _ensure_session_snapshots(client)
        spec = _load_fixture_spec()
        plugin = _load_fixture_plugin(spec)
        sid = client.post("/api/sessions", json={"factor_id": spec["paper"]["factor_id"]}).json()["session_id"]
        return sid, spec, plugin


class TestStep3PluginValidation:
    """A malformed/empty `plugin` in step3/4/5's request must be a proper 422
    with pydantic's real error detail, not an unhandled 500 -- reproduced
    live: the frontend's request editor resets `plugin` to the empty
    template default (`{}`) when the user navigates away from step3 and
    back before submitting, and posting that used to crash with
    `PluginRecord.model_validate({})` -> 500. See docs/decision-log.md
    2026-08-05 entry / `_validate_plugin` in backend/routers/sessions.py."""

    def test_empty_plugin_on_step3_script_is_422_not_500(self):
        with TestClient(app) as client:
            _ensure_session_snapshots(client)
            spec = _load_fixture_spec()
            sid = client.post("/api/sessions", json={"factor_id": spec["paper"]["factor_id"]}).json()["session_id"]
            resp = client.post(
                f"/api/sessions/{sid}/steps/3/script",
                json={"expected_revision": 0, "spec": spec, "plugin": {}, "snapshot_id": "synthetic_demo_v1"},
            )
            assert resp.status_code == 422
            assert "Invalid plugin" in resp.json()["detail"]

    def test_validate_unknown_script_sha256_is_404(self):
        """Step4 no longer accepts `spec`/`plugin` over the wire -- it reads
        both back from step3's own `{sha}.spec.json`/`{sha}.plugin.json` by
        `script_sha256` -- so a hash step3 never built for must 404, not
        silently validate nothing."""
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)
            resp = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={"expected_revision": 0, "script_sha256": "0" * 64},
            )
            assert resp.status_code == 404

    def _new_session_with_snapshot(self, client: TestClient) -> tuple[str, dict, dict]:
        _ensure_session_snapshots(client)
        spec = _load_fixture_spec()
        plugin = _load_fixture_plugin(spec)
        sid = client.post("/api/sessions", json={"factor_id": spec["paper"]["factor_id"]}).json()["session_id"]
        return sid, spec, plugin


def test_artifact_read_rejects_path_traversal():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
        resp = client.get(f"/api/sessions/{sid}/steps/1/artifact/..%2F..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)


def test_artifact_read_rejects_reference_only_steps():
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
        resp = client.get(f"/api/sessions/{sid}/steps/5/artifact/whatever")
        assert resp.status_code == 400


class TestArtifactIdentityChain:
    """step3 -> step4 -> step5, tied together by the script's own sha256."""

    def _new_session_with_snapshot(self, client: TestClient) -> tuple[str, dict, dict]:
        _ensure_session_snapshots(client)
        spec = _load_fixture_spec()
        plugin = _load_fixture_plugin(spec)
        sid = client.post("/api/sessions", json={"factor_id": spec["paper"]["factor_id"]}).json()["session_id"]
        return sid, spec, plugin

    def test_full_chain_matches_golden_numbers(self):
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)

            built = client.post(
                f"/api/sessions/{sid}/steps/3/script",
                json={
                    "expected_revision": 0,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                },
            )
            assert built.status_code == 200, built.text
            sha = built.json()["sha256"]
            rev = built.json()["revision"]

            validated = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={
                    "expected_revision": rev,
                    "spec": spec,
                    "plugin": plugin,
                    "script_sha256": sha,
                },
            )
            assert validated.status_code == 200, validated.text
            validate_job = _poll_job(client, validated.json()["job_id"])
            assert validate_job["status"] == "completed", validate_job.get("error")
            assert validate_job["result"]["report"]["passed"] is True
            rev = validate_job["result"]["revision"]

            executed = client.post(
                f"/api/sessions/{sid}/steps/5/execute",
                json={
                    "expected_revision": rev,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                    "script_sha256": sha,
                },
            )
            assert executed.status_code == 200, executed.text
            job = _poll_job(client, executed.json()["job_id"])
            assert job["status"] == "completed", job.get("error")
            result = job["result"]
            golden = expected_metrics()
            assert result["metrics"]["n_months"] == golden["n_months"]
            assert result["metrics"]["mean_monthly_return"] == pytest.approx(
                golden["mean_monthly_return"], rel=1e-9
            )
            assert result["run_record"]["status"] == "success"
            # Embedded for charting (Phase E) -- one row per rebalance period,
            # with at least the `ls_return`/`yyyymm` columns ReturnChart needs.
            assert isinstance(result["return_series"], list)
            assert len(result["return_series"]) == golden["n_months"]
            assert "yyyymm" in result["return_series"][0]

            manifest = client.get(f"/api/sessions/{sid}").json()
            assert manifest["steps"]["5"]["attempts"][-1]["status"] == "success"

    def test_execute_rejects_script_never_validated(self):
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)
            resp = client.post(
                f"/api/sessions/{sid}/steps/5/execute",
                json={
                    "expected_revision": 0,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                    "script_sha256": "0" * 64,
                },
            )
            assert resp.status_code == 400
            assert "not passed step4 validation" in resp.json()["detail"]

    def test_execute_rejects_hash_mismatch_against_validated_artifact(self):
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)
            built = client.post(
                f"/api/sessions/{sid}/steps/3/script",
                json={
                    "expected_revision": 0,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                },
            ).json()
            sha = built["sha256"]
            rev = built["revision"]
            validate_resp = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={
                    "expected_revision": rev,
                    "spec": spec,
                    "plugin": plugin,
                    "script_sha256": sha,
                },
            )
            validate_job = _poll_job(client, validate_resp.json()["job_id"])
            assert validate_job["status"] == "completed", validate_job.get("error")
            rev = validate_job["result"]["revision"]

            # Attacker-supplied different hash -- must be rejected even though
            # SOME validation succeeded in this session.
            forged_sha = "f" * 64
            resp = client.post(
                f"/api/sessions/{sid}/steps/5/execute",
                json={
                    "expected_revision": rev,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                    "script_sha256": forged_sha,
                },
            )
            assert resp.status_code == 400

    def test_validate_rejects_tampered_artifact_file(self):
        with TestClient(app) as client:
            sid, spec, plugin = self._new_session_with_snapshot(client)
            built = client.post(
                f"/api/sessions/{sid}/steps/3/script",
                json={
                    "expected_revision": 0,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                },
            ).json()
            sha = built["sha256"]

            from backend.sessions import session_store

            step3_dir = session_store.step_dir(sid, 3)
            (step3_dir / f"{sha}.py").write_text("tampered = True\n")

            resp = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={
                    "expected_revision": built["revision"],
                    "spec": spec,
                    "plugin": plugin,
                    "script_sha256": sha,
                },
            )
            assert resp.status_code == 400
            assert "does not match its own filename hash" in resp.json()["detail"]
