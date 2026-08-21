"""Read-only C&Z factor manifest for the step6 UI's C_cz preview dropdown
(docs/step6.md gap #1) -- a static list, not session-scoped."""

from __future__ import annotations

from fastapi import APIRouter

from src.infra.reference.manifest import CZ_FACTOR_ACRONYM_MANIFEST

router = APIRouter(prefix="/api/reference", tags=["reference"])


@router.get("/cz-factors")
def list_cz_factors() -> dict:
    return {
        "factors": [
            {"factor_id": factor_id, "acronym": acronym}
            for factor_id, acronym in CZ_FACTOR_ACRONYM_MANIFEST.items()
        ]
    }
