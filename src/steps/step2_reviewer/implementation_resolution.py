"""Physical-mapping resolution over the paper-first schema (Phase C). Builds
`ImplementationResolution` from a `MethodSpec` + `MethodReview` -- NOT
wired into `src.pipeline` yet (see docs/methodspec-v2-plan.md section 9).

Reuses the existing `DataDictionary.normalize_fields()`/`normalize_fields_
with_llm()` catalog matchers (`src/infra/data_layer/__init__.py`) rather
than reimplementing concept -> physical-column matching -- this module only
adapts `RequiredField`'s shape into the dict form those matchers already
accept. An unresolved `signal_input` concept is left OUT of
`concept_mapping` (never silently guessed); this is what makes
`ResolvedMethodSpec.is_ready` correctly refuse to proceed (see
`_all_concepts_mapped` in `method_spec.py`).
"""

from __future__ import annotations

from src.infra.data_layer import DataDictionary
from src.infra.models.method_spec import (
    ImplementationResolution,
    MethodReview,
    MethodSpec,
    SourceColumn,
)


def catalog_shim_fields(paper: MethodSpec) -> list[dict]:
    """Adapt `data.fields[]` + any `universe.filters[]` concept not already
    covered by `data.fields` into the dict shape `DataDictionary.
    normalize_fields[_with_llm]()` accepts -- the single place both
    `build_implementation_resolution` (below) and `review.py`'s catalog-
    mapping check build this concept set from, so they always run over the
    exact same fields.
    """
    shim_fields = [
        {
            "field": f.concept_id,
            "source_detail": f.paper_source_hint,
            "concept": f.paper_name,
        }
        for f in paper.data.fields
    ]
    # `universe.filters[].concept_id` (e.g. "exchange") is a SEPARATE concept
    # namespace from `data.fields` -- a filter concept isn't necessarily also
    # listed as a required data field, but `build_config`/the engine still
    # need it in `concept_mapping` to resolve the physical column. Add any
    # filter concept not already covered by data.fields (skip duplicates so
    # a concept_id used both ways isn't looked up twice).
    existing_field_ids = {f.concept_id for f in paper.data.fields}
    for filt in paper.universe.filters:
        if filt.concept_id not in existing_field_ids:
            shim_fields.append({"field": filt.concept_id})
            existing_field_ids.add(filt.concept_id)
    return shim_fields


def build_implementation_resolution(
    paper: MethodSpec,
    review: MethodReview,
    data_dictionary: DataDictionary | None = None,
    returns_source: str = "us_equity_crsp",
    cz_acronym: str | None = None,
    llm_client=None,
) -> ImplementationResolution:
    """Resolve `paper.data.fields[].concept_id` (+ filter-only concepts) to
    physical `{source, column}` pairs via the shared data catalog matcher.

    `llm_client=None` (the default) keeps this fully deterministic, exactly
    as before. When a client is passed, any concept the deterministic
    exact/substring matcher couldn't resolve gets one extra attempt via
    `DataDictionary.normalize_fields_with_llm()` -- every LLM pick is still
    hard-validated against the real catalog there, never trusted blindly --
    and concepts resolved ONLY that way are recorded in
    `llm_matched_concepts` so a human can specifically re-check them.
    """
    data_dictionary = data_dictionary or DataDictionary()
    shim_fields = catalog_shim_fields(paper)

    deterministic = data_dictionary.normalize_fields(shim_fields)
    resolved = (
        data_dictionary.normalize_fields_with_llm(shim_fields, llm_client=llm_client)
        if llm_client is not None
        else deterministic
    )
    llm_matched_concepts = sorted(set(resolved) - set(deterministic))

    concept_mapping = {
        concept_id: SourceColumn(source=hit["source"], column=hit["column"])
        for concept_id, hit in resolved.items()
    }

    return ImplementationResolution(
        factor_id=paper.factor_id,
        concept_mapping=concept_mapping,
        returns_source=returns_source,
        cz_acronym=cz_acronym,
        llm_matched_concepts=llm_matched_concepts,
    )
