"""Run a REAL experiment matrix (original_method + standardized_hxz +
ablation/factorial switches) for the AssetGrowth factor (Cooper, Gulen &
Schill 2008) against the actual `data/local` WRDS CSV exports -- not
synthetic data. Demonstrates the "config-sensitivity" analysis discussed in
docs/decision-log.md 2026-08-04: how much of a gap vs. the paper's/C&Z's
reported number could plausibly be explained by portfolio-construction
config alone, using only the agent's own signal (no C&Z bridge needed).

Usage:
    python scripts/run_real_asset_growth_experiment.py

Reuses the exact resolved MethodSpec + generated plugin fixtures the MVP/
bridge e2e tests use (tests/fixtures/method_specs/
cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json,
tests/fixtures/plugins/cooper_gulen_schill_2008_asset_growth.py) -- these
are the SAME artifacts already verified end-to-end against synthetic data,
now pointed at the real snapshot instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.infra.data_layer import SnapshotMetadata  # noqa: E402
from src.infra.models.method_spec import MethodSpec  # noqa: E402
from src.infra.models.plugin import PluginRecord  # noqa: E402
from src.pipeline import Pipeline  # noqa: E402
from src.steps.step6_dual_track_controller import ExperimentPlan  # noqa: E402

SPEC_PATH = REPO_ROOT / "tests" / "fixtures" / "method_specs" / "cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json"
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"
SNAPSHOT_ID = "real_wrds_local_v1"
FACTOR_ID = "cooper_gulen_schill_2008_asset_growth"


def main() -> int:
    pipeline = Pipeline(
        data_path=str(REPO_ROOT / "data"),
        evidence_path=str(REPO_ROOT / "runs" / "evidence"),
        scripts_path=str(REPO_ROOT / "runs" / "backtest_scripts"),
    )

    # storage_path is the PARENT of the raw-CSV "local" folder convention
    # (see src/infra/data_layer/sources.py) -- data/local/*.csv are the real
    # WRDS exports, so storage_path is the repo's own data/ directory.
    if pipeline.data_layer.snapshots.get_snapshot(SNAPSHOT_ID) is None:
        pipeline.data_layer.snapshots.register_snapshot(
            SnapshotMetadata(
                snapshot_id=SNAPSHOT_ID,
                pull_date="2026-08-04",
                crsp_end_date="2026-06-30",
                compustat_end_date="2025-12-31",
                storage_path=str(REPO_ROOT / "data"),
            )
        )

    spec = MethodSpec.model_validate(json.loads(SPEC_PATH.read_text(encoding="utf-8")))
    plugin = PluginRecord(
        plugin_id=f"{FACTOR_ID}_real_v1",
        factor_id=FACTOR_ID,
        code=PLUGIN_PATH.read_text(encoding="utf-8"),
        code_hash="real_fixture_v1",
        validation_status="passed",
    )

    plan = ExperimentPlan(
        factor_id=FACTOR_ID,
        run_original=True,
        run_standardized=True,
        ablation_switches=["breakpoint", "weighting", "lag", "rebalance"],
        factorial_switches=["weighting", "breakpoint"],
    )

    print(f"=== Running real experiment matrix for {FACTOR_ID} against data/local ===")
    runs = pipeline.controller.run_experiment(plugin, spec, plan, snapshot_id=SNAPSHOT_ID)

    print()
    print(f"{'track':35s} {'status':10s} {'mean_ret%':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for r in runs:
        m = r.metrics
        mean_pct = f"{m.mean_return * 100:.3f}" if m.mean_return is not None else "n/a"
        tstat = f"{m.t_stat:.2f}" if m.t_stat is not None else "n/a"
        nmo = str(m.n_months) if m.n_months is not None else "n/a"
        print(f"{r.track:35s} {r.status:10s} {mean_pct:>10s} {tstat:>8s} {nmo:>9s}")
        if r.status != "success":
            print(f"    logs: {r.logs}")

    print()
    print(f"batch_invalidated: {runs[0].batch_invalidated if runs else 'n/a'}")
    comparison_path = REPO_ROOT / "runs" / "backtest_scripts" / "results" / FACTOR_ID / "comparison.json"
    print(f"comparison.json: {comparison_path} (exists={comparison_path.exists()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
