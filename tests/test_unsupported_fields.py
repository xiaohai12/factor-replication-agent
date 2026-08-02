"""Regression test for the "unspecified vs other" distinction (2026-08-02):

A paper-silent field (e.g. weighting never mentioned) and a paper-EXPLICIT
field whose value isn't an engine menu member (e.g. weighting="capped_vw")
used to collapse into the same "unspecified" sentinel and lose the paper's
actual value. Now:

- `unspecified`: the paper never addresses the choice (case A, untouched).
- `other`: the paper states a specific, off-menu value (case B). The field
  itself normalizes to "other"; `MethodSpec.unsupported_fields` is the only
  place the paper's literal value survives; `registry.build_config` is the
  single deterministic point that substitutes the menu default and records
  it in `config["substitutions"]`; `ReviewGate` surfaces it for human
  confirmation, distinctly from a plain paper-silent default.

See docs/decision-log.md (2026-08-02 entry) and
docs/multi-config-evidence-plan.md for the design discussion this closes.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.infra.models.method_spec import MethodSpec
from src.steps.step2_reviewer import Disposition, ReviewGate
from src.steps.step3_codegen.registry import build_config


NOVY_MARX_SPEC = (
    Path(__file__).parent
    / "fixtures"
    / "method_specs"
    / "novy_marx_2013_gross_profitability.resolved.methodspec.json"
)


def _spec_with_portfolio(**portfolio_overrides) -> MethodSpec:
    payload = {
        "factor_id": "x",
        "factor_name": "X",
        "signal": {"required_fields": ["f"], "formula": {"expression": "f"}},
        "data": {"normalized_mapping": {"f": "ret"}},
        "portfolio": portfolio_overrides,
    }
    return MethodSpec.model_validate(payload)


class TestUnsupportedVsUnspecified:
    def test_paper_silent_weighting_stays_unspecified_and_unrecorded(self):
        spec = _spec_with_portfolio()  # no "weighting" key at all

        assert spec.portfolio.weighting == "unspecified"
        assert spec.unsupported_fields == []

    def test_paper_stated_off_menu_weighting_becomes_other_and_is_recorded(self):
        spec = _spec_with_portfolio(weighting="capped_vw")

        assert spec.portfolio.weighting == "other"
        assert len(spec.unsupported_fields) == 1
        entry = spec.unsupported_fields[0]
        assert entry.field == "portfolio.weighting"
        assert entry.paper_value == "capped_vw"
        assert entry.reason == "not_in_engine_menu"

    def test_paper_stated_off_menu_breakpoint_source_becomes_other_and_is_recorded(self):
        spec = _spec_with_portfolio(sort={"breakpoint_source": "conditional"})

        assert spec.portfolio.sort.breakpoint_source == "other"
        assert any(
            uf.field == "portfolio.sort.breakpoint_source" and uf.paper_value == "conditional"
            for uf in spec.unsupported_fields
        )

    def test_paper_stated_off_menu_missing_action_becomes_other_and_is_recorded(self):
        payload = {
            "factor_id": "x",
            "factor_name": "X",
            "signal": {
                "required_fields": ["f"],
                "formula": {"expression": "f"},
                "missing_policy": {"action": "winsorize"},
            },
            "data": {"normalized_mapping": {"f": "ret"}},
        }
        spec = MethodSpec.model_validate(payload)

        assert spec.signal.missing_policy.action == "other"
        assert any(
            uf.field == "signal.missing_policy.action" and uf.paper_value == "winsorize"
            for uf in spec.unsupported_fields
        )

    def test_recognized_synonym_still_normalizes_to_the_menu_value(self):
        """A known synonym (not off-menu) must NOT be recorded as unsupported."""
        spec = _spec_with_portfolio(weighting="value_weighted")

        assert spec.portfolio.weighting == "vw"
        assert spec.unsupported_fields == []


class TestBuildConfigSubstitutionLog:
    def test_novy_marx_fixture_preserves_capped_vw_and_runs_vw(self):
        spec = MethodSpec.model_validate(json.loads(NOVY_MARX_SPEC.read_text()))

        assert spec.portfolio.weighting == "other"
        assert any(
            field.field == "portfolio.weighting" and field.paper_value == "capped_vw"
            for field in spec.unsupported_fields
        )

        config = build_config(spec, overrides=None)
        assert config["weighting_rule"] == "vw"
        assert config["substitutions"] == [
            {
                "field": "portfolio.weighting",
                "paper_value": "capped_vw",
                "engine_value": "vw",
                "reason": "not_in_engine_menu",
            }
        ]

    def test_other_weighting_is_clamped_to_vw_and_logged_as_a_substitution(self):
        spec = _spec_with_portfolio(weighting="capped_vw")

        config = build_config(spec, overrides=None)

        assert config["weighting_rule"] == "vw"
        assert config["substitutions"] == [
            {
                "field": "portfolio.weighting",
                "paper_value": "capped_vw",
                "engine_value": "vw",
                "reason": "not_in_engine_menu",
            }
        ]

    def test_no_substitutions_key_when_nothing_is_off_menu(self):
        spec = _spec_with_portfolio(weighting="vw")

        config = build_config(spec, overrides=None)

        assert "substitutions" not in config


class TestReviewGateSurfacesUnsupportedFields:
    def test_other_weighting_requires_human_confirmation_distinctly_from_unspecified(self):
        spec = _spec_with_portfolio(weighting="capped_vw")
        gate = ReviewGate(data_dictionary=None)

        result = gate.review(spec)

        assert "portfolio.weighting" in result.blocked_fields
        note = next(n for n in result.field_notes if n.field == "portfolio.weighting")
        assert note.status == Disposition.NEEDS_HUMAN_CONFIRMATION
        assert note.current_value == "capped_vw"
        assert "capped_vw" in note.reason
        assert "not a paper-silent default" in note.reason or "NOT a paper-silent" in note.reason
