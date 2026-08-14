"""Phase B tests: extraction prompt splicing + raw-dict extraction contract.

Step1 no longer validates or normalizes its output (see
docs/step1-step2-refactor-plan.md) -- `MethodSpecExtractor.extract()` just
returns whatever JSON dict the LLM produced. All correctness work
(`model_validate`, menu-vocabulary classification, structural repair) now
lives in Step2's `spec_build.build_reviewed_method_spec` -- see
`tests/test_spec_build.py`.
"""

from __future__ import annotations

import json

from src.infra.models.schema_render import (
    SCHEMA_SKELETON_END,
    SCHEMA_SKELETON_START,
    render_schema_skeleton_block,
)
from src.steps.step1_extractor.extractor import (
    ExtractionResult,
    MethodSpecExtractor,
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
    """A hand-built dict shaped like what the prompt asks for, standing in
    for what an LLM extraction call would return. Deliberately uses paper
    prose (not engine menu tokens) for `weighting`/`breakpoints.basis` --
    Step1 no longer classifies these; that's Step2's job now."""
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
                    "name_in_paper": "total assets",
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
                    "breakpoints": {"basis": {"value": "NYSE breakpoints", "evidence": [], "status": "clear"}, "values": []},
                }
            ],
            "legs": [
                {"leg_id": "long", "side": "long", "selector": {"sort1": 0}},
                {"leg_id": "short", "side": "short", "selector": {"sort1": 9}},
            ],
            "weighting": {"value": "value-weighted", "evidence": [], "status": "clear"},
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


class _FakeLLMClient:
    """Minimal stand-in for a chat-completions client, mirroring what the
    real `chat.completions.create(...).choices[0].message.content` shape
    looks like."""

    def __init__(self, content: str):
        self.chat = self
        self.completions = self
        self._content = content

    def create(self, **kwargs):
        class _Msg:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, content):
                self.message = _Msg(content)

        class _Response:
            def __init__(self, content):
                self.choices = [_Choice(content)]
                self.usage = None

        return _Response(self._content)


class TestExtractReturnsRawDict:
    def test_extract_returns_raw_dict_unvalidated(self):
        raw = _valid_raw_llm_output()
        client = _FakeLLMClient(json.dumps(raw))
        extractor = MethodSpecExtractor(llm_client=client, call_delay=0.0)
        result = extractor.extract("cooper2008", "asset_growth", "paper text")
        assert isinstance(result, ExtractionResult)
        assert result.error is None
        # Step1 does no normalization -- the paper-prose weighting value
        # survives untouched (Step2's job to classify it).
        assert result.raw_spec["portfolio"]["weighting"]["value"] == "value-weighted"
        # factor_id/schema_version are never injected by Step1.
        assert "factor_id" not in result.raw_spec
        assert "schema_version" not in result.raw_spec

    def test_extract_reports_error_on_empty_llm_response(self):
        client = _FakeLLMClient("")
        extractor = MethodSpecExtractor(llm_client=client, call_delay=0.0)
        result = extractor.extract("cooper2008", "asset_growth", "paper text")
        assert result.raw_spec is None
        assert result.error is not None

    def test_extract_requires_llm_client(self):
        extractor = MethodSpecExtractor(llm_client=None)
        try:
            extractor.extract("cooper2008", "asset_growth", "paper text")
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass


class _CapturingFakeLLMClient(_FakeLLMClient):
    """Same shape as `_FakeLLMClient` but records the messages it was
    called with, so tests can inspect what actually reached the LLM."""

    def __init__(self, content: str):
        super().__init__(content)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return super().create(**kwargs)


class TestStep1ToolPrelude:
    """Step1's tools+LLM wiring: a prelude-only (no round loop, no
    `tool_requests`) run of `STEP1_TOOLS` before the single LLM call --
    see docs/tools-plus-llm-plan.md §4.1."""

    def test_tool_results_are_recorded_on_the_extraction_result(self):
        raw = _valid_raw_llm_output()
        client = _CapturingFakeLLMClient(json.dumps(raw))
        extractor = MethodSpecExtractor(llm_client=client, call_delay=0.0)
        result = extractor.extract("cooper2008", "asset_growth", "paper text")
        assert [r.name for r in result.tool_results] == ["schema_skeleton", "data_catalog"]
        assert result.tool_results[0].status == "ok"

    def test_catalog_is_spliced_into_the_system_prompt(self):
        raw = _valid_raw_llm_output()
        client = _CapturingFakeLLMClient(json.dumps(raw))
        extractor = MethodSpecExtractor(llm_client=client, call_delay=0.0)
        extractor.extract("cooper2008", "asset_growth", "paper text")
        system_prompt = client.calls[0]["messages"][0]["content"]
        assert "## TOOL CATALOG" in system_prompt
        assert "schema_skeleton" in system_prompt

    def test_tool_results_json_reaches_the_user_message(self):
        raw = _valid_raw_llm_output()
        client = _CapturingFakeLLMClient(json.dumps(raw))
        extractor = MethodSpecExtractor(llm_client=client, call_delay=0.0)
        extractor.extract("cooper2008", "asset_growth", "paper text")
        user_msg = client.calls[0]["messages"][1]["content"]
        assert "## TOOL RESULTS" in user_msg
        assert "schema_skeleton" in user_msg


class TestPersistRawSpec:
    def test_persist_raw_spec_writes_json_file(self, tmp_path, monkeypatch):
        import src.steps.step1_extractor.extractor as extractor_module

        monkeypatch.setattr(extractor_module, "RAW_SPEC_DIR", tmp_path)
        raw = _valid_raw_llm_output()
        out_path = extractor_module.persist_raw_spec("cooper2008", "asset_growth", raw)
        assert out_path.exists()
        loaded = json.loads(out_path.read_text())
        assert loaded["portfolio"]["weighting"]["value"] == "value-weighted"

