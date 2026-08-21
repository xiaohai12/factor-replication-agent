"""Read-only Data Catalog reference endpoint: every registered signal source,
link table, and returns universe -- the single source of truth
`src/infra/data_layer/catalog.py`/`sources.py` already maintain, exposed for
the frontend's Data Catalog page (plan.md; user request 2026-08-06).
"""

from __future__ import annotations

from fastapi import APIRouter

from src.infra.data_layer import catalog

router = APIRouter(prefix="/api/data-catalog", tags=["data-catalog"])


@router.get("")
def get_data_catalog() -> dict:
    """Registered signal sources (join metadata + physical/concept columns),
    link tables, and returns universes -- sourced entirely from
    `catalog.DATA_CATALOG`/`LINK_TABLES`/`RETURNS_UNIVERSES`, never a
    hand-duplicated list, so this page can't drift from what the data loader
    actually resolves at runtime."""
    return {
        "signal_sources": {
            name: {
                "join": entry["join"],
                "physical_columns": sorted(entry["physical_columns"]),
                "columns": entry["columns"],
                "description": entry["description"],
                "column_descriptions": entry["column_descriptions"],
            }
            for name, entry in catalog.DATA_CATALOG.items()
        },
        "link_tables": catalog.LINK_TABLES,
        "returns_universes": catalog.RETURNS_UNIVERSES,
        "default_returns_universe": catalog.DEFAULT_RETURNS_UNIVERSE,
    }
