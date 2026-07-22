"""Dual-Track + Factorial Controller - Run experiments across implementation variants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step3_codegen import MetaCoder
from src.steps.step4_validator import AdversarialSandbox
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord


MAX_REPAIR_RETRIES = 3

# Standard HXZ-style settings for the standardized track
HXZ_STANDARD_CONFIG = {
    "breakpoint_source": "nyse",
    "breakpoint_quantiles": [10, 20, 30, 40, 50, 60, 70, 80, 90],
    "weighting_rule": "vw",
    "rebalance_frequency": "monthly",
    "holding_period_months": 1,
    "accounting_lag_months": 6,
    "missing_action": "drop",
    "universe": "NYSE + AMEX + NASDAQ, exchcd in (1,2,3), shrcd in (10,11)",
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

    Each track is Step 5 (build script -> execute) run once per config
    override, with a bounded repair loop on execution failure — the same
    Step-5-fails-loop-to-Step-3 pattern `Pipeline.run_from_method_spec` uses
    for the single-track path, so a factor with an ablation plan gets the same
    self-debugging safety net as a plain single-track run.
    """

    def __init__(
        self,
        runner: BacktestRunner,
        meta_coder: MetaCoder,
        sandbox: AdversarialSandbox,
    ):
        self.runner = runner
        self.meta_coder = meta_coder
        self.sandbox = sandbox

    def run_experiment(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        plan: ExperimentPlan,
        snapshot_id: str,
    ) -> list[RunRecord]:
        """Run all planned tracks for a factor.

        `plugin` is assumed already validated (Step4, done once before this
        is called — every track shares the same signal formula, only
        `config_overrides` differs per track, so re-running the compute_signal
        smoke test per track would be redundant). A per-track execution
        failure still gets its own bounded repair loop (see `_run_track`).
        """
        runs: list[RunRecord] = []

        if plan.run_original:
            runs.append(self._run_track(plugin, spec, snapshot_id, "original_method", {}))

        if plan.run_standardized:
            runs.append(
                self._run_track(plugin, spec, snapshot_id, "standardized_hxz", HXZ_STANDARD_CONFIG)
            )

        for switch in plan.ablation_switches:
            override = self._get_ablation_override(switch, spec)
            runs.append(
                self._run_track(plugin, spec, snapshot_id, f"ablation_{switch}", override)
            )

        return runs

    def _run_track(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        snapshot_id: str,
        track_name: str,
        config_overrides: dict[str, Any],
    ) -> RunRecord:
        """Build the standalone script for this track's config and execute it
        (Step 5), with a bounded repair loop on execution failure:
        `MetaCoder.repair_plugin()` (Step 3) on the run's stderr, a quick
        re-validate (Step 4, static only — the compute_signal execution smoke
        test already ran once before `run_experiment` was called; re-running
        it per repair attempt per track would be redundant), then rebuild and
        retry. Mirrors `Pipeline.run_from_method_spec`'s run-with-repair loop,
        applied per track instead of once.
        """
        result = None
        for attempt in range(MAX_REPAIR_RETRIES + 1):
            built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides)
            try:
                result = self.runner.execute(built)
                break
            except RuntimeError as run_error:
                can_repair = attempt < MAX_REPAIR_RETRIES and self.meta_coder.llm_client is not None
                if not can_repair:
                    return self.runner.make_failed_run_record(
                        spec, plugin, track_name, config_overrides, str(run_error)
                    )
                plugin = self.meta_coder.repair_plugin(plugin, [str(run_error)])
                report = self.sandbox.validate(plugin, spec)
                plugin.validation_report = report
                plugin.validation_status = "passed" if report.passed else "needs_repair"

        return self.runner.make_run_record(spec, plugin, track_name, result)

    def _get_ablation_override(self, switch: str, spec: MethodSpec) -> dict[str, Any]:
        """Get config override for a single ablation switch."""
        # Flip one setting from original to standardized (or vice versa)
        ablation_map = {
            "breakpoint": {"breakpoint_source": HXZ_STANDARD_CONFIG["breakpoint_source"]},
            "weighting": {"weighting_rule": HXZ_STANDARD_CONFIG["weighting_rule"]},
            "lag": {"accounting_lag_months": HXZ_STANDARD_CONFIG["accounting_lag_months"]},
            "missing": {"missing_action": HXZ_STANDARD_CONFIG["missing_action"]},
            "rebalance": {"rebalance_frequency": HXZ_STANDARD_CONFIG["rebalance_frequency"]},
            "universe": {"universe": HXZ_STANDARD_CONFIG["universe"]},
        }
        return ablation_map.get(switch, {})
