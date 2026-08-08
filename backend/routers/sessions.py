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
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.sessions import append_event, complete_attempt_with_retry, read_events, session_store
from backend.state import (
    REAL_WRDS_SNAPSHOT_ID,
    VALIDATION_SAMPLE_SNAPSHOT_ID,
    build_llm_client,
    build_meta_coder,
    ensure_real_wrds_snapshot,
    ensure_validation_sample_snapshot,
    pipeline,
)
from src.evaluation import diagnostics as step_diagnostics
from src.infra.models.paper_method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.repair import RepairLoop
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


def _validate_spec(raw_spec: dict) -> ResolvedMethodSpec:
    """`ResolvedMethodSpec.model_validate(raw_spec)` raises a pydantic
    `ValidationError` for a malformed/incomplete spec (e.g. the request
    body's `spec` field was left as the UI's empty placeholder `{}`) --
    uncaught, that propagates as an unhandled exception and FastAPI turns it
    into an opaque 500 with no useful detail. Every endpoint that validates
    a client-supplied spec should go through this instead of calling
    `ResolvedMethodSpec.model_validate` directly."""
    try:
        return ResolvedMethodSpec.model_validate(raw_spec)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MethodSpec: {exc}")


def _validate_plugin(raw_plugin: dict) -> PluginRecord:
    """Same rationale/fix as `_validate_spec`, for `req.plugin` -- reproduced
    live: navigating away from step3's page and back resets the request
    editor's `plugin` field to the empty template default (`{}`), and
    submitting that uncaught crashed with a real 500 (`PluginRecord.
    model_validate({})` -> missing plugin_id/factor_id/code). Every endpoint
    that validates a client-supplied plugin should go through this instead
    of calling `PluginRecord.model_validate` directly. See
    docs/decision-log.md 2026-08-05 entry."""
    try:
        return PluginRecord.model_validate(raw_plugin)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid plugin: {exc}")


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


class HardDeleteRequest(BaseModel):
    expected_revision: int
    # Explicit second confirmation, not just the HTTP verb -- a session
    # delete is otherwise a single click/request away from being
    # irreversible for the session's OWN step1-4 artifacts (never for
    # EvidenceStore, which this never touches).
    confirm: bool = False


@router.delete("/{session_id}")
def hard_delete_session(session_id: str, req: HardDeleteRequest) -> dict:
    """Physically deletes the session's own directory (writes a tombstone
    record first -- see `SessionStore.hard_delete`). Never deletes
    `EvidenceStore`/`comparison.json`/`diagnosis.json`, which this session
    only ever referenced."""
    _get_or_404(session_id)
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Hard delete requires confirm=true -- this is irreversible for this session's own artifacts",
        )
    _concurrent_or_409(lambda: session_store.hard_delete(session_id, req.expected_revision))
    return {"session_id": session_id, "deleted": True}


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
# Step3 -> Step4 -> Step5 artifact-identity chain
# ---------------------------------------------------------------------------


class BuildScriptRequest(BaseModel):
    expected_revision: int
    spec: dict
    plugin: dict
    config_overrides: Optional[dict] = None
    track: str = "original_method"


@router.post("/{session_id}/steps/3/script")
def build_step3_script(session_id: str, req: BuildScriptRequest) -> dict:
    """Assembles the backtest script and returns only `{artifact_id, sha256}`
    -- never the raw script body over this endpoint (use the artifact-read
    endpoint, which is traversal-guarded, to fetch the text for display).

    No user-facing `snapshot_id` anymore: always builds against
    `REAL_WRDS_SNAPSHOT_ID` (the real data/local export). Step4 validates the
    same script against a small `VALIDATION_SAMPLE_SNAPSHOT_ID` sample via an
    env-var data-path override instead of rebuilding (see validate_step4_artifact
    / script_generator.py's DATA_PATH/SIGNAL_DATA_DIR env vars)."""
    spec = _validate_spec(req.spec)
    plugin = _validate_plugin(req.plugin)
    ensure_real_wrds_snapshot()

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=3))
    manifest = session_store.get(session_id)

    try:
        built = pipeline.runner.build_script(
            plugin, spec, REAL_WRDS_SNAPSHOT_ID, req.config_overrides, track_name=req.track
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
    # Sessions that skip step1/2 (e.g. loaded an already-resolved MethodSpec
    # straight into step3 via MethodSpecPicker) have no step1 methodspec_ref
    # for step4/5's `spec` to be auto-filled from -- persist it here too so
    # the frontend's buildAutoFilledRequest always has a fallback.
    (step_dir / f"{script_sha256}.spec.json").write_text(json.dumps(spec.model_dump(mode="json")))

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
            "spec_ref": f"{script_sha256}.spec.json",
        },
        diagnostics=diagnostics,
    )
    append_event(session_id, step=3, stage="codegen", event="script_built", detail=script_sha256)
    return {"artifact_id": script_sha256, "sha256": script_sha256, "revision": manifest.revision}


class ValidateArtifactRequest(BaseModel):
    expected_revision: int
    script_sha256: str
    llm_provider: str = "codex"
    llm_model: Optional[str] = None


