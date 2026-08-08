"""Adversarial Sandbox - Validate generated plugins before use."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.infra.models.paper_method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord, ValidationReport


# Patterns that indicate potential future information leakage
FORBIDDEN_PATTERNS = [
    "shift(-",   # backward shift (future data)
    ".future",
    "lead(",
]

# Seconds a compute_signal execution smoke test may run before it's treated as
# a hang (a hang is a real defect, not an inconclusive result -- see
# _check_executes). Deliberately generous: the slice is small, but the plugin
# code is imported/compiled fresh in a subprocess.
_EXECUTE_TIMEOUT_SECONDS = 60


class AdversarialSandbox:
    """Validates generated signal plugins for correctness and safety.

    Layered, cheap -> expensive; every layer gates codegen -> run and (via
    Pipeline's bounded repair loop) feeds only technical/execution errors back
    to MetaCoder -- never any C&Z ground-truth comparison, which stays a
    post-hoc, never-fed-back evaluation (see docs/decision-log.md).

    Checks:
    - Syntax validity (the compute_signal plugin)
    - Forbidden pattern scan (future functions)
    - Schema/contract: compute_signal exists
    - Execution smoke test: the ONE complete standalone script Pipeline built
      (`_build_script`) is imported (not run as `__main__` -- its `main()` is
      guarded, so no full-data load or engine run is triggered) in a
      subprocess, and its `compute_signal` is called on a small real-data
      slice, confirming it doesn't raise (lenient -- an empty/degenerate
      result on a thin slice is inconclusive, not a failure; only a raised
      exception fails it). This validates the EXACT artifact Step5 will later
      execute -- no separate hand-rolled "exec the plugin code" runner. A
      Step-5 run failure is the guaranteed safety net that feeds any remaining
      full-data bugs back to repair.
    """

    def validate(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        script_text: str | None = None,
        data=None,
    ) -> ValidationReport:
        """Run full validation suite on a plugin.

        Args:
            plugin:      the generated plugin (the compute_signal function).
            spec:        the resolved MethodSpec the plugin was generated from
                         (accepted for API/provenance parity with `MetaCoder.
                         generate_plugin`/`script_generator.
                         generate_backtest_script` -- every check below reads
                         only `plugin`/`script_text`/`data`, so `spec` itself
                         is never inspected here).
            script_text: the ONE complete standalone backtest script built from
                         this exact plugin (see `Pipeline._build_script`) --
                         the same text Step5 will execute. When None, the
                         execution check is skipped (executes_ok stays True) so
                         static-only callers (e.g. app.py's inline validate
                         button, which has no snapshot to build a script from)
                         still pass.
            data:        optional small real-data slice (a pandas DataFrame
                         keyed [permno, time_avail_m, ...]) for the
                         compute_signal execution smoke test. Required
                         alongside `script_text` for the execution check to run.
        """
        report = ValidationReport()

        report.syntax_ok = self._check_syntax(plugin, report)
        if report.syntax_ok:
            report.schema_ok = self._check_schema(plugin, report)
            report.no_future_leak = self._check_no_future_leak(plugin, report)
            report.reproducible = self._check_reproducibility(plugin, report)
            report.executes_ok = self._check_executes(script_text, data, report)

        report.passed = all([
            report.syntax_ok,
            report.schema_ok,
            report.no_future_leak,
            report.reproducible,
            report.executes_ok,
        ])
        return report

    def _check_syntax(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that code parses without syntax errors."""
        try:
            ast.parse(plugin.code)
            return True
        except SyntaxError as e:
            report.errors.append(f"SyntaxError: {e}")
            return False

    def _check_schema(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that plugin defines expected entry function with correct signature."""
        try:
            tree = ast.parse(plugin.code)
            func_names = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            if plugin.entry_function not in func_names:
                report.errors.append(
                    f"Entry function '{plugin.entry_function}' not found in code"
                )
                return False
            return True
        except Exception as e:
            report.errors.append(f"Schema check failed: {e}")
            return False

    def _check_no_future_leak(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Scan for patterns that might indicate future information usage."""
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in plugin.code:
                report.errors.append(f"Forbidden pattern detected: '{pattern}'")
                return False
        return True

    def _check_reproducibility(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check for non-deterministic operations."""
        # TODO: Run plugin twice with same input, check outputs match
        return True

    def _check_executes(
        self,
        script_text: str | None,
        data,
        report: ValidationReport,
    ) -> bool:
        """Execution smoke test: import the ALREADY-BUILT complete backtest
        script (see `Pipeline._build_script`) in an isolated subprocess (with a
        timeout) and call its `compute_signal` on a small real-data slice,
        confirming it doesn't raise.

        Importing the script (rather than running it) never triggers its
        `main()` -- the generated template guards that call with
        `if __name__ == "__main__":` -- so no full snapshot load or full
        BacktestExecutor run happens here; only the module-level
        `exec(compile(PLUGIN_CODE, ...))` line runs, which defines the
        formula-only `compute_signal` in the imported module's namespace. This
        reuses the single generated artifact directly
        instead of re-deriving a separate "how do I exec this plugin" runner.

        Lenient by design (see class docstring): only a raised exception or a
        hang (timeout) fails this check. A result that runs but is empty or
        degenerate is treated as INCONCLUSIVE -- recorded as a warning, not a
        failure -- because on a thin validation slice that usually reflects
        data coverage, not a code defect. The guaranteed net for anything this
        lenient check lets through is the real Step-5 run (which executes
        compute_signal AND every hook on full data and feeds failures back to
        repair).

        Skipped (returns True) when no `script_text` or no `data` slice is
        supplied.
        """
        if script_text is None or data is None:
            return True

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_pkl = tmp_path / "slice.pkl"
            target_py = tmp_path / "validation_target.py"
            driver_py = tmp_path / "driver.py"
            # Pickle (not parquet) so the subprocess needs no pyarrow/fastparquet.
            data.to_pickle(data_pkl)
            target_py.write_text(script_text)
            driver_py.write_text(_EXECUTE_DRIVER.format(
                target_py=repr(str(target_py)),
                data_pkl=repr(str(data_pkl)),
            ))

            repo_root = Path(__file__).resolve().parents[3]
            import os
            env = {**os.environ, "PYTHONPATH": f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
            try:
                proc = subprocess.run(
                    [sys.executable, str(driver_py)],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=_EXECUTE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                report.errors.append(
                    f"compute_signal execution timed out after {_EXECUTE_TIMEOUT_SECONDS}s (possible hang)"
                )
                return False

        result = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if result is None:
            # Driver produced no parseable verdict -- treat as a real failure
            # (e.g. the script failed to import at module-load time).
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            report.errors.append(f"compute_signal execution produced no result. stderr: {tail}")
            return False

        if result.get("error"):
            report.errors.append(f"compute_signal raised: {result['error']}")
            return False

        if result.get("empty"):
            report.warnings.append(
                "compute_signal execution smoke test inconclusive: empty/degenerate "
                "output on the validation slice (likely data coverage, not a code "
                "defect) -- deferring to the full Step-5 run"
            )
        return True


# Generic driver exec'd in a subprocess by _check_executes: imports whatever
# script it's pointed at (the exact artifact Step5 will run) and calls its
# `compute_signal`. Doesn't know anything about plugin internals -- it would
# work against any script with the same shape, so there's no separate
# "how do I run a plugin" logic duplicated here. Catches every error into a
# single JSON verdict line so the parent can distinguish a raised exception
# (real defect -> fail) from an empty result (inconclusive -> warn).
_EXECUTE_DRIVER = '''\
import importlib.util
import json
import sys
import traceback

import pandas as pd

TARGET_PY = {target_py}
DATA_PKL = {data_pkl}


def _main():
    spec = importlib.util.spec_from_file_location("validation_target", TARGET_PY)
    mod = importlib.util.module_from_spec(spec)
    try:
        # Runs the script's module-level code only -- NOT its `main()`, which
        # is guarded by `if __name__ == "__main__":` in the generated template.
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return {{"error": "script import failed: " + repr(e), "trace": traceback.format_exc()}}

    fn = getattr(mod, "compute_signal", None)
    if not callable(fn):
        return {{"error": "compute_signal not defined in generated script"}}

    df = pd.read_pickle(DATA_PKL)
    try:
        out = fn(df)
    except Exception as e:  # noqa: BLE001
        return {{"error": repr(e), "trace": traceback.format_exc()}}

    if not isinstance(out, pd.DataFrame):
        return {{"error": "compute_signal returned " + type(out).__name__ + ", expected DataFrame"}}

    missing = [c for c in ("permno", "yyyymm", "signal") if c not in out.columns]
    if missing:
        return {{"error": "compute_signal output missing columns: " + repr(missing)}}

    empty = len(out) == 0 or out["signal"].notna().sum() == 0
    return {{"error": None, "empty": bool(empty), "n_rows": int(len(out))}}


print(json.dumps(_main()))
'''

