"""DataSource registry — the CRSP-centric, class-based single source of truth
for the data layer. `catalog.py` derives its query views from this module, and
`data_layer/__init__.py` exposes the `DataLayer` facade over it.

Layering (single-direction dependency, must not cycle):

    sources.py  <-  catalog.py  <-  __init__.py

`sources.py` is self-contained: it must NOT import from `data_layer/__init__.py`
(which imports sources/catalog, not the other way round).

Design decisions this encodes
-----------------------------
- **CRSP-centric**: `permno` is the one security identity; every non-CRSP
  signal source declares a point-in-time `CrspLinkSpec` (native key -> permno).
- **Declarative-config-first**: an ordinary CSV/Parquet source is one
  `SourceSpec` consumed by the generic `SignalSource`; only CRSP-shaped
  specials (multi-file assembly / derived exchcd·shrcd / delisting merge) get a
  bespoke `DataSource` subclass.
- **CRSP dual role**: CRSP is BOTH the returns backbone (`CrspReturnsUniverse`)
  AND a signal source (`CrspSignalSource` — momentum/reversal/size read CRSP
  ret/prc/me directly).
- **Minimal `SourceSpec`**: carries only the fields a consumer actually reads;
  add a field the moment a real consumer needs it, not before.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Point-in-time link declaration: how a source's native identifier resolves to
# a CRSP `permno`, valid at a given date. The link table's own schema lives on
# `LinkTableSpec`; this per-source spec just names the link + the date column.
# ---------------------------------------------------------------------------
@dataclass
class CrspLinkSpec:
    #: The source's own identifier column that the link is keyed on
    #: (gvkey/ticker/cusip/…). For an already-permno-keyed source this is
    #: "permno" and `link_table` is None.
    native_key: str
    #: Name of the link table (a registered `LinkTableSpec`) used to translate
    #: `native_key` -> permno. None ⇒ the source is already permno-keyed and
    #: needs no link hop. The link table's own schema (its key/permno columns,
    #: validity window, and data-quality/primary filters) lives on the
    #: `LinkTableSpec`, not here — two sources sharing a link table (e.g.
    #: comp_funda + comp_fundq both via "ccm") reference one shared spec.
    link_table: Optional[str]

    #: The source-row date column used to pick the valid link row
    #: (`valid_from <= date <= valid_to`). Defaults to the source's
    #: `observation_date` when None.
    link_date: Optional[str] = None

    @property
    def is_permno_keyed(self) -> bool:
        """True when the source already carries `permno` and needs no link hop."""
        return self.link_table is None


@dataclass
class LinkTableSpec:
    """Physical schema of a CRSP link table (how a native key -> permno with a
    point-in-time validity window). A shared resource referenced by
    `CrspLinkSpec.link_table` — registered once, reused by every source that
    links through it."""

    name: str
    key: str                 # native-id column ON the link table (e.g. gvkey/ticker)
    permno_column: str       # permno column ON the link table (e.g. lpermno/permno)
    valid_from: str          # validity-window start column (e.g. linkdt/sdate)
    valid_to: str            # validity-window end column (e.g. linkenddt/edate)
    parquet_stem: str        # pre-converted `<stem>.parquet` filename stem
    raw_file: Optional[str] = None      # real WRDS raw CSV fallback (data/local/)
    #: Data-quality filter (rows outside allowed values dropped BEFORE joining,
    #: e.g. CCM linktype/linkprim) and a one-to-many tie-break preference
    #: (e.g. CCM linkprim == "P").
    valid_filters: Optional[dict[str, list]] = None
    primary_filter: Optional[dict[str, Any]] = None



# ---------------------------------------------------------------------------
# Declarative source spec: everything the generic `SignalSource` needs to read
# and normalize an ordinary CSV/Parquet source to [permno, time_avail_m, *cols].
# CRSP-shaped specials don't use this — they get a bespoke subclass.
# ---------------------------------------------------------------------------
@dataclass
class SourceSpec:
    #: Registry key, e.g. "comp_funda" / "ibes_statsumu".
    name: str
    #: "signal" | "returns" (CRSP is registered as both — see module docstring).
    role: str
    #: Real WRDS raw CSV filename under `data/local/` (None ⇒ parquet-only).
    raw_file: Optional[str]

    #: Physical columns this source supplies (drives "which source owns a
    #: column") and the paper-concept-alias -> physical-column map (drives
    #: concept resolution).
    physical_columns: set[str]
    concept_columns: dict[str, str]

    #: The source's native id column + its observation-date column + the
    #: availability lag (int months, or a marker like "accounting_lag_months"
    #: meaning "use the reviewed spec's accounting lag").
    source_key: str
    observation_date: Optional[str]
    lag: int | str

    #: How this source's native id resolves to permno, point-in-time.
    crsp_link: CrspLinkSpec

    #: Optional dedup/quality filter applied to the RAW input only (never to a
    #: pre-cleaned snapshot), e.g. {"indfmt": "INDL"} for Compustat. A DECLARED
    #: (reviewed) filter may remove expected duplicates; an UNEXPECTED
    #: post-clean [permno, time_avail_m] duplicate must fail loud — enforced by
    #: the loader, not here.
    raw_filters: dict[str, Any] = field(default_factory=dict)

    #: One-line human description of the SOURCE itself (e.g. "CRSP Monthly
    #: Stock File"). Purely descriptive -- surfaced in `catalog.DATA_CATALOG`
    #: for the field-help UI and fed to an LLM concept-matching prompt (see
    #: `DataDictionary.normalize_fields`); never used by any loading/join
    #: logic, so leaving it blank never changes runtime behavior.
    description: str = ""
    #: {physical_column: one-line WRDS definition}, e.g. {"at": "Total Assets
    #: (Compustat annual item AT) -- total balance sheet assets"}. Same
    #: purely-descriptive status as `description` above -- disambiguates
    #: near-synonym columns (e.g. comp_funda's "sale" vs "revt") that a bare
    #: column name or single concept alias can't distinguish on its own.
    column_descriptions: dict[str, str] = field(default_factory=dict)

    # NOTE: `snapshot_table` and `frequency` are intentionally omitted until a
    # consumer needs them (`frequency` would feed a future reviewer
    # frequency-mismatch check).


# ---------------------------------------------------------------------------
# DataSource hierarchy. `load()` returns a standardized DataFrame:
#   - signal source  -> [permno, time_avail_m, *cols]
#   - returns universe -> [permno, yyyymm, ret, me, exchcd, shrcd, siccd, dlret]
# ---------------------------------------------------------------------------
class DataSource(ABC):
    """A registered data source. Subclasses either wrap a `SourceSpec`
    (generic `SignalSource`) or hand-implement a CRSP-shaped special
    (`ReturnsUniverse`)."""

    #: The declarative spec, when this source is config-driven. Bespoke
    #: subclasses that don't use a SourceSpec leave this None and override the
    #: `name`/`role` properties.
    spec: Optional[SourceSpec] = None

    @property
    def name(self) -> str:
        if self.spec is None:
            raise NotImplementedError("bespoke DataSource must override `name`")
        return self.spec.name

    @property
    def role(self) -> str:
        if self.spec is None:
            raise NotImplementedError("bespoke DataSource must override `role`")
        return self.spec.role

    @abstractmethod
    def load(
        self,
        data_dir: str | Path,
        columns: Optional[list[str]] = None,
        ctx: Optional[dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """Read + normalize this source. See subclass docstrings for the exact
        output contract."""
        raise NotImplementedError


class SignalSource(DataSource):
    """Generic, config-driven signal source constructed from a `SourceSpec`.
    `load()` reads the needed columns, applies `raw_filters`, links the native
    key to permno point-in-time, and stamps `time_avail_m` (see `load`).
    """

    def __init__(self, spec: SourceSpec):
        if spec.role != "signal":
            raise ValueError(
                f"SignalSource requires role='signal', got {spec.role!r} for {spec.name!r}"
            )
        self.spec = spec

    def load(self, data_dir, columns=None, ctx=None):
        """Read + normalize this source to [permno, time_avail_m, *columns].

        Reads ONLY the needed columns (+ source key + observation date), applies
        the declared raw-input filters, links the native key to `permno`
        point-in-time, and computes the availability month `time_avail_m` =
        observation month + the source's lag. Returns None when neither the
        pre-converted `<name>.parquet` nor the raw CSV fallback is present (the
        source simply isn't available in this data dir — the caller drops it).
        """
        ctx = ctx or {}
        return _load_generic_signal_frame(
            self.spec,
            Path(data_dir),
            list(columns or []),
            link_tables=ctx.get("link_tables", {}),
            accounting_lag_months=int(ctx.get("accounting_lag_months", 0) or 0),
        )


class ReturnsUniverse(DataSource):
    """Base for a returns backbone (produces the [permno, yyyymm, ret, me,
    exchcd, shrcd, siccd, dlret] panel). `CrspReturnsUniverse` is the concrete
    subclass — a bespoke class (multi-file assembly + exchcd/shrcd derivation +
    delisting merge), not a SourceSpec.

    Addressable by one or more `universe_aliases` (e.g. "us_equity_crsp"), which
    the catalog's RETURNS_UNIVERSES view is derived from.
    """

    #: MethodSpec.returns_source values that select this universe.
    universe_aliases: tuple[str, ...] = ()
    #: Engine-config tags the catalog's RETURNS_UNIVERSES view is derived from.
    returns_layout: Optional[str] = None
    returns_table: Optional[str] = None

    def load(self, data_dir, columns=None, ctx=None) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "ReturnsUniverse.load is implemented by concrete subclasses "
            "(e.g. CrspReturnsUniverse)."
        )


# ---------------------------------------------------------------------------
# Registry. The one place that knows "which sources exist". `catalog.py`'s
# query views (signal_sources / concept_map / source_of_column / resolve_concept
# / RETURNS_UNIVERSES) are DERIVED from this, keeping their existing signatures
# so `method_spec.py`/reviewer don't change.
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, DataSource] = {}


def register(source: DataSource) -> DataSource:
    """Register a data source under its `name`. Fails loud on a duplicate name
    (two sources claiming the same identity is a bug, never silently the last
    one wins)."""
    name = source.name
    if name in _REGISTRY:
        raise ValueError(f"DataSource {name!r} is already registered")
    _REGISTRY[name] = source
    return source


def get_source(name: str) -> DataSource:
    """Return the registered source `name`, or fail loud (never guess a
    substitute — the CRSP-centric 'no silent default source' rule)."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown data source {name!r}: not in the DataSource registry. "
            f"Registered: {sorted(_REGISTRY)}"
        ) from None


