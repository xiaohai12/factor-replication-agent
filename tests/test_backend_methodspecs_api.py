"""Integration test for the paper-first API lifecycle
(`backend/routers/methodspecs.py`): deterministic review + resolve
endpoints (no LLM call), proving the paper-first HTTP surface round-trips
through `ResolvedMethodSpec.is_ready` correctly. Extract is not covered here
(LLM call) -- see `MethodSpecExtractor` for that logic, tested without a real
network call would require a fake client wired through `build_llm_client`,
out of scope for this HTTP-level test.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.main import app
from src.infra.models.method_spec import FilterOp, FilterSpec, SourceColumn
from tests.test_meta_coder_resolved_method_spec import _resolved_spec


def test_review_and_resolve_round_trip():
    resolved = _resolved_spec()
    paper_payload = json.loads(resolved.paper.model_dump_json())

    with TestClient(app) as client:
        review_resp = client.post("/api/methodspecs/review", json={"paper": paper_payload})
        assert review_resp.status_code == 200
        review_json = review_resp.json()
        assert review_json["factor_id"] == resolved.paper.factor_id

        resolve_resp = client.post(
            "/api/methodspecs/resolve",
            json={"paper": paper_payload, "review": review_json},
        )
        assert resolve_resp.status_code == 200
        resolve_json = resolve_resp.json()
        assert "resolution" in resolve_json
        assert isinstance(resolve_json["is_ready"], bool)

        listed = client.get("/api/methodspecs/reviews").json()
        assert resolved.paper.factor_id in listed

        loaded = client.get(f"/api/methodspecs/reviews/{resolved.paper.factor_id}").json()
        assert loaded["factor_id"] == resolved.paper.factor_id


def test_unknown_stage_404s():
    with TestClient(app) as client:
        resp = client.get("/api/methodspecs/bogus-stage")
        assert resp.status_code == 404


def test_unsupported_universe_filter_findings_reports_column_and_native_list():
    """docs/resolve-diagnostics-gaps.md problem 1: a universe filter that
    resolves to a physical column the engine's returns panel doesn't supply
    (e.g. a Compustat-only listing-history column) must be surfaced as a
    `Finding`, not just silently fail `is_ready` with no visible reason.
    """
    from backend.routers.methodspecs import _unsupported_universe_filter_findings
    from src.infra.models.method_spec import Disposition, ResolvedMethodSpec

    resolved = _resolved_spec()
    paper = resolved.paper.model_copy(deep=True)
    paper.universe.filters.append(
        FilterSpec(concept_id="listing_history", op=FilterOp.GTE, value=2)
    )
    resolution = resolved.resolution.model_copy(deep=True)
    resolution.concept_mapping["listing_history"] = SourceColumn(source="comp_names", column="ipodate")
    resolved_with_filter = ResolvedMethodSpec(paper=paper, review=resolved.review, resolution=resolution)

    findings = _unsupported_universe_filter_findings(paper, resolution, resolved_with_filter)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == "unsupported"
    assert finding.disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
    assert finding.paper_value == "listing_history"
    assert "ipodate" in finding.reason
    assert "exchcd" in finding.reason  # a native column, listed for contrast
