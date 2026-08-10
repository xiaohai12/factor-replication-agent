"""Phase B tests: extraction prompt splicing + LLM-output parsing.

Does NOT touch the live v1 `SemanticExtractor` / `src.pipeline` -- these
tests only lock the new extractor module's contract (see
docs/methodspec-v2-plan.md section 9, Phase B).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.infra.models.method_spec import EvidenceStatus, MethodSpec
from src.infra.models.schema_render import (
    SCHEMA_SKELETON_END,
    SCHEMA_SKELETON_START,
    render_schema_skeleton_block,
)
from src.steps.step1_extractor.extractor import (
    build_method_spec,
    load_extraction_system_prompt,
)


class TestPromptSplicing:
    def test_prompt_loads_and_contains_spliced_skeleton(self):
        prompt = load_extraction_system_prompt()
        assert SCHEMA_SKELETON_START in prompt
        assert SCHEMA_SKELETON_END in prompt
        # The skeleton block should contain a real field name from the model,
        # not the raw unspliced marker pair with nothing between them.
        assert '"formula"' in prompt
        assert '"portfolio"' in prompt

    def test_prompt_never_asks_llm_for_factor_id_or_schema_version(self):
        prompt = load_extraction_system_prompt()
        start = prompt.find(SCHEMA_SKELETON_START)
        end = prompt.find(SCHEMA_SKELETON_END)
        skeleton_block = prompt[start:end]
        assert '"factor_id"' not in skeleton_block
        assert '"schema_version"' not in skeleton_block

    def test_skeleton_is_valid_json(self):
        block = render_schema_skeleton_block()
        # Strip the markers and the ```json fence to parse the JSON body.
        body = block.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
        parsed = json.loads(body)
        assert "signal" in parsed
        assert "portfolio" in parsed
        assert "reported_results" in parsed


def _valid_raw_llm_output() -> dict:
    """A hand-built dict shaped exactly like what the prompt asks for,
    standing in for what an LLM extraction call would return."""
    return {
        "paper": {"title": "Asset Growth...", "citation": "Cooper et al 2008", "publication_year": 2008},
        "signal": {
            "definition": {"value": "(AT_t - AT_t-1) / AT_t-1", "evidence": [], "status": "clear"},
            "economic_intuition": {"value": "overinvestment", "evidence": [], "status": "clear"},
            "direction": {"value": "negative", "evidence": [], "status": "clear"},
            "category": "continuous",
            "formula": {
                "paper_expression": "(AT_t - AT_t-1) / AT_t-1",
                "steps": [
                    {"step_id": "s1", "description": "take total assets and lag", "expression": "at, at_lag1"},
                    {"step_id": "s2", "description": "compute ratio", "expression": "(at - at_lag1) / at_lag1"},
                ],
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
            "sources": [{"value": "Compustat", "evidence": [], "status": "clear"}],
            "fields": [
                {
                    "concept_id": "at",
                    "paper_name": "total assets",
                    "paper_source_hint": "Compustat annual",
                    "roles": ["signal_input"],
                    "evidence": [],
                }
            ],
            "coverage_notes": [],
        },
        "sample": {
            "data_coverage": {"start_year": 1962, "end_year": 2003},
            "formation": {"start_year": 1968, "end_year": 2003},
            "reported_returns": {"start_year": 1968, "end_year": 2003},
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
                    "mode": "independent", "group_type": "quantile", "group_count": 10,
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


class TestBuildMethodSpec:
    def test_valid_raw_output_parses(self):
        spec = build_method_spec("cooper2008", "asset_growth", _valid_raw_llm_output())
        assert isinstance(spec, MethodSpec)
        assert spec.target_name == "asset_growth"
        assert spec.schema_version == "methodspec.v2"

    def test_factor_id_is_deterministic_and_ignores_llm_supplied_value(self):
        raw = _valid_raw_llm_output()
        raw["factor_id"] = "llm_invented_id_should_be_ignored"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        expected = MethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert spec.factor_id == expected
        assert spec.factor_id != "llm_invented_id_should_be_ignored"

    def test_document_id_filled_into_paper_block(self):
        spec = build_method_spec("cooper2008", "asset_growth", _valid_raw_llm_output())
        assert spec.paper.document_id == "cooper2008"

    def test_unknown_field_from_llm_rejected_loudly(self):
        raw = _valid_raw_llm_output()
        raw["signal"]["ghost_field_llm_invented"] = "should not survive"
        with pytest.raises(ValidationError):
            build_method_spec("cooper2008", "asset_growth", raw)


class TestEngineVocabularyNormalization:
    """docs/known-gaps-paper-first-v2.md gap #1: the extractor doesn't
    reliably emit canonical engine-menu tokens for weighting/return_combination.
    `build_method_spec` should canonicalize known synonyms before validation;
    `weighting` is a constrained enum (`vw`/`ew`/`other`), so anything
    unrecognized maps to `other` rather than failing validation, while
    `return_combination` stays free text and is left unrecognized untouched."""

    def test_value_weighted_synonym_normalized_to_vw(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["weighting"]["value"] = "value-weighted"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.weighting.value == "vw"

    def test_equal_weighted_synonym_normalized_to_ew(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["weighting"]["value"] = "Equally Weighted"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.weighting.value == "ew"

    def test_unrecognized_weighting_text_maps_to_other(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["weighting"]["value"] = "some novel scheme"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.weighting.value == "other"

    def test_long_short_sentence_normalized_to_extreme_group_spread(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["return_combination"]["value"] = (
            "Goes long the lowest asset-growth decile and short the highest decile"
        )
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.return_combination.value == "extreme_group_spread"

    def test_average_of_portfolios_sentence_normalized_to_average_leg_spread(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["return_combination"]["value"] = (
            "Long the average of the three lowest decile portfolios and short the average of "
            "the three highest decile portfolios"
        )
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.return_combination.value == "average_leg_spread"

    def test_unrecognized_return_combination_text_left_untouched(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["return_combination"]["value"] = "reported in Table 3"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.return_combination.value == "reported in Table 3"

    def test_missing_policy_drop_sentence_normalized_to_drop(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["missing_policies"] = [
            {
                "stage": "signal",
                "action": {
                    "value": "Require nonzero total assets in both input years.",
                    "evidence": [],
                    "status": "clear",
                },
            }
        ]
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.missing_policies[0].action.value == "drop"

    def test_missing_policy_unrecognized_sentence_maps_to_other(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["missing_policies"] = [
            {
                "stage": "signal",
                "action": {"value": "Impute using the prior year's value.", "evidence": [], "status": "clear"},
            }
        ]
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.missing_policies[0].action.value == "other"

    def test_breakpoint_basis_synonym_normalized_to_full_sample(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["sorts"][0]["breakpoints"]["basis"]["value"] = "all eligible stocks"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.sorts[0].breakpoints.basis.value == "full_sample"

    def test_breakpoint_basis_unrecognized_text_maps_to_other(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["sorts"][0]["breakpoints"]["basis"]["value"] = "size-conditional subset"
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.portfolio.sorts[0].breakpoints.basis.value == "other"

    def test_original_raw_dict_not_mutated(self):
        raw = _valid_raw_llm_output()
        raw["portfolio"]["weighting"]["value"] = "value-weighted"
        build_method_spec("cooper2008", "asset_growth", raw)
        assert raw["portfolio"]["weighting"]["value"] == "value-weighted"

    def test_missing_required_nested_field_rejected(self):
        raw = _valid_raw_llm_output()
        del raw["signal"]["direction"]
        with pytest.raises(ValidationError):
            build_method_spec("cooper2008", "asset_growth", raw)

    def test_bare_formation_month_scalar_is_wrapped_as_sourced_value(self):
        """Real drift observed: the LLM sometimes emits `timing.formation_month`
        as a bare int instead of the required SourcedValue wrapper -- salvage
        it (status=unspecified, since no evidence was captured) rather than
        failing the whole extraction."""
        raw = _valid_raw_llm_output()
        raw["timing"]["formation_month"] = 6
        spec = build_method_spec("cooper2008", "asset_growth", raw)
        assert spec.timing.formation_month.value == 6
        assert spec.timing.formation_month.status == EvidenceStatus.UNSPECIFIED