def has_source(name: str) -> bool:
    return name in _REGISTRY


def iter_sources() -> Iterator[DataSource]:
    """Iterate registered sources (registration order)."""
    return iter(_REGISTRY.values())


def clear_registry() -> None:
    """Test-only: empty the registry (so a test can register throwaway sources
    without leaking into others)."""
    _REGISTRY.clear()
    _RETURNS_UNIVERSES.clear()


# ---------------------------------------------------------------------------
# Returns-universe sub-registry: a ReturnsUniverse is addressed BOTH by its
# `universe_aliases` (the MethodSpec.returns_source values / the catalog
# RETURNS_UNIVERSES keys, e.g. "us_equity_crsp") AND, for the engine's config
# path, by its `returns_layout` tag (e.g. "crsp_ciz"). `catalog.RETURNS_UNIVERSES`
# is DERIVED from these.
# ---------------------------------------------------------------------------
_RETURNS_UNIVERSES: dict[str, "ReturnsUniverse"] = {}


def register_returns_universe(universe: "ReturnsUniverse") -> "ReturnsUniverse":
    """Register a returns universe (also placed in the main registry under its
    `name`). Fails loud on a duplicate alias."""
    register(universe)
    for alias in universe.universe_aliases:
        if alias in _RETURNS_UNIVERSES:
            raise ValueError(f"Returns-universe alias {alias!r} is already registered")
        _RETURNS_UNIVERSES[alias] = universe
    return universe


