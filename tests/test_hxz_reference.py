"""Focused tests for Step 6's labelled HXZ manual references."""

from __future__ import annotations

from src.infra.reference import external_reference_endpoints
from src.infra.reference.hxz_bridge import compute_hxz_reported_both_windows


def test_zscore_uses_the_user_provided_hxz_reference_when_no_csv_is_wired():
    result = compute_hxz_reported_both_windows("ZScore", 1981, 1995)

    assert result is not None
    original = result["original_insample"]
    assert original == {
        "mean_return": 0.01,
        "t_stat": 0.06,
        "n_months": None,
        "start_year": 1981,
        "end_year": 1995,
        "label": "HXZ (user-provided reference; no testing-portfolio CSV)",
    }
    assert result["hxz_paper_sample"]["mean_return"] == 0.01
    assert result["hxz_paper_sample"]["t_stat"] == 0.06


def test_zscore_manual_reference_is_not_reported_as_window_adjustable(tmp_path):
    endpoints = external_reference_endpoints(
        "ZScore", paper_sample_start_year=1981, paper_sample_end_year=1995,
        signaldoc_path=tmp_path / "missing.csv",
    )

    hxz = endpoints["hxz"]
    assert hxz["spread"] == 0.01
    assert hxz["t_stat"] == 0.06
    assert hxz["source"] == "HXZ (user-provided reference; no testing-portfolio CSV)"
    assert hxz["window_adjustable"] is False
    assert hxz["window_sensitivity_spread"] is None
