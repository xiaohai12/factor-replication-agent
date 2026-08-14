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

from src.infra.models.diagnosis import DiagnosisClaim, ReplicationDiagnosisReport
from src.steps.step7_replication_diff import ReplicationDiffResult, safe_diff_ablation
from src.steps.step7_replication_diff.bundle import (
    SIGNIFICANCE_T_THRESHOLD,
    build_bridge_comparison,
    build_config_diff,
    build_evidence_bundle,
    build_gap_decomposition,
    build_menu_deviations,
    build_publication_decay,
    build_robustness_summary,
    build_spec_quality,
    build_track_vs_paper,
    classify_overall,
    flatten,
    stage_of,
)
from src.steps.step8_diagnosis import ReplicationDiagnoser, validate_claims
from src.steps.step8_diagnosis.render import render_markdown
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

    def test_opposite_sign_is_flagged(self):
        vs = build_track_vs_paper(PAPER, TRACKS["standardized_hxz"]["metrics"])
        assert vs["sign_agrees"] is False
        assert vs["track_significant"] is False
        assert vs["significance_agrees"] is False

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
    def test_sign_mismatch(self):
        assert classify_overall({"sign_agrees": False}) == "sign_mismatch"

    def test_unknown_sign_is_inconclusive(self):
        assert classify_overall({"sign_agrees": None}) == "inconclusive"

    def test_close_replication_requires_ratio_band_and_significance_agreement(self):
        vs = {"sign_agrees": True, "abs_spread_ratio": 0.8, "significance_agrees": True}
        assert classify_overall(vs) == "close_replication"

    def test_same_sign_but_far_magnitude_is_not_close(self):
        vs = {"sign_agrees": True, "abs_spread_ratio": 5.0, "significance_agrees": True}
        assert classify_overall(vs) == "sign_agrees_magnitude_differs"


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


class TestEvidenceBundle:
    def test_bundle_exposes_derived_config_diff_and_a_citable_key_whitelist(self):
        bundle = build_evidence_bundle(PAPER, TRACKS)
        keys = bundle["evidence_keys"]

        assert bundle["derived"]["baseline_track"] == "original_method"
        assert bundle["derived"]["overall_tag"] == "close_replication"
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


class TestBridgeComparison:
    def test_no_bridge_track_is_unavailable(self):
        section = build_bridge_comparison(TRACKS, PAPER)
        assert section["available"] is False
        assert "no bridge track" in section["reason"]

    def test_both_reproduce(self):
        tracks = dict(TRACKS)
        tracks["cz_bridge_x"] = {
            "config": {},
            "metrics": {"mean_return": -0.009, "t_stat": -4.5, "n_months": 870},
            "is_bridge_track": True,
        }
        section = build_bridge_comparison(tracks, PAPER)
        assert section["available"] is True
        assert section["bridge_track"] == "cz_bridge_x"
        assert section["own_track"] == "original_method"
        assert section["bridge_reproduces_paper"] is True
        assert section["own_reproduces_paper"] is True
        assert section["signal_implementation_agreement"] == "both_reproduce"

    def test_only_bridge_reproduces(self):
        tracks = {
            "original_method": TRACKS["standardized_hxz"],  # sign disagrees w/ paper
            "cz_bridge_x": {
                "config": {},
                "metrics": {"mean_return": -0.009, "t_stat": -4.5, "n_months": 870},
                "is_bridge_track": True,
            },
        }
        section = build_bridge_comparison(tracks, PAPER)
        assert section["signal_implementation_agreement"] == "only_bridge"


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
        _, _, report = self._diagnose({"claims": [], "overall_tag": "close_replication_LLM_SAYS"})
        assert report.overall_tag == "close_replication"
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
    menu_deviations/bridge_comparison/publication_decay/robustness_summary),
    hand-built the way `build_evidence_bundle()` would actually produce them."""
    bundle = _bundle()
    bundle["spec_quality"] = {
        "available": True,
        "weak_fields": [
            {"field_path": "portfolio.weighting", "reason": "evidence_status=unspecified", "disposition": "needs_human_confirmation"}
        ],
    }
    bundle["menu_deviations"] = {"available": True, "unsupported_paper_fields": [], "clamped_by_track": {}}
    bundle["bridge_comparison"] = {
        "available": True,
        "bridge_track": "cz_bridge_x",
        "own_track": "original_method",
        "bridge_reproduces_paper": True,
        "own_reproduces_paper": True,
        "signal_implementation_agreement": "both_reproduce",
    }
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
        "bridge_comparison": bundle["bridge_comparison"],
        "publication_decay": bundle["publication_decay"],
        "robustness_summary": bundle["robustness_summary"],
    }))
    return bundle


class TestValidateClaimsNewTypes:
    """docs/tools-plus-llm-plan.md §4.3's three new claim types:
    signal_reproducibility (bridge track), publication_decay (McLean-Pontiff
    style decay), implementation_robustness (OAT aggregate)."""

    def setup_method(self):
        self.evidence = _bundle_with_extras()["evidence_keys"]

    def _validate_one(self, claim: dict):
        return validate_claims([claim], self.evidence)

    def test_signal_reproducibility_accepted_when_relation_matches_agreement(self):
        accepted, rejected = self._validate_one({
            "claim_type": "signal_reproducibility",
            "relation": "reproduces",
            "subject_track": "original_method",
            "evidence_keys": ["bridge_comparison.signal_implementation_agreement"],
        })
        assert rejected == []
        assert accepted[0].reason_layer == "signal_fidelity"

    def test_signal_reproducibility_rejected_when_relation_contradicts(self):
        accepted, rejected = self._validate_one({
            "claim_type": "signal_reproducibility",
            "relation": "diverges",
            "subject_track": "original_method",
            "evidence_keys": ["bridge_comparison.signal_implementation_agreement"],
        })
        assert accepted == []
        assert "contradicts" in rejected[0].reason

    def test_signal_reproducibility_requires_subject_track_be_bridge_or_own(self):
        accepted, rejected = self._validate_one({
            "claim_type": "signal_reproducibility",
            "relation": "reproduces",
            "subject_track": "standardized_hxz",
            "evidence_keys": ["bridge_comparison.signal_implementation_agreement"],
        })
        assert accepted == []
        assert "bridge_comparison" in rejected[0].reason

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
    def test_figures_come_from_the_bundle_and_sentence_from_the_relation(self):
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
        md = render_markdown(report, bundle)

        assert "llm-assisted proposal" in md.lower()
        assert "`close_replication`" in md
        # the sentence is generated from the relation, not from claim.text
        assert "agrees with the paper's headline sign" in md
        # the cited value is rendered from the bundle
        assert "`derived.tracks.original_method.vs_paper.sign_agrees` = true" in md
        # the deterministic table carries the actual numbers
        assert "-0.008" in md
        assert "870" in md

    def test_missing_gap_decomposition_is_stated_as_unavailable(self):
        bundle = _bundle()
        md = render_markdown(ReplicationDiagnosisReport(factor_id="t"), bundle)
        assert "Not available" in md
        assert "No claims survived evidence validation." in md
