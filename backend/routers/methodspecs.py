"""Paper-first MethodSpec lifecycle endpoints: extract (LLM job) ->
`MethodSpec`, deterministic review (sync) -> `MethodReview`, and
physical-field resolution (sync) -> `ImplementationResolution` /
`ResolvedMethodSpec`.

This is the ONLY MethodSpec lifecycle in the repo -- the older flat v1
`MethodSpec` model and its own `backend/routers/methodspecs.py` were fully
deleted 2026-08-07 (see docs/decision-log.md). Artifacts are persisted under
`runs/method_specs/{unreviewed,reviewed,resolutions,resolved}/` (see
`backend/state.py`).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.jobs import job_manager
from backend.routers.papers import extract_text_from_pdf_bytes
from backend.serialization import to_jsonable
from backend.sessions import append_event, complete_attempt_with_retry, start_attempt_with_retry
from backend.state import (
    PAPER_TEXT_CACHE_DIR,
    RESOLUTIONS_DIR,
    RESOLVED_DIR,
    REVIEWED_DIR,
    UNREVIEWED_DIR,
    build_extractor,
    build_llm_client,
    pipeline,
)
from src.infra.models.method_spec import (
    RETURNS_PANEL_NATIVE_COLUMNS,
    Disposition,
    Finding,
    MethodReview,
    MethodSpec,
    ResolvedMethodSpec,
)
from src.infra.models.schema_reference import build_schema_reference
from src.infra.models.session import StepStatus
from src.steps.step1_extractor.extractor import persist_raw_spec
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.review import apply_value_patches, review_method_spec
from src.steps.step2_reviewer.spec_build import build_reviewed_method_spec

router = APIRouter(prefix="/api/methodspecs", tags=["methodspecs"])

STAGE_DIRS = {
    "drafts": UNREVIEWED_DIR,
    "reviews": REVIEWED_DIR,
    "resolutions": RESOLUTIONS_DIR,
    "resolved": RESOLVED_DIR,
}




def _validate_paper_spec(raw: dict) -> MethodSpec:
    try:
        return MethodSpec.model_validate(raw)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MethodSpec: {exc}")


class ExtractRequest(BaseModel):
    document_id: str
    target_name: str
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None
    session_id: str | None = None


def _extract_job(
    document_id: str, target_name: str, paper_text: str, llm_provider: str, llm_model: str | None,
    pdf_bytes: bytes | None = None, session_id: str | None = None,
):
    """Step1 only -- a single LLM call, no validation, no Step2 review loop
    (see `_review_loop_job` below, kicked off as its own job once this one
    completes). Splitting these into two jobs means Step1 can show
    "succeeded" the moment extraction itself returns, instead of only after
    the whole (much slower) review loop also finishes.

    When `session_id` is given, records this job's outcome as a real step-1
    attempt via `complete_attempt_with_retry` -- mirrors steps 3-5
    (`backend/routers/sessions.py`), which previously left steps 1/2
    invisible to the session's own progress tracking (`session.json` stayed
    `attempts: []` for both even after real extraction/review work ran),
    making a session that only got through Step1/2 look indistinguishable
    from one that was never touched at all in any session list.
    """
    def run(log):
        # Cached under `document_id` the same way `/api/papers/upload` caches
        # it (`backend/routers/papers.py`) -- so later calls can fetch it
        # back via `GET /api/papers/{document_id}` even after the extraction
        # job itself has expired (`JOB_TTL_SECONDS`) or the frontend's
        # sessionStorage was cleared.
        (PAPER_TEXT_CACHE_DIR / f"{document_id}.txt").write_text(paper_text, encoding="utf-8")
        log(f"Cached paper text for document '{document_id}'.")
        log(f"Building {llm_provider} LLM client...")
        client = build_llm_client(llm_provider, llm_model)
        extractor = build_extractor(client)
        log(f"Extracting raw MethodSpec JSON for '{target_name}' (document '{document_id}')...")
        result = extractor.extract(document_id=document_id, target_name=target_name, paper_text=paper_text, pdf_bytes=pdf_bytes)
        if result.raw_spec is None:
            log(f"Extraction failed: {result.error}")
            if session_id:
                complete_attempt_with_retry(session_id, step=1, status=StepStatus.FAILED, error=result.error)
            return {
                "raw_spec": None,
                "error": result.error,
                "token_usage": result.token_usage,
                "paper_text": paper_text,
                "tool_results": result.tool_results,
            }
        log(f"Extraction call succeeded (token usage: {result.token_usage}).")

        raw_path = persist_raw_spec(document_id, target_name, result.raw_spec)
        log(f"Persisted raw Step1 spec to {raw_path}")
        if session_id:
            complete_attempt_with_retry(
                session_id, step=1, status=StepStatus.SUCCESS, output_refs={"raw_spec_ref": str(raw_path)}
            )
        return {
            "raw_spec": result.raw_spec,
            "error": None,
            "token_usage": result.token_usage,
            "paper_text": paper_text,
            "tool_results": result.tool_results,
        }

    return run


class ReviewLoopRequest(BaseModel):
    raw_spec: dict
    document_id: str
    target_name: str
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None
    session_id: str | None = None


def _review_loop_job(
    raw_spec: dict, document_id: str, target_name: str, paper_text: str, llm_provider: str, llm_model: str | None,
    session_id: str | None = None,
):
    """Step2's LLM review loop, run as its own job so its progress/log is
    scoped to the Step2 page (see docstring on `_extract_job` above).

    Recorded as a real step-2 attempt (SUCCESS) whenever `outcome.spec` is
    set -- which happens whenever the final `model_validate()` after all
    `MAX_REVIEW_ROUNDS` passes, REGARDLESS of whether the loop's own
    round-to-round convergence check (`validate_passed and not diff`) ever
    tripped early. A spec that only ran the full round budget without an
    early exit is not a failure -- `build_reviewed_method_spec` already
    treats it as good enough to review (see its docstring); this attempt
    recording must not re-impose a stricter "must have converged early" bar
    on top of that.
    """
    def run(log):
        log(f"Building {llm_provider} LLM client...")
        client = build_llm_client(llm_provider, llm_model)
        log("Running Step2 review loop (validate <-> LLM review)...")
        outcome = build_reviewed_method_spec(
            raw_spec, document_id, target_name, paper_text, client, log=log
        )
        if outcome.spec is not None:
            out_path = UNREVIEWED_DIR / f"{outcome.spec.factor_id}.paper.json"
            out_path.write_text(outcome.spec.model_dump_json(indent=2), encoding="utf-8")
            log(f"Saved reviewed draft spec to {out_path}")
            if session_id:
                complete_attempt_with_retry(
                    session_id, step=2, status=StepStatus.SUCCESS,
                    output_refs={"unreviewed_ref": str(out_path)},
                )
        else:
            log(f"Review loop did not converge: {outcome.error}")
            if session_id:
                complete_attempt_with_retry(session_id, step=2, status=StepStatus.FAILED, error=outcome.error)
        return {
            "spec": outcome.spec,
            "error": outcome.error,
            "review": outcome.review,
            "history": outcome.history,
            "total_diff": outcome.total_diff,
            "llm_notes": outcome.llm_notes,
            "tool_results": outcome.tool_results,
        }

    return run


@router.post("/review-loop")
async def review_loop(req: ReviewLoopRequest) -> dict:
    job_id = job_manager.create_job(
        _review_loop_job(
            req.raw_spec, req.document_id, req.target_name, req.paper_text, req.llm_provider, req.llm_model,
            session_id=req.session_id,
        ),
        session_id=req.session_id,
        step=2,
        stage="review_loop",
    )
    if req.session_id:
        start_attempt_with_retry(req.session_id, step=2, job_id=job_id)
    return {"job_id": job_id}


@router.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    job_id = job_manager.create_job(
        _extract_job(req.document_id, req.target_name, req.paper_text, req.llm_provider, req.llm_model, session_id=req.session_id),
        session_id=req.session_id,
        step=1,
        stage="extract",
    )
    if req.session_id:
        start_attempt_with_retry(req.session_id, step=1, job_id=job_id)
    return {"job_id": job_id}


@router.post("/extract-pdf")
async def extract_from_pdf(
    document_id: str = Form(...),
    target_name: str = Form(...),
    llm_provider: str = Form("codex"),
    llm_model: str | None = Form(None),
    session_id: str | None = Form(None),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI's own required idiom for file-upload params
) -> dict:
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    paper_text = extract_text_from_pdf_bytes(pdf_bytes)
    job_id = job_manager.create_job(
        _extract_job(document_id, target_name, paper_text, llm_provider, llm_model, pdf_bytes=pdf_bytes, session_id=session_id),
        session_id=session_id,
        step=1,
        stage="extract",
    )
    if session_id:
        start_attempt_with_retry(session_id, step=1, job_id=job_id)
    return {"job_id": job_id}


class ReviewRequest(BaseModel):
    paper: dict
    session_id: str | None = None


@router.post("/review")
def review(req: ReviewRequest) -> dict:
    paper = _validate_paper_spec(req.paper)
    if req.session_id:
        append_event(req.session_id, step=2, stage="review", event="start", detail=f"reviewing {paper.factor_id}")
    result = review_method_spec(paper)
    (REVIEWED_DIR / f"{paper.factor_id}.review.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    if req.session_id:
        needs_human = [f.field_path for f in result.findings if f.disposition == "needs_human_confirmation"]
        level = "error" if needs_human else "info"
        detail = (
            f"{len(result.findings)} finding(s), needs human confirmation: {needs_human}"
            if needs_human
            else f"{len(result.findings)} finding(s), none needing human confirmation"
        )
        append_event(req.session_id, step=2, stage="review", event="completed", detail=detail, level=level)
    return to_jsonable(result)


class PatchValueRequest(BaseModel):
    paper: dict
    patches: dict[str, Any]  # field_path -> corrected value
    reason: str = ""
    session_id: str | None = None
    #: field_path -> paper's literal wording, only used for a patch that
    #: sets that same field_path's value to the enum's "other" member (see
    #: `apply_value_patches`).
    unsupported_values: dict[str, str] = {}


@router.post("/patch-value")
def patch_value(req: PatchValueRequest) -> dict:
    """A human directly corrects the extracted VALUE of one or more
    high-impact fields. Produces a NEW draft `MethodSpec` (saved over the
    unreviewed draft, same as re-extraction would) with each patched field's
    `status` set to `clear` and an evidence citation recording the human
    correction. The caller should re-run `/review` (and `/resolve`) against
    the returned spec -- there's no automatic staleness detection forcing
    that (docs/decision-log.md 2026-08-09).
    """
    paper = _validate_paper_spec(req.paper)
    try:
        patched = apply_value_patches(paper, req.patches, req.reason, source="human", unsupported_values=req.unsupported_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    out_path = UNREVIEWED_DIR / f"{patched.factor_id}.paper.json"
    out_path.write_text(patched.model_dump_json(indent=2), encoding="utf-8")
    if req.session_id:
        append_event(
            req.session_id, step=2, stage="review", event="completed",
            detail=f"human value patch applied to {sorted(req.patches)}, re-run review before resolving",
            level="info",
        )
    return to_jsonable(patched)


def _unsupported_universe_filter_findings(
    paper: MethodSpec, resolution, resolved: ResolvedMethodSpec
) -> list[Finding]:
    """`ResolvedMethodSpec.unsupported_universe_filters()` only returns a bare
    concept_id list, computed at RESOLVE time (needs `resolution.
    concept_mapping`, unavailable at Step2 `review_method_spec(paper)` time --
    see docs/resolve-diagnostics-gaps.md problem 1). Reuses the same
    `Finding`/`Disposition` model and UI rendering language as the Step2
    review findings, so a human sees this the same way, just attached to the
    resolve result instead.
    """
    unsupported = set(resolved.unsupported_universe_filters())
    findings = []
    for i, filt in enumerate(paper.universe.filters):
        if filt.concept_id not in unsupported:
            continue
        column = resolution.concept_mapping[filt.concept_id].column
        findings.append(
            Finding(
                field_path=f"universe.filters[{i}].concept_id",
                kind="unsupported",
                reason=(
                    f"resolves to column {column!r}, which isn't on the engine's returns "
                    f"panel (native columns: {sorted(RETURNS_PANEL_NATIVE_COLUMNS)}) and isn't "
                    "registered in the data catalog for its source either, so the generated "
                    "script has no way to join it in. Register this column in the catalog "
                    "(src/infra/data_layer/sources.py), or mark this filter accepted_unapplied "
                    "with a reason."
                ),
                empirical_impact="high",
                disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                paper_value=filt.concept_id,
            )
        )
    return findings


class ResolveRequest(BaseModel):
    paper: dict
    review: dict
    returns_source: str = "us_equity_crsp"
    cz_acronym: str | None = None
    session_id: str | None = None
    #: Opt-in: when set, concepts the deterministic catalog matcher can't
    #: resolve get one extra attempt via `DataDictionary.
    #: normalize_fields_with_llm()` before being left unmapped. None (the
    #: default) keeps `/resolve` fully deterministic, unchanged from before.
    llm_provider: str | None = None
    llm_model: str | None = None


@router.post("/resolve")
def resolve(req: ResolveRequest) -> dict:
    paper = _validate_paper_spec(req.paper)
    try:
        review_obj = MethodReview.model_validate(req.review)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MethodReview: {exc}")

    if req.session_id:
        append_event(req.session_id, step=2, stage="resolve", event="start", detail=f"resolving {paper.factor_id}")

    llm_client = build_llm_client(req.llm_provider, req.llm_model) if req.llm_provider else None
    resolution = build_implementation_resolution(
        paper,
        review_obj,
        data_dictionary=pipeline.data_layer.dictionary,
        returns_source=req.returns_source,
        cz_acronym=req.cz_acronym,
        llm_client=llm_client,
    )
    (RESOLUTIONS_DIR / f"{paper.factor_id}.resolution.json").write_text(
        resolution.model_dump_json(indent=2), encoding="utf-8"
    )

    resolved = ResolvedMethodSpec(paper=paper, review=review_obj, resolution=resolution)
    (RESOLVED_DIR / f"{paper.factor_id}.resolved.json").write_text(
        resolved.model_dump_json(indent=2), encoding="utf-8"
    )

    unmapped = resolved.unmapped_concepts()
    resolution_findings = _unsupported_universe_filter_findings(paper, resolution, resolved)
    if req.session_id:
        detail = f"is_ready={resolved.is_ready}" + (f", unmapped concepts: {unmapped}" if unmapped else "")
        if resolution.llm_matched_concepts:
            detail += f", LLM-matched: {resolution.llm_matched_concepts}"
        append_event(
            req.session_id, step=2, stage="resolve", event="completed", detail=detail,
            level="info" if resolved.is_ready else "error",
        )

    return {
        "resolution": to_jsonable(resolution),
        "is_ready": resolved.is_ready,
        "unmapped_concepts": unmapped,
        "llm_matched_concepts": resolution.llm_matched_concepts,
        "resolution_findings": [to_jsonable(f) for f in resolution_findings],
    }


@router.get("/schema")
def get_schema() -> dict:
    """Field-reference payload for `SchemaReferencePage.tsx`, generated
    directly from the `MethodSpec` model (see `schema_reference.py`) --
    registered BEFORE `/{stage}` below so the literal path "schema" isn't
    swallowed by that catch-all.
    """
    return build_schema_reference()


@router.get("/{stage}")
def list_specs(stage: str) -> list[str]:
    directory = STAGE_DIRS.get(stage)
    if directory is None:
        raise HTTPException(status_code=404, detail=f"Unknown stage '{stage}'")
    return sorted({p.name.split(".")[0] for p in directory.glob("*.json")})


@router.get("/{stage}/{factor_id}")
def load_spec(stage: str, factor_id: str) -> dict:
    directory = STAGE_DIRS.get(stage)
    if directory is None:
        raise HTTPException(status_code=404, detail=f"Unknown stage '{stage}'")
    matches = sorted(directory.glob(f"{factor_id}.*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"No spec '{factor_id}' in stage '{stage}'")
    return json.loads(matches[0].read_text(encoding="utf-8"))
