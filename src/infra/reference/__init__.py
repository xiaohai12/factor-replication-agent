"""C&Z (Chen & Zimmermann) external reference contract (Phase B,
docs/multi-config-evidence-plan.md): a normalized, versioned profile of what
C&Z's OWN metadata (`SignalDoc.csv`) reports for one factor -- their reported
monthly return/t-stat, sign, weighting, breakpoint filter, and sample
window.

Scope, stated plainly: this is metadata-only. It does NOT compute or load
C&Z's actual firm-level signal values -- that requires running C&Z's own
Predictors/*.py or Portfolios/Code/*.R source (see `data/CZ code/`) against
real WRDS data, which is a separate, substantial data-integration task this
module does not attempt. `matched_comparison.py` in this package is written
to consume a real firm-level C&Z signal series WHEN one is loaded by some
future adapter; this module only supplies the reported summary numbers that
are already available today without that adapter.

Reads `SignalDoc.csv` directly via `load_signaldoc` below (moved here from
the retired v1 extraction-eval helpers module) -- this module's
`CZReferenceProfile` is a DIFFERENT normalized shape for a different purpose
(replication-gap comparison, not MethodSpec field-by-field accuracy
scoring), but reads the identical rows.

Also hosts `load_hxz_standard_config`/`HXZ_STANDARD_CONFIG`: the
`standardized_hxz` track's config, loaded from
`data/reference/hxz_standard_config.yaml` (single canonical source; see that
file's header for field-by-field provenance against the HXZ paper).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SIGNALDOC_PATH = Path(__file__).resolve().parents[3] / "data" / "osap" / "SignalDoc.csv"
_HXZ_STANDARD_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "hxz_standard_config.yaml"
)


def load_signaldoc(signaldoc_path: Path | None = None) -> dict[str, dict]:
    """Load SignalDoc.csv into {Acronym: row_dict}."""
    path = signaldoc_path or _SIGNALDOC_PATH
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[row["Acronym"]] = row
    return rows


def load_hxz_standard_config(path: Path | None = None) -> dict[str, Any]:
    """Load the `standardized_hxz` track's config from
    `data/reference/hxz_standard_config.yaml` -- the single canonical source
    (see that file's own header comment for full field-by-field provenance).
    Re-exported as `HXZ_STANDARD_CONFIG` below and from
    `src.steps.step6_dual_track_controller`.
    """
    with open(path or _HXZ_STANDARD_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


HXZ_STANDARD_CONFIG: dict[str, Any] = load_hxz_standard_config()


@dataclass
class CZReferenceProfile:
    """One factor's C&Z-reported summary numbers, normalized.

    `acronym` is the SignalDoc.csv `Acronym` this was loaded from -- the
    join key between a `MethodSpec.factor_id` and this profile (that mapping
    itself lives outside this module; a factor->acronym manifest is the
    remaining piece of Phase B's "factor-to-C&Z manifest schema").
    """

    acronym: str
    mean_return: float | None = None      # decimal fraction, already /100'd from SignalDoc "Return" (% Monthly)
    t_stat: float | None = None           # SignalDoc "T-Stat"
    sign: int | None = None               # +1 / -1
    stock_weight: str | None = None       # "ew" | "vw"
    ls_quantile: float | None = None
    quantile_filter: str | None = None    # e.g. breakpoint universe filter
    portfolio_period: int | None = None   # holding period, months
    start_month: int | None = None        # formation month
    sample_start_year: int | None = None
    sample_end_year: int | None = None


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and value != value


def _to_float(value: Any) -> float | None:
    if value is None or value == "" or _is_nan(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _clean_str(value: Any) -> str | None:
    if value is None or _is_nan(value):
        return None
    s = str(value).strip()
    return s or None


def _profile_from_row(acronym: str, row: dict) -> CZReferenceProfile:
    """Shared row->`CZReferenceProfile` mapping for BOTH `SignalDoc.csv`
    (string cells) and a live `openassetpricing` DataFrame row (numeric
    cells, `NaN` for missing instead of an empty string) -- one mapping, so
    the two sources can never silently drift apart on field semantics.

    `Return` is `"Return (% Monthly)"` per `data/CZ code/SignalDoc-Browser.
    html` -- a raw value of `1.73` means 1.73% monthly, NOT the decimal
    fraction (0.0173) this engine's own `RunMetrics.mean_return` uses
    everywhere else. Divided by 100 here so `CZReferenceProfile.mean_return`
    is always on the SAME (decimal) scale as our own computed metrics --
    every OTHER caller must never re-apply this conversion.
    """
    stock_weight = _clean_str(row.get("Stock Weight"))
    raw_return = _to_float(row.get("Return"))
    return CZReferenceProfile(
        acronym=acronym,
        mean_return=raw_return / 100 if raw_return is not None else None,
        t_stat=_to_float(row.get("T-Stat")),
        sign=_to_int(row.get("Sign")),
        stock_weight=stock_weight.lower() if stock_weight else None,
        ls_quantile=_to_float(row.get("LS Quantile")),
        quantile_filter=_clean_str(row.get("Quantile Filter")),
        portfolio_period=_to_int(row.get("Portfolio Period")),
        start_month=_to_int(row.get("Start Month")),
        sample_start_year=_to_int(row.get("SampleStartYear")),
        sample_end_year=_to_int(row.get("SampleEndYear")),
    )


def load_cz_reference_profile(
    acronym: str, signaldoc_path: str | Path | None = None
) -> CZReferenceProfile | None:
    """Load one factor's `CZReferenceProfile` from `SignalDoc.csv` by
    `Acronym`. Returns None if the acronym isn't found or the file isn't
    available (e.g. `data/osap/SignalDoc.csv` not downloaded --
    `scripts/download_osap.py`)."""
    path = Path(signaldoc_path) if signaldoc_path else None
    try:
        rows = load_signaldoc(path) if path else load_signaldoc()
    except FileNotFoundError:
        return None

    row = rows.get(acronym)
    if row is None:
        return None

    return _apply_manual_return_fallback(_profile_from_row(acronym, row))


# Manual paper-reported fallback for a factor where C&Z's own SignalDoc
# carries NO long-short portfolio Return (only a regression coefficient --
# e.g. Bhandari 1988 `Leverage`: `Test in OP = mv reg`, blank `LS Quantile`,
# see CHANGELOG.md's Leverage hard-reject note) -- filled in from the
# ORIGINAL paper's own stated result, one factor at a time, never guessed.
# Applied only when SignalDoc's own `Return` is missing, so a real C&Z
# number always wins over this fallback.
MANUAL_PAPER_RETURN_FALLBACK: dict[str, dict[str, float]] = {
    "Leverage": {"mean_return": 0.0036, "t_stat": 2.64},
    # Datar/Naik/Radcliffe 1998 `ShareVol`: SignalDoc carries a T-Stat (8.86)
    # but no Return, so it still qualifies for this fallback (see
    # `_apply_manual_return_fallback` -- SignalDoc's own T-Stat is dropped in
    # favor of this pair, not merged with it).
    "ShareVol": {"mean_return": 0.0091, "t_stat": 3.87},
    # Lakonishok/Shleifer/Vishny 1994 `MeanRankRevGrowth`: SignalDoc has
    # neither Return nor T-Stat (only a paper-text note of t=4.5 from a
    # double sort, not the LS-portfolio field this fallback represents).
    "MeanRankRevGrowth": {"mean_return": 0.0055, "t_stat": 3.94},
}


def _apply_manual_return_fallback(profile: CZReferenceProfile) -> CZReferenceProfile:
    if profile.mean_return is not None:
        return profile
    fallback = MANUAL_PAPER_RETURN_FALLBACK.get(profile.acronym)
    if fallback is None:
        return profile
    profile.mean_return = fallback["mean_return"]
    profile.t_stat = fallback["t_stat"]
    return profile


# Pinned, not `None`/"latest" -- a caller must get the SAME SignalDoc release
# on every call for a given experiment batch, or `C_cz` silently drifts
# between two reviews of the same factor (docs/step6.md gap #1 follow-up,
# UI review flow discussion 2026-08-16). Bump deliberately, not implicitly.
DEFAULT_OPENAP_RELEASE_YEAR = 202510


def fetch_cz_reference_profile_live(
    acronym: str, release_year: int = DEFAULT_OPENAP_RELEASE_YEAR
) -> CZReferenceProfile | None:
    """Live equivalent of `load_cz_reference_profile`: fetches C&Z's
    `SignalDoc` metadata over the network via the `openassetpricing` package
    (`OpenAP(release_year=...).dl_signal_doc()`) instead of reading a local
    `SignalDoc.csv` copy -- no local file path to keep in sync. Returns None
    if `acronym` isn't in this release. Raises whatever `openassetpricing`
    raises on a network/library failure (e.g. an unreachable download link)
    -- callers needing retry/backoff (e.g. the step6 UI's preview endpoint)
    handle that themselves; this function makes exactly one attempt.
    """
    import openassetpricing as oap

    openap = oap.OpenAP(release_year=release_year)
    df = openap.dl_signal_doc("pandas")
    matches = df[df["Acronym"] == acronym]
    if matches.empty:
        return None
    return _apply_manual_return_fallback(_profile_from_row(acronym, matches.iloc[0].to_dict()))


# C&Z's own house-convention default (`01_PortfolioFunction.R:83-93`,
# docs/step6.md \u00a79): `LS Quantile` NA -> `q_cut=0.2` -> 5 groups. Deliberately
# NOT the engine's own default of 10 (`registry._resolve_ls_quantile`) --
# this function represents C_cz (what C&Z actually did), not the engine's
# house convention, and the two defaults differ.
_CZ_DEFAULT_GROUP_COUNT = 5

# C&Z's `Portfolio Period` (months) -> the engine's `rebalance_frequency`
# menu (`registry.STANDARD`, only {"annual", "quarterly", "monthly"} are
# dispatched -- `BacktestExecutor._rebalance_step_months`). A Portfolio
# Period outside this map still gets `holding_period_months` set (below),
# which the engine falls back to when `rebalance_frequency` doesn't resolve.
_PORTFOLIO_PERIOD_TO_REBALANCE_FREQUENCY: dict[int, str] = {1: "monthly", 3: "quarterly", 12: "annual"}


def _cz_breakpoint_quantiles(ls_quantile: float | None) -> int:
    """C&Z's `LS Quantile` -> a breakpoint group count for
    `build_config(..., overrides={"breakpoint_quantiles": ...})`.

    Same two accepted forms as C&Z's own convention: a value `> 1` means "N
    groups"; a value in `(0, 0.5]` means a fraction, `1/value` groups (e.g.
    `0.1` -> 10, `0.2` -> 5). `None` (SignalDoc blank) resolves to C&Z's own
    default of 5 groups (`_CZ_DEFAULT_GROUP_COUNT`), not the engine's.
    """
    value = ls_quantile if ls_quantile is not None else 0.2
    if value > 1:
        n = round(value)
        return n if n >= 2 else _CZ_DEFAULT_GROUP_COUNT
    if 0 < value <= 0.5:
        return round(1.0 / value)
    return _CZ_DEFAULT_GROUP_COUNT


def cz_profile_to_config_override(profile: CZReferenceProfile) -> dict[str, Any]:
    """Convert a `CZReferenceProfile` (C&Z's own reported empirical choices,
    parsed from `SignalDoc.csv`) into a `registry.build_config(...,
    overrides=...)`-compatible dict -- this is `C_cz` as a runnable config
    (docs/step6.md gap #1, \u00a710's field-mapping table).

    Every field falls back to C&Z's OWN house-convention default (\u00a79's
    `01_PortfolioFunction.R:83-93`), not the engine's, when SignalDoc leaves
    it blank -- `C_cz` must represent what C&Z actually ran, including their
    silent defaults, not this engine's different defaults. Unexpected values
    for `stock_weight`/`quantile_filter` (anything other than "ew"/"vw" or
    ""/"nyse") raise rather than silently guess, matching this codebase's
    fail-loud convention for unmapped/unexpected data.

    Also sets `formation_lag_months=1` -- C&Z's global 1-month
    portfolio-formation lag (`signal[, yyyymm := yyyymm + 1]`, docs/step6.md
    gap #2, now implemented in `BacktestExecutor._apply_formation_lag`),
    applied to every C&Z factor unconditionally, never read from SignalDoc.

    Also sets `universe_filters` unconditionally to C&Z's own base universe
    (`shrcd` in {10, 11, 12}, `exchcd` in {1, 2, 3}) -- `Signals/pyCode/
    SignalMasterTable.py`, the shared table every predictor is built from,
    not SignalDoc (which doesn't record it at all).
    """
    weighting = profile.stock_weight or "ew"  # C&Z default: sweight NA -> EW
    if weighting not in ("ew", "vw"):
        raise ValueError(
            f"Unexpected CZReferenceProfile.stock_weight {profile.stock_weight!r} "
            f"for acronym {profile.acronym!r}: expected 'ew'/'vw'."
        )

    quantile_filter = (profile.quantile_filter or "").strip().lower()
    if quantile_filter not in ("", "nyse"):
        raise ValueError(
            f"Unexpected CZReferenceProfile.quantile_filter {profile.quantile_filter!r} "
            f"for acronym {profile.acronym!r}: expected '' or 'NYSE'."
        )

    override: dict[str, Any] = {
        "weighting_rule": weighting,
        "breakpoint_quantiles": _cz_breakpoint_quantiles(profile.ls_quantile),
        "breakpoint_source": "nyse" if quantile_filter == "nyse" else "full_sample",
        # Always the same for every C&Z factor, never in SignalDoc (\u00a79):
        "accounting_lag_months": 6,
        "missing_action": "drop",
        "formation_lag_months": 1,
        # `Signals/pyCode/SignalMasterTable.py`'s shared "backbone" table
        # EVERY predictor is built from -- "keep if (shrcd == 10 | shrcd ==
        # 11 | shrcd == 12) & (exchcd == 1 | exchcd == 2 | exchcd == 3)".
        # Never in SignalDoc either (that file has its own dev comment: "TBC:
        # remove and use this filter as default in SignalDoc.csv") -- was
        # entirely missing from this override until 2026-08-16, silently
        # letting `cz_actual_config` inherit whatever universe_filters (or
        # none) the paper's own MethodSpec happened to carry instead of
        # C&Z's actual universe.
        "universe_filters": [
            {"field": "shrcd", "op": "in", "value": [10, 11, 12]},
            {"field": "exchcd", "op": "in", "value": [1, 2, 3]},
        ],
    }
    if profile.portfolio_period is not None:
        override["holding_period_months"] = profile.portfolio_period
        rebalance = _PORTFOLIO_PERIOD_TO_REBALANCE_FREQUENCY.get(profile.portfolio_period)
        if rebalance is not None:
            override["rebalance_frequency"] = rebalance
    if profile.start_month is not None:
        override["formation_month"] = profile.start_month
    if profile.sample_start_year is not None:
        override["sample_start_year"] = profile.sample_start_year
    if profile.sample_end_year is not None:
        override["sample_end_year"] = profile.sample_end_year
    return override


def external_reference_endpoints(
    acronym: str | None,
    paper_sample_start_year: int | None = None,
    paper_sample_end_year: int | None = None,
    signaldoc_path: str | Path | None = None,
    return_ref_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve the two EXTERNAL replication endpoints (`CZ` and `HXZ` in
    docs/paper-outline.md's notation) into the plain-dict shape
    `bundle.build_three_term_identity` consumes.

    These are the OTHER implementers' OWN measured results -- C&Z's signal
    under C&Z's config, HXZ's signal under HXZ's config -- as opposed to
    this engine's `cz_actual_config`/`standardized_hxz` tracks, which are
    the AGENT's signal under those implementers' configs. Keeping them
    separate is the whole point of the three-term decomposition: only with
    both can the signal-side and config-side of a replication gap be told
    apart.

    Window/basis provenance travels WITH each endpoint rather than being
    assumed, because the two sources differ on it (docs/paper-outline.md
    Ch.3, option (a)):

    - **C&Z** is metadata-only: `SignalDoc.csv`'s static `Return`/`T-Stat`
      are fixed to C&Z's own sample window and were produced by C&Z's own R
      engine, so `window_adjustable=False` and no window-sensitivity number
      can be computed for it.
    - **HXZ** is normally recomputed from their published testing-portfolio
      returns by `hxz_bridge`, on whichever window is asked for and using
      this engine's own Newey-West `_series_metrics`. A specifically labelled
      manual reference may be used when no such file exists; it is not
      window-adjustable and never described as a recomputation.

    Returns `{}` for an endpoint that cannot be resolved (unknown acronym,
    SignalDoc not downloaded, no HXZ testing-portfolio CSV for this factor)
    rather than raising -- a missing external reference degrades the
    three-term identity to "unavailable with a stated reason", it does not
    fail the run.
    """
    if not acronym:
        return {}

    endpoints: dict[str, dict[str, Any]] = {}

    profile = load_cz_reference_profile(acronym, signaldoc_path)
    if profile is not None and profile.mean_return is not None:
        endpoints["cz"] = {
            "spread": profile.mean_return,
            "t_stat": profile.t_stat,
            "sample_start_year": profile.sample_start_year,
            "sample_end_year": profile.sample_end_year,
            "source": "SignalDoc.csv (C&Z's own reported Return/T-Stat)",
            "window_adjustable": False,
            "window_sensitivity_spread": None,
        }

    from src.infra.reference.hxz_bridge import (
        HXZ_PAPER_SAMPLE_END_YEAR,
        HXZ_PAPER_SAMPLE_START_YEAR,
        compute_hxz_reported_both_windows,
    )

    hxz_windows = compute_hxz_reported_both_windows(
        acronym, paper_sample_start_year, paper_sample_end_year, return_ref_dir
    )
    on_paper_window = (hxz_windows or {}).get("original_insample") or {}
    on_hxz_window = (hxz_windows or {}).get("hxz_paper_sample") or {}
    if on_paper_window.get("mean_return") is not None:
        alt_spread = on_hxz_window.get("mean_return")
        is_manual_reference = on_paper_window.get("n_months") is None
        endpoints["hxz"] = {
            "spread": on_paper_window["mean_return"],
            "t_stat": on_paper_window.get("t_stat"),
            "sample_start_year": on_paper_window.get("start_year"),
            "sample_end_year": on_paper_window.get("end_year"),
            "n_months": on_paper_window.get("n_months"),
            "source": (
                str(on_paper_window.get("label"))
                if is_manual_reference
                else (
                    f"{on_paper_window.get('label')} testing-portfolio returns, recomputed on the "
                    "paper's own window with this engine's Newey-West metrics"
                )
            ),
            "window_adjustable": not is_manual_reference,
            "window_sensitivity_spread": (
                None if is_manual_reference or alt_spread is None else on_paper_window["mean_return"] - alt_spread
            ),
            "window_sensitivity_basis": {
                "alt_spread": alt_spread,
                "alt_start_year": HXZ_PAPER_SAMPLE_START_YEAR,
                "alt_end_year": HXZ_PAPER_SAMPLE_END_YEAR,
            },
        }

    return endpoints
