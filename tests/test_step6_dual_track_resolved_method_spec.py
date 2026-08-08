"""Phase D test: `DualTrackController`'s `ResolvedMethodSpec` dispatch
(`_spec_factor_id`, `_plan_to_matrix`, `_get_ablation_override`). Not yet
used by `src.pipeline`/backend routers/`app.py` (see
docs/methodspec-v2-plan.md section 9, Phase D). Exercises matrix-building
only (no real snapshot/data needed) -- full track execution is already
covered end-to-end by tests/test_registry_resolved_method_spec.py at the
engine layer.
"""

from __future__ import annotations

from src.steps.step6_dual_track_controller import (
    DualTrackController,
    ExperimentPlan,
    _spec_factor_id,
)
from tests.test_meta_coder_resolved_method_spec import _resolved_spec


def _controller() -> DualTrackController:
    return DualTrackController(runner=None, meta_coder=None, sandbox=None)


class TestSpecFactorIdDispatch:
    def test_resolves_paper_factor_id(self):
        resolved = _resolved_spec()
        assert _spec_factor_id(resolved) == resolved.paper.factor_id


class TestPlanToMatrix:
    def test_builds_matrix_with_resolved_spec_factor_id(self):
        resolved = _resolved_spec()
        controller = _controller()
        plan = ExperimentPlan(
            factor_id=resolved.paper.factor_id, run_original=True,
            run_standardized=True, ablation_switches=["weighting"],
        )
        matrix = controller._plan_to_matrix(plan, resolved)
        assert matrix.factor_id == resolved.paper.factor_id
        names = [e.name for e in matrix.experiments]
        assert "standardized_hxz" in names
        assert "ablation_weighting" in names

    def test_ablation_override_unaffected_by_spec_type(self):
        controller = _controller()
        resolved = _resolved_spec()
        override = controller._get_ablation_override("weighting", resolved)
        assert override == {"weighting_rule": "vw"}
