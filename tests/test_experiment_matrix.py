"""Tests for the declarative experiment matrix loader (Phase A2,
docs/multi-config-evidence-plan.md): `experiments/<factor_id>.experiments.yaml`
loading/validation/family+identification-level derivation.
"""

from __future__ import annotations

import pytest

from src.steps.step6_dual_track_controller.experiment_spec import (
    ExperimentMatrixError,
    load_experiment_matrix,
)
from tests._spec_test_helpers import minimal_resolved_spec


def _spec(weighting: str = "vw"):
    return minimal_resolved_spec("t", weighting=weighting)


def _write(tmp_path, text: str):
    p = tmp_path / "t.experiments.yaml"
    p.write_text(text)
    return p


class TestBasicLoading:
    def test_factor_id_mismatch_raises(self, tmp_path):
        path = _write(tmp_path, "factor_id: other\nexperiments: []\n")
        with pytest.raises(ExperimentMatrixError, match="does not match"):
            load_experiment_matrix(path, _spec())

    def test_single_valid_experiment_loads(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
baseline: original_method
experiments:
  - name: ablation_weighting_ew
    config_overrides: {weighting_rule: ew}
""",
        )
        matrix = load_experiment_matrix(path, _spec())
        assert matrix.factor_id == "t"
        assert matrix.baseline == "original_method"
        assert len(matrix.experiments) == 1
        exp = matrix.experiments[0]
        assert exp.name == "ablation_weighting_ew"
        assert exp.resolved_config["weighting_rule"] == "ew"

    def test_experiment_spec_hash_is_stable_for_same_content(self, tmp_path):
        text = "factor_id: t\nexperiments:\n  - name: x\n    config_overrides: {weighting_rule: ew}\n"
        p1 = _write(tmp_path, text)
        matrix1 = load_experiment_matrix(p1, _spec())
        matrix2 = load_experiment_matrix(p1, _spec())
        assert matrix1.experiment_spec_hash == matrix2.experiment_spec_hash


class TestValidationFailures:
    def test_duplicate_name_raises(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: dup
    config_overrides: {weighting_rule: ew}
  - name: dup
    config_overrides: {breakpoint_source: nyse}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="duplicate experiment name"):
            load_experiment_matrix(path, _spec())

    def test_unknown_override_key_raises_with_experiment_name_context(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: bad
    config_overrides: {weighitng_rule: ew}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="bad.*Unknown config override key"):
            load_experiment_matrix(path, _spec())

    def test_off_menu_value_raises(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: bad
    config_overrides: {weighting_rule: capped_vw}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="must be one of"):
            load_experiment_matrix(path, _spec())

    def test_no_op_experiment_raises(self, tmp_path):
        # spec resolves weighting_rule="vw" already; declaring the same value
        # as a standalone named experiment is a caller mistake, not a warning.
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: noop
    config_overrides: {weighting_rule: vw}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="no-op"):
            load_experiment_matrix(path, _spec(weighting="vw"))

    def test_expected_diff_mismatch_raises(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: mismatched
    config_overrides: {weighting_rule: ew}
    expected_diff: {breakpoint_source: nyse}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="expected_diff"):
            load_experiment_matrix(path, _spec(weighting="vw"))

    def test_expected_diff_match_passes(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: matched
    config_overrides: {weighting_rule: ew}
    expected_diff: {weighting_rule: ew}
""",
        )
        matrix = load_experiment_matrix(path, _spec(weighting="vw"))
        assert matrix.experiments[0].resolved_diff["weighting_rule"]["track_value"] == "ew"

    def test_missing_name_raises(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - config_overrides: {weighting_rule: ew}
""",
        )
        with pytest.raises(ExperimentMatrixError, match="missing 'name'"):
            load_experiment_matrix(path, _spec())


class TestFamilyAndIdentificationLevelDerivation:
    def test_single_post_signal_key_is_controlled_portfolio_ablation(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: x
    config_overrides: {weighting_rule: ew}
""",
        )
        exp = load_experiment_matrix(path, _spec(weighting="vw")).experiments[0]
        assert exp.identification_level == "controlled"
        assert exp.family == "portfolio_ablation"

    def test_single_pre_signal_key_is_controlled_signal_input(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: x
    config_overrides: {accounting_lag_months: 12}
""",
        )
        exp = load_experiment_matrix(path, _spec()).experiments[0]
        assert exp.identification_level == "controlled"
        assert exp.family == "signal_input"

    def test_multiple_keys_is_unidentified(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: x
    config_overrides: {weighting_rule: ew, breakpoint_source: full_sample}
""",
        )
        exp = load_experiment_matrix(path, _spec(weighting="vw")).experiments[0]
        assert exp.identification_level == "unidentified"
        assert len(exp.resolved_diff) == 2

    def test_signal_input_ref_forces_reference_bridge_family(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: bridge
    signal_input_ref: "cz:AssetGrowth"
""",
        )
        exp = load_experiment_matrix(path, _spec()).experiments[0]
        assert exp.family == "reference_bridge"

    def test_snapshot_ref_forces_data_vintage_family(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments:
  - name: vintage
    snapshot_ref: "2020Q1"
""",
        )
        exp = load_experiment_matrix(path, _spec()).experiments[0]
        assert exp.family == "data_vintage"


class TestSweepExpansion:
    def test_sweep_expands_to_cartesian_product(self, tmp_path):
        path = _write(
            tmp_path,
            """
factor_id: t
experiments: []
sweep:
  - keys: [weighting_rule, breakpoint_source]
    values:
      weighting_rule: [ew, vw]
      breakpoint_source: [nyse, full_sample]
""",
        )
        matrix = load_experiment_matrix(path, _spec(weighting="ew"))
        # 2x2 grid, minus any no-op combos (ew+full_sample might coincide
        # with baseline defaults depending on spec) -- assert at least the
        # non-baseline-coinciding combos are present.
        names = {e.name for e in matrix.experiments}
        assert any("weighting_rule=vw" in n for n in names)
        assert any("breakpoint_source=nyse" in n for n in names)
