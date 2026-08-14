"""`MetaCoder.generate_filter_derivation_plugin`/`_build_prompt_for_filter_
derivation`: codegen for `FilterSpec.derivation` (docs/resolve-diagnostics-
gaps.md problem 1/3), mirroring `generate_plugin`'s existing dispatch with a
fake LLM client (no real network call).
"""

from __future__ import annotations

from src.infra.models.method_spec import CalculationStep, FilterOp, FilterSpec, FormulaSpec, SourceColumn
from src.steps.step3_codegen import MetaCoder
from tests.test_meta_coder_resolved_method_spec import _FakeLLMClient, _resolved_spec


def _spec_with_filter_derivation():
    resolved = _resolved_spec()
    paper = resolved.paper.model_copy(deep=True)
    paper.universe.filters.append(
        FilterSpec(
            concept_id="listing_exchange",
            op=FilterOp.IN,
            value=["NYSE", "Amex", "NASDAQ"],
            derivation=FormulaSpec(
                paper_expression='"NYSE"/"Amex"/"NASDAQ" -> exchcd 1/2/3',
                steps=[
                    CalculationStep(
                        step_id="map_label_to_code",
                        description="Map paper's exchange label to CRSP numeric exchcd",
                        expression='{"NYSE": 1, "Amex": 2, "NASDAQ": 3}',
                    ),
                ],
                inputs=["listing_exchange"],
            ),
        )
    )
    resolution = resolved.resolution.model_copy(deep=True)
    resolution.concept_mapping["listing_exchange"] = SourceColumn(source="crsp_msf", column="exchcd")
    return resolved.model_copy(update={"paper": paper, "resolution": resolution})


class TestGenerateFilterDerivationPlugin:
    def test_generates_plugin_with_derivation_entry_function(self):
        coder = MetaCoder(llm_client=_FakeLLMClient("def compute_filter_value(df):\n    return df['exchcd']\n"))
        record = coder.generate_filter_derivation_plugin(_spec_with_filter_derivation(), filter_index=0)
        assert record.entry_function == "compute_filter_value"
        assert record.plugin_id.endswith("::filter_derivation::listing_exchange")
        assert "compute_filter_value" in record.code

    def test_missing_derivation_raises(self):
        resolved = _spec_with_filter_derivation()
        resolved.paper.universe.filters[0].derivation = None
        coder = MetaCoder(llm_client=_FakeLLMClient())
        try:
            coder.generate_filter_derivation_plugin(resolved, filter_index=0)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_prompt_includes_steps_and_column_mapping(self):
        coder = MetaCoder(llm_client=_FakeLLMClient())
        prompt = coder._build_prompt_for_filter_derivation(_spec_with_filter_derivation(), filter_index=0)
        assert "Map paper's exchange label to CRSP numeric exchcd" in prompt
        assert 'listing_exchange -> df["exchcd"]' in prompt
        assert '"NYSE"/"Amex"/"NASDAQ" -> exchcd 1/2/3' in prompt
