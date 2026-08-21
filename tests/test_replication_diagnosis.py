"""Tests for the replication-diagnosis layer (deterministic bundle + step 8).

No real LLM is ever called: `FakeLLM` returns a canned JSON payload. What
matters here is the *discipline*, not the wording:

- the evidence bundle's arithmetic and its "missing evidence != zero" handling;
- the flat `evidence_keys` whitelist the LLM is allowed to cite;
- the validator rejecting hallucinated numbers, unknown keys, and claim types
  cited with the wrong kind of evidence;
- the renderer taking every figure from the bundle rather than from claim text.
"""

from __future__ import annotations

import json

import pytest

from src.infra.models.diagnosis import DiagnosisClaim, ReplicationDiagnosisReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step7_replication_diff import ReplicationDiff, ReplicationDiffResult, safe_diff_ablation
from src.steps.step7_replication_diff.bundle import (
    SIGNIFICANCE_T_THRESHOLD,
    build_config_diff,
    build_evidence_bundle,
    build_gap_closure,
    build_gap_decomposition,
    build_menu_deviations,
    build_publication_decay,
    build_robustness_summary,
    build_spec_quality,
    build_three_term_identities,
    build_three_term_identity,
    build_universe_description,
    build_t_channel_decomposition,
    build_track_vs_paper,
    classify_overall,
    flatten,
    stage_of,
)
from src.steps.step8_diagnosis import ReplicationDiagnoser, validate_claims
from src.steps.step8_diagnosis.render import deterministic_sentence, render_markdown, report_to_jsonable
from src.steps.step8_diagnosis.summary import (
    build_deterministic_summary,
    build_spec_quality_summary,
    build_three_term_summaries,
    build_vs_paper_summary,
    _build_robustness_summary,
    _fold_claim_evidence_into_details,
)
from tests._spec_test_helpers import minimal_resolved_spec


PAPER = {
    "return_type": "raw",
    "main_spread": -0.010,
    "main_t_stat": -5.04,
}

TRACKS = {
    "original_method": {
        "config": {
            "breakpoint_source": "full_sample",
            "rebalance_frequency": "annual",
            "holding_period_months": 12,
            "weighting_rule": "vw",
        },
        "metrics": {"mean_return": -0.008, "t_stat": -4.0, "n_months": 870},
    },
    "standardized_hxz": {
        "config": {
            "breakpoint_source": "nyse",
            "rebalance_frequency": "monthly",
            "holding_period_months": 1,
            "weighting_rule": "vw",
        },
        "metrics": {"mean_return": 0.002, "t_stat": 0.8, "n_months": 876},
    },
}


class TestFlatten:
    def test_nested_dicts_and_lists_become_dotted_keys(self):
        flat = flatten({"a": {"b": 1}, "c": [{"d": 2}, 3]})
        assert flat == {"a.b": 1, "c[0].d": 2, "c[1]": 3}

    def test_prefix_is_prepended(self):
        assert flatten({"x": 1}, prefix="root") == {"root.x": 1}


class TestTrackVsPaper:
    def test_same_sign_gives_deltas_and_agreement(self):
        vs = build_track_vs_paper(PAPER, TRACKS["original_method"]["metrics"])
        assert vs["track_spread_metric"] == "mean_return"
        assert vs["sign_agrees"] is True
        assert vs["spread_delta"] == 0.002
        assert vs["abs_spread_ratio"] == 0.8
        assert vs["t_stat_comparable"] is True
        assert vs["t_stat_delta"] == 1.04
        assert vs["paper_significant"] is True
        assert vs["track_significant"] is True
        assert vs["significance_agrees"] is True
        assert vs["significance_threshold"] == SIGNIFICANCE_T_THRESHOLD
        # Both PAPER's t=-5.04 and the track's t=-4.0 clear all three HXZ
        # hurdles (1.96/2.78/3.39) -- docs/step7-8.md Q7.
        assert vs["paper_significance_tier"] == 3
        assert vs["track_significance_tier"] == 3

    def test_opposite_sign_is_flagged(self):
        vs = build_track_vs_paper(PAPER, TRACKS["standardized_hxz"]["metrics"])
        assert vs["sign_agrees"] is False
        assert vs["track_significant"] is False
        assert vs["significance_agrees"] is False
        assert vs["track_significance_tier"] == 0

    def test_alpha_headline_compares_against_our_alpha_not_the_raw_spread(self):
        paper = {"return_type": "three-factor alpha", "main_spread": -0.007, "main_t_stat": -3.84}
        metrics = {"mean_return": 0.001, "alpha_ff3": -0.005, "t_stat": 0.75}
        vs = build_track_vs_paper(paper, metrics)
        assert vs["track_spread_metric"] == "alpha_ff3"
        assert vs["track_spread"] == -0.005
        assert vs["sign_agrees"] is True
        # We store no alpha t-stat, so the two t-stats are not like-for-like.
        assert vs["t_stat_comparable"] is False
        assert vs["t_stat_delta"] is None

    def test_missing_paper_numbers_are_inconclusive_not_zero(self):
        vs = build_track_vs_paper({}, {"mean_return": 0.01, "t_stat": 2.0})
        assert vs["sign_agrees"] is None
        assert vs["spread_delta"] is None
        assert vs["paper_significant"] is None
        assert vs["significance_agrees"] is None


class TestClassifyOverall:
    def test_unknown_sign_is_inconclusive(self):
        assert classify_overall({"sign_agrees": None}) == "inconclusive"

    def test_both_significant_same_sign_is_reproduced(self):
        vs = {
            "sign_agrees": True, "t_stat_comparable": True,
            "paper_significant": True, "track_significant": True,
        }
        assert classify_overall(vs) == "reproduced"

    def test_both_significant_opposite_sign_is_contradicted(self):
        vs = {
            "sign_agrees": False, "t_stat_comparable": True,
            "paper_significant": True, "track_significant": True,
        }
        assert classify_overall(vs) == "contradicted"

    def test_paper_significant_ours_not_is_not_reproduced_regardless_of_sign(self):
        vs = {
            "sign_agrees": False, "t_stat_comparable": True,
            "paper_significant": True, "track_significant": False,
        }
        assert classify_overall(vs) == "not_reproduced"
        vs["sign_agrees"] = True
        assert classify_overall(vs) == "not_reproduced"

    def test_paper_insignificant_ours_significant_same_sign_is_reproduced(self):
        vs = {
            "sign_agrees": True, "t_stat_comparable": True,
            "paper_significant": False, "track_significant": True,
        }
        assert classify_overall(vs) == "reproduced"

    def test_paper_insignificant_ours_significant_opposite_sign_is_inconclusive(self):
        vs = {
            "sign_agrees": False, "t_stat_comparable": True,
            "paper_significant": False, "track_significant": True,
        }
        assert classify_overall(vs) == "inconclusive"

    def test_neither_significant_is_inconclusive(self):
        vs = {
            "sign_agrees": True, "t_stat_comparable": True,
            "paper_significant": False, "track_significant": False,
        }
        assert classify_overall(vs) == "inconclusive"

    def test_alpha_basis_t_stat_not_comparable_falls_back_to_sign_only(self):
        vs = {"sign_agrees": True, "t_stat_comparable": False}
        assert classify_overall(vs) == "reproduced"
        vs["sign_agrees"] = False
        assert classify_overall(vs) == "contradicted"


class TestConfigDiff:
    def test_diffs_each_track_against_the_original_method_baseline(self):
        diff = build_config_diff(TRACKS)
        assert diff["baseline_track"] == "original_method"
        pair = diff["pairs"]["standardized_hxz"]
        assert pair["changed_keys"] == [
            "breakpoint_source",
            "holding_period_months",
            "rebalance_frequency",
        ]
        assert "weighting_rule" not in pair["changed_keys"]
        assert pair["details"]["breakpoint_source"]["baseline_value"] == "full_sample"
        assert pair["details"]["breakpoint_source"]["track_value"] == "nyse"

    def test_changed_keys_are_tagged_with_their_pipeline_stage(self):
        diff = build_config_diff(TRACKS)
        pair = diff["pairs"]["standardized_hxz"]
        assert pair["changed_stages"] == ["portfolio"]
        assert pair["keys_by_stage"]["portfolio"] == pair["changed_keys"]

    def test_unknown_config_key_is_unclassified_rather_than_dropped(self):
        assert stage_of("breakpoint_source") == "portfolio"
        assert stage_of("accounting_lag_months") == "signal_input"
        assert stage_of("some_future_key") == "unclassified"


class TestGapDecomposition:
    def test_absent_diff_is_reported_as_unavailable_with_a_reason(self):
        gap = build_gap_decomposition(None)
        assert gap["available"] is False
        assert "requires" in gap["reason"]
        assert "contributions" not in gap

    def test_no_ablation_tracks_is_missing_evidence_not_zero_contributions(self):
        result = ReplicationDiffResult(factor_id="t", total_gap=1.5)
        gap = build_gap_decomposition(result)
        assert gap["available"] is False
        assert "no ablation" in gap["reason"]
        assert gap["total_gap"] == 1.5
        assert "contributions" not in gap

    def test_measured_contributions_are_exposed(self):
        result = ReplicationDiffResult(
            factor_id="t",
            total_gap=1.5,
            contributions={"breakpoint": 1.0, "weighting": 0.4},
            explained_fraction=0.933,
            residual=0.1,
        )
        gap = build_gap_decomposition(result)
        assert gap["available"] is True
        assert gap["contributions"] == {"breakpoint": 1.0, "weighting": 0.4}


class TestSafeDiffAblation:
    def test_returns_none_instead_of_raising_when_tracks_are_missing(self):
        assert safe_diff_ablation([]) is None


class TestDiffAblationInSample:
    """`diff_ablation` must prefer `metrics.by_sample_period.insamp.t_stat`
    (the paper's own sample window) over the top-level `t_stat` (this
    engine's full extended history) -- same preference `bundle.py`'s
    `_in_sample_metrics`/`attribution._in_sample_mean_return` already apply."""

    def _run(self, track: str, t_stat: float, insamp_t_stat: float | None = None) -> RunRecord:
        metrics = RunMetrics(
            t_stat=t_stat,
            by_sample_period={"insamp": {"t_stat": insamp_t_stat}} if insamp_t_stat is not None else None,
        )
        return RunRecord(run_id=track, factor_id="t", plugin_id="p", track=track, metrics=metrics)

    def test_prefers_in_sample_t_stat_over_full_history(self):
        runs = [
            self._run("original_method", t_stat=10.0, insamp_t_stat=2.0),
            self._run("standardized_hxz", t_stat=8.0, insamp_t_stat=1.0),
        ]
        result = ReplicationDiff().diff_ablation(runs)
        assert result.original_tstat == pytest.approx(2.0)
        assert result.standardized_tstat == pytest.approx(1.0)
        assert result.total_gap == pytest.approx(1.0)

    def test_falls_back_to_full_history_when_no_in_sample_window(self):
        runs = [
            self._run("original_method", t_stat=10.0),
            self._run("standardized_hxz", t_stat=8.0),
        ]
        result = ReplicationDiff().diff_ablation(runs)
        assert result.original_tstat == pytest.approx(10.0)
        assert result.standardized_tstat == pytest.approx(8.0)


