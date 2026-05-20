"""Dual-Track + Factorial Controller - Run experiments across implementation variants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.engine import BacktestEngine
from src.models.method_spec import MethodSpec
from src.models.plugin import PluginRecord
from src.models.run_record import RunRecord


# Standard HXZ-style settings for the standardized track
HXZ_STANDARD_CONFIG = {
    "breakpoint_rule": "nyse",
    "weighting_rule": "vw",
    "n_quantiles": 10,
    "rebalance_frequency": "monthly",
    "holding_period_months": 1,
    "accounting_lag_months": 6,
    "missing_policy": "drop",
    "universe_filters": ["exchcd_in_123", "shrcd_in_10_11"],
}


@dataclass
class ExperimentPlan:
    """Defines which tracks and ablations to run for a factor."""

    factor_id: str
    run_original: bool = True
    run_standardized: bool = True
    ablation_switches: list[str] = field(default_factory=list)
    factorial_switches: list[str] = field(default_factory=list)


class DualTrackController:
    """Controls multi-track experiments for implementation-gap analysis.

    Tracks:
    - original_method: Faithful to paper/C&Z/OSAP settings
    - standardized_hxz: Uniform HXZ-style standardized settings
    - ablation_*: Change one implementation choice at a time
    - factorial_*: Full-factorial combinations
    """

    def __init__(self, engine: BacktestEngine):
        self.engine = engine

    def run_experiment(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        plan: ExperimentPlan,
    ) -> list[RunRecord]:
        """Run all planned tracks for a factor."""
        runs: list[RunRecord] = []

        if plan.run_original:
            runs.append(self._run_track(plugin, spec, "original_method", {}))

        if plan.run_standardized:
            runs.append(
                self._run_track(plugin, spec, "standardized_hxz", HXZ_STANDARD_CONFIG)
            )

        for switch in plan.ablation_switches:
            override = self._get_ablation_override(switch, spec)
            runs.append(
                self._run_track(plugin, spec, f"ablation_{switch}", override)
            )

        return runs

    def _run_track(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        track_name: str,
        config_overrides: dict[str, Any],
    ) -> RunRecord:
        """Execute a single track."""
        # TODO: Execute plugin to get signal, then run engine
        raise NotImplementedError

    def _get_ablation_override(self, switch: str, spec: MethodSpec) -> dict[str, Any]:
        """Get config override for a single ablation switch."""
        # Flip one setting from original to standardized (or vice versa)
        ablation_map = {
            "breakpoint": {"breakpoint_rule": HXZ_STANDARD_CONFIG["breakpoint_rule"]},
            "weighting": {"weighting_rule": HXZ_STANDARD_CONFIG["weighting_rule"]},
            "lag": {"accounting_lag_months": HXZ_STANDARD_CONFIG["accounting_lag_months"]},
            "missing": {"missing_policy": HXZ_STANDARD_CONFIG["missing_policy"]},
            "rebalance": {"rebalance_frequency": HXZ_STANDARD_CONFIG["rebalance_frequency"]},
        }
        return ablation_map.get(switch, {})
