"""Backend API tests for the step6 C_cz preview endpoints (docs/step6.md
gap #1): the static factor manifest listing and the live cz-config preview
(mocked -- never hits the real network in tests, and never triggers a
backtest)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.main import app
from src.infra.reference import CZReferenceProfile
from tests._spec_test_helpers import minimal_resolved_spec


def _new_session(client: TestClient) -> str:
    return client.post("/api/sessions", json={"factor_id": "AssetGrowth"}).json()["session_id"]


def test_list_cz_factors_returns_the_manifest():
    with TestClient(app) as client:
        resp = client.get("/api/reference/cz-factors")
        assert resp.status_code == 200
        factors = resp.json()["factors"]
        assert {"factor_id": "AssetGrowth", "acronym": "AssetGrowth"} in factors


def test_cz_config_preview_succeeds(monkeypatch):
    profile = CZReferenceProfile(
        acronym="AssetGrowth", mean_return=1.73, t_stat=8.45, sign=-1,
        stock_weight="ew", ls_quantile=0.1, quantile_filter=None,
        portfolio_period=12, start_month=6, sample_start_year=1968, sample_end_year=2003,
    )
    monkeypatch.setattr(
        "backend.routers.replication.fetch_cz_reference_profile_live", lambda acronym: profile
    )
    with TestClient(app) as client:
        sid = _new_session(client)
        resp = client.get(f"/api/sessions/{sid}/steps/6/cz-config", params={"acronym": "AssetGrowth"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["acronym"] == "AssetGrowth"
        assert body["raw"]["stock_weight"] == "ew"
        assert body["config_override"]["weighting_rule"] == "ew"
        assert body["config_override"]["formation_lag_months"] == 1
        assert body["cz_reported"]["t_stat"] == 8.45


def test_cz_config_preview_unknown_acronym_is_404(monkeypatch):
    monkeypatch.setattr(
        "backend.routers.replication.fetch_cz_reference_profile_live", lambda acronym: None
    )
    with TestClient(app) as client:
        sid = _new_session(client)
        resp = client.get(f"/api/sessions/{sid}/steps/6/cz-config", params={"acronym": "NotReal"})
        assert resp.status_code == 404


def test_cz_config_preview_retries_and_gives_up_after_three_attempts(monkeypatch):
    calls = {"n": 0}

    def _always_fails(acronym):
        calls["n"] += 1
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.routers.replication.fetch_cz_reference_profile_live", _always_fails)
    with TestClient(app) as client:
        sid = _new_session(client)
        resp = client.get(f"/api/sessions/{sid}/steps/6/cz-config", params={"acronym": "AssetGrowth"})
        assert resp.status_code == 502
        assert calls["n"] == 3

        events = client.get(f"/api/sessions/{sid}/events").json()
        stages = [e["stage"] for e in events]
        assert stages.count("cz_config_preview") >= 4  # 3 failed attempts + 1 exhausted


def test_cz_config_preview_succeeds_after_transient_failures(monkeypatch):
    profile = CZReferenceProfile(acronym="AssetGrowth", stock_weight="ew")
    calls = {"n": 0}

    def _fails_twice_then_succeeds(acronym):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return profile

    monkeypatch.setattr("backend.routers.replication.fetch_cz_reference_profile_live", _fails_twice_then_succeeds)
    with TestClient(app) as client:
        sid = _new_session(client)
        resp = client.get(f"/api/sessions/{sid}/steps/6/cz-config", params={"acronym": "AssetGrowth"})
        assert resp.status_code == 200
        assert calls["n"] == 3


def test_resolved_configs_returns_original_and_standardized_from_spec_alone():
    # docs/step6.md \u00a71: \u2460/\u2462 previewable straight from `spec`, no plugin/
    # snapshot/run needed -- so all three (\u2460\u2461\u2462) configs can be shown side by
    # side as soon as \u2461 has been queried.
    spec = json.loads(minimal_resolved_spec("t", weighting="ew").model_dump_json())
    with TestClient(app) as client:
        sid = _new_session(client)
        resp = client.post(f"/api/sessions/{sid}/steps/6/resolved-configs", json={"spec": spec})
        assert resp.status_code == 200
        body = resp.json()
        assert body["original_method"]["weighting_rule"] == "ew"
        assert body["standardized_hxz"]["weighting_rule"] == "vw"

