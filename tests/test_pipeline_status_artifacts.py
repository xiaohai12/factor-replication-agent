"""Test that `Pipeline.run_full_pipeline`'s returned `PipelineStatus` surfaces
the `comparison.json`/`diagnosis.json` files step 5/6/8 already write to disk
(docs/multi-config-evidence-plan.md Phase C/D: "persisted and
pipeline-returned diagnosis report"). Uses a fake controller (no real
subprocess/data) that just pre-writes the files at the path `Pipeline`
already knows to look at, so this is a pure wiring test.
"""

from __future__ import annotations

import json

from src.infra.models.method_spec import MethodSpec, SignalSpec
from src.infra.models.run_record import RunMetrics, RunRecord
from src.pipeline import Pipeline
from src.steps.step2_reviewer import ReviewResult


def _spec() -> MethodSpec:
    return MethodSpec(factor_id="t", factor_name="Test", signal=SignalSpec())


class FakeExtraction:
    def __init__(self, spec):
        self.spec = spec


class FakeExtractor:
    def extract(self, factor_id, paper_text, reextract_feedback=None, **kw):
        return FakeExtraction(_spec())


class FakeController:
    """Writes comparison.json (+ optional diagnosis.json) at the exact path
    `Pipeline.run_full_pipeline` expects, then returns one successful run --
    mirrors what the REAL `DualTrackController.run_experiment` would have
    produced on disk, without any real subprocess/data/LLM."""

    def __init__(self, scripts_path, write_diagnosis: bool = False):
        self.scripts_path = scripts_path
        self.write_diagnosis = write_diagnosis

    def run_experiment(self, plugin, spec, plan, snapshot_id):
        results_dir = self.scripts_path / "results" / spec.factor_id
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "comparison.json").write_text(json.dumps({"schema_version": 2}))
        if self.write_diagnosis:
            (results_dir / "diagnosis.json").write_text(
                json.dumps({"status": "llm_assisted_proposal", "claims": []})
            )
        return [
            RunRecord(
                run_id="t_original_method", factor_id="t", plugin_id="p1",
                track="original_method", metrics=RunMetrics(), status="success",
            )
        ]


def _pipeline(tmp_path, write_diagnosis: bool = False) -> Pipeline:
    p = Pipeline(
        data_path=str(tmp_path), evidence_path=str(tmp_path / "ev"),
        scripts_path=str(tmp_path / "sc"),
    )
    p.extractor = FakeExtractor()
    p._review = lambda spec, paper_text: ReviewResult(
        disposition="approved", approved=True, codegen_ready=True, paper_faithful=True
    )
    p.meta_coder.generate_plugin = lambda spec: __import__(
        "src.infra.models.plugin", fromlist=["PluginRecord"]
    ).PluginRecord(plugin_id="p1", factor_id="t", code="def compute_signal(df): return df", code_hash="h1")
    p.repair_loop.build_validate_repair = lambda plugin, spec, snapshot_id, overrides: type(
        "V", (), {"plugin": plugin}
    )()
    p.controller = FakeController(p.scripts_path, write_diagnosis=write_diagnosis)
    return p


class TestPipelineStatusArtifacts:
    def test_comparison_path_set_when_comparison_json_exists(self, tmp_path):
        p = _pipeline(tmp_path, write_diagnosis=False)
        _runs, status = p.run_full_pipeline("t", "snap", paper_text="paper")

        assert status.comparison_path is not None
        assert status.comparison_path.exists()
        assert status.diagnosis is None

    def test_diagnosis_loaded_when_diagnosis_json_exists(self, tmp_path):
        p = _pipeline(tmp_path, write_diagnosis=True)
        _runs, status = p.run_full_pipeline("t", "snap", paper_text="paper")

        assert status.diagnosis is not None
        assert status.diagnosis["status"] == "llm_assisted_proposal"