def get_returns_universe(alias: str) -> "ReturnsUniverse":
    """Return the returns universe for a MethodSpec `returns_source` alias
    (e.g. "us_equity_crsp"), or fail loud (never guess a default panel)."""
    try:
        return _RETURNS_UNIVERSES[alias]
    except KeyError:
        raise KeyError(
            f"Unknown returns universe {alias!r}: not registered. "
            f"Registered: {sorted(_RETURNS_UNIVERSES)}"
        ) from None


def get_returns_universe_by_layout(layout: str) -> "ReturnsUniverse":
    """Return the returns universe whose `returns_layout` tag matches (the
    engine's `config['returns_layout']` path). Fails loud when no registered
    universe supplies that layout."""
    for u in _RETURNS_UNIVERSES.values():
        if getattr(u, "returns_layout", None) == layout:
            return u
    raise KeyError(
        f"No registered returns universe with returns_layout={layout!r}. "
        f"Registered layouts: "
        f"{sorted({getattr(u, 'returns_layout', None) for u in _RETURNS_UNIVERSES.values()})}"
    )


# ===========================================================================
# CRSP "new CIZ" returns universe. A bespoke class (not a SourceSpec) because it
# needs multi-file assembly (CRSP_STOCK_MONTH.csv + CRSP_DELISTING.csv), derived
# exchcd/shrcd approximations, and a delisting merge — the "CRSP-shaped special"
# case. CRSP is dual-role: the returns/universe/month backbone here AND a signal
# source (`CrspSignalSource` below — momentum/reversal/size read its ret/prc/me).
#
# WRDS's CIZ format bundles what legacy CRSP split into three tables into ONE
# already-point-in-time row per (permno, month) — CRSP_STOCK_MONTH.csv's own
# exchcd/siccd/etc. already reflect that exact month, so no windowed
# point-in-time join is needed.
#
# Known simplifications (see docs/decision-log.md 2026-07-30 — a best-effort
# adapter, not a byte-exact reproduction of CRSP's share-code/exchange-code
# logic):
#   - `exchcd`: CIZ's `PrimaryExch` letter code has no official public mapping
#     back to legacy numeric exchcd. Only N=NYSE, A=AMEX/NYSE American,
#     Q=Nasdaq are mapped; every other code -> 0 ("other/unclassified") rather
#     than guessing. So `breakpoint_source="nyse"` sees exactly the exchcd==1
#     rows.
#   - `shrcd`: CIZ has no direct share-code equivalent — approximated from
#     SecurityType/SecuritySubType/ShareType/USIncFlg (see `_ciz_shrcd`) well
#     enough for the common `shrcd in [10, 11]` universe filter, not a faithful
#     reproduction of every legacy value.
#   - **Delisting-month row is often unclassified** (confirmed vs real data,
#     2026-07-31): on the exact delisting month WRDS commonly blanks
#     PrimaryExch/SecurityType/SecuritySubType/SICCD and sets MthRet==0.0 (the
#     real delisting return lives in CRSP_DELISTING.csv's DelRet, folded in
#     below), so that row gets exchcd=0/shrcd=0 for its final month even if the
#     stock was ordinary common every prior month. This matches the CIZ file's
#     own content (not a bug).
# ===========================================================================

#: WRDS CIZ `PrimaryExch` letter code -> legacy numeric `exchcd`, and the raw
#: column lists to read from CRSP_STOCK_MONTH.csv / CRSP_STOCK_DAILY.csv. These
#: are CRSP-source physical-schema details, so they live here with the CRSP
#: source rather than in catalog.py (which can't be imported by this module
#: under the sources <- catalog <- __init__ layering).
CIZ_EXCHCD_MAP: dict[str, int] = {"N": 1, "A": 2, "Q": 3}

CIZ_MONTHLY_USECOLS: list[str] = [
    "PERMNO", "YYYYMM", "MthRet", "MthCap", "PrimaryExch", "SICCD",
    "SecurityType", "SecuritySubType", "ShareType", "USIncFlg",
]

CIZ_DAILY_USECOLS: list[str] = [
    "PERMNO", "DlyCalDt", "DlyRet", "DlyPrc", "ShrOut", "PrimaryExch", "SICCD",
    "SecurityType", "SecuritySubType", "ShareType", "USIncFlg",
]


def _ciz_shrcd(
    security_type: pd.Series,
    security_subtype: pd.Series,
    share_type: pd.Series,
    us_inc_flg: pd.Series,
) -> pd.Series:
    """Approximate the legacy CRSP `shrcd` (share code) from CIZ's own
    classification columns — see the section comment above for why this is a
    best-effort mapping:
      - EQTY/COM, US-incorporated, non-ADR share -> 11 (ordinary common)
      - EQTY/COM, non-US-incorporated, or ADR share type ("AD") -> 12
      - EQTY/CEF (closed-end fund)   -> 18
      - EQTY/ETF, or SecurityType=="FUND" -> 73
      - anything else -> 0 (unclassified)
    """
    out = pd.Series(0, index=security_type.index, dtype=int)
    is_common = security_subtype == "COM"
    is_adr = share_type == "AD"
    out[is_common & (us_inc_flg == "Y") & ~is_adr] = 11
    out[is_common & ((us_inc_flg == "N") | is_adr)] = 12
    out[security_subtype == "CEF"] = 18
    out[(security_subtype == "ETF") | (security_type == "FUND")] = 73
    return out


