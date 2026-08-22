"""Tests for the Step2 LLM review loop (`spec_build.build_reviewed_method_spec`).

2026-08-11: replaced the earlier "only merge explicitly declared fields"
guardrail with a full-trust model -- the LLM's entire rewritten spec takes
effect directly each round (except `factor_id`/`schema_version`/
`paper.document_id`, D7, always re-injected deterministically). A
mechanical before/after diff (`ReviewRound.diff`/`SpecBuildOutcome.
total_diff`) is the new safety mechanism: nothing is silently discarded,
everything the LLM changes is visible. See docs/decision-log.md.
"""

from __future__ import annotations

import json

from src.infra.models.method_spec import MethodSpec
from src.steps.step2_reviewer.spec_build import (
    build_reviewed_method_spec,
)


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
    """Returns each payload in `payloads` in turn (one per LLM call);
    repeats the last payload if more calls happen than payloads supplied."""

    def __init__(self, payloads: list[dict]):
        self._payloads = payloads
        self.calls: list[list[dict]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs.get("messages"))
        idx = min(len(self.calls) - 1, len(self._payloads) - 1)
        return _FakeResponse(json.dumps(self._payloads[idx]))


class _FakeChat:
    def __init__(self, payloads: list[dict]):
        self.completions = _FakeCompletions(payloads)


class _FakeLlmClient:
    def __init__(self, payloads: list[dict]):
        self.chat = _FakeChat(payloads)
        self.completions = self.chat.completions


def _minimal_raw_spec(**overrides) -> dict:
    """A raw dict shaped like Step1's output, already validate-clean except
    for whatever `overrides` intentionally breaks -- lets tests target one
    failure mode at a time without re-typing the whole schema."""
    spec = {
        "paper": {"title": "Asset Growth...", "citation": "Cooper et al 2008"},
        "signal": {
            "definition": {"value": "(AT_t - AT_t-1) / AT_t-1", "evidence": [], "status": "clear"},
            "economic_intuition": {"value": "overinvestment", "evidence": [], "status": "clear"},
            "direction": {"value": "negative", "evidence": [], "status": "clear"},
            "category": "continuous",
            "formula": {
                "paper_expression": "(AT_t - AT_t-1) / AT_t-1",
                "steps": [],
                "inputs": ["at"],
                "constants": {},
                "output_concept": "asset_growth",
                "evidence": [],
            },
            "estimation": None,
        },
        "data": {
            "signal_frequency": {"value": "year", "evidence": [], "status": "clear"},
            "return_frequency": {"value": "month", "evidence": [], "status": "clear"},
            "sources": [],
            "fields": [
                {
                    "concept_id": "at", "name_in_paper": "total assets",
                    "paper_source_hint": "Compustat annual", "roles": ["signal_input"], "evidence": [],
                    "source_table": {"value": "compustat_fundamental_annual", "evidence": [], "status": "clear"},
                    "source_column": {"value": "at", "evidence": [], "status": "clear"},
                }
            ],
            "coverage_notes": [],
        },
        "sample": {
            "data_coverage": {"start_year": 1962, "end_year": 2004},
            "formation": {"start_year": 1968, "end_year": 2003},
            # end_year=2004, NOT 2003: identical to `formation` would trip
            # `_reported_returns_holding_period_mismatch_finding` given the
            # 12-month holding_period below (see docs/decision-log.md
            # 2026-08-22) -- this fixture is meant to already validate clean.
            "reported_returns": {"start_year": 1968, "end_year": 2004},
        },
        "timing": {
            "formation_rule": {"value": "every June", "evidence": [], "status": "clear"},
            "rebalance_frequency": {"value": "year", "evidence": [], "status": "clear"},
            "holding_period": {"value": 12, "evidence": [], "status": "clear"},
            "data_availability": {"lag_value": 6, "lag_unit": "month", "anchor": "fiscal_period_end", "basis": "fixed_calendar_lag"},
        },
        "universe": {"description": {"value": "NYSE/AMEX/NASDAQ", "evidence": [], "status": "clear"}, "filters": []},
        "portfolio": {
            "construction_type": {"value": "characteristic_sort", "evidence": [], "status": "clear"},
            "sorts": [
                {
                    "sort_id": "sort1", "concept_id": "at", "role": "target", "order": 1,
                    "mode": {"value": "independent", "evidence": [], "status": "clear"},
                    "group_type": {"value": "quantile", "evidence": [], "status": "clear"},
                    "group_count": 10,
                    "breakpoints": {"basis": {"value": "nyse", "evidence": [], "status": "clear"}, "values": []},
                }
            ],
            "legs": [
                {"leg_id": "long", "side": "long", "selector": {"sort1": 0}},
                {"leg_id": "short", "side": "short", "selector": {"sort1": 9}},
            ],
            "weighting": {"value": "vw", "evidence": [], "status": "clear"},
            "return_combination": {"value": "extreme_group_spread", "evidence": [], "status": "clear"},
        },
        "reported_results": {
            "primary_metric_id": "m1",
            "metrics": [
                {
                    "metric_id": "m1", "label": "L-H spread", "estimand": "spread",
                    "adjustment_model": "raw", "estimate": 0.0045, "unit": "decimal",
                    "frequency": "month", "statistic": {"kind": "t_stat", "value": 3.2},
                    "sample_period": {"start_year": 1968, "end_year": 2003},
                    "status": "table_only",
                    "evidence": [{"table_ref": {"table": "Table 3", "row": "L-H"}}],
                }
            ],
        },
    }
    spec.update(overrides)
    return spec


