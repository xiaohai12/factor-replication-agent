"""Tests for the LLM-assisted and human-override Step2 review passes
(`review_method_spec_with_llm` / `apply_human_status_overrides`). Does not
touch the live v1 `ReviewGate` -- see `test_step2_reviewer.py` for the
rule-based pass these build on.
"""

from __future__ import annotations

import json

from src.infra.models.method_spec import Disposition, EvidenceStatus
from src.steps.step2_reviewer.review import (
    apply_human_status_overrides,
    review_method_spec_with_llm,
)
from tests.test_step2_reviewer import _base_spec


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, payload: dict):
        self._payload = payload
        self.last_messages: list[dict] | None = None

    def create(self, **kwargs):
        self.last_messages = kwargs.get("messages")
        return _FakeResponse(json.dumps(self._payload))


class _FakeChat:
    def __init__(self, payload: dict):
        self.completions = _FakeCompletions(payload)


class _FakeLlmClient:
    def __init__(self, payload: dict):
        self.chat = _FakeChat(payload)


class TestReviewMethodSpecWithLlm:
    def test_llm_can_downgrade_an_unspecified_field_to_clear(self):
        paper = _base_spec()
        paper.timing.formation_rule.status = EvidenceStatus.UNSPECIFIED
        client = _FakeLlmClient(
            {
                "field_assessments": [
                    {
                        "field_path": "timing.formation_rule",
                        "evidence_status": "clear",
                        "reason": "Section 2 states formation happens every June.",
                    }
                ],
                "additional_findings": [],
            }
        )
        review, raw = review_method_spec_with_llm(paper, "paper text...", client)
        assert review.status_overrides["timing.formation_rule"] == EvidenceStatus.CLEAR
        assert not any(f.field_path == "timing.formation_rule" for f in review.findings)
        assert raw["field_assessments"][0]["field_path"] == "timing.formation_rule"

    def test_llm_cannot_invent_a_field_path_outside_the_snapshot(self):
        paper = _base_spec()
        client = _FakeLlmClient(
            {
                "field_assessments": [
                    {"field_path": "signal.formula.expression", "evidence_status": "clear", "reason": "..."}
                ],
                "additional_findings": [],
            }
        )
        review, _raw = review_method_spec_with_llm(paper, "paper text...", client)
        assert review.status_overrides == {}

    def test_llm_additional_finding_is_always_needs_human_confirmation(self):
        paper = _base_spec()
        client = _FakeLlmClient(
            {
                "field_assessments": [],
                "additional_findings": [
                    {"field_path": "portfolio.legs", "reason": "long/short legs look swapped vs Table 1"}
                ],
            }
        )
        review, _raw = review_method_spec_with_llm(paper, "paper text...", client)
        matches = [f for f in review.findings if f.field_path == "portfolio.legs"]
        assert len(matches) == 1
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert matches[0].kind == "inconsistent"

    def test_llm_cannot_touch_capability_blocked_findings(self):
        paper = _base_spec()
        paper.portfolio.weighting.value = "capped_vw_at_5pct"
        client = _FakeLlmClient(
            {
                "field_assessments": [
                    {"field_path": "portfolio.weighting", "evidence_status": "clear", "reason": "paper is clear"}
                ],
                "additional_findings": [],
            }
        )
        review, _raw = review_method_spec_with_llm(paper, "paper text...", client)
        blocked = [f for f in review.findings if f.field_path == "portfolio.weighting" and f.kind == "unsupported"]
        assert len(blocked) == 1
        assert blocked[0].disposition == Disposition.BLOCKED

    def test_prompt_includes_full_spec_beyond_the_snapshot_fields(self):
        paper = _base_spec()
        client = _FakeLlmClient({"field_assessments": [], "additional_findings": []})
        review_method_spec_with_llm(paper, "paper text...", client)
        user_message = client.chat.completions.last_messages[1]["content"]
        # signal.formula is never part of the high-impact snapshot, so its
        # presence proves the full spec (not just fields_json) was sent.
        assert "paper_expression" in user_message
        assert "(AT_t - AT_t-1) / AT_t-1" in user_message

    def test_llm_can_flag_a_field_outside_the_snapshot_as_an_additional_finding(self):
        paper = _base_spec()
        client = _FakeLlmClient(
            {
                "field_assessments": [],
                "additional_findings": [
                    {
                        "field_path": "signal.formula.inputs",
                        "reason": "formula references 'at' but universe filters never mention it",
                    }
                ],
            }
        )
        review, _raw = review_method_spec_with_llm(paper, "paper text...", client)
        matches = [f for f in review.findings if f.field_path == "signal.formula.inputs"]
        assert len(matches) == 1
        assert matches[0].kind == "inconsistent"
        assert matches[0].disposition == Disposition.NEEDS_HUMAN_CONFIRMATION


class TestApplyHumanStatusOverrides:
    def test_human_override_recomputes_disposition_without_llm(self):
        paper = _base_spec()
        paper.universe.description.status = EvidenceStatus.TABLE_ONLY
        review = apply_human_status_overrides(paper, {"universe.description": EvidenceStatus.CLEAR})
        assert review.status_overrides["universe.description"] == EvidenceStatus.CLEAR
        assert not any(f.field_path == "universe.description" for f in review.findings)
