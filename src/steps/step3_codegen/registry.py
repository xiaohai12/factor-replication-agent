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

from src.infra.models.method_spec import (
    BreakpointSource,
    MissingAction,
    MethodSpec,
    ReturnCombinationType,
    WeightingRule,
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
# conditionally-present `returns_table`/`returns_layout`/`substitutions`,
# which are handled separately below). A caller override for any OTHER key
# is almost certainly a typo and is rejected rather than silently merged in.
KNOWN_CONFIG_KEYS: frozenset[str] = frozenset({
    "breakpoint_source", "breakpoint_quantiles", "weighting_rule",
    "rebalance_frequency", "holding_period_months", "accounting_lag_months",
    "signal_max_staleness_months", "missing_action", "universe",
    "formation_month", "formation_month_explicit", "long_leg", "short_leg",
    "sample_start_year", "sample_end_year", "publication_year",
    "universe_filters", "apply_delisting_returns", "return_combination_type",
    "return_basis", "return_frequency", "estimator",
    "returns_table", "returns_layout",
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
    "apply_delisting_returns": "universe",
    "returns_table": "universe",
    "returns_layout": "universe",
    # sample — the calendar window / metric split
    "sample_start_year": "sample",
    "sample_end_year": "sample",
    "publication_year": "sample",
    # estimator — how the return series is measured
    "return_basis": "estimator",
    "return_frequency": "estimator",
    "estimator": "estimator",
    "substitutions": "estimator",
}

UNCLASSIFIED_STAGE = "unclassified"


def stage_of(config_key: str) -> str:
    """Return the pipeline stage a resolved-config key belongs to."""
    return CONFIG_KEY_STAGE.get(config_key, UNCLASSIFIED_STAGE)


# ---------------------------------------------------------------------------
# Standard menu — the values for which the engine has a built-in
# implementation. A MethodSpec value outside its menu is clamped to the menu
# default by `build_config`/`_clamp` (never code-generated). Values are drawn
# directly from the MethodSpec enums (src/infra/models/method_spec.py) so the
# two stay in sync instead of duplicating strings.
# ---------------------------------------------------------------------------

STANDARD: dict[str, set[str]] = {
    "breakpoint_source": {
        BreakpointSource.FULL_SAMPLE.value,
        BreakpointSource.NYSE.value,
    },
    "weighting": {
        WeightingRule.VALUE_WEIGHTED.value,
        WeightingRule.EQUAL_WEIGHTED.value,
    },
    "missing_action": {
        MissingAction.DROP.value,
        MissingAction.UNSPECIFIED.value,
    },
    "return_combination": {
        ReturnCombinationType.EXTREME_GROUP_SPREAD.value,
        ReturnCombinationType.SINGLE_SIGNAL_PORTFOLIO_RETURN.value,
        # BacktestExecutor.combine_portfolio_returns implements all four
        # supported return-combination types. Note
        # average_leg_spread only *actually* averages multiple portfolios
        # per leg when config["long_portfolios"]/["short_portfolios"] are
        # explicitly given (free-text leg descriptions aren't auto-parsed);
        # without them it's numerically identical to extreme_group_spread.
        ReturnCombinationType.AVERAGE_LEG_SPREAD.value,
        ReturnCombinationType.FULL_PORTFOLIO_RETURN.value,
        ReturnCombinationType.UNSPECIFIED.value,
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


# Dotted MethodSpec.unsupported_fields[].field -> the resolved config key that
# build_config eventually clamps it to, so the substitution log (see
# build_config) can report "paper said X, engine ran Y" for exactly those
# fields the engine has a standard menu for.
_UNSUPPORTED_FIELD_TO_CONFIG_KEY: dict[str, str] = {
    "portfolio.weighting": "weighting_rule",
    "portfolio.sort.breakpoint_source": "breakpoint_source",
    "signal.missing_policy.action": "missing_action",
}


def _clamp(val: Any, allowed: set[str], default: str) -> str:
    """Resolve a MethodSpec field to a value the engine actually implements.

    ``unspecified`` (or None) and any value outside ``allowed`` both resolve to
    ``default`` — the engine is standardized, so an out-of-menu empirical
    choice is deterministically clamped to the built-in default rather than
    triggering code generation.
    """
    v = ev(val)
    if v == "unspecified" or v not in allowed:
        return default
    return v


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


def build_config(spec: MethodSpec, overrides: dict | None) -> dict:
    """Build run config entirely from resolved MethodSpec fields."""

    n_quantiles = _resolve_ls_quantile(spec.portfolio.sort.ls_quantile)

    config = {
        "breakpoint_source":    _clamp(spec.breakpoint_source, STANDARD["breakpoint_source"], "full_sample"),
        "breakpoint_quantiles": n_quantiles,
        "weighting_rule":       _clamp(spec.weighting_rule, STANDARD["weighting"], "vw"),
        "rebalance_frequency":  ev(spec.rebalance_frequency),
        "holding_period_months": spec.holding_period_months or 12,
        "accounting_lag_months": spec.accounting_lag_months or 6,
        "signal_max_staleness_months": 11,
        "missing_action":       _clamp(spec.missing_action, STANDARD["missing_action"], "drop"),
        "universe":             spec.universe_description,
        "formation_month":      spec.formation_month or 6,
        "formation_month_explicit": spec.formation_month is not None,
        "long_leg":             resolve_long_leg(spec),
        "short_leg":            resolve_short_leg(spec),
        # Optional in-sample / post-sample / post-publication metric split in
        # steps.compute_metrics (mirrors CZ's sumportmonth insamp/between/
        # postpub). No-op there when all three are None.
        "sample_start_year":    spec.sample_start_year,
        "sample_end_year":      spec.sample_end_year,
        "publication_year":     spec.publication_year,
        # Deterministic ResearchDesign fields. Each has a documented canonical
        # default and may be overridden only by an explicit run config.
        "universe_filters": [
            {"field": f.field, "op": ev(f.op), "value": f.value}
            for f in spec.portfolio.universe_filters
        ],
        "apply_delisting_returns": True,
        # How per-portfolio returns combine into the reported series; see
        # steps.compute_long_short.
        "return_combination_type": _clamp(
            spec.portfolio.return_combination.type,
            STANDARD["return_combination"],
            "extreme_group_spread",
        ),
        # Return basis / frequency. "excess" only actually
        # takes effect when factor data with an `rf` column is supplied to
        # BacktestExecutor.run(factors=...) -- see BacktestExecutor.apply_excess_returns.
        # return_frequency isn't consumed by the standard steps yet (which
        # are frequency-agnostic given a `yyyymm`-keyed panel); it documents
        # intent and is available for callers that load daily source data
        # via `data_layer.load_daily_msf_ciz()` ahead of time.
        "return_basis": "excess",
        "return_frequency": (spec.reported_results.return_horizon or "monthly"),
        # Estimator: "portfolio_sort" is the only standard estimator (see
        # estimators.py / docs/decision-log.md).
        "estimator": "portfolio_sort",
    }
    # Returns universe (portfolio-construction stock-return panel) comes from
    # the reviewed spec, never a hardcoded CRSP default. When the spec names a
    # registered returns universe we bake its returns_table/returns_layout into
    # the config; when unset, catalog.returns_universe_config defaults to the
    # us_equity_crsp monthly panel (the standardized default returns table).
    from src.infra.data_layer import catalog

    returns_cfg = catalog.returns_universe_config(getattr(spec, "returns_universe", None))
    if returns_cfg:
        config["returns_table"] = returns_cfg["returns_table"]
        config["returns_layout"] = returns_cfg["returns_layout"]

    # Substitution log: MethodSpec.unsupported_fields is the authoritative
    # record of "the paper stated this value explicitly, but it isn't an
    # engine menu member" (see UnsupportedField / _record_unsupported in
    # method_spec.py) -- distinct from a field the paper never addressed
    # (`unspecified`, not logged here). build_config is the single place that
    # decides what the engine actually ran instead, so pair each recorded
    # paper value with the resolved config value here. Never used to make an
    # empirical decision; purely descriptive provenance for review/reporting
    # (e.g. Phase C/D "vs paper" comparisons must carry this as a caveat).
    substitutions = [
        {
            "field": uf.field,
            "paper_value": uf.paper_value,
            "engine_value": config[config_key],
            "reason": uf.reason,
        }
        for uf in spec.unsupported_fields
        if (config_key := _UNSUPPORTED_FIELD_TO_CONFIG_KEY.get(uf.field)) is not None
    ]
    if substitutions:
        config["substitutions"] = substitutions

    if overrides:
        _validate_overrides(config, overrides)
        config.update(overrides)
    return config


def resolve_long_leg(spec: MethodSpec) -> str:
    ifd = spec.portfolio.implied_factor_direction
    raw = ifd.get("long_leg") if isinstance(ifd, dict) else None
    raw = raw or spec.portfolio.long_leg
    return normalize_leg(raw, default="low")


def resolve_short_leg(spec: MethodSpec) -> str:
    ifd = spec.portfolio.implied_factor_direction
    raw = ifd.get("short_leg") if isinstance(ifd, dict) else None
    raw = raw or spec.portfolio.short_leg
    return normalize_leg(raw, default="high")


def normalize_leg(value: Any, default: str) -> str:
    """Map a leg descriptor to the 'low'/'high' token used by compute_long_short.

    MethodSpec long_leg/short_leg fields are often free-text descriptions
    (e.g. "lowest asset-growth decile") rather than the bare 'low'/'high'
    tokens the engine expects, so match by substring instead of equality.
    """
    text = str(value or "").lower()
    if "low" in text:
        return "low"
    if "high" in text:
        return "high"
    return default