def build_crsp_monthly_panel_ciz(
    data_dir: str | Path,
    *,
    monthly_file: str = "CRSP_STOCK_MONTH.csv",
    delisting_file: str = "CRSP_DELISTING.csv",
    nrows: int | None = None,
) -> pd.DataFrame:
    """Assemble the standard CRSP monthly returns panel from a real WRDS "new
    CIZ" export.

    Output contract: [permno, yyyymm, ret, me, exchcd, shrcd, siccd, dlret].

    Args:
        data_dir: directory containing `monthly_file` (+ `delisting_file`).
        nrows: dev/test-only row cap forwarded to `pd.read_csv` — production
            exports here are tens of millions of rows; tests should always
            pass a small `nrows` rather than loading the full file.
    """
    d = Path(data_dir)
    monthly = pd.read_csv(
        d / monthly_file,
        usecols=CIZ_MONTHLY_USECOLS,
        dtype={"PERMNO": "int64", "YYYYMM": "int64"},
        nrows=nrows,
    )
    monthly = monthly.rename(
        columns={"PERMNO": "permno", "YYYYMM": "yyyymm", "MthRet": "ret", "MthCap": "me", "SICCD": "siccd"}
    )
    monthly["ret"] = pd.to_numeric(monthly["ret"], errors="coerce")
    monthly["me"] = pd.to_numeric(monthly["me"], errors="coerce")
    monthly["siccd"] = pd.to_numeric(monthly["siccd"], errors="coerce")
    monthly["exchcd"] = monthly["PrimaryExch"].map(CIZ_EXCHCD_MAP).fillna(0).astype(int)
    monthly["shrcd"] = _ciz_shrcd(
        monthly["SecurityType"], monthly["SecuritySubType"], monthly["ShareType"], monthly["USIncFlg"]
    )

    delist_path = d / delisting_file
    if delist_path.exists():
        delist = pd.read_csv(
            delist_path, usecols=["PERMNO", "DelistingDt", "DelRet"], dtype={"PERMNO": "int64"}
        )
        delist["DelistingDt"] = pd.to_datetime(delist["DelistingDt"], format="%Y-%m-%d", errors="coerce")
        delist = delist.dropna(subset=["DelistingDt"])
        delist["yyyymm"] = (delist["DelistingDt"].dt.year * 100 + delist["DelistingDt"].dt.month).astype(int)
        delist = delist.rename(columns={"PERMNO": "permno", "DelRet": "dlret"})
        delist = delist[["permno", "yyyymm", "dlret"]].drop_duplicates(subset=["permno", "yyyymm"])
        monthly = monthly.merge(delist, on=["permno", "yyyymm"], how="left")
    else:
        monthly["dlret"] = float("nan")

    out = monthly[["permno", "yyyymm", "ret", "me", "exchcd", "shrcd", "siccd", "dlret"]].copy()
    out["permno"] = out["permno"].astype(int)
    out["yyyymm"] = out["yyyymm"].astype(int)
    return out.reset_index(drop=True)


