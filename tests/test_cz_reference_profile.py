"""Tests for `src.infra.reference.load_cz_reference_profile` (Phase B,
docs/multi-config-evidence-plan.md): metadata-only C&Z reference profile
parsed from a (synthetic, in-test) SignalDoc.csv-shaped file. Explicitly does
NOT test any real firm-level signal loading -- see the module docstring for
why that's out of scope here.
"""

from __future__ import annotations

import csv

import pytest

from src.infra.reference import (
    CZReferenceProfile,
    cz_profile_to_config_override,
    fetch_cz_reference_profile_live,
    load_cz_reference_profile,
)


_HEADER = [
    "Acronym", "Return", "T-Stat", "Sign", "Stock Weight", "LS Quantile",
    "Quantile Filter", "Portfolio Period", "Start Month",
    "SampleStartYear", "SampleEndYear",
]


def _write_signaldoc(tmp_path, rows: list[dict]):
    path = tmp_path / "SignalDoc.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in _HEADER})
    return path


class TestLoadCzReferenceProfile:
    def test_loads_known_acronym(self, tmp_path):
        path = _write_signaldoc(tmp_path, [{
            "Acronym": "BM", "Return": "0.45", "T-Stat": "3.2", "Sign": "1",
            "Stock Weight": "VW", "LS Quantile": "0.1",
            "Quantile Filter": "NYSE", "Portfolio Period": "12",
            "Start Month": "6", "SampleStartYear": "1963", "SampleEndYear": "2003",
        }])
        profile = load_cz_reference_profile("BM", signaldoc_path=path)
        assert profile is not None
        assert profile.acronym == "BM"
        assert profile.mean_return == pytest.approx(0.0045)  # "0.45" is 0.45% monthly -> 0.0045 decimal
        assert profile.t_stat == 3.2
        assert profile.sign == 1
        assert profile.stock_weight == "vw"
        assert profile.ls_quantile == 0.1
        assert profile.quantile_filter == "NYSE"
        assert profile.portfolio_period == 12
        assert profile.start_month == 6
        assert profile.sample_start_year == 1963
        assert profile.sample_end_year == 2003

    def test_unknown_acronym_returns_none(self, tmp_path):
        path = _write_signaldoc(tmp_path, [{"Acronym": "BM", "Return": "0.45"}])
        assert load_cz_reference_profile("NOT_A_REAL_FACTOR", signaldoc_path=path) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert load_cz_reference_profile("BM", signaldoc_path=tmp_path / "does_not_exist.csv") is None

    def test_blank_optional_fields_are_none(self, tmp_path):
        path = _write_signaldoc(tmp_path, [{"Acronym": "X", "Return": "0.1"}])
        profile = load_cz_reference_profile("X", signaldoc_path=path)
        assert profile.t_stat is None
        assert profile.sign is None


