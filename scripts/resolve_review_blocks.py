"""Interactively resolve Review Gate blocked fields and write a resolved MethodSpec."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infra.models.method_spec import MethodSpec


DEFAULT_RESOLUTION_DIR = Path("data/method_specs/resolutions")
DEFAULT_RESOLVED_DIR = Path("data/method_specs/resolved")


PATH_ALIASES = {
    "universe.missing_policy.action": "signal.missing_policy.action",
    "universe.winsorize_bounds": "signal.missing_policy.winsorize_bounds",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return ""
    if raw.lower() in {"null", "none"}:
        return None
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _get_path(data: dict[str, Any], field_path: str) -> Any:
    current: Any = data
    for part in PATH_ALIASES.get(field_path, field_path).split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(data: dict[str, Any], field_path: str, value: Any) -> None:
    parts = PATH_ALIASES.get(field_path, field_path).split(".")
    current = data
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _suggest_options(note: dict[str, Any]) -> list[tuple[str, Any]]:
    field = note["field"]
    current = note.get("current_value")
    candidate = note.get("candidate_value")

    options: list[tuple[str, Any]] = []
    if candidate not in (None, "", "unspecified"):
        options.append((f"use candidate: {candidate}", candidate))

    if field.endswith("breakpoint_source"):
        options.extend([
            ("full_sample", "full_sample"),
            ("nyse", "nyse"),
            ("keep blocked / unspecified", "unspecified"),
        ])
    elif field.endswith("missing_policy.action"):
        options.extend([
            ("drop", "drop"),
            ("keep blocked / unspecified", "unspecified"),
        ])
    elif field == "portfolio.implied_factor_direction":
        if current not in (None, "", "unspecified"):
            options.append(("keep current inferred direction", current))
        options.append(("keep blocked / unspecified", "unspecified"))
    elif field.endswith("winsorize_bounds"):
        options.extend([
            ("no winsorization for main spec (null)", None),
            ("keep blocked / unspecified", "unspecified"),
        ])
    else:
        if current not in (None, "", "unspecified"):
            options.append((f"keep current: {current}", current))
        options.append(("keep blocked / unspecified", "unspecified"))

    deduped: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for label, value in options:
        key = json.dumps(value, sort_keys=True, default=str)
        if key not in seen:
            deduped.append((label, value))
            seen.add(key)
    deduped.append(("custom value", "__custom__"))
    return deduped


def _print_evidence(note: dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print(f"Blocked field: {note['field']}")
    print(f"Status: {note.get('status')}")
    print(f"Empirical impact: {note.get('empirical_impact')}")
    print("\nWhy blocked:")
    print(note.get("reason") or "(no reason recorded)")

    evidence = note.get("evidence") or []
    if evidence:
        print("\nPaper evidence to inspect:")
        for idx, item in enumerate(evidence, start=1):
            print(f"{idx}. Location: {item.get('location') or '(not recorded)'}")
            print(f"   Quote: {item.get('quote') or '(not recorded)'}")
            interpretation = item.get("interpretation")
            if interpretation:
                print(f"   Interpretation: {interpretation}")

    print("\nCurrent value:")
    print(json.dumps(note.get("current_value"), indent=2, ensure_ascii=False))
    print("\nCandidate value:")
    print(json.dumps(note.get("candidate_value"), indent=2, ensure_ascii=False))


def _ask_decision(note: dict[str, Any]) -> tuple[Any, str]:
    _print_evidence(note)
    options = _suggest_options(note)

    print("\nChoose decision:")
    for idx, (label, _) in enumerate(options, start=1):
        print(f"{idx}. {label}")

    while True:
        choice = input("> ").strip()
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter an option number.")
            continue
        if 0 <= index < len(options):
            _, value = options[index]
            break
        print("Invalid option.")

    if value == "__custom__":
        print("Enter custom value. Use JSON for objects/lists/null; plain strings are accepted.")
        value = _parse_value(input("> "))

    print("Decision reason. Mention the paper section/table/quote you inspected:")
    reason = input("> ").strip()
    if not reason:
        reason = "Human reviewer confirmed this empirical assumption after inspecting the cited evidence."
    return value, reason


def _build_decision(
    note: dict[str, Any],
    spec_data: dict[str, Any],
    new_value: Any,
    reason: str,
    reviewer: str,
) -> dict[str, Any]:
    field_path = note["field"]
    canonical_path = PATH_ALIASES.get(field_path, field_path)
    return {
        "field_path": field_path,
        "canonical_field_path": canonical_path,
        "old_value": _get_path(spec_data, field_path),
        "new_value": new_value,
        "decision_type": "human_empirical_assumption",
        "reason": reason,
        "reviewer": reviewer,
        "paper_evidence": note.get("evidence", []),
    }


def _apply_decisions(spec_data: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    for decision in decisions:
        _set_path(spec_data, decision["field_path"], decision["new_value"])
        for ambiguous in spec_data.get("ambiguous_fields", []):
            if not isinstance(ambiguous, dict):
                continue
            if ambiguous.get("field") != decision["field_path"]:
                continue
            ambiguous["source"] = "clear"
            ambiguous["status"] = "clear"
            ambiguous["confidence"] = "high"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--reviewer", default="human")
    parser.add_argument("--resolution-dir", default=str(DEFAULT_RESOLUTION_DIR))
    parser.add_argument("--resolved-dir", default=str(DEFAULT_RESOLVED_DIR))
    args = parser.parse_args()

    spec_path = Path(args.spec)
    report_path = Path(args.report)
    spec_data = _load_json(spec_path)
    report = _load_json(report_path)
    blocked = set(report.get("blocked_fields", []))
    notes = [note for note in report.get("field_notes", []) if note.get("field") in blocked]

    if not notes:
        print("No blocked fields found in review report.")
        return 0

    factor_id = spec_data.get("factor_id") or spec_path.stem.split(".")[0]
    decisions = []
    for note in notes:
        value, reason = _ask_decision(note)
        decisions.append(_build_decision(note, spec_data, value, reason, args.reviewer))

    resolved_data = json.loads(json.dumps(spec_data))
    _apply_decisions(resolved_data, decisions)
    MethodSpec.model_validate(resolved_data)

    resolution_dir = Path(args.resolution_dir)
    resolved_dir = Path(args.resolved_dir)
    resolution_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir.mkdir(parents=True, exist_ok=True)

    resolution_path = resolution_dir / f"{factor_id}.resolution.json"
    resolved_path = resolved_dir / f"{factor_id}.resolved.methodspec.json"

    resolution_payload = {
        "factor_id": factor_id,
        "source_spec": str(spec_path),
        "source_review_report": str(report_path),
        "reviewer": args.reviewer,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
    }
    resolution_path.write_text(json.dumps(resolution_payload, indent=2, ensure_ascii=False) + "\n")
    resolved_path.write_text(json.dumps(resolved_data, indent=2, ensure_ascii=False) + "\n")

    print("\nResolution record written:")
    print(f"- {resolution_path}")
    print("Resolved MethodSpec written:")
    print(f"- {resolved_path}")
    print("\nNext:")
    print(f"python3 scripts/review_methodspecs.py --file {resolved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
