"""Backtest Runner — assembles step3's built script and executes it (Step 5).

`execute()` (literally `subprocess.run([sys.executable, script_path])`) is
the actual "Step 5" pipeline action. `build_script()` calls
`src.steps.step3_codegen.script_generator.generate_backtest_script` and is
conceptually part of step3's output (assembling the plugin's compute_signal +
hooks into the one complete standalone script) — it lives on this class
rather than in `step3_codegen/` only because it needs `DataLayer` snapshot
path resolution, which step3_codegen doesn't have access to. Neither method
has retry/repair logic of its own; that's orchestration owned by callers
(`Pipeline.run_from_method_spec` for the single-track path,
`DualTrackController` for multi-track), the same way `AdversarialSandbox.validate()`
doesn't retry itself either — repair loops live one level up, in the code that
has access to `MetaCoder.repair_plugin()`.

Deliberately has NO dependency on `src.infra.backtest_engine` (the
`BacktestExecutor` engine class): that's only ever imported by the generated
script itself, inside its own subprocess, never by the code that builds or
launches that script.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.infra.data_layer import DataLayer
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step3_codegen.registry import build_config
from src.steps.step3_codegen.script_generator import generate_backtest_script, pick_signal_input_mode


class BacktestRunner:
    """Builds and executes the one standalone backtest script per run.

    Two-phase by design (`build_script` then `execute`) so a caller can
    validate the built script (Step4) before ever executing it — see
    `Pipeline._validate_with_repair`, which validates the exact text this
    class will later run.
    """

    def __init__(self, data_layer: DataLayer, scripts_path: str | Path):
        self.data_layer = data_layer
        self.scripts_path = Path(scripts_path)

    def build_script(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
    ) -> dict:
        """Assemble the ONE complete standalone backtest script — no execution.

        This is the single place the script is generated (see
        `src/steps/step3_codegen/script_generator.py`): callers validate this
        exact text (Step4) before ever calling `execute()` on it (Step5), so
        what's validated and what's executed are always the same bytes.

        Data is NOT auto-generated here: the registered snapshot's
        storage_path must already contain crsp_msf.parquet (and, in
        'compustat' mode, comp_funda.parquet + ccm_lnkhist.parquet).

        Returns a dict: script_text, script_path, output_csv, config.
        """
        snapshot = self.data_layer.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            raise RuntimeError(f"Snapshot '{snapshot_id}' not registered on this DataLayer")
        storage_path = Path(snapshot.storage_path)

        signal_input_mode = pick_signal_input_mode(spec)

        scripts_dir = self.scripts_path
        scripts_dir.mkdir(parents=True, exist_ok=True)
        results_dir = scripts_dir / "results"
        output_csv = results_dir / f"{spec.factor_id}.csv"

        # Phase 2 (plan.md): FF factor + rf data for alpha metrics, if
        # available. Checked per-snapshot first (most reproducible — matches
        # the snapshot's own pull date), falling back to the shared
        # data/local/ff_factors.parquet fetched once via
        # scripts/fetch_ff_factors.py. Neither is required; alphas are simply
        # omitted from metrics when no factor data is found.
        ff_factors_path = None
        for candidate in (storage_path / "ff_factors.parquet", self.data_layer.data_path / "local" / "ff_factors.parquet"):
            if candidate.exists():
                ff_factors_path = str(candidate)
                break

        script_text = generate_backtest_script(
            spec,
            plugin.code,
            data_path=str(storage_path / "crsp_msf.parquet"),
            signal_input_mode=signal_input_mode,
            output_path=str(output_csv),
            config_overrides=config_overrides,
            ff_factors_path=ff_factors_path,
            signal_data_dir=str(storage_path),
        )
        script_path = scripts_dir / f"{spec.factor_id}_backtest.py"
        config = build_config(spec, config_overrides)

        return {
            "script_text": script_text,
            "script_path": script_path,
            "output_csv": output_csv,
            "config": config,
        }

    def execute(self, built: dict) -> dict:
        """Write the already-built script (see `build_script`) to disk and
        execute it via subprocess — literally "run the generated file".
        Results are read back from the CSV/metrics.json the script itself
        writes, rather than computed in-process, so the persisted script is
        always the actual source of the reported numbers.

        Raises RuntimeError (with stdout/stderr) on a nonzero exit code.
        """
        script_path: Path = built["script_path"]
        output_csv: Path = built["output_csv"]
        script_path.write_text(built["script_text"])

        # The generated script does `from src...` imports (see
        # script_generator.py's module docstring — Phase 0 unification made
        # it a thin wrapper around BacktestExecutor instead of a fully
        # self-contained script). This repo's editable install only puts
        # `src/` itself on sys.path (its .pth file points at .../src, not the
        # repo root — see `pip show factor-replication-agent`), and Python
        # puts a *script's own directory* (not the cwd) on sys.path[0], so
        # `from src...` only resolves when the script happens to run with the
        # repo root on sys.path already. Since this script is written to an
        # arbitrary scripts_dir (e.g. a pytest tmp_path), explicitly prepend
        # the repo root to PYTHONPATH for the subprocess.
        repo_root = Path(__file__).resolve().parents[2]
        env = {**os.environ, "PYTHONPATH": f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}

        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Backtest script {script_path} failed (exit {proc.returncode}):\n"
                f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
            )

        metrics_path = output_csv.with_suffix(".metrics.json")
        metrics = json.loads(metrics_path.read_text())
        return_series = pd.read_csv(output_csv)

        return {
            "metrics": metrics,
            "return_series": return_series,
            "config": built["config"],
            "script_path": str(script_path),
            "stdout": proc.stdout,
        }

    def make_run_record(
        self,
        spec: MethodSpec,
        plugin: PluginRecord,
        track: str,
        result: dict,
    ) -> RunRecord:
        """Build a status="success" RunRecord from an `execute()` result."""
        metrics = result["metrics"]
        config_hash = hashlib.sha256(
            json.dumps(result["config"], sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return RunRecord(
            run_id=f"{spec.factor_id}_{track}_{plugin.code_hash[:8]}",
            factor_id=spec.factor_id,
            plugin_id=plugin.plugin_id,
            track=track,
            method_spec_hash=spec.stable_hash(),
            code_hash=plugin.code_hash,
            config_hash=config_hash,
            metrics=RunMetrics(
                mean_return=metrics.get("mean_monthly_return"),
                t_stat=metrics.get("t_stat"),
                n_months=metrics.get("n_months"),
                sharpe_ratio=metrics.get("sharpe_ratio"),
                alpha_capm=metrics.get("alpha_capm"),
                alpha_ff3=metrics.get("alpha_ff3"),
                alpha_ff5=metrics.get("alpha_ff5"),
            ),
            status="success",
        )

    def make_failed_run_record(
        self,
        spec: MethodSpec,
        plugin: PluginRecord,
        track: str,
        config_overrides: dict | None,
        log: str,
    ) -> RunRecord:
        """Build a status="failed" RunRecord for a backtest that raised at run
        time (after bounded repair was exhausted), so every attempt leaves an
        auditable trail instead of a bare exception."""
        try:
            config = build_config(spec, config_overrides)
            config_hash = hashlib.sha256(
                json.dumps(config, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
        except Exception:
            config_hash = ""
        return RunRecord(
            run_id=f"{spec.factor_id}_{track}_{plugin.code_hash[:8]}_failed",
            factor_id=spec.factor_id,
            plugin_id=plugin.plugin_id,
            track=track,
            method_spec_hash=spec.stable_hash(),
            code_hash=plugin.code_hash,
            config_hash=config_hash,
            metrics=RunMetrics(),
            status="failed",
            logs=[log[:2000]],
        )
