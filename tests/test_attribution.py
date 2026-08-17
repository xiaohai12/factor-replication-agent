"""Tests for `src/steps/step7_replication_diff/attribution.py`
(docs/step7-8.md Part V): Shapley-value decomposition of the `mean_return`
gap across switches, paired Newey-West significance per switch, and a
joint Wald test across all single-switch contrasts at once.

Numeric checks are pinned against a real AssetGrowth batch
(`runs/backtest_scripts/results/099f6e1136bd316c/`) verified by hand during
design -- see docs/step7-8.md Part V for the reference numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.steps.step7_replication_diff.attribution import (
    compute_shapley_effects,
    joint_switch_wald_test,
    paired_switch_significance,
    split_tracks_by_comparison_line,
)


class TestSplitTracksByComparisonLine:
    def test_only_hxz_line_present(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.01}},
            "factorial_weighting": {"switches_flipped": {"weighting": "vw"}},
            "standardized_hxz": {"switches_flipped": {"weighting": "vw", "breakpoint": "nyse"}},
        }
        lines = split_tracks_by_comparison_line(tracks)
        assert set(lines) == {"to_hxz"}
        assert set(lines["to_hxz"]) == {"original_method", "factorial_weighting", "standardized_hxz"}

    def test_both_lines_present_and_kept_separate(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.01}},
            "factorial_universe": {"switches_flipped": {"universe": "hxz_value"}},
            "cz_factorial_universe": {"switches_flipped": {"universe": "cz_value"}},
            "cz_actual_config": {"switches_flipped": {"universe": "cz_value", "weighting": "ew"}},
        }
        lines = split_tracks_by_comparison_line(tracks)
        assert set(lines) == {"to_hxz", "to_cz"}
        assert set(lines["to_hxz"]) == {"original_method", "factorial_universe"}
        assert set(lines["to_cz"]) == {"original_method", "cz_factorial_universe", "cz_actual_config"}
        # Same baseline object handed to both lines -- not a copy per line.
        assert lines["to_hxz"]["original_method"] is lines["to_cz"]["original_method"]

    def test_tracks_without_switches_flipped_are_excluded(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.01}},
            "cz_actual_config": {"switches_flipped": {}},  # no-op override, e.g. §25's degenerate case
            "some_bridge_track": {"is_bridge_track": True},
        }
        lines = split_tracks_by_comparison_line(tracks)
        assert lines == {}


class TestComputeShapleyEffects:
    def test_missing_baseline_track_is_unavailable(self):
        result = compute_shapley_effects({"factorial_weighting": {"metrics": {"mean_return": 0.01}}})
        assert result["available"] is False
        assert "original_method" in result["reason"]

    def test_no_switches_flipped_anywhere_is_unavailable(self):
        tracks = {"original_method": {"metrics": {"mean_return": 0.01}}}
        result = compute_shapley_effects(tracks)
        assert result["available"] is False
        assert "switches_flipped" in result["reason"]

    def test_incomplete_grid_lists_missing_subsets(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.01}},
            "factorial_a": {"metrics": {"mean_return": 0.02}, "switches_flipped": {"a": "x"}},
            "factorial_a_b": {
                "metrics": {"mean_return": 0.03},
                "switches_flipped": {"a": "x", "b": "y"},
            },
            # Missing the pure "b" corner -- 2^2=4 subsets needed, only 3 present.
        }
        result = compute_shapley_effects(tracks)
        assert result["available"] is False
        assert result["reason"].startswith("incomplete factorial grid")
        assert "['b']" in result["reason"]

    def test_two_switches_no_interaction_splits_evenly(self):
        """With no interaction (v(a,b) - v(b) == v(a) - v(empty)), Shapley
        reduces to the simple additive split: each switch's value is just
        its own marginal effect, independent of averaging weights."""
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.10}},
            "factorial_a": {"metrics": {"mean_return": 0.08}, "switches_flipped": {"a": "x"}},
            "factorial_b": {"metrics": {"mean_return": 0.07}, "switches_flipped": {"b": "y"}},
            "factorial_a_b": {
                "metrics": {"mean_return": 0.05},
                "switches_flipped": {"a": "x", "b": "y"},
            },
        }
        result = compute_shapley_effects(tracks)
        assert result["available"] is True
        assert result["identification_level"] == "controlled"
        assert result["shapley_effects"]["a"] == pytest.approx(-0.02)
        assert result["shapley_effects"]["b"] == pytest.approx(-0.03)
        assert result["total_gap"] == pytest.approx(-0.05)
        # Efficiency property: contributions sum exactly to the total gap.
        assert sum(result["shapley_effects"].values()) == pytest.approx(result["total_gap"])

    def test_duplicate_subset_from_two_tracks_is_ambiguous(self):
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.10}},
            "factorial_a": {"metrics": {"mean_return": 0.08}, "switches_flipped": {"a": "x"}},
            "ablation_a": {"metrics": {"mean_return": 0.09}, "switches_flipped": {"a": "x"}},
        }
        result = compute_shapley_effects(tracks)
        assert result["available"] is False
        assert "ambiguous" in result["reason"]

    def test_three_switches_matches_hand_computed_asset_growth_reference(self):
        """Reference values hand-verified against
        runs/backtest_scripts/results/099f6e1136bd316c/comparison.json
        during design (docs/step7-8.md Part V)."""
        tracks = {
            "original_method": {"metrics": {"mean_return": 0.009125940536357952}},
            "factorial_universe": {
                "metrics": {"mean_return": 0.011804336371329537},
                "switches_flipped": {"universe": "x"},
            },
            "factorial_weighting": {
                "metrics": {"mean_return": 0.004157542273751619},
                "switches_flipped": {"weighting": "x"},
            },
            "factorial_breakpoint": {
                "metrics": {"mean_return": 0.007110825049620208},
                "switches_flipped": {"breakpoint": "x"},
            },
            "factorial_weighting_universe": {
                "metrics": {"mean_return": 0.004820376835993562},
                "switches_flipped": {"weighting": "x", "universe": "x"},
            },
            "factorial_breakpoint_universe": {
                "metrics": {"mean_return": 0.009501636858430128},
                "switches_flipped": {"breakpoint": "x", "universe": "x"},
            },
            "factorial_breakpoint_weighting": {
                "metrics": {"mean_return": 0.0027012468946608454},
                "switches_flipped": {"breakpoint": "x", "weighting": "x"},
            },
            "standardized_hxz": {
                "metrics": {"mean_return": 0.0032306653593001753},
                "switches_flipped": {"breakpoint": "x", "weighting": "x", "universe": "x"},
            },
        }
        result = compute_shapley_effects(tracks)
        assert result["available"] is True
        assert result["shapley_effects"]["weighting"] == pytest.approx(-0.0056453795356279845)
        assert result["shapley_effects"]["breakpoint"] == pytest.approx(-0.001828108136475407)
        assert result["shapley_effects"]["universe"] == pytest.approx(0.0015782124950456152)
        assert sum(result["shapley_effects"].values()) == pytest.approx(result["total_gap"])


def _write_series(path, yyyymm_values, returns):
    pd.DataFrame({"yyyymm": yyyymm_values, "ls_return": returns}).to_csv(path, index=False)


class TestPairedSwitchSignificance:
    def test_no_baseline_csv_is_unavailable(self, tmp_path):
        result = paired_switch_significance(tmp_path, {"original_method": {"config": {}}})
        assert result["available"] is False
        assert "original_method" in result["reason"]

    def test_single_switch_track_gets_a_paired_test(self, tmp_path):
        months = list(range(200001, 200013))
        rng = np.random.default_rng(0)
        baseline_returns = rng.normal(0.01, 0.02, size=12)
        other_returns = baseline_returns - 0.005  # constant shift -> clean signal
        _write_series(tmp_path / "original_method.csv", months, baseline_returns)
        _write_series(tmp_path / "factorial_weighting.csv", months, other_returns)

        tracks = {
            "original_method": {"config": {}},
            "factorial_weighting": {"switches_flipped": {"weighting": "vw"}},
        }
        result = paired_switch_significance(tmp_path, tracks)
        assert result["available"] is True
        assert "weighting" in result["per_switch"]
        entry = result["per_switch"]["weighting"]
        assert entry["available"] is True
        assert entry["mean_diff"] == pytest.approx(0.005)
        assert entry["n_overlap_months"] == 12

    def test_multi_switch_track_is_ignored(self, tmp_path):
        months = list(range(200001, 200013))
        _write_series(tmp_path / "original_method.csv", months, [0.01] * 12)
        _write_series(tmp_path / "factorial_a_b.csv", months, [0.02] * 12)
        tracks = {
            "original_method": {"config": {}},
            "factorial_a_b": {"switches_flipped": {"a": "x", "b": "y"}},
        }
        result = paired_switch_significance(tmp_path, tracks)
        assert result["available"] is False

    def test_missing_switch_csv_is_reported_per_switch(self, tmp_path):
        months = list(range(200001, 200013))
        _write_series(tmp_path / "original_method.csv", months, [0.01] * 12)
        tracks = {
            "original_method": {"config": {}},
            "factorial_weighting": {"switches_flipped": {"weighting": "vw"}},
        }
        result = paired_switch_significance(tmp_path, tracks)
        assert result["available"] is True
        assert result["per_switch"]["weighting"]["available"] is False

    def test_two_tracks_mapping_to_the_same_switch_is_reported_not_silently_picked(self, tmp_path):
        """A batch that ran both a `factorial_universe` (target
        HXZ_STANDARD_CONFIG) and a `cz_factorial_universe` (target
        cz_config_override) auto-attribution track produces two DIFFERENT
        tracks whose `switches_flipped` both touch only "universe" -- must
        be reported as ambiguous, never silently resolved by picking
        whichever track happens to be iterated last."""
        months = list(range(200001, 200013))
        _write_series(tmp_path / "original_method.csv", months, [0.01] * 12)
        _write_series(tmp_path / "factorial_universe.csv", months, [0.02] * 12)
        _write_series(tmp_path / "cz_factorial_universe.csv", months, [0.03] * 12)
        tracks = {
            "original_method": {"config": {}},
            "factorial_universe": {"switches_flipped": {"universe": "hxz_value"}},
            "cz_factorial_universe": {"switches_flipped": {"universe": "cz_value"}},
        }
        result = paired_switch_significance(tmp_path, tracks)
        assert result["available"] is True
        entry = result["per_switch"]["universe"]
        assert entry["available"] is False
        assert "ambiguous" in entry["reason"]
        assert "factorial_universe" in entry["reason"]
        assert "cz_factorial_universe" in entry["reason"]


class TestJointSwitchWaldTest:
    def test_fewer_than_two_switch_series_is_unavailable(self, tmp_path):
        months = list(range(200001, 200013))
        _write_series(tmp_path / "original_method.csv", months, [0.01] * 12)
        _write_series(tmp_path / "factorial_weighting.csv", months, [0.02] * 12)
        tracks = {
            "original_method": {"config": {}},
            "factorial_weighting": {"switches_flipped": {"weighting": "vw"}},
        }
        result = joint_switch_wald_test(tmp_path, tracks)
        assert result["available"] is False

    def test_ambiguous_switch_is_excluded_not_silently_picked(self, tmp_path):
        """Same duplicate-`universe`-track scenario as the paired-test
        version above, but for the joint test: the ambiguous switch is
        dropped from the test entirely (listed in
        `ambiguous_switches_excluded`) rather than one of the two
        candidate tracks being picked arbitrarily."""
        months = list(range(200001, 200013))
        rng = np.random.default_rng(1)
        baseline_returns = rng.normal(0.01, 0.02, size=12)
        _write_series(tmp_path / "original_method.csv", months, baseline_returns)
        _write_series(tmp_path / "factorial_universe.csv", months, baseline_returns - 0.01)
        _write_series(tmp_path / "cz_factorial_universe.csv", months, baseline_returns - 0.02)
        _write_series(tmp_path / "factorial_weighting.csv", months, baseline_returns - 0.03)
        tracks = {
            "original_method": {"config": {}},
            "factorial_universe": {"switches_flipped": {"universe": "hxz_value"}},
            "cz_factorial_universe": {"switches_flipped": {"universe": "cz_value"}},
            "factorial_weighting": {"switches_flipped": {"weighting": "vw"}},
        }
        result = joint_switch_wald_test(tmp_path, tracks)
        # Only "weighting" is unambiguous -- fewer than 2 switches left, so
        # the joint test itself can't run, but the ambiguity must still be
        # visible in the reason rather than silently dropped.
        assert result["available"] is False
        assert result["ambiguous_switches_excluded"] == ["universe"]

    def test_asset_growth_reference_numbers(self, tmp_path):
        """Rebuilds the exact 3-switch scenario from
        runs/backtest_scripts/results/099f6e1136bd316c/ using real
        original_method.csv/factorial_*.csv content, and checks the Wald
        statistic matches the value hand-verified during design."""
        real_dir_candidates = [
            "runs/backtest_scripts/results/099f6e1136bd316c",
        ]
        import os

        real_dir = next((p for p in real_dir_candidates if os.path.isdir(p)), None)
        if real_dir is None:
            pytest.skip("reference AssetGrowth run directory not present in this checkout")

        import json
        from pathlib import Path

        real_dir = Path(real_dir)
        comparison = json.loads((real_dir / "comparison.json").read_text())
        tracks = {
            "original_method": comparison["tracks"]["original_method"],
            "factorial_universe": {
                **comparison["tracks"]["factorial_universe"],
                "switches_flipped": {"universe": "x"},
            },
            "factorial_weighting": {
                **comparison["tracks"]["factorial_weighting"],
                "switches_flipped": {"weighting": "x"},
            },
            "factorial_breakpoint": {
                **comparison["tracks"]["factorial_breakpoint"],
                "switches_flipped": {"breakpoint": "x"},
            },
        }
        result = joint_switch_wald_test(real_dir, tracks)
        assert result["available"] is True
        assert result["n_overlap_months"] == 432
        assert result["wald_stat"] == pytest.approx(21.617310202387486, rel=1e-6)
        assert result["df"] == 3
        assert result["p_value"] == pytest.approx(7.835258674682155e-05, rel=1e-4)
