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

from src.infra.data_layer import sources


# ---------------------------------------------------------------------------
# Link tables: how a source's native key resolves to permno, with a validity
# window. This is the "join with what" target of every source's `join.link`.
#
# Optional per-entry keys (currently only "ccm" needs them):
#   valid_filters   — {column: [allowed values]}. Rows outside the allowed set
#                      are dropped BEFORE joining — a data-quality filter, e.g.
#                      CCM's linktype/linkprim (mirrors the same rule
#                      `CCMLinker` enforces for the legacy snapshot path: only
#                      linktype in LC/LU, linkprim in P/C are usable links).
#   primary_filter  — {column: value} marking the "primary" row. When a
#                      source row still has multiple valid link candidates
#                      (rare overlapping windows), the row matching
#                      `primary_filter` is preferred over an arbitrary pick
#                      (e.g. CCM linkprim == "P"), matching `CCMLinker`'s
#                      tie-break semantics.
# ---------------------------------------------------------------------------
# NOTE: `optionm_crsp_link` was removed 2026-07-31 -- no OptionMetrics data
# exists in this project (see docs/decision-log.md).
#
# The link-table registry lives in `sources.py` (as `LinkTableSpec` objects,
# alongside the sources that link through them, incl. the on-disk file names).
# This dict is DERIVED from that registry so importers of `catalog.LINK_TABLES`
# see the same shape as before.
LINK_TABLES: dict[str, dict[str, Any]] = sources.link_tables_view()


# ---------------------------------------------------------------------------
# The catalog. One entry per registered SIGNAL source, DERIVED from the
# `sources.py` DataSource registry (the single source of truth):
#   join:             {key, link, date, lag}  (see module docstring)
#   physical_columns: the set of physical column names this source supplies —
#                     drives `source_of_column()` (which source owns a column)
#   columns:          {concept_alias (lower-case) -> physical_column} — drives
#                     `resolve_concept()` (paper concept -> source + column).
# `lag` is either an int (months) or the marker string "accounting_lag_months"
# meaning "use the reviewed spec's accounting lag".
# ---------------------------------------------------------------------------
DATA_CATALOG: dict[str, dict[str, Any]] = sources.data_catalog_view()


# ---------------------------------------------------------------------------
# Derived views + lookups. Keep these the ONLY way other modules read the
# catalog so every consumer stays in sync with the registry automatically.
# ---------------------------------------------------------------------------

def signal_sources() -> dict[str, dict[str, Any]]:
    """The per-source join metadata (key/link/date/lag), in the `SIGNAL_SOURCES`
    dict shape."""
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
#   returns_table  — the table name passed through to `_load_data`
#   returns_layout — "crsp_ciz" (assembled from the real WRDS "new CIZ"
#                    export; see `data_layer.build_crsp_monthly_panel_ciz`).
#                    The single-pre-flattened-parquet "panel" layout was
#                    removed 2026-07-31 along with `load_msf`/`load_daily_msf`
#                    — see docs/decision-log.md same date.
# Register a new universe (e.g. an international panel) by registering a new
# `ReturnsUniverse` in `sources.py`; this dict is DERIVED from that registry.
# ---------------------------------------------------------------------------
RETURNS_UNIVERSES: dict[str, dict[str, str]] = sources.returns_universes_view()


# ---------------------------------------------------------------------------
# The on-disk file names + raw-CSV dedup filters for signal sources / link
# tables live on their `SourceSpec` / `LinkTableSpec` in `sources.py`, and the
# CIZ raw column lists + PrimaryExch->exchcd map live with the CRSP source
# there too. `sources.py` can't import `catalog` under the sources <- catalog
# <- __init__ layering, so this physical-schema detail lives with the sources
# it describes.
# ---------------------------------------------------------------------------


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
