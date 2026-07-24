"""Declarative data catalog — the SINGLE source of truth for which data sources
exist, how each links to the CRSP `permno` backbone, and which physical column
each paper concept maps to.

Why this exists
---------------
Before this module, the same "what data sources do we have" knowledge was
scattered across four fragments that only ever agreed for CRSP/Compustat:
  - `_CONCEPT_MAP`   (concept -> physical column; CRSP/Compustat only)
  - `SIGNAL_SOURCES` (per-source join: key/link/date/lag)
  - `LINK_TABLES`    (link-table key -> permno + validity window)
  - `DataDictionary` (field-existence registry; was empty)

The catalog unifies them so that registering a NEW data source (IBES,
OptionMetrics, 13F, patents, …) is a single declarative entry here, after
which every paper that uses that source is handled automatically. This is the
"register once" target of the reviewer's hard-block on unknown sources: an
unregistered source is blocked at review, a human adds one catalog entry, done.

Join model (important)
----------------------
`join.key` is the SOURCE's own native identifier (gvkey/ticker/secid/permno),
NOT permno. `join.link` names a `LINK_TABLES` entry — that link table is "what
you join with" to translate the native key into a permno, point-in-time
(`start <= observation_date <= end`). It is a 2-hop process:

    native key --(link table, point-in-time)--> permno
    all sources --(outer merge)--> the [permno, time_avail_m] backbone

`link=None` means the source is already permno-keyed (CRSP, 13F).

Invariants (enforced by `validate_catalog()` and the reviewer):
  - every non-null `join.link` resolves to a `LINK_TABLES` entry
  - `join` has exactly the keys {key, link, date, lag}
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Link tables: how a source's native key resolves to permno, with a validity
# window. This is the "join with what" target of every source's `join.link`.
# ---------------------------------------------------------------------------
LINK_TABLES: dict[str, dict[str, str]] = {
    "ccm":               {"key": "gvkey",  "permno": "lpermno", "start": "linkdt", "end": "linkenddt"},
    "ibes_crsp_link":    {"key": "ticker", "permno": "permno",  "start": "sdate",  "end": "edate"},
    "optionm_crsp_link": {"key": "secid",  "permno": "permno",  "start": "sdate",  "end": "edate"},
}

# File name of each link table on disk (LINK_TABLES key -> parquet stem).
LINK_TABLE_FILES: dict[str, str] = {
    "ccm": "ccm_lnkhist",
    "ibes_crsp_link": "ibes_crsp_link",
    "optionm_crsp_link": "optionm_crsp_link",
}


# ---------------------------------------------------------------------------
# The catalog. One entry per registered data source:
#   join:             {key, link, date, lag}  (see module docstring)
#   physical_columns: the set of physical column names this source supplies —
#                     drives `source_of_column()` (which source owns a column)
#   columns:          {concept_alias (lower-case) -> physical_column} — drives
#                     `resolve_concept()` (paper concept -> source + column).
#                     Aliases are matched exactly; the CRSP/Compustat aliases
#                     mirror the historical `_CONCEPT_MAP` so nothing moves.
# `lag` is either an int (months) or the marker string "accounting_lag_months"
# meaning "use the reviewed spec's accounting lag".
# ---------------------------------------------------------------------------
DATA_CATALOG: dict[str, dict[str, Any]] = {
    "crsp_msf": {
        "join": {"key": "permno", "link": None, "date": None, "lag": 0},
        "physical_columns": {
            "permno", "yyyymm", "date", "ret", "me",
            "prc", "shrout", "shrcd", "exchcd", "siccd",
        },
        "columns": {
            "monthly_return": "ret", "ret": "ret", "monthly stock return": "ret",
            "monthly return": "ret", "stock return": "ret",
            "market_equity": "me", "me": "me", "market_equity_june": "me",
            "market value": "me", "market capitalization": "me",
            "market value of equity": "me", "market cap": "me",
            "listing_exchange": "exchcd", "exchcd": "exchcd",
            "exchange": "exchcd", "exchange code": "exchcd",
            "sic_code": "siccd", "siccd": "siccd", "sic": "siccd",
            "four-digit sic": "siccd", "industry code": "siccd",
            "shrcd": "shrcd", "share code": "shrcd", "share_code": "shrcd",
            "shrout": "shrout", "shares outstanding": "shrout",
            "prc": "prc", "price": "prc", "closing price": "prc",
        },
    },
    "comp_funda": {
        "join": {"key": "gvkey", "link": "ccm", "date": "datadate", "lag": "accounting_lag_months"},
        "physical_columns": {
            "gvkey", "datadate", "at", "ceq", "sale", "ib",
            "dltt", "act", "lct", "dp", "capx",
            "txditc", "pstkl", "pstk", "cogs", "xint", "revt", "che", "dlc",
            "xsga", "xrd", "rect", "invt", "xpp", "drc", "drlt", "ap", "xacc",
        },
        "columns": {
            "total_assets": "at", "at": "at", "compustat data item 6": "at",
            "data6": "at", "data item 6": "at",
            "book_equity": "ceq", "ceq": "ceq", "common equity": "ceq",
            "sales": "sale", "sale": "sale", "revenue": "sale",
            "revenues": "revt", "revt": "revt",
            "net_income": "ib", "ib": "ib", "income before extraordinary": "ib",
            "long_term_debt": "dltt", "dltt": "dltt", "long term debt": "dltt",
            "short_term_debt": "dlc", "dlc": "dlc",
            "current_assets": "act", "act": "act",
            "current_liabilities": "lct", "lct": "lct",
            "cash": "che", "che": "che",
            "depreciation": "dp", "dp": "dp",
            "capital_expenditure": "capx", "capx": "capx",
            "cost_of_goods_sold": "cogs", "cogs": "cogs",
            "interest_expense": "xint", "xint": "xint",
            "deferred_taxes": "txditc", "txditc": "txditc",
            "preferred_stock": "pstkl", "pstkl": "pstkl", "pstk": "pstk",
            "sga_expense": "xsga", "xsga": "xsga",
            "rd_expense": "xrd", "xrd": "xrd",
            "receivables": "rect", "rect": "rect",
            "inventory": "invt", "invt": "invt",
            "prepaid_expenses": "xpp", "xpp": "xpp",
            "deferred_revenue_current": "drc", "drc": "drc",
            "deferred_revenue_longterm": "drlt", "drlt": "drlt",
            "accounts_payable": "ap", "ap": "ap",
            "accrued_expenses": "xacc", "xacc": "xacc",
        },
    },
    "comp_fundq": {
        "join": {"key": "gvkey", "link": "ccm", "date": "datadate", "lag": "accounting_lag_months"},
        "physical_columns": {"gvkey", "datadate", "atq", "ceqq", "saleq", "ibq"},
        "columns": {
            "total_assets_quarterly": "atq", "atq": "atq",
            "common_equity_quarterly": "ceqq", "ceqq": "ceqq",
            "sales_quarterly": "saleq", "saleq": "saleq",
            "net_income_quarterly": "ibq", "ibq": "ibq",
        },
    },
    "ibes_statsumu": {
        "join": {"key": "ticker", "link": "ibes_crsp_link", "date": "statpers", "lag": 0},
        "physical_columns": {"ticker", "statpers", "meanest", "medest", "numest", "stdev"},
        "columns": {
            "analyst_forecast_mean": "meanest", "mean_estimate": "meanest", "meanest": "meanest",
            "analyst_forecast_median": "medest", "median_estimate": "medest", "medest": "medest",
            "num_analysts": "numest", "number_of_estimates": "numest", "numest": "numest",
            "forecast_dispersion": "stdev", "forecast_stdev": "stdev", "stdev": "stdev",
        },
    },
    "optionm_vsurf": {
        "join": {"key": "secid", "link": "optionm_crsp_link", "date": "date", "lag": 0},
        "physical_columns": {"secid", "date", "impl_volatility", "delta", "days"},
        "columns": {
            "implied_volatility": "impl_volatility", "implied_vol": "impl_volatility",
            "impl_volatility": "impl_volatility",
            "option_delta": "delta", "delta": "delta",
            "days_to_maturity": "days", "days": "days",
        },
    },
    "tr_13f": {
        "join": {"key": "permno", "link": None, "date": "rdate", "lag": 0},
        "physical_columns": {"permno", "rdate", "shares", "instown_perc"},
        "columns": {
            "institutional_ownership": "instown_perc", "instown_perc": "instown_perc",
            "institutional_shares": "shares", "shares": "shares",
        },
    },
    "patents_nber": {
        "join": {"key": "gvkey", "link": "ccm", "date": None, "lag": 0},
        "physical_columns": {"gvkey", "npats", "ncites"},
        "columns": {
            "patent_count": "npats", "npats": "npats",
            "citation_count": "ncites", "ncites": "ncites",
        },
    },
}


# ---------------------------------------------------------------------------
# Derived views + lookups. Keep these the ONLY way other modules read the
# catalog so the four historical fragments stay in sync automatically.
# ---------------------------------------------------------------------------

def signal_sources() -> dict[str, dict[str, Any]]:
    """The per-source join metadata (key/link/date/lag), byte-compatible with
    the historical `SIGNAL_SOURCES` literal."""
    return {name: dict(entry["join"]) for name, entry in DATA_CATALOG.items()}


def concept_map() -> dict[str, str]:
    """Flattened concept-alias -> physical-column map across all sources
    (superset of the historical CRSP/Compustat-only `_CONCEPT_MAP`)."""
    out: dict[str, str] = {}
    for entry in DATA_CATALOG.values():
        out.update(entry.get("columns", {}))
    return out


def source_of_column(column: str) -> str:
    """Return the source that owns a physical `column`, or "" when no
    registered source declares it (the fail-loud signal: do NOT guess).

    CRSP is checked first so shared-looking columns resolve to the returns
    backbone, matching the historical CRSP-first assumption."""
    if not column:
        return ""
    for name, entry in DATA_CATALOG.items():
        if column in entry.get("physical_columns", set()):
            return name
    return ""


def resolve_concept(concept: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve a paper `concept` (or physical column) to (source, column).

    Returns (None, None) when nothing in the catalog matches — the caller must
    then treat the field as unresolved (fail loud), never guess a source."""
    if not concept:
        return None, None
    key = concept.strip().lower()
    for name, entry in DATA_CATALOG.items():
        cols = entry.get("columns", {})
        if key in cols:
            return name, cols[key]
        # also allow resolving a physical column name directly
        if key in entry.get("physical_columns", set()):
            return name, key
    return None, None


