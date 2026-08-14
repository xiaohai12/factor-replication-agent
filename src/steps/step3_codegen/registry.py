"""Codegen decision layer: how an approved MethodSpec resolves into a run
config for the standardized backtest engine.

The engine is fully standardized: there is no LLM-generated hook code. Every
portfolio-construction choice is *selected* from a fixed menu of built-in
implementations (see ``STANDARD`` below). A MethodSpec value outside the menu
is deterministically clamped to the menu default (``build_config`` /
``_clamp``) rather than triggering code generation.

This module answers "how does a MethodSpec resolve into a run config" — not
"what does a backtest compute" (that's the single-file
`src/infra/backtest_engine/__init__.py`).

Lives in `step3_codegen/` (not `src/infra/backtest_engine/`) because every
function here is only ever called at generation time — by
`script_generator.generate_backtest_script()` (`build_config`) — never by
`BacktestExecutor`'s own run-time dispatch (`run_with_config`/`_dispatch`),
which only consumes the already-resolved config dict `build_config` produced.
The engine library depends on this decision layer for MethodSpec-to-config
resolution; this module never depends on the engine library.
"""

from __future__ import annotations

import warnings
from typing import Any

from src.infra.data_layer import catalog
from src.infra.models.method_spec import (
    FILTER_VALUE_ENCODINGS,
    MAX_SUPPORTED_SORT_DIMENSIONS,
    MissingStage,
    ResolvedMethodSpec,
    RETURNS_PANEL_NATIVE_COLUMNS,
    SortRole,
    TimeUnit,
)


class ConfigOverrideError(ValueError):
    """Raised by `build_config` when a caller-supplied override is invalid:
    an unknown config key, or a value outside the menu for a menu-governed
    key. See docs/multi-config-evidence-plan.md Phase 0.2 -- callers must
    never have an override silently ignored or clamped away, since that
    would make an experiment's config-diff attribution false (e.g. a track
    named "ablation_weighting_ew" that actually ran on the default weighting
    because the override key was misspelled).
    """


# The full set of keys `build_config` may produce (excluding the
# conditionally-present `returns_table`/`returns_layout`/`substitutions`/
# `defaults_applied`, which are handled separately below). A caller override
# for any OTHER key is almost certainly a typo and is rejected rather than
# silently merged in.
KNOWN_CONFIG_KEYS: frozenset[str] = frozenset({
    "breakpoint_source", "breakpoint_quantiles", "weighting_rule",
    "rebalance_frequency", "holding_period_months", "accounting_lag_months",
    "signal_max_staleness_months", "missing_action", "universe",
    "formation_month", "formation_month_explicit", "long_leg", "short_leg",
    "sample_start_year", "sample_end_year", "publication_year",
    "universe_filters", "apply_delisting_returns", "return_combination_type",
    "return_basis", "estimator",
    "returns_table", "returns_layout", "unapplied_universe_filters",
    "universe_filter_join_sources",
})

# Which config keys are governed by a fixed menu (see STANDARD below) --
# an override for one of these must be a menu member, not just any string.
_OVERRIDE_MENU: dict[str, set[str]] = {}  # populated after STANDARD is defined

