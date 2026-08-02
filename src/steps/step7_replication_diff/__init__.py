"""Replication-Diff Layer - Analyze/decompose the replication gap.

Terminal reporting step (step 7): compares our replication against reference
(C&Z / paper) results and decomposes where the gap comes from. It is NOT a
feedback-loop trigger -- empirical correctness is gated upstream at the
human-in-the-loop Review Gate; this step only reports the residual gap for a
human to interpret (see docs/decision-log.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.infra.models.run_record import RunRecord


@dataclass
class ReplicationDiffResult:
    """Result of implementation-gap analysis."""

    factor_id: str
    original_tstat: float | None = None
    standardized_tstat: float | None = None
    total_gap: float | None = None

    # Per-switch contributions
    contributions: dict[str, float] = field(default_factory=dict)
    interaction_effects: dict[str, float] = field(default_factory=dict)

    # Diagnostics
    explained_fraction: float | None = None
    residual: float | None = None


class ReplicationDiff:
    """Basic terminal comparison for original/standardized/OAT runs.

    This is not yet a causal decomposition: OAT effects may interact and the
    pipeline does not persist or return the result. The complete pairwise,
    bridge, and identification-level design is documented in
    `docs/multi-config-evidence-plan.md`.
    """

    def diff_ablation(self, runs: list[RunRecord]) -> ReplicationDiffResult:
        """Decompose gap using one-at-a-time ablation results.

        Requires: original_method run + one ablation run per switch.
        """
        original = next((r for r in runs if r.track == "original_method"), None)
        standardized = next((r for r in runs if r.track == "standardized_hxz"), None)

        if not original or not standardized:
            raise ValueError("Need both original_method and standardized_hxz runs")

        result = ReplicationDiffResult(
            factor_id=original.factor_id,
            original_tstat=(
                original.metrics.t_stat if original.metrics else None
            ),
            standardized_tstat=(
                standardized.metrics.t_stat if standardized.metrics else None
            ),
        )

        if result.original_tstat is not None and result.standardized_tstat is not None:
            result.total_gap = result.original_tstat - result.standardized_tstat

        # Compute per-switch contributions from ablation runs
        ablation_runs = [r for r in runs if r.track.startswith("ablation_")]
        for run in ablation_runs:
            switch_name = run.track.replace("ablation_", "")
            if run.metrics and run.metrics.t_stat is not None and result.original_tstat is not None:
                result.contributions[switch_name] = (
                    result.original_tstat - run.metrics.t_stat
                )

        # Compute explained fraction
        if result.total_gap and result.total_gap != 0:
            total_explained = sum(result.contributions.values())
            result.explained_fraction = total_explained / result.total_gap
            result.residual = result.total_gap - total_explained

        return result

    def generate_report(self, result: ReplicationDiffResult) -> str:
        """Generate human-readable replication-diff report."""
        lines = [
            f"# Replication-Diff Report: {result.factor_id}",
            "",
            f"Original t-stat: {result.original_tstat}",
            f"Standardized t-stat: {result.standardized_tstat}",
            f"Total gap: {result.total_gap}",
            "",
            "## Per-Switch Contributions",
        ]
        for switch, contrib in sorted(
            result.contributions.items(), key=lambda x: abs(x[1]), reverse=True
        ):
            lines.append(f"- {switch}: {contrib:+.3f}")

        if result.explained_fraction is not None:
            lines.append("")
            lines.append(f"Explained fraction: {result.explained_fraction:.1%}")
            lines.append(f"Residual (interactions): {result.residual:+.3f}")

        return "\n".join(lines)
