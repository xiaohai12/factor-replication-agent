"""Integration tests for the Session control-plane HTTP surface
(backend/routers/sessions.py) -- Phase 1 of the session-centric UI redesign
(docs/decision-log.md 2026-08-04). Uses the same deterministic synthetic
fixture as tests/test_backend_api.py so the step3->4->5 artifact-identity
chain is verified against real golden numbers, not just fakes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.synthetic_data.asset_growth_synthetic_data import expected_metrics

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVED_SPEC_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "method_specs"
    / "cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json"
)
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"


def _load_fixture_spec() -> dict:
    return json.loads(RESOLVED_SPEC_PATH.read_text(encoding="utf-8"))


def _load_fixture_plugin(spec: dict) -> dict:
    return {
        "plugin_id": f"{spec['factor_id']}_v1",
        "factor_id": spec["factor_id"],
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
        assert step3["contract"]["output_refs"] == ["plugin_ref", "script_ref", "script_sha256"]


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
            rev = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={"expected_revision": rev, "spec": spec, "plugin": plugin, "script_sha256": sha},
            ).json()["revision"]
            executed = client.post(
                f"/api/sessions/{sid}/steps/5/execute",
                json={
                    "expected_revision": rev, "spec": spec, "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1", "script_sha256": sha,
                },
            ).json()
            run_id = executed["run_record"]["run_id"]
            factor_id = spec["factor_id"]

            manifest = client.get(f"/api/sessions/{sid}").json()
            resp = client.request(
                "DELETE", f"/api/sessions/{sid}", json={"expected_revision": manifest["revision"], "confirm": True}
            )
            assert resp.status_code == 200

            evidence_resp = client.get(f"/api/evidence/{factor_id}/{run_id}")
            assert evidence_resp.status_code == 200
            assert "metadata.json" in evidence_resp.json()["files"]

    def _new_session_with_snapshot(self, client: TestClient) -> tuple[str, dict, dict]:
        client.get("/api/backtest/snapshots")
        spec = _load_fixture_spec()
        plugin = _load_fixture_plugin(spec)
        sid = client.post("/api/sessions", json={"factor_id": spec["factor_id"]}).json()["session_id"]
        return sid, spec, plugin


class TestStep1PdfUpload:
    """No real LLM call -- monkeypatches `build_extractor` with a fake whose
    `.extract()` returns a canned result, so this only exercises the PDF
    text extraction + job/session wiring, not the LLM prompt itself."""

    def _fake_build_extractor(self, monkeypatch, captured: dict):
        import backend.routers.sessions as sessions_module
        from src.infra.models.method_spec import MethodSpec, SignalSpec
        from src.steps.step1_extractor import ExtractionResult

        class _FakeExtractor:
            def extract(self, factor_id, paper_text, pdf_bytes=None, reextract_feedback=None):
                captured["paper_text"] = paper_text
                captured["pdf_bytes"] = pdf_bytes
                return ExtractionResult(
                    sources_used=["paper"],
                    spec=MethodSpec(factor_id=factor_id, factor_name="Test", signal=SignalSpec()),
                )

        monkeypatch.setattr(sessions_module, "build_extractor", lambda client: _FakeExtractor())

    def _minimal_pdf_bytes(self) -> bytes:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello from a test PDF")
        data = doc.tobytes()
        doc.close()
        return data

    def test_upload_extracts_text_and_completes_the_job(self, monkeypatch):
        captured: dict = {}
        self._fake_build_extractor(monkeypatch, captured)
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
            resp = client.post(
                f"/api/sessions/{sid}/steps/1/extract-pdf",
                data={"expected_revision": "0", "llm_provider": "codex"},
                files={"file": ("paper.pdf", self._minimal_pdf_bytes(), "application/pdf")},
            )
            assert resp.status_code == 200, resp.text
            job_id = resp.json()["job_id"]

            import time

            deadline = time.time() + 10
            while time.time() < deadline:
                snapshot = client.get(f"/api/jobs/{job_id}").json()
                if snapshot["status"] in ("completed", "failed"):
                    break
                time.sleep(0.05)
            assert snapshot["status"] == "completed", snapshot.get("error")

            assert "Hello from a test PDF" in captured["paper_text"]
            assert captured["pdf_bytes"] is not None

            manifest = client.get(f"/api/sessions/{sid}").json()
            assert manifest["steps"]["1"]["attempts"][-1]["status"] == "success"

    def test_empty_file_is_rejected(self, monkeypatch):
        self._fake_build_extractor(monkeypatch, {})
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
            resp = client.post(
                f"/api/sessions/{sid}/steps/1/extract-pdf",
                data={"expected_revision": "0"},
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
            assert resp.status_code == 400


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
        client.get("/api/backtest/snapshots")  # ensures synthetic_demo_v1 is registered
        spec = _load_fixture_spec()
        plugin = _load_fixture_plugin(spec)
        sid = client.post("/api/sessions", json={"factor_id": spec["factor_id"]}).json()["session_id"]
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
            assert validated.json()["report"]["passed"] is True
            rev = validated.json()["revision"]

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
            result = executed.json()
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
            rev = client.post(
                f"/api/sessions/{sid}/steps/4/validate",
                json={
                    "expected_revision": rev,
                    "spec": spec,
                    "plugin": plugin,
                    "script_sha256": sha,
                },
            ).json()["revision"]

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
