"""Physical-mapping resolution over the paper-first schema (Phase C). Builds
`ImplementationResolution` from a `MethodSpec` + `MethodReview` -- NOT
wired into `src.pipeline` yet (see docs/methodspec-v2-plan.md section 9).

As of 2026-08-13, `RequiredField.source_table`/`source_column` (reviewed,
human-facing fields on `MethodSpec` itself -- see docs/decision-log.md same
date) are the PRIMARY source for `data.fields[]` concepts: if a field
already has a real (non-`other`) `source_table`/`source_column`, it's used
directly (already Pydantic-validated against the catalog at spec-construction
time -- no re-matching needed). Only fields left unset/`other`, plus any
`universe.filters[]`-only concept (which has no `RequiredField` of its own
to carry these fields), fall back to the older `DataDictionary.
normalize_fields()`/`normalize_fields_with_llm()` string-matchers -- kept for
backward compatibility with specs written before this field existed, and for
that filter-only case. An unresolved concept is left OUT of `concept_mapping`
(never silently guessed); this is what makes `ResolvedMethodSpec.is_ready`
correctly refuse to proceed (see `_all_concepts_mapped` in `method_spec.py`).
"""

from __future__ import annotations

from src.infra.data_layer import DataDictionary
from src.infra.models.method_spec import (
    ImplementationResolution,
    MethodReview,
    MethodSpec,
    SourceColumn,
)


def catalog_shim_fields(paper: MethodSpec, *, skip_concept_ids: set[str] = frozenset()) -> list[dict]:
    """Adapt `data.fields[]` + any `universe.filters[]` concept not already
    covered by `data.fields` into the dict shape `DataDictionary.
    normalize_fields[_with_llm]()` accepts -- the single place both
    `build_implementation_resolution` (below) and `review.py`'s catalog-
    mapping check build this concept set from, so they always run over the
    exact same fields. `skip_concept_ids` excludes concepts already resolved
    directly from `source_table`/`source_column` (see module docstring) --
    they don't need the string-matcher at all.
    """
    shim_fields = [
        {
            "field": f.concept_id,
            "source_detail": f.paper_source_hint,
            "concept": f.name_in_paper,
        }
        for f in paper.data.fields
        if f.concept_id not in skip_concept_ids
    ]
    # `universe.filters[].concept_id` (e.g. "exchange") is a SEPARATE concept
    # namespace from `data.fields` -- a filter concept isn't necessarily also
    # listed as a required data field, but `build_config`/the engine still
    # need it in `concept_mapping` to resolve the physical column. Add any
    # filter concept not already covered by data.fields (skip duplicates so
    # a concept_id used both ways isn't looked up twice).
    existing_field_ids = {f.concept_id for f in paper.data.fields}
    for filt in paper.universe.filters:
        if filt.concept_id not in existing_field_ids and filt.concept_id not in skip_concept_ids:
            shim_fields.append({"field": filt.concept_id})
            existing_field_ids.add(filt.concept_id)
    return shim_fields


def _mapping_from_source_fields(paper: MethodSpec) -> dict[str, SourceColumn]:
    """Concept -> `SourceColumn` for every `data.fields[]` entry that already
    has a real, non-`other` `source_table`/`source_column` set -- these were
    already Pydantic-validated (`RequiredField._source_column_belongs_to_
    source_table`) at spec-construction time, so no re-matching is needed."""
    out: dict[str, SourceColumn] = {}
    for f in paper.data.fields:
        table = f.source_table.value
        column = f.source_column.value
        if table is None or column is None or str(getattr(table, "value", table)) == "other":
            continue
        out[f.concept_id] = SourceColumn(source=table.value, column=column)
    return out


def build_implementation_resolution(
    paper: MethodSpec,
    review: MethodReview,
    data_dictionary: DataDictionary | None = None,
    returns_source: str = "us_equity_crsp",
    cz_acronym: str | None = None,
    llm_client=None,
) -> ImplementationResolution:
    """Resolve `paper.data.fields[].concept_id` (+ filter-only concepts) to
    physical `{source, column}` pairs.

    Primary path (2026-08-13): a field's own `source_table`/`source_column`,
    when set to a real (non-`other`) catalog entry -- see module docstring.
    Fallback path (unchanged from before): the shared data-catalog string
    matcher, for fields without these set yet and for filter-only concepts.
    `llm_client=None` (the default) keeps the fallback path fully
    deterministic. When a client is passed, any fallback concept the
    deterministic exact/substring matcher couldn't resolve gets one extra
    attempt via `DataDictionary.normalize_fields_with_llm()` -- every LLM
    pick is still hard-validated against the real catalog there, never
    trusted blindly -- and concepts resolved ONLY that way are recorded in
    `llm_matched_concepts` so a human can specifically re-check them.
    """
    data_dictionary = data_dictionary or DataDictionary()
    concept_mapping = _mapping_from_source_fields(paper)
    shim_fields = catalog_shim_fields(paper, skip_concept_ids=set(concept_mapping))

    deterministic = data_dictionary.normalize_fields(shim_fields)
    resolved = (
        data_dictionary.normalize_fields_with_llm(shim_fields, llm_client=llm_client)
        if llm_client is not None
        else deterministic
    )
    llm_matched_concepts = sorted(set(resolved) - set(deterministic))

    for concept_id, hit in resolved.items():
        concept_mapping[concept_id] = SourceColumn(source=hit["source"], column=hit["column"])

    return ImplementationResolution(
        factor_id=paper.factor_id,
        concept_mapping=concept_mapping,
        returns_source=returns_source,
        cz_acronym=cz_acronym,
        llm_matched_concepts=llm_matched_concepts,
    )