# ---------------------------------------------------------------------------
# Returns-universe registry: which stock-return panel the portfolio-construction
# side (breakpoints / returns / long-short) runs on. This is a SEPARATE concern
# from signal-input sources above — but, like them, it must come from the
# reviewed MethodSpec (`MethodSpec.returns_universe`), never a hardcoded
# default. CRSP US equity is ONE registered entry here, not a fallback.
#
# Each entry maps to the BacktestExecutor `_load_data` config:
#   returns_table  — parquet stem under <data_path>/raw/ (panel layout)
#   returns_layout — "panel" (single flat parquet) or "crsp_raw" (assembled
#                    from separate WRDS-shaped tables; see assemble_panel)
# Register a new universe (e.g. an international panel) by adding one entry.
# ---------------------------------------------------------------------------
RETURNS_UNIVERSES: dict[str, dict[str, str]] = {
    "us_equity_crsp": {"returns_table": "crsp_msf", "returns_layout": "panel"},
    "us_equity_crsp_raw": {"returns_table": "crsp_msf", "returns_layout": "crsp_raw"},
}


#: The standardized default returns universe (CRSP monthly). Used when a
#: MethodSpec leaves `returns_universe` unset — the pipeline now defaults the
#: stock-return panel to CRSP monthly rather than hard-blocking.
DEFAULT_RETURNS_UNIVERSE = "us_equity_crsp"


def returns_universe_config(name: Optional[str]) -> Optional[dict[str, str]]:
    """Return the {returns_table, returns_layout} for a registered returns
    universe. When `name` is unset, default to the standardized CRSP monthly
    panel (`DEFAULT_RETURNS_UNIVERSE`). An explicitly-set but unregistered name
    returns None so the caller can surface it (the reviewer flags an
    unregistered universe)."""
    if not name:
        name = DEFAULT_RETURNS_UNIVERSE
    reg = RETURNS_UNIVERSES.get(name)
    return dict(reg) if reg else None


def validate_catalog() -> None:
    """Fail fast at import time if the catalog is internally inconsistent."""
    for name, entry in DATA_CATALOG.items():
        join = entry.get("join", {})
        if set(join) != {"key", "link", "date", "lag"}:
            raise ValueError(
                f"catalog source {name!r}: join must have exactly "
                f"{{key, link, date, lag}}, got {sorted(join)}"
            )
        link = join.get("link")
        if link is not None and link not in LINK_TABLES:
            raise ValueError(
                f"catalog source {name!r}: join.link={link!r} has no LINK_TABLES entry"
            )


validate_catalog()
