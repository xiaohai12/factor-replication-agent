"""Generate `SchemaReferencePage.tsx`'s field-reference payload directly from
the `MethodSpec` Pydantic model (mirrors `schema_render.py`'s approach for
the extraction prompt skeleton) -- so the reference page can never silently
drift from the real schema the way a hand-duplicated doc would.

Mechanically derived per field: dotted path, allowed enum values, a
representative example, and whether it's a list/composite. `description`/
`usage`/`engine_consumed` are NOT purely mechanical (the model has no
`Field(description=...)` text and "does the deterministic engine actually
read this" is domain knowledge, not something inferable from a type
annotation) -- these come from the curated `_FIELD_NOTES` table below, keyed
by dotted path, with safe generic defaults for any path not listed there.
`origin` is always `"llm"`: every field on `MethodSpec` is Step 1 extractor
output (unlike v1, this model no longer mixes in review/resolution state).
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from src.infra.models.method_spec import EvidenceCitation, MethodSpec, SourcedValue

# Dotted paths the deterministic backtest engine (registry.build_config /
# BacktestExecutor) actually reads to produce its resolved numeric config --
# everything else is extracted/reviewed metadata that's real and audited,
# but has no direct effect on what the engine computes. Cross-checked
# against src/steps/step3_codegen/registry.py's _build_config_from_resolved.
_ENGINE_CONSUMED_PATHS = {
    "paper.publication_year",
    "data.fields",
    "sample.formation",
    "timing.formation_month",
    "timing.rebalance_frequency",
    "timing.holding_period",
    "timing.data_availability",
    "universe.filters",
    "portfolio.construction_type",
    "portfolio.sorts",
    "portfolio.legs",
    "portfolio.weighting",
    "portfolio.return_combination",
    "portfolio.missing_policies",
}

# Curated description/usage text for the paths worth explaining -- anything
# not listed here still gets a full entry (path/type/allowed_values/example),
# just with empty description/usage text.
_FIELD_NOTES: dict[str, dict[str, str]] = {
    "paper": {"description": "Which academic paper this MethodSpec was extracted from."},
    "paper.publication_year": {
        "usage": "Read by registry.build_config as config['publication_year'] (audit/provenance field on the resolved config, not a behavior switch)."
    },
    "signal.definition": {"description": "Plain-language definition of the signal, as the paper states it."},
    "signal.economic_intuition": {"description": "Why the paper expects this signal to predict returns."},
    "signal.direction": {"description": "Whether high signal values predict higher or lower subsequent returns."},
    "signal.formula": {
        "description": "The paper's own formula for computing the signal.",
        "usage": "Feeds MetaCoder's Step 3 codegen prompt (compute_signal generation), not the engine's numeric config directly.",
    },
    "signal.formula.steps": {"description": "Ordered calculation steps, each with its own evidence citation."},
    "signal.estimation": {
        "description": "Set only when signal.category == 'estimated' (e.g. rolling beta, residual momentum) -- the regression/rolling-statistic method used to derive the signal."
    },
    "data.fields": {
        "description": "Concepts the signal/universe/weighting need (e.g. total assets, market equity), each with the paper's own name for it and which role it plays.",
        "usage": "Anchors ImplementationResolution's concept_mapping -- codegen can't resolve a physical column for a concept that isn't listed here.",
    },
    "sample.data_coverage": {"description": "The raw data's available date range (not necessarily the strategy's own sample)."},
    "sample.formation": {
        "description": "The executable strategy's own sample period.",
        "usage": "Read by registry.build_config as config['sample_start_year']/['sample_end_year'].",
    },
    "sample.reported_returns": {"description": "The date range the paper's headline reported numbers actually cover."},
    "timing.formation_rule": {"description": "Free-text description of when/how often portfolios form (e.g. 'every June')."},
    "timing.formation_month": {
        "description": "Structured calendar month (1-12) portfolios form on, when the paper states an explicit one.",
        "usage": "Read by registry.build_config as config['formation_month']; defaults to June (6) when unstated.",
    },
    "timing.rebalance_frequency": {"usage": "Read by registry.build_config as config['rebalance_frequency']."},
    "timing.holding_period": {"usage": "Read by registry.build_config as config['holding_period_months']."},
    "timing.data_availability": {
        "description": "How long after the underlying data's own period-end the signal actually becomes available (the accounting lag).",
        "usage": "lag_value read by registry.build_config as config['accounting_lag_months'].",
    },
    "universe.description": {"description": "Free-text description of the paper's stock universe (exchanges, exclusions)."},
    "universe.filters": {
        "description": (
            "Structured universe filters (exchange listing, SIC exclusions, listing-history "
            "requirements, etc). `derivation` (optional) describes how to compute the filter's "
            "value from its concept_id's underlying physical column, when the paper's vocabulary "
            "doesn't match the column's raw encoding (e.g. 'NYSE/Amex/NASDAQ' -> exchcd 1/2/3) -- "
            "same shape as signal.formula, codegen'd the same way compute_signal is."
        ),
        "usage": "Read by registry.build_config as config['universe_filters'], applied by the engine's filter_universe step.",
    },
    "portfolio.construction_type": {
        "description": "How portfolios are built from the signal (characteristic sort, Fama-MacBeth regression, etc).",
        "usage": "Anything other than 'characteristic_sort' is blocked at review -- the engine only implements characteristic-sort portfolios.",
    },
    "portfolio.sorts": {
        "description": "One or more sort dimensions (e.g. a single decile sort on the signal, or a double sort on signal+size).",
        "usage": "The target sort's breakpoints.basis and group_count feed config['breakpoint_source']/['breakpoint_quantiles'].",
    },
    "portfolio.legs": {
        "description": "Which sort-group combination forms the long side and which forms the short side.",
        "usage": "Resolved into config['long_portfolios']/['short_portfolios'] by the engine.",
    },
    "portfolio.weighting": {
        "description": "How portfolio returns are weighted across constituent stocks.",
        "usage": "Read directly as config['weighting_rule']. An off-menu value ('other') is clamped to the engine default ('vw') if not caught first at review.",
    },
    "portfolio.return_combination": {
        "description": "How the long and short legs' returns are combined into the reported spread.",
        "usage": "Read directly as config['return_combination_type'].",
    },
    "portfolio.missing_policies": {
        "description": "What to do when an input/signal/portfolio-stage value is missing (drop, etc).",
        "usage": "The signal-stage policy's action feeds config['missing_action'].",
    },
    "portfolio.transforms": {
        "description": "Winsorization/truncation/standardization/rank/log transforms applied to the signal.",
        "usage": "Recorded for audit; not yet read by registry.build_config (documentation-only today).",
    },
    "reported_results": {"description": "The paper's own headline numbers, kept only for replication comparison -- never fed back into the engine."},
    "reported_results.metrics": {"description": "Up to 4 reported metrics: exactly one primary plus up to 3 secondary robustness metrics."},
}


@dataclass
class _FieldEntry:
    description: str
    example: str
    allowed_values: list[str] | None
    engine_consumed: bool
    usage: str
    origin: str | None
    sub_fields: list[str] | None
    list_item_fields: list[str] | None

    def to_json(self) -> dict:
        return {
            "description": self.description,
            "example": self.example,
            "allowed_values": self.allowed_values,
            "engine_consumed": self.engine_consumed,
            "usage": self.usage,
            "origin": self.origin,
            "sub_fields": self.sub_fields,
            "list_item_fields": self.list_item_fields,
        }


def _is_optional(annotation: typing.Any) -> tuple[bool, typing.Any]:
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return True, args[0]
    return False, annotation


def _unwrap_sourced(annotation: typing.Any) -> typing.Any | None:
    """Return the inner type T if annotation is SourcedValue[T], else None.

    Pydantic v2 materializes `SourcedValue[T]` as a real generated subclass
    (not a `typing._GenericAlias`), so `typing.get_origin()` returns `None`
    for it -- must check `__pydantic_generic_metadata__` instead.
    """
    _, annotation = _is_optional(annotation)
    metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
    if metadata and isinstance(metadata.get("origin"), type) and issubclass(metadata["origin"], SourcedValue):
        args = metadata.get("args") or (str,)
        return args[0]
    origin = typing.get_origin(annotation)
    if origin is not None and isinstance(origin, type) and issubclass(origin, SourcedValue):
        (inner_type,) = typing.get_args(annotation) or (str,)
        return inner_type
    return None


def _example_for(annotation: typing.Any) -> str:
    _, annotation = _is_optional(annotation)
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        args = typing.get_args(annotation)
        return repr(args[0]) if args else ""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        members = list(annotation)
        return repr(members[0].value) if members else ""
    if annotation is str:
        return '"..."'
    if annotation in (int, float):
        return "0"
    if annotation is bool:
        return "false"
    return ""


def _allowed_values_for(annotation: typing.Any) -> list[str] | None:
    _, annotation = _is_optional(annotation)
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return [str(a) for a in typing.get_args(annotation)]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [m.value for m in annotation]
    return None


def _notes_for(path: str) -> dict[str, str]:
    if path.endswith(".evidence") and path not in _FIELD_NOTES:
        return {"description": "Paper citation(s) supporting this field's value -- same {location, quote, interpretation, table_ref} shape everywhere."}
    return _FIELD_NOTES.get(path, {})


def _leaf_entry(path: str, annotation: typing.Any, is_list: bool = False) -> _FieldEntry:
    notes = _notes_for(path)
    example = _example_for(annotation)
    return _FieldEntry(
        description=notes.get("description", ""),
        example=f"[{example}, ...]" if is_list and example else example,
        allowed_values=_allowed_values_for(annotation),
        engine_consumed=path in _ENGINE_CONSUMED_PATHS,
        usage=notes.get("usage", ""),
        origin="llm",
        sub_fields=None,
        list_item_fields=None,
    )


def _composite_entry(path: str, sub_fields: list[str]) -> _FieldEntry:
    notes = _notes_for(path)
    return _FieldEntry(
        description=notes.get("description", ""),
        example="",
        allowed_values=None,
        engine_consumed=path in _ENGINE_CONSUMED_PATHS,
        usage=notes.get("usage", ""),
        origin="llm",
        sub_fields=sub_fields,
        list_item_fields=None,
    )


def _list_entry(path: str, item_names: list[str] | None) -> _FieldEntry:
    notes = _notes_for(path)
    return _FieldEntry(
        description=notes.get("description", ""),
        example="[]",
        allowed_values=None,
        engine_consumed=path in _ENGINE_CONSUMED_PATHS,
        usage=notes.get("usage", ""),
        origin="llm",
        sub_fields=None,
        list_item_fields=item_names,
    )


def _walk_model(model_cls: type[BaseModel], prefix: str, out: dict[str, _FieldEntry]) -> None:
    fields: dict[str, FieldInfo] = model_cls.model_fields
    for name, info in fields.items():
        path = f"{prefix}.{name}" if prefix else name
        annotation = info.annotation
        _, unwrapped = _is_optional(annotation)

        sourced_inner = _unwrap_sourced(annotation)
        if sourced_inner is not None:
            out[path] = _leaf_entry(path, sourced_inner)
            continue

        origin = typing.get_origin(unwrapped)
        if origin in (list, set, frozenset):
            (item_type,) = typing.get_args(unwrapped) or (str,)
            item_sourced = _unwrap_sourced(item_type)
            if item_sourced is not None:
                out[path] = _list_entry(path, ["value", "evidence", "status"])
            elif isinstance(item_type, type) and issubclass(item_type, BaseModel):
                out[path] = _list_entry(path, list(item_type.model_fields.keys()))
                # Recurse into the item model under the SAME path (no `[i]`
                # segment) -- matches how the frontend strips `[\d+]` before
                # looking a field up, so e.g. `portfolio.sorts[0].breakpoints.basis`
                # resolves to `portfolio.sorts.breakpoints.basis` here. Without
                # this, nested list-item fields (e.g. breakpoints.basis) never
                # got an entry at all, so the review page fell back to a plain
                # text input instead of a dropdown even though the field is a
                # 3-value enum (full_sample/nyse/other).
                # EXCEPTION: EvidenceCitation is the exact same {location, quote,
                # interpretation, table_ref} shape under every single evidence-
                # bearing field in the schema -- recursing into it here would
                # duplicate those same 4 leaf entries under dozens of parent
                # paths for zero extra information. Its own field names are
                # already listed via list_item_fields above.
                if item_type is not EvidenceCitation:
                    nested_items: dict[str, _FieldEntry] = {}
                    _walk_model(item_type, path, nested_items)
                    out.update(nested_items)
            else:
                out[path] = _list_entry(path, None)
            continue

        if isinstance(unwrapped, type) and issubclass(unwrapped, BaseModel):
            # `sub_fields` must be only unwrapped's OWN direct field names --
            # computed from `unwrapped.model_fields` BEFORE recursing, not
            # from `nested`'s keys afterward. `_walk_model` recursion writes
            # grandchild (and deeper) paths into the same `nested` dict (so
            # the frontend tree can resolve them at their own path when
            # expanded), which used to make `list(nested.keys())` silently
            # include those descendants too -- flattening e.g. `signal.
            # formula.steps.step_id` into `signal.formula`'s own sub_fields
            # as if it were a direct child, one level shallower than reality.
            direct_children = [f"{path}.{child_name}" for child_name in unwrapped.model_fields]
            nested: dict[str, _FieldEntry] = {}
            _walk_model(unwrapped, path, nested)
            out[path] = _composite_entry(path, direct_children)
            out.update(nested)
            continue

        out[path] = _leaf_entry(path, unwrapped)


def build_schema_reference() -> dict:
    """`{fields: {dotted_path: entry}, json_schema: <MethodSpec.model_json_schema()>}`
    -- the payload `GET /api/methodspecs/schema` serves to `SchemaReferencePage.tsx`.
    """
    entries: dict[str, _FieldEntry] = {}
    _walk_model(MethodSpec, "", entries)
    # factor_id/schema_version are pipeline-computed, not extractor output --
    # same exclusion schema_render.py's prompt skeleton makes, for the same reason.
    entries.pop("factor_id", None)
    entries.pop("schema_version", None)
    return {
        "fields": {path: entry.to_json() for path, entry in entries.items()},
        "json_schema": MethodSpec.model_json_schema(),
    }
