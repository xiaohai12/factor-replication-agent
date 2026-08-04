"""Session control-plane HTTP surface (Phase 1 of the session-centric UI
redesign; see docs/decision-log.md 2026-08-04).

Session CRUD + step-record reads live here as plain (fast) endpoints.
step3/4/5 gain artifact-identity-chained endpoints so `execute` can never be
handed arbitrary script text or a filesystem path -- only an `artifact_id`
(the script's own sha256) that a step4 validation record already vouches
for. See `_ARTIFACT_SAFETY` note on `execute_step5` below.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.sessions import append_event, complete_attempt_with_retry, read_events, session_store
from backend.state import build_extractor, build_llm_client, pipeline
from src.evaluation import diagnostics as step_diagnostics
from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.session import (
    STEP_IO_CONTRACT,
    ConcurrentModificationError,
    StepStatus,
    missing_input_refs,
)
from src.infra.session_store import SessionNotFoundError

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _get_or_404(session_id: str):
    try:
        return session_store.get(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"No session '{session_id}'")


def _concurrent_or_409(fn):
    try:
        return fn()
    except ConcurrentModificationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    factor_id: str
    paper_id: Optional[str] = None


@router.post("")
def create_session(req: CreateSessionRequest) -> dict:
    manifest = session_store.create(factor_id=req.factor_id, paper_id=req.paper_id)
    append_event(manifest.session_id, step=None, stage="session", event="created")
    return to_jsonable(manifest)


@router.get("")
def list_sessions() -> list[dict]:
    return [to_jsonable(m) for m in session_store.list_all()]


@router.get("/{session_id}")
def get_session(session_id: str) -> dict:
    return to_jsonable(_get_or_404(session_id))


@router.get("/{session_id}/steps/{step}")
def get_step(session_id: str, step: int) -> dict:
    manifest = _get_or_404(session_id)
    if step not in manifest.steps:
        raise HTTPException(status_code=404, detail=f"No step {step}")
    return {
        "record": to_jsonable(manifest.steps[step]),
        "contract": STEP_IO_CONTRACT.get(step, {}),
        "missing_input_refs": missing_input_refs(manifest, step),
    }


@router.get("/{session_id}/events")
def get_events(session_id: str, since_seq: int = -1) -> list[dict]:
    _get_or_404(session_id)  # 404 rather than an empty list for an unknown session
    return read_events(session_id, since_seq=since_seq)


@router.get("/{session_id}/diagnostics")
def get_diagnostics(session_id: str) -> dict:
    """Aggregate the latest recorded per-step diagnostics -- readiness/
    counters/flags ONLY, never a unified score (see
    src/evaluation/diagnostics.py's module docstring)."""
    manifest = _get_or_404(session_id)
    return {
        step: record.latest.diagnostics
        for step, record in manifest.steps.items()
        if record.latest and record.latest.diagnostics
    }


class ArchiveRequest(BaseModel):
    expected_revision: int


@router.post("/{session_id}/archive")
def archive_session(session_id: str, req: ArchiveRequest) -> dict:
    """Soft delete only -- never touches EvidenceStore/comparison.json
    artifacts a session merely references."""
    manifest = _concurrent_or_409(
        lambda: session_store.archive(session_id, req.expected_revision)
    )
    append_event(session_id, step=None, stage="session", event="archived")
    return to_jsonable(manifest)


# ---------------------------------------------------------------------------
# Step1-4 artifact read (traversal-guarded; only SESSION_OWNED_STEPS)
# ---------------------------------------------------------------------------


@router.get("/{session_id}/steps/{step}/artifact/{filename}")
def read_step_artifact(session_id: str, step: int, filename: str) -> dict:
    manifest = _get_or_404(session_id)
    if step not in manifest.steps:
        raise HTTPException(status_code=404, detail=f"No step {step}")
    try:
        step_dir = session_store.step_dir(session_id, step).resolve()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    file_path = (step_dir / filename).resolve()
    if not file_path.is_relative_to(step_dir) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"filename": filename, "content": file_path.read_text()}


