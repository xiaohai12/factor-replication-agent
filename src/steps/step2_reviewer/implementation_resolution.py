"""Physical-mapping resolution over the paper-first schema (Phase C). Builds
`ImplementationResolution` from a `PaperMethodSpec` + `MethodReview` -- NOT
wired into `src.pipeline` yet (see docs/methodspec-v2-plan.md section 9).

Reuses the existing `DataDictionary.normalize_fields()` catalog matcher
(`src/infra/data_layer/__init__.py`) rather than reimplementing concept ->
physical-column matching -- this module only adapts `RequiredField`'s shape into the
dict form that matcher already accepts. An unresolved `signal_input` concept
is left OUT of `concept_mapping` (never silently guessed); this is what
makes `ResolvedMethodSpec.is_ready` correctly refuse to proceed (see
`_all_concepts_mapped` in `paper_method_spec.py`).
"""

from __future__ import annotations

from src.infra.data_layer import DataDictionary
from src.infra.models.paper_method_spec import (
    ImplementationResolution,
    MethodReview,
    PaperMethodSpec,
    SourceColumn,
)


def build_implementation_resolution(
    paper: PaperMethodSpec,
    review: MethodReview,
    data_dictionary: DataDictionary | None = None,
    returns_source: str = "us_equity_crsp",
    cz_acronym: str | None = None,
) -> ImplementationResolution:
    """Resolve `paper.data.fields[].concept_id` to physical `{source, column}`
    pairs via the shared data catalog matcher, and bind the result to the
    exact paper/review hashes it was built from.
    """
    data_dictionary = data_dictionary or DataDictionary()

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
    resolved = data_dictionary.normalize_fields(shim_fields)

    concept_mapping = {
        concept_id: SourceColumn(source=hit["source"], column=hit["column"])
        for concept_id, hit in resolved.items()
    }

    return ImplementationResolution(
        factor_id=paper.factor_id,
        paper_spec_hash=paper.content_hash(),
        review_hash=review.content_hash(),
        concept_mapping=concept_mapping,
        returns_source=returns_source,
        cz_acronym=cz_acronym,
    )
