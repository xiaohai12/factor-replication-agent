"""Tests for `matched_comparison.matched_sample_stats` (Phase C/D,
docs/multi-config-evidence-plan.md): deterministic matched-sample signal
comparison math on two synthetic `[permno, yyyymm, signal]` panels.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.steps.step7_replication_diff.matched_comparison import matched_sample_stats


def _panel(rows):
    return pd.DataFrame(rows, columns=["permno", "yyyymm", "signal"])


class TestCoverage:
    def test_full_overlap_coverage_is_one(self):
        rows = [(1, 200001, 1.0), (2, 200001, 2.0)]
        a = _panel(rows)
        b = _panel(rows)
        stats = matched_sample_stats(a, b)
        assert stats["n_matched"] == 2
        assert stats["coverage_ratio_a"] == 1.0
        assert stats["coverage_ratio_b"] == 1.0

    def test_partial_overlap_computes_correct_ratios(self):
        a = _panel([(1, 200001, 1.0), (2, 200001, 2.0), (3, 200001, 3.0)])
        b = _panel([(1, 200001, 1.5), (2, 200001, 2.5)])
        stats = matched_sample_stats(a, b)
        assert stats["n_matched"] == 2
        assert stats["coverage_ratio_a"] == pytest.approx(2 / 3)
        assert stats["coverage_ratio_b"] == 1.0

    def test_no_overlap_returns_none_correlations(self):
        a = _panel([(1, 200001, 1.0)])
        b = _panel([(2, 200001, 1.0)])
        stats = matched_sample_stats(a, b)
        assert stats["n_matched"] == 0
        assert stats["pearson_corr"] is None
        assert stats["spearman_corr"] is None


class TestCorrelation:
    def test_perfectly_correlated_signals(self):
        a = _panel([(i, 200001, float(i)) for i in range(1, 11)])
        b = _panel([(i, 200001, float(i) * 2) for i in range(1, 11)])
        stats = matched_sample_stats(a, b)
        assert stats["pearson_corr"] == pytest.approx(1.0)
        assert stats["spearman_corr"] == pytest.approx(1.0)

    def test_perfectly_anti_correlated_signals(self):
        a = _panel([(i, 200001, float(i)) for i in range(1, 11)])
        b = _panel([(i, 200001, -float(i)) for i in range(1, 11)])
        stats = matched_sample_stats(a, b)
        assert stats["pearson_corr"] == pytest.approx(-1.0)


class TestSignAgreement:
    def test_all_signs_agree(self):
        a = _panel([(1, 200001, 1.0), (2, 200001, -1.0)])
        b = _panel([(1, 200001, 5.0), (2, 200001, -5.0)])
        stats = matched_sample_stats(a, b)
        assert stats["sign_agreement_rate"] == 1.0

    def test_signs_disagree(self):
        a = _panel([(1, 200001, 1.0), (2, 200001, -1.0)])
        b = _panel([(1, 200001, -5.0), (2, 200001, 5.0)])
        stats = matched_sample_stats(a, b)
        assert stats["sign_agreement_rate"] == 0.0

    def test_zero_values_excluded_from_sign_agreement(self):
        a = _panel([(1, 200001, 0.0), (2, 200001, 1.0)])
        b = _panel([(1, 200001, 5.0), (2, 200001, 1.0)])
        stats = matched_sample_stats(a, b)
        # Only row 2 counts (row 1 has a zero value in a).
        assert stats["sign_agreement_rate"] == 1.0


class TestExtremePortfolioOverlap:
    def test_identical_rankings_give_full_overlap(self):
        rows_a = [(i, 200001, float(i)) for i in range(1, 11)]
        a = _panel(rows_a)
        b = _panel(rows_a)
        stats = matched_sample_stats(a, b, extreme_quantile=0.1)
        assert stats["top_decile_overlap"] == 1.0
        assert stats["bottom_decile_overlap"] == 1.0

    def test_reversed_rankings_give_zero_top_overlap(self):
        a = _panel([(i, 200001, float(i)) for i in range(1, 11)])
        b = _panel([(i, 200001, float(11 - i)) for i in range(1, 11)])
        stats = matched_sample_stats(a, b, extreme_quantile=0.1)
        # a's top decile is permno 10; b's top decile (highest value) is permno 1.
        assert stats["top_decile_overlap"] == 0.0
        assert stats["bottom_decile_overlap"] == 0.0

    def test_computed_across_multiple_months_and_averaged(self):
        a = _panel([
            (1, 200001, 1.0), (2, 200001, 2.0),
            (1, 200002, 1.0), (2, 200002, 2.0),
        ])
        b = _panel([
            (1, 200001, 1.0), (2, 200001, 2.0),
            (1, 200002, 2.0), (2, 200002, 1.0),  # reversed in month 2
        ])
        stats = matched_sample_stats(a, b, extreme_quantile=0.5)
        # month 1: full overlap (1.0); month 2: no overlap (0.0) -> avg 0.5
        assert stats["top_decile_overlap"] == pytest.approx(0.5)
