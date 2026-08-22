"""Tests for `external_references_for_results_dir` (step6-preview
persistence preferred over a fresh query) and
`build_external_performance_comparison` (the direct, non-`paper_reported`
-anchored multi-way comparison)."""

from __future__ import annotations

import json

import pytest

from src.infra.reference import external_references_for_results_dir
from src.steps.step7_replication_diff.bundle import (
    build_external_performance_comparison,
    build_paper_verdict_agreement,
)


def _write(path, payload):
    path.write_text(json.dumps(payload))


class TestExternalReferencesForResultsDir:
    def test_prefers_persisted_cz_and_hxz_over_a_live_query(self, tmp_path):
        _write(
            tmp_path / "cz_reference.json",
            {
                "acronym": "ZScore",
                "raw": {"sample_start_year": 1981, "sample_end_year": 1995},
                "cz_reported": {"mean_return": 0.99, "t_stat": 9.9, "sign": 1},
            },
        )
        _write(
            tmp_path / "hxz_reference.json",
            {
                "acronym": "ZScore",
                "original_insample": {
                    "mean_return": 0.88, "t_stat": 8.8, "n_months": None,
                    "start_year": 1981, "end_year": 1995, "label": "persisted test label",
                },
                "hxz_paper_sample": {
                    "mean_return": 0.88, "t_stat": 8.8, "n_months": None,
                    "start_year": 1967, "end_year": 2016, "label": "persisted test label",
                },
            },
        )

        endpoints = external_references_for_results_dir(tmp_path, "ZScore", 1981, 1995)

        assert endpoints["cz"]["spread"] == 0.99
        assert endpoints["cz"]["t_stat"] == 9.9
        assert "persisted" in endpoints["cz"]["source"]
        assert endpoints["hxz"]["spread"] == 0.88
        assert endpoints["hxz"]["t_stat"] == 8.8
        assert "persisted test label" in endpoints["hxz"]["source"]

    def test_falls_back_to_live_query_when_no_persisted_files_exist(self, tmp_path):
        endpoints = external_references_for_results_dir(tmp_path, "ZScore", 1981, 1995)

        assert endpoints["hxz"]["spread"] == 0.01
        assert endpoints["hxz"]["t_stat"] == 0.06
        assert "persisted" not in endpoints["hxz"]["source"]

    def test_missing_results_dir_falls_back_to_live_query(self):
        endpoints = external_references_for_results_dir(None, "ZScore", 1981, 1995)

        assert endpoints["hxz"]["spread"] == 0.01

    def test_only_cz_persisted_still_falls_back_for_hxz(self, tmp_path):
        _write(
            tmp_path / "cz_reference.json",
            {
                "acronym": "ZScore",
                "raw": {"sample_start_year": 1981, "sample_end_year": 1995},
                "cz_reported": {"mean_return": 0.99, "t_stat": 9.9, "sign": 1},
            },
        )

        endpoints = external_references_for_results_dir(tmp_path, "ZScore", 1981, 1995)

        assert endpoints["cz"]["spread"] == 0.99
        assert endpoints["hxz"]["spread"] == 0.01
        assert "persisted" not in endpoints["hxz"]["source"]

    def test_no_acronym_and_no_persisted_files_returns_empty(self, tmp_path):
        assert external_references_for_results_dir(tmp_path, None) == {}


