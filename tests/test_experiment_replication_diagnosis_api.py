"""Integration tests for the step6/7/8 session endpoints
(backend/routers/experiments.py, replication.py, diagnosis.py). Runs a real
(fast) single-track experiment against the same deterministic synthetic
fixture as tests/test_backend_api.py / tests/test_session_api.py, so step7's
comparison validation and step8's diagnosis run against a REAL
`comparison.json`, not a hand-built fake -- only the step8 LLM call itself
is faked (FakeLLM, same pattern as tests/test_replication_diagnosis.py).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from tests.test_replication_diagnosis import FakeLLM

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


def _poll_job(client: TestClient, job_id: str, timeout_s: float = 60.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        snapshot = resp.json()
        if snapshot["status"] in ("completed", "failed"):
            return snapshot
        time.sleep(0.2)
    raise TimeoutError(f"Job '{job_id}' did not finish within {timeout_s}s")


def _run_baseline_only_experiment(client: TestClient, factor_id_suffix: str = "") -> tuple[str, dict, str]:
    """Creates a session and runs JUST the `original_method` track (fast --
    no standardized/ablation tracks) so step7/8 tests have a real batch to
    work with without paying for a multi-track subprocess run each time.

    `factor_id_suffix`, when given, produces a run under a DIFFERENT
    `factor_id` (still against the same underlying synthetic data) so its
    `run_id`/`execution_id` -- deterministic from
    `(factor_id, track, code_hash, config_hash)`, see
    `BacktestRunner.build_script` -- can never collide with a plain call's
    run_id, which some tests need (two GENUINELY distinct batches, not one
    overwriting the other in `RunRegistry`).
    """
    client.get("/api/backtest/snapshots")  # ensures synthetic_demo_v1 is registered
    spec = _load_fixture_spec()
    if factor_id_suffix:
        spec["factor_id"] = f"{spec['factor_id']}{factor_id_suffix}"
    plugin = _load_fixture_plugin(spec)
    sid = client.post("/api/sessions", json={"factor_id": spec["factor_id"]}).json()["session_id"]

    resp = client.post(
        f"/api/sessions/{sid}/steps/6/experiment",
        json={
            "expected_revision": 0,
            "spec": spec,
            "plugin": plugin,
            "snapshot_id": "synthetic_demo_v1",
            "run_original": True,
            "run_standardized": False,
            "ablation_switches": [],
            "factorial_switches": [],
        },
    )
    assert resp.status_code == 200, resp.text
    snapshot = _poll_job(client, resp.json()["job_id"])
    assert snapshot["status"] == "completed", snapshot.get("error")
    batch_id = snapshot["result"]["experiment_batch_id"]
    assert snapshot["result"]["batch_invalidated"] is False
    return sid, spec, batch_id


class TestStep6Experiment:
    def test_experiment_batch_recorded_on_session(self):
        with TestClient(app) as client:
            sid, _spec, batch_id = _run_baseline_only_experiment(client)
            manifest = client.get(f"/api/sessions/{sid}").json()
            attempt = manifest["steps"]["6"]["attempts"][-1]
            assert attempt["status"] == "success"
            assert attempt["output_refs"]["experiment_batch_id"] == batch_id
            execution_ids = json.loads(attempt["output_refs"]["execution_ids"])
            assert len(execution_ids) == 1


class TestStep7Comparison:
    def test_comparison_recorded_from_batch_id(self):
        with TestClient(app) as client:
            sid, spec, batch_id = _run_baseline_only_experiment(client)
            resp = client.post(
                f"/api/sessions/{sid}/steps/7/comparison",
                json={"expected_revision": 2, "experiment_batch_id": batch_id},
            )
            assert resp.status_code == 200, resp.text
            bundle = resp.json()["bundle"]
            assert bundle["factor_id"] == spec["factor_id"]
            assert bundle["batch"]["experiment_batch_id"] == batch_id

            # And the convenience GET returns the same recorded bundle.
            got = client.get(f"/api/sessions/{sid}/steps/7/comparison")
            assert got.status_code == 200
            assert got.json()["batch"]["experiment_batch_id"] == batch_id

    def test_unknown_batch_id_is_rejected(self):
        with TestClient(app) as client:
            sid, _, _ = _run_baseline_only_experiment(client)
            resp = client.post(
                f"/api/sessions/{sid}/steps/7/comparison",
                json={"expected_revision": 2, "experiment_batch_id": "does-not-exist"},
            )
            assert resp.status_code == 404

    def test_execution_ids_spanning_two_batches_is_rejected(self):
        with TestClient(app) as client:
            sid1, _spec, batch_id_1 = _run_baseline_only_experiment(client)
            manifest1 = client.get(f"/api/sessions/{sid1}").json()
            exec_ids_1 = json.loads(manifest1["steps"]["6"]["attempts"][-1]["output_refs"]["execution_ids"])

            # A DIFFERENT factor_id -- guarantees a genuinely different
            # run_id/batch_id, not just a second call that could otherwise
            # collide on an identical (factor,track,code_hash,config_hash)
            # run_id and silently overwrite the first batch's registry entry.
            sid2, _, batch_id_2 = _run_baseline_only_experiment(client, factor_id_suffix="_variant_a")
            manifest2 = client.get(f"/api/sessions/{sid2}").json()
            exec_ids_2 = json.loads(manifest2["steps"]["6"]["attempts"][-1]["output_refs"]["execution_ids"])
            assert batch_id_1 != batch_id_2

            resp = client.post(
                f"/api/sessions/{sid1}/steps/7/comparison",
                json={"expected_revision": 2, "execution_ids": exec_ids_1 + exec_ids_2},
            )
            assert resp.status_code == 400
            assert "more than one experiment_batch_id" in resp.json()["detail"]

    def test_stale_comparison_on_disk_is_rejected_not_silently_served(self):
        """comparison.json is overwritten per-factor (not versioned per
        batch): once a SECOND batch for the same factor runs, requesting the
        FIRST batch's (now-superseded) comparison must fail loudly rather
        than silently return the wrong batch's numbers."""
        with TestClient(app) as client:
            sid, spec, first_batch_id = _run_baseline_only_experiment(client)
            # Run a SECOND, differently-CONFIGURED experiment for the SAME
            # factor (an ablation track instead of plain original_method) --
            # a distinct config_hash means a distinct run_id, so the first
            # batch's RunRecord survives in RunRegistry untouched, while
            # `comparison.json` on disk (keyed only by factor_id) gets
            # overwritten with the second batch's contents.
            plugin = _load_fixture_plugin(spec)
            resp = client.post(
                f"/api/sessions/{sid}/steps/6/experiment",
                json={
                    "expected_revision": 2,
                    "spec": spec,
                    "plugin": plugin,
                    "snapshot_id": "synthetic_demo_v1",
                    "run_original": False,
                    "run_standardized": False,
                    "ablation_switches": ["breakpoint"],
                },
            )
            snapshot = _poll_job(client, resp.json()["job_id"])
            assert snapshot["status"] == "completed", snapshot.get("error")
            second_batch_id = snapshot["result"]["experiment_batch_id"]
            assert second_batch_id != first_batch_id

            stale_resp = client.post(
                f"/api/sessions/{sid}/steps/7/comparison",
                json={"expected_revision": 4, "experiment_batch_id": first_batch_id},
            )
            assert stale_resp.status_code == 409
            assert "overwritten" in stale_resp.json()["detail"] or "not versioned" in stale_resp.json()["detail"]


