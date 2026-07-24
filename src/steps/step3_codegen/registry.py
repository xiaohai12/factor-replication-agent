"""Codegen decision layer: how an approved MethodSpec resolves into a run
config for the standardized backtest engine.

The engine is fully standardized: there is no LLM-generated hook code. Every
portfolio-construction choice is *selected* from a fixed menu of built-in
implementations (see ``STANDARD`` below). A MethodSpec value outside the menu
is deterministically clamped to the menu default (``build_config`` /
``_clamp``) rather than triggering code generation.

This module answers "how does a MethodSpec resolve into a run config" — not
"what does a backtest compute" (that's
`src/infra/backtest_engine/steps.py`).

Lives in `step3_codegen/` (not `src/infra/backtest_engine/`) because every
function here is only ever called at generation time — by
`script_generator.generate_backtest_script()` (`build_config`) — never by
`BacktestExecutor`'s own run-time dispatch (`run_with_config`/`_dispatch`),
which only consumes the already-resolved config dict `build_config` produced.
`BacktestExecutor._build_config()`/`_resolve_long_leg()`/
`_resolve_short_leg()`/`_normalize_leg()` remain as thin backward-compatible
delegates to this module (existing callers, including tests, use those
names) — the engine library depends on this decision layer for those
delegates, but this module never depends on the engine library.
"""

from __future__ import annotations

from typing import Any

from src.infra.models.method_spec import (
    BreakpointSource,
    MissingAction,
    MethodSpec,
    ReturnCombinationType,
    WeightingRule,
)


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
        # AVERAGE_LEG_SPREAD / FULL_PORTFOLIO_RETURN added Phase 4 (plan.md):
        # steps.compute_long_short now implements all four types. Note
        # average_leg_spread only *actually* averages multiple portfolios
        # per leg when config["long_portfolios"]/["short_portfolios"] are
        # explicitly given (free-text leg descriptions aren't auto-parsed);
        # without them it's numerically identical to extreme_group_spread.
        ReturnCombinationType.AVERAGE_LEG_SPREAD.value,
        ReturnCombinationType.FULL_PORTFOLIO_RETURN.value,
        ReturnCombinationType.UNSPECIFIED.value,
    },
}


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
    v = ev(val)
    if v == "unspecified" or v not in allowed:
        return default
    return v


def build_config(spec: MethodSpec, overrides: dict | None) -> dict:
    """Build run config entirely from resolved MethodSpec fields."""

    # ls_quantile > 1 means "N groups"; < 1 means it's a fraction (1/N groups)
    ls_q = spec.portfolio.sort.ls_quantile or 10.0
    n_quantiles = int(ls_q) if ls_q >= 1 else int(round(1.0 / ls_q))

    config = {
        "breakpoint_source":    _clamp(spec.breakpoint_source, STANDARD["breakpoint_source"], "full_sample"),
        "breakpoint_quantiles": n_quantiles,
        "weighting_rule":       _clamp(spec.weighting_rule, STANDARD["weighting"], "vw"),
        "rebalance_frequency":  ev(spec.rebalance_frequency),
        "holding_period_months": spec.holding_period_months or 12,
        "accounting_lag_months": spec.accounting_lag_months or 6,
        "missing_action":       _clamp(spec.missing_action, STANDARD["missing_action"], "drop"),
        "universe":             spec.universe_description,
        "formation_month":      spec.formation_month or 6,
        "long_leg":             resolve_long_leg(spec),
        "short_leg":            resolve_short_leg(spec),
        # Sample-period segmentation (plan.md CZ-import Phase A). Drives the
        # optional in-sample / post-sample / post-publication metric split in
        # steps.compute_metrics (mirrors CZ's sumportmonth insamp/between/
        # postpub). No-op there when all three are None.
        "sample_start_year":    spec.sample_start_year,
        "sample_end_year":      spec.sample_end_year,
        "publication_year":     spec.publication_year,
        # Deterministic ResearchDesign fields (plan.md Phase 2.5). Each is a
        # documented canonical default, overridable per run/ablation.
        "universe_filters": [
            {"field": f.field, "op": ev(f.op), "value": f.value}
            for f in spec.portfolio.universe_filters
        ],
        "apply_delisting_returns": True,
        # Return combination (plan.md Phase 4): how per-portfolio returns
        # combine into the reported series; see steps.compute_long_short.
        "return_combination_type": _clamp(
            spec.portfolio.return_combination.type,
            STANDARD["return_combination"],
            "extreme_group_spread",
        ),
        # Return basis / frequency (plan.md Phase 6). "excess" only actually
        # takes effect when factor data with an `rf` column is supplied to
        # BacktestExecutor.run(factors=...) -- see BacktestExecutor.apply_excess_returns.
        # return_frequency isn't consumed by the standard steps yet (which
        # are frequency-agnostic given a `yyyymm`-keyed panel); it documents
        # intent and is available for callers that load daily source data
        # via BacktestExecutor.load_daily_msf() ahead of time.
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

    if overrides:
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
