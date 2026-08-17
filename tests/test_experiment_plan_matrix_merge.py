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
from src.steps.step6_dual_track_controller import MultiTrackController, ExperimentPlan, HXZ_STANDARD_CONFIG
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
        # auto_attribution=False: this test means to exercise the plain
        # run_original/run_standardized toggles, not the 2026-08-16
        # auto-attribution default (covered separately below).
        plan = ExperimentPlan(factor_id="t", auto_attribution=False)

        runs = controller.run_experiment(_plugin(), _spec(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"original_method", "standardized_hxz"}
        assert all(r.status == "success" for r in runs)

    def test_run_original_false_skips_the_baseline(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=True, auto_attribution=False
        )

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
        assert factorial_tracks[0] == "factorial_weighting"

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

        specs = controller._factorial_track_specs(["weighting", "breakpoint"], baseline_config, HXZ_STANDARD_CONFIG)

        assert len(specs) == 3  # 2^2 - 1 (all-baseline excluded)
        names = {name for name, _ in specs}
        assert all(name.startswith("factorial_") for name in names)

    def test_degenerate_switch_where_baseline_already_matches_hxz_produces_zero(self):
        """When a switch's baseline value already equals HXZ's own value for
        that key, there is nothing to explore for that dimension -- this
        must produce zero tracks (not a duplicate-name collision)."""
        controller = MultiTrackController(runner=FakeRunner(), meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        baseline_config = build_config(_spec(), None)  # weighting_rule="vw" == HXZ's own "vw"

        specs = controller._factorial_track_specs(["weighting"], baseline_config, HXZ_STANDARD_CONFIG)

        assert specs == []


class TestSwitchesFlipped:
    """docs/step7-8.md Part V, Q2: `RunRecord.switches_flipped` is derived
    from `ExperimentSpec.resolved_diff` (never parsed from the track name),
    so attribution.py can identify which switches a factorial/ablation track
    varied without depending on any naming convention."""

    def test_factorial_tracks_get_switches_flipped_from_resolved_diff(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=True, run_standardized=False,
            factorial_switches=["weighting", "breakpoint"],
        )

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        by_track = {r.track: r for r in runs}
        assert by_track["original_method"].switches_flipped is None or by_track["original_method"].switches_flipped == {}
        assert by_track["factorial_weighting"].switches_flipped == {"weighting": "vw"}
        assert by_track["factorial_breakpoint"].switches_flipped == {"breakpoint": "nyse"}
        assert by_track["factorial_weighting_breakpoint"].switches_flipped == {
            "breakpoint": "nyse", "weighting": "vw",
        }

    def test_tracks_summary_carries_switches_flipped(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=True, run_standardized=False,
            factorial_switches=["weighting"],
        )

        controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = runner.comparison_calls[-1]["tracks"]
        assert tracks["factorial_weighting"]["switches_flipped"] == {"weighting": "vw"}
        assert not tracks["original_method"]["switches_flipped"]


class TestAutoAttribution:
    """docs/step6.md §4a's default (2026-08-16): when the caller leaves
    BOTH `ablation_switches`/`factorial_switches` empty (the step6 UI's own
    default since its 2026-08-16 simplification removed the manual switch
    pickers), auto-derive attribution tracks from the ACTUAL config diff --
    factorial when <=5 fields differ, one-at-a-time otherwise."""

    def test_default_plan_auto_generates_factorial_tracks_for_the_real_diff(self):
        """`_spec_ew()` differs from HXZ_STANDARD_CONFIG on 3 known switches
        (weighting, breakpoint, universe -- `minimal_resolved_spec`'s
        default `universe_filters=[]` vs HXZ's real exchcd/siccd/ceq
        filters) -- well under the factorial cutoff, so ①→③ should get a
        2^3-1=7-way factorial expansion automatically, with no
        ablation_switches/factorial_switches set by the caller."""
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=False)

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert "standardized_hxz" in tracks
        factorial_tracks = [t for t in tracks if t.startswith("factorial_")]
        # 2^3-1=7 non-baseline corners, minus the all-3-flipped corner
        # (identical to `standardized_hxz` itself -- see
        # test_cz_config_override_auto_generates_cz_factorial_tracks).
        assert len(factorial_tracks) == 6
        assert not any(
            all(s in t for s in ("weighting", "breakpoint", "universe")) for t in factorial_tracks
        )
        assert not any(t.startswith("ablation_") for t in tracks)

    def test_explicit_switches_disable_auto_attribution(self):
        """An explicit (even single-item) `ablation_switches`/
        `factorial_switches` list means the caller is taking manual control
        -- auto-attribution must not ALSO run and silently add extra tracks
        alongside the caller's explicit request."""
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=False,
            ablation_switches=["weighting"],
        )

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"ablation_weighting"}

    def test_auto_attribution_false_disables_it_entirely(self):
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(factor_id="t", run_original=False, auto_attribution=False)

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"standardized_hxz"}

    def test_cz_config_override_auto_generates_cz_factorial_tracks(self):
        """The ①→② comparison gets its OWN auto-attribution, independent of
        ①→③'s -- distinct `cz_factorial_*` naming so the two never collide
        even when they happen to flip the same switch. The all-switches-
        flipped corner is excluded (2^2-1-1=2 tracks, not 3): it would
        duplicate `cz_actual_config` itself, which already flips both
        switches simultaneously (docs/step7-8.md Part V, real production
        bug -- same redundancy as the single-switch case, generalized)."""
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=False,
            cz_config_override={"weighting_rule": "vw", "breakpoint_source": "nyse"},
        )

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert "cz_actual_config" in tracks
        cz_factorial_tracks = [t for t in tracks if t.startswith("cz_factorial_")]
        assert len(cz_factorial_tracks) == 2
        assert not any(
            all(s in t for s in ("weighting", "breakpoint")) for t in cz_factorial_tracks
        )
        assert not any(t.startswith("factorial_") and not t.startswith("cz_factorial_") for t in tracks)

    def test_single_switch_diff_skips_redundant_auto_attribution_track(self):
        """When only ONE known switch differs, the endpoint track itself
        (`cz_actual_config`) already IS that switch's flip -- no
        `cz_factorial_<switch>` should be generated alongside it, since it
        would duplicate the exact same config under a second name and
        `attribution.py` would then have to refuse it as an ambiguous
        duplicate (docs/step7-8.md Part V, real production bug)."""
        runner = FakeRunner()
        controller = MultiTrackController(runner=runner, meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        plan = ExperimentPlan(
            factor_id="t", run_original=False, run_standardized=False,
            cz_config_override={"weighting_rule": "vw"},
        )

        runs = controller.run_experiment(_plugin(), _spec_ew(), plan, snapshot_id="snap1")

        tracks = {r.track for r in runs}
        assert tracks == {"cz_actual_config"}

    def test_auto_attribution_falls_back_to_oat_above_four_switches(self):
        """More than MAX_FACTORIAL_SWITCHES (4) differing fields must fall
        back to one-at-a-time (ablation_*) instead of a full 2^n factorial --
        exercised directly against `_auto_attribution_specs` with a
        hand-built target differing on all 6 known switches, since a real
        spec/HXZ diff practically never reaches 6."""
        controller = MultiTrackController(runner=FakeRunner(), meta_coder=FakeMetaCoder(), sandbox=FakeSandbox())
        baseline_config = build_config(_spec_ew(), None)
        target_config = dict(baseline_config)
        target_config.update({
            "breakpoint_source": "nyse",
            "weighting_rule": "vw",
            "accounting_lag_months": (baseline_config["accounting_lag_months"] or 0) + 1,
            "missing_action": "unspecified",
            "rebalance_frequency": "quarterly",
            "universe_filters": [{"field": "exchcd", "op": "in", "value": [1]}],
        })

        specs = controller._auto_attribution_specs(
            _spec_ew(), baseline_config, target_config,
            factorial_prefix="factorial", ablation_prefix="ablation",
        )

        assert len(specs) == 6
        assert all(s.name.startswith("ablation_") for s in specs)