# ---------------------------------------------------------------------------
# Step1 (extract) / Step2 (review) -- session-owned small artifacts
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    expected_revision: int
    paper_text: str
    llm_provider: str = "codex"
    llm_model: Optional[str] = None


@router.post("/{session_id}/steps/1/extract")
async def extract_step1(session_id: str, req: ExtractRequest) -> dict:
    manifest = _get_or_404(session_id)
    factor_id = manifest.factor_id
    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=1))

    def run(log):
        log(f"Building {req.llm_provider} LLM client...")
        client = build_llm_client(req.llm_provider, req.llm_model)
        extractor = build_extractor(client)
        log(f"Extracting MethodSpec for '{factor_id}'...")
        result = extractor.extract(factor_id, req.paper_text)
        if result.spec is None:
            complete_attempt_with_retry(session_id, step=1, status=StepStatus.FAILED, error=result.error or "extraction failed")
            append_event(session_id, step=1, stage="extract", event="failed", detail=result.error or "", level="error")
            raise RuntimeError(result.error or "extraction failed")

        step_dir = session_store.step_dir(session_id, 1)
        spec_filename = "methodspec.json"
        (step_dir / spec_filename).write_text(json.dumps(result.spec.model_dump(mode="json"), indent=2, default=str))

        diagnostics = step_diagnostics.step1_diagnostics(result.spec)
        complete_attempt_with_retry(
            session_id, step=1, status=StepStatus.SUCCESS,
            output_refs={"methodspec_ref": spec_filename}, diagnostics=diagnostics,
        )
        append_event(session_id, step=1, stage="extract", event="extracted", detail=spec_filename)
        return {"spec": to_jsonable(result.spec), "diagnostics": diagnostics}

    job_id = job_manager.create_job(run, session_id=session_id, step=1, stage="extract")
    return {"job_id": job_id}


class ReviewRequest(BaseModel):
    expected_revision: int
    spec: dict


@router.post("/{session_id}/steps/2/review")
def review_step2(session_id: str, req: ReviewRequest) -> dict:
    """Rules-based review only (sync, no LLM) -- matches the existing
    `POST /api/methodspecs/review` route's cost profile; the LLM-backed
    `review_with_llm` variant is not session-wired yet (future work)."""
    spec = MethodSpec.model_validate(req.spec)
    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=2))
    manifest = session_store.get(session_id)

    review = pipeline.review_gate.review(spec)
    step_dir = session_store.step_dir(session_id, 2)
    report_filename = "review_report.json"
    (step_dir / report_filename).write_text(json.dumps(to_jsonable(review), indent=2, default=str))

    diagnostics = step_diagnostics.step2_diagnostics(review)
    status = StepStatus.BLOCKED if review.requires_human else StepStatus.SUCCESS
    manifest = session_store.complete_attempt(
        session_id, manifest.revision, step=2, status=status,
        output_refs={"review_report_ref": report_filename}, diagnostics=diagnostics,
    )
    append_event(session_id, step=2, stage="review", event="reviewed", detail=review.disposition)
    return {"review": to_jsonable(review), "diagnostics": diagnostics, "revision": manifest.revision}


# ---------------------------------------------------------------------------
# Step3 -> Step4 -> Step5 artifact-identity chain
# ---------------------------------------------------------------------------


class BuildScriptRequest(BaseModel):
    expected_revision: int
    spec: dict
    plugin: dict
    snapshot_id: str
    config_overrides: Optional[dict] = None
    track: str = "original_method"