# Which pipeline stage each resolved-config key belongs to, so a track-vs-track
# config diff reports *where* two runs diverge rather than just listing keys.
# Single source of truth (moved from step7_replication_diff/bundle.py 2026-08-03,
# which now imports it from here) -- see docs/multi-config-evidence-plan.md
# Decision 2 (per-key stage taxonomy). Split into two families used to derive
# identification level: "signal_input" changes the realized signal; the rest
# (portfolio/universe/sample/estimator) only change how an already-computed
# signal is used, never its value.
CONFIG_KEY_STAGE: dict[str, str] = {
    # signal_input — how the raw signal panel is built/aligned
    "accounting_lag_months": "signal_input",
    "signal_max_staleness_months": "signal_input",
    "missing_action": "signal_input",
    # portfolio — sorting, weighting, rebalancing, leg definition
    "breakpoint_source": "portfolio",
    "breakpoint_quantiles": "portfolio",
    "weighting_rule": "portfolio",
    "rebalance_frequency": "portfolio",
    "holding_period_months": "portfolio",
    "formation_month": "portfolio",
    "formation_month_explicit": "portfolio",
    "long_leg": "portfolio",
    "short_leg": "portfolio",
    "return_combination_type": "portfolio",
    # universe — which firm-months are eligible, and the returns panel
    "universe": "universe",
    "universe_filters": "universe",
    "unapplied_universe_filters": "universe",
    "universe_filter_join_sources": "universe",
    "apply_delisting_returns": "universe",
    "returns_table": "universe",
    "returns_layout": "universe",
    # sample — the calendar window / metric split
    "sample_start_year": "sample",
    "sample_end_year": "sample",
    "publication_year": "sample",
    # estimator — how the return series is measured
    "return_basis": "estimator",
    "estimator": "estimator",
    "substitutions": "estimator",
    "defaults_applied": "estimator",
}

UNCLASSIFIED_STAGE = "unclassified"


def stage_of(config_key: str) -> str:
    """Return the pipeline stage a resolved-config key belongs to."""
    return CONFIG_KEY_STAGE.get(config_key, UNCLASSIFIED_STAGE)


# ---------------------------------------------------------------------------
# Standard menu — the values for which the engine has a built-in
# implementation. A ResolvedMethodSpec value outside its menu is clamped to
# the menu default by `build_config`/`_clamp` (never code-generated).
# ---------------------------------------------------------------------------

STANDARD: dict[str, set[str]] = {
    "breakpoint_source": {"full_sample", "nyse"},
    "weighting": {"vw", "ew"},
    "missing_action": {"drop", "unspecified"},
    "return_combination": {
        "extreme_group_spread",
        "single_signal_portfolio_return",
        # BacktestExecutor.combine_portfolio_returns implements all four
        # supported return-combination types. Note
        # average_leg_spread only *actually* averages multiple portfolios
        # per leg when config["long_portfolios"]/["short_portfolios"] are
        # explicitly given (free-text leg descriptions aren't auto-parsed);
        # without them it's numerically identical to extreme_group_spread.
        "average_leg_spread",
        "full_portfolio_return",
        "unspecified",
    },
}


_OVERRIDE_MENU.update({
    "breakpoint_source": STANDARD["breakpoint_source"],
    "weighting_rule": STANDARD["weighting"],
    "missing_action": STANDARD["missing_action"],
    "return_combination_type": STANDARD["return_combination"],
})


def ev(v: Any) -> str:
    """Return string value of an enum or plain string."""
    if hasattr(v, "value"):
        return v.value
    return str(v) if v is not None else "unspecified"

def _clamp(val: Any, allowed: set[str], default: str) -> str:
    """Resolve a MethodSpec field to a value the engine actually implements.

    ``unspecified`` (or None) and any value outside ``allowed`` both resolve to
    ``default`` — the engine is standardized, so an out-of-menu empirical
    choice is deterministically clamped to the built-in default rather than
    triggering code generation.
    """
    return _clamp_with_provenance(val, allowed, default)[0]


def _clamp_with_provenance(val: Any, allowed: set[str], default: str) -> tuple[str, bool]:
    """Same resolution as `_clamp`, plus whether `default` was actually used
    (as opposed to the MethodSpec supplying an already-valid menu value) --
    the provenance `build_config` needs for its `defaults_applied` list.
    """
    v = ev(val)
    if v == "unspecified" or v not in allowed:
        return default, True
    return v, False