class TestBuildExternalPerformanceComparison:
    def test_lays_agent_tracks_and_external_references_side_by_side(self):
        derived = {
            "tracks": {
                "original_method": {
                    "vs_paper": {"track_spread": 0.005, "track_raw_t_stat": 3.0, "track_significance_tier": 2},
                    "n_months": 276,
                    "raw_mean_return": 0.005,
                    "raw_t_stat": 3.0,
                },
                "standardized_hxz": {
                    "vs_paper": {"track_spread": 0.0025, "track_raw_t_stat": 1.3, "track_significance_tier": 0},
                    "n_months": 276,
                    "raw_mean_return": 0.0025,
                    "raw_t_stat": 1.3,
                },
            }
        }
        external_references = {
            "cz": {"spread": 0.0055, "t_stat": 3.94, "sample_start_year": 1968, "sample_end_year": 1990, "source": "cz src"},
        }

        result = build_external_performance_comparison(derived, external_references)

        assert result["agent_tracks"]["original_method"]["mean_return"] == 0.005
        assert result["agent_tracks"]["original_method"]["t_stat"] == 3.0
        assert result["agent_tracks"]["original_method"]["spread_basis"] == "raw_mean_return"
        assert result["agent_tracks"]["standardized_hxz"]["significance_tier"] == 0
        assert result["cz"] == {
            "available": True,
            "mean_return": 0.0055,
            "t_stat": 3.94,
            "sample_start_year": 1968,
            "sample_end_year": 1990,
            "source": "cz src",
        }
        assert result["hxz"]["available"] is False

    def test_agent_tracks_mean_return_uses_the_raw_spread_not_the_papers_alpha_basis(self):
        # docs/step7-8.md "Step A" follow-up: when `paper_reported.
        # return_type` is alpha-based, `vs_paper.track_spread` silently
        # becomes an alpha_ff3/alpha_capm/alpha_ff5 value (see
        # `_resolve_track_spread`) -- but C&Z's/HXZ's own self-reported
        # numbers are always the raw long-short spread, never an alpha.
        # `agent_tracks[*].mean_return` must therefore read `raw_mean_
        # return`, not `vs_paper.track_spread`, even though in THIS
        # fixture the two deliberately differ to prove the fix.
        derived = {
            "tracks": {
                "original_method": {
                    "vs_paper": {
                        "track_spread": 0.009,  # this is alpha_ff3, NOT the raw spread
                        "track_spread_metric": "alpha_ff3",
                        "track_raw_t_stat": 3.0,
                    },
                    "n_months": 276,
                    "raw_mean_return": 0.005,  # the actual raw long-short mean return
                    "raw_t_stat": 3.0,
                },
            }
        }
        result = build_external_performance_comparison(derived, None)
        assert result["agent_tracks"]["original_method"]["mean_return"] == 0.005

    def test_no_external_references_still_returns_agent_tracks(self):
        derived = {
            "tracks": {
                "original_method": {
                    "vs_paper": {"track_spread": 0.005},
                    "n_months": 100,
                    "raw_mean_return": 0.005,
                    "raw_t_stat": None,
                }
            }
        }

        result = build_external_performance_comparison(derived, None)

        assert result["agent_tracks"]["original_method"]["mean_return"] == 0.005
        assert result["cz"]["available"] is False
        assert result["hxz"]["available"] is False
        assert result["agent_vs_cz"]["available"] is False
        assert result["agent_vs_hxz"]["available"] is False

    def test_agent_vs_cz_reproduces_closely_matches_real_meanrankrevgrowth_numbers(self):
        # Real numbers from runs/backtest_scripts/results/4a483a60aae1c941/comparison.json
        # (MeanRankRevGrowth): cz_actual_config track vs C&Z's own reported number.
        derived = {
            "tracks": {
                "cz_actual_config": {
                    "vs_paper": {
                        "track_spread": 0.00383312504558415,
                        "track_raw_t_stat": 2.834708997988981,
                        "track_significance_tier": 2,
                    },
                    "n_months": 276,
                    "raw_mean_return": 0.00383312504558415,
                    "raw_t_stat": 2.834708997988981,
                },
            }
        }
        external_references = {"cz": {"spread": 0.0055, "t_stat": 3.94, "source": "cz"}}

        result = build_external_performance_comparison(derived, external_references)
        verdict = result["agent_vs_cz"]

        assert verdict["available"] is True
        assert verdict["track"] == "cz_actual_config"
        assert verdict["sign_agrees"] is True
        assert verdict["reference_significant"] is True
        assert verdict["track_significant"] is True
        assert verdict["verdict"] == "reproduced"
        assert verdict["abs_spread_ratio"] == pytest.approx(0.6969, abs=1e-3)

    def test_agent_vs_hxz_inconclusive_when_both_sides_insignificant_and_opposite_sign(self):
        # Same session: standardized_hxz track vs HXZ's own reported number
        # (opposite sign, neither side statistically significant).
        derived = {
            "tracks": {
                "standardized_hxz": {
                    "vs_paper": {
                        "track_spread": 0.0024952091226623134,
                        "track_raw_t_stat": 1.326868441579084,
                        "track_significance_tier": 0,
                    },
                    "n_months": 276,
                    "raw_mean_return": 0.0024952091226623134,
                    "raw_t_stat": 1.326868441579084,
                },
            }
        }
        external_references = {"hxz": {"spread": -0.0019, "t_stat": 1.08, "source": "hxz"}}

        result = build_external_performance_comparison(derived, external_references)
        verdict = result["agent_vs_hxz"]

        assert verdict["available"] is True
        assert verdict["sign_agrees"] is False
        assert verdict["reference_significant"] is False
        assert verdict["track_significant"] is False
        assert verdict["verdict"] == "inconclusive"

    def test_agent_vs_cz_unavailable_when_track_missing_t_stat(self):
        derived = {
            "tracks": {
                "cz_actual_config": {
                    "vs_paper": {"track_spread": 0.005},
                    "n_months": 100,
                    "raw_mean_return": 0.005,
                    "raw_t_stat": None,
                }
            }
        }
        external_references = {"cz": {"spread": 0.0055, "t_stat": 3.94}}

        result = build_external_performance_comparison(derived, external_references)

        assert result["agent_vs_cz"]["available"] is False


class TestBuildPaperVerdictAgreement:
    def test_conflict_when_one_side_significant_and_the_other_is_not(self):
        # Real MeanRankRevGrowth numbers: C&Z significant positive, HXZ
        # insignificant and oppositely signed.
        result = build_paper_verdict_agreement(
            {"cz": {"spread": 0.0055, "t_stat": 3.94}, "hxz": {"spread": -0.0019, "t_stat": 1.08}}
        )
        assert result["available"] is True
        assert result["cz_significant"] is True
        assert result["hxz_significant"] is False
        assert result["sign_agrees"] is False
        assert result["verdict"] == "conflict"

    def test_conflict_when_both_significant_but_opposite_sign(self):
        result = build_paper_verdict_agreement(
            {"cz": {"spread": 0.005, "t_stat": 3.0}, "hxz": {"spread": -0.004, "t_stat": -2.5}}
        )
        assert result["verdict"] == "conflict"

    def test_agree_significant_when_both_significant_same_sign(self):
        result = build_paper_verdict_agreement(
            {"cz": {"spread": 0.005, "t_stat": 3.0}, "hxz": {"spread": 0.004, "t_stat": 2.5}}
        )
        assert result["verdict"] == "agree_significant"

    def test_agree_insignificant_when_neither_side_significant(self):
        result = build_paper_verdict_agreement(
            {"cz": {"spread": 0.001, "t_stat": 0.4}, "hxz": {"spread": -0.0005, "t_stat": -0.2}}
        )
        assert result["verdict"] == "agree_insignificant"

    def test_unavailable_when_one_side_missing(self):
        result = build_paper_verdict_agreement({"cz": {"spread": 0.005, "t_stat": 3.0}})
        assert result["available"] is False
        assert result["verdict"] == "unavailable"

    def test_unavailable_when_none_supplied(self):
        result = build_paper_verdict_agreement(None)
        assert result["available"] is False
        assert result["verdict"] == "unavailable"
