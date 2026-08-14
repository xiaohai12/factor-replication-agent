"""Tests for `src/infra/models/schema_reference.py` -- the auto-generated
field-reference payload `GET /api/methodspecs/schema` serves to
`SchemaReferencePage.tsx`."""

from __future__ import annotations

from src.infra.models.schema_reference import build_schema_reference


def test_top_level_pipeline_fields_excluded():
    ref = build_schema_reference()
    assert "factor_id" not in ref["fields"]
    assert "schema_version" not in ref["fields"]


def test_json_schema_present_and_real():
    ref = build_schema_reference()
    assert "properties" in ref["json_schema"]
    assert "portfolio" in ref["json_schema"]["properties"]


def test_sourced_enum_field_shows_allowed_values_not_sub_fields():
    """portfolio.weighting is SourcedValue[WeightingScheme] -- must be
    unwrapped to a leaf entry with allowed_values, not treated as a nested
    composite object (the SourcedValue[T] parametrized-generic detection
    bug this test guards against)."""
    ref = build_schema_reference()
    entry = ref["fields"]["portfolio.weighting"]
    assert entry["allowed_values"] == ["vw", "ew", "other"]
    assert entry["sub_fields"] is None
    assert entry["engine_consumed"] is True


def test_sourced_str_field_has_no_allowed_values():
    ref = build_schema_reference()
    entry = ref["fields"]["signal.definition"]
    assert entry["allowed_values"] is None
    assert entry["sub_fields"] is None


def test_composite_field_lists_its_children_as_sub_fields():
    ref = build_schema_reference()
    entry = ref["fields"]["paper"]
    assert entry["sub_fields"] is not None
    assert "paper.citation" in entry["sub_fields"]
    assert "paper.citation" in ref["fields"]


def test_list_of_model_field_has_list_item_fields_and_recursed_paths():
    """`list_item_fields` still lists the item model's direct field names
    for display, but the item model's own fields are ALSO recursed into
    `out` (under the same un-indexed path the frontend looks up after
    stripping `[i]`) -- otherwise a nested list-item field like
    `portfolio.sorts[i].breakpoints.basis` (a real 3-value enum) would never
    get an entry and the review page would silently fall back to a free-text
    box instead of a dropdown."""
    ref = build_schema_reference()
    entry = ref["fields"]["data.fields"]
    assert entry["list_item_fields"] == [
        "concept_id",
        "name_in_paper",
        "description",
        "paper_source_hint",
        "roles",
        "evidence",
        "source_table",
        "source_column",
    ]
    assert "data.fields.concept_id" in ref["fields"]


def test_list_item_nested_enum_field_gets_allowed_values():
    ref = build_schema_reference()
    entry = ref["fields"]["portfolio.sorts.breakpoints.basis"]
    assert entry["allowed_values"] == ["full_sample", "nyse", "other"]


def test_list_of_sourced_value_field_has_value_evidence_status_item_fields():
    ref = build_schema_reference()
    entry = ref["fields"]["data.sources"]
    assert entry["list_item_fields"] == ["value", "evidence", "status"]


def test_every_field_origin_is_llm():
    ref = build_schema_reference()
    assert all(entry["origin"] == "llm" for entry in ref["fields"].values())
