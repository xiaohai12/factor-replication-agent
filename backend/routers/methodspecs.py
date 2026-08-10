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
from backend.sessions import append_event
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
    EvidenceStatus,
    MethodReview,
    MethodSpec,
    ResolvedMethodSpec,
)
from src.infra.models.schema_reference import build_schema_reference
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.review import (
    apply_human_status_overrides,
    apply_human_value_patches,
    review_method_spec,
    review_method_spec_with_llm,
)

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


def _extract_job(document_id: str, target_name: str, paper_text: str, llm_provider: str, llm_model: str | None, pdf_bytes: bytes | None = None):
    def run(log):
        # Cached under `document_id` the same way `/api/papers/upload` caches
        # it (`backend/routers/papers.py`) -- so a later `/review/llm` call
        # can fetch it back via `GET /api/papers/{document_id}` even after
        # the extraction job itself has expired (`JOB_TTL_SECONDS`) or the
        # frontend's sessionStorage was cleared.
        (PAPER_TEXT_CACHE_DIR / f"{document_id}.txt").write_text(paper_text, encoding="utf-8")
        log(f"Building {llm_provider} LLM client...")
        client = build_llm_client(llm_provider, llm_model)
        extractor = build_extractor(client)
        log(f"Extracting MethodSpec for '{target_name}' (document '{document_id}')...")
        result = extractor.extract(document_id=document_id, target_name=target_name, paper_text=paper_text, pdf_bytes=pdf_bytes)
        if result.spec is not None:
            out_path = UNREVIEWED_DIR / f"{result.spec.factor_id}.paper.json"
            out_path.write_text(result.spec.model_dump_json(indent=2), encoding="utf-8")
            log(f"Saved draft spec to {out_path}")
        else:
            log(f"Extraction failed: {result.error}")
        # `paper_text` is stashed alongside the extraction result (not part
        # of `ExtractionResult` itself) purely so the session-workflow
        # frontend can persist it and later pass it to `/review/llm`, which
        # needs the original paper text to re-check evidence status.
        return {
            "spec": result.spec,
            "error": result.error,
            "raw_llm_output": result.raw_llm_output,
            "token_usage": result.token_usage,
            "paper_text": paper_text,
        }

    return run


@router.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    job_id = job_manager.create_job(
        _extract_job(req.document_id, req.target_name, req.paper_text, req.llm_provider, req.llm_model),
        session_id=req.session_id,
        step=1,
        stage="extract",
    )
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
        _extract_job(document_id, target_name, paper_text, llm_provider, llm_model, pdf_bytes=pdf_bytes),
        session_id=session_id,
        step=1,
        stage="extract",
    )
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
        blocked = [f.field_path for f in result.findings if f.disposition == "blocked"]
        level = "error" if blocked else "info"
        detail = f"{len(result.findings)} finding(s), blocked: {blocked}" if blocked else f"{len(result.findings)} finding(s), none blocked"
        append_event(req.session_id, step=2, stage="review", event="completed", detail=detail, level=level)
    return to_jsonable(result)


class ReviewLlmRequest(BaseModel):
    paper: dict
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None
    session_id: str | None = None


def _review_llm_job(paper_dict: dict, paper_text: str, llm_provider: str, llm_model: str | None):
    def run(log):
        paper = _validate_paper_spec(paper_dict)
        log(f"Building {llm_provider} LLM client for LLM-assisted review...")
        client = build_llm_client(llm_provider, llm_model)
        log(f"Re-reading paper text to double-check evidence status for '{paper.factor_id}'...")
        result, raw_llm_output = review_method_spec_with_llm(paper, paper_text, client)
        (REVIEWED_DIR / f"{paper.factor_id}.review.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        blocked = [f.field_path for f in result.findings if f.disposition == "blocked"]
        log(f"LLM-assisted review done: {len(result.findings)} finding(s), blocked: {blocked}")
        return {"review": to_jsonable(result), "raw_llm_output": raw_llm_output}

    return run


@router.post("/review/llm")
async def review_llm(req: ReviewLlmRequest) -> dict:
    """LLM-assisted counterpart to `/review` -- async job (like `/extract`)
    since it makes an LLM call over the full paper text instead of a cheap
    in-process rule pass. Wraps `review_method_spec_with_llm`, which still
    computes `disposition` deterministically; the LLM only proposes
    `EvidenceStatus` re-assessments and new human-confirmation findings.
    """
    _validate_paper_spec(req.paper)  # fail fast with a 422 before spawning the job
    job_id = job_manager.create_job(
        _review_llm_job(req.paper, req.paper_text, req.llm_provider, req.llm_model),
        session_id=req.session_id,
        step=2,
        stage="review_llm",
    )
    return {"job_id": job_id}


class ReviewOverrideRequest(BaseModel):
    paper: dict
    overrides: dict[str, str]  # field_path -> evidence_status
    session_id: str | None = None


@router.post("/review/override")
def review_override(req: ReviewOverrideRequest) -> dict:
    """Manual-resolution path for D2 (evidence-status) findings: a human
    directly asserts a corrected `EvidenceStatus` per field (e.g. "the paper
    does state this clearly in Section 3") instead of going through the LLM
    pass. Sync, no LLM call -- same deterministic `DISPOSITION_MATRIX` as
    `/review` decides the outcome.
    """
    paper = _validate_paper_spec(req.paper)
    try:
        status_overrides = {field: EvidenceStatus(status) for field, status in req.overrides.items()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid evidence_status: {exc}")

    result = apply_human_status_overrides(paper, status_overrides)
    (REVIEWED_DIR / f"{paper.factor_id}.review.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    if req.session_id:
        blocked = [f.field_path for f in result.findings if f.disposition == "blocked"]
        detail = f"human override applied, {len(result.findings)} finding(s), blocked: {blocked}"
        append_event(
            req.session_id, step=2, stage="review", event="completed", detail=detail,
            level="error" if blocked else "info",
        )
    return to_jsonable(result)


class PatchValueRequest(BaseModel):
    paper: dict
    patches: dict[str, Any]  # field_path -> corrected value
    reason: str = ""
    session_id: str | None = None


@router.post("/patch-value")
def patch_value(req: PatchValueRequest) -> dict:
    """A human directly corrects the extracted VALUE of one or more
    high-impact fields (not just its evidence status -- see `/review/
    override` for that). Produces a NEW draft `MethodSpec` (saved over the
    unreviewed draft, same as re-extraction would) with each patched field's
    `status` set to `clear` and an evidence citation recording the human
    correction. The caller should re-run `/review` (and `/resolve`) against
    the returned spec -- there's no automatic staleness detection forcing
    that (docs/decision-log.md 2026-08-09).
    """
    paper = _validate_paper_spec(req.paper)
    try:
        patched = apply_human_value_patches(paper, req.patches, req.reason)
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
