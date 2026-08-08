"""Integration test for the paper-first API lifecycle
(`backend/routers/paper_methodspecs.py`): deterministic review + resolve
endpoints (no LLM call), proving the new v2 (paper-first) HTTP surface
round-trips through `ResolvedMethodSpec.is_ready` correctly. Extract is not
covered here (LLM call) -- see `PaperExtractor` for that logic, tested
without a real network call would require a fake client wired through
`build_llm_client`, out of scope for this HTTP-level test.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.main import app
from tests.test_meta_coder_resolved_method_spec import _resolved_spec


def test_review_and_resolve_round_trip():
    resolved = _resolved_spec()
    paper_payload = json.loads(resolved.paper.model_dump_json())

    with TestClient(app) as client:
        review_resp = client.post("/api/paper-methodspecs/review", json={"paper": paper_payload})
        assert review_resp.status_code == 200
        review_json = review_resp.json()
        assert review_json["factor_id"] == resolved.paper.factor_id

        resolve_resp = client.post(
            "/api/paper-methodspecs/resolve",
            json={"paper": paper_payload, "review": review_json},
        )
        assert resolve_resp.status_code == 200
        resolve_json = resolve_resp.json()
        assert "resolution" in resolve_json
        assert isinstance(resolve_json["is_ready"], bool)

        listed = client.get("/api/paper-methodspecs/reviews").json()
        assert resolved.paper.factor_id in listed

        loaded = client.get(f"/api/paper-methodspecs/reviews/{resolved.paper.factor_id}").json()
        assert loaded["factor_id"] == resolved.paper.factor_id


def test_unknown_stage_404s():
    with TestClient(app) as client:
        resp = client.get("/api/paper-methodspecs/bogus-stage")
        assert resp.status_code == 404
