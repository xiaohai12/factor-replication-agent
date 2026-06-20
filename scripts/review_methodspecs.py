"""Run Review Gate over MethodSpec JSON files and write reviewed artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.method_spec import MethodSpec
from src.review_gate import ReviewGate, ReviewResult


DEFAULT_INPUT_DIR = Path("data/method_specs/curated")
DEFAULT_OUTPUT_DIR = Path("data/method_specs/reviewed")


def _status_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _review_result_to_dict(result: ReviewResult) -> dict[str, Any]:
    return {
        "review_id": result.review_id,
        "methodspec_version": result.methodspec_version,
        "reviewer": result.reviewer,
        "disposition": result.disposition,
        "remediation_mode": result.remediation_mode,
        "codegen_ready": result.codegen_ready,
        "paper_faithful": result.paper_faithful,
        "approved": result.approved,
        "issues": result.issues,
        "warnings": result.warnings,
        "field_notes": [
            {
                "field": note.field,
                "status": _status_value(note.status),
                "reason": note.reason,
                "current_value": note.current_value,
                "candidate_value": note.candidate_value,
                "empirical_impact": note.empirical_impact,
                "evidence": [e.model_dump(mode="json") for e in note.evidence],
            }
            for note in result.field_notes
        ],
        "blocked_fields": result.blocked_fields,
        "requires_human": result.requires_human,
    }


def _apply_review_to_spec(spec: MethodSpec, result: ReviewResult) -> MethodSpec:
    spec.review_status = result.disposition
    spec.remediation_mode = result.remediation_mode
    spec.codegen_ready = result.codegen_ready
    spec.paper_faithful = result.paper_faithful
    spec.review_notes = [
        {
            "field": note.field,
            "status": _status_value(note.status),
            "reason": note.reason,
            "current_value": note.current_value,
            "candidate_value": note.candidate_value,
            "empirical_impact": note.empirical_impact,
            "evidence": [e.model_dump(mode="json") for e in note.evidence],
        }
        for note in result.field_notes
    ]
    return spec


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _write_artifacts(
    spec: MethodSpec,
    result: ReviewResult,
    source_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    factor_id = _slug(spec.factor_id or source_path.stem.replace(".methodspec", ""))

    reviewed_spec_path = output_dir / f"{factor_id}.reviewed.methodspec.json"
    review_report_path = output_dir / f"{factor_id}.review_report.json"

    reviewed_spec_path.write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    )
    review_report_path.write_text(
        json.dumps(_review_result_to_dict(result), indent=2, ensure_ascii=False) + "\n"
    )
    return reviewed_spec_path, review_report_path


def _iter_input_files(args: argparse.Namespace) -> list[Path]:
    if args.file:
        return [Path(args.file)]

    input_dir = Path(args.dir)
    files = sorted(input_dir.glob("*.methodspec.json"))
    if args.factor:
        factor = args.factor.lower()
        files = [path for path in files if factor in path.stem.lower()]
    return files


def review_file(path: Path, output_dir: Path) -> dict[str, Any]:
    try:
        spec = MethodSpec.model_validate_json(path.read_text())
    except (ValidationError, json.JSONDecodeError, OSError) as exc:
        return {
            "path": str(path),
            "ok": False,
            "factor_id": "",
            "disposition": "parse_failed",
            "codegen_ready": False,
            "requires_human": False,
            "blocked_fields": [],
            "issues": [str(exc)],
            "warnings": [],
            "reviewed_spec_path": "",
            "review_report_path": "",
        }

    result = ReviewGate().review(spec)
    reviewed_spec = _apply_review_to_spec(spec, result)
    reviewed_spec_path, review_report_path = _write_artifacts(
        reviewed_spec, result, path, output_dir
    )

    return {
        "path": str(path),
        "ok": True,
        "factor_id": reviewed_spec.factor_id,
        "disposition": result.disposition,
        "codegen_ready": result.codegen_ready,
        "requires_human": result.requires_human,
        "blocked_fields": result.blocked_fields,
        "issues": result.issues,
        "warnings": result.warnings,
        "reviewed_spec_path": str(reviewed_spec_path),
        "review_report_path": str(review_report_path),
    }


def _print_text_summary(items: list[dict[str, Any]]) -> None:
    total = len(items)
    parsed = sum(1 for item in items if item["ok"])
    approved = sum(1 for item in items if item["disposition"] == "approved")
    blocked = sum(1 for item in items if item["disposition"] == "blocked")
    revision_required = sum(1 for item in items if item["disposition"] == "revision_required")

    print("MethodSpec review summary")
    print("=========================")
    print(f"total_files: {total}")
    print(f"parse_success: {parsed}")
    print(f"approved: {approved}")
    print(f"revision_required: {revision_required}")
    print(f"blocked: {blocked}")

    if items:
        print("\nReviewed files")
        print("--------------")
        for item in items:
            factor = item["factor_id"] or Path(item["path"]).name
            fields = ", ".join(item["blocked_fields"])
            suffix = f" blocked_fields=[{fields}]" if fields else ""
            print(f"- {factor}: {item['disposition']}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--file", default="")
    parser.add_argument("--factor", default="")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    files = _iter_input_files(args)
    if not files:
        print("No MethodSpec files found.")
        return 1

    output_dir = Path(args.out_dir)
    items = [review_file(path, output_dir) for path in files]

    if args.format == "json":
        print(json.dumps({"total_files": len(items), "items": items}, indent=2))
    else:
        _print_text_summary(items)

    return 1 if any(not item["ok"] for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
