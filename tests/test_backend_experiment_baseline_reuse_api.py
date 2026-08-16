"""Backend router test: step6's `/steps/6/experiment` endpoint looks up
step5's latest successful `original_method` RunRecord and passes it to
`MultiTrackController.run_experiment` as `reuse_original_run` -- the
controller itself decides (via `_reusable_baseline_error`) whether it's
actually safe to reuse; this only checks the router resolves and forwards
the right candidate (or `None` when there isn't one)."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from backend.main import app
from backend.sessions import complete_attempt_with_retry, session_store
from backend.state import pipeline
from src.infra.models.run_record import RunMetrics, RunRecord
from src.infra.models.session import StepStatus
from tests._spec_test_helpers import minimal_resolved_spec


def _poll_job(client: TestClient, job_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        snapshot = resp.json()
        if snapshot["status"] in ("completed", "failed"):
            return snapshot
        time.sleep(0.05)
    raise TimeoutError(f"job did not finish within {timeout_s}s")


def _minimal_request_body():
    spec = json.loads(minimal_resolved_spec("AssetGrowth").model_dump_json())
    return {
        "expected_revision": 0,
        "spec": spec,
        "plugin": {"plugin_id": "p", "factor_id": "AssetGrowth", "code": "x", "code_hash": "h"},
        "snapshot_id": "snap1",
        "run_original": True,
        "run_standardized": False,
    }


def test_reuse_candidate_resolved_from_a_successful_step5_attempt(monkeypatch):
    captured = {}

    def fake_run_experiment(plugin, spec, plan, snapshot_id, reuse_original_run=None):
        captured["reuse_original_run"] = reuse_original_run
        return []

    monkeypatch.setattr(pipeline.controller, "run_experiment", fake_run_experiment)

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "AssetGrowth"}).json()["session_id"]

        prior_run = RunRecord(
            run_id="prior_run_1", factor_id="AssetGrowth", plugin_id="p", track="original_method",
            metrics=RunMetrics(mean_return=0.01, t_stat=2.0), status="success",
        )
        pipeline.run_registry.register(prior_run)

        session_store.start_attempt(sid, 0, step=5, job_id="fake-job")
        complete_attempt_with_retry(
            sid, step=5, status=StepStatus.SUCCESS,
            output_refs={"execution_ids": '["prior_run_1"]'},
        )

        req = _minimal_request_body()
        req["expected_revision"] = session_store.get(sid).revision
        resp = client.post(f"/api/sessions/{sid}/steps/6/experiment", json=req)
        assert resp.status_code == 200
        _poll_job(client, resp.json()["job_id"])

    assert captured["reuse_original_run"] is not None
    assert captured["reuse_original_run"].run_id == "prior_run_1"


def test_no_reuse_candidate_when_step5_never_ran(monkeypatch):
    captured = {}

    def fake_run_experiment(plugin, spec, plan, snapshot_id, reuse_original_run=None):
        captured["reuse_original_run"] = reuse_original_run
        return []

    monkeypatch.setattr(pipeline.controller, "run_experiment", fake_run_experiment)

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "AssetGrowth"}).json()["session_id"]
        req = _minimal_request_body()
        req["expected_revision"] = session_store.get(sid).revision
        resp = client.post(f"/api/sessions/{sid}/steps/6/experiment", json=req)
        assert resp.status_code == 200
        _poll_job(client, resp.json()["job_id"])

    assert captured["reuse_original_run"] is None


def test_no_reuse_candidate_when_run_original_is_false(monkeypatch):
    captured = {}

    def fake_run_experiment(plugin, spec, plan, snapshot_id, reuse_original_run=None):
        captured["reuse_original_run"] = reuse_original_run
        return []

    monkeypatch.setattr(pipeline.controller, "run_experiment", fake_run_experiment)

    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"factor_id": "AssetGrowth"}).json()["session_id"]

        prior_run = RunRecord(
            run_id="prior_run_2", factor_id="AssetGrowth", plugin_id="p", track="original_method",
            metrics=RunMetrics(), status="success",
        )
        pipeline.run_registry.register(prior_run)
        session_store.start_attempt(sid, 0, step=5, job_id="fake-job")
        complete_attempt_with_retry(
            sid, step=5, status=StepStatus.SUCCESS, output_refs={"execution_ids": '["prior_run_2"]'},
        )

        req = _minimal_request_body()
        req["run_original"] = False
        req["expected_revision"] = session_store.get(sid).revision
        resp = client.post(f"/api/sessions/{sid}/steps/6/experiment", json=req)
        assert resp.status_code == 200
        _poll_job(client, resp.json()["job_id"])

    assert captured["reuse_original_run"] is None
