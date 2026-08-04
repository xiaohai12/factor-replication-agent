"""Tests for the isolated extraction-evaluation endpoint
(backend/routers/evaluations.py) -- no `session_id` anywhere, confirming it
never touches session state, plus the new step1/step2 session endpoints and
the session diagnostics aggregate endpoint (src/evaluation/diagnostics.py
wiring, Phase 3 of the session-centric UI redesign).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVED_SPEC_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "method_specs"
    / "cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json"
)


def _load_fixture_spec() -> dict:
    return json.loads(RESOLVED_SPEC_PATH.read_text(encoding="utf-8"))


class TestEvaluationsExtraction:
    def test_scores_against_curated_reference(self):
        with TestClient(app) as client:
            spec = _load_fixture_spec()
            resp = client.post(
                "/api/evaluations/extraction",
                json={"factor_id": "AssetGrowth", "spec": spec, "protocol": "human_labeled_v1"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["protocol"] == "human_labeled_v1"
            assert 0.0 <= body["metrics"]["field_accuracy"] <= 1.0
            assert len(body["field_details"]) == body["metrics"]["total"]

    def test_unknown_factor_id_404s(self):
        with TestClient(app) as client:
            resp = client.post(
                "/api/evaluations/extraction",
                json={"factor_id": "does_not_exist_at_all", "spec": {}},
            )
            assert resp.status_code == 404

    def test_unsupported_protocol_rejected(self):
        with TestClient(app) as client:
            resp = client.post(
                "/api/evaluations/extraction",
                json={"factor_id": "AssetGrowth", "spec": {}, "protocol": "signaldoc_v1"},
            )
            assert resp.status_code == 400


class TestStep1Step2SessionEndpoints:
    def test_step2_review_records_diagnostics(self):
        with TestClient(app) as client:
            spec = _load_fixture_spec()
            sid = client.post("/api/sessions", json={"factor_id": spec["factor_id"]}).json()["session_id"]
            resp = client.post(
                f"/api/sessions/{sid}/steps/2/review",
                json={"expected_revision": 0, "spec": spec},
            )
            assert resp.status_code == 200, resp.text
            assert "readiness" in resp.json()["diagnostics"]

            manifest = client.get(f"/api/sessions/{sid}").json()
            attempt = manifest["steps"]["2"]["attempts"][-1]
            assert attempt["diagnostics"]["readiness"] in ("ready", "not_ready", "blocked")
            assert "review_report_ref" in attempt["output_refs"]

    def test_session_diagnostics_aggregate_endpoint(self):
        with TestClient(app) as client:
            spec = _load_fixture_spec()
            sid = client.post("/api/sessions", json={"factor_id": spec["factor_id"]}).json()["session_id"]
            client.post(
                f"/api/sessions/{sid}/steps/2/review",
                json={"expected_revision": 0, "spec": spec},
            )
            diag = client.get(f"/api/sessions/{sid}/diagnostics").json()
            assert "2" in diag
            assert "readiness" in diag["2"]
            # step1 was never run in this session -- must not appear.
            assert "1" not in diag

    def test_diagnostics_endpoint_empty_for_fresh_session(self):
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"factor_id": "factor_a"}).json()["session_id"]
            diag = client.get(f"/api/sessions/{sid}/diagnostics").json()
            assert diag == {}