class TestDeterministicInjection:
    def test_factor_id_schema_version_document_id_injected_before_first_validate(self):
        raw = _minimal_raw_spec()
        client = _FakeLlmClient([{"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []}])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.factor_id == MethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert outcome.spec.schema_version == "methodspec.v2"
        assert outcome.spec.paper.document_id == "cooper2008"

    def test_llm_supplied_factor_id_is_ignored(self):
        raw = _minimal_raw_spec()
        llm_spec = dict(raw)
        llm_spec["factor_id"] = "llm_invented_id"
        client = _FakeLlmClient([{"spec": llm_spec, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []}])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.factor_id != "llm_invented_id"

    def test_llm_supplied_factor_id_ignored_on_a_later_round_too(self):
        """D7 re-injection isn't a one-time round-1 special case -- it must
        happen every round, since the LLM sees its own previous output
        (with the real injected ID) and could plausibly echo/mutate it."""
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6  # forces at least 2 rounds
        fixed = dict(raw)
        fixed["timing"] = dict(raw["timing"])
        fixed["timing"]["formation_month"] = {"value": 6, "evidence": [], "status": "unspecified"}
        fixed["factor_id"] = "llm_invented_id_round2"
        client = _FakeLlmClient([
            {"spec": fixed, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.spec is not None
        assert outcome.spec.factor_id == MethodSpec.make_factor_id("cooper2008", "asset_growth")


class TestLoopConvergence:
    def test_converges_on_first_round_when_raw_already_validates(self):
        raw = _minimal_raw_spec()
        client = _FakeLlmClient([{"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []}])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.error is None
        assert outcome.spec is not None
        assert len(outcome.history) == 1
        assert outcome.history[0].error_log == ""
        assert outcome.history[0].diff == []
        assert outcome.total_diff == []

    def test_structural_fix_is_trusted_directly_and_the_loop_converges(self):
        """2026-08-11 fix: under the old "only merge declared fields"
        guardrail, a correct structural fix to a non-menu field
        (`formation_month`) was discarded and the loop always exhausted its
        budget (see the old test this replaces). Under the full-trust
        model, the LLM's fix is simply the new spec -- the loop converges
        normally once the fix stabilizes across a round with no diff."""
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6  # bare scalar, not a SourcedValue wrapper -> validate fails
        fixed = dict(raw)
        fixed["timing"] = dict(raw["timing"])
        fixed["timing"]["formation_month"] = {"value": 6, "evidence": [], "status": "unspecified"}
        client = _FakeLlmClient([
            {"spec": fixed, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        assert outcome.spec is not None
        assert outcome.spec.timing.formation_month.value == 6
        # round 1: validate fails, LLM fixes it (diff non-empty) -> continue.
        # round 2: validate now passes against the fix, LLM repeats the same
        # fixed spec (diff empty) -> exit.
        assert len(outcome.history) == 2
        assert outcome.history[0].error_log != ""
        assert any(d["field_path"] == "timing.formation_month" for d in outcome.history[0].diff)
        assert outcome.history[1].diff == []

    def test_error_log_reaches_the_same_round_llm_input(self):
        """The `ValidationError` text for round N's spec must appear in
        THAT SAME round's LLM prompt, not the next one."""
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6
        client = _FakeLlmClient([
            {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=1)
        assert "formation_month" in outcome.history[0].error_log
        first_call_user_msg = client.chat.completions.calls[0][1]["content"]
        assert "formation_month" in first_call_user_msg  # error log made it into round 1's prompt

    def test_budget_exhausted_returns_error_not_raises(self):
        """The LLM never fixes the structural problem (echoes the same
        broken spec every round) -- after `MAX_REVIEW_ROUNDS` calls,
        return an `error`, never raise."""
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6
        client = _FakeLlmClient([
            {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.spec is None
        assert outcome.error is not None
        assert len(outcome.history) == 2  # exactly max_rounds, no +1
        assert len(client.chat.completions.calls) == 2

    def test_stops_when_validated_and_llm_makes_no_further_changes(self):
        raw = _minimal_raw_spec()
        payload = {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []}
        client = _FakeLlmClient([payload, payload, payload])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        assert len(outcome.history) == 1  # exits after round 1: validate passed, no diff

    def test_a_change_on_an_already_valid_spec_forces_another_round(self):
        """Even if round N's pre-flight validate already passed, a diff
        this round (the LLM decided to fix something anyway) must NOT let
        the loop exit immediately -- one more round must confirm nothing
        further changes before exiting."""
        raw = _minimal_raw_spec()
        touched_up = dict(raw)
        touched_up["timing"] = dict(raw["timing"])
        touched_up["timing"]["formation_rule"] = {"value": "every June (Section 2)", "evidence": [], "status": "clear"}
        no_further_changes = dict(touched_up)
        client = _FakeLlmClient([
            {"spec": touched_up, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
            {"spec": no_further_changes, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        assert len(client.chat.completions.calls) == 2
        assert outcome.spec.timing.formation_rule.value == "every June (Section 2)"


class TestFullyTrustedRewrite:
    """2026-08-11: the earlier 'only merge declared/menu fields' guardrail
    was removed -- every field the LLM writes in its rewritten spec takes
    effect directly (except D7's factor_id/schema_version/document_id).
    """

    def test_menu_classification_takes_effect(self):
        raw = _minimal_raw_spec()
        raw["portfolio"]["weighting"] = {"value": "value-weighted", "evidence": [], "status": "clear"}
        classified = dict(raw)
        classified["portfolio"] = dict(raw["portfolio"])
        classified["portfolio"]["weighting"] = {"value": "vw", "evidence": [], "status": "clear"}
        client = _FakeLlmClient([
            {"spec": classified, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.portfolio.weighting.value == "vw"

    def test_other_classification_populates_unsupported_value(self):
        raw = _minimal_raw_spec()
        raw["portfolio"]["weighting"] = {"value": "capped VW at 5% per stock", "evidence": [], "status": "clear"}
        classified = dict(raw)
        classified["portfolio"] = dict(raw["portfolio"])
        classified["portfolio"]["weighting"] = {
            "value": "other", "unsupported_value": "capped VW at 5% per stock", "evidence": [], "status": "clear",
        }
        client = _FakeLlmClient([
            {"spec": classified, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.portfolio.weighting.value == "other"
        assert outcome.spec.portfolio.weighting.unsupported_value == "capped VW at 5% per stock"

    def test_a_non_menu_field_correction_takes_effect_directly(self):
        """The scenario the old guardrail explicitly discarded -- an
        undeclared change to a field outside the menu/status channels --
        is now trusted directly (no `value_corrections`/`field_assessments`
        entry needed for it to take effect)."""
        raw = _minimal_raw_spec()
        corrected = dict(raw)
        corrected["signal"] = dict(raw["signal"])
        corrected["signal"]["definition"] = {"value": "corrected formula per Eq. 3", "evidence": [], "status": "clear"}
        client = _FakeLlmClient([
            {"spec": corrected, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.signal.definition.value == "corrected formula per Eq. 3"

    def test_field_assessments_status_change_takes_effect(self):
        raw = _minimal_raw_spec()
        raw["timing"]["formation_rule"]["status"] = "unspecified"
        corrected = dict(raw)
        corrected["timing"] = dict(raw["timing"])
        corrected["timing"]["formation_rule"] = dict(raw["timing"]["formation_rule"])
        corrected["timing"]["formation_rule"]["status"] = "clear"
        client = _FakeLlmClient([
            {
                "spec": corrected,
                "field_assessments": [{"field_path": "timing.formation_rule", "evidence_status": "clear"}],
                "value_corrections": [],
                "evidence_assessments": [],
                "additional_findings": [],
            },
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.timing.formation_rule.status.value == "clear"

    def test_value_correction_now_takes_effect_directly(self):
        """Inverse of the pre-2026-08-11 behavior: `value_corrections` is
        now an explanatory annotation, not a human-gated proposal channel
        -- the corrected value in `spec` is what lands."""
        raw = _minimal_raw_spec()
        corrected = dict(raw)
        corrected["timing"] = dict(raw["timing"])
        corrected["timing"]["formation_rule"] = {"value": "every December", "evidence": [], "status": "clear"}
        client = _FakeLlmClient([
            {
                "spec": corrected,
                "field_assessments": [],
                "value_corrections": [
                    {"field_path": "timing.formation_rule", "proposed_value": "every December", "reason": "misread"}
                ],
                "evidence_assessments": [],
                "additional_findings": [],
            },
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client)
        assert outcome.spec is not None
        assert outcome.spec.timing.formation_rule.value == "every December"
        assert outcome.llm_notes["value_corrections"][0]["field_path"] == "timing.formation_rule"


class TestPreLlmTools:
    """docs/resolve-diagnostics-gaps.md problem 2 follow-up: `review_method_
    spec`'s findings (previously only computed for the standalone `/review`
    endpoint) are now surfaced to the LLM review loop itself, as one of
    Step2's registered Tool Prelude tools (see docs/tools-plus-llm-plan.md
    §5) -- rendered as a `### tool_name` block with a JSON payload, not the
    old hand-tagged `[tool_name]` text."""

    @staticmethod
    def _tool_block(user_message: str, name: str) -> str:
        start = user_message.find(f"### {name}")
        assert start != -1, f"no ### {name} block in message"
        rest = user_message[start:]
        next_marker = rest.find("\n### ", 1)
        return rest if next_marker == -1 else rest[:next_marker]

    def test_engine_menu_finding_is_included_in_the_prompt_once_schema_is_valid(self):
        raw = _minimal_raw_spec()
        raw["portfolio"]["weighting"] = {
            "value": "other", "unsupported_value": "capped VW at 5% per stock", "evidence": [], "status": "clear",
        }
        client = _FakeLlmClient([
            {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=1)
        user_message = client.chat.completions.calls[0][1]["content"]
        block = self._tool_block(user_message, "engine_menu_and_capability")
        assert "portfolio.weighting" in block
        assert "capped VW at 5% per stock" in block

    def test_no_engine_menu_report_when_spec_is_clean(self):
        raw = _minimal_raw_spec()
        client = _FakeLlmClient([
            {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=1)
        user_message = client.chat.completions.calls[0][1]["content"]
        block = self._tool_block(user_message, "engine_menu_and_capability")
        assert '"report"' not in block

    def test_schema_validation_report_present_when_invalid_and_tool_skipped(self):
        """When schema validation fails, the engine-menu tool self-reports
        `status="skipped"` (no valid `MethodSpec` object to check yet)."""
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6  # bare scalar -> validate fails
        client = _FakeLlmClient([
            {"spec": raw, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=1)
        user_message = client.chat.completions.calls[0][1]["content"]
        schema_block = self._tool_block(user_message, "schema_validation")
        assert "formation_month" in schema_block
        engine_block = self._tool_block(user_message, "engine_menu_and_capability")
        assert "status: skipped" in engine_block
        assert '"report"' not in engine_block



class TestDiffAndHistory:
    def test_round_records_before_and_after_snapshots(self):
        raw = _minimal_raw_spec()
        corrected = dict(raw)
        corrected["universe"] = dict(raw["universe"])
        corrected["universe"]["description"] = {"value": "NYSE/AMEX only", "evidence": [], "status": "clear"}
        client = _FakeLlmClient([
            {"spec": corrected, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
            {"spec": corrected, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        round1 = outcome.history[0]
        assert round1.spec_before["universe"]["description"]["value"] == "NYSE/AMEX/NASDAQ"
        assert round1.spec_after["universe"]["description"]["value"] == "NYSE/AMEX only"
        assert any(d["field_path"] == "universe.description.value" for d in round1.diff)

    def test_total_diff_spans_the_whole_run_not_just_the_last_round(self):
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6
        fixed = dict(raw)
        fixed["timing"] = dict(raw["timing"])
        fixed["timing"]["formation_month"] = {"value": 6, "evidence": [], "status": "unspecified"}
        client = _FakeLlmClient([
            {"spec": fixed, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        assert any(d["field_path"] == "timing.formation_month" for d in outcome.total_diff)


class TestToolResultsAndRequests:
    """docs/tools-plus-llm-plan.md §5: `SpecBuildOutcome.tool_results` is the
    LAST round's results (same "final state" semantics as `spec`/`review`),
    and `tool_requests` -- even though Step2 registers no `opt_in` tools --
    is parsed uniformly and surfaces as an "unknown tool name" catalog
    notice next round, never a crash."""

    def test_outcome_tool_results_is_the_last_rounds(self):
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6  # round 1 fails schema validation
        fixed = dict(raw)
        fixed["timing"] = dict(raw["timing"])
        fixed["timing"]["formation_month"] = {"value": 6, "evidence": [], "status": "unspecified"}
        client = _FakeLlmClient([
            {"spec": fixed, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert len(outcome.history) == 2
        assert outcome.tool_results == outcome.history[-1].tool_results
        # Round 1: schema_validation failed -> engine_menu self-skips.
        r1_engine = next(r for r in outcome.history[0].tool_results if r.name == "engine_menu_and_capability")
        assert r1_engine.status == "skipped"
        # Round 2: schema now valid -> engine_menu actually ran.
        r2_engine = next(r for r in outcome.history[1].tool_results if r.name == "engine_menu_and_capability")
        assert r2_engine.status == "ok"

    def test_unknown_tool_request_surfaces_as_a_notice_next_round_without_crashing(self):
        raw = _minimal_raw_spec()
        raw["timing"]["formation_month"] = 6  # round 1: schema invalid -> continues to round 2
        fixed = dict(raw)
        fixed["timing"] = dict(raw["timing"])
        fixed["timing"]["formation_month"] = {"value": 6, "evidence": [], "status": "unspecified"}
        client = _FakeLlmClient([
            {
                "spec": fixed, "field_assessments": [], "value_corrections": [],
                "evidence_assessments": [], "additional_findings": [],
                "tool_requests": ["made_up_tool"],
            },
            {"spec": fixed, "field_assessments": [], "value_corrections": [], "evidence_assessments": [], "additional_findings": []},
        ])
        outcome = build_reviewed_method_spec(raw, "cooper2008", "asset_growth", "paper text", client, max_rounds=2)
        assert outcome.error is None
        assert len(client.chat.completions.calls) == 2
        round2_system_prompt = client.chat.completions.calls[1][0]["content"]
        assert "未知工具名" in round2_system_prompt
        assert "made_up_tool" in round2_system_prompt