def _resolve_ls_quantile(ls_quantile: float | None) -> int:
    """Resolve `MethodSpec.portfolio.sort.ls_quantile` into a breakpoint
    group count.

    Two accepted forms: a value `> 1` means "N groups" (e.g. `10` -> decile
    sort); a value in `(0, 0.5]` means a fraction, `1/value` groups (e.g.
    `0.1` -> decile). Any other value -- `None`, `<= 0`, a fraction `> 0.5`
    (which would mean fewer than 2 groups), or a `> 1` value that doesn't
    round to at least 2 whole groups -- is invalid/ambiguous for a
    long-short sort and is clamped to the standard 10-group (decile)
    default, same "clamp an out-of-menu value to the canonical default"
    policy as every other field in `build_config`. Without this, a negative
    or degenerate value (e.g. `-1` -> `-1` "groups", `1.5`/`3.3` silently
    truncated to `1`/`3` via a bare `int()`) used to reach
    `compute_breakpoints`/`assign_portfolios` unvalidated and fail deep
    inside the engine (`np.linspace(0, 1, 0)` producing zero breakpoint
    columns -> `IndexError` on `bins[0]`) instead of resolving to a sensible
    value at config-build time. See docs/decision-log.md for the fix this
    implements.
    """
    if ls_quantile is None:
        return 10
    if ls_quantile > 1:
        n = round(ls_quantile)
        return n if n >= 2 else 10
    if 0 < ls_quantile <= 0.5:
        return round(1.0 / ls_quantile)
    return 10


def _validate_overrides(resolved_config: dict, overrides: dict) -> None:
    """Reject an override before it's merged into the resolved config.

    Two hard failures (raise `ConfigOverrideError`), matching
    docs/multi-config-evidence-plan.md Phase 0.2:

    - an override key that isn't one `build_config` actually produces (a
      typo, or a key the engine has no menu for at all) -- would otherwise
      be silently merged in and read by nothing;
    - an override value for a menu-governed key (breakpoint_source,
      weighting_rule, missing_action, return_combination_type) that isn't a
      menu member -- would otherwise be silently clamped away by whatever
      *reads* the config later, making the override a no-op without saying so.

    One soft warning (via `warnings.warn`, not raised): an override whose
    value is identical to what the MethodSpec already resolved to. This is
    not rejected outright -- a named track like `standardized_hxz` legitimately
    ships a whole bundle of settings as one package, and one of them
    coinciding with the paper's own choice is a meaningful, reportable fact
    (not a caller mistake) rather than an error. Strict no-op rejection for a
    single declared experiment is Phase A2's job (`ExperimentSpec.expected_diff`
    cross-check), not this general-purpose resolver's.
    """
    for key, value in overrides.items():
        if key not in KNOWN_CONFIG_KEYS:
            raise ConfigOverrideError(
                f"Unknown config override key {key!r}. Valid keys: "
                f"{sorted(KNOWN_CONFIG_KEYS)}"
            )
        menu = _OVERRIDE_MENU.get(key)
        normalized = ev(value) if menu is not None else value
        if menu is not None and normalized not in menu:
            raise ConfigOverrideError(
                f"Invalid override value {value!r} for {key!r}: "
                f"must be one of {sorted(menu)}"
            )
        if key in resolved_config and resolved_config[key] == normalized:
            warnings.warn(
                f"Config override {key!r}={value!r} is a no-op: the "
                "MethodSpec already resolves to this value.",
                stacklevel=3,
            )


def build_config(spec: ResolvedMethodSpec, overrides: dict | None) -> dict:
    """Build run config from an approved `ResolvedMethodSpec` -- see
    `_build_config_from_resolved` below for the full resolution logic.
    """
    return _build_config_from_resolved(spec, overrides)


# ---------------------------------------------------------------------------
# ResolvedMethodSpec resolution. Produces the config-dict shape
# `BacktestExecutor.run_with_config` consumes.
# ---------------------------------------------------------------------------

_REBALANCE_FREQUENCY_FROM_TIME_UNIT: dict[TimeUnit, str] = {
    TimeUnit.YEAR: "annual",
    TimeUnit.QUARTER: "quarterly",
    TimeUnit.MONTH: "monthly",
}

_LAG_UNIT_TO_MONTHS: dict[TimeUnit, int] = {
    TimeUnit.MONTH: 1,
    TimeUnit.QUARTER: 3,
    TimeUnit.YEAR: 12,
}


