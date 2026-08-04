"""Regression tests for D2 (docs/multi-config-evidence-plan.md /
docs/decision-log.md 2026-08-03, Phase 0.4): `RunRecord.run_id` used to be
`f"{factor_id}_{track}_{code_hash[:8]}"` -- no `config_hash` component at
all, so two DIFFERENT config overrides run on the same track name with the
same plugin code were indistinguishable by run_id. `BacktestRunner.
build_script` now computes `config_hash`/`execution_id` from the resolved
config BEFORE execution (thread through `execute()`'s result), and
`make_run_record`/`make_failed_run_record` use that pre-computed identity
instead of recomputing (or omitting) it.
"""

from __future__ import annotations

from src.infra.models.method_spec import MethodSpec, SignalSpec
from src.infra.models.plugin import PluginRecord
from src.steps.step5_backtest_runner import BacktestRunner


def _spec() -> MethodSpec:
    return MethodSpec(factor_id="t", factor_name="Test", signal=SignalSpec())


def _plugin() -> PluginRecord:
    return PluginRecord(
        plugin_id="t_v1", factor_id="t",
        code="def compute_signal(df): return df", code_hash="deadbeef",
    )


def _runner() -> BacktestRunner:
    # make_run_record/make_failed_run_record don't touch self.data_layer or
    # self.scripts_path, so a bare instance (no real DataLayer/snapshot) is
    # enough for these unit tests.
    return BacktestRunner(data_layer=None, scripts_path="/tmp/unused")


class TestRunIdIncludesConfigHash:
    def test_two_different_configs_on_same_track_get_different_run_ids(self):
        runner = _runner()
        spec = _spec()
        plugin = _plugin()

        result_a = {
            "metrics": {"mean_monthly_return": 0.01, "t_stat": 2.0},
            "config": {"weighting_rule": "vw"},
            "config_hash": "hashA00000000000",
            "execution_id": "t__original_method__deadbeef__hashA000",
        }
        result_b = {
            "metrics": {"mean_monthly_return": 0.02, "t_stat": 3.0},
            "config": {"weighting_rule": "ew"},
            "config_hash": "hashB00000000000",
            "execution_id": "t__original_method__deadbeef__hashB000",
        }

        record_a = runner.make_run_record(spec, plugin, "original_method", result_a)
        record_b = runner.make_run_record(spec, plugin, "original_method", result_b)

        assert record_a.run_id != record_b.run_id
        assert record_a.config_hash != record_b.config_hash

    def test_execution_id_is_used_verbatim_as_run_id_when_present(self):
        runner = _runner()
        result = {
            "metrics": {},
            "config": {},
            "config_hash": "abc123",
            "execution_id": "t__original_method__deadbeef__abc123",
        }
        record = runner.make_run_record(_spec(), _plugin(), "original_method", result)
        assert record.run_id == "t__original_method__deadbeef__abc123"

    def test_falls_back_to_legacy_run_id_format_when_execution_id_absent(self):
        """A minimal fake runner's execute() result (no config_hash/
        execution_id keys) must still produce a valid, deterministic run_id."""
        runner = _runner()
        result = {"metrics": {}, "config": {"weighting_rule": "vw"}}
        record = runner.make_run_record(_spec(), _plugin(), "original_method", result)
        assert record.run_id == "t_original_method_deadbeef"
        assert record.config_hash  # still computed, just not pre-supplied


class TestFailedRunIdIncludesConfigHash:
    def test_failed_record_run_id_includes_config_hash(self):
        runner = _runner()
        record = runner.make_failed_run_record(
            _spec(), _plugin(), "original_method", {"weighting_rule": "ew"}, "boom"
        )
        assert record.status == "failed"
        assert record.config_hash
        assert record.config_hash[:8] in record.run_id
        assert record.run_id.endswith("_failed")
