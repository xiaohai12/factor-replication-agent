"""Isolated extraction-evaluation endpoint (Phase 3.3 of the session-centric
UI redesign plan) -- deliberately has NO `session_id` parameter at all and
never touches a session's own extractor call. A normal session's step1
`SemanticExtractor.extract()` must never be handed the evaluation reference
data (`data/test_method_specs_human_labeled/`, `data/osap/SignalDoc.csv`) --
AGENTS.md hard constraint. This endpoint only SCORES an already-produced
MethodSpec (however the caller got it) against a fixed, server-side curated
reference dataset the caller cannot influence.

Exposes exactly ONE protocol today (`human_labeled_v1`, reusing
`scripts/run_extraction_eval.py`'s comparison logic against
`data/test_method_specs_human_labeled/`) rather than mechanically merging it
with the OTHER existing scorer (`src/evaluation/helpers.py`'s
SignalDoc-based one) -- those two differ in reference SOURCE and matching
rules, not just field list, so merging them without first defining a shared
protocol would risk silently changing either one's numbers (see
docs/decision-log.md 2026-08-04 review, point 7). `signaldoc_v1` is left as
an explicit, documented gap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scripts.run_extraction_eval import (
    GT_DIR,
    compare_specs,
    compute_metrics,
    load_curated_reference,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

SUPPORTED_PROTOCOLS = ("human_labeled_v1",)


class ExtractionEvalRequest(BaseModel):
    factor_id: str
    spec: dict
    protocol: str = "human_labeled_v1"


@router.post("/extraction")
def evaluate_extraction(req: ExtractionEvalRequest) -> dict:
    if req.protocol not in SUPPORTED_PROTOCOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported protocol {req.protocol!r}; supported: {SUPPORTED_PROTOCOLS}",
        )
    reference = load_curated_reference(req.factor_id)
    if not reference:
        raise HTTPException(
            status_code=404,
            detail=f"No curated human-labeled reference for factor_id '{req.factor_id}' "
            f"(expected {GT_DIR / f'{req.factor_id}.methodspec.json'})",
        )
    comparisons = compare_specs(req.spec, reference)
    metrics = compute_metrics(comparisons)
    return {
        "factor_id": req.factor_id,
        "protocol": req.protocol,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "field_details": comparisons,
    }
