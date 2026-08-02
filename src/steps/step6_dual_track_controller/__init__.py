"""Basic multi-track controller for original, standardized, and OAT runs.

The module/directory retain their historical name for API compatibility. A
validated declarative matrix, factorial expansion, batch-level plugin freeze,
and complete evidence persistence are future work documented in
`docs/multi-config-evidence-plan.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.steps.step5_backtest_runner import BacktestRunner
from src.steps.step3_codegen import MetaCoder
from src.steps.step4_validator import AdversarialSandbox
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunRecord
from src.infra.repair import RepairLoop


# Standardized-track config: force EVERY factor onto one uniform "house
# standard" so cross-factor results are comparable and any original-vs-standard
# gap is attributable to a known set of switches. This is NOT auto-derived from
# any dataset — it is a hand-curated convention. Provenance per field (cited so
# the "standard" is defensible in the paper — see docs/cz-reference.md §7):
#
#   breakpoint_source="nyse"      Hou, Xue & Zhang (2020, RFS) "Replicating
#   breakpoint_quantiles=deciles   Anomalies" — NYSE breakpoints + value weights
#   weighting_rule="vw"            + decile sorts are their core protocol for
#                                  damping microcap influence.
#   rebalance_frequency="monthly"  HXZ q-factor protocol (monthly VW rebalance).
#   holding_period_months=1        1-month holding (standard monthly-rebalanced).
#   universe (exchcd 1/2/3,        Common CRSP ordinary-common-stock universe
#     shrcd 10/11)                 (Fama-French / HXZ shared convention).
#   accounting_lag_months=6        Fama-French (1992) 6-month accounting lag,
#                                  NOT HXZ (HXZ match most-recent quarterly
#                                  earnings monthly). Kept here as the
#                                  conservative FF-style default; the "HXZ"
#                                  label is therefore approximate for THIS field.
#   missing_action="drop"          Drop firm-months with a missing signal input.
#
# Distinct from step2's SENSIBLE_DEFAULTS (a DIFFERENT concept): that fills a
# paper-SILENT field with its field-level convention to keep `original_method`
# faithful to the paper; this deliberately OVERRIDES the paper onto one house
# standard. They legitimately differ — e.g. rebalance is "annual" there (the
# usual default for an unspecified accounting-factor rebalance) vs "monthly"
# here (the HXZ standardized protocol). Do not merge them.
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
        # The one shared technical repair loop — same object type Pipeline uses,
        # so per-track execute failures get the identical bounded
        # repair -> rebuild -> re-validate behavior (see src/infra/repair.py).
        self.repair_loop = RepairLoop(runner, sandbox, meta_coder)

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
        """Build this track's script (from an already-validated plugin) and
        execute it via the shared `RepairLoop` (Step 5), which on an execution
        failure loops back to Step 3 (`MetaCoder.repair_plugin`) with a Step 4
        re-validate, bounded by `MAX_REPAIR_RETRIES` -- the same loop
        `Pipeline.run_from_method_spec` uses, applied per track. On exhaustion a
        status="failed" RunRecord is returned instead of raising. The repair
        history is attached to the RunRecord for audit.
        """
        built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides)
        outcome = self.repair_loop.execute_with_repair(
            plugin, built, spec, snapshot_id, config_overrides
        )
        if outcome.error is not None:
            record = self.runner.make_failed_run_record(
                spec, outcome.plugin, track_name, config_overrides, outcome.error
            )
        else:
            record = self.runner.make_run_record(
                spec, outcome.plugin, track_name, outcome.result
            )
        record.repair_history = outcome.history
        return record

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