def _accounting_lag_months(data_availability) -> tuple[int | None, bool]:
    """Returns `(months, unit_unsupported)`. `unit_unsupported=True` means
    the paper DID specify a `lag_value`/`lag_unit`, but `lag_unit` isn't one
    this month-granularity config field can represent (e.g. `TimeUnit.DAY`)
    -- distinct from "paper didn't specify anything at all" (`months=None,
    unit_unsupported=False`), so the caller can record an honest reason
    instead of falsely claiming the field was unspecified (see
    docs/resolve-diagnostics-gaps.md problem 2)."""
    if data_availability.lag_value is None:
        return None, False
    multiplier = _LAG_UNIT_TO_MONTHS.get(data_availability.lag_unit)
    if multiplier is None:
        return None, True
    return data_availability.lag_value * multiplier, False


def _resolved_column(resolution, concept_id: str) -> str:
    """Physical column for a paper concept, via `ImplementationResolution.
    concept_mapping` -- fails loudly (never silently guesses a column) when
    unmapped, matching the engine's existing fail-loud conventions for a
    missing physical field."""
    mapping = resolution.concept_mapping.get(concept_id)
    if mapping is None:
        raise ValueError(
            f"concept_id {concept_id!r} has no physical column mapping in "
            "ImplementationResolution.concept_mapping -- register one before "
            "building the run config."
        )
    return mapping.column


def _translate_filter_value(column: str, value: Any) -> Any:
    """Translate a universe filter's paper-vocabulary `value` (e.g.
    `["NYSE", "Amex", "NASDAQ"]`) into `column`'s actual physical encoding,
    via `FILTER_VALUE_ENCODINGS` (docs/resolve-diagnostics-gaps.md problem
    3) -- e.g. `exchcd` is a numeric column, so `series.isin(["NYSE", ...])`
    would otherwise silently be all-False, filtering the universe down to
    zero rows with no error anywhere near this call.

    Fails loud (never silently guesses) when `column` HAS a registered
    encoding but a string element doesn't match any of its known labels --
    that combination means either the paper used wording not yet
    registered, or a genuine typo; either way this must not be passed
    through as-is (same "never silently ignore a stated universe
    restriction" policy as `apply_universe_filters`'s missing-field check).
    Elements that are already numeric (or `column` has no registered
    encoding at all) pass through unchanged.
    """
    encoding = FILTER_VALUE_ENCODINGS.get(column)
    if encoding is None:
        return value
    items = value if isinstance(value, list) else [value]
    translated = []
    for item in items:
        if not isinstance(item, str):
            translated.append(item)
            continue
        key = item.strip().lower()
        if key not in encoding:
            raise ValueError(
                f"Universe filter value {item!r} has no registered encoding for "
                f"column {column!r} (known: {sorted(encoding)}) -- register it in "
                "FILTER_VALUE_ENCODINGS (src/infra/models/method_spec.py) or "
                "correct the MethodSpec's filter value."
            )
        translated.append(encoding[key])
    return translated if isinstance(value, list) else translated[0]


def _applied_universe_filters(paper) -> list:
    """`paper.universe.filters` minus (a) every filter a human has explicitly
    marked `accepted_unapplied` (the "other" escape hatch -- see
    `FilterSpec.accepted_unapplied`'s docstring), and (b) every filter whose
    `derivation` is non-null. A non-null `derivation` means the paper's
    condition needs a COMPUTED value (e.g. "years since first observed in
    Compustat"), not a literal op/value comparison against the resolved
    column as-is -- the engine has no derivation-execution step, so applying
    it literally would silently run a different (and often broken, e.g.
    comparing a date column to an integer) condition than the paper states.
    Neither case plays a runtime role at all; `_unapplied_universe_filters`
    below records both instead of silently dropping them."""
    return [f for f in paper.universe.filters if not f.accepted_unapplied and f.derivation is None]