def load_daily_msf_ciz(
    daily_path: str | Path,
    *,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Load real WRDS CIZ daily CRSP data (`CRSP_STOCK_DAILY.csv`) into a
    standard daily-frequency shape (permno, date, ret, prc, shrout, exchcd,
    shrcd, siccd) that a daily-source-data signal (e.g. short-term reversal,
    realized volatility) can consume directly.

    `nrows`: dev/test-only row cap — the production export is on the order of
    10^8 rows; always pass a small `nrows` in tests.
    """
    df = pd.read_csv(daily_path, usecols=CIZ_DAILY_USECOLS, dtype={"PERMNO": "int64"}, nrows=nrows)
    df = df.rename(
        columns={
            "PERMNO": "permno", "DlyCalDt": "date", "DlyRet": "ret",
            "DlyPrc": "prc", "ShrOut": "shrout", "SICCD": "siccd",
        }
    )
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    df["ret"] = pd.to_numeric(df["ret"], errors="coerce")
    df["prc"] = pd.to_numeric(df["prc"], errors="coerce")
    df["siccd"] = pd.to_numeric(df["siccd"], errors="coerce")
    df["exchcd"] = df["PrimaryExch"].map(CIZ_EXCHCD_MAP).fillna(0).astype(int)
    df["shrcd"] = _ciz_shrcd(df["SecurityType"], df["SecuritySubType"], df["ShareType"], df["USIncFlg"])
    out = df[["permno", "date", "ret", "prc", "shrout", "exchcd", "shrcd", "siccd"]].copy()
    out["permno"] = out["permno"].astype(int)
    return out.reset_index(drop=True)


class CrspReturnsUniverse(ReturnsUniverse):
    """CRSP monthly returns backbone from the real WRDS "new CIZ" export.

    `load(data_dir)` -> [permno, yyyymm, ret, me, exchcd, shrcd, siccd, dlret].
    Addressed by alias "us_equity_crsp" (MethodSpec.returns_source) and by
    the engine-config layout tag "crsp_ciz".
    """

    universe_aliases = ("us_equity_crsp",)
    returns_layout = "crsp_ciz"
    returns_table = "crsp_msf"

    @property
    def name(self) -> str:
        return "crsp"

    @property
    def role(self) -> str:
        return "returns"

    def load(self, data_dir, columns=None, ctx=None) -> pd.DataFrame:
        return build_crsp_monthly_panel_ciz(data_dir)


register_returns_universe(CrspReturnsUniverse())


# ===========================================================================
# Link-table registry — the shared "join with what" target of every signal
# source's CrspLinkSpec. `catalog.LINK_TABLES` is DERIVED from this registry.
# ===========================================================================
_LINK_TABLES: dict[str, LinkTableSpec] = {}


def register_link_table(link: LinkTableSpec) -> LinkTableSpec:
    if link.name in _LINK_TABLES:
        raise ValueError(f"Link table {link.name!r} is already registered")
    _LINK_TABLES[link.name] = link
    return link


def get_link_table(name: str) -> LinkTableSpec:
    try:
        return _LINK_TABLES[name]
    except KeyError:
        raise KeyError(
            f"Unknown link table {name!r}: not registered. "
            f"Registered: {sorted(_LINK_TABLES)}"
        ) from None


def iter_link_tables() -> Iterator[LinkTableSpec]:
    return iter(_LINK_TABLES.values())


register_link_table(LinkTableSpec(
    name="ccm", key="gvkey", permno_column="lpermno",
    valid_from="linkdt", valid_to="linkenddt",
    parquet_stem="ccm_lnkhist", raw_file="CRSP_COMPUSTAT_LINK.csv",
    valid_filters={"linktype": ["LC", "LU"], "linkprim": ["P", "C"]},
    primary_filter={"linkprim": "P"},
))
register_link_table(LinkTableSpec(
    name="ibes_crsp_link", key="ticker", permno_column="permno",
    valid_from="sdate", valid_to="edate",
    parquet_stem="ibes_crsp_link", raw_file="IBES_CRSP_Link.csv",
))


# ===========================================================================
# Signal-input loading. Each function reads from the DataSource registry above
# (the single source of truth). Public names (`link_to_permno`,
# `assemble_signal_master_table`, `signal_input_sources`, `_load_source_frame`)
# keep their signatures and are re-exported from `data_layer/__init__.py` so
# every importer (incl. the generated standalone script) is unchanged.
# ===========================================================================


def link_to_permno(
    df: pd.DataFrame,
    source_name: str,
    link_tables: dict[str, pd.DataFrame],
    *,
    date_col: str | None = None,
) -> pd.DataFrame:
    """Resolve a signal-input source's native key to `permno`, point-in-time.

    `link=None` sources already have a permno; otherwise the source's key is
    joined to its declared link table and filtered to the row valid at the
    source's observation date (`start <= date <= end`, open-ended `end` treated
    as valid through the present). A link table's `valid_filters` data-quality
    filter drops out-of-set rows before joining; its `primary_filter` breaks
    remaining one-to-many ties (else the smallest permno wins, for determinism).
    Exactly one output row per input row; rows resolving to no permno are dropped.
    """
    spec = get_source(source_name).spec
    if spec is None or spec.crsp_link.is_permno_keyed:
        return df

    key = spec.source_key
    lt = get_link_table(spec.crsp_link.link_table)
    valid_filters: dict[str, list] = lt.valid_filters or {}
    primary_filter: dict[str, Any] = lt.primary_filter or {}
    filter_cols = [c for c in {*valid_filters, *primary_filter} if c not in (lt.key, lt.permno_column)]
    link_cols = [lt.key, lt.permno_column, lt.valid_from, lt.valid_to, *filter_cols]
    link_df = link_tables[spec.crsp_link.link_table][link_cols].rename(
        columns={lt.key: key, lt.permno_column: "permno"}
    )
    for col, allowed in valid_filters.items():
        link_df = link_df[link_df[col].isin(allowed)]

    work = df.reset_index(drop=True).copy()
    work["_row"] = range(len(work))
    merged = work.merge(link_df, on=key, how="left")

    dcol = date_col or spec.crsp_link.link_date or spec.observation_date
    if dcol and dcol in merged.columns:
        dt = pd.to_datetime(merged[dcol], errors="coerce")
        start = pd.to_datetime(merged[lt.valid_from], errors="coerce")
        end = pd.to_datetime(merged[lt.valid_to], errors="coerce").fillna(pd.Timestamp.max)
        keep = (start <= dt) & (dt <= end)
        merged = merged[keep | merged["permno"].isna()]

    merged = merged.drop(columns=[lt.valid_from, lt.valid_to])
    merged = merged.dropna(subset=["permno"])

    sort_cols = ["_row"]
    if primary_filter:
        (prim_col, prim_val), = primary_filter.items()
        if prim_col in merged.columns:
            merged["_primary_rank"] = (merged[prim_col] != prim_val).astype(int)
            sort_cols.append("_primary_rank")
    sort_cols.append("permno")
    merged = merged.sort_values(sort_cols).drop_duplicates("_row", keep="first")

    drop_cols = ["_row", "_primary_rank", *filter_cols]
    merged["permno"] = merged["permno"].astype(int)
    return merged.drop(columns=[c for c in drop_cols if c in merged.columns]).reset_index(drop=True)


def _load_link_tables(d: Path) -> dict[str, pd.DataFrame]:
    """Load every registered link table from `<d>/<stem>.parquet`, falling back
    to the real WRDS raw CSV export (`<d>/local/<raw_file>`)."""
    out: dict[str, pd.DataFrame] = {}
    for lt in iter_link_tables():
        p = d / f"{lt.parquet_stem}.parquet"
        if p.exists():
            out[lt.name] = pd.read_parquet(p)
            continue
        raw_path = d / "local" / lt.raw_file if lt.raw_file else None
        if raw_path is not None and raw_path.exists():
            out[lt.name] = _read_raw_link_table_csv(raw_path, lt.name)
    return out


def _read_raw_link_table_csv(path: Path, link: str) -> pd.DataFrame:
    """Read a real WRDS link-table CSV export as a fallback for
    `_load_link_tables`. Both registered raw exports already use the exact
    (lower-cased) field names the `LinkTableSpec` expects. Date columns are
    parsed with the known WRDS `YYYY-MM-DD` format (CCM's open links are coded
    as the literal `"E"`, which `errors="coerce"` turns into NaT ->
    later treated as open-ended)."""
    lt = get_link_table(link)
    filter_cols = {*(lt.valid_filters or {}), *(lt.primary_filter or {})}
    wanted_lower = {lt.key, lt.permno_column, lt.valid_from, lt.valid_to, *filter_cols}
    header = pd.read_csv(path, nrows=0).columns
    header_map = {c.lower(): c for c in header}
    usecols = [header_map[c] for c in wanted_lower if c in header_map]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    for col in (lt.valid_from, lt.valid_to):
        df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
    return df


def _resolve_lag(lag: Any, accounting_lag_months: int) -> int:
    """A source's `lag` is either an int (months) or a marker string
    ("accounting_lag_months") meaning "use the spec's accounting lag"."""
    if isinstance(lag, str):
        return int(accounting_lag_months or 0)
    return int(lag or 0)


def _apply_raw_filters(df: pd.DataFrame, raw_filters: dict[str, Any]) -> pd.DataFrame:
    """Apply a source's declared raw-input filter — a {column: value} equality
    map (e.g. Compustat `{"indfmt": "INDL"}`, IBES `{"measure": "EPS",
    "fiscalp": "ANN", "fpi": "1"}`). Compared as strings so an int/str mismatch
    (e.g. IBES `fpi` stored as 1 vs "1") still matches. This is a DECLARED,
    reviewed dedup filter, applied to the RAW input only — never silent
    de-duplication."""
    if not raw_filters:
        return df
    keep = pd.Series(True, index=df.index)
    for col, value in raw_filters.items():
        if col in df.columns:
            keep &= df[col].astype(str) == str(value)
    return df[keep]


def _read_raw_source_csv(
    path: Path, source_name: str, cols: list[str], date_col: str | None = None
) -> pd.DataFrame:
    """Read a real WRDS signal-source CSV export as a fallback for a source's
    `<name>.parquet`. Reads only the needed columns via a case-insensitive
    header probe, normalizes to lower-case, and applies the source's declared
    raw filter (`SourceSpec.raw_filters`). `date_col` is pre-parsed with the
    known WRDS `YYYY-MM-DD` format (these exports are multi-GB, so a later
    format-inferring parse would be very slow)."""
    spec = get_source(source_name).spec
    raw_filters = spec.raw_filters if spec else {}
    wanted = {*cols, *raw_filters.keys()}
    header = pd.read_csv(path, nrows=0).columns
    header_map = {c.lower(): c for c in header}
    usecols = [header_map[c] for c in wanted if c in header_map]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    df = _apply_raw_filters(df, raw_filters)
    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], format="%Y-%m-%d", errors="coerce")
    return df


def _load_generic_signal_frame(
    spec: SourceSpec,
    d: Path,
    cols: list[str],
    *,
    link_tables: dict,
    accounting_lag_months: int,
) -> pd.DataFrame | None:
    """Generic `SignalSource.load` body: read a linked/permno-keyed source to
    [permno, time_avail_m, *cols]. Returns None when the source's data file is
    absent."""
    key, date_col = spec.source_key, spec.observation_date
    read_cols = [c for c in {key, *([date_col] if date_col else []), *cols} if c]

    path = d / f"{spec.name}.parquet"
    if path.exists():
        df = pd.read_parquet(path, columns=read_cols)
    else:
        raw_path = d / "local" / spec.raw_file if spec.raw_file else None
        if raw_path is None or not raw_path.exists():
            return None
        df = _read_raw_source_csv(raw_path, spec.name, read_cols, date_col=date_col)
    df = link_to_permno(df, spec.name, link_tables)

    if not date_col or date_col not in df.columns:
        raise ValueError(
            f"Signal source {spec.name!r} has no usable observation-date "
            f"column ({date_col!r}) -- cannot compute time_avail_m. Register "
            "a per-row date column for this source before using it in a MethodSpec."
        )

    lag = _resolve_lag(spec.lag, accounting_lag_months)
    dt = pd.to_datetime(df[date_col], errors="coerce")
    total = dt.dt.year * 12 + (dt.dt.month - 1) + lag
    df["time_avail_m"] = (total // 12) * 100 + (total % 12) + 1

    out = df[["permno", "time_avail_m", *cols]].dropna(subset=["time_avail_m"])
    out["time_avail_m"] = out["time_avail_m"].astype(int)
    return out


def _load_source_frame(
    d: Path, source_name: str, cols: list[str], accounting_lag_months: int, link_tables: dict
) -> pd.DataFrame | None:
    """Load one signal-input source, resolved to [permno, time_avail_m, *cols],
    by dispatching to the registered `DataSource.load` (CRSP assembles from the
    CIZ export; other sources read their own file + link to permno)."""
    return get_source(source_name).load(
        d,
        columns=cols,
        ctx={"accounting_lag_months": accounting_lag_months, "link_tables": link_tables},
    )


def assemble_signal_master_table_from_sources(
    data_dir: str | Path,
    by_source: dict[str, list[str]],
    accounting_lag_months: int = 6,
) -> pd.DataFrame:
    """Spec-free core of `assemble_signal_master_table`: build the
    [permno, time_avail_m, ...] table from an explicit {source: [columns]} map.
    Used directly by the generated standalone backtest script."""
    d = Path(data_dir)
    link_tables = _load_link_tables(d)
    frames = [
        f for name, cols in by_source.items()
        if (f := _load_source_frame(d, name, cols, accounting_lag_months, link_tables)) is not None
    ]
    if not frames:
        return pd.DataFrame(columns=["permno", "time_avail_m"])

    master = frames[0]
    for f in frames[1:]:
        master = master.merge(f, on=["permno", "time_avail_m"], how="outer")
    return master.sort_values(["permno", "time_avail_m"]).reset_index(drop=True)


def assemble_signal_master_table(spec: Any, data_dir: str | Path) -> pd.DataFrame:
    """Assemble the signal-formula input table keyed [permno, time_avail_m]
    from however many sources the spec's fields span.

    Fields are sourced via `ImplementationResolution.concept_mapping` (see
    `script_generator.signal_input_sources_from_resolved`) and the
    accounting lag via the already-resolved config (`registry.build_config`).

    Cross-source alignment is an exact [permno, time_avail_m] outer merge,
    not an as-of join -- fine for single-source and same-frequency
    multi-source signals; mixing annual+monthly in one formula needs an as-of
    join (future)."""
    from src.steps.step3_codegen.registry import build_config
    from src.steps.step3_codegen.script_generator import signal_input_sources_from_resolved

    by_source = signal_input_sources_from_resolved(spec)
    lag_months = build_config(spec, None).get("accounting_lag_months") or 6
    return assemble_signal_master_table_from_sources(data_dir, by_source, lag_months)


class CrspSignalSource(DataSource):
    """CRSP as a SIGNAL input (CRSP's dual role): momentum/reversal/size read
    CRSP's own ret/prc/me directly. Distinct from `CrspReturnsUniverse` (the
    returns backbone) because its output contract is the signal-master shape
    [permno, time_avail_m, *cols] rather than the returns panel. Registered as
    `crsp_msf` — the signal-source name `catalog.source_of_column("ret")`
    resolves to."""

    def __init__(self, spec: SourceSpec):
        self.spec = spec

    def load(self, data_dir, columns=None, ctx=None) -> pd.DataFrame:
        # CRSP is always the real WRDS CIZ export under <data_dir>/local/.
        panel = build_crsp_monthly_panel_ciz(Path(data_dir) / "local")
        cols = list(columns or [])
        keep = ["permno", "yyyymm", *[c for c in cols if c in panel.columns]]
        return panel[keep].rename(columns={"yyyymm": "time_avail_m"})


# ---------------------------------------------------------------------------
# Signal-source registry entries. Registration ORDER matters: CRSP first, so
# `source_of_column` resolves a shared-looking column to the CRSP backbone.
# `catalog.DATA_CATALOG` / `signal_sources()` / `concept_map()` /
# `source_of_column()` / `resolve_concept()` are DERIVED from these.
# ---------------------------------------------------------------------------

register(CrspSignalSource(SourceSpec(
    name="crsp_msf", role="signal", raw_file=None,
    physical_columns={
        "permno", "yyyymm", "date", "ret", "me",
        "prc", "shrout", "shrcd", "exchcd", "siccd",
    },
    concept_columns={
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
    source_key="permno", observation_date=None, lag=0,
    crsp_link=CrspLinkSpec(native_key="permno", link_table=None),
    description=(
        "CRSP Monthly Stock File (MSF) -- the monthly return/price/shares "
        "backbone for the US common-stock universe. Also the returns panel "
        "portfolio construction runs on (see catalog.RETURNS_UNIVERSES)."
    ),
    column_descriptions={
        "permno": "CRSP permanent security identifier (the one identity every other source links to).",
        "yyyymm": "Observation year-month (int, e.g. 199201) of this row's data.",
        "date": "Calendar trading date of the observation (daily file only; monthly rows use yyyymm).",
        "ret": "Holding-period monthly total return (incl. dividends/distributions), decimal (0.05 = 5%).",
        "me": "Market equity = |prc| * shrout (shares in thousands), i.e. market capitalization.",
        "prc": "Month-end closing price; negative value means CRSP used the bid-ask midpoint (no trade).",
        "shrout": "Shares outstanding, in thousands.",
        "shrcd": "CRSP share code (10/11 = ordinary common shares; used to filter the eligible universe).",
        "exchcd": "CRSP listing exchange code (1=NYSE, 2=AMEX, 3=NASDAQ).",
        "siccd": "4-digit Standard Industrial Classification code (used for industry exclusions, e.g. financials/utilities).",
    },
)))

register(SignalSource(SourceSpec(
    name="comp_funda", role="signal", raw_file="COMPUSTAT_FUNDAMENTALS_ANNUAL.csv",
    physical_columns={
        "gvkey", "datadate", "at", "ceq", "sale", "ib",
        "dltt", "act", "lct", "dp", "capx",
        "txditc", "pstkl", "pstk", "cogs", "xint", "revt", "che", "dlc",
        "xsga", "xrd", "rect", "invt", "xpp", "drc", "drlt", "ap", "xacc",
    },
    concept_columns={
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
    source_key="gvkey", observation_date="datadate", lag="accounting_lag_months",
    crsp_link=CrspLinkSpec(native_key="gvkey", link_table="ccm"),
    raw_filters={"indfmt": "INDL"},
    description=(
        "Compustat Fundamentals Annual (industrial format, INDL) -- yearly "
        "firm-level balance sheet / income statement items, keyed on gvkey, "
        "linked to permno via the CCM link table (see LINK_TABLES['ccm'])."
    ),
    column_descriptions={
        "gvkey": "Compustat/CCM firm identifier (native key; linked to permno via 'ccm').",
        "datadate": "Fiscal year-end date of this annual record (accounting_lag_months is applied on top before the data becomes 'available').",
        "at": "Total Assets (Compustat annual item AT) -- total balance sheet assets.",
        "ceq": "Total Common/Ordinary Equity (item CEQ) -- book value of common equity.",
        "sale": "Net Sales / Turnover (item SALE) -- top-line revenue net of returns/discounts.",
        "revt": "Total Revenue (item REVT) -- broader revenue measure than SALE, includes non-operating revenue.",
        "ib": "Income Before Extraordinary Items (item IB) -- net income before extraordinary items/discontinued ops.",
        "dltt": "Long-Term Debt Total (item DLTT) -- debt due beyond one year.",
        "dlc": "Debt in Current Liabilities (item DLC) -- short-term/current portion of debt.",
        "act": "Current Assets Total (item ACT).",
        "lct": "Current Liabilities Total (item LCT).",
        "che": "Cash and Short-Term Investments (item CHE).",
        "dp": "Depreciation and Amortization (item DP), income-statement flow measure.",
        "capx": "Capital Expenditures (item CAPX).",
        "cogs": "Cost of Goods Sold (item COGS).",
        "xint": "Interest and Related Expense Total (item XINT).",
        "txditc": "Deferred Taxes and Investment Tax Credit (item TXDITC).",
        "pstkl": "Preferred Stock Liquidating Value (item PSTKL).",
        "pstk": "Preferred/Preference Stock, Total Par Value (item PSTK).",
        "xsga": "Selling, General and Administrative Expense (item XSGA).",
        "xrd": "Research and Development Expense (item XRD).",
        "rect": "Receivables Total (item RECT).",
        "invt": "Inventories Total (item INVT).",
        "xpp": "Prepaid Expenses (item XPP).",
        "drc": "Deferred Revenue, Current (item DRC).",
        "drlt": "Deferred Revenue, Long-Term (item DRLT).",
        "ap": "Accounts Payable Trade (item AP).",
        "xacc": "Accrued Expenses (item XACC).",
    },
)))

register(SignalSource(SourceSpec(
    name="comp_fundq", role="signal", raw_file="COMPUSTAT_FUNDAMENTALS_QUATER.csv",
    physical_columns={"gvkey", "datadate", "atq", "ceqq", "saleq", "ibq"},
    concept_columns={
        "total_assets_quarterly": "atq", "atq": "atq",
        "common_equity_quarterly": "ceqq", "ceqq": "ceqq",
        "sales_quarterly": "saleq", "saleq": "saleq",
        "net_income_quarterly": "ibq", "ibq": "ibq",
    },
    source_key="gvkey", observation_date="datadate", lag="accounting_lag_months",
    crsp_link=CrspLinkSpec(native_key="gvkey", link_table="ccm"),
    raw_filters={"indfmt": "INDL"},
    description=(
        "Compustat Fundamentals Quarterly (industrial format, INDL) -- "
        "quarterly firm-level balance sheet / income statement items, same "
        "gvkey/CCM linkage as comp_funda but on a quarterly reporting cadence."
    ),
    column_descriptions={
        "gvkey": "Compustat/CCM firm identifier (native key; linked to permno via 'ccm').",
        "datadate": "Fiscal quarter-end date of this record.",
        "atq": "Total Assets, quarterly (item ATQ).",
        "ceqq": "Total Common/Ordinary Equity, quarterly (item CEQQ).",
        "saleq": "Net Sales/Turnover, quarterly (item SALEQ).",
        "ibq": "Income Before Extraordinary Items, quarterly (item IBQ).",
    },
)))

register(SignalSource(SourceSpec(
    name="ibes_statsumu", role="signal", raw_file="IBES_UNADJUSTED_SUMMARY.csv",
    physical_columns={"ticker", "statpers", "meanest", "medest", "numest", "stdev"},
    concept_columns={
        "analyst_forecast_mean": "meanest", "mean_estimate": "meanest", "meanest": "meanest",
        "analyst_forecast_median": "medest", "median_estimate": "medest", "medest": "medest",
        "num_analysts": "numest", "number_of_estimates": "numest", "numest": "numest",
        "forecast_dispersion": "stdev", "forecast_stdev": "stdev", "stdev": "stdev",
    },
    source_key="ticker", observation_date="statpers", lag=0,
    crsp_link=CrspLinkSpec(native_key="ticker", link_table="ibes_crsp_link"),
    raw_filters={"measure": "EPS", "fiscalp": "ANN", "fpi": "1"},
    description=(
        "IBES Unadjusted Summary Statistics (annual EPS forecast consensus, "
        "1-year-ahead) -- analyst estimate dispersion/consensus fields, keyed "
        "on IBES ticker, linked to permno via 'ibes_crsp_link'. Pre-filtered "
        "to measure=EPS, fiscalp=ANN, fpi=1 (annual, 1-year-ahead) at load time."
    ),
    column_descriptions={
        "ticker": "IBES ticker (native key; linked to permno via 'ibes_crsp_link').",
        "statpers": "Statistical period (summary file's as-of date for this consensus snapshot).",
        "meanest": "Mean analyst EPS estimate across contributing analysts.",
        "medest": "Median analyst EPS estimate across contributing analysts.",
        "numest": "Number of analysts contributing to this consensus estimate.",
        "stdev": "Standard deviation of analyst EPS estimates (forecast dispersion).",
    },
)))


# ---------------------------------------------------------------------------
# Catalog view builders — the derivations `catalog.py` uses so its public
# query surface (DATA_CATALOG / LINK_TABLES / signal_sources / concept_map /
# source_of_column / resolve_concept / RETURNS_UNIVERSES) matches the dict
# shapes callers expect, while this registry stays the single source of truth.
# ---------------------------------------------------------------------------

def _signal_sources() -> Iterator[DataSource]:
    return (s for s in _REGISTRY.values() if s.role == "signal")


def signal_sources_view() -> dict[str, dict[str, Any]]:
    """{name: {key, link, date, lag}} for each signal source (the
    `SIGNAL_SOURCES` dict shape)."""
    out: dict[str, dict[str, Any]] = {}
    for s in _signal_sources():
        sp = s.spec
        out[s.name] = {
            "key": sp.source_key,
            "link": sp.crsp_link.link_table,
            "date": sp.observation_date,
            "lag": sp.lag,
        }
    return out


def data_catalog_view() -> dict[str, dict[str, Any]]:
    """{name: {join, physical_columns, columns, description, column_descriptions}}
    for each signal source (the `DATA_CATALOG` dict shape)."""
    out: dict[str, dict[str, Any]] = {}
    for s in _signal_sources():
        sp = s.spec
        out[s.name] = {
            "join": {
                "key": sp.source_key,
                "link": sp.crsp_link.link_table,
                "date": sp.observation_date,
                "lag": sp.lag,
            },
            "physical_columns": set(sp.physical_columns),
            "columns": dict(sp.concept_columns),
            "description": sp.description,
            "column_descriptions": dict(sp.column_descriptions),
        }
    return out


def link_tables_view() -> dict[str, dict[str, Any]]:
    """{name: {key, permno, start, end, [valid_filters], [primary_filter]}}
    (the `LINK_TABLES` dict shape — optional keys omitted when unset)."""
    out: dict[str, dict[str, Any]] = {}
    for lt in iter_link_tables():
        entry: dict[str, Any] = {
            "key": lt.key, "permno": lt.permno_column,
            "start": lt.valid_from, "end": lt.valid_to,
        }
        if lt.valid_filters:
            entry["valid_filters"] = lt.valid_filters
        if lt.primary_filter:
            entry["primary_filter"] = lt.primary_filter
        out[lt.name] = entry
    return out


def returns_universes_view() -> dict[str, dict[str, str]]:
    """{alias: {returns_table, returns_layout}} for each registered returns
    universe (the `RETURNS_UNIVERSES` dict shape)."""
    out: dict[str, dict[str, str]] = {}
    for alias, u in _RETURNS_UNIVERSES.items():
        out[alias] = {"returns_table": u.returns_table, "returns_layout": u.returns_layout}
    return out

