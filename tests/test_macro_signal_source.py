"""Tests for the "time_only" (non-permno-keyed, market-wide) macro signal
source mechanism -- `MacroSignalSource` / the `fred_gdp_deflator` registration
and the `time_avail_m`-only broadcast merge in
`assemble_signal_master_table_from_sources`. Mirrors
`tests/test_crsp_fiscal_market_equity_alignment.py`'s monkeypatch style."""

from __future__ import annotations

import pandas as pd

from src.infra.data_layer import sources


def test_fred_gdp_deflator_is_registered_time_only():
    src = sources.get_source("fred_gdp_deflator")
    assert isinstance(src, sources.MacroSignalSource)
    assert src.keyed_by == "time_only"
    assert src.role == "signal"
    assert "value" in src.spec.physical_columns
    assert src.spec.concept_columns["gnp_price_level_index"] == "value"


def test_default_keyed_by_is_permno_time_for_ordinary_sources():
    # Every currently-registered ordinary source (e.g. CRSP itself) must stay
    # on the default -- this is what keeps the existing [permno, time_avail_m]
    # merge path exactly as it was before this mechanism was added.
    assert sources.get_source("crsp_msf").keyed_by == "permno_time"
    assert sources.get_source("compustat_fundamental_annual").keyed_by == "permno_time"


def test_macro_source_load_returns_none_when_snapshot_missing(tmp_path):
    src = sources.get_source("fred_gdp_deflator")
    assert src.load(tmp_path) is None


def test_macro_source_load_stamps_time_avail_m_with_lag(tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    pd.DataFrame({"yyyymm": [200303, 200306], "value": [100.0, 100.5]}).to_parquet(
        local / "gdp_deflator.parquet"
    )
    src = sources.get_source("fred_gdp_deflator")
    out = src.load(tmp_path, columns=["value"])
    assert list(out.columns) == ["time_avail_m", "value"]
    assert "permno" not in out.columns
    # default lag_months=1: 200303 -> 200304, 200306 -> 200307
    assert list(out["time_avail_m"]) == [200304, 200307]


def test_time_only_source_broadcasts_across_every_permno_at_a_period(monkeypatch, tmp_path):
    compustat = pd.DataFrame({
        "permno": [10, 20], "time_avail_m": [200304, 200304], "at": [50.0, 75.0],
    })
    macro = pd.DataFrame({"time_avail_m": [200304], "value": [101.2]})

    monkeypatch.setattr(sources, "_load_link_tables", lambda _: {})
    monkeypatch.setattr(
        sources,
        "_load_source_frame",
        lambda _d, name, _cols, _lag, _links: (
            compustat if name == "compustat_fundamental_annual" else macro
        ),
    )

    out = sources.assemble_signal_master_table_from_sources(
        tmp_path,
        {"compustat_fundamental_annual": ["at"], "fred_gdp_deflator": ["value"]},
        accounting_lag_months=6,
    )

    assert set(out["permno"]) == {10, 20}
    # the SAME macro value is broadcast onto both permnos for that period
    assert (out["value"] == 101.2).all()
    assert list(out.columns) == ["permno", "time_avail_m", "at", "value"]


def test_time_only_source_alone_falls_back_to_its_own_frame(monkeypatch, tmp_path):
    macro = pd.DataFrame({"time_avail_m": [200304, 200401], "value": [101.2, 101.5]})
    monkeypatch.setattr(sources, "_load_link_tables", lambda _: {})
    monkeypatch.setattr(sources, "_load_source_frame", lambda *a, **k: macro)

    out = sources.assemble_signal_master_table_from_sources(
        tmp_path, {"fred_gdp_deflator": ["value"]}, accounting_lag_months=6,
    )

    assert "permno" not in out.columns
    assert list(out["time_avail_m"]) == [200304, 200401]