@router.post("/{session_id}/steps/3/script")
def build_step3_script(session_id: str, req: BuildScriptRequest) -> dict:
    """Assembles the backtest script and returns only `{artifact_id, sha256}`
    -- never the raw script body over this endpoint (use the artifact-read
    endpoint, which is traversal-guarded, to fetch the text for display)."""
    spec = MethodSpec.model_validate(req.spec)
    plugin = PluginRecord.model_validate(req.plugin)

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=3))
    manifest = session_store.get(session_id)

    try:
        built = pipeline.runner.build_script(
            plugin, spec, req.snapshot_id, req.config_overrides, track_name=req.track
        )
    except Exception as exc:  # noqa: BLE001 - report any build failure to the client
        session_store.complete_attempt(
            session_id, manifest.revision, step=3, status=StepStatus.FAILED, error=str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc))

    script_sha256 = hashlib.sha256(built["script_text"].encode()).hexdigest()
    step_dir = session_store.step_dir(session_id, 3)
    (step_dir / f"{script_sha256}.py").write_text(built["script_text"])
    (step_dir / f"{script_sha256}.plugin.json").write_text(json.dumps(plugin.model_dump(mode="json")))

    diagnostics = step_diagnostics.step3_diagnostics(plugin, built["config"])
    manifest = session_store.complete_attempt(
        session_id,
        manifest.revision,
        step=3,
        status=StepStatus.SUCCESS,
        output_refs={
            "plugin_ref": f"{script_sha256}.plugin.json",
            "script_ref": f"{script_sha256}.py",
            "script_sha256": script_sha256,
        },
        diagnostics=diagnostics,
    )
    append_event(session_id, step=3, stage="codegen", event="script_built", detail=script_sha256)
    return {"artifact_id": script_sha256, "sha256": script_sha256, "revision": manifest.revision}


class ValidateArtifactRequest(BaseModel):
    expected_revision: int
    spec: dict
    plugin: dict
    script_sha256: str


@router.post("/{session_id}/steps/4/validate")
def validate_step4_artifact(session_id: str, req: ValidateArtifactRequest) -> dict:
    """Validates the EXACT artifact step3 produced, identified by its own
    sha256 -- never accepts script text over the wire."""
    manifest = _get_or_404(session_id)
    step3_dir = session_store.step_dir(session_id, 3)
    script_path = step3_dir / f"{req.script_sha256}.py"
    if not script_path.is_file():
        raise HTTPException(status_code=404, detail=f"No script artifact '{req.script_sha256}'")
    script_text = script_path.read_text()
    # Defense in depth: the filename itself claims this hash, but a bug or a
    # tampered file must not silently be trusted -- recompute and check.
    if hashlib.sha256(script_text.encode()).hexdigest() != req.script_sha256:
        raise HTTPException(status_code=400, detail="Stored script artifact does not match its own filename hash")

    spec = MethodSpec.model_validate(req.spec)
    plugin = PluginRecord.model_validate(req.plugin)

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=4))
    manifest = session_store.get(session_id)

    report = pipeline.sandbox.validate(plugin, spec, script_text=script_text)
    (step3_dir / f"{req.script_sha256}.validation.json").write_text(
        json.dumps(to_jsonable(report), indent=2)
    )

    output_refs = {"validation_ref": f"{req.script_sha256}.validation.json"}
    if report.passed:
        output_refs["validated_script_sha256"] = req.script_sha256
    # This endpoint never passes a `data` slice to `sandbox.validate`, so the
    # execution smoke test is always SKIPPED here (not a genuine pass) --
    # `execution_check_supplied=False` renders that honestly rather than as
    # a green check (see src/evaluation/diagnostics.py's step4_diagnostics).
    diagnostics = step_diagnostics.step4_diagnostics(report, execution_check_supplied=False)
    manifest = session_store.complete_attempt(
        session_id,
        manifest.revision,
        step=4,
        status=StepStatus.SUCCESS if report.passed else StepStatus.FAILED,
        output_refs=output_refs,
        error=None if report.passed else "; ".join(report.errors),
        diagnostics=diagnostics,
    )
    append_event(
        session_id, step=4, stage="validate", event="validated",
        detail=f"passed={report.passed}", level="info" if report.passed else "warning",
    )
    return {"report": to_jsonable(report), "diagnostics": diagnostics, "revision": manifest.revision}