def _unapplied_universe_filters(paper) -> list[dict[str, Any]]:
    """Recorded, never-resolved entries for every filter NOT applied at
    runtime -- either explicitly `accepted_unapplied` by a human, or
    automatically skipped because it has a non-null `derivation` (see
    `_applied_universe_filters`). Deliberately does NOT call
    `_resolved_column` (an unapplied filter's concept may have no
    `concept_mapping` entry at all, e.g. no registered data source can
    supply it yet). This is what makes the deviation auditable rather than a
    silent drop: every entry keeps the concept_id/op/value the paper
    actually stated plus a reason (the human's own `unapplied_reason` when
    explicitly marked, else a fixed note for the derivation case).
    """
    return [
        {
            "concept_id": f.concept_id,
            "op": ev(f.op),
            "value": f.value,
            "reason": f.unapplied_reason if f.accepted_unapplied else "derivation not executable by the engine",
        }
        for f in paper.universe.filters
        if f.accepted_unapplied or f.derivation is not None
    ]


def _universe_filter_join_sources(paper, resolution) -> dict[str, list[str]]:
    """`{source: [columns]}` for every APPLIED universe filter whose
    resolved column is a REAL registered physical column (see
    `catalog.DATA_CATALOG`) but not one the returns panel supplies natively
    (`RETURNS_PANEL_NATIVE_COLUMNS`) -- e.g. a Compustat-only backfill-bias
    screen. The generated script joins these columns onto the returns panel
    point-in-time (via `assemble_signal_master_table_from_sources`, the SAME
    mechanism `compute_signal`'s own input already uses) BEFORE
    `filter_universe` runs, so the filter sees them as ordinary panel
    columns. A column that ISN'T registered in the catalog at all is left
    OUT here -- there's no way to load it -- and stays flagged by
    `ResolvedMethodSpec.unsupported_universe_filters()` instead. Deduped per
    source, order-stable.
    """
    out: dict[str, list[str]] = {}
    for f in _applied_universe_filters(paper):
        mapping = resolution.concept_mapping.get(f.concept_id)
        if mapping is None or mapping.column in RETURNS_PANEL_NATIVE_COLUMNS:
            continue
        registered_columns = catalog.DATA_CATALOG.get(mapping.source, {}).get("physical_columns", set())
        if mapping.column not in registered_columns:
            continue
        cols = out.setdefault(mapping.source, [])
        if mapping.column not in cols:
            cols.append(mapping.column)
    return out


def _resolve_legs(paper, sort_id: str, n_groups: int) -> tuple[list[int], list[int]]:
    """Convert `PortfolioLeg.selector` (0-based group index; group 0 = lowest
    bucket, per the extraction prompt's convention) into 1-based engine
    bucket numbers (the engine labels buckets `1..n`), split by leg side.
    """
    long_buckets: list[int] = []
    short_buckets: list[int] = []
    for leg in paper.portfolio.legs:
        if sort_id not in leg.selector:
            continue
        bucket = int(leg.selector[sort_id]) + 1
        (long_buckets if leg.side == "long" else short_buckets).append(bucket)
    return long_buckets, short_buckets


