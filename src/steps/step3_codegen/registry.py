"""Codegen decision layer: which steps are "standard" (built-in on
BacktestExecutor) vs. need an LLM-generated hook, and how a MethodSpec
resolves into a run config.

This module answers "what does the LLM need to generate for this MethodSpec"
(the controlled-codegen side of the system) — not "what does a backtest
compute" (that's `src/infra/backtest_engine/steps.py`) and not "how does a
plugin's hook get loaded at run time" (that's
`src/infra/backtest_engine/registry.py::load_hooks`).

Lives in `step3_codegen/` (not `src/infra/backtest_engine/`) because every
function here is only ever called at generation time — by
`MetaCoder.generate_plugin()` (`detect_hooks`) and
`script_generator.generate_backtest_script()` (`build_config`) — never by
`BacktestExecutor`'s own run-time dispatch (`run_with_config`/`_dispatch`),
which only consumes the already-resolved config dict `build_config` produced.
`BacktestExecutor._detect_hooks()`/`_build_config()`/`_resolve_long_leg()`/
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
    PortfolioConstructionType,
    ReturnCombinationType,
    WeightingRule,
)


# ---------------------------------------------------------------------------
# Standard set — values for which BacktestExecutor has a built-in implementation.
# Anything outside triggers a hook request to MetaCoder. Values are drawn
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
    "portfolio_construction": {
        PortfolioConstructionType.CHARACTERISTIC_SORT.value,
        # REGRESSION_WEIGHTED added Phase 7 (plan.md): routed to the
        # Fama-MacBeth estimator (steps.compute_fama_macbeth) entirely
        # instead of compute_returns -- see build_config()'s "estimator"
        # field and BacktestExecutor.run_with_config()'s branch.
        PortfolioConstructionType.REGRESSION_WEIGHTED.value,
        PortfolioConstructionType.UNSPECIFIED.value,
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
    # Sort form (plan.md CZ-import Phase B; mirrors CZ Cat.Form). Only the two
    # forms with a canonical deterministic implementation are standard in
    # steps.compute_breakpoints/assign_portfolios:
    #   continuous -> quantile sort; discrete -> one portfolio per distinct
    #   signal value (categorical scores like governance index / MS / PS).
    # Anything else (e.g. CZ's "custom" pre-assigned portfolios, which don't
    # fit this pipeline's signal-plugin-computes-a-formula data model) falls
    # through to a hook via detect_hooks() rather than being special-cased.
    "cat_form": {"continuous", "discrete"},
}

# filter_universe used to have no STANDARD set and was unconditionally routed
# to an LLM hook (every paper's sample-membership rules were treated as
# non-standard by definition). Phase 2.5 (plan.md) replaced that with a
# deterministic FilterOp DSL applied against `portfolio.universe_filters` (see
# steps.apply_universe_filters) alongside the baseline shrcd/exchcd/siccd
# screen, so filter_universe is standard by default now. A plugin-supplied
# filter_universe_hook still overrides it when a paper's universe rule is
# genuinely inexpressible in the DSL.
FILTER_UNIVERSE_ALWAYS_HOOK_REASON = (
    "filter_universe is always LLM-generated from portfolio.universe_filters/universe"
)  # kept for any external references; no longer used by detect_hooks()


def ev(v: Any) -> str:
    """Return string value of an enum or plain string."""
    if hasattr(v, "value"):
        return v.value
    return str(v) if v is not None else "unspecified"


def detect_hooks(spec: MethodSpec) -> dict[str, str]:
    """Return {step_name: reason} for steps that need LLM-generated hooks.

    Compares resolved MethodSpec field values against STANDARD sets.
    Steps whose value falls outside STANDARD require a hook function.
    """
    hooks: dict[str, str] = {}

    bp = ev(spec.breakpoint_source)
    if bp not in STANDARD["breakpoint_source"]:
        hooks["compute_breakpoints"] = f"non-standard breakpoint_source={bp!r}"

    wt = ev(spec.weighting_rule)
    if wt not in STANDARD["weighting"]:
        hooks["compute_returns"] = f"non-standard weighting={wt!r}"

    ma = ev(spec.missing_action)
    if ma not in STANDARD["missing_action"]:
        hooks["apply_missing_policy"] = f"non-standard missing_action={ma!r}"

    portfolio_return = spec.reported_results.return_calculation.portfolio_return

    if spec.signal.timing.overlapping_portfolios:
        # Phase 5 (plan.md): overlapping-cohort holding is now standard
        # (steps.merge_signal_overlap + friends) -- no longer unconditionally
        # hooked. Not yet combined with a multi-dimensional sort in this v1
        # (BacktestExecutor._dispatch() only routes to one alternate path or
        # the other); that specific combination still needs a hook.
        if len(portfolio_return.sorts) > 1:
            hooks["merge_signal"] = (
                "overlapping_portfolios=true combined with a multi-dimensional "
                "sort isn't supported by the standard overlapping-cohort path yet"
            )

    # filter_universe is deterministic by default since Phase 2.5 (see
    # FILTER_UNIVERSE_ALWAYS_HOOK_REASON above) — no longer unconditionally
    # hooked. A plugin may still define filter_universe_hook to override it;
    # that's a plugin-authoring choice, not something detect_hooks() predicts.

    if len(portfolio_return.sorts) > 1:
        dims = [s.variable for s in portfolio_return.sorts if s.variable]
        # Phase 3 (plan.md): a characteristic x size double sort is now a
        # standard multi-dim sort (steps.compute_breakpoints_multi /
        # assign_portfolios_multi), not hooked. Anything resolve_sort_dims()
        # can't map (3+ dims, or 2 dims with neither/both being "size") still
        # falls back to a hook.
        if resolve_sort_dims(spec) is None:
            hooks["compute_breakpoints"] = f"multi-dimensional sort: {dims!r}"
            hooks["assign_portfolios"] = f"multi-dimensional sort: {dims!r}"

    ct = ev(portfolio_return.construction_type)
    if ct not in STANDARD["portfolio_construction"]:
        hooks["compute_returns"] = f"non-standard construction_type={ct!r}"

    rc = ev(portfolio_return.return_combination.type)
    if rc not in STANDARD["return_combination"]:
        hooks["compute_long_short"] = f"non-standard return_combination={rc!r}"

    # Sort form (plan.md CZ-import Phase B). continuous/discrete are standard;
    # any other cat_form (incl. CZ's "custom") needs a hook. discrete is only
    # implemented on the single-dim, non-overlapping sort path, so combining
    # it with an overlapping-cohort or multi-dimensional sort also needs a
    # hook (those alternate paths ignore cat_form).
    cf = (spec.cat_form or "continuous").lower()
    if cf not in STANDARD["cat_form"]:
        hooks["compute_breakpoints"] = f"non-standard cat_form={cf!r}"
        hooks["assign_portfolios"] = f"non-standard cat_form={cf!r}"
    elif cf == "discrete" and (
        spec.signal.timing.overlapping_portfolios or len(portfolio_return.sorts) > 1
    ):
        reason = (
            "cat_form='discrete' isn't supported by the overlapping-cohort / "
            "multi-dimensional sort paths yet"
        )
        hooks["compute_breakpoints"] = reason
        hooks["assign_portfolios"] = reason

    return hooks


def build_config(spec: MethodSpec, overrides: dict | None) -> dict:
    """Build run config entirely from resolved MethodSpec fields."""

    def effective(val: Any, default: str) -> str:
        v = ev(val)
        return v if v != "unspecified" else default

    # ls_quantile > 1 means "N groups"; < 1 means it's a fraction (1/N groups)
    ls_q = spec.portfolio.breakpoints.ls_quantile or 10.0
    n_quantiles = int(ls_q) if ls_q >= 1 else int(round(1.0 / ls_q))

    config = {
        "breakpoint_source":    effective(spec.breakpoint_source, "full_sample"),
        "breakpoint_quantiles": n_quantiles,
        "weighting_rule":       effective(spec.weighting_rule, "vw"),
        "rebalance_frequency":  ev(spec.rebalance_frequency),
        "holding_period_months": spec.holding_period_months or 12,
        "accounting_lag_months": spec.accounting_lag_months or 6,
        "missing_action":       effective(spec.missing_action, "drop"),
        "universe":             spec.universe_description,
        "formation_month":      spec.formation_month or 6,
        "skip_month":           spec.skip_month or 0,
        "long_leg":             resolve_long_leg(spec),
        "short_leg":            resolve_short_leg(spec),
        # Sort form (plan.md CZ-import Phase B; mirrors CZ Cat.Form): drives
        # steps.compute_breakpoints/assign_portfolios branching between
        # quantile (continuous), one-portfolio-per-value (discrete), and
        # signal-is-portfolio (custom).
        "cat_form":             (spec.cat_form or "continuous").lower(),
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
        "microcap_exclude": False,
        "neutralization": "none",
        # Multi-dimensional sort (plan.md Phase 3): [] unless the spec's
        # portfolio_return.sorts[] resolves to a standard characteristic x
        # size double sort (see resolve_sort_dims). >1 entries routes
        # compute_breakpoints/assign_portfolios/compute_returns/
        # compute_long_short to their _multi counterparts in _dispatch().
        "sort_dims": resolve_sort_dims(spec, default_quantiles=n_quantiles) or [],
        # Return combination (plan.md Phase 4): how per-portfolio returns
        # combine into the reported series; see steps.compute_long_short.
        "return_combination_type": effective(
            spec.reported_results.return_calculation.portfolio_return.return_combination.type,
            "extreme_group_spread",
        ),
        # Overlapping-cohort holding (plan.md Phase 5): standard when true
        # (steps.merge_signal_overlap + friends), unless combined with a
        # multi-dimensional sort (still hooked in that case, see
        # detect_hooks()).
        "overlapping": bool(spec.signal.timing.overlapping_portfolios),
        # Return basis / frequency (plan.md Phase 6). "excess" only actually
        # takes effect when factor data with an `rf` column is supplied to
        # BacktestExecutor.run(factors=...) -- see steps.apply_excess_returns.
        # return_frequency isn't consumed by the standard steps yet (which
        # are frequency-agnostic given a `yyyymm`-keyed panel); it documents
        # intent and is available for callers that load daily source data
        # via steps.load_daily_msf() ahead of time.
        "return_basis": "excess",
        "return_frequency": effective(spec.reported_results.return_horizon, "monthly"),
        # Estimator (plan.md Phase 7): "portfolio_sort" (default) runs the
        # standard sort/breakpoints/assign/returns/combine chain;
        # "fama_macbeth" (construction_type=regression_weighted) routes to
        # steps.compute_fama_macbeth entirely instead, right after
        # merge_signal -- see BacktestExecutor.run_with_config().
        "estimator": (
            "fama_macbeth"
            if ev(spec.reported_results.return_calculation.portfolio_return.construction_type)
            == "regression_weighted"
            else "portfolio_sort"
        ),
    }
    if overrides:
        config.update(overrides)
    return config


def _sort_variable_column(variable: str) -> str | None:
    """Map a SortLegSpec.variable name onto a column the standard engine's
    merged panel actually has. Only 'size'-like variables are recognized as a
    control dimension (-> `me`, already present from CRSP); anything else is
    assumed to be the paper's own characteristic (-> `signal`)."""
    v = (variable or "").lower()
    if "size" in v or "market_equity" in v or v == "me" or v == "mktcap":
        return "me"
    return None


