"""MethodSpec lifecycle endpoints: extract (LLM job), rules-based review
(sync), LLM review (job), and human resolution of blocked/ambiguous fields
(sync). File layout mirrors the existing `runs/method_specs/{stage}/`
convention used by app.py and scripts/resolve_review_blocks.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.routers.papers import extract_text_from_pdf_bytes
from backend.serialization import to_jsonable
from backend.state import (
    RESOLUTIONS_DIR,
    RESOLVED_DIR,
    REVIEWED_DIR,
    UNREVIEWED_DIR,
    build_extractor,
    build_llm_client,
    build_review_gate,
    pipeline,
)
from src.infra.models.method_spec import MethodSpec
from src.steps.step2_reviewer.resolution import apply_decisions

router = APIRouter(prefix="/api/methodspecs", tags=["methodspecs"])

STAGE_DIRS = {
    "unreviewed": UNREVIEWED_DIR,
    "reviewed": REVIEWED_DIR,
    "resolved": RESOLVED_DIR,
}


class ExtractRequest(BaseModel):
    factor_id: str
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None


def _extract_job(factor_id: str, paper_text: str, llm_provider: str, llm_model: str | None, pdf_bytes: bytes | None = None):
    """Shared job body for the pasted-text and PDF-upload extract endpoints
    -- mirrors `backend/routers/sessions.py`'s `_run_extraction` (same
    `pdf_bytes` pass-through rationale: `SemanticExtractor.extract()`
    already accepts it, used when the built LLM client supports native PDF
    attachments; `paper_text` is still required as the fallback)."""

    def run(log):
        log(f"Building {llm_provider} LLM client...")
        client = build_llm_client(llm_provider, llm_model)
        extractor = build_extractor(client)
        log(f"Extracting MethodSpec for '{factor_id}'...")
        result = extractor.extract(factor_id=factor_id, paper_text=paper_text, pdf_bytes=pdf_bytes)
        if result.spec is not None:
            out_path = UNREVIEWED_DIR / f"{factor_id}.methodspec.json"
            out_path.write_text(result.spec.model_dump_json(indent=2), encoding="utf-8")
            log(f"Saved draft spec to {out_path}")
        else:
            log(f"Extraction failed: {result.error}")
        return result

    return run


@router.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    job_id = job_manager.create_job(_extract_job(req.factor_id, req.paper_text, req.llm_provider, req.llm_model))
    return {"job_id": job_id}


@router.post("/extract-pdf")
async def extract_from_pdf(
    factor_id: str = Form(...),
    llm_provider: str = Form("codex"),
    llm_model: str | None = Form(None),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI's own required idiom for file-upload params
) -> dict:
    """Same extraction job as `extract`, but takes a PDF upload directly
    instead of requiring pasted text first (mirrors
    `backend/routers/sessions.py`'s `extract_step1_from_pdf`)."""
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    paper_text = extract_text_from_pdf_bytes(pdf_bytes)
    job_id = job_manager.create_job(_extract_job(factor_id, paper_text, llm_provider, llm_model, pdf_bytes=pdf_bytes))
    return {"job_id": job_id}


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
    matches = sorted(directory.glob(f"{factor_id}.*methodspec.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"No spec '{factor_id}' in stage '{stage}'")
    return json.loads(matches[0].read_text(encoding="utf-8"))


class ReviewRequest(BaseModel):
    spec: dict


@router.post("/review")
def review(req: ReviewRequest) -> dict:
    spec = MethodSpec.model_validate(req.spec)
    result = pipeline.review_gate.review(spec)
    report = to_jsonable(result)
    report_path = REVIEWED_DIR / f"{spec.factor_id}.review_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


class ReviewLLMRequest(BaseModel):
    spec: dict
    paper_text: str
    llm_provider: str = "codex"
    llm_model: str | None = None


@router.post("/review/llm")
async def review_llm(req: ReviewLLMRequest) -> dict:
    def run(log):
        spec = MethodSpec.model_validate(req.spec)
        log(f"Building {req.llm_provider} LLM client...")
        client = build_llm_client(req.llm_provider, req.llm_model)
        gate = build_review_gate(client)
        log("Running LLM-backed review against the source paper...")
        result, raw_llm_output = gate.review_with_llm(spec, req.paper_text)
        return {"review_result": result, "raw_llm_output": raw_llm_output}

    job_id = job_manager.create_job(run)
    return {"job_id": job_id}


class ResolveRequest(BaseModel):
    spec: dict
    decisions: list[dict]
    reviewer: str = "human"


@router.post("/resolve")
def resolve(req: ResolveRequest) -> dict:
    resolved_data = json.loads(json.dumps(req.spec))
    apply_decisions(resolved_data, req.decisions)
    # Raises 422-worthy validation error if decisions produced an invalid spec.
    MethodSpec.model_validate(resolved_data)

    factor_id = resolved_data.get("factor_id", "unknown_factor")
    resolution_payload = {
        "factor_id": factor_id,
        "reviewer": req.reviewer,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decisions": req.decisions,
    }
    (RESOLUTIONS_DIR / f"{factor_id}.resolution.json").write_text(
        json.dumps(resolution_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESOLVED_DIR / f"{factor_id}.resolved.methodspec.json").write_text(
        json.dumps(resolved_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return resolved_data