def _build_config_from_resolved(resolved: ResolvedMethodSpec, overrides: dict | None) -> dict:
    """`build_config`'s `ResolvedMethodSpec` branch -- see that function's
    docstring. Every engine-menu field (weighting/return_combination/
    breakpoint_source/missing_action/group_type/sort mode/rebalance_
    frequency/lag_unit/sort-dimension count) is auto-clamped to a documented
    default when the paper's value is off-menu -- never blocks `is_ready`,
    always recorded in `defaults_applied` (see docs/resolve-diagnostics-gaps.md
    problem 2).
    """
    paper = resolved.paper
    resolution = resolved.resolution

    defaults_applied: list[dict[str, Any]] = []

    def _track_clamp(config_key: str, val: Any, allowed: set[str], default: str) -> str:
        resolved_val, defaulted = _clamp_with_provenance(val, allowed, default)
        if defaulted:
            defaults_applied.append({
                "config_key": config_key,
                "value": resolved_val,
                "reason": "MethodSpec field unspecified or off-menu; engine default applied",
            })
        return resolved_val

    def _track_or(config_key: str, val: Any, default: Any) -> Any:
        if val is None:
            defaults_applied.append({
                "config_key": config_key,
                "value": default,
                "reason": "MethodSpec field unspecified; engine default applied",
            })
            return default
        return val

    def _track_sort_mode(config_key: str, sourced_mode) -> str:
        """`within_group` is a known, unimplemented engine capability (see
        `SortMode` docstring) -- passed through AS-IS (never silently
        clamped to `sequential`); the engine itself fails loud on it. Only a
        genuine `other` classification is clamped to the `independent`
        default here.
        """
        mode_str = ev(sourced_mode.value)
        if mode_str == "other":
            defaults_applied.append({
                "config_key": config_key,
                "value": "independent",
                "reason": (
                    "paper's sort-dimension relationship isn't classifiable as "
                    "independent/sequential/within_group; defaulted to independent"
                ),
            })
            return "independent"
        return mode_str

    def _track_group_type(config_key: str, sourced_group_type) -> None:
        """The engine only ever executes quantile grouping (there is no
        separate `group_type` config key) -- this only records the
        deviation for non-quantile values, it doesn't change execution
        (already quantile-only regardless of what's recorded)."""
        group_type_str = ev(sourced_group_type.value)
        if group_type_str != "quantile":
            defaults_applied.append({
                "config_key": config_key,
                "value": "quantile",
                "reason": f"engine only implements quantile grouping (paper used {group_type_str!r})",
            })

    def _clamp_sort_dims(sorts: list) -> list:
        """Deterministically trims to `MAX_SUPPORTED_SORT_DIMENSIONS`: the
        `target` dimension is always kept (the paper's own signal); non-
        target dimensions are kept in ascending `order` (ties broken by
        `sort_id` -- `order` has no uniqueness constraint), dropping the
        rest. Recorded in `defaults_applied`, never blocks `is_ready`."""
        if len(sorts) <= MAX_SUPPORTED_SORT_DIMENSIONS:
            return sorts
        target = next(s for s in sorts if s.role == SortRole.TARGET)
        others = sorted(
            (s for s in sorts if s.role != SortRole.TARGET),
            key=lambda s: (s.order, s.sort_id),
        )
        kept = [target] + others[: MAX_SUPPORTED_SORT_DIMENSIONS - 1]
        kept_ids = {s.sort_id for s in kept}
        dropped_ids = [s.sort_id for s in sorts if s.sort_id not in kept_ids]
        defaults_applied.append({
            "config_key": "sort_dims",
            "value": [s.sort_id for s in kept],
            "reason": (
                f"engine supports at most {MAX_SUPPORTED_SORT_DIMENSIONS} sort dimensions; "
                f"dropped {dropped_ids} (kept target + lowest-order control dims)"
            ),
        })
        return sorted(kept, key=lambda s: s.order)

    sorts = _clamp_sort_dims(sorted(paper.portfolio.sorts, key=lambda s: s.order))
    target_sort = next((s for s in sorts if s.role.value == "target"), sorts[0])

    for i, s in enumerate(sorts):
        _track_group_type(f"sorts[{i}].group_type", s.group_type)

    lag_months, lag_unit_unsupported = _accounting_lag_months(paper.timing.data_availability)
    if lag_unit_unsupported:
        defaults_applied.append({
            "config_key": "accounting_lag_months",
            "value": 6,
            "reason": (
                f"paper specified lag_unit={paper.timing.data_availability.lag_unit.value!r} "
                f"(lag_value={paper.timing.data_availability.lag_value}), which this "
                "month-granularity config field can't represent -- defaulted to 6 months"
            ),
        })
        lag_months = 6
    else:
        lag_months = _track_or("accounting_lag_months", lag_months, 6)

    config: dict[str, Any] = {
        "breakpoint_source": _track_clamp(
            "breakpoint_source", target_sort.breakpoints.basis.value,
            STANDARD["breakpoint_source"], "nyse",
        ),
        "breakpoint_quantiles": target_sort.group_count or 10,
        "weighting_rule": _track_clamp(
            "weighting_rule", paper.portfolio.weighting.value, STANDARD["weighting"], "vw"
        ),
        "rebalance_frequency": _track_clamp(
            "rebalance_frequency",
            _REBALANCE_FREQUENCY_FROM_TIME_UNIT.get(paper.timing.rebalance_frequency.value),
            {"annual", "quarterly", "monthly"}, "monthly",
        ),
        "holding_period_months": _track_or(
            "holding_period_months", paper.timing.holding_period.value, 12
        ),
        "accounting_lag_months": lag_months,
        "signal_max_staleness_months": 11,
        "missing_action": _track_clamp(
            "missing_action",
            next(
                (mp.action.value for mp in paper.portfolio.missing_policies if mp.stage == MissingStage.SIGNAL),
                None,
            ),
            STANDARD["missing_action"], "drop",
        ),
        "formation_month": _track_or(
            "formation_month",
            paper.timing.formation_month.value if paper.timing.formation_month else None,
            6,
        ),
        "formation_month_explicit": bool(
            paper.timing.formation_month and paper.timing.formation_month.value is not None
        ),
        "sample_start_year": paper.sample.formation.start_year,
        "sample_end_year": paper.sample.formation.end_year,
        "publication_year": paper.paper.publication_year,
        "universe_filters": [
            {
                "field": (col := _resolved_column(resolution, f.concept_id)),
                "op": ev(f.op),
                "value": _translate_filter_value(col, f.value),
            }
            for f in _applied_universe_filters(paper)
        ],
        "unapplied_universe_filters": _unapplied_universe_filters(paper),
        "universe_filter_join_sources": _universe_filter_join_sources(paper, resolution),
        "apply_delisting_returns": True,
        "return_combination_type": _track_clamp(
            "return_combination_type", paper.portfolio.return_combination.value,
            STANDARD["return_combination"], "extreme_group_spread",
        ),
        "return_basis": "excess",
        "estimator": "portfolio_sort",
    }

    long_buckets, short_buckets = _resolve_legs(paper, target_sort.sort_id, config["breakpoint_quantiles"])
    n = config["breakpoint_quantiles"]
    config["long_leg"] = "low" if long_buckets and min(long_buckets) == 1 else "high"
    config["short_leg"] = "high" if config["long_leg"] == "low" else "low"
    if long_buckets:
        config["long_portfolios"] = long_buckets
    if short_buckets:
        config["short_portfolios"] = short_buckets

    if len(sorts) >= 2:
        # The `target` dimension is the paper's own signal -- it always
        # lands on the engine's literal "signal" column (set by
        # apply_signal_holding_period from compute_signal()'s output), never
        # a physical concept column. Only non-target (control/conditioning)
        # dimensions -- e.g. a size sort -- come straight from the returns
        # panel and need a real physical-column resolution.
        config["sort_dims"] = [
            {
                "column": "signal" if s.role == SortRole.TARGET else _resolved_column(resolution, s.concept_id),
                "quantiles": s.group_count or 2,
                "source": ev(s.breakpoints.basis.value),
                "mode": (mode_str := _track_sort_mode(f"sorts[{i}].mode", s.mode)),
                "independent": mode_str == "independent",
                "role": s.role.value,
            }
            for i, s in enumerate(sorts)
        ]

    from src.infra.data_layer import catalog

    returns_cfg = catalog.returns_universe_config(resolution.returns_source or None)
    if returns_cfg:
        config["returns_table"] = returns_cfg["returns_table"]
        config["returns_layout"] = returns_cfg["returns_layout"]

    substitutions = [
        {
            "field": sub.field_path,
            "paper_value": sub.paper_value,
            "engine_value": sub.substituted_value,
            "reason": sub.reason,
        }
        for sub in resolution.approved_substitutions
    ]
    if substitutions:
        config["substitutions"] = substitutions

    if defaults_applied:
        config["defaults_applied"] = defaults_applied

    if overrides:
        _validate_overrides(config, overrides)
        config.update(overrides)
    return config
