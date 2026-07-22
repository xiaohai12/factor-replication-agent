"""Unit tests for AdversarialSandbox (step4) — the hook contract check and the
compute_signal execution smoke test added alongside the existing static checks.

Design under test (see docs/decision-log.md):
  - Static hook check: every hook the MethodSpec required (PluginRecord.hooks)
    must be defined with a matching arity, else hooks_ok=False. This closes the
    gap where a missing/misnamed hook is silently ignored at run time.
  - Execution smoke: `validate()` is given the ONE complete standalone backtest
    script (built via `generate_backtest_script()`, the same function
    `Pipeline._build_script` calls) -- not a separate hand-rolled runner. The
    check imports that script (never running its guarded `main()`) and calls
    its `compute_signal` on a small in-memory data slice. It is LENIENT — only
    a raised exception fails it (executes_ok=False); an empty/degenerate
    result is inconclusive (warning, not failure); no `script_text` skips the
    check entirely (executes_ok stays True). Hooks are NOT executed here.

Uses in-memory DataFrames and generated scripts pointed at a fake data path
(never touched, since the execution check never calls `main()`) so this runs
without pyarrow.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.models.method_spec import MethodSpec, SignalSpec
from src.infra.models.plugin import PluginRecord
from src.steps.step3_codegen.script_generator import generate_backtest_script
from src.steps.step4_validator import AdversarialSandbox


def _spec() -> MethodSpec:
    return MethodSpec(factor_id="t", factor_name="Test", signal=SignalSpec())



def _plugin(code: str, hooks: dict | None = None) -> PluginRecord:
    return PluginRecord(
        plugin_id="t_v1",
        factor_id="t",
        code=code,
        code_hash="deadbeef",
        hooks=hooks or {},
    )


def _slice() -> pd.DataFrame:
    """Tiny in-memory panel keyed [permno, time_avail_m] with an `x` column the
    good plugin turns into `signal`."""
    rows = []
    for permno in (1, 2, 3):
        for m in range(1, 13):
            rows.append({"permno": permno, "time_avail_m": 200000 + m, "x": float(permno * m)})
    return pd.DataFrame(rows)


_GOOD_SIGNAL = """
import pandas as pd

def compute_signal(df):
    out = df[["permno", "time_avail_m", "x"]].copy()
    out["signal"] = out["x"] * 2.0
    return out.rename(columns={"time_avail_m": "yyyymm"})[["permno", "yyyymm", "signal"]]
"""

_RAISES_SIGNAL = """
import pandas as pd

def compute_signal(df):
    # references a column that isn't in the slice -> KeyError (a real bug)
    return df[["permno", "does_not_exist"]]
"""

_EMPTY_SIGNAL = """
import pandas as pd

def compute_signal(df):
    out = df[["permno", "time_avail_m"]].copy()
    out["signal"] = float("nan")  # all-NaN -> degenerate/empty result
    return out.rename(columns={"time_avail_m": "yyyymm"})[["permno", "yyyymm", "signal"]]
"""


def _script_for(plugin: PluginRecord) -> str:
    """Build the ONE complete standalone script for a plugin, the same way
    Pipeline._build_script does -- so the execution smoke test validates the
    real artifact, not a hand-rolled stand-in. `signal_input_mode="crsp_only"`
    and a nonexistent data_path are fine: the execution check only imports the
    script (never calling its guarded `main()`), so the data path is never
    touched.
    """
    return generate_backtest_script(
        _spec(), plugin.code, data_path="data/does_not_exist/msf.parquet",
        signal_input_mode="crsp_only",
    )


class TestStaticChecks:
    def test_good_plugin_no_hooks_passes_without_data(self):
        report = AdversarialSandbox().validate(_plugin(_GOOD_SIGNAL), _spec())
        assert report.passed
        assert report.hooks_ok
        assert report.executes_ok  # skipped (no data) -> stays True

    def test_missing_hook_function_fails_hooks_ok(self):
        # plugin.hooks declares a hook the code never defines
        plugin = _plugin(_GOOD_SIGNAL, hooks={"compute_breakpoints": "compute_breakpoints_hook"})
        report = AdversarialSandbox().validate(plugin, _spec())
        assert not report.hooks_ok
        assert not report.passed
        assert any("compute_breakpoints_hook" in e for e in report.errors)

    def test_wrong_arity_hook_fails_hooks_ok(self):
        # compute_breakpoints_hook contract is (df, config) -> 2 args; define 1
        code = _GOOD_SIGNAL + "\n\ndef compute_breakpoints_hook(df):\n    return df\n"
        plugin = _plugin(code, hooks={"compute_breakpoints": "compute_breakpoints_hook"})
        report = AdversarialSandbox().validate(plugin, _spec())
        assert not report.hooks_ok
        assert any("positional args" in e for e in report.errors)

    def test_correct_hook_passes_hooks_ok(self):
        code = _GOOD_SIGNAL + "\n\ndef compute_breakpoints_hook(df, config):\n    return df\n"
        plugin = _plugin(code, hooks={"compute_breakpoints": "compute_breakpoints_hook"})
        report = AdversarialSandbox().validate(plugin, _spec())
        assert report.hooks_ok


class TestExecutionSmoke:
    def test_good_signal_executes_on_slice(self):
        plugin = _plugin(_GOOD_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        assert report.executes_ok
        assert report.passed

    def test_raising_signal_fails_executes_ok(self):
        plugin = _plugin(_RAISES_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        assert not report.executes_ok
        assert not report.passed
        assert any("compute_signal raised" in e for e in report.errors)

    def test_empty_output_is_inconclusive_not_failure(self):
        plugin = _plugin(_EMPTY_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        assert report.executes_ok  # lenient: empty result != failure
        assert report.passed
        assert any("inconclusive" in w for w in report.warnings)

    def test_no_script_text_skips_execution_check(self):
        """Backward-compat: callers with no script artifact (e.g. app.py's
        inline static-validate button) still get executes_ok=True."""
        plugin = _plugin(_GOOD_SIGNAL)
        report = AdversarialSandbox().validate(plugin, _spec(), data=_slice())
        assert report.executes_ok
        assert report.passed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
