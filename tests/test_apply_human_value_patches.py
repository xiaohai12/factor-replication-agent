"""Tests for `apply_human_value_patches` -- a human directly correcting the
extracted VALUE of a high-impact field (not just its evidence status; see
`test_step2_reviewer_llm.py`'s override tests for the status-only path).
"""

from __future__ import annotations

import pytest

from src.infra.models.method_spec import EvidenceStatus
from src.steps.step2_reviewer.review import apply_human_value_patches
from tests.test_step2_reviewer import _base_spec


class TestApplyHumanValuePatches:
    def test_patches_value_and_marks_status_clear(self):
        paper = _base_spec()
        paper.timing.formation_rule.value = "every June"
        paper.timing.formation_rule.status = EvidenceStatus.UNSPECIFIED

        patched = apply_human_value_patches(
            paper, {"timing.formation_rule": "every December"}, reason="Section 2 actually says December"
        )

        assert patched.timing.formation_rule.value == "every December"
        assert patched.timing.formation_rule.status == EvidenceStatus.CLEAR
        assert "human correction" in patched.timing.formation_rule.evidence[-1].interpretation

    def test_original_paper_is_not_mutated(self):
        paper = _base_spec()
        original_value = paper.timing.formation_rule.value
        apply_human_value_patches(paper, {"timing.formation_rule": "every December"})
        assert paper.timing.formation_rule.value == original_value

    def test_unknown_field_path_rejected(self):
        paper = _base_spec()
        with pytest.raises(ValueError, match="not a patchable high-impact field"):
            apply_human_value_patches(paper, {"signal.formula.expression": "malicious"})

    def test_sort_breakpoints_basis_is_patchable_by_index(self):
        paper = _base_spec()
        patched = apply_human_value_patches(paper, {"portfolio.sorts[0].breakpoints.basis": "full_sample"})
        assert patched.portfolio.sorts[0].breakpoints.basis.value == "full_sample"
        assert patched.portfolio.sorts[0].breakpoints.basis.status == EvidenceStatus.CLEAR

    def test_multiple_patches_in_one_call(self):
        paper = _base_spec()
        patched = apply_human_value_patches(
            paper,
            {
                "timing.formation_rule": "every December",
                "portfolio.weighting": "ew",
            },
        )
        assert patched.timing.formation_rule.value == "every December"
        assert patched.portfolio.weighting.value == "ew"


class TestValuePatchTypeCoercion:
    def test_string_input_coerced_to_int_field(self):
        paper = _base_spec()
        patched = apply_human_value_patches(paper, {"timing.holding_period": "24"})
        assert patched.timing.holding_period.value == 24
        assert isinstance(patched.timing.holding_period.value, int)

    def test_invalid_int_string_fails_loud(self):
        paper = _base_spec()
        with pytest.raises(ValueError, match="expects an integer"):
            apply_human_value_patches(paper, {"timing.holding_period": "not a number"})

    def test_string_input_coerced_to_enum_field(self):
        paper = _base_spec()
        patched = apply_human_value_patches(paper, {"signal.direction": "positive"})
        assert patched.signal.direction.value.value == "positive"

    def test_invalid_enum_string_fails_loud(self):
        paper = _base_spec()
        with pytest.raises(ValueError, match="expects one of"):
            apply_human_value_patches(paper, {"signal.direction": "sideways"})
