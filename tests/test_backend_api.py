"""Integration tests for the FastAPI backend (backend/main.py) using
FastAPI's TestClient. No LLM/network calls: exercises the data-catalog
endpoint and the full plugin -> backtest job pipeline against the same
deterministic synthetic data used by tests/test_mvp_e2e.py (golden numbers
from tests/synthetic_data/asset_growth_synthetic_data.py), proving the
backend wraps `BacktestRunner`/`EvidenceStore`/`RunRegistry` correctly
end-to-end. The paper-first extract/review/resolve lifecycle has its own
test file (test_backend_paper_methodspecs_api.py).
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


def test_health():
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_data_catalog_endpoint_lists_registered_sources_and_universes():
    """`GET /api/data-catalog`: every registered signal source/link
    table/returns universe, sourced straight from `catalog.py`/`sources.py`."""
    with TestClient(app) as client:
        resp = client.get("/api/data-catalog")
        assert resp.status_code == 200
        body = resp.json()

        assert "crsp_msf" in body["signal_sources"]
        assert "comp_funda" in body["signal_sources"]
        comp_funda = body["signal_sources"]["comp_funda"]
        assert comp_funda["join"]["link"] == "ccm"
        assert "at" in comp_funda["physical_columns"]

        assert "ccm" in body["link_tables"]

        assert body["returns_universes"]["us_equity_crsp"]["returns_table"] == "crsp_msf"
        assert body["default_returns_universe"] == "us_equity_crsp"


def test_backtest_run_matches_golden_numbers():
    resolved = asset_growth_resolved_spec()
    spec = json.loads(resolved.model_dump_json())
    plugin_code = PLUGIN_PATH.read_text(encoding="utf-8")
    plugin = {
        "plugin_id": "cooper_gulen_schill_2008_asset_growth_resolved",
        "factor_id": resolved.paper.factor_id,
        "code": plugin_code,
        "code_hash": "synthetic",
    }

    with TestClient(app) as client:
        snapshots = client.get("/api/backtest/snapshots").json()
        snapshot_ids = [s["snapshot_id"] for s in snapshots]
        assert "synthetic_demo_v1" in snapshot_ids

        resp = client.post(
            "/api/backtest/run",
            json={
                "spec": spec,
                "plugin": plugin,
                "snapshot_id": "synthetic_demo_v1",
            },
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        snapshot = _poll_job(client, job_id)
        assert snapshot["status"] == "completed", snapshot.get("error")

        result = snapshot["result"]
        golden = expected_metrics()
        assert result["metrics"]["n_months"] == golden["n_months"]
        assert result["metrics"]["mean_monthly_return"] == pytest.approx(
            golden["mean_monthly_return"], rel=1e-9
        )
        assert result["metrics"]["t_stat"] == pytest.approx(golden["t_stat"], rel=1e-9)
        assert result["run_record"]["status"] == "success"

        run_id = result["run_record"]["run_id"]
        factor_id = resolved.paper.factor_id

        runs_resp = client.get(f"/api/runs/{factor_id}")
        assert any(r["run_id"] == run_id for r in runs_resp.json())

        evidence_resp = client.get(f"/api/evidence/{factor_id}/{run_id}")
        assert evidence_resp.status_code == 200
        assert "metadata.json" in evidence_resp.json()["files"]