@router.post("/{session_id}/steps/4/validate")
async def validate_step4_artifact(session_id: str, req: ValidateArtifactRequest) -> dict:
    """Validates the EXACT artifact step3 produced, identified by its own
    sha256 -- never accepts script text, spec, or plugin JSON over the wire.
    The `spec`/`plugin` that get validated are read back from step3's own
    `{sha}.spec.json`/`{sha}.plugin.json` (written by build_step3_script),
    same artifact-identity-chain principle as `script_text` below -- the
    caller can never smuggle in a different spec/plugin than what step3
    actually built this exact script from.

    No user-facing `snapshot_id`: always validates against the small
    `VALIDATION_SAMPLE_SNAPSHOT_ID` real-data sample (fast, genuinely real
    data) via `Pipeline._build_validation_slice`, wired through the shared
    `RepairLoop` (a technical-only build->validate->repair->rebuild cycle,
    same one `Pipeline.run_from_method_spec`/`DualTrackController` use) so a
    repairable syntax/schema failure is fixed automatically instead of just
    reported. Runs as a background job since a multi-attempt repair loop can
    involve LLM calls that take a while; `log` streams progress into the
    job's SSE log.
    """
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

    spec_path = step3_dir / f"{req.script_sha256}.spec.json"
    plugin_path = step3_dir / f"{req.script_sha256}.plugin.json"
    if not spec_path.is_file() or not plugin_path.is_file():
        raise HTTPException(status_code=404, detail=f"No spec/plugin artifact for script '{req.script_sha256}'")
    spec = _validate_spec(json.loads(spec_path.read_text()))
    plugin = _validate_plugin(json.loads(plugin_path.read_text()))

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=4))

    def run(log):
        ensure_validation_sample_snapshot()
        step4_dir = session_store.step_dir(session_id, 4)
        validation_slice = pipeline._build_validation_slice(spec, VALIDATION_SAMPLE_SNAPSHOT_ID)
        current_plugin = plugin
        repair_history = []
        report = pipeline.sandbox.validate(
            current_plugin, spec, script_text=script_text, data=validation_slice
        )
        validated_sha256 = req.script_sha256
        output_refs = {}
        if not report.passed:
            log("Initial validation failed; requesting technical repair...")
            llm_client = build_llm_client(req.llm_provider, req.llm_model)
            meta_coder = build_meta_coder(llm_client)
            repair_loop = RepairLoop(pipeline.runner, pipeline.sandbox, meta_coder)
            outcome = repair_loop.build_validate_repair(
                current_plugin, spec, VALIDATION_SAMPLE_SNAPSHOT_ID, None, data=validation_slice, log=log
            )
            current_plugin = outcome.plugin
            repair_history = outcome.history
            report = current_plugin.validation_report
            if report.passed:
                validated_sha256 = hashlib.sha256(outcome.built["script_text"].encode()).hexdigest()
                (step3_dir / f"{validated_sha256}.py").write_text(outcome.built["script_text"])
                # Repair only ever changes the plugin's code, never the spec --
                # copy it forward under the repaired hash too so step5 (which
                # reads spec/plugin back by `script_sha256`, never over the
                # wire) can always find both artifacts for whatever hash ends
                # up in `validated_script_sha256`.
                (step3_dir / f"{validated_sha256}.spec.json").write_text(
                    json.dumps(spec.model_dump(mode="json"))
                )
                # Repair changed the plugin's code -- record the REPAIRED
                # plugin as this step's own output_ref so any later auto-fill
                # (e.g. the frontend's step5 request) picks up the plugin that
                # was actually validated, not step3's original (buggy) one.
                (step4_dir / f"{validated_sha256}.plugin.json").write_text(
                    json.dumps(current_plugin.model_dump(mode="json"))
                )
                output_refs["plugin_ref"] = f"{validated_sha256}.plugin.json"
                output_refs["spec_ref"] = f"{validated_sha256}.spec.json"
        (step3_dir / f"{validated_sha256}.validation.json").write_text(
            json.dumps(to_jsonable(report), indent=2)
        )
        output_refs["validation_ref"] = f"{validated_sha256}.validation.json"
        if report.passed:
            output_refs["validated_script_sha256"] = validated_sha256
        diagnostics = step_diagnostics.step4_diagnostics(report, execution_check_supplied=True)
        log(f"Validation {'passed' if report.passed else 'failed'}.")
        result_manifest = complete_attempt_with_retry(
            session_id,
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
        return {
            "report": to_jsonable(report),
            "diagnostics": diagnostics,
            "revision": result_manifest.revision,
            "repair_history": to_jsonable(repair_history) if repair_history else [],
            "plugin": to_jsonable(current_plugin) if repair_history else None,
            "validated_script_sha256": validated_sha256,
        }

    job_id = job_manager.create_job(run, session_id=session_id, step=4, stage="validate")
    return {"job_id": job_id}


class ExecuteArtifactRequest(BaseModel):
    expected_revision: int
    script_sha256: str
    config_overrides: Optional[dict] = None
    track: str = "original_method"


@router.post("/{session_id}/steps/5/execute")
async def execute_step5(session_id: str, req: ExecuteArtifactRequest) -> dict:
    """_ARTIFACT_SAFETY: this endpoint accepts ONLY a `script_sha256` that
    matches a step4 attempt already recorded as SUCCESS with that exact
    `validated_script_sha256`. It never accepts raw script text, spec, or
    plugin JSON over the wire -- that would make this endpoint an arbitrary-
    code-execution surface (per docs/decision-log.md 2026-08-04 review). The
    script bytes, spec, and plugin are all read back from the session-owned
    step3 (or, if step4's RepairLoop changed the plugin, step4) artifacts and
    the script is re-hashed before running, so what was validated is
    guaranteed to be what runs -- never a freshly-regenerated (and
    potentially different) script/spec/plugin.

    No user-facing `snapshot_id`: always executes against
    `REAL_WRDS_SNAPSHOT_ID` (the real data/local export) regardless of what
    step4 validated the script against (step4 always validates against the
    small `VALIDATION_SAMPLE_SNAPSHOT_ID` sample instead -- see
    validate_step4_artifact) via the env-var data-path override (see
    script_generator.py / BacktestRunner.execute()). Only the data SOURCE
    differs between the two steps, never the `compute_signal` code itself.

    Runs as a background job (not a plain sync response): a real-data
    backtest subprocess (see `BacktestRunner.execute`'s `log` param) can take
    anywhere from seconds (synthetic data) to minutes (full real WRDS CSVs),
    and a synchronous request gives the caller zero feedback for however
    long that takes, indistinguishable from a hang. Streaming the
    subprocess's stdout/stderr into the job's SSE log as it runs fixes that.
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

    spec_path = step3_dir / f"{req.script_sha256}.spec.json"
    if not spec_path.is_file():
        raise HTTPException(status_code=404, detail=f"No spec artifact for script '{req.script_sha256}'")
    spec = _validate_spec(json.loads(spec_path.read_text()))

    # step4's RepairLoop, when it changed the plugin's code, records its OWN
    # plugin_ref (in step4_dir) for this exact hash -- that repaired plugin
    # must win over step3's original (possibly-buggy) one.
    step4_dir = session_store.step_dir(session_id, 4)
    plugin_path = step4_dir / f"{req.script_sha256}.plugin.json"
    if not plugin_path.is_file():
        plugin_path = step3_dir / f"{req.script_sha256}.plugin.json"
    if not plugin_path.is_file():
        raise HTTPException(status_code=404, detail=f"No plugin artifact for script '{req.script_sha256}'")
    plugin = _validate_plugin(json.loads(plugin_path.read_text()))

    _concurrent_or_409(lambda: session_store.start_attempt(session_id, req.expected_revision, step=5))

    def run(log):
        try:
            ensure_real_wrds_snapshot()
            # Rebuild `built` for its path/config/execution_id bookkeeping, but
            # overwrite script_text with the EXACT validated bytes before
            # execute() writes them to disk -- build_script is deterministic
            # given the same inputs, but this removes any need to trust that.
            built = pipeline.runner.build_script(
                plugin, spec, REAL_WRDS_SNAPSHOT_ID, req.config_overrides, track_name=req.track
            )
            built["script_text"] = script_text
            # The validated bytes' own DATA_PATH/SIGNAL_DATA_DIR literals
            # still point at whatever step4 validated against (the small
            # `VALIDATION_SAMPLE_SNAPSHOT_ID` sample) -- override them via env
            # vars to the real data snapshot this endpoint always executes
            # against (see script_generator.py's env-var-overridable
            # DATA_PATH/SIGNAL_DATA_DIR + BacktestRunner.execute()'s override
            # params). Without this, execution would silently keep reading
            # step4's small sample instead of the real data.
            snapshot = pipeline.data_layer.snapshots.get_snapshot(REAL_WRDS_SNAPSHOT_ID)
            if snapshot is None:
                raise RuntimeError(f"Snapshot '{REAL_WRDS_SNAPSHOT_ID}' not registered on this DataLayer")
            storage_path = Path(snapshot.storage_path)
            log(f"Executing backtest script for '{spec.paper.factor_id}' (snapshot '{REAL_WRDS_SNAPSHOT_ID}')...")
            result = pipeline.runner.execute(
                built,
                log=log,
                data_path_override=str(storage_path / "crsp_msf.parquet"),
                signal_data_dir_override=str(storage_path),
            )
            run_record = pipeline.runner.make_run_record(spec, plugin, req.track, result)
            pipeline.evidence_store.save_run(run_record)
            pipeline.run_registry.register(run_record)
        except Exception as exc:  # noqa: BLE001 - report any execute failure to the client
            complete_attempt_with_retry(session_id, step=5, status=StepStatus.FAILED, error=str(exc))
            append_event(session_id, step=5, stage="execute", event="failed", detail=str(exc), level="error")
            raise

        manifest = complete_attempt_with_retry(
            session_id,
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

    job_id = job_manager.create_job(run, session_id=session_id, step=5, stage="execute")
    return {"job_id": job_id}
