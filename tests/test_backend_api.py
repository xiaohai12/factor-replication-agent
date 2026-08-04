"""Integration tests for the FastAPI backend (backend/main.py) using
FastAPI's TestClient. No LLM/network calls: exercises the rules-based
review endpoint, the human-resolution endpoint, and the full
plugin -> backtest job pipeline against the same deterministic synthetic
data used by tests/test_mvp_e2e.py (golden numbers from
tests/synthetic_data/asset_growth_synthetic_data.py), proving the backend
wraps `BacktestRunner`/`EvidenceStore`/`RunRegistry` correctly end-to-end.
"""

from __future__ import annotations

import json
import time
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


def test_extract_from_pdf_uses_extracted_text_and_pdf_bytes(monkeypatch):
    """No real LLM call -- monkeypatches `build_extractor` (same pattern as
    tests/test_session_api.py's TestStep1PdfUpload) so this only exercises
    PDF text extraction + job wiring for the non-session
    `/api/methodspecs/extract-pdf` endpoint."""
    import backend.routers.methodspecs as methodspecs_module
    from src.infra.models.method_spec import MethodSpec, SignalSpec
    from src.steps.step1_extractor import ExtractionResult

    captured: dict = {}

    class _FakeExtractor:
        def extract(self, factor_id, paper_text, pdf_bytes=None, reextract_feedback=None):
            captured["paper_text"] = paper_text
            captured["pdf_bytes"] = pdf_bytes
            return ExtractionResult(
                sources_used=["paper"],
                spec=MethodSpec(factor_id=factor_id, factor_name="Test", signal=SignalSpec()),
            )

    monkeypatch.setattr(methodspecs_module, "build_extractor", lambda client: _FakeExtractor())

    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello from a test PDF")
    pdf_bytes = doc.tobytes()
    doc.close()

    with TestClient(app) as client:
        resp = client.post(
            "/api/methodspecs/extract-pdf",
            data={"factor_id": "factor_a", "llm_provider": "codex"},
            files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200, resp.text
        snapshot = _poll_job(client, resp.json()["job_id"])
        assert snapshot["status"] == "completed", snapshot.get("error")

    assert "Hello from a test PDF" in captured["paper_text"]
    assert captured["pdf_bytes"] is not None


def test_extract_from_pdf_rejects_empty_file():
    with TestClient(app) as client:
        resp = client.post(
            "/api/methodspecs/extract-pdf",
            data={"factor_id": "factor_a"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400


def test_review_endpoint_rules_based():
    spec = _load_fixture_spec()
    with TestClient(app) as client:
        resp = client.post("/api/methodspecs/review", json={"spec": spec})
        assert resp.status_code == 200
        report = resp.json()
        assert report["disposition"] in ("approved", "revision_required", "blocked")


def test_resolve_endpoint_applies_decisions_and_persists_files():
    spec = _load_fixture_spec()
    decisions = [
        {
            "field_path": "portfolio.breakpoints.source",
            "canonical_field_path": "portfolio.breakpoints.source",
            "old_value": spec.get("portfolio", {}).get("breakpoints", {}).get("source"),
            "new_value": "nyse",
            "decision_type": "human_empirical_assumption",
            "reason": "test resolution",
            "reviewer": "test",
            "paper_evidence": [],
        }
    ]
    with TestClient(app) as client:
        resp = client.post(
            "/api/methodspecs/resolve",
            json={"spec": spec, "decisions": decisions, "reviewer": "test"},
        )
        assert resp.status_code == 200
        resolved = resp.json()
        assert resolved["portfolio"]["breakpoints"]["source"] == "nyse"
        assert resolved["codegen_ready"] is False
        assert resolved["review_status"] == "pending"

        factor_id = resolved["factor_id"]
        from backend.state import RESOLUTIONS_DIR, RESOLVED_DIR

        assert (RESOLUTIONS_DIR / f"{factor_id}.resolution.json").exists()
        assert (RESOLVED_DIR / f"{factor_id}.resolved.methodspec.json").exists()


def test_backtest_run_matches_golden_numbers():
    spec = _load_fixture_spec()
    plugin_code = PLUGIN_PATH.read_text(encoding="utf-8")
    plugin = {
        "plugin_id": "cooper_gulen_schill_2008_asset_growth_v1",
        "factor_id": spec["factor_id"],
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
        factor_id = spec["factor_id"]

        runs_resp = client.get(f"/api/runs/{factor_id}")
        assert any(r["run_id"] == run_id for r in runs_resp.json())

        evidence_resp = client.get(f"/api/evidence/{factor_id}/{run_id}")
        assert evidence_resp.status_code == 200
        assert "metadata.json" in evidence_resp.json()["files"]
