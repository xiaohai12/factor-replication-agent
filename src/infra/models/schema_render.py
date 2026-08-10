"""Render a paper-first MethodSpec extraction-prompt JSON skeleton directly
from the `MethodSpec` Pydantic model (docs/methodspec-v2-plan.md Phase B
item 2: "在可行处从模型元数据生成提示词 schema 片段").

This is the structural fix for the original drift bug (plan section 3.1):
instead of hand-maintaining a JSON example that can silently diverge from
what the model actually accepts, the skeleton is regenerated from
`model_fields` on every prompt load -- same pattern as
`field_contract.splice_allowed_values` uses for the "Allowed Values" block.
"""

from __future__ import annotations

import typing
from enum import Enum

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from src.infra.models.method_spec import EvidenceCitation, SourcedValue

_MAX_LIST_EXAMPLES = 1  # one example element is enough to show shape


def _is_optional(annotation: typing.Any) -> tuple[bool, typing.Any]:
    """Return (True, inner_type) if annotation is Optional[inner_type]."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return True, args[0]
    return False, annotation


def _render_scalar(annotation: typing.Any) -> typing.Any:
    if annotation is str:
        return ""
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return False
    if annotation.__name__ == "datetime":
        return "<ISO8601 timestamp>"
    return None


def render_field(annotation: typing.Any) -> typing.Any:
    """Recursively render a placeholder value for a type annotation."""
    _, annotation = _is_optional(annotation)

    origin = typing.get_origin(annotation)

    # SourcedValue[T] -- our generic evidence wrapper (special-cased so the
    # skeleton shows {value, evidence, status} rather than recursing into
    # SourcedValue's own generic internals).
    if origin is not None and isinstance(origin, type) and issubclass(origin, SourcedValue):
        (inner_type,) = typing.get_args(annotation) or (str,)
        return {
            "value": render_field(inner_type),
            "evidence": [render_field(EvidenceCitation)],
            "status": "clear | table_only | inferred | conflicting | unspecified",
        }

    if origin is typing.Literal:
        return " | ".join(str(a) for a in typing.get_args(annotation))

    if origin in (list, set, frozenset):
        (item_type,) = typing.get_args(annotation) or (str,)
        return [render_field(item_type) for _ in range(_MAX_LIST_EXAMPLES)]

    if origin is dict:
        return {}

    if origin is tuple:
        return [render_field(a) for a in typing.get_args(annotation)]

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return " | ".join(m.value for m in annotation)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return render_model(annotation)

    if isinstance(annotation, type):
        return _render_scalar(annotation)

    return None


def render_model(model_cls: type[BaseModel]) -> dict[str, typing.Any]:
    """Render a JSON-shaped skeleton dict for a BaseModel subclass."""
    out: dict[str, typing.Any] = {}
    fields: dict[str, FieldInfo] = model_cls.model_fields
    for name, info in fields.items():
        out[name] = render_field(info.annotation)
    return out


# Markers delimiting the auto-generated block inside
# prompts/extractor/method_spec_extractor.md -- same splice pattern as
# field_contract.splice_allowed_values, so the "Required JSON Shape" example
# can never silently diverge from what MethodSpec actually accepts
# (the exact drift bug plan section 3.1 documents for the original schema).
SCHEMA_SKELETON_START = "<!-- METHODSPEC:SCHEMA_SKELETON:START -->"
SCHEMA_SKELETON_END = "<!-- METHODSPEC:SCHEMA_SKELETON:END -->"


def render_schema_skeleton_block() -> str:
    import json

    from src.infra.models.method_spec import MethodSpec

    skeleton = render_model(MethodSpec)
    # factor_id and schema_version are computed by the pipeline, not the LLM
    # (D7: factor_id = sha256(document_id + "::" + target_name)); drop them
    # from the prompt example so the model doesn't try to invent one.
    skeleton.pop("factor_id", None)
    skeleton.pop("schema_version", None)
    body = json.dumps(skeleton, indent=2)
    return f"{SCHEMA_SKELETON_START}\n```json\n{body}\n```\n{SCHEMA_SKELETON_END}"


def splice_schema_skeleton(markdown_text: str) -> str:
    start = markdown_text.find(SCHEMA_SKELETON_START)
    end = markdown_text.find(SCHEMA_SKELETON_END)
    if start == -1 or end == -1 or end < start:
        return markdown_text
    end += len(SCHEMA_SKELETON_END)
    return markdown_text[:start] + render_schema_skeleton_block() + markdown_text[end:]