class TestTChannelDecomposition:
    """docs/step7-8.md Q1/Q5: t-stat's own exact log-identity decomposition,
    a companion to (not a replacement for) the mean_return-based
    gap_decomposition/Shapley attribution."""

    def test_non_degenerate_channels_sum_exactly_to_the_log_t_ratio(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.005, "t_stat": 2.0, "n_months": 400}},
            "standardized_hxz": {"metrics": {"mean_return": 0.008, "t_stat": 3.6, "n_months": 400}},
        }
        result = build_t_channel_decomposition(tracks)
        assert result["available"] is True
        entry = result["tracks"]["standardized_hxz"]
        assert entry["degenerate"] is False
        channels = entry["channels"]
        assert channels["mean_return"] + channels["volatility"] + channels["sample_size"] == pytest.approx(
            entry["log_t_ratio"], rel=1e-9
        )
        assert entry["channel_sum_check"] == pytest.approx(entry["log_t_ratio"], rel=1e-9)

    def test_sample_size_channel_isolates_a_pure_n_months_change(self):
        # Same mean_return everywhere; t_stat only moves because n_months doubles
        # (t scales with sqrt(N) at fixed mean/vol) -- mean_return/volatility
        # channels should be ~0, sample_size should carry the whole ratio.
        import math

        tracks = {
            "original_method": {"metrics": {"mean_return": 0.005, "t_stat": 2.0, "n_months": 400}},
            "double_n": {"metrics": {"mean_return": 0.005, "t_stat": 2.0 * math.sqrt(2), "n_months": 800}},
        }
        result = build_t_channel_decomposition(tracks)
        entry = result["tracks"]["double_n"]
        assert entry["channels"]["mean_return"] == pytest.approx(0.0, abs=1e-9)
        assert entry["channels"]["volatility"] == pytest.approx(0.0, abs=1e-9)
        assert entry["channels"]["sample_size"] == pytest.approx(0.5 * math.log(2), rel=1e-9)

    def test_negative_baseline_mean_return_degenerates_to_abs_t_delta(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": -0.005, "t_stat": -2.0, "n_months": 400}},
            "standardized_hxz": {"metrics": {"mean_return": 0.008, "t_stat": 3.6, "n_months": 400}},
        }
        result = build_t_channel_decomposition(tracks)
        entry = result["tracks"]["standardized_hxz"]
        assert entry["degenerate"] is True
        assert "positive" in entry["reason"]
        assert entry["t_stat_abs_delta"] == pytest.approx(3.6 - 2.0)
        assert "channels" not in entry

    def test_opposite_signed_track_mean_return_also_degenerates(self):
        # Both individually positive-required-baseline case aside: a track whose
        # mean_return is negative while baseline's is positive must degenerate too.
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.005, "t_stat": 2.0, "n_months": 400}},
            "flipped": {"metrics": {"mean_return": -0.003, "t_stat": -1.5, "n_months": 400}},
        }
        result = build_t_channel_decomposition(tracks)
        entry = result["tracks"]["flipped"]
        assert entry["degenerate"] is True

    def test_missing_metrics_degenerates_with_a_reason_not_a_crash(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.005, "t_stat": 2.0, "n_months": 400}},
            "no_metrics": {"metrics": {}},
        }
        result = build_t_channel_decomposition(tracks)
        entry = result["tracks"]["no_metrics"]
        assert entry["degenerate"] is True
        assert entry["t_stat_abs_delta"] is None

    def test_no_tracks_is_unavailable(self):
        result = build_t_channel_decomposition({})
        assert result["available"] is False

    def test_wired_into_evidence_bundle_and_citable(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        assert "t_channel_decomposition" in bundle
        key = "t_channel_decomposition.tracks.standardized_hxz.degenerate"
        assert key in bundle["evidence_keys"]


class TestEvidenceBundle:
    def test_bundle_exposes_derived_config_diff_and_a_citable_key_whitelist(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        keys = bundle["evidence_keys"]

        assert bundle["derived"]["baseline_track"] == "original_method"
        assert bundle["derived"]["overall_tag"] == "reproduced"
        assert keys["derived.tracks.original_method.vs_paper.sign_agrees"] is True
        assert keys["tracks.standardized_hxz.metrics.t_stat"] == 0.8
        assert keys["paper_reported.main_spread"] == -0.010
        assert (
            keys["config_diff.pairs.standardized_hxz.details.breakpoint_source.track_value"]
            == "nyse"
        )
        assert keys["gap_decomposition.available"] is False

    def test_config_diff_and_gap_decomposition_carry_identification_level(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        assert bundle["config_diff"]["identification_level"] == "observational"
        assert bundle["gap_decomposition"]["identification_level"] == "unidentified"

        result = ReplicationDiffResult(
            factor_id="t", total_gap=1.5, contributions={"breakpoint": 1.0}
        )
        gap = build_gap_decomposition(result)
        assert gap["identification_level"] == "harmonized"
        assert "one-at-a-time" in gap["interaction_caveat"]

    def test_every_citable_value_is_a_scalar(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        assert not any(
            isinstance(v, (dict, list)) for v in bundle["evidence_keys"].values()
        )

    def test_empty_tracks_is_inconclusive(self):
        bundle = build_evidence_bundle(PAPER, {})
        assert bundle["derived"]["overall_tag"] == "inconclusive"
        assert bundle["config_diff"]["baseline_track"] is None


class TestShapleyAndSignificanceWiring:
    """docs/step7-8.md Part V: `build_evidence_bundle` always computes
    `shapley_attribution` (only needs `mean_return`, already in `tracks`),
    but `paired_tests`/`joint_test` need `results_dir` (the on-disk monthly
    return series) and report `available=False` without it, never raise."""

    def test_without_results_dir_paired_and_joint_are_unavailable_shapley_is_not(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        assert bundle["paired_tests"]["available"] is False
        assert bundle["joint_test"]["available"] is False
        # TRACKS has no switches_flipped set at all, so shapley_attribution
        # is unavailable for its OWN reason (no switches), not because
        # results_dir is missing -- distinct failure modes.
        assert bundle["shapley_attribution"]["available"] is False
        assert "switches_flipped" in bundle["shapley_attribution"]["reason"]

    def test_evidence_keys_include_the_new_blocks(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        assert "paired_tests.available" in bundle["evidence_keys"]
        assert "joint_test.available" in bundle["evidence_keys"]
        assert "shapley_attribution.available" in bundle["evidence_keys"]

    def test_two_comparison_lines_no_longer_collide_on_the_same_switch_name(self):
        """The real bug this per-line split fixes: a batch running BOTH
        \u2460\u2192\u2461 (`cz_factorial_universe`) and \u2460\u2192\u2462 (`factorial_universe`) used to have
        both tracks fight over the same "universe" slot in one shared
        calculation. Splitting by comparison line means each is computed
        entirely independently and neither is ever flagged ambiguous."""
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.01}},
            "factorial_universe": {
                "metrics": {"mean_return": 0.02},
                "switches_flipped": {"universe": "hxz_value"},
            },
            "cz_factorial_universe": {
                "metrics": {"mean_return": 0.03},
                "switches_flipped": {"universe": "cz_value"},
            },
        }
        bundle = build_evidence_bundle(PAPER, tracks)
        shapley = bundle["shapley_attribution"]
        assert shapley["to_hxz"]["available"] is True
        assert shapley["to_hxz"]["shapley_effects"]["universe"] == pytest.approx(0.01)
        assert shapley["to_cz"]["available"] is True
        assert shapley["to_cz"]["shapley_effects"]["universe"] == pytest.approx(0.02)

    def test_with_results_dir_and_switches_flipped_shapley_is_computed(self, tmp_path):
        tracks = {
            "original_method": {
                "config": TRACKS["original_method"]["config"],
                "metrics": {**TRACKS["original_method"]["metrics"]},
            },
            "factorial_a": {
                "config": TRACKS["standardized_hxz"]["config"],
                "metrics": {"mean_return": -0.006, "t_stat": -3.0, "n_months": 870},
                "switches_flipped": {"a": "x"},
            },
        }
        bundle = build_evidence_bundle(PAPER, tracks, results_dir=tmp_path)
        # `factorial_a` doesn't start with "cz_" -- it belongs to the "to_hxz"
        # comparison line (docs/step7-8.md Part V's per-line split), so the
        # result is nested one level deeper than a batch with no switches at all.
        assert bundle["shapley_attribution"]["to_hxz"]["available"] is True
        assert bundle["shapley_attribution"]["to_hxz"]["shapley_effects"]["a"] == pytest.approx(0.002)
        # No <track>.csv files exist under tmp_path at all (not even the
        # baseline's), so the two series-based checks stay unavailable even
        # though results_dir itself was supplied.
        assert bundle["paired_tests"]["to_hxz"]["available"] is False
        assert bundle["joint_test"]["to_hxz"]["available"] is False


class TestGapClosure:
    """docs/step7-8.md Part XII: does the sum of catalogued per-switch
    effects to C&Z actually explain the total to_cz gap, or leave a
    residual not produced by any of them?"""

    def test_unavailable_without_cz_actual_config_track(self):
        derived = {
            "baseline_track": "original_method",
            "tracks": {"original_method": {"vs_paper": {"track_spread": -0.008}}},
        }
        section = build_gap_closure(derived, {})
        assert section["available"] is False
        assert "cz_actual_config" in section["reason"]

    def test_unavailable_without_a_resolvable_spread(self):
        derived = {
            "baseline_track": "original_method",
            "tracks": {
                "original_method": {"vs_paper": {"track_spread": None}},
                "cz_actual_config": {"vs_paper": {"track_spread": 0.006}},
            },
        }
        section = build_gap_closure(derived, {})
        assert section["available"] is False

    def test_total_gap_and_residual_computed_from_available_switch_effects(self):
        derived = {
            "baseline_track": "original_method",
            "tracks": {
                "original_method": {"vs_paper": {"track_spread": -0.0031}},
                "cz_actual_config": {"vs_paper": {"track_spread": 0.0062}},
            },
        }
        paired_tests = {
            "to_cz": {
                "per_switch": {
                    "weighting": {"available": True, "mean_diff": -0.00764},
                    "universe": {"available": True, "mean_diff": 0.00043},
                    "lag": {"available": False, "reason": "no overlapping in-sample months"},
                }
            }
        }
        section = build_gap_closure(derived, paired_tests)
        assert section["available"] is True
        assert section["total_gap"] == pytest.approx(-0.0093)
        assert section["sum_of_switch_effects"] == pytest.approx(-0.00721)
        assert section["residual"] == pytest.approx(-0.0093 - -0.00721)
        assert section["explained_fraction"] == pytest.approx(-0.00721 / -0.0093)
        assert "lag" not in section["contributions"]
        assert "interaction_caveat" in section

    def test_no_switch_evidence_reports_gap_but_no_contributions(self):
        derived = {
            "baseline_track": "original_method",
            "tracks": {
                "original_method": {"vs_paper": {"track_spread": -0.003}},
                "cz_actual_config": {"vs_paper": {"track_spread": 0.006}},
            },
        }
        section = build_gap_closure(derived, {"to_cz": {"per_switch": {}}})
        assert section["available"] is True
        assert section["total_gap"] == pytest.approx(-0.009)
        assert section["sum_of_switch_effects"] is None
        assert section["residual"] is None
        assert "no per-switch paired-test evidence" in section["reason"]

    def test_wired_into_evidence_bundle_with_a_real_cz_track(self, tmp_path):
        tracks = {
            "original_method": {
                "config": {},
                "metrics": {"mean_return": -0.0031, "t_stat": -1.12, "n_months": 500},
            },
            "cz_actual_config": {
                "config": {},
                "metrics": {"mean_return": 0.0062, "t_stat": 2.41, "n_months": 500},
            },
            "cz_factorial_weighting": {
                "config": {},
                "metrics": {"mean_return": 0.00454, "t_stat": 1.5, "n_months": 500},
                "switches_flipped": {"weighting": "ew"},
            },
        }
        bundle = build_evidence_bundle(PAPER, tracks, results_dir=tmp_path)
        gap_closure = bundle["gap_closure"]["to_cz"]
        assert gap_closure["available"] is True
        assert gap_closure["total_gap"] == pytest.approx(-0.0031 - 0.0062)
        assert "gap_closure.to_cz.total_gap" in bundle["evidence_keys"]


class TestThreeTermIdentity:
    """docs/paper-outline.md C1: an EXTERNAL implementer's distance from the
    paper's own reported spread, split into signal+environment, config, and
    agent-replication residual."""

    DERIVED = {
        "baseline_track": "original_method",
        "tracks": {
            "original_method": {"vs_paper": {"track_spread": -0.008}},
            "cz_actual_config": {"vs_paper": {"track_spread": -0.005}},
        },
    }
    EXTERNAL = {
        "spread": -0.004,
        "t_stat": -2.1,
        "sample_start_year": 1968,
        "sample_end_year": 2002,
        "window_adjustable": False,
        "window_sensitivity_spread": None,
        "source": "SignalDoc.csv",
    }

    def test_terms_telescope_exactly_to_the_total_gap(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, self.EXTERNAL, "cz_actual_config", "cz"
        )
        assert section["available"] is True
        assert section["total_gap"] == pytest.approx(-0.004 - -0.010)
        # external - hybrid, hybrid - baseline, baseline - paper
        assert section["terms"]["signal_and_environment"] == pytest.approx(-0.004 - -0.005)
        assert section["terms"]["config"] == pytest.approx(-0.005 - -0.008)
        assert section["terms"]["agent_replication_residual"] == pytest.approx(-0.008 - -0.010)
        # The identity telescopes, so the residual is zero by construction --
        # it is emitted purely as an arithmetic audit check.
        assert section["residual"] == pytest.approx(0.0, abs=1e-12)
        assert section["terms_sum_check"] == pytest.approx(section["total_gap"])

    def test_largest_term_is_by_absolute_size(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, self.EXTERNAL, "cz_actual_config", "cz"
        )
        assert section["largest_term"] == "config"

    def test_purity_notes_and_window_caveat_travel_with_the_numbers(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, self.EXTERNAL, "cz_actual_config", "cz"
        )
        assert set(section["term_purity_notes"]) == set(section["terms"])
        assert section["window_basis"]["external_window_adjustable"] is False
        assert section["window_basis"]["paper_sample_start_year"] is None  # PAPER carries no window
        assert "window/basis mismatch" in section["window_basis"]["caveat"]

    def test_can_never_be_better_than_observational(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, self.EXTERNAL, "cz_actual_config", "cz"
        )
        assert section["identification_level"] == "observational"

    def test_missing_external_reference_is_unavailable_not_zero(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, None, "cz_actual_config", "cz"
        )
        assert section["available"] is False
        assert "external cz reference spread" in section["reason"]
        assert "terms" not in section

    def test_missing_hybrid_track_is_unavailable(self):
        section = build_three_term_identity(
            self.DERIVED, PAPER, self.EXTERNAL, "standardized_hxz", "hxz"
        )
        assert section["available"] is False
        assert "standardized_hxz" in section["reason"]

    def test_both_endpoints_always_present_even_when_unresolvable(self):
        sections = build_three_term_identities(self.DERIVED, PAPER, {"cz": self.EXTERNAL})
        assert set(sections) == {"cz", "hxz"}
        assert sections["cz"]["available"] is True
        assert sections["hxz"]["available"] is False

    def test_wired_into_evidence_bundle_and_citable(self, tmp_path):
        tracks = {
            "original_method": {"config": {}, "metrics": {"mean_return": -0.008, "t_stat": -2.0, "n_months": 400}},
            "cz_actual_config": {"config": {}, "metrics": {"mean_return": -0.005, "t_stat": -1.4, "n_months": 400}},
        }
        bundle = build_evidence_bundle(
            PAPER, tracks, results_dir=tmp_path, external_references={"cz": self.EXTERNAL}
        )
        assert bundle["three_term_identity"]["cz"]["available"] is True
        assert "three_term_identity.cz.terms.config" in bundle["evidence_keys"]
        assert "three_term_identity.cz.total_gap" in bundle["evidence_keys"]

    def test_absent_external_references_does_not_raise(self, tmp_path):
        tracks = {
            "original_method": {"config": {}, "metrics": {"mean_return": -0.008, "t_stat": -2.0, "n_months": 400}},
        }
        bundle = build_evidence_bundle(PAPER, tracks, results_dir=tmp_path)
        assert bundle["three_term_identity"]["cz"]["available"] is False
        assert bundle["three_term_identity"]["hxz"]["available"] is False


class TestThreeTermClaimValidation:
    """The step8 validator must accept a well-formed three_term_gap_component
    claim and reject one that cites the section's metadata instead of a term."""

    EVIDENCE_KEYS = {
        "three_term_identity.cz.terms.config": 0.003,
        "three_term_identity.cz.terms.signal_and_environment": 0.001,
        "three_term_identity.cz.total_gap": 0.006,
        "three_term_identity.cz.window_basis.external_window_adjustable": False,
    }

    def _claim(self, **overrides):
        raw = {
            "claim_type": "three_term_gap_component",
            "relation": "larger",
            "comparison_line": "cz",
            "text": "the configuration component dominates",
            "evidence_keys": ["three_term_identity.cz.terms.config"],
        }
        raw.update(overrides)
        return raw

    def test_accepts_a_term_citing_claim(self):
        accepted, rejected = validate_claims([self._claim()], self.EVIDENCE_KEYS)
        assert rejected == []
        assert accepted[0].claim_type == "three_term_gap_component"
        assert accepted[0].identification_level == "observational"

    def test_rejects_a_claim_citing_only_the_section_metadata(self):
        accepted, rejected = validate_claims(
            [self._claim(evidence_keys=["three_term_identity.cz.window_basis.external_window_adjustable"])],
            self.EVIDENCE_KEYS,
        )
        assert accepted == []
        assert rejected

    def test_rejects_a_causal_relation(self):
        accepted, rejected = validate_claims(
            [self._claim(relation="associated_change")], self.EVIDENCE_KEYS
        )
        assert accepted == []
        assert rejected

    def test_rendered_sentence_names_the_component_and_stays_non_causal(self):
        accepted, _ = validate_claims([self._claim()], self.EVIDENCE_KEYS)
        sentence = deterministic_sentence(accepted[0], self.EVIDENCE_KEYS)
        assert "configuration" in sentence
        assert "accounting split, not a controlled experiment" in sentence


class TestThreeTermSummary:
    """The reader-facing `gap_split` section is built from the bundle alone,
    so it appears even when the LLM produced zero claims about it."""

    BUNDLE = {
        "derived": {"overall_tag": "reproduced"},
        "three_term_identity": {
            "cz": {
                "available": True,
                "total_gap": 0.006,
                "terms": {
                    "signal_and_environment": 0.001,
                    "config": 0.003,
                    "agent_replication_residual": 0.002,
                },
                "largest_term": "config",
                "window_basis": {"window_sensitivity_spread": None},
            },
            "hxz": {"available": False, "reason": "no HXZ testing-portfolio CSV for this factor"},
        },
    }

    def test_available_reference_gets_a_gap_split_section(self):
        summaries = build_three_term_summaries(self.BUNDLE)
        assert [s.comparison_line for s in summaries] == ["cz"]
        assert summaries[0].section == "gap_split"
        assert "C&Z" in summaries[0].headline

    def test_details_are_ordered_by_absolute_size_and_name_the_largest(self):
        details = build_three_term_summaries(self.BUNDLE)[0].details
        assert details[0].startswith("Portfolio-construction settings")
        assert "not a controlled experiment" in details[-1]

    def test_footnote_states_the_terms_are_not_equally_clean(self):
        footnote = build_three_term_summaries(self.BUNDLE)[0].footnote
        assert "not equally clean" in footnote
        assert "sample window" in footnote

    def test_unavailable_reference_is_skipped_not_rendered_as_zero(self):
        assert all(s.comparison_line != "hxz" for s in build_three_term_summaries(self.BUNDLE))

    def test_window_sensitivity_is_reported_when_measurable(self):
        bundle = json.loads(json.dumps(self.BUNDLE))
        bundle["three_term_identity"]["cz"]["window_basis"]["window_sensitivity_spread"] = -0.0012
        details = build_three_term_summaries(bundle)[0].details
        assert any("sample window alone" in d for d in details)

    def test_appended_by_build_deterministic_summary_without_any_claims(self):
        summaries = build_deterministic_summary([], self.BUNDLE)
        assert any(s.section == "gap_split" for s in summaries)

    def test_reference_keys_never_become_a_track_comparison_line(self):
        claim = DiagnosisClaim(
            claim_type="three_term_gap_component",
            relation="larger",
            comparison_line="cz",
            evidence_keys=["three_term_identity.cz.terms.config"],
        )
        summaries = build_deterministic_summary([claim], self.BUNDLE)
        # exactly one "cz" summary -- the gap_split one, not a second
        # robustness-bucketed line summary built by the per-line loop.
        cz_summaries = [s for s in summaries if s.comparison_line == "cz"]
        assert len(cz_summaries) == 1
        assert cz_summaries[0].section == "gap_split"


class TestSpecQuality:
    def test_no_spec_reports_unavailable(self):
        section = build_spec_quality(None)
        assert section["available"] is False
        assert section["weak_fields"] == []

    def test_ambiguous_finding_is_surfaced_as_a_weak_field(self):
        spec = minimal_resolved_spec()
        # unspecified status on a high-impact field -> DISPOSITION_MATRIX flags it
        # (NEEDS_HUMAN_CONFIRMATION, not AUTO_APPROVE).
        from src.infra.models.method_spec import EvidenceStatus

        spec.paper.signal.direction.status = EvidenceStatus.UNSPECIFIED
        section = build_spec_quality(spec)
        assert section["available"] is True
        assert any(f["field_path"] == "signal.direction" for f in section["weak_fields"])

    def test_clear_status_fields_are_not_weak(self):
        spec = minimal_resolved_spec()
        section = build_spec_quality(spec)
        assert section["weak_fields"] == []


class TestUniverseDescription:
    """docs/step7-8.md Part XIII: the paper's own extracted universe
    description, so step8 can quote the paper directly instead of us
    re-deriving a description from resolved `universe_filters` (which can't
    generalize to a future paper's own filter choices the way the paper's
    own extracted text already does)."""

    def test_no_spec_reports_unavailable(self):
        section = build_universe_description(None)
        assert section["available"] is False

    def test_available_spec_surfaces_the_papers_own_text(self):
        spec = minimal_resolved_spec()
        spec.paper.universe.description.value = "NYSE/AMEX/NASDAQ nonfinancial firms"
        section = build_universe_description(spec)
        assert section["available"] is True
        assert section["text"] == "NYSE/AMEX/NASDAQ nonfinancial firms"


class TestMenuDeviations:
    def test_no_spec_reports_unavailable(self):
        section = build_menu_deviations(None, TRACKS)
        assert section["available"] is False
        assert section["unsupported_paper_fields"] == []
        assert section["clamped_by_track"] == {}

    def test_unsupported_value_is_surfaced(self):
        spec = minimal_resolved_spec()
        spec.paper.portfolio.weighting.value = "other"
        spec.paper.portfolio.weighting.unsupported_value = "capped VW at 5% per stock"
        section = build_menu_deviations(spec, TRACKS)
        assert section["available"] is True
        assert {
            "field_path": "portfolio.weighting",
            "unsupported_value": "capped VW at 5% per stock",
        } in section["unsupported_paper_fields"]

    def test_clamped_defaults_are_read_from_each_track_config(self):
        spec = minimal_resolved_spec()
        tracks = {
            "original_method": {
                "config": {
                    "defaults_applied": [
                        {"config_key": "accounting_lag_months", "value": 6, "reason": "unspecified"}
                    ]
                },
                "metrics": {},
            },
            "standardized_hxz": {"config": {}, "metrics": {}},
        }
        section = build_menu_deviations(spec, tracks)
        assert section["clamped_by_track"] == {
            "original_method": [
                {"config_key": "accounting_lag_months", "value": 6, "reason": "unspecified"}
            ]
        }


class TestPublicationDecay:
    def test_no_by_sample_period_is_unavailable(self):
        section = build_publication_decay(TRACKS)
        assert section["available"] is False
        assert "by_sample_period" in section["reason"] or "sample_start_year" in section["reason"]

    def test_decayed_track_is_flagged(self):
        tracks = {
            "original_method": {
                "config": {},
                "metrics": {
                    "by_sample_period": {
                        "insamp": {"t_stat": 3.5},
                        "postpub": {"t_stat": 0.5},
                    }
                },
            }
        }
        section = build_publication_decay(tracks)
        assert section["available"] is True
        entry = section["tracks"]["original_method"]
        assert entry["insamp_significant"] is True
        assert entry["postpub_significant"] is False
        assert entry["decayed"] is True

    def test_stable_track_is_not_flagged_as_decayed(self):
        tracks = {
            "original_method": {
                "config": {},
                "metrics": {
                    "by_sample_period": {
                        "insamp": {"t_stat": 3.5},
                        "postpub": {"t_stat": 2.5},
                    }
                },
            }
        }
        section = build_publication_decay(tracks)
        assert section["tracks"]["original_method"]["decayed"] is False


class TestRobustnessSummary:
    def test_no_ablation_tracks_is_unavailable(self):
        section = build_robustness_summary(TRACKS)
        assert section["available"] is False
        assert "ablation" in section["reason"]

    def test_robust_when_no_sign_or_significance_flips(self):
        tracks = dict(TRACKS)
        tracks["ablation_breakpoint"] = {
            "config": {},
            "metrics": {"t_stat": -3.5},
        }
        section = build_robustness_summary(tracks)
        assert section["available"] is True
        assert section["n_ablation_tracks"] == 1
        assert section["sign_flips"] == 0
        assert section["significance_flips"] == 0
        assert section["robust"] is True

    def test_fragile_when_ablation_flips_sign(self):
        tracks = dict(TRACKS)
        tracks["ablation_weighting"] = {
            "config": {},
            "metrics": {"t_stat": 2.0},  # opposite sign of baseline's -4.0
        }
        section = build_robustness_summary(tracks)
        assert section["sign_flips"] == 1
        assert section["robust"] is False


def _bundle() -> dict:
    bundle = build_evidence_bundle(PAPER, TRACKS)
    bundle.update(
        {
            "factor_id": "t",
            "paper_ref": "Someone (2008)",
            "paper_reported": PAPER,
            "tracks": TRACKS,
        }
    )
    return bundle


class TestValidateClaims:
    def setup_method(self):
        self.evidence = _bundle()["evidence_keys"]

    def _validate_one(self, claim: dict):
        accepted, rejected = validate_claims([claim], self.evidence)
        return accepted, rejected

    def test_well_formed_claim_is_accepted(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "sign_agreement",
                "relation": "agrees",
                "subject_track": "original_method",
                "text": "The reviewed-method track reproduces the paper's headline sign.",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert rejected == []
        assert accepted[0].claim_type == "sign_agreement"
        assert accepted[0].stage is None
        assert accepted[0].identification_level == "observational"
        assert accepted[0].evidence_strength == "low"

    def test_claim_containing_a_number_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "sign_agreement",
                "relation": "agrees",
                "text": "Our spread is -0.008 versus the paper's headline.",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert accepted == []
        assert "digit" in rejected[0].reason

    def test_causal_language_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "gap_attribution",
                "relation": "associated_change",
                "text": "The breakpoint switch drives the gap.",
                "evidence_keys": ["gap_decomposition.contributions.breakpoint"],
            }
        )
        assert accepted == []
        assert "causal" in rejected[0].reason

    def test_relation_contradicting_cited_value_is_rejected(self):
        # sign_agrees is True for original_method, but the claim asserts disagreement.
        accepted, rejected = self._validate_one(
            {
                "claim_type": "sign_agreement",
                "relation": "disagrees",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_subject_track_mismatch_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "sign_agreement",
                "relation": "agrees",
                "subject_track": "standardized_hxz",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert accepted == []
        assert "subject_track" in rejected[0].reason

    def test_claim_citing_an_unknown_key_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "sign_agreement",
                "relation": "agrees",
                "text": "Signs agree.",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.made_up"],
            }
        )
        assert accepted == []
        assert "whitelist" in rejected[0].reason

    def test_claim_with_no_evidence_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "magnitude_gap",
                "relation": "larger",
                "text": "The gap is large.",
                "evidence_keys": [],
            }
        )
        assert accepted == []
        assert "no evidence_keys" in rejected[0].reason

    def test_significance_claim_must_cite_the_deterministic_significance_flag(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "significance",
                "relation": "insignificant",
                "text": "The standardized track's spread is indistinguishable from zero.",
                "evidence_keys": ["derived.tracks.standardized_hxz.vs_paper.track_spread"],
            }
        )
        assert accepted == []
        assert "significant" in rejected[0].reason

        accepted, rejected = self._validate_one(
            {
                "claim_type": "significance",
                "relation": "insignificant",
                "text": "The standardized track's spread is indistinguishable from zero.",
                "evidence_keys": ["derived.tracks.standardized_hxz.vs_paper.track_significant"],
            }
        )
        assert rejected == []
        assert len(accepted) == 1

    def test_magnitude_gap_relation_is_checked_against_abs_spread_ratio(self):
        # original_method's abs_spread_ratio is 0.8, inside the close-replication band.
        accepted, rejected = self._validate_one(
            {
                "claim_type": "magnitude_gap",
                "relation": "larger",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.abs_spread_ratio"],
            }
        )
        assert accepted == []
        assert "contradicts" in rejected[0].reason

        accepted, rejected = self._validate_one(
            {
                "claim_type": "magnitude_gap",
                "relation": "similar",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.abs_spread_ratio"],
            }
        )
        assert rejected == []

    def test_config_divergence_requires_both_baseline_and_track_value(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "config_divergence",
                "relation": "differs",
                "subject_track": "standardized_hxz",
                "evidence_keys": [
                    "config_diff.pairs.standardized_hxz.details.breakpoint_source.track_value"
                ],
            }
        )
        assert accepted == []
        assert "baseline_value" in rejected[0].reason

        accepted, rejected = self._validate_one(
            {
                "claim_type": "config_divergence",
                "relation": "differs",
                "subject_track": "standardized_hxz",
                "evidence_keys": [
                    "config_diff.pairs.standardized_hxz.details.breakpoint_source.track_value",
                    "config_diff.pairs.standardized_hxz.details.breakpoint_source.baseline_value",
                ],
            }
        )
        assert rejected == []
        assert accepted[0].stage == "portfolio"

    def test_attribution_claim_without_a_measured_contribution_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "gap_attribution",
                "relation": "associated_change",
                "text": "The breakpoint switch is associated with the gap.",
                "evidence_keys": [
                    "config_diff.pairs.standardized_hxz.details.breakpoint_source.track_value"
                ],
            }
        )
        assert accepted == []
        assert "gap_decomposition.contributions." in rejected[0].reason

    def test_gap_attribution_is_rejected_when_ablation_track_sample_size_collapses(self):
        # ablation_rebalance has 74 months against a baseline of 870: a >2x
        # mismatch, mirroring the real annual-signal/monthly-rebalance bug.
        tracks = dict(TRACKS)
        tracks["ablation_rebalance"] = {
            "config": {**TRACKS["original_method"]["config"], "rebalance_frequency": "monthly"},
            "metrics": {"mean_return": 0.005, "t_stat": 1.44, "n_months": 74},
        }
        result = ReplicationDiffResult(
            factor_id="t",
            total_gap=1.5,
            contributions={"rebalance": 1.43},
            explained_fraction=0.95,
            residual=0.07,
        )
        bundle = build_evidence_bundle(PAPER, tracks, result)
        accepted, rejected = validate_claims(
            [
                {
                    "claim_type": "gap_attribution",
                    "relation": "associated_change",
                    "text": "A measured change in the gap is associated with the rebalance switch.",
                    "evidence_keys": ["gap_decomposition.contributions.rebalance"],
                }
            ],
            bundle["evidence_keys"],
        )
        assert accepted == []
        assert "sample-size mismatch" in rejected[0].reason

    def test_gap_attribution_is_accepted_when_sample_sizes_are_comparable(self):
        tracks = dict(TRACKS)
        tracks["ablation_breakpoint"] = {
            "config": {**TRACKS["original_method"]["config"], "breakpoint_source": "nyse"},
            "metrics": {"mean_return": 0.003, "t_stat": 2.57, "n_months": 860},
        }
        result = ReplicationDiffResult(
            factor_id="t",
            total_gap=1.5,
            contributions={"breakpoint": 0.3},
            explained_fraction=0.2,
            residual=1.2,
        )
        bundle = build_evidence_bundle(PAPER, tracks, result)
        accepted, rejected = validate_claims(
            [
                {
                    "claim_type": "gap_attribution",
                    "relation": "associated_change",
                    "text": "A measured change in the gap is associated with the breakpoint switch.",
                    "evidence_keys": ["gap_decomposition.contributions.breakpoint"],
                }
            ],
            bundle["evidence_keys"],
        )
        assert rejected == []
        assert len(accepted) == 1

    def test_evidence_limitation_rejects_citing_a_present_result(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "evidence_limitation",
                "relation": "unavailable",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert accepted == []
        assert "evidence_limitation" in rejected[0].reason

    def test_unknown_claim_type_is_rejected(self):
        accepted, rejected = self._validate_one(
            {
                "claim_type": "vibes",
                "relation": "agrees",
                "text": "Looks fine.",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            }
        )
        assert accepted == []
        assert "unknown claim_type" in rejected[0].reason


class FakeLLM:
    """Minimal OpenAI-shaped client returning one canned JSON response."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, messages, **kwargs):
                outer.calls.append({"messages": messages, "kwargs": kwargs})
                return type(
                    "R",
                    (),
                    {
                        "choices": [
                            type(
                                "C",
                                (),
                                {
                                    "message": type(
                                        "M", (), {"content": json.dumps(outer._payload)}
                                    )()
                                },
                            )()
                        ]
                    },
                )()

        self.chat = type("Chat", (), {"completions": _Completions()})()


class TestReplicationDiagnoser:
    def _diagnose(self, payload: dict):
        bundle = _bundle()
        llm = FakeLLM(payload)
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        return bundle, llm, report

    def test_verdict_comes_from_the_bundle_not_the_llm(self):
        _, _, report = self._diagnose({"claims": [], "overall_tag": "reproduced_LLM_SAYS"})
        assert report.overall_tag == "reproduced"
        assert report.status == "llm_assisted_proposal"

    def test_prompt_carries_the_citable_key_whitelist(self):
        bundle, llm, _ = self._diagnose({"claims": []})
        user_msg = llm.calls[0]["messages"][1]["content"]
        assert "derived.tracks.original_method.vs_paper.sign_agrees" in user_msg
        assert llm.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}

    def test_good_and_bad_claims_are_split(self):
        _, _, report = self._diagnose(
            {
                "claims": [
                    {
                        "claim_type": "sign_agreement",
                        "relation": "agrees",
                        "text": "The reviewed-method track reproduces the paper's sign.",
                        "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
                    },
                    {
                        "claim_type": "magnitude_gap",
                        "relation": "larger",
                        "text": "Our spread is wider.",
                        "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
                    },
                ]
            }
        )
        assert len(report.claims) == 1
        assert len(report.rejected_claims) == 1

    def test_unparseable_response_yields_no_claims_rather_than_raising(self):
        bundle = _bundle()
        llm = FakeLLM({})
        llm._payload = "not json at all"
        report = ReplicationDiagnoser(llm_client=llm).diagnose(bundle)
        assert report.claims == []


def _bundle_with_extras() -> dict:
    """`_bundle()` plus the newer reason-layer evidence sections (spec_quality/
    menu_deviations/publication_decay/robustness_summary),
    hand-built the way `build_evidence_bundle()` would actually produce them."""
    bundle = _bundle()
    bundle["spec_quality"] = {
        "available": True,
        "weak_fields": [
            {"field_path": "portfolio.weighting", "reason": "evidence_status=unspecified", "disposition": "needs_human_confirmation"}
        ],
    }
    bundle["menu_deviations"] = {"available": True, "unsupported_paper_fields": [], "clamped_by_track": {}}
    bundle["publication_decay"] = {
        "available": True,
        "tracks": {
            "original_method": {
                "insamp_t_stat": 3.5, "postpub_t_stat": 0.5,
                "insamp_significant": True, "postpub_significant": False, "decayed": True,
            }
        },
    }
    bundle["robustness_summary"] = {
        "available": True, "n_ablation_tracks": 1, "t_stat_range": 1.0,
        "sign_flips": 0, "significance_flips": 0, "robust": True,
    }
    bundle["evidence_keys"].update(flatten({
        "spec_quality": bundle["spec_quality"],
        "menu_deviations": bundle["menu_deviations"],
        "publication_decay": bundle["publication_decay"],
        "robustness_summary": bundle["robustness_summary"],
    }))
    return bundle


class TestValidateClaimsNewTypes:
    """docs/tools-plus-llm-plan.md §4.3's newer claim types:
    publication_decay (McLean-Pontiff style decay), implementation_robustness
    (OAT aggregate)."""

    def setup_method(self):
        self.evidence = _bundle_with_extras()["evidence_keys"]

    def _validate_one(self, claim: dict):
        return validate_claims([claim], self.evidence)

    def test_publication_decay_accepted_and_subject_track_auto_derived(self):
        accepted, rejected = self._validate_one({
            "claim_type": "publication_decay",
            "relation": "decayed",
            "evidence_keys": ["publication_decay.tracks.original_method.decayed"],
        })
        assert rejected == []
        assert accepted[0].subject_track == "original_method"
        assert accepted[0].reason_layer == "temporal_pattern"

    def test_publication_decay_rejected_when_relation_contradicts(self):
        accepted, rejected = self._validate_one({
            "claim_type": "publication_decay",
            "relation": "stable",
            "evidence_keys": ["publication_decay.tracks.original_method.decayed"],
        })
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_implementation_robustness_accepted(self):
        accepted, rejected = self._validate_one({
            "claim_type": "implementation_robustness",
            "relation": "robust",
            "evidence_keys": ["robustness_summary.robust"],
        })
        assert rejected == []
        assert accepted[0].reason_layer == "config_sensitivity"

    def test_implementation_robustness_rejected_when_relation_contradicts(self):
        accepted, rejected = self._validate_one({
            "claim_type": "implementation_robustness",
            "relation": "fragile",
            "evidence_keys": ["robustness_summary.robust"],
        })
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_existing_claim_types_get_config_sensitivity_reason_layer(self):
        accepted, rejected = self._validate_one({
            "claim_type": "sign_agreement",
            "relation": "agrees",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
        })
        assert rejected == []
        assert accepted[0].reason_layer == "config_sensitivity"


def _bundle_with_attribution_extras() -> dict:
    """`_bundle_with_extras()` plus docs/step7-8.md Part VIII's three new
    line-nested sections (shapley_attribution/paired_tests/joint_test),
    hand-built with two comparison lines present (to_hxz/to_cz) so
    `comparison_line` derivation/validation has something real to check."""
    bundle = _bundle_with_extras()
    bundle["shapley_attribution"] = {
        "to_hxz": {
            "available": True,
            "identification_level": "controlled",
            "switches": ["weighting"],
            "total_gap": -0.005645,
            "shapley_effects": {"weighting": -0.005645},
            "shapley_sum_check": -0.005645,
        },
        "to_cz": {
            "available": True,
            "identification_level": "controlled",
            "switches": ["universe"],
            "total_gap": 0.000257,
            "shapley_effects": {"universe": 0.000257},
            "shapley_sum_check": 0.000257,
        },
    }
    bundle["paired_tests"] = {
        "to_hxz": {
            "available": True,
            "lags": 6,
            "per_switch": {
                "weighting": {
                    "available": True, "track": "factorial_weighting",
                    "mean_diff": 0.00702, "t_stat": 2.74, "n_overlap_months": 432,
                }
            },
        },
        "to_cz": {
            "available": True,
            "lags": 6,
            "per_switch": {
                "universe": {
                    "available": True, "track": "cz_actual_config",
                    "mean_diff": 0.000874, "t_stat": 1.781, "n_overlap_months": 432,
                }
            },
        },
    }
    bundle["joint_test"] = {
        "to_hxz": {
            "available": True, "switches": ["weighting"],
            "wald_stat": 21.62, "df": 1, "p_value": 0.0000784,
        },
        "to_cz": {
            "available": False,
            "reason": "need >=2 single-switch tracks with a loadable return series for a joint test, found 1",
        },
    }
    bundle["evidence_keys"].update(flatten({
        "shapley_attribution": bundle["shapley_attribution"],
        "paired_tests": bundle["paired_tests"],
        "joint_test": bundle["joint_test"],
    }))
    return bundle


class TestValidateClaimsPartVIIITypes:
    """docs/step7-8.md Part VIII: gap_attribution_shapley/switch_significance/
    joint_attribution_support, plus the new comparison_line field these three
    (and only these three) need."""

    def setup_method(self):
        self.evidence = _bundle_with_attribution_extras()["evidence_keys"]

    def _validate_one(self, claim: dict):
        return validate_claims([claim], self.evidence)

    def test_gap_attribution_shapley_accepted_with_controlled_identification(self):
        accepted, rejected = self._validate_one({
            "claim_type": "gap_attribution_shapley",
            "relation": "associated_change",
            "evidence_keys": ["shapley_attribution.to_hxz.shapley_effects.weighting"],
        })
        assert rejected == []
        claim = accepted[0]
        assert claim.comparison_line == "to_hxz"
        assert claim.identification_level == "controlled"
        # to_hxz's joint_test IS significant (p=0.0000784 < 0.05), so no cap applied.
        assert claim.evidence_strength == "high"
        assert claim.reason_layer == "config_sensitivity"

    def test_gap_attribution_shapley_evidence_strength_capped_when_joint_test_not_significant(self):
        evidence = dict(self.evidence)
        # Same shape as to_hxz but flip the joint test to "measured, not significant".
        evidence["joint_test.to_hxz.p_value"] = 0.4
        accepted, rejected = validate_claims([{
            "claim_type": "gap_attribution_shapley",
            "relation": "associated_change",
            "evidence_keys": ["shapley_attribution.to_hxz.shapley_effects.weighting"],
        }], evidence)
        assert rejected == []
        claim = accepted[0]
        # identification_level is still "controlled" (the grid itself is complete) --
        # only evidence_strength is downgraded, per Part VIII's gating rule.
        assert claim.identification_level == "controlled"
        assert claim.evidence_strength == "low"

    def test_gap_attribution_shapley_rejected_without_shapley_effects_citation(self):
        accepted, rejected = self._validate_one({
            "claim_type": "gap_attribution_shapley",
            "relation": "associated_change",
            "evidence_keys": ["shapley_attribution.to_hxz.available"],
        })
        assert accepted == []
        assert "shapley_effects" in rejected[0].reason

    def test_switch_significance_accepted_when_relation_matches_threshold(self):
        accepted, rejected = self._validate_one({
            "claim_type": "switch_significance",
            "relation": "significant",
            "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
        })
        assert rejected == []
        assert accepted[0].comparison_line == "to_hxz"
        assert accepted[0].identification_level == "harmonized"

    def test_switch_significance_borderline_t_stat_is_insignificant(self):
        # docs/step7-8.md Part VII example 5: to_cz's universe t=1.781 < 1.96.
        accepted, rejected = self._validate_one({
            "claim_type": "switch_significance",
            "relation": "insignificant",
            "evidence_keys": ["paired_tests.to_cz.per_switch.universe.t_stat"],
        })
        assert rejected == []
        assert accepted[0].comparison_line == "to_cz"

    def test_switch_significance_rejected_when_relation_contradicts(self):
        accepted, rejected = self._validate_one({
            "claim_type": "switch_significance",
            "relation": "significant",
            "evidence_keys": ["paired_tests.to_cz.per_switch.universe.t_stat"],
        })
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_joint_attribution_support_accepted_when_significant(self):
        accepted, rejected = self._validate_one({
            "claim_type": "joint_attribution_support",
            "relation": "significant",
            "evidence_keys": ["joint_test.to_hxz.p_value"],
        })
        assert rejected == []
        assert accepted[0].comparison_line == "to_hxz"
        assert accepted[0].identification_level == "harmonized"

    def test_joint_attribution_support_rejected_when_relation_contradicts(self):
        accepted, rejected = self._validate_one({
            "claim_type": "joint_attribution_support",
            "relation": "insignificant",
            "evidence_keys": ["joint_test.to_hxz.p_value"],
        })
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_comparison_line_required_when_citing_both_lines(self):
        accepted, rejected = self._validate_one({
            "claim_type": "gap_attribution_shapley",
            "relation": "associated_change",
            "evidence_keys": [
                "shapley_attribution.to_hxz.shapley_effects.weighting",
                "shapley_attribution.to_cz.shapley_effects.universe",
            ],
        })
        assert accepted == []
        assert "names no comparison_line" in rejected[0].reason

    def test_comparison_line_mismatch_with_citation_is_rejected(self):
        accepted, rejected = self._validate_one({
            "claim_type": "switch_significance",
            "relation": "significant",
            "comparison_line": "to_cz",
            "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
        })
        assert accepted == []
        assert "does not match" in rejected[0].reason

    def test_new_claim_types_get_per_switch_or_joint_gate_analysis_stage(self):
        accepted, _ = self._validate_one({
            "claim_type": "gap_attribution_shapley",
            "relation": "associated_change",
            "evidence_keys": ["shapley_attribution.to_hxz.shapley_effects.weighting"],
        })
        assert accepted[0].analysis_stage == "per_switch"

        accepted, _ = self._validate_one({
            "claim_type": "switch_significance",
            "relation": "significant",
            "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
        })
        assert accepted[0].analysis_stage == "per_switch"

        accepted, _ = self._validate_one({
            "claim_type": "joint_attribution_support",
            "relation": "significant",
            "evidence_keys": ["joint_test.to_hxz.p_value"],
        })
        assert accepted[0].analysis_stage == "joint_gate"

    def test_vs_paper_and_auxiliary_claim_types_get_their_analysis_stage(self):
        accepted, _ = self._validate_one({
            "claim_type": "sign_agreement",
            "relation": "agrees",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
        })
        assert accepted[0].analysis_stage == "vs_paper"

        accepted, _ = self._validate_one({
            "claim_type": "publication_decay",
            "relation": "decayed",
            "evidence_keys": ["publication_decay.tracks.original_method.decayed"],
        })
        assert accepted[0].analysis_stage == "auxiliary"

    def test_gap_attribution_is_unstaged(self):
        result = ReplicationDiffResult(
            factor_id="t", total_gap=1.5, contributions={"breakpoint": 1.0}
        )
        gap = build_gap_decomposition(result)
        evidence = {**self.evidence, **flatten({"gap_decomposition": gap})}
        accepted, rejected = validate_claims([{
            "claim_type": "gap_attribution",
            "relation": "associated_change",
            "evidence_keys": ["gap_decomposition.contributions.breakpoint"],
        }], evidence)
        assert rejected == []
        assert accepted[0].analysis_stage is None


def _bundle_with_narrative_extras() -> dict:
    """`_bundle_with_attribution_extras()` plus what docs/step7-8.md Part XI's
    narrative builders need: a real `config_diff.pairs.cz_actual_config`
    (universe_filters differs -- a CZ_HOUSE_CONVENTION_KEYS member, so this
    should classify as "house_convention" regardless of spec_quality),
    `menu_deviations.clamped_by_track.original_method` with a paper-silent
    field (mirrors the real AssetGrowth session's `accounting_lag_months`),
    and a `publication_decay` entry for `factorial_universe` (cross-line
    callout target)."""
    bundle = _bundle_with_attribution_extras()
    bundle["config_diff"]["pairs"]["cz_actual_config"] = {
        "changed_keys": ["universe_filters"],
        "changed_stages": ["universe"],
        "keys_by_stage": {"universe": ["universe_filters"]},
        "identification_level": "observational",
        "details": {
            "universe_filters": {
                "stage": "universe",
                "baseline_value": [{"field": "siccd", "op": "not_between", "value": [6000, 6999]}],
                "track_value": [
                    {"field": "shrcd", "op": "in", "value": [10, 11, 12]},
                    {"field": "exchcd", "op": "in", "value": [1, 2, 3]},
                ],
            }
        },
    }
    bundle["menu_deviations"]["clamped_by_track"]["original_method"] = [
        {
            "config_key": "accounting_lag_months", "value": 6,
            "reason": "MethodSpec field unspecified; engine default applied", "paper_value": None,
        },
    ]
    bundle["publication_decay"]["tracks"]["factorial_universe"] = {
        "insamp_t_stat": 7.45, "postpub_t_stat": 2.84,
        "insamp_significant": True, "postpub_significant": True, "decayed": False,
    }
    bundle["evidence_keys"].update(flatten({
        "config_diff": bundle["config_diff"],
        "menu_deviations": bundle["menu_deviations"],
        "publication_decay": bundle["publication_decay"],
    }))
    return bundle


class TestCzNarrative:
    """docs/step7-8.md Part XI: the PRIMARY narrative (project's core
    research question, AGENTS.md -- inter-implementer agreement)."""

    def setup_method(self):
        self.bundle = _bundle_with_narrative_extras()

    def test_house_convention_classification_and_effect_are_reported(self):
        summaries = build_deterministic_summary([], self.bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        detail_text = " ".join(to_cz.details)
        # docs/step7-8.md Part XI readability follow-up: no raw config-key
        # identifiers in reader-facing text -- a human-readable label instead.
        assert "universe_filters" not in detail_text
        assert "stock universe:" in detail_text.lower()
        assert to_cz.glossary["stock universe"] == "which stocks are allowed into consideration at all"
        assert "excludes financial companies" in detail_text
        assert "listed on the nyse, amex, or nasdaq" in detail_text.lower()
        assert "cross-factor house" in detail_text
        assert "not an ambiguity in the paper" in detail_text
        assert "t=-0.52" in detail_text or "t=" in detail_text
        # docs/step7-8.md Part XII: headline is the bottom line, shown first,
        # and names the comparison target itself (no separate "vs. C&Z" title).
        assert to_cz.headline
        assert "Compared with C&Z's independent replication" in to_cz.headline

    def test_cross_line_callout_mentions_hxz_decay_status_when_switch_is_significant(self):
        # The decay callout only fires when the switch's OWN isolated effect
        # is itself statistically significant -- a decay/no-decay verdict on
        # a noise-level effect has nothing to say. `self.bundle`'s "universe"
        # switch is insignificant (t=1.781) by design (see the next test), so
        # bump it here just to exercise the callout.
        bundle = _bundle_with_narrative_extras()
        bundle["paired_tests"]["to_cz"]["per_switch"]["universe"]["t_stat"] = 3.2
        summaries = build_deterministic_summary([], bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert "does NOT decay" in " ".join(to_cz.details)

    def test_cross_line_callout_suppressed_when_switch_is_not_significant(self):
        summaries = build_deterministic_summary([], self.bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert "does NOT decay" not in " ".join(to_cz.details)

    def test_headline_reflects_high_agreement_when_all_explained_and_insignificant(self):
        summaries = build_deterministic_summary([], self.bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert "none has a statistically significant effect" in to_cz.headline

    def test_unresolved_divergence_gets_the_concerning_headline(self):
        bundle = _bundle_with_narrative_extras()
        # Make it NOT a house-convention key and NOT flagged weak, to hit "unresolved".
        bundle["config_diff"]["pairs"]["cz_actual_config"]["changed_keys"] = ["some_other_key"]
        bundle["config_diff"]["pairs"]["cz_actual_config"]["details"] = {
            "some_other_key": {"stage": "portfolio", "baseline_value": "a", "track_value": "b"}
        }
        bundle["evidence_keys"].update(flatten({"config_diff": bundle["config_diff"]}))
        summaries = build_deterministic_summary([], bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert "warrants human review" in to_cz.headline

    def test_paper_ambiguous_classification_when_flagged_weak(self):
        bundle = _bundle_with_narrative_extras()
        bundle["config_diff"]["pairs"]["cz_actual_config"]["changed_keys"] = ["rebalance_frequency"]
        bundle["config_diff"]["pairs"]["cz_actual_config"]["details"] = {
            "rebalance_frequency": {"stage": "portfolio", "baseline_value": "annual", "track_value": "monthly"}
        }
        bundle["spec_quality"]["weak_fields"].append(
            {"field_path": "timing.rebalance_frequency", "reason": "evidence_status=unspecified", "disposition": "needs_human_confirmation"}
        )
        bundle["evidence_keys"].update(flatten({
            "config_diff": bundle["config_diff"], "spec_quality": bundle["spec_quality"],
        }))
        summaries = build_deterministic_summary([], bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert "flagged by our own review as weakly specified" in " ".join(to_cz.details)

    def test_no_cz_pair_yields_no_headline_not_a_crash(self):
        bundle = _bundle_with_attribution_extras()
        summaries = build_deterministic_summary([], bundle)
        to_cz = next((s for s in summaries if s.comparison_line == "to_cz"), None)
        assert to_cz is None or to_cz.headline == ""

    def test_universe_filters_prefers_the_papers_own_extracted_description(self):
        # docs/step7-8.md Part XIII: when available, quote the paper's own
        # words instead of re-deriving a description from the resolved
        # universe_filters config -- this is what lets it generalize to any
        # future paper without a hardcoded per-value lookup table.
        bundle = _bundle_with_narrative_extras()
        bundle["universe_description"] = {
            "available": True,
            "text": "NYSE/AMEX/NASDAQ nonfinancial firms excluding SIC 6000-6999",
        }
        summaries = build_deterministic_summary([], bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        detail_text = " ".join(to_cz.details)
        assert 'the paper describes its universe as: "NYSE/AMEX/NASDAQ nonfinancial firms excluding SIC 6000-6999"' in detail_text
        # C&Z's side stays the fixed house-convention description either way.
        assert "C&Z's own fixed cross-factor universe convention" in detail_text


class TestSensitivitySummary:
    """docs/step7-8.md Part XVI: the "robustness" section -- folds the
    ablation robustness_summary, the standardized-HXZ named case, baseline
    publication decay, and the t-stat channel decomposition into ONE
    section that's populated independently of whether the HXZ factorial
    grid exists."""

    def test_dominant_choice_and_joint_gate_are_both_mentioned(self):
        bundle = _bundle_with_narrative_extras()
        summaries = build_deterministic_summary([], bundle)
        to_hxz = next(s for s in summaries if s.comparison_line == "to_hxz")
        assert any("portfolio weighting" in d.lower() for d in to_hxz.details)
        assert to_hxz.glossary["portfolio weighting"] == (
            "whether bigger companies count for more in the portfolio, or every stock counts equally"
        )
        assert "joint significance test" in " ".join(to_hxz.details).lower()
        assert "sensitivity context, not itself the reproducibility question" in to_hxz.footnote
        assert "Standardized HXZ protocol (a named case" in " ".join(to_hxz.details)
        assert to_hxz.section == "robustness"

    def test_unavailable_shapley_still_shows_robustness_evidence_when_available(self):
        # `robustness_summary`/baseline `publication_decay` are populated by
        # `_bundle_with_extras()` independently of the HXZ factorial grid --
        # the robustness section must not vanish just because that grid
        # doesn't exist for this batch.
        bundle = _bundle_with_narrative_extras()
        bundle["shapley_attribution"]["to_hxz"] = {"available": False, "reason": "no grid"}
        summaries = build_deterministic_summary([], bundle)
        to_hxz = next(s for s in summaries if s.comparison_line == "to_hxz")
        assert to_hxz.headline != ""
        assert "the result is stable" in to_hxz.headline
        assert "Compared with the fully standardized HXZ protocol" not in " ".join(to_hxz.details)

    def test_nothing_available_at_all_yields_no_card(self):
        bundle = _bundle_with_narrative_extras()
        bundle["shapley_attribution"]["to_hxz"] = {"available": False, "reason": "no grid"}
        bundle["robustness_summary"] = {"available": False, "reason": "n/a"}
        bundle["publication_decay"]["tracks"] = {}
        headline, details, footnote, glossary = _build_robustness_summary(bundle)
        assert (headline, details, footnote, glossary) == ("", [], "", {})

    def test_joint_test_not_significant_is_reflected_and_shares_suppressed(self):
        bundle = _bundle_with_narrative_extras()
        bundle["joint_test"]["to_hxz"]["p_value"] = 0.4  # flip to "measured, not significant"
        summaries = build_deterministic_summary([], bundle)
        to_hxz = next(s for s in summaries if s.comparison_line == "to_hxz")
        detail_text = " ".join(to_hxz.details)
        assert "does not confirm this" in detail_text
        assert "contribution share not shown" in detail_text
        assert "accounts for" not in detail_text


class TestVsPaperSummary:
    def test_mentions_paper_silent_fields_as_a_caveat(self):
        bundle = _bundle_with_narrative_extras()
        summary = build_vs_paper_summary(bundle)
        # docs/step7-8.md Part XI readability follow-up: readable label, not the
        # raw `accounting_lag_months` config-key identifier.
        assert "accounting_lag_months" not in " ".join(summary.details)
        assert "accounting lag" in " ".join(summary.details).lower()
        assert summary.glossary["accounting lag"].startswith("how many months we wait")
        assert "cannot separate the two" in summary.footnote
        assert "Compared with the paper's own reported result" in summary.headline

    def test_no_clamped_fields_omits_the_caveat(self):
        bundle = _bundle_with_narrative_extras()
        bundle["menu_deviations"]["clamped_by_track"]["original_method"] = []
        summary = build_vs_paper_summary(bundle)
        assert summary.footnote == ""
        assert summary.details == []

    def test_no_baseline_track_is_handled(self):
        bundle = _bundle_with_narrative_extras()
        bundle["derived"]["baseline_track"] = None
        summary = build_vs_paper_summary(bundle)
        assert summary.headline == ""


class TestSpecQualitySummary:
    """docs/step7-8.md Part XVI: the 4th section -- how clearly the paper
    specified its own method, quoting the review's own reason per field."""

    def test_weak_fields_are_quoted_with_their_own_reason(self):
        bundle = _bundle_with_extras()
        summary = build_spec_quality_summary(bundle)
        assert summary.section == "spec_quality"
        detail_text = " ".join(summary.details)
        assert "evidence_status=unspecified" in detail_text
        assert "needs_human_confirmation" in detail_text
        assert "1 setting(s) were flagged as weakly specified" in summary.headline

    def test_unsupported_paper_fields_are_listed(self):
        bundle = _bundle_with_extras()
        bundle["spec_quality"]["weak_fields"] = []
        bundle["menu_deviations"]["unsupported_paper_fields"] = [
            {"field_path": "portfolio.rebalance_frequency", "unsupported_value": "weekly"},
        ]
        summary = build_spec_quality_summary(bundle)
        assert "weekly" in " ".join(summary.details)
        assert "outside the engine's menu" in summary.headline

    def test_nothing_flagged_yields_empty_summary(self):
        bundle = _bundle_with_extras()
        bundle["spec_quality"]["weak_fields"] = []
        bundle["menu_deviations"]["unsupported_paper_fields"] = []
        summary = build_spec_quality_summary(bundle)
        assert summary.headline == ""
        assert summary.details == []
        assert summary.section == "spec_quality"


class TestBuildDeterministicSummary:
    """docs/step7-8.md Part IX §9.3: a pure rollup over already-validated
    claims -- no LLM call, no re-reading of raw bundle evidence beyond
    `derived.overall_tag` (copied) and `shapley_attribution` magnitudes
    (sorting only, not a new conclusion)."""

    def setup_method(self):
        self.bundle = _bundle_with_attribution_extras()

    def _claims(self, raws: list[dict]) -> list[DiagnosisClaim]:
        accepted, rejected = validate_claims(raws, self.bundle["evidence_keys"])
        assert rejected == [], rejected
        return accepted

    def test_one_summary_per_comparison_line_present(self):
        claims = self._claims([
            {
                "claim_type": "switch_significance", "relation": "significant",
                "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
            },
            {
                "claim_type": "switch_significance", "relation": "insignificant",
                "evidence_keys": ["paired_tests.to_cz.per_switch.universe.t_stat"],
            },
        ])
        summaries = build_deterministic_summary(claims, self.bundle)
        lines = {s.comparison_line for s in summaries}
        assert lines == {"to_hxz", "to_cz"}

    def test_per_switch_summary_and_joint_supported_and_dominant_switches(self):
        claims = self._claims([
            {
                "claim_type": "switch_significance", "relation": "significant",
                "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
            },
            {
                "claim_type": "joint_attribution_support", "relation": "significant",
                "evidence_keys": ["joint_test.to_hxz.p_value"],
            },
            {
                "claim_type": "gap_attribution_shapley", "relation": "associated_change",
                "evidence_keys": ["shapley_attribution.to_hxz.shapley_effects.weighting"],
            },
        ])
        summaries = build_deterministic_summary(claims, self.bundle)
        to_hxz = next(s for s in summaries if s.comparison_line == "to_hxz")
        assert to_hxz.overall_tag == self.bundle["derived"]["overall_tag"]
        assert to_hxz.per_switch_summary == {"weighting": "significant"}
        assert to_hxz.joint_supported is True
        assert to_hxz.dominant_switches == ["weighting"]

    def test_not_significant_joint_test_downgrades_evidence_strength_and_drops_dominance(self):
        evidence = dict(self.bundle["evidence_keys"])
        evidence["joint_test.to_hxz.p_value"] = 0.4  # flip to "measured, not significant"
        accepted, rejected = validate_claims([
            {
                "claim_type": "joint_attribution_support", "relation": "insignificant",
                "evidence_keys": ["joint_test.to_hxz.p_value"],
            },
            {
                "claim_type": "gap_attribution_shapley", "relation": "associated_change",
                "evidence_keys": ["shapley_attribution.to_hxz.shapley_effects.weighting"],
            },
        ], evidence)
        assert rejected == []
        summaries = build_deterministic_summary(accepted, self.bundle)
        to_hxz = next(s for s in summaries if s.comparison_line == "to_hxz")
        assert to_hxz.joint_supported is False
        # capped evidence_strength ("low") excludes it from dominant_switches
        assert to_hxz.dominant_switches == []
        # Note: `headline`/`details`/`footnote` are built straight from `bundle`
        # (docs/step7-8.md Part XII), not from these claims -- `self.bundle`'s
        # OWN `joint_test.to_hxz.p_value` is still significant here (only the
        # local `evidence` copy used for claim validation was flipped above),
        # so the headline still reads as joint-supported; see
        # TestSensitivitySummary for the bundle-driven "not confirmed" case.

    def test_llm_dominant_pick_agreeing_with_deterministic_ranking_adds_no_bullet(self):
        # `self.bundle`'s to_hxz line has only one switch ("weighting"), so
        # it's trivially both the LLM's pick and the deterministic largest-|t|.
        details = _fold_claim_evidence_into_details(["existing bullet"], self.bundle, "to_hxz", ["weighting"])
        assert details == ["existing bullet"]

    def test_llm_dominant_pick_disagreeing_with_deterministic_ranking_adds_a_conflict_note(self):
        bundle = _bundle_with_attribution_extras()
        # Add a second, larger-|t| switch so "weighting" is no longer the
        # deterministic largest-|t| pick on the to_hxz line.
        bundle["paired_tests"]["to_hxz"]["per_switch"]["lag"] = {
            "available": True, "track": "factorial_lag", "mean_diff": 0.01, "t_stat": 5.0, "n_overlap_months": 400,
        }
        details = _fold_claim_evidence_into_details([], bundle, "to_hxz", ["weighting"])
        assert len(details) == 1
        assert "differs from the setting with the largest measured effect" in details[0]
        assert "accounting_lag_months" not in details[0]  # raw config-key identifiers never in prose

    def test_joint_supported_is_none_not_false_when_not_tested(self):
        claims = self._claims([
            {
                "claim_type": "switch_significance", "relation": "insignificant",
                "evidence_keys": ["paired_tests.to_cz.per_switch.universe.t_stat"],
            },
        ])
        summaries = build_deterministic_summary(claims, self.bundle)
        to_cz = next(s for s in summaries if s.comparison_line == "to_cz")
        assert to_cz.joint_supported is None

    def test_line_scoped_summaries_now_surface_even_without_matching_claims(self):
        """docs/step7-8.md Part XI: narratives are built straight from `bundle`
        (`to_hxz`'s Shapley grid, `to_cz`'s config_diff pair), so both lines get
        a summary even when the only accepted claim is a line-less one -- this
        used to yield exactly 1 summary before Part XI; the extra 2 are the
        (now claim-independent) `to_hxz`/`to_cz` narrative summaries."""
        claims = self._claims([
            {
                "claim_type": "sign_agreement", "relation": "agrees",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            },
        ])
        summaries = build_deterministic_summary(claims, self.bundle)
        lines = {s.comparison_line for s in summaries}
        assert lines == {None, "to_hxz", "to_cz"}
        none_summary = next(s for s in summaries if s.comparison_line is None)
        assert none_summary.overall_tag == self.bundle["derived"]["overall_tag"]


class TestDiagnoseWiresSummary:
    def test_diagnose_populates_report_summary_from_accepted_claims(self):
        bundle = _bundle_with_attribution_extras()
        llm = FakeLLM({
            "claims": [
                {
                    "claim_type": "switch_significance", "relation": "significant",
                    "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
                },
            ]
        })
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        # docs/step7-8.md Part XI: `to_cz` also gets a summary now, built
        # straight from `bundle`'s own evidence, independent of this claim.
        assert {s.comparison_line for s in report.summary} == {"to_hxz", "to_cz"}
        to_hxz = next(s for s in report.summary if s.comparison_line == "to_hxz")
        assert to_hxz.per_switch_summary == {"weighting": "significant"}
        # docs/step7-8.md Part XVI: the 4 reader-facing sections are always
        # populated on the report, independent of what the LLM claimed.
        to_cz = next(s for s in report.summary if s.comparison_line == "to_cz")
        assert to_cz.section == "vs_cz"
        assert to_hxz.section == "robustness"
        assert report.vs_paper_summary.section == "reproduction"
        assert report.spec_quality_summary.section == "spec_quality"


class _CyclingFakeLLM:
    """Returns each payload in `payloads` in turn (one per call); repeats the
    last payload if more calls happen than payloads supplied."""

    def __init__(self, payloads: list[dict]):
        self._payloads = payloads
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, messages, **kwargs):
                outer.calls.append({"messages": messages, "kwargs": kwargs})
                idx = min(len(outer.calls) - 1, len(outer._payloads) - 1)
                content = json.dumps(outer._payloads[idx])
                return type(
                    "R", (),
                    {"choices": [type("C", (), {"message": type("M", (), {"content": content})()})()]},
                )()

        self.chat = type("Chat", (), {"completions": _Completions()})()


class TestDiagnoseRetryLoop:
    """docs/tools-plus-llm-plan.md §4.3: a bounded (max 1 extra) retry round
    resubmits ONLY previously-rejected claims with their rejection reason."""

    def test_rejected_claim_gets_one_retry_and_can_be_fixed(self):
        bundle = _bundle()
        bad_claim = {
            "claim_type": "magnitude_gap", "relation": "larger",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
        }
        fixed_claim = {
            "claim_type": "magnitude_gap", "relation": "similar",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.abs_spread_ratio"],
        }
        llm = _CyclingFakeLLM([{"claims": [bad_claim]}, {"claims": [fixed_claim]}])
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        assert len(llm.calls) == 2
        assert len(report.claims) == 1
        assert report.claims[0].relation == "similar"
        assert report.rejected_claims == []

    def test_retry_prompt_carries_the_rejection_reason(self):
        bundle = _bundle()
        bad_claim = {
            "claim_type": "magnitude_gap", "relation": "larger",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
        }
        llm = _CyclingFakeLLM([{"claims": [bad_claim]}, {"claims": []}])
        ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        round2_user_msg = llm.calls[1]["messages"][1]["content"]
        assert "Previously rejected claims" in round2_user_msg
        assert "abs_spread_ratio" in round2_user_msg

    def test_no_retry_call_when_round1_has_no_rejections(self):
        bundle = _bundle()
        llm = _CyclingFakeLLM([{"claims": []}])
        ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        assert len(llm.calls) == 1

    def test_repeated_full_resubmission_does_not_double_count_accepted_claims(self):
        """A client that ignores the retry instructions and resubmits its
        WHOLE original answer (good + bad) every round must not duplicate
        the already-accepted claim."""
        bundle = _bundle()
        good_claim = {
            "claim_type": "sign_agreement", "relation": "agrees",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
        }
        bad_claim = {
            "claim_type": "magnitude_gap", "relation": "larger",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
        }
        llm = _CyclingFakeLLM([{"claims": [good_claim, bad_claim]}])  # same payload every round
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        assert len(report.claims) == 1
        assert len(report.rejected_claims) == 1


class TestFieldEvidenceDetailOptIn:
    def test_requested_tool_result_reaches_the_retry_prompt(self):
        from src.infra.models.method_spec import EvidenceCitation, EvidenceStatus

        spec = minimal_resolved_spec()
        spec.paper.portfolio.weighting.status = EvidenceStatus.UNSPECIFIED
        spec.paper.portfolio.weighting.evidence = [
            EvidenceCitation(quote="the paper never states a weighting scheme")
        ]
        bundle = _bundle_with_extras()

        bad_claim = {
            "claim_type": "magnitude_gap", "relation": "larger",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
        }
        llm = _CyclingFakeLLM([
            {"claims": [bad_claim], "tool_requests": ["field_evidence_detail"]},
            {"claims": []},
        ])
        ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle, resolved_spec=spec)
        assert len(llm.calls) == 2
        round2_user_msg = llm.calls[1]["messages"][1]["content"]
        assert "field_evidence_detail" in round2_user_msg
        assert "the paper never states a weighting scheme" in round2_user_msg

    def test_unavailable_without_resolved_spec(self):
        bundle = _bundle_with_extras()
        bad_claim = {
            "claim_type": "magnitude_gap", "relation": "larger",
            "evidence_keys": ["derived.tracks.original_method.vs_paper.spread_delta"],
        }
        llm = _CyclingFakeLLM([
            {"claims": [bad_claim], "tool_requests": ["field_evidence_detail"]},
            {"claims": []},
        ])
        ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)  # no resolved_spec
        round2_user_msg = llm.calls[1]["messages"][1]["content"]
        assert "no resolved_spec supplied" in round2_user_msg


