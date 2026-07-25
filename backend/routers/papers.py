"""Paper upload + text extraction. Mirrors app.py's
`_extract_text_from_pdf_bytes` / `_save_paper_text_cache` helpers so both the
old Streamlit app and the new backend read/write the same
`data/paper_text_cache/{name}.txt` cache convention.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from backend.state import PAPER_TEXT_CACHE_DIR

router = APIRouter(prefix="/api/papers", tags=["papers"])


class PaperUploadResponse(BaseModel):
    paper_id: str
    paper_text: str
    text_length: int


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(file: UploadFile) -> PaperUploadResponse:
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    paper_text = _extract_text_from_pdf_bytes(pdf_bytes)
    paper_id = Path(file.filename or "uploaded_paper.pdf").stem
    cache_path = PAPER_TEXT_CACHE_DIR / f"{paper_id}.txt"
    cache_path.write_text(paper_text, encoding="utf-8")
    return PaperUploadResponse(paper_id=paper_id, paper_text=paper_text, text_length=len(paper_text))


@router.get("")
def list_papers() -> list[str]:
    """Paper ids (cached text stems) already available for extraction."""
    return sorted(p.stem for p in PAPER_TEXT_CACHE_DIR.glob("*.txt"))


@router.get("/{paper_id}")
def get_paper_text(paper_id: str) -> dict:
    cache_path = PAPER_TEXT_CACHE_DIR / f"{paper_id}.txt"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail=f"No cached paper text for '{paper_id}'")
    text = cache_path.read_text(encoding="utf-8")
    return {"paper_id": paper_id, "paper_text": text, "text_length": len(text)}
