"""Apply human resolution decisions to blocked/ambiguous MethodSpec fields.

Extracted from scripts/resolve_review_blocks.py so the interactive CLI script
and the web backend's `/api/resolve` endpoint share one implementation
instead of duplicating this logic.
"""

from __future__ import annotations

from typing import Any

# Some Review Gate blocked-field paths point at a legacy/alternate location
# in the actual MethodSpec schema. Canonicalize before reading/writing.
PATH_ALIASES = {
    "universe.missing_policy.action": "signal.missing_policy.action",
    "universe.winsorize_bounds": "signal.missing_policy.winsorize_bounds",
}


def get_path(data: dict[str, Any], field_path: str) -> Any:
    """Read a dotted field path (post-alias) out of a nested dict."""
    current: Any = data
    for part in PATH_ALIASES.get(field_path, field_path).split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def set_path(data: dict[str, Any], field_path: str, value: Any) -> None:
    """Write `value` at a dotted field path (post-alias) in a nested dict,
    creating intermediate dicts as needed."""
    parts = PATH_ALIASES.get(field_path, field_path).split(".")
    current = data
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def build_decision(
    note: dict[str, Any],
    spec_data: dict[str, Any],
    new_value: Any,
    reason: str,
    reviewer: str,
) -> dict[str, Any]:
    """Build a resolution decision record for one blocked field note."""
    field_path = note["field"]
    canonical_path = PATH_ALIASES.get(field_path, field_path)
    return {
        "field_path": field_path,
        "canonical_field_path": canonical_path,
        "old_value": get_path(spec_data, field_path),
        "new_value": new_value,
        "decision_type": "human_empirical_assumption",
        "reason": reason,
        "reviewer": reviewer,
        "paper_evidence": note.get("evidence", []),
    }


def apply_decisions(spec_data: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    """Apply a list of resolution decisions to `spec_data` in place: writes
    each new value, clears the matching `ambiguous_fields` entry, appends to
    `resolution_log`, and resets review/codegen status so the resolved spec
    goes back through Review Gate before it can be used for codegen."""
    for decision in decisions:
        set_path(spec_data, decision["field_path"], decision["new_value"])
        for ambiguous in spec_data.get("ambiguous_fields", []):
            if not isinstance(ambiguous, dict):
                continue
            if ambiguous.get("field") != decision["field_path"]:
                continue
            ambiguous["source"] = "clear"
            ambiguous["status"] = "clear"
            ambiguous["candidate_value"] = decision["new_value"]
            ambiguous["human_resolution"] = {
                "decision_type": decision["decision_type"],
                "reviewer": decision["reviewer"],
                "reason": decision["reason"],
            }
    spec_data.setdefault("resolution_log", []).extend(decisions)
    spec_data["review_status"] = "pending"
    spec_data["codegen_ready"] = False
    spec_data["paper_faithful"] = False