class TestRenderMarkdown:
    def test_banner_and_deterministic_table_come_from_the_bundle(self):
        bundle = _bundle()
        report = ReplicationDiagnosisReport(factor_id="t", overall_tag=bundle["derived"]["overall_tag"])
        md = render_markdown(report, bundle)

        assert "llm-assisted proposal" in md.lower()
        assert "`reproduced`" in md
        # the deterministic table carries the actual numbers
        assert "-0.008" in md
        assert "870" in md

    def test_missing_gap_decomposition_is_stated_as_unavailable(self):
        bundle = _bundle()
        md = render_markdown(ReplicationDiagnosisReport(factor_id="t"), bundle)
        assert "Not available" in md

    def test_sentence_generated_from_relation_not_claim_text(self):
        # docs/step7-8.md Part XV §15.4: the per-claim "Findings" listing was
        # dropped from render_markdown entirely (duplicated the Summary
        # section's own bundle-derived prose) -- `deterministic_sentence` is
        # exercised directly here instead; it still backs `report_to_jsonable`'s
        # `rendered_sentence` field for API/audit consumers.
        bundle = _bundle()
        claim = DiagnosisClaim(
            claim_type="sign_agreement",
            relation="agrees",
            subject_track="original_method",
            evidence_keys=["derived.tracks.original_method.vs_paper.sign_agrees"],
            identification_level="observational",
            evidence_strength="low",
        )
        sentence = deterministic_sentence(claim, bundle["evidence_keys"])
        assert "agrees with the paper's headline sign" in sentence

    def test_part_viii_claim_types_render_switch_and_line_into_the_sentence(self):
        bundle = _bundle_with_attribution_extras()
        evidence = bundle["evidence_keys"]
        shapley_claim = DiagnosisClaim(
            claim_type="gap_attribution_shapley",
            relation="associated_change",
            comparison_line="to_hxz",
            evidence_keys=["shapley_attribution.to_hxz.shapley_effects.weighting"],
            identification_level="controlled",
            evidence_strength="high",
        )
        switch_claim = DiagnosisClaim(
            claim_type="switch_significance",
            relation="insignificant",
            comparison_line="to_cz",
            evidence_keys=["paired_tests.to_cz.per_switch.universe.t_stat"],
            identification_level="harmonized",
            evidence_strength="medium",
        )
        joint_claim = DiagnosisClaim(
            claim_type="joint_attribution_support",
            relation="significant",
            comparison_line="to_hxz",
            evidence_keys=["joint_test.to_hxz.p_value"],
            identification_level="harmonized",
            evidence_strength="medium",
        )

        assert "weighting switch" in deterministic_sentence(shapley_claim, evidence)
        assert "universe switch's own paired effect" in deterministic_sentence(switch_claim, evidence)
        assert "not statistically significant" in deterministic_sentence(switch_claim, evidence)
        assert "switches varied jointly explain a statistically significant" in deterministic_sentence(
            joint_claim, evidence
        )
        # both comparison lines' friendly labels show up, distinguishing the claims
        assert "vs. HXZ standardized config" in deterministic_sentence(shapley_claim, evidence)
        assert "vs. C&Z actual config" in deterministic_sentence(switch_claim, evidence)

    def test_findings_are_grouped_by_analysis_stage_and_summary_section_is_rendered(self):
        bundle = _bundle_with_attribution_extras()
        claims, rejected = validate_claims([
            {
                "claim_type": "switch_significance", "relation": "significant",
                "evidence_keys": ["paired_tests.to_hxz.per_switch.weighting.t_stat"],
            },
            {
                "claim_type": "joint_attribution_support", "relation": "significant",
                "evidence_keys": ["joint_test.to_hxz.p_value"],
            },
            {
                "claim_type": "sign_agreement", "relation": "agrees",
                "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
            },
        ], bundle["evidence_keys"])
        assert rejected == []
        report = ReplicationDiagnosisReport(
            factor_id="t", overall_tag=bundle["derived"]["overall_tag"], claims=claims,
            summary=build_deterministic_summary(claims, bundle),
        )
        md = render_markdown(report, bundle)

        # docs/step7-8.md Part XV §15.4: the per-analysis_stage "## Findings"
        # listing was removed entirely -- per-switch/joint-gate claim evidence
        # is folded into the Summary section's own details bullets instead
        assert "## Findings" not in md
        # docs/step7-8.md Part XVI: the LLM's per-switch/joint-gate claims are
        # no longer restated as prose (they duplicated the deterministic
        # per-setting "Effect: ..." bullet and joint-test headline/footnote) --
        # only a genuine LLM/deterministic dominant-driver DISAGREEMENT would
        # add a bullet, and none exists in this fixture.
        assert "LLM-reviewed" not in md


