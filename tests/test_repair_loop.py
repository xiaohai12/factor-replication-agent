"""Unit tests for the shared RepairLoop (src/infra/repair.py) — the one
technical self-debugging loop used by Pipeline and DualTrackController.

Focus: the audit trail (RepairAttempt history) and the success/failure
outcome contract, exercised with minimal fakes (no subprocess, no LLM).
"""

from __future__ import annotations

from src.infra.models.method_spec import MethodSpec, SignalSpec
from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.repair import RepairLoop


def _spec() -> MethodSpec:
    return MethodSpec(factor_id="t", factor_name="Test", signal=SignalSpec())


def _plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="t_v1", factor_id="t",
        code="def compute_signal(df): return df", code_hash="hash0",
    )


class FakeRunner:
    def __init__(self, execute_fail_times: int = 0):
        self.execute_fail_times = execute_fail_times
        self.execute_calls = 0

    def build_script(self, plugin, spec, snapshot_id, config_overrides, track_name=None) -> dict:
        return {"script_text": plugin.code, "config": {}}

    def execute(self, built: dict) -> dict:
        self.execute_calls += 1
        if self.execute_calls <= self.execute_fail_times:
            raise RuntimeError(f"exec fail {self.execute_calls}")
        return {"metrics": {}, "config": built["config"]}


class FakeSandbox:
    """Passes validation after `fail_times` failures."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.validate_calls = 0

    def validate(self, plugin, spec, script_text=None, data=None) -> ValidationReport:
        self.validate_calls += 1
        if self.validate_calls <= self.fail_times:
            return ValidationReport(passed=False, errors=[f"validate fail {self.validate_calls}"])
        return ValidationReport(passed=True)


class FakeMetaCoder:
    def __init__(self, llm: bool = True):
        self.llm_client = object() if llm else None
        self.repair_calls = 0

    def repair_plugin(self, plugin, errors):
        self.repair_calls += 1
        new = plugin.model_copy(deep=True)
        new.code_hash = f"hash{self.repair_calls}"
        return new


def test_validate_pass_first_try_has_empty_history():
    loop = RepairLoop(FakeRunner(), FakeSandbox(fail_times=0), FakeMetaCoder())
    outcome = loop.build_validate_repair(_plugin(), _spec(), "snap", None)
    assert outcome.plugin.validation_status == "passed"
    assert outcome.history == []


def test_validate_failure_then_pass_records_one_attempt():
    sandbox = FakeSandbox(fail_times=1)  # fail once, then pass
    meta = FakeMetaCoder()
    loop = RepairLoop(FakeRunner(), sandbox, meta)

    outcome = loop.build_validate_repair(_plugin(), _spec(), "snap", None)

    assert meta.repair_calls == 1
    assert len(outcome.history) == 1
    attempt = outcome.history[0]
    assert attempt.trigger_stage == "validate"
    assert attempt.error_kind == "technical"
    assert attempt.code_hash_before == "hash0"
    assert attempt.code_hash_after == "hash1"
    assert attempt.passed is True  # the repair led to a passing re-validation


def test_validate_exhaustion_raises():
    loop = RepairLoop(FakeRunner(), FakeSandbox(fail_times=99), FakeMetaCoder(), max_retries=2)
    try:
        loop.build_validate_repair(_plugin(), _spec(), "snap", None)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "repair failed after 2 attempts" in str(e)


def test_execute_success_first_try_empty_history():
    runner = FakeRunner(execute_fail_times=0)
    loop = RepairLoop(runner, FakeSandbox(), FakeMetaCoder())
    built = runner.build_script(_plugin(), _spec(), "snap", None)
    outcome = loop.execute_with_repair(_plugin(), built, _spec(), "snap", None)
    assert outcome.error is None
    assert outcome.result is not None
    assert outcome.history == []


def test_execute_failure_then_repair_then_success_records_execute_attempt():
    runner = FakeRunner(execute_fail_times=1)  # fail once, then succeed
    sandbox = FakeSandbox(fail_times=0)  # re-validate passes
    meta = FakeMetaCoder()
    loop = RepairLoop(runner, sandbox, meta)
    built = runner.build_script(_plugin(), _spec(), "snap", None)

    outcome = loop.execute_with_repair(_plugin(), built, _spec(), "snap", None)

    assert outcome.error is None
    assert meta.repair_calls == 1
    assert runner.execute_calls == 2
    # exactly one execute-triggered repair recorded
    exec_attempts = [a for a in outcome.history if a.trigger_stage == "execute"]
    assert len(exec_attempts) == 1
    assert exec_attempts[0].passed is True


def test_execute_exhaustion_returns_error_not_raise():
    runner = FakeRunner(execute_fail_times=99)  # always fails
    loop = RepairLoop(runner, FakeSandbox(), FakeMetaCoder(), max_retries=2)
    built = runner.build_script(_plugin(), _spec(), "snap", None)

    outcome = loop.execute_with_repair(_plugin(), built, _spec(), "snap", None)

    assert outcome.result is None
    assert outcome.error is not None
    assert "exec fail" in outcome.error


def test_execute_failure_no_llm_stops_immediately():
    runner = FakeRunner(execute_fail_times=99)
    meta = FakeMetaCoder(llm=False)  # no repair available
    loop = RepairLoop(runner, FakeSandbox(), meta)
    built = runner.build_script(_plugin(), _spec(), "snap", None)

    outcome = loop.execute_with_repair(_plugin(), built, _spec(), "snap", None)

    assert outcome.error is not None
    assert meta.repair_calls == 0
    assert runner.execute_calls == 1  # no retry without an LLM client
