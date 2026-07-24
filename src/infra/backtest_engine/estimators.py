"""Estimator strategy layer (estimator-strategy redesign, Phase 1).

`BacktestExecutor.run_with_config()` runs a fixed *prep* chain (load data,
delisting, missing policy, universe filter, excess returns, merge_signal),
then hands the merged panel off to one **estimator** — the pluggable part
that decides how a signal turns into a return series + metrics. This module
is the estimator registry: each entry is a plain function of shape

    (merged: pd.DataFrame, config: dict, dispatch: DispatchFn,
     factors: pd.DataFrame | None, trace: list[str]) -> {"metrics": dict,
     "return_series": pd.DataFrame}

`dispatch` is `BacktestExecutor._dispatch` (bound, so it already has the
config context) — estimators call it exactly like `run_with_config` used to,
routing each step to the standard implementation or its deterministic
`_overlap`/`_multi` variant.

Two estimators are standard today:
  - `portfolio_sort` (default): the sort -> weight -> combine -> metrics
    chain used by the vast majority of factor-replication papers.
  - `fama_macbeth`: single-characteristic cross-sectional regression
    (steps.compute_fama_macbeth), selected via
    `config["estimator"] == "fama_macbeth"` (set by
    step3_codegen.registry.build_config() from
    `construction_type == "regression_weighted"`).

Adding a genuinely different estimator (e.g. a future `custom` estimator
that delegates entirely to an `estimator_hook`) means adding one function
here and registering it in `ESTIMATORS` — `run_with_config` itself doesn't
need to change.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

import pandas as pd

from src.infra.backtest_engine import steps

DispatchFn = Callable[..., Any]


class Estimator(Protocol):
    """Uniform contract every estimator satisfies: given the merged
    (signal-joined) panel and run config, produce metrics + a return series.
    """

    def __call__(
        self,
        merged: pd.DataFrame,
        config: dict[str, Any],
        dispatch: DispatchFn,
        factors: pd.DataFrame | None,
        trace: list[str],
    ) -> dict[str, Any]: ...


def run_portfolio_sort(
    merged: pd.DataFrame,
    config: dict[str, Any],
    dispatch: DispatchFn,
    factors: pd.DataFrame | None,
    trace: list[str],
) -> dict[str, Any]:
    """Standard characteristic-sort estimator: form portfolios -> per-portfolio
    returns -> long-short combination -> metrics. Every step is individually
    hookable via `dispatch` (a plugin's hook for any of these names still
    overrides the standard implementation)."""
    portfolios = dispatch("form_portfolios", merged, config=config)
    trace.append("form_portfolios")
    returns = dispatch("compute_returns", portfolios, config=config)
    trace.append("compute_returns")
    long_short = dispatch("compute_long_short", returns, config=config)
    trace.append("compute_long_short")

    metrics = steps.compute_metrics(long_short, config)
    trace.append("compute_metrics")
    if factors is not None:
        metrics.update(steps.compute_factor_alphas(long_short, factors, config))
        trace.append("compute_factor_alphas")

    return {"metrics": metrics, "return_series": long_short}


def run_fama_macbeth(
    merged: pd.DataFrame,
    config: dict[str, Any],
    dispatch: DispatchFn,
    factors: pd.DataFrame | None,
    trace: list[str],
) -> dict[str, Any]:
    """Single-characteristic Fama-MacBeth cross-sectional regression
    estimator. Not a variant of the portfolio-sort chain above — no
    breakpoints/portfolios/long-short combination are computed at all."""
    metrics = steps.compute_fama_macbeth(merged, config)
    trace.append("compute_fama_macbeth")
    return {"metrics": metrics, "return_series": pd.DataFrame()}


#: Registry of standard estimators, keyed by `config["estimator"]`.
#: Anything not in this dict falls back to `portfolio_sort` (the historical
#: default before this registry existed).
ESTIMATORS: dict[str, Estimator] = {
    "portfolio_sort": run_portfolio_sort,
    "fama_macbeth": run_fama_macbeth,
}


def get_estimator(name: str | None) -> Estimator:
    """Resolve `config.get("estimator")` to a registered estimator function,
    defaulting to `run_portfolio_sort` for None/unknown values."""
    return ESTIMATORS.get(name or "portfolio_sort", run_portfolio_sort)
