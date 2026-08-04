"""Tests for `src.infra.reference.load_cz_reference_profile` (Phase B,
docs/multi-config-evidence-plan.md): metadata-only C&Z reference profile
parsed from a (synthetic, in-test) SignalDoc.csv-shaped file. Explicitly does
NOT test any real firm-level signal loading -- see the module docstring for
why that's out of scope here.
"""

from __future__ import annotations

import csv

from src.infra.reference import load_cz_reference_profile


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
        assert profile.mean_return == 0.45
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
        assert profile.stock_weight is None
