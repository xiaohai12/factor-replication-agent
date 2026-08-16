"""Tests for the ExperimentPlan/ExperimentMatrix merge (2026-08-04,
docs/decision-log.md): `MultiTrackController.run_experiment` is now a thin
adapter over `run_from_matrix` via `_plan_to_matrix`, so both entry points
share one execution implementation. Also covers `factorial_switches`
(declared on `ExperimentPlan` since early on but never executed until this
merge) as a real full-factorial expansion.
"""

from __future__ import annotations

from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step6_dual_track_controller import MultiTrackController, ExperimentPlan
from src.steps.step3_codegen.registry import build_config
from tests._spec_test_helpers import minimal_resolved_spec, spec_factor_id


def _spec():
    return minimal_resolved_spec("t")


def _spec_ew():
    """A spec whose own weighting ("ew") genuinely DIFFERS from HXZ's
    standardized default ("vw") -- needed so a factorial expansion over
    "weighting" actually produces 2 distinct values to combine, rather than
    degenerately coinciding with `_spec()`'s own "vw" default.
    Explicitly sets breakpoint_source to full_sample to keep tests independent
    of the default breakpoint basis value."""
    return minimal_resolved_spec("t", weighting="ew", breakpoint_source="full_sample")


def _plugin() -> PluginRecord:
    return PluginRecord(plugin_id="t_v1", factor_id="t", code="def compute_signal(df): return df", code_hash="deadbeef")


class FakeRunner:
    def __init__(self):
        self.build_calls: list[dict] = []
        self.comparison_calls: list[dict] = []
        self.comparison_path = None

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None, precomputed_signal_path=None):
        self.build_calls.append({"track_name": track_name, "config_overrides": dict(config_overrides or {})})
        return {"config": dict(config_overrides or {}), "script_text": plugin.code}

    def execute(self, built):
        return {"metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0}, "config": built["config"]}

    def make_run_record(self, spec, plugin, track, result):
        metrics = result["metrics"]
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}", factor_id=spec_factor_id(spec), plugin_id=plugin.plugin_id,
            track=track, code_hash=plugin.code_hash,
            metrics=RunMetrics(mean_return=metrics.get("mean_monthly_return"), t_stat=metrics.get("t_stat")),
            status="success",
        )

    def make_failed_run_record(self, spec, plugin, track, config_overrides, log):
        return RunRecord(
            run_id=f"{spec_factor_id(spec)}_{track}_failed", factor_id=spec_factor_id(spec), plugin_id=plugin.plugin_id,
            track=track, metrics=RunMetrics(), status="failed", logs=[log],
        )

    def write_comparison_summary(self, spec, tracks, snapshot_id=None, diff_result=None, batch_info=None):
        self.comparison_calls.append({"tracks": tracks, "batch_info": batch_info})
        return self.comparison_path


class FakeMetaCoder:
    llm_client = object()


class FakeSandbox:
    def validate(self, plugin, spec, script_text=None, data=None):
        return ValidationReport(passed=True)


class TestRunExperimentDelegatesToRunFromMatrix:
    def test_default_plan_produces_original_and_standardized_tracks(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t")

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"original_method", "standardized_hxz"}
        assert all(r.status == "success" for r in runs)

    def test_run_original_false_skips_the_baseline(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=False, run_standardized=True)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"standardized_hxz"}
        assert "original_method" not in tracks

    def test_ablation_switches_produce_ablation_tracks_with_derived_tags(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=True, run_standardized=False,
            ablation_switches=["weighting"],
        )

        # _spec_ew() so the ablation actually changes something (baseline
        # "ew" -> HXZ "vw" is a real 1-key diff); _spec()'s own weighting
        # default happens to already equal HXZ's, which would make this a
        # no-op ablation (identification_level="unidentified", not
        # "controlled") -- a real, if coincidental, edge case, not what this
        # test means to exercise.
        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        ablation_run = next(r for r in runs if r.track == "ablation_weighting")
        assert any("family='portfolio_ablation'" in log for log in ablation_run.logs)
        assert any("identification_level='controlled'" in log for log in ablation_run.logs)

    def test_experiment_spec_hash_recorded_for_plan_based_runs_too(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t")

        controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        # Bonus of the merge: even the legacy ExperimentPlan path now gets a
        # real experiment_spec_hash in its batch info (run_from_matrix
        # always records one), which it never had before.
        batch_info = runner.comparison_calls[0]["batch_info"]
        assert batch_info["experiment_spec_hash"]
        matrix = controller._plan_to_matrix(plan, _spec())
        assert matrix.experiment_spec_hash == batch_info["experiment_spec_hash"]

    def test_cz_config_override_produces_a_cz_actual_config_track(self):
        # docs/step6.md gap #1: a human-reviewed C_cz override becomes its
        # own track, alongside ①/③, in the SAME batch.
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_standardized=False,
            cz_config_override={"weighting_rule": "ew"},
        )

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert "cz_actual_config" in tracks
        cz_run = next(r for r in runs if r.track == "cz_actual_config")
        assert runner.build_calls[
            next(i for i, c in enumerate(runner.build_calls) if c["track_name"] == "cz_actual_config")
        ]["config_overrides"] == {"weighting_rule": "ew"}

    def test_no_cz_config_override_means_no_cz_actual_config_track(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_standardized=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        assert "cz_actual_config" not in {r.track for r in runs}


class TestFactorialSwitches:
    def test_single_switch_factorial_produces_one_non_baseline_combo(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=True, run_standardized=False,
            factorial_switches=["weighting"],
        )

        # _spec_ew(): baseline "ew" vs HXZ "vw" -- 2 genuinely distinct
        # values to combine over. With plain _spec() (weighting already
        # "vw" == HXZ's own default), BOTH cartesian points degenerate to
        # the baseline itself and this would correctly produce ZERO tracks
        # (nothing to explore when the two options coincide) -- a real,
        # separate case, not what this test means to exercise.
        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert "original_method" in tracks
        factorial_tracks = [t for t in tracks if t.startswith("factorial_")]
        assert len(factorial_tracks) == 1
        assert "weighting_rule=vw" in factorial_tracks[0]

    def test_two_switch_factorial_produces_three_non_baseline_combos(self):
        """2^2 = 4 combos, minus the all-baseline corner (redundant with
        original_method) = 3."""
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=False,
            factorial_switches=["weighting", "breakpoint"],
        )

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        factorial_tracks = [r.track for r in runs if r.track.startswith("factorial_")]
        assert len(factorial_tracks) == 3

    def test_unknown_switch_name_produces_no_tracks(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=False,
            factorial_switches=["not_a_real_switch"],
        )

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")
        assert runs == []

    def test_factorial_track_specs_directly(self):
        controller = MultiTrackController(runner=FakeRunner(), meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        baseline_config = build_config(_spec_ew(), None)

        specs = controller._factorial_track_specs(["weighting", "breakpoint"], baseline_config)

        assert len(specs) == 3  # 2^2 - 1 (all-baseline excluded)
        names = {name for name, _ in specs}
        assert all(name.startswith("factorial_") for name in names)

    def test_degenerate_switch_where_baseline_already_matches_hxz_produces_zero(self):
        """When a switch's baseline value already equals HXZ's own value for
        that key, there is nothing to explore for that dimension -- this
        must produce zero tracks (not a duplicate-name collision)."""
        controller = MultiTrackController(runner=FakeRunner(), meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        baseline_config = build_config(_spec(), None)  # weighting_rule="vw" == HXZ's own "vw"

        specs = controller._factorial_track_specs(["weighting"], baseline_config)

        assert specs == []
