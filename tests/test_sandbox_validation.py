"""Unit tests for AdversarialSandbox (step4) — the compute_signal execution
smoke test alongside the existing static checks.

Design under test (see docs/decision-log.md):
  - Execution smoke: `validate()` is given the ONE complete standalone backtest
    script (built via `generate_backtest_script()`, the same function
    `Pipeline._build_script` calls) -- not a separate hand-rolled runner. The
    check imports that script (never running its guarded `main()`) and calls
    its `compute_signal` on a small in-memory data slice. It is LENIENT — only
    a raised exception fails it (executes_ok=False); an empty/degenerate
    result is inconclusive (warning, not failure); no `script_text` skips the
    check entirely (executes_ok stays True).

Uses in-memory DataFrames and generated scripts pointed at a fake data path
(never touched, since the execution check never calls `main()`) so this runs
without pyarrow.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.infra.models.plugin import PluginRecord
from src.steps.step3_codegen.script_generator import generate_backtest_script
from src.steps.step4_validator import AdversarialSandbox
from tests._spec_test_helpers import minimal_resolved_spec


def _spec():
    return minimal_resolved_spec("t")



def _plugin(code: str) -> PluginRecord:
    return PluginRecord(
        plugin_id="t_v1",
        factor_id="t",
        code=code,
        code_hash="deadbeef",
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

_NON_NUMERIC_SIGNAL = """
import pandas as pd

def compute_signal(df):
    out = df[["permno", "time_avail_m"]].copy()
    out["signal"] = "not_a_number"  # wrong dtype, but doesn't raise
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
    def test_good_plugin_passes_without_data(self):
        report = AdversarialSandbox().validate(_plugin(_GOOD_SIGNAL), _spec())
        assert report.passed
        assert report.executes_ok  # skipped (no data) -> stays True


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


class TestTechnicalMetricsAndDtype:
    """docs/tools-plus-llm-plan.md §4.2: `technical_metrics` is a whitelisted,
    audit-only payload (nan_ratio/n_permno/n_months/missing_columns/dtype);
    a non-numeric `signal` dtype is a NEW deterministic hard failure that
    reuses the existing errors -> repair_plugin path, no new code path."""

    def test_good_signal_reports_technical_metrics(self):
        plugin = _plugin(_GOOD_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        assert report.technical_metrics["n_permno"] == 3
        assert report.technical_metrics["n_months"] == 12
        assert report.technical_metrics["missing_columns"] == []
        assert report.technical_metrics["nan_ratio"] == 0.0
        assert report.technical_metrics["dtype"].startswith("float")

    def test_non_numeric_signal_dtype_fails_deterministically(self):
        plugin = _plugin(_NON_NUMERIC_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        assert not report.executes_ok
        assert not report.passed
        assert any("non-numeric dtype" in e for e in report.errors)

    def test_technical_metrics_never_contains_performance_numbers(self):
        plugin = _plugin(_GOOD_SIGNAL)
        report = AdversarialSandbox().validate(
            plugin, _spec(), script_text=_script_for(plugin), data=_slice()
        )
        forbidden = {"mean_return", "t_stat", "alpha", "sharpe", "return"}
        assert forbidden.isdisjoint(report.technical_metrics.keys())


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        return _FakeCompletion(self._content)


class _FakeChatNamespace:
    def __init__(self, content: str):
        self.completions = _FakeCompletions(content)


class _FakeLLMClient:
    """Minimal stand-in for the `llm_client.chat.completions.create(...)`
    surface, returning a fixed JSON verdict string (mirrors the fakes used
    elsewhere for MetaCoder/ReplicationDiagnoser tests)."""

    def __init__(self, content: str):
        self.chat = _FakeChatNamespace(content)


class TestFaithfulnessCheck:
    """Opt-in LLM check: does compute_signal implement the SAME approved
    signal.formula (never whether the formula itself is the right economic
    choice -- see docs/decision-log.md and step4_validator's docstring)."""

    def test_skipped_without_llm_client(self):
        """Default AdversarialSandbox() never calls an LLM -- faithful_ok
        stays True and no extra warnings/errors appear."""
        plugin = _plugin(_GOOD_SIGNAL)
        report = AdversarialSandbox().validate(plugin, _spec())
        assert report.faithful_ok
        assert report.passed

    def test_faithful_verdict_passes(self):
        verdict = '{"faithful": true, "reason": "matches", "quoted_code": "", "quoted_spec": ""}'
        sandbox = AdversarialSandbox(llm_client=_FakeLLMClient(verdict))
        plugin = _plugin(_GOOD_SIGNAL)
        report = sandbox.validate(plugin, _spec())
        assert report.faithful_ok
        assert report.passed

    def test_verified_mismatch_fails_and_feeds_repair_loop(self):
        plugin = _plugin(_GOOD_SIGNAL)
        # Quotes must be verbatim substrings of the code/spec to be trusted.
        code_quote = 'out["signal"] = out["x"] * 2.0'
        spec_quote = "(x_t - x_t-1) / x_t-1"
        verdict = json.dumps({
            "faithful": False,
            "reason": "sign is flipped",
            "quoted_code": code_quote,
            "quoted_spec": spec_quote,
        })
        sandbox = AdversarialSandbox(llm_client=_FakeLLMClient(verdict))
        report = sandbox.validate(plugin, _spec())
        assert not report.faithful_ok
        assert not report.passed
        assert any("Faithfulness check FAILED" in e for e in report.errors)

    def test_unverifiable_quote_is_inconclusive_not_a_failure(self):
        """A quote that doesn't actually appear in the code/spec is dropped
        as inconclusive -- the check can never block on an unverifiable claim
        (same anti-hallucination discipline as Step 8's evidence-cited claims)."""
        verdict = json.dumps({
            "faithful": False,
            "reason": "hallucinated mismatch",
            "quoted_code": "this substring is not in the code at all",
            "quoted_spec": "",
        })
        sandbox = AdversarialSandbox(llm_client=_FakeLLMClient(verdict))
        plugin = _plugin(_GOOD_SIGNAL)
        report = sandbox.validate(plugin, _spec())
        assert report.faithful_ok
        assert report.passed
        assert any("inconclusive" in w for w in report.warnings)

    def test_malformed_llm_response_is_inconclusive_not_a_failure(self):
        sandbox = AdversarialSandbox(llm_client=_FakeLLMClient("not json at all"))
        plugin = _plugin(_GOOD_SIGNAL)
        report = sandbox.validate(plugin, _spec())
        assert report.faithful_ok
        assert report.passed
        assert any("inconclusive" in w for w in report.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