class ExecuteArtifactRequest(BaseModel):
    expected_revision: int
    spec: dict
    plugin: dict
    snapshot_id: str
    script_sha256: str
    config_overrides: Optional[dict] = None
    track: str = "original_method"


@router.post("/{session_id}/steps/5/execute")
def execute_step5(session_id: str, req: ExecuteArtifactRequest) -> dict:
    """_ARTIFACT_SAFETY: this endpoint accepts ONLY a `script_sha256` that
    matches a step4 attempt already recorded as SUCCESS with that exact
    `validated_script_sha256`. It never accepts raw script text or a
    filesystem path -- that would make this endpoint an arbitrary-code-
    execution surface (per docs/decision-log.md 2026-08-04 review). The
    bytes actually executed are read back from the session-owned step3
    artifact and re-hashed before running, so what was validated is
    guaranteed to be what runs -- never a freshly-regenerated (and
    potentially different) script.
    """
    manifest = _get_or_404(session_id)
    step4_record = manifest.steps.get(4)
    latest4 = step4_record.latest if step4_record else None
    if (
        not latest4
        or latest4.status != StepStatus.SUCCESS
        or latest4.output_refs.get("validated_script_sha256") != req.script_sha256
    ):
        raise HTTPException(
            status_code=400,
            detail="script_sha256 has not passed step4 validation in this session; refusing to execute",
        )

    step3_dir = session_store.step_dir(session_id, 3)
    script_path = step3_dir / f"{req.script_sha256}.py"
    if not script_path.is_file():
        raise HTTPException(status_code=404, detail=f"No script artifact '{req.script_sha256}'")
    script_text = script_path.read_text()
    if hashlib.sha256(script_text.encode()).hexdigest() != req.script_sha256:
        raise HTTPException(status_code=400, detail="Stored script artifact does not match its own filename hash")

    spec = MethodSpec.model_validate(req.spec)
    plugin = PluginRecord.model_validate(req.plugin)

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=5))
    manifest = session_store.get(session_id)

    try:
        # Rebuild `built` for its path/config/execution_id bookkeeping, but
        # overwrite script_text with the EXACT validated bytes before
        # execute() writes them to disk -- build_script is deterministic
        # given the same inputs, but this removes any need to trust that.
        built = pipeline.runner.build_script(
            plugin, spec, req.snapshot_id, req.config_overrides, track_name=req.track
        )
        built["script_text"] = script_text
        result = pipeline.runner.execute(built)
        run_record = pipeline.runner.make_run_record(spec, plugin, req.track, result)
        pipeline.evidence_store.save_run(run_record)
        pipeline.run_registry.register(run_record)
    except Exception as exc:  # noqa: BLE001 - report any execute failure to the client
        session_store.complete_attempt(
            session_id, manifest.revision, step=5, status=StepStatus.FAILED, error=str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc))

    manifest = session_store.complete_attempt(
        session_id,
        manifest.revision,
        step=5,
        status=StepStatus.SUCCESS,
        output_refs={"execution_ids": json.dumps([run_record.run_id])},
        diagnostics=step_diagnostics.step5_diagnostics(run_record),
    )
    append_event(session_id, step=5, stage="execute", event="executed", detail=run_record.run_id)
    return {
        "run_record": to_jsonable(run_record),
        "metrics": result["metrics"],
        # Embedded so the frontend can chart it without a second round trip
        # (to_jsonable converts the pandas DataFrame to list-of-records JSON,
        # same conversion the pre-existing /api/backtest/run job already
        # relies on for its own return_series field).
        "return_series": to_jsonable(result["return_series"]),
        "revision": manifest.revision,
    }
