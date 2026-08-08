"""Phase D test: `script_generator.generate_backtest_script`'s
`ResolvedMethodSpec` dispatch (`pick_signal_input_mode`/
`signal_input_sources_from_resolved`). Not yet used by `src.pipeline`/
`BacktestRunner`/backend routers (see docs/methodspec-v2-plan.md section 9,
Phase D).
"""

from __future__ import annotations

from src.infra.models.paper_method_spec import SourceColumn
from src.steps.step3_codegen.script_generator import (
    generate_backtest_script,
    pick_signal_input_mode,
    signal_input_sources_from_resolved,
)
from tests.test_meta_coder_resolved_method_spec import _resolved_spec


class TestSignalInputSourcesFromResolved:
    def test_groups_signal_input_concepts_by_source(self):
        resolved = _resolved_spec()
        sources = signal_input_sources_from_resolved(resolved)
        assert sources == {"comp_funda": ["at"]}

    def test_pick_signal_input_mode_compustat(self):
        resolved = _resolved_spec()
        assert pick_signal_input_mode(resolved) == "compustat"

    def test_pick_signal_input_mode_crsp_only(self):
        resolved = _resolved_spec()
        resolved.resolution.concept_mapping["at"] = SourceColumn(source="crsp_msf", column="me")
        assert pick_signal_input_mode(resolved) == "crsp_only"

    def test_pick_signal_input_mode_raises_when_unmapped(self):
        resolved = _resolved_spec()
        resolved.resolution.concept_mapping = {}
        try:
            pick_signal_input_mode(resolved)
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestGenerateBacktestScript:
    def test_generates_script_with_resolved_method_spec(self):
        resolved = _resolved_spec()
        script = generate_backtest_script(
            resolved, plugin_code="def compute_signal(df):\n    return df\n",
        )
        assert 'FACTOR_ID = "' in script
        assert resolved.paper.factor_id in script
        assert "compute_signal" in script
