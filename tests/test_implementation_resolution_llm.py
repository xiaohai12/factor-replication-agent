"""Tests for `build_implementation_resolution`'s optional `llm_client` --
wires `DataDictionary.normalize_fields_with_llm` (already tested standalone
in `test_llm_normalized_mapping.py`) into the resolution builder and records
which concepts were resolved ONLY via the LLM pass in
`ImplementationResolution.llm_matched_concepts`.
"""

from __future__ import annotations

from src.infra.data_layer import DataDictionary
from src.infra.models.method_spec import FieldRole, RequiredField
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.review import review_method_spec
from tests._spec_test_helpers import minimal_resolved_spec
from tests.test_llm_normalized_mapping import FakeLLM


def _paper_with_unresolvable_field():
    resolved = minimal_resolved_spec()
    paper = resolved.paper
    paper.data.fields.append(
        RequiredField(
            concept_id="firm_beta_estimate", paper_name="rolling market beta",
            paper_source_hint="", roles=[FieldRole.SIGNAL_INPUT],
        )
    )
    return paper


class TestBuildImplementationResolutionWithLlm:
    def test_no_llm_client_stays_fully_deterministic(self):
        paper = _paper_with_unresolvable_field()
        review = review_method_spec(paper)
        resolution = build_implementation_resolution(paper, review, data_dictionary=DataDictionary())
        assert "firm_beta_estimate" not in resolution.concept_mapping
        assert resolution.llm_matched_concepts == []

    def test_valid_llm_pick_is_recorded_as_llm_matched(self):
        paper = _paper_with_unresolvable_field()
        review = review_method_spec(paper)
        llm = FakeLLM({"firm_beta_estimate": {"source": "comp_funda", "column": "at"}})
        resolution = build_implementation_resolution(
            paper, review, data_dictionary=DataDictionary(), llm_client=llm
        )
        assert resolution.concept_mapping["firm_beta_estimate"].column == "at"
        assert resolution.llm_matched_concepts == ["firm_beta_estimate"]
        # a concept the deterministic matcher already resolved is never
        # counted as "LLM-matched", even though the LLM path also ran.
        assert "x" not in resolution.llm_matched_concepts

    def test_invalid_llm_pick_leaves_concept_unresolved(self):
        paper = _paper_with_unresolvable_field()
        review = review_method_spec(paper)
        llm = FakeLLM({"firm_beta_estimate": {"source": "not_a_real_source", "column": "made_up"}})
        resolution = build_implementation_resolution(
            paper, review, data_dictionary=DataDictionary(), llm_client=llm
        )
        assert "firm_beta_estimate" not in resolution.concept_mapping
        assert resolution.llm_matched_concepts == []
