"""Dynamic `SourceName` enum -- generated from the live `DataSource` registry
(`src/infra/data_layer/sources.py`) at import time, so a new registered
source is automatically a new valid `RequiredField.source_table` choice with
zero manual Enum maintenance (see docs/decision-log.md 2026-08-13 entry:
`MethodSpec` now intentionally carries physical table/column choices,
reversing the earlier "paper-facts-only" boundary).

Deliberately importing `src.infra.data_layer.catalog` here (not the other
way round) -- `data_layer`/`sources.py` never import from `src.infra.models`
(verified before this change), so this is a new but non-circular, one-way
dependency. Every import of `method_spec.py` now transitively imports
pandas + runs `sources.py`'s in-memory `register()` calls (no file I/O) --
a small, accepted cost (see decision-log for the full trade-off writeup).
"""

from __future__ import annotations

from enum import Enum

from src.infra.data_layer import catalog


def _build_source_name_enum() -> type[Enum]:
    members = {name.upper(): name for name in catalog.DATA_CATALOG}
    members["OTHER"] = "other"
    return Enum("SourceName", members, type=str)  # type: ignore[return-value]


#: One member per currently-registered `DataSource` (e.g. `SourceName.COMPUSTAT_FUNDAMENTAL_ANNUAL
#: == "compustat_fundamental_annual"`), plus the `OTHER` escape hatch -- same pattern as
#: `WeightingScheme`/`ConstructionType`. Regenerated fresh on every import, so
#: it always reflects whatever sources are registered right now.
SourceName = _build_source_name_enum()