class TestStep8Diagnosis:
    def test_diagnosis_runs_over_recorded_comparison(self, monkeypatch):
        with TestClient(app) as client:
            sid, _spec, batch_id = _run_baseline_only_experiment(client)
            comparison_resp = client.post(
                f"/api/sessions/{sid}/steps/7/comparison",
                json={"expected_revision": 2, "experiment_batch_id": batch_id},
            )
            assert comparison_resp.status_code == 200

            import backend.routers.diagnosis as diagnosis_module

            monkeypatch.setattr(
                diagnosis_module, "build_llm_client", lambda provider, model: FakeLLM({"claims": []})
            )

            resp = client.post(
                f"/api/sessions/{sid}/steps/8/diagnosis",
                json={"expected_revision": 4, "llm_provider": "codex"},
            )
            assert resp.status_code == 200, resp.text
            snapshot = _poll_job(client, resp.json()["job_id"])
            assert snapshot["status"] == "completed", snapshot.get("error")
            assert snapshot["result"]["report"]["status"] == "llm_assisted_proposal"

            manifest = client.get(f"/api/sessions/{sid}").json()
            assert manifest["steps"]["8"]["attempts"][-1]["status"] == "success"
            assert Path(manifest["steps"]["8"]["attempts"][-1]["output_refs"]["diagnosis_ref"]).is_file()

            # GET reads back the same persisted diagnosis.json, without recomputing.
            got = client.get(f"/api/sessions/{sid}/steps/8/diagnosis")
            assert got.status_code == 200
            assert got.json()["status"] == "llm_assisted_proposal"

    def test_get_diagnosis_404s_before_any_diagnosis_recorded(self):
        with TestClient(app) as client:
            sid, _, _ = _run_baseline_only_experiment(client)
            resp = client.get(f"/api/sessions/{sid}/steps/8/diagnosis")
            assert resp.status_code == 404

    def test_diagnosis_requires_a_recorded_comparison_first(self):
        with TestClient(app) as client:
            sid, _, _ = _run_baseline_only_experiment(client)
            resp = client.post(
                f"/api/sessions/{sid}/steps/8/diagnosis",
                json={"expected_revision": 2},
            )
            assert resp.status_code == 400

    def test_diagnosis_failure_never_touches_step7_success_status(self, monkeypatch):
        with TestClient(app) as client:
            sid, _spec, batch_id = _run_baseline_only_experiment(client)
            client.post(
                f"/api/sessions/{sid}/steps/7/comparison",
                json={"expected_revision": 2, "experiment_batch_id": batch_id},
            )

            import backend.routers.diagnosis as diagnosis_module

            class _ExplodingLLM:
                @property
                def chat(self):
                    raise RuntimeError("simulated LLM outage")

            monkeypatch.setattr(diagnosis_module, "build_llm_client", lambda provider, model: _ExplodingLLM())

            resp = client.post(
                f"/api/sessions/{sid}/steps/8/diagnosis",
                json={"expected_revision": 4},
            )
            assert resp.status_code == 200  # job accepted; failure surfaces inside the job
            snapshot = _poll_job(client, resp.json()["job_id"])
            assert snapshot["status"] == "failed"

            manifest = client.get(f"/api/sessions/{sid}").json()
            assert manifest["steps"]["8"]["attempts"][-1]["status"] == "failed"
            assert manifest["steps"]["7"]["attempts"][-1]["status"] == "success"
