"""Paper-first MethodSpec lifecycle endpoints: extract (LLM job) ->
`PaperMethodSpec`, deterministic review (sync) -> `MethodReview`, and
physical-field resolution (sync) -> `ImplementationResolution` /
`ResolvedMethodSpec`.

This is a parallel, additive workflow alongside `backend/routers/
methodspecs.py`'s v1 (flat `MethodSpec`) lifecycle -- see
docs/methodspec-v2-plan.md section 9. Nothing here touches the v1 dirs or
endpoints; artifacts are persisted under their own `paper_*` dirs (see
`backend/state.py`) so the two workflows never collide on filenames.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from backend.jobs import job_manager
from backend.routers.papers import extract_text_from_pdf_bytes
from backend.serialization import to_jsonable
from backend.state import (
    PAPER_DRAFTS_DIR,
    PAPER_RESOLUTIONS_DIR,
    PAPER_RESOLVED_DIR,
    PAPER_REVIEWS_DIR,
    build_llm_client,
    build_paper_extractor,
    pipeline,
)
from src.infra.models.paper_method_spec import (
    MethodReview,
    PaperMethodSpec,
    ResolvedMethodSpec,
)
from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
from src.steps.step2_reviewer.paper_review import review_paper_method_spec

router = APIRouter(prefix="/api/paper-methodspecs", tags=["paper-methodspecs"])

STAGE_DIRS = {
    "drafts": PAPER_DRAFTS_DIR,
    "reviews": PAPER_REVIEWS_DIR,
    "resolutions": PAPER_RESOLUTIONS_DIR,
    "resolved": PAPER_RESOLVED_DIR,
}


def _validate_paper_spec(raw: dict) -> PaperMethodSpec:
    try:
        return PaperMethodSpec.model_validate(raw)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid PaperMethodSpec: {exc}")


class ExtractRequest(BaseModel):
    document_id: str
    target_name: str
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None


def _extract_job(document_id: str, target_name: str, paper_text: str, llm_provider: str, llm_model: str | None, pdf_bytes: bytes | None = None):
    def run(log):
        log(f"Building {llm_provider} LLM client...")
        client = build_llm_client(llm_provider, llm_model)
        extractor = build_paper_extractor(client)
        log(f"Extracting PaperMethodSpec for '{target_name}' (document '{document_id}')...")
        result = extractor.extract(document_id=document_id, target_name=target_name, paper_text=paper_text, pdf_bytes=pdf_bytes)
        if result.spec is not None:
            out_path = PAPER_DRAFTS_DIR / f"{result.spec.factor_id}.paper.json"
            out_path.write_text(result.spec.model_dump_json(indent=2), encoding="utf-8")
            log(f"Saved draft spec to {out_path}")
        else:
            log(f"Extraction failed: {result.error}")
        return result

    return run


@router.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    job_id = job_manager.create_job(
        _extract_job(req.document_id, req.target_name, req.paper_text, req.llm_provider, req.llm_model)
    )
    return {"job_id": job_id}


@router.post("/extract-pdf")
async def extract_from_pdf(
    document_id: str = Form(...),
    target_name: str = Form(...),
    llm_provider: str = Form("codex"),
    llm_model: str | None = Form(None),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI's own required idiom for file-upload params
) -> dict:
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    paper_text = extract_text_from_pdf_bytes(pdf_bytes)
    job_id = job_manager.create_job(
        _extract_job(document_id, target_name, paper_text, llm_provider, llm_model, pdf_bytes=pdf_bytes)
    )
    return {"job_id": job_id}


class ReviewRequest(BaseModel):
    paper: dict


@router.post("/review")
def review(req: ReviewRequest) -> dict:
    paper = _validate_paper_spec(req.paper)
    result = review_paper_method_spec(paper)
    (PAPER_REVIEWS_DIR / f"{paper.factor_id}.review.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    return to_jsonable(result)


class ResolveRequest(BaseModel):
    paper: dict
    review: dict
    returns_source: str = "us_equity_crsp"
    cz_acronym: str | None = None


@router.post("/resolve")
def resolve(req: ResolveRequest) -> dict:
    paper = _validate_paper_spec(req.paper)
    try:
        review_obj = MethodReview.model_validate(req.review)
    except PydanticValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid MethodReview: {exc}")

    resolution = build_implementation_resolution(
        paper,
        review_obj,
        data_dictionary=pipeline.data_layer.dictionary,
        returns_source=req.returns_source,
        cz_acronym=req.cz_acronym,
    )
    (PAPER_RESOLUTIONS_DIR / f"{paper.factor_id}.resolution.json").write_text(
        resolution.model_dump_json(indent=2), encoding="utf-8"
    )

    resolved = ResolvedMethodSpec(paper=paper, review=review_obj, resolution=resolution)
    (PAPER_RESOLVED_DIR / f"{paper.factor_id}.resolved.json").write_text(
        resolved.model_dump_json(indent=2), encoding="utf-8"
    )

    return {"resolution": to_jsonable(resolution), "is_ready": resolved.is_ready}


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
