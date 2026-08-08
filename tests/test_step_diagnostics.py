"""Tests for `src/evaluation/diagnostics.py` -- deterministic per-step
diagnostics (readiness/counters/flags), NOT a unified quality score. Step1/
step2 diagnostics have no coverage here: those concepts (paper-extraction
ambiguity, rules-based review) only existed on the retired v1 flat
`MethodSpec`/`ReviewGate`; the paper-first schema's equivalent (`MethodReview.
findings`) is structurally different, not a mechanical port.
"""

from __future__ import annotations

from pathlib import Path

from src.evaluation import diagnostics as diag
from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunMetrics, RunRecord
from src.steps.step3_codegen.registry import build_config
from src.steps.step4_validator import AdversarialSandbox
from tests._spec_test_helpers import asset_growth_resolved_spec
from tests.test_replication_diagnosis import FakeLLM, _bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "tests" / "fixtures" / "plugins" / "cooper_gulen_schill_2008_asset_growth.py"


def _load_plugin(spec) -> PluginRecord:
    return PluginRecord(
        plugin_id=f"{spec.paper.factor_id}_resolved",
        factor_id=spec.paper.factor_id,
        code=PLUGIN_PATH.read_text(),
        code_hash="synthetic",
    )


class TestStep3Diagnostics:
    def test_real_fixture_plugin_and_config(self):
        spec = asset_growth_resolved_spec()
        plugin = _load_plugin(spec)
        config = build_config(spec, None)
        result = diag.step3_diagnostics(plugin, config)
        assert result["counters"]["repair_attempt_count"] == 0
        assert isinstance(result["counters"]["substitution_count"], int)

    def test_repair_attempts_surface_as_a_flag(self):
        spec = asset_growth_resolved_spec()
        plugin = _load_plugin(spec)
        plugin.repair_trace = ["attempt 1: fixed a syntax error"]
        config = build_config(spec, None)
        result = diag.step3_diagnostics(plugin, config)
        assert result["counters"]["repair_attempt_count"] == 1
        assert any("repair attempt" in f for f in result["flags"])


class TestStep4Diagnostics:
    def test_real_fixture_validation_without_execution_check(self):
        spec = asset_growth_resolved_spec()
        plugin = _load_plugin(spec)
        report = AdversarialSandbox().validate(plugin, spec, script_text=None)
        result = diag.step4_diagnostics(report, execution_check_supplied=False)
        # executes_ok defaults True even though the check was skipped --
        # must be rendered "skipped", never conflated with a real pass.
        assert result["counters"]["executes_ok"] == "skipped"
        assert any("skipped" in f for f in result["flags"])

    def test_executes_ok_true_with_check_supplied_is_a_real_pass(self):
        report = ValidationReport(
            passed=True, syntax_ok=True, schema_ok=True, no_future_leak=True,
            reproducible=True, executes_ok=True,
        )
        result = diag.step4_diagnostics(report, execution_check_supplied=True)
        assert result["counters"]["executes_ok"] == "pass"
        assert result["readiness"] == "ready"

    def test_failed_report_is_blocked(self):
        report = ValidationReport(passed=False, errors=["future leak detected"])
        result = diag.step4_diagnostics(report, execution_check_supplied=True)
        assert result["readiness"] == "blocked"
        assert "future leak detected" in result["flags"]


class TestStep5Diagnostics:
    def test_successful_run_record(self):
        run = RunRecord(
            run_id="r1", factor_id="f", plugin_id="p", track="original_method",
            status="success",
            metrics=RunMetrics(coverage=0.9, n_months=100, microcap_share=0.1),
        )
        result = diag.step5_diagnostics(run)
        assert result["readiness"] == "ready"
        assert result["counters"]["n_months"] == 100
        assert result["flags"] == []

    def test_high_microcap_share_is_flagged(self):
        run = RunRecord(
            run_id="r1", factor_id="f", plugin_id="p", track="original_method",
            status="success",
            metrics=RunMetrics(microcap_share=0.9),
        )
        result = diag.step5_diagnostics(run)
        assert any("microcap_share" in f for f in result["flags"])

    def test_failed_run_is_not_ready(self):
        run = RunRecord(run_id="r1", factor_id="f", plugin_id="p", track="original_method", status="failed")
        result = diag.step5_diagnostics(run)
        assert result["readiness"] == "not_ready"


class TestStep6Diagnostics:
    def test_invalidated_batch_is_blocked(self):
        runs = [
            RunRecord(
                run_id="r1", factor_id="f", plugin_id="p", track="original_method",
                status="success", batch_invalidated=True,
                batch_invalidation_reason="a track's repair changed its code",
            ),
        ]
        result = diag.step6_diagnostics(runs)
        assert result["readiness"] == "blocked"
        assert "changed its code" in result["flags"][0]

    def test_all_success_no_invalidation_is_ready(self):
        runs = [
            RunRecord(run_id="r1", factor_id="f", plugin_id="p", track="original_method", status="success"),
            RunRecord(run_id="r2", factor_id="f", plugin_id="p", track="ablation_breakpoint", status="success"),
        ]
        result = diag.step6_diagnostics(runs)
        assert result["readiness"] == "ready"
        assert result["counters"] == {"track_count": 2, "success_count": 2, "batch_invalidated": False}


class TestStep7Diagnostics:
    def test_real_bundle_from_step7_helpers(self):
        bundle = _bundle()
        result = diag.step7_diagnostics(bundle)
        assert "overall_tag" in result["counters"]
        assert result["readiness"] == "ready"

    def test_sign_mismatch_is_flagged(self):
        bundle = {"derived": {"overall_tag": "sign_mismatch"}, "gap_decomposition": {"available": True}}
        result = diag.step7_diagnostics(bundle)
        assert any("sign mismatch" in f for f in result["flags"])


class TestStep8Diagnostics:
    def test_real_diagnoser_report_no_rejections(self):
        from src.steps.step8_diagnosis import ReplicationDiagnoser

        bundle = _bundle()
        llm = FakeLLM({"claims": []})
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        result = diag.step8_diagnostics(report)
        assert result["counters"]["accepted_claim_count"] == 0
        assert result["counters"]["rejected_claim_count"] == 0
        assert result["flags"] == []

    def test_rejected_claims_surface_as_a_flag(self):
        from src.steps.step8_diagnosis import ReplicationDiagnoser

        bundle = _bundle()
        llm = FakeLLM(
            {
                "claims": [
                    {
                        "claim_type": "sign_agreement",
                        "relation": "agrees",
                        "text": "Our spread is -0.008.",
                        "evidence_keys": ["derived.tracks.original_method.vs_paper.sign_agrees"],
                    }
                ]
            }
        )
        report = ReplicationDiagnoser(llm_client=llm, model="fake").diagnose(bundle)
        result = diag.step8_diagnostics(report)
        assert result["counters"]["rejected_claim_count"] == 1
        assert any("rejected" in f for f in result["flags"])