class TestCzProfileToConfigOverride:
    """docs/step6.md gap #1: C_cz as a runnable `build_config` override."""

    def test_clean_case_all_fields_specified(self):
        profile = CZReferenceProfile(
            acronym="BM", stock_weight="vw", ls_quantile=0.1,
            quantile_filter="NYSE", portfolio_period=12, start_month=6,
            sample_start_year=1963, sample_end_year=2003,
        )
        override = cz_profile_to_config_override(profile)
        assert override == {
            "weighting_rule": "vw",
            "breakpoint_quantiles": 10,
            "breakpoint_source": "nyse",
            "accounting_lag_months": 6,
            "missing_action": "drop",
            "formation_lag_months": 1,
            "universe_filters": [
                {"field": "shrcd", "op": "in", "value": [10, 11, 12]},
                {"field": "exchcd", "op": "in", "value": [1, 2, 3]},
            ],
            "holding_period_months": 12,
            "rebalance_frequency": "annual",
            "formation_month": 6,
            "sample_start_year": 1963,
            "sample_end_year": 2003,
        }

    def test_blank_fields_fall_back_to_cz_defaults_not_engine_defaults(self):
        # SignalDoc blank for every optional field -- C&Z's OWN house
        # convention (EW / 5 groups / full-sample), not the engine's
        # (10 groups is the engine's default, per registry._resolve_ls_quantile).
        profile = CZReferenceProfile(acronym="X")
        override = cz_profile_to_config_override(profile)
        assert override["weighting_rule"] == "ew"
        assert override["breakpoint_quantiles"] == 5
        assert override["breakpoint_source"] == "full_sample"
        assert override["accounting_lag_months"] == 6
        assert override["missing_action"] == "drop"
        assert override["formation_lag_months"] == 1
        assert "rebalance_frequency" not in override
        assert "holding_period_months" not in override
        assert "formation_month" not in override

    def test_ls_quantile_as_direct_group_count(self):
        profile = CZReferenceProfile(acronym="X", ls_quantile=10.0)
        assert cz_profile_to_config_override(profile)["breakpoint_quantiles"] == 10

    def test_portfolio_period_not_in_rebalance_map_still_sets_holding_period(self):
        # e.g. a 6-month rebalance: no clean "annual"/"quarterly"/"monthly"
        # bucket, so rebalance_frequency is left unset (engine falls back to
        # holding_period_months, BacktestExecutor._rebalance_step_months).
        profile = CZReferenceProfile(acronym="X", portfolio_period=6)
        override = cz_profile_to_config_override(profile)
        assert override["holding_period_months"] == 6
        assert "rebalance_frequency" not in override

    def test_unexpected_stock_weight_raises(self):
        profile = CZReferenceProfile(acronym="X", stock_weight="equal")
        with pytest.raises(ValueError, match="stock_weight"):
            cz_profile_to_config_override(profile)

    def test_unexpected_quantile_filter_raises(self):
        profile = CZReferenceProfile(acronym="X", quantile_filter="SP500")
        with pytest.raises(ValueError, match="quantile_filter"):
            cz_profile_to_config_override(profile)


class TestFetchCzReferenceProfileLive:
    """docs/step6.md gap #1 follow-up: live `openassetpricing` fetch instead
    of a local `SignalDoc.csv` copy. Mocks `openassetpricing.OpenAP` --
    never hits the real network in tests."""

    def _fake_openap(self, monkeypatch, rows: list[dict]):
        import pandas as pd

        class FakeOpenAP:
            def __init__(self, release_year=None):
                self.release_year = release_year

            def dl_signal_doc(self, backend):
                assert backend == "pandas"
                return pd.DataFrame(rows)

        monkeypatch.setattr("openassetpricing.OpenAP", FakeOpenAP)

    def test_found_acronym_returns_profile(self, monkeypatch):
        self._fake_openap(monkeypatch, [
            {
                "Acronym": "AssetGrowth", "Return": 1.73, "T-Stat": 8.45, "Sign": -1.0,
                "Stock Weight": "EW", "LS Quantile": 0.1, "Quantile Filter": None,
                "Portfolio Period": 12.0, "Start Month": 6.0,
                "SampleStartYear": 1968, "SampleEndYear": 2003,
            },
        ])
        profile = fetch_cz_reference_profile_live("AssetGrowth", release_year=202510)
        assert profile is not None
        assert profile.stock_weight == "ew"
        assert profile.ls_quantile == 0.1
        assert profile.quantile_filter is None
        assert profile.portfolio_period == 12
        assert profile.mean_return == pytest.approx(0.0173)  # 1.73% monthly -> 0.0173 decimal
        assert profile.t_stat == 8.45

    def test_unknown_acronym_returns_none(self, monkeypatch):
        self._fake_openap(monkeypatch, [{"Acronym": "AssetGrowth", "Return": 1.73}])
        assert fetch_cz_reference_profile_live("NOT_A_REAL_FACTOR") is None

    def test_nan_numeric_cell_treated_as_none(self, monkeypatch):
        import math

        self._fake_openap(monkeypatch, [
            {
                "Acronym": "X", "Return": math.nan, "T-Stat": math.nan, "Sign": math.nan,
                "Stock Weight": "EW", "LS Quantile": math.nan, "Quantile Filter": None,
                "Portfolio Period": math.nan, "Start Month": 6.0,
                "SampleStartYear": 1968, "SampleEndYear": 2003,
            },
        ])
        profile = fetch_cz_reference_profile_live("X")
        assert profile.mean_return is None
        assert profile.ls_quantile is None
        assert profile.portfolio_period is None
