"""Lock the DataSource registry contract (register / get_source /
duplicate-rejection / unknown-source fail-loud) and the SourceSpec/CrspLinkSpec
declaration shapes.

The registry-contract tests use throwaway sources and a snapshotted/restored
registry (the `clean_registry` fixture) to avoid leaking into module state.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.data_layer import sources as S


class _DummySource(S.DataSource):
    def __init__(self, name: str, role: str = "signal"):
        self._name = name
        self._role = role

    @property
    def name(self) -> str:
        return self._name

    @property
    def role(self) -> str:
        return self._role

    def load(self, data_dir, columns=None, ctx=None) -> pd.DataFrame:
        return pd.DataFrame()


@pytest.fixture
def clean_registry():
    """Snapshot + restore the module registry around each test."""
    saved = dict(S._REGISTRY)
    saved_ru = dict(S._RETURNS_UNIVERSES)
    S.clear_registry()
    try:
        yield
    finally:
        S._REGISTRY.clear()
        S._REGISTRY.update(saved)
        S._RETURNS_UNIVERSES.clear()
        S._RETURNS_UNIVERSES.update(saved_ru)


def test_register_and_get_roundtrip(clean_registry):
    src = _DummySource("comp_funda")
    assert S.register(src) is src
    assert S.get_source("comp_funda") is src
    assert S.has_source("comp_funda")
    assert [s.name for s in S.iter_sources()] == ["comp_funda"]


def test_duplicate_registration_fails_loud(clean_registry):
    S.register(_DummySource("crsp_msf"))
    with pytest.raises(ValueError, match="already registered"):
        S.register(_DummySource("crsp_msf"))


def test_unknown_source_fails_loud(clean_registry):
    with pytest.raises(KeyError, match="Unknown data source"):
        S.get_source("does_not_exist")
    assert not S.has_source("does_not_exist")


def test_crsp_link_spec_permno_keyed_flag():
    permno_keyed = S.CrspLinkSpec(native_key="permno", link_table=None)
    assert permno_keyed.is_permno_keyed

    gvkey_linked = S.CrspLinkSpec(native_key="gvkey", link_table="ccm")
    assert not gvkey_linked.is_permno_keyed


def test_source_spec_holds_declarative_fields():
    spec = S.SourceSpec(
        name="comp_funda",
        role="signal",
        raw_file="comp_funda.csv",
        physical_columns={"at", "ceq"},
        concept_columns={"total_assets": "at"},
        source_key="gvkey",
        observation_date="datadate",
        lag="accounting_lag_months",
        crsp_link=S.CrspLinkSpec(native_key="gvkey", link_table="ccm"),
    )
    assert spec.role == "signal"
    assert spec.raw_filters == {}  # default-factory, not shared
    assert spec.concept_columns["total_assets"] == "at"


def test_signal_source_rejects_wrong_role():
    spec = S.SourceSpec(
        name="bad",
        role="returns",
        raw_file=None,
        physical_columns=set(),
        concept_columns={},
        source_key="permno",
        observation_date=None,
        lag=0,
        crsp_link=S.CrspLinkSpec(native_key="permno", link_table=None),
    )
    with pytest.raises(ValueError, match="role='signal'"):
        S.SignalSource(spec)


def test_unwired_loads_raise_notimplemented():
    # The abstract ReturnsUniverse base has no load (concrete subclasses like
    # CrspReturnsUniverse implement it). SignalSource.load IS implemented (see
    # test_signal_source_load_returns_none_when_file_absent).
    with pytest.raises(NotImplementedError, match="concrete subclasses"):
        S.ReturnsUniverse().load("data/local")


def test_signal_source_load_returns_none_when_file_absent(tmp_path):
    # A generic SignalSource.load returns None (source not available in this
    # data dir) rather than raising, so the assembler can drop it.
    spec = S.SourceSpec(
        name="comp_funda", role="signal", raw_file="COMPUSTAT_FUNDAMENTALS_ANNUAL.csv",
        physical_columns={"at"}, concept_columns={"total_assets": "at"},
        source_key="gvkey", observation_date="datadate", lag=0,
        crsp_link=S.CrspLinkSpec(native_key="gvkey", link_table="ccm"),
    )
    out = S.SignalSource(spec).load(tmp_path, columns=["at"], ctx={"link_tables": {}})
    assert out is None


# --- CRSP returns universe registration + DataLayer facade -----------------

def test_crsp_returns_universe_registered():
    u = S.get_returns_universe("us_equity_crsp")
    assert isinstance(u, S.CrspReturnsUniverse)
    assert u.name == "crsp"
    assert u.role == "returns"
    # also resolvable by the engine-config layout tag
    assert S.get_returns_universe_by_layout("crsp_ciz") is u
    # and present in the main registry under its name
    assert S.get_source("crsp") is u


def test_unknown_returns_universe_fails_loud():
    with pytest.raises(KeyError, match="Unknown returns universe"):
        S.get_returns_universe("tokyo_stock_exchange")
    with pytest.raises(KeyError, match="No registered returns universe"):
        S.get_returns_universe_by_layout("nikkei_layout")


def test_datalayer_facade_delegates_to_registry(monkeypatch):
    """DataLayer.load_returns / load_returns_by_layout must resolve through the
    sources registry (not re-implement loading). Patch the CRSP universe's
    load so the test needs no real CRSP data on disk."""
    import pandas as pd

    from src.infra.data_layer import DataLayer

    sentinel = pd.DataFrame({"permno": [1], "yyyymm": [200001]})
    captured = {}

    def fake_load(data_dir, columns=None, ctx=None):
        captured["data_dir"] = data_dir
        return sentinel

    monkeypatch.setattr(S.get_returns_universe("us_equity_crsp"), "load", fake_load)

    dl = DataLayer(data_path="data")
    out = dl.load_returns("us_equity_crsp", returns_dir="data/local")
    assert out is sentinel
    assert str(captured["data_dir"]) == "data/local"

    out2 = dl.load_returns_by_layout("crsp_ciz", returns_dir="data/local")
    assert out2 is sentinel
