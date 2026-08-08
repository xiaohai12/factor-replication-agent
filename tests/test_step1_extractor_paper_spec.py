"""Phase B tests: extraction prompt splicing + LLM-output parsing.

Does NOT touch the live v1 `SemanticExtractor` / `src.pipeline` -- these
tests only lock the new extractor module's contract (see
docs/methodspec-v2-plan.md section 9, Phase B).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.infra.models.paper_method_spec import PaperMethodSpec
from src.infra.models.schema_render import (
    SCHEMA_SKELETON_END,
    SCHEMA_SKELETON_START,
    render_schema_skeleton_block,
)
from src.steps.step1_extractor.paper_extractor import (
    build_paper_method_spec,
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
                    "breakpoints": {"population": {"value": "nyse", "evidence": [], "status": "clear"}, "values": []},
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


class TestBuildPaperMethodSpec:
    def test_valid_raw_output_parses(self):
        spec = build_paper_method_spec("cooper2008", "asset_growth", _valid_raw_llm_output())
        assert isinstance(spec, PaperMethodSpec)
        assert spec.target_name == "asset_growth"
        assert spec.schema_version == "methodspec.v2"

    def test_factor_id_is_deterministic_and_ignores_llm_supplied_value(self):
        raw = _valid_raw_llm_output()
        raw["factor_id"] = "llm_invented_id_should_be_ignored"
        spec = build_paper_method_spec("cooper2008", "asset_growth", raw)
        expected = PaperMethodSpec.make_factor_id("cooper2008", "asset_growth")
        assert spec.factor_id == expected
        assert spec.factor_id != "llm_invented_id_should_be_ignored"

    def test_document_id_filled_into_paper_block(self):
        spec = build_paper_method_spec("cooper2008", "asset_growth", _valid_raw_llm_output())
        assert spec.paper.document_id == "cooper2008"

    def test_unknown_field_from_llm_rejected_loudly(self):
        raw = _valid_raw_llm_output()
        raw["signal"]["ghost_field_llm_invented"] = "should not survive"
        with pytest.raises(ValidationError):
            build_paper_method_spec("cooper2008", "asset_growth", raw)

    def test_missing_required_nested_field_rejected(self):
        raw = _valid_raw_llm_output()
        del raw["signal"]["direction"]
        with pytest.raises(ValidationError):
            build_paper_method_spec("cooper2008", "asset_growth", raw)
