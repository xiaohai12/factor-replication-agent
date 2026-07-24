"""Phase 0 catalog: the derived SIGNAL_SOURCES/LINK_TABLES must be byte-identical
to the historical hand-written literals so nothing moves, plus lookups behave."""

from __future__ import annotations

from src.infra.data_layer import SIGNAL_SOURCES, LINK_TABLES
from src.infra.data_layer import catalog


# The historical literals, frozen here as the golden reference.
_HISTORICAL_SIGNAL_SOURCES = {
    "crsp_msf":      {"key": "permno", "link": None,                "date": None,       "lag": 0},
    "comp_funda":    {"key": "gvkey",  "link": "ccm",               "date": "datadate", "lag": "accounting_lag_months"},
    "comp_fundq":    {"key": "gvkey",  "link": "ccm",               "date": "datadate", "lag": "accounting_lag_months"},
    "ibes_statsumu": {"key": "ticker", "link": "ibes_crsp_link",    "date": "statpers", "lag": 0},
    "optionm_vsurf": {"key": "secid",  "link": "optionm_crsp_link", "date": "date",     "lag": 0},
    "tr_13f":        {"key": "permno", "link": None,                "date": "rdate",    "lag": 0},
    "patents_nber":  {"key": "gvkey",  "link": "ccm",               "date": None,       "lag": 0},
}

_HISTORICAL_LINK_TABLES = {
    "ccm":               {"key": "gvkey",  "permno": "lpermno", "start": "linkdt", "end": "linkenddt"},
    "ibes_crsp_link":    {"key": "ticker", "permno": "permno",  "start": "sdate",  "end": "edate"},
    "optionm_crsp_link": {"key": "secid",  "permno": "permno",  "start": "sdate",  "end": "edate"},
}


def test_signal_sources_unchanged():
    assert SIGNAL_SOURCES == _HISTORICAL_SIGNAL_SOURCES


def test_link_tables_unchanged():
    assert LINK_TABLES == _HISTORICAL_LINK_TABLES


def test_source_of_column_known_and_unknown():
    # CRSP-owned columns
    assert catalog.source_of_column("ret") == "crsp_msf"
    assert catalog.source_of_column("me") == "crsp_msf"
    assert catalog.source_of_column("exchcd") == "crsp_msf"
    # Compustat-owned columns
    assert catalog.source_of_column("at") == "comp_funda"
    assert catalog.source_of_column("ceq") == "comp_funda"
    # Other registered sources
    assert catalog.source_of_column("meanest") == "ibes_statsumu"
    assert catalog.source_of_column("impl_volatility") == "optionm_vsurf"
    # Unknown -> "" (fail loud, never guess)
    assert catalog.source_of_column("totally_made_up_col") == ""
    assert catalog.source_of_column("") == ""


def test_resolve_concept():
    assert catalog.resolve_concept("total_assets") == ("comp_funda", "at")
    assert catalog.resolve_concept("monthly_return") == ("crsp_msf", "ret")
    assert catalog.resolve_concept("analyst_forecast_mean") == ("ibes_statsumu", "meanest")
    # physical column resolves directly
    assert catalog.resolve_concept("at") == ("comp_funda", "at")
    # unknown -> (None, None)
    assert catalog.resolve_concept("no_such_concept") == (None, None)


def test_catalog_is_internally_valid():
    # validate_catalog() runs at import; call again explicitly.
    catalog.validate_catalog()
    for name, entry in catalog.DATA_CATALOG.items():
        link = entry["join"]["link"]
        assert link is None or link in catalog.LINK_TABLES, name
