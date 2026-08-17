"""Backtest Runner — assembles step3's built script and executes it (Step 5).

`execute()` (literally `subprocess.run([sys.executable, script_path])`) is
the actual "Step 5" pipeline action. `build_script()` calls
`src.steps.step3_codegen.script_generator.generate_backtest_script` and is
conceptually part of step3's output (assembling the plugin's compute_signal +
the deterministic engine config into one complete standalone script) — it lives on this class
rather than in `step3_codegen/` only because it needs `DataLayer` snapshot
path resolution, which step3_codegen doesn't have access to. Neither method
has retry/repair logic of its own; that's orchestration owned by callers
(`Pipeline.run_from_method_spec` for the single-track path,
`MultiTrackController` for multi-track), the same way `AdversarialSandbox.validate()`
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from src.infra.data_layer import DataLayer
from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RunMetrics, RunRecord
from src.infra.provenance import collect_runtime_provenance
from src.infra.hashing import snapshot_manifest_hash
from src.steps.step3_codegen.registry import build_config
from src.steps.step3_codegen.script_generator import generate_backtest_script, pick_signal_input_mode
from src.steps.step7_replication_diff.bundle import build_evidence_bundle


# Bumped to 2 when comparison.json gained the deterministic evidence bundle
# (derived / config_diff / gap_decomposition / evidence_keys) that the step-8
# LLM diagnosis layer consumes. v1 files carried only paper_reported + tracks.
# Bumped to 3 when the bundle gained spec_quality / menu_deviations /
# bridge_comparison / publication_decay / robustness_summary -- the richer
# reason-layer evidence for step8's diagnosis redesign (docs/tools-plus-llm-plan.md).
COMPARISON_SCHEMA_VERSION = 3


def _spec_factor_id(spec: ResolvedMethodSpec) -> str:
    return spec.paper.factor_id


def _spec_paper_ref(spec: ResolvedMethodSpec) -> str:
    return spec.paper.paper.citation


def _spec_stable_hash(spec: ResolvedMethodSpec) -> str:
    return spec.paper.content_hash()


def _spec_paper_reported(spec: ResolvedMethodSpec) -> dict:
    """Flattens a `ResolvedMethodSpec`'s `ReportedResults` (primary + up to
    3 secondary typed metrics, D5) into the
    `{return_type, spreads, t_stats, main_spread, main_t_stat}` shape
    `write_comparison_summary`'s existing consumers
    (`step7_replication_diff.bundle.build_evidence_bundle`) expect."""
    rr = spec.paper.reported_results
    primary = next((m for m in rr.metrics if m.metric_id == rr.primary_metric_id), None)
    return {
        "return_type": primary.estimand.value if primary else "",
        "spreads": {m.metric_id: m.estimate for m in rr.metrics},
        "t_stats": {m.metric_id: m.statistic.value for m in rr.metrics if m.statistic},
        "main_spread": primary.estimate if primary else None,
        "main_t_stat": primary.statistic.value if primary and primary.statistic else None,
    }


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
        spec: ResolvedMethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
        track_name: str | None = None,
        precomputed_signal_path: str | None = None,
    ) -> dict:
        """Assemble the ONE complete standalone backtest script — no execution.

        This is the single place the script is generated (see
        `src/steps/step3_codegen/script_generator.py`): callers validate this
        exact text (Step4) before ever calling `execute()` on it (Step5), so
        what's validated and what's executed are always the same bytes.

        Data is NOT auto-generated here: the registered snapshot's
        storage_path must already contain crsp_msf.parquet (and, in
        'compustat' mode, comp_funda.parquet + ccm_lnkhist.parquet).

        `track_name` (e.g. "original_method", "standardized_hxz",
        "ablation_breakpoint") disambiguates the output filenames when the
        SAME factor_id runs multiple tracks/configs -- without it, every
        track/config for one factor would write to the identical
        `{factor_id}.csv`/`{factor_id}_backtest.py` path and silently
        overwrite the previous track's on-disk artifact (the in-memory
        `RunRecord` per track was always correct; only the persisted files
        collided). Omitting it preserves the original single-track filename
        for backward compatibility. See docs/decision-log.md for the gap
        this closes.

        `precomputed_signal_path`, when given, is threaded straight through
        to `generate_backtest_script` -- the generated script skips
        `compute_signal()` and loads this parquet directly (a C&Z bridge
        track; see `src.infra.reference.cz_bridge`).

        Returns a dict: script_text, script_path, output_csv, config.
        """
        snapshot = self.data_layer.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            raise RuntimeError(f"Snapshot '{snapshot_id}' not registered on this DataLayer")
        storage_path = Path(snapshot.storage_path)

        factor_id = spec.paper.factor_id

        signal_input_mode = pick_signal_input_mode(spec)

        scripts_dir = self.scripts_path
        scripts_dir.mkdir(parents=True, exist_ok=True)
        # Every track/config for one factor writes its CSV/metrics into its
        # OWN results/<factor_id>/ folder (rather than flat files at
        # results/<factor_id>__<track>.*) so all of one paper's generated
        # result files live together. Within that folder, `track_name`
        # (falling back to "original_method" for a plain single-track call)
        # is enough to disambiguate -- no need to repeat factor_id in the
        # filename since it's already the folder name. The .py SCRIPT itself
        # stays in the flat `scripts_dir` (not nested -- only "results" was
        # asked to be per-paper), so it still needs factor_id in its own
        # filename to avoid colliding with another factor's same-named track.
        results_dir = scripts_dir / "results" / factor_id
        csv_stem = track_name or "original_method"
        output_csv = results_dir / f"{csv_stem}.csv"

        # FF factor + rf data for alpha metrics, if available. Checked
        # per-snapshot first (most reproducible — matches
        # the snapshot's own pull date), falling back to the shared
        # data/local/ff_factors.parquet fetched once via
        # scripts/fetch_ff_factors.py. Neither is required; alphas are simply
        # omitted from metrics when no factor data is found.
        ff_factors_path = None
        for candidate in (storage_path / "ff_factors.parquet", self.data_layer.data_path / "local" / "ff_factors.parquet"):
            if candidate.exists():
                ff_factors_path = str(candidate)
                break

        # Same idea for the Pastor-Stambaugh liquidity factor (2026-08-13) --
        # SEPARATE from ff_factors_path (a market-wide time series with no
        # permno, so it doesn't fit sources.py's per-stock registry).
        # `load_liquidity_factors(data_dir)` wants the OUTER dir (it appends
        # "local/liquidity_factors.csv" itself), so the candidate here is a
        # directory, not the CSV path.
        liquidity_factors_data_dir = None
        liquidity_factors_path = None
        for candidate_dir in (storage_path, self.data_layer.data_path):
            candidate_csv = candidate_dir / "local" / "liquidity_factors.csv"
            if candidate_csv.exists():
                liquidity_factors_data_dir = str(candidate_dir)
                liquidity_factors_path = str(candidate_csv)
                break

        # Resolve config ONCE, before script generation -- per
        # docs/multi-config-evidence-plan.md Phase 0.4, a run's identity
        # (`config_hash`/`execution_id` below) must be knowable
        # pre-execution, not reconstructed from execute()'s result
        # afterward. Passed into generate_backtest_script as
        # `resolved_config` so it isn't independently re-resolved a second
        # time (which would also emit any override-validation warning twice).
        config = build_config(spec, config_overrides)

        script_text = generate_backtest_script(
            spec,
            plugin.code,
            data_path=str(storage_path / "crsp_msf.parquet"),
            signal_input_mode=signal_input_mode,
            output_path=str(output_csv),
            config_overrides=config_overrides,
            ff_factors_path=ff_factors_path,
            liquidity_factors_data_dir=liquidity_factors_data_dir,
            signal_data_dir=str(storage_path),
            resolved_config=config,
            precomputed_signal_path=precomputed_signal_path,
        )
        script_stem = f"{factor_id}__{track_name}" if track_name else factor_id
        script_path = scripts_dir / f"{script_stem}_backtest.py"

        # `execution_id` folds in the plugin's code_hash so two tracks that
        # coincidentally resolve to the same config but run different plugin
        # code (e.g. after a track-local repair) are never confused for the
        # same run.
        config_hash = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        execution_id = (
            f"{factor_id}__{track_name or 'original_method'}"
            f"__{plugin.code_hash[:8]}__{config_hash[:8]}"
        )

        return {
            "script_text": script_text,
            "script_path": script_path,
            "output_csv": output_csv,
            "config": config,
            "config_hash": config_hash,
            "execution_id": execution_id,
            "ff_factors_path": ff_factors_path,
            "liquidity_factors_path": liquidity_factors_path,
            "data_snapshot_hash": snapshot_manifest_hash(storage_path),
        }

    def execute(
        self,
        built: dict,
        log: Optional[Callable[[str], None]] = None,
        data_path_override: Optional[str] = None,
        signal_data_dir_override: Optional[str] = None,
    ) -> dict:
        """Write the already-built script (see `build_script`) to disk and
        execute it via subprocess — literally "run the generated file".
        Results are read back from the CSV/metrics.json the script itself
        writes, rather than computed in-process, so the persisted script is
        always the actual source of the reported numbers.

        `log`, when given, receives each line of the subprocess's combined
        stdout/stderr AS IT RUNS (not just at the end) -- callers running
        this inside a background job (see backend/routers/sessions.py's
        step5 execute endpoint) wire this straight into the job's SSE log
        stream so the user sees real-time progress instead of the request
        appearing to hang for however long the real-data backtest takes.
        Always optional and additive: the full captured output is still
        returned in `stdout` regardless of whether `log` was given.

        `data_path_override`/`signal_data_dir_override`, when given, are set
        as the `BACKTEST_DATA_PATH`/`BACKTEST_SIGNAL_DATA_DIR` environment
        variables for the subprocess -- the generated script's own
        `DATA_PATH`/`SIGNAL_DATA_DIR` constants read these env vars first,
        falling back to whatever was baked in at generation time (see
        script_generator.py). This lets the EXACT SAME validated script
        (identical bytes, identical sha256) execute against a DIFFERENT data
        source than the one it was validated with (e.g. Step4 validates
        against a small real-data sample, Step5 executes against the full
        real data/local export) -- only the data source changes, never the
        compute_signal code itself.

        Raises RuntimeError (with combined stdout/stderr) on a nonzero exit code.
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
        if data_path_override:
            env["BACKTEST_DATA_PATH"] = data_path_override
        if signal_data_dir_override:
            env["BACKTEST_SIGNAL_DATA_DIR"] = signal_data_dir_override

        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        captured_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            captured_lines.append(line)
            if log:
                log(line.rstrip("\n"))
        proc.wait()
        combined_output = "".join(captured_lines)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Backtest script {script_path} failed (exit {proc.returncode}):\n"
                f"--- stdout/stderr ---\n{combined_output}"
            )

        metrics_path = output_csv.with_suffix(".metrics.json")
        metrics = json.loads(metrics_path.read_text())
        return_series = pd.read_csv(output_csv)

        # Written by the generated script itself right after compute_signal()
        # (see script_generator.py's `main()`) -- same naming convention here
        # so execute() can locate it without re-deriving path logic in two
        # places. Best-effort: an older already-built script (or a fake
        # runner in tests) may not have written one.
        signal_path = output_csv.with_name(output_csv.stem + ".signal.parquet")

        return {
            "metrics": metrics,
            "return_series": return_series,
            "config": built["config"],
            "config_hash": built.get("config_hash"),
            "execution_id": built.get("execution_id"),
            "ff_factors_path": built.get("ff_factors_path"),
            "liquidity_factors_path": built.get("liquidity_factors_path"),
            "data_snapshot_hash": built.get("data_snapshot_hash"),
            "script_path": str(script_path),
            "output_csv": str(output_csv),
            "signal_path": str(signal_path) if signal_path.exists() else None,
            "stdout": combined_output,
        }

    def write_comparison_summary(
        self,
        spec: ResolvedMethodSpec,
        tracks: dict[str, dict],
        snapshot_id: str | None = None,
        diff_result=None,
        batch_info: dict | None = None,
    ) -> Path:
        """Write one `comparison.json` under `results/<factor_id>/` combining
        every track's RESOLVED CONFIG + metrics with the paper's OWN reported
        results (`spec.reported_results`), so a human -- or an LLM handed
        just this one file -- can read model-vs-paper and track-vs-track
        together, including WHY two tracks' numbers differ (their configs),
        without opening each track's separate `<track>.metrics.json` /
        generated script.

        `tracks` is `{track_name: {"config": {...}, "metrics": {...}}}` --
        one entry per track already executed (e.g. `{"original_method":
        {"config": {...}, "metrics": {...}}, ...}`), built by the caller
        (`MultiTrackController.run_experiment`) from each track's resolved
        `registry.build_config()` output and `RunRecord.metrics`.

        Schema v2 additionally embeds the DETERMINISTIC EVIDENCE BUNDLE
        (`src.steps.step7_replication_diff.bundle.build_evidence_bundle`):
        every track-vs-paper delta, the baseline-vs-track config diff tagged
        by pipeline stage, the optional OAT gap decomposition, and
        `evidence_keys` -- the flat dotted-key whitelist the step-8 LLM
        diagnosis layer is allowed to cite. All of it is pure arithmetic over
        numbers already computed here, so the file stays reproducible with
        the LLM switched off.

        This is purely a convenience aggregate written ALONGSIDE the
        per-track `<track>.csv`/`<track>.metrics.json` files build_script()/
        execute() already produce -- it never replaces them, since each
        per-track metrics.json is written by that track's own standalone
        script and is the authoritative source for that track's numbers.

        `batch_info`, when supplied (see `MultiTrackController.run_experiment`,
        docs/multi-config-evidence-plan.md Phase 0.6), is embedded verbatim
        under the `"batch"` key: `experiment_batch_id`, `frozen_plugin_hash`,
        and whether a track-local repair invalidated this batch's "every
        track ran identical code" guarantee.
        """
        results_dir = self.scripts_path / "results" / _spec_factor_id(spec)
        results_dir.mkdir(parents=True, exist_ok=True)

        paper_reported = _spec_paper_reported(spec)

        payload = {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "factor_id": _spec_factor_id(spec),
            "paper_ref": _spec_paper_ref(spec),
            "method_spec_hash": _spec_stable_hash(spec),
            "snapshot_id": snapshot_id,
            "paper_reported": paper_reported,
            "tracks": tracks,
            "batch": batch_info or {},
        }
        payload.update(
            build_evidence_bundle(paper_reported, tracks, diff_result, spec=spec, results_dir=results_dir)
        )
        path = results_dir / "comparison.json"
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    def make_run_record(
        self,
        spec: ResolvedMethodSpec,
        plugin: PluginRecord,
        track: str,
        result: dict,
    ) -> RunRecord:
        """Build a status="success" RunRecord from an `execute()` result.

        Prefers the `config_hash`/`execution_id` already computed
        pre-execution by `build_script` (threaded through via `execute()`'s
        result dict) over recomputing them here -- see Phase 0.4 in
        docs/multi-config-evidence-plan.md: a run's identity should be
        computed once, before execution, not reconstructed afterward. Falls
        back to recomputing `config_hash` (and the old `run_id` format,
        which omitted config_hash entirely) when `result` doesn't carry them,
        e.g. a caller-supplied fake runner in tests that returns a minimal
        `execute()` result.
        """
        metrics = result["metrics"]
        config_hash = result.get("config_hash") or hashlib.sha256(
            json.dumps(result["config"], sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        run_id = result.get("execution_id") or f"{_spec_factor_id(spec)}_{track}_{plugin.code_hash[:8]}"
        provenance = collect_runtime_provenance(result.get("ff_factors_path"), result.get("liquidity_factors_path"))
        return RunRecord(
            run_id=run_id,
            factor_id=_spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            method_spec_hash=_spec_stable_hash(spec),
            code_hash=plugin.code_hash,
            config_hash=config_hash,
            lifecycle_commit=(
                f"{provenance['git_commit']}-dirty"
                if provenance.get("git_dirty")
                else provenance["git_commit"]
            ),
            runtime_provenance=provenance,
            return_series_path=result.get("output_csv"),
            signal_series_path=result.get("signal_path"),
            data_snapshot_hash=result.get("data_snapshot_hash") or "",
            metrics=RunMetrics(
                mean_return=metrics.get("mean_monthly_return"),
                t_stat=metrics.get("t_stat"),
                n_months=metrics.get("n_months"),
                sharpe_ratio=metrics.get("sharpe_ratio"),
                alpha_capm=metrics.get("alpha_capm"),
                alpha_ff3=metrics.get("alpha_ff3"),
                alpha_ff5=metrics.get("alpha_ff5"),
                by_sample_period=metrics.get("by_sample_period"),
            ),
            status="success",
        )

    def make_failed_run_record(
        self,
        spec: ResolvedMethodSpec,
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
        run_id = (
            f"{_spec_factor_id(spec)}_{track}_{plugin.code_hash[:8]}_{config_hash[:8]}_failed"
            if config_hash
            else f"{_spec_factor_id(spec)}_{track}_{plugin.code_hash[:8]}_failed"
        )
        provenance = collect_runtime_provenance()
        return RunRecord(
            run_id=run_id,
            factor_id=_spec_factor_id(spec),
            plugin_id=plugin.plugin_id,
            track=track,
            method_spec_hash=_spec_stable_hash(spec),
            code_hash=plugin.code_hash,
            config_hash=config_hash,
            lifecycle_commit=(
                f"{provenance['git_commit']}-dirty"
                if provenance.get("git_dirty")
                else provenance["git_commit"]
            ),
            runtime_provenance=provenance,
            metrics=RunMetrics(),
            status="failed",
            logs=[log[:2000]],
        )
