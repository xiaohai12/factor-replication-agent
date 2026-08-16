"""Test for the static factor_id -> C&Z acronym manifest
(docs/step6.md gap #1). Trivial by design -- this is a hand-curated dict,
not derived logic; the test just locks its current confirmed contents."""

from __future__ import annotations

from src.infra.reference.manifest import CZ_FACTOR_ACRONYM_MANIFEST


def test_asset_growth_is_mapped():
    assert CZ_FACTOR_ACRONYM_MANIFEST["AssetGrowth"] == "AssetGrowth"
