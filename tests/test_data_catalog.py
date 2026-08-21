"""Phase 0 catalog: the derived SIGNAL_SOURCES/LINK_TABLES must be byte-identical
to the historical hand-written literals so nothing moves, plus lookups behave.

As of 2026-07-31 the catalog only registers sources actually backed by real
data (see catalog.py's DATA_CATALOG comment): `optionm_vsurf`/
`optionm_crsp_link` (no OptionMetrics data anywhere in this project) and
`tr_13f`/`patents_nber` (tr_13f's assumed permno-keyed shape didn't match
the real, cusip-keyed data/local/13F.csv export; no NBER patents data
exists) were removed -- see docs/decision-log.md (2026-07-31 entry).

2026-08-13: `tr_13f` came back, this time correctly -- `ThirteenFSignalSource`
(`sources.py`) does the real CUSIP->permno match itself (best-effort,
most-recently-observed, not point-in-time -- see its docstring) instead of
assuming permno-keyed input.
"""

from __future__ import annotations

from src.infra.data_layer import SIGNAL_SOURCES, LINK_TABLES
from src.infra.data_layer import catalog


# The historical literals, frozen here as the golden reference.
_HISTORICAL_SIGNAL_SOURCES = {
    "crsp_msf":      {"key": "permno", "link": None,                "date": None,       "lag": 0},
    "compustat_fundamental_annual": {"key": "gvkey",  "link": "ccm",               "date": "datadate", "lag": "accounting_lag_months"},
    "ibes_statsumu": {"key": "ticker", "link": "ibes_crsp_link",    "date": "statpers", "lag": 0},
    "tr_13f":        {"key": "permno", "link": None,                "date": "yyyymm",   "lag": 2},
    # fred_gdp_deflator (2026-08-21): market-wide "time_only" macro source
    # (no permno) -- see MacroSignalSource in sources.py.
    "fred_gdp_deflator": {"key": "time_avail_m", "link": None, "date": None, "lag": 0},
}

_HISTORICAL_LINK_TABLES = {
    "ccm": {
        "key": "gvkey", "permno": "lpermno", "start": "linkdt", "end": "linkenddt",
        # Data-quality filter added 2026-07-25: link_to_permno() now enforces
        # the same linktype/linkprim rule used for the
        # legacy snapshot path (see CHANGELOG.md / decision-log.md).
        "valid_filters": {"linktype": ["LC", "LU"], "linkprim": ["P", "C"]},
        "primary_filter": {"linkprim": "P"},
    },
    "ibes_crsp_link":    {"key": "ticker", "permno": "permno",  "start": "sdate",  "end": "edate"},
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
    assert catalog.source_of_column("at") == "compustat_fundamental_annual"
    assert catalog.source_of_column("ceq") == "compustat_fundamental_annual"
    # Other registered sources
    assert catalog.source_of_column("meanest") == "ibes_statsumu"
    assert catalog.source_of_column("instown_perc") == "tr_13f"
    # Unknown -> "" (fail loud, never guess) -- also covers a source that WAS
    # registered before 2026-07-31 (no real data ever backed it)
    assert catalog.source_of_column("impl_volatility") == ""
    assert catalog.source_of_column("totally_made_up_col") == ""
    assert catalog.source_of_column("") == ""


def test_resolve_concept():
    assert catalog.resolve_concept("total_assets") == ("compustat_fundamental_annual", "at")
    assert catalog.resolve_concept("monthly_return") == ("crsp_msf", "ret")
    assert catalog.resolve_concept("analyst_forecast_mean") == ("ibes_statsumu", "meanest")
    # physical column resolves directly
    assert catalog.resolve_concept("at") == ("compustat_fundamental_annual", "at")
    # unknown -> (None, None)
    assert catalog.resolve_concept("no_such_concept") == (None, None)


def test_catalog_is_internally_valid():
    # validate_catalog() runs at import; call again explicitly.
    catalog.validate_catalog()
    for name, entry in catalog.DATA_CATALOG.items():
        link = entry["join"]["link"]
        assert link is None or link in catalog.LINK_TABLES, name
