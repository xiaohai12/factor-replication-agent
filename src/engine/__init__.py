"""Controlled Backtesting Lifecycle Engine - Fixed empirical pipeline."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models.method_spec import MethodSpec


class BacktestEngine:
    """Controlled backtesting lifecycle engine.

    Executes the fixed empirical pipeline:
    1. Load approved data snapshots
    2. CRSP / Compustat / CCM linking
    3. Apply approved lag rules
    4. Apply missing-value policy
    5. Universe filtering
    6. Breakpoint computation
    7. Portfolio assignment
    8. Return computation (EW/VW/capped VW)
    9. Long-short return construction
    10. Metrics computation
    11. Evidence logging

    This code is FROZEN during formal experiments.
    Parameters are controlled by approved MethodSpec / implementation config.
    """

    def __init__(self, data_path: str | None = None):
        self.data_path = data_path

    def run(
        self,
        signal: pd.DataFrame,
        spec: MethodSpec,
        config_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute controlled backtest lifecycle on a signal.

        Args:
            signal: DataFrame with columns [permno, date, signal]
            spec: Approved MethodSpec controlling parameters
            config_overrides: Optional overrides for ablation experiments

        Returns:
            Dict with metrics, return series, and evidence artifacts
        """
        config = self._build_config(spec, config_overrides)

        # Pipeline steps
        data = self._load_data(config)
        data = self._apply_lag(data, config)
        data = self._apply_missing_policy(data, config)
        data = self._filter_universe(data, config)
        merged = self._merge_signal(data, signal)
        breakpoints = self._compute_breakpoints(merged, config)
        portfolios = self._assign_portfolios(merged, breakpoints, config)
        returns = self._compute_returns(portfolios, config)
        ls_returns = self._compute_long_short(returns, config)
        metrics = self._compute_metrics(ls_returns, config)

        return {
            "metrics": metrics,
            "return_series": ls_returns,
            "config": config,
        }

    def _build_config(self, spec: MethodSpec, overrides: dict | None) -> dict:
        """Build run config from MethodSpec + optional overrides."""
        config = {
            "breakpoint_rule": spec.breakpoint_rule.value,
            "weighting_rule": spec.weighting_rule.value,
            "n_quantiles": spec.n_quantiles,
            "rebalance_frequency": spec.rebalance_frequency.value,
            "holding_period_months": spec.holding_period_months,
            "accounting_lag_months": spec.accounting_lag_months,
            "missing_policy": spec.missing_policy.value,
            "universe_filters": spec.universe_filters,
            "formation_month": spec.formation_month,
            "skip_month": spec.skip_month,
        }
        if overrides:
            config.update(overrides)
        return config

    def _load_data(self, config: dict) -> pd.DataFrame:
        """Load CRSP/Compustat/CCM data snapshot."""
        # TODO: Implement data loading
        raise NotImplementedError

    def _apply_lag(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Apply accounting lag rules."""
        # TODO: Implement lag application
        raise NotImplementedError

    def _apply_missing_policy(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Apply missing-value policy."""
        # TODO: Implement missing policy
        raise NotImplementedError

    def _filter_universe(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Apply universe filters (exchange, share code, price, etc)."""
        # TODO: Implement universe filtering
        raise NotImplementedError

    def _merge_signal(self, data: pd.DataFrame, signal: pd.DataFrame) -> pd.DataFrame:
        """Merge signal with market data."""
        # TODO: Implement merge
        raise NotImplementedError

    def _compute_breakpoints(self, data: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Compute portfolio breakpoints (NYSE or full-sample)."""
        # TODO: Implement breakpoint computation
        raise NotImplementedError

    def _assign_portfolios(
        self, data: pd.DataFrame, breakpoints: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        """Assign stocks to portfolios based on breakpoints."""
        # TODO: Implement portfolio assignment
        raise NotImplementedError

    def _compute_returns(self, portfolios: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Compute portfolio returns (EW/VW/capped VW)."""
        # TODO: Implement return computation
        raise NotImplementedError

    def _compute_long_short(self, returns: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Compute long-short portfolio returns."""
        # TODO: Implement long-short construction
        raise NotImplementedError

    def _compute_metrics(self, returns: pd.DataFrame, config: dict) -> dict:
        """Compute t-stat, alpha, coverage, microcap share, etc."""
        # TODO: Implement metrics computation
        raise NotImplementedError