class TestReportToJsonable:
    """Frontend follow-up to Part IX: `diagnosis.json` (what the GET
    .../steps/8/diagnosis endpoint serves) carries a `rendered_sentence` per
    claim, computed by the SAME `deterministic_sentence` function `diagnosis.md`
    uses -- a single Python source of truth, not duplicated in TypeScript."""

    def test_each_claim_gets_the_same_sentence_render_markdown_would_show(self):
        bundle = _bundle()
        report = ReplicationDiagnosisReport(
            factor_id="t",
            overall_tag=bundle["derived"]["overall_tag"],
            claims=[
                DiagnosisClaim(
                    claim_type="sign_agreement",
                    relation="agrees",
                    subject_track="original_method",
                    evidence_keys=["derived.tracks.original_method.vs_paper.sign_agrees"],
                    identification_level="observational",
                    evidence_strength="low",
                )
            ],
        )
        data = report_to_jsonable(report, bundle)
        assert (
            data["claims"][0]["rendered_sentence"]
            == "The original_method track's spread sign agrees with the paper's headline sign."
        )

    def test_rendered_sentence_survives_json_round_trip(self):
        bundle = _bundle()
        report = ReplicationDiagnosisReport(
            factor_id="t",
            overall_tag=bundle["derived"]["overall_tag"],
            claims=[
                DiagnosisClaim(
                    claim_type="sign_agreement",
                    relation="agrees",
                    subject_track="original_method",
                    evidence_keys=["derived.tracks.original_method.vs_paper.sign_agrees"],
                    identification_level="observational",
                    evidence_strength="low",
                )
            ],
        )
        data = json.loads(json.dumps(report_to_jsonable(report, bundle), default=str))
        assert "rendered_sentence" in data["claims"][0]
        assert data["claims"][0]["rendered_sentence"]

    def test_empty_claims_list_is_handled(self):
        bundle = _bundle()
        report = ReplicationDiagnosisReport(factor_id="t", overall_tag=bundle["derived"]["overall_tag"])
        data = report_to_jsonable(report, bundle)
        assert data["claims"] == []