def resolve_sort_dims(spec: MethodSpec, default_quantiles: int = 10) -> list[dict] | None:
    """Best-effort mapping of `portfolio_return.sorts[]` onto the standard
    engine's available columns (`signal`, `me`).

    Deliberately narrow v1 (plan.md Phase 3): returns a resolved dims list
    only for an exactly-2-dimensional sort where exactly one dimension is
    recognized as a size/market-equity control variable and the other is the
    paper's own characteristic. Anything else (3+ dims, 2 dims where neither
    or both are size-like) returns None so `detect_hooks()` still requests a
    hook — covers the single most common double-sort pattern in the
    literature (characteristic x size) without over-claiming generality for
    exotic multi-way sorts.
    """
    sorts = spec.reported_results.return_calculation.portfolio_return.sorts
    if len(sorts) != 2:
        return None

    resolved: list[dict] = []
    signal_dim_seen = False
    for leg in sorts:
        col = _sort_variable_column(leg.variable)
        if col is None:
            if signal_dim_seen:
                return None  # two unrecognized dims -- can't map both to "signal"
            col = "signal"
            signal_dim_seen = True
        n_groups = len(leg.groups) if leg.groups else 0
        quantiles = n_groups if n_groups >= 2 else (3 if col == "me" else default_quantiles)
        resolved.append({
            "variable": leg.variable,
            "column": col,
            "quantiles": quantiles,
            "source": "nyse",
            "independent": leg.independent_sort if leg.independent_sort is not None else True,
        })
    if not signal_dim_seen:
        return None  # both dims recognized as size-like -- degenerate
    return resolved


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
