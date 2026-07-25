"""Unit tests for src.steps.step2_reviewer.resolution: applying human
resolution decisions to blocked/ambiguous MethodSpec fields. Extracted from
scripts/resolve_review_blocks.py so the CLI script and the web backend's
`/api/resolve` endpoint share one implementation -- these tests pin that
shared behavior.
"""

from __future__ import annotations

from src.steps.step2_reviewer.resolution import (
    apply_decisions,
    build_decision,
    get_path,
    set_path,
)


def test_get_set_path_plain_dotted_field():
    data = {"portfolio": {"breakpoints": {"source": "unspecified"}}}
    assert get_path(data, "portfolio.breakpoints.source") == "unspecified"

    set_path(data, "portfolio.breakpoints.source", "nyse")
    assert data["portfolio"]["breakpoints"]["source"] == "nyse"


def test_get_set_path_uses_alias():
    # universe.missing_policy.action is aliased to signal.missing_policy.action
    data = {"signal": {"missing_policy": {"action": "unspecified"}}}
    assert get_path(data, "universe.missing_policy.action") == "unspecified"

    set_path(data, "universe.missing_policy.action", "drop")
    assert data["signal"]["missing_policy"]["action"] == "drop"
    # no stray "universe" key should have been created
    assert "universe" not in data


def test_set_path_creates_intermediate_dicts():
    data = {}
    set_path(data, "portfolio.breakpoints.source", "full_sample")
    assert data == {"portfolio": {"breakpoints": {"source": "full_sample"}}}


def test_build_decision_captures_old_and_new_value():
    spec_data = {"portfolio": {"breakpoints": {"source": "unspecified"}}}
    note = {
        "field": "portfolio.breakpoints.source",
        "evidence": [{"location": "Table 2", "quote": "NYSE breakpoints"}],
    }
    decision = build_decision(note, spec_data, "nyse", "cited Table 2", "human")

    assert decision["field_path"] == "portfolio.breakpoints.source"
    assert decision["canonical_field_path"] == "portfolio.breakpoints.source"
    assert decision["old_value"] == "unspecified"
    assert decision["new_value"] == "nyse"
    assert decision["decision_type"] == "human_empirical_assumption"
    assert decision["reason"] == "cited Table 2"
    assert decision["reviewer"] == "human"
    assert decision["paper_evidence"] == note["evidence"]


def test_apply_decisions_writes_value_clears_ambiguous_and_resets_status():
    spec_data = {
        "portfolio": {"breakpoints": {"source": "unspecified"}},
        "ambiguous_fields": [
            {
                "field": "portfolio.breakpoints.source",
                "source": "ambiguous",
                "status": "blocked",
                "confidence": "low",
                "candidate_value": None,
            }
        ],
        "review_status": "approved",
        "codegen_ready": True,
        "paper_faithful": True,
    }
    decision = build_decision(
        {"field": "portfolio.breakpoints.source", "evidence": []},
        spec_data,
        "nyse",
        "cited Table 2",
        "human",
    )

    apply_decisions(spec_data, [decision])

    assert spec_data["portfolio"]["breakpoints"]["source"] == "nyse"

    ambiguous = spec_data["ambiguous_fields"][0]
    assert ambiguous["source"] == "clear"
    assert ambiguous["status"] == "clear"
    assert ambiguous["confidence"] == "high"
    assert ambiguous["candidate_value"] == "nyse"
    assert ambiguous["human_resolution"]["decision_type"] == "human_empirical_assumption"
    assert ambiguous["human_resolution"]["reviewer"] == "human"

    assert spec_data["resolution_log"] == [decision]
    # resolved spec must go back through Review Gate before codegen
    assert spec_data["review_status"] == "pending"
    assert spec_data["codegen_ready"] is False
    assert spec_data["paper_faithful"] is False


def test_apply_decisions_ignores_non_dict_ambiguous_entries():
    spec_data = {
        "signal": {},
        "ambiguous_fields": ["not-a-dict"],
    }
    decision = build_decision(
        {"field": "signal.name", "evidence": []}, spec_data, "value", "reason", "human"
    )

    # Should not raise despite the malformed ambiguous_fields entry.
    apply_decisions(spec_data, [decision])
    assert spec_data["signal"]["name"] == "value"
