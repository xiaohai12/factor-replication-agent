"""Run Review Gate over MethodSpec JSON files and write reviewed artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.method_spec import MethodSpec
from src.review_gate import ReviewGate, ReviewResult
from src.llm import create_llm_client


DEFAULT_INPUT_DIR = Path("data/method_specs/curated")
DEFAULT_OUTPUT_DIR = Path("data/method_specs/reviewed")
DEFAULT_PROMPT_PATH = Path("prompts/review_gate/methodspec_audit.md")
DEFAULT_PAPERS_DIR = Path("data/papers")


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


def _apply_raw_review_to_spec(spec: MethodSpec, result: dict[str, Any]) -> MethodSpec:
    spec.review_status = result.get("disposition", "pending")
    spec.remediation_mode = result.get("remediation_mode", spec.remediation_mode)
    spec.codegen_ready = bool(result.get("codegen_ready", False))
    spec.paper_faithful = bool(result.get("paper_faithful", False))
    spec.review_notes = [
        {
            "field": note.get("field", ""),
            "status": _status_value(note.get("status")),
            "severity": note.get("severity", ""),
            "reason": note.get("reason", ""),
            "current_value": note.get("current_value"),
            "candidate_value": note.get("candidate_value"),
            "empirical_impact": note.get("empirical_impact", ""),
            "evidence": note.get("evidence", []),
        }
        for note in result.get("field_notes", [])
    ]
    return spec


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract PDF text locally so CLI LLMs only receive the minimal paper content."""
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Paper text extraction requires either pdftotext on PATH or pymupdf installed."
        ) from exc

    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _resolve_paper_path(spec: MethodSpec, spec_path: Path, explicit_paper: str, papers_dir: Path) -> Path:
    if explicit_paper:
        path = Path(explicit_paper)
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path

    pdf_name = getattr(spec.paper, "pdf_file", "") if getattr(spec, "paper", None) else ""
    if pdf_name:
        candidate = (papers_dir / pdf_name).resolve()
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Could not resolve paper PDF for {spec_path.name}. Pass --paper explicitly."
    )


def _build_llm_messages(
    prompt_text: str,
    spec: MethodSpec,
    spec_path: Path,
    paper_path: Path,
    paper_text: str,
) -> list[dict[str, str]]:
    review_contract = """
Return exactly one JSON object with this shape:
{
  "review_id": "string",
  "methodspec_version": "string",
  "reviewer": "string",
  "disposition": "approved|revision_required|blocked",
  "remediation_mode": "patch_existing_json|targeted_reextraction|full_regeneration",
  "codegen_ready": true,
  "paper_faithful": true,
  "approved": true,
  "issues": ["string"],
  "warnings": ["string"],
  "field_notes": [
    {
      "field": "dotted.path",
      "severity": "P0|P1|P2|P3",
      "status": "auto_approve|auto_approve_with_flag|approve_with_default|needs_llm_review|needs_human_confirmation",
      "reason": "string",
      "current_value": "any JSON value",
      "candidate_value": "any JSON value",
      "empirical_impact": "high|low",
      "evidence": [
        {
          "location": "string",
          "quote": "string",
          "interpretation": "string",
          "source_type": "paper"
        }
      ]
    }
  ],
  "blocked_fields": ["dotted.path"],
  "requires_human": true,
  "markdown_report": "full markdown review report"
}
Rules:
- blocked_fields must equal the subset of field_notes whose status is needs_human_confirmation.
- approved must be true iff disposition is approved.
- codegen_ready must be false for blocked or revision_required outputs.
- If a field is paper-silent but high-impact, mark status needs_human_confirmation rather than approving it as paper fact.
- Respond with JSON only.
""".strip()

    user_request = f"""Audit this MethodSpec against the original paper.

MethodSpec JSON path: {spec_path}
Paper PDF path: {paper_path}

Use only the content below as your input corpus.

[METHODSPEC JSON]
{json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False)}

[PAPER TEXT]
{paper_text}

{review_contract}
"""
    return [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": user_request},
    ]


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


def _write_llm_artifacts(
    spec: MethodSpec,
    result: dict[str, Any],
    source_path: Path,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    factor_id = _slug(spec.factor_id or source_path.stem.replace(".methodspec", ""))

    reviewed_spec_path = output_dir / f"{factor_id}.reviewed.methodspec.json"
    review_report_path = output_dir / f"{factor_id}.review_report.json"
    markdown_review_path = output_dir / f"{factor_id}.llm_review.md"

    reviewed_spec_path.write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    )
    review_report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    markdown_review_path.write_text((result.get("markdown_report") or "").strip() + "\n")
    return reviewed_spec_path, review_report_path, markdown_review_path


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


def llm_review_file(
    path: Path,
    output_dir: Path,
    provider: str,
    model: str | None,
    prompt_path: Path,
    papers_dir: Path,
    explicit_paper: str = "",
) -> dict[str, Any]:
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
            "markdown_review_path": "",
        }

    try:
        paper_path = _resolve_paper_path(spec, path, explicit_paper, papers_dir)
        prompt_text = prompt_path.read_text()
        paper_text = _extract_pdf_text(paper_path)
        client = create_llm_client(provider=provider, model=model)
        response = client.chat.completions.create(
            messages=_build_llm_messages(prompt_text, spec, path, paper_path, paper_text),
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw_result = json.loads(response.choices[0].message.content)

        reviewed_spec = _apply_raw_review_to_spec(spec, raw_result)
        reviewed_spec_path, review_report_path, markdown_review_path = _write_llm_artifacts(
            reviewed_spec, raw_result, path, output_dir
        )

        return {
            "path": str(path),
            "ok": True,
            "factor_id": reviewed_spec.factor_id,
            "disposition": raw_result.get("disposition", "pending"),
            "codegen_ready": bool(raw_result.get("codegen_ready", False)),
            "requires_human": bool(raw_result.get("requires_human", False)),
            "blocked_fields": raw_result.get("blocked_fields", []),
            "issues": raw_result.get("issues", []),
            "warnings": raw_result.get("warnings", []),
            "reviewed_spec_path": str(reviewed_spec_path),
            "review_report_path": str(review_report_path),
            "markdown_review_path": str(markdown_review_path),
        }
    except Exception as exc:
        return {
            "path": str(path),
            "ok": False,
            "factor_id": getattr(spec, "factor_id", ""),
            "disposition": "llm_review_failed",
            "codegen_ready": False,
            "requires_human": False,
            "blocked_fields": [],
            "issues": [str(exc)],
            "warnings": [],
            "reviewed_spec_path": "",
            "review_report_path": "",
            "markdown_review_path": "",
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
    parser.add_argument("--backend", choices=["rules", "llm"], default="rules")
    parser.add_argument("--provider", choices=["codex", "copilot", "openrouter"], default="codex")
    parser.add_argument("--model", default="")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT_PATH))
    parser.add_argument("--paper", default="")
    parser.add_argument("--papers-dir", default=str(DEFAULT_PAPERS_DIR))
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    files = _iter_input_files(args)
    if not files:
        print("No MethodSpec files found.")
        return 1

    output_dir = Path(args.out_dir)
    if args.backend == "llm":
        prompt_path = Path(args.prompt)
        papers_dir = Path(args.papers_dir)
        items = [
            llm_review_file(
                path,
                output_dir,
                provider=args.provider,
                model=args.model or None,
                prompt_path=prompt_path,
                papers_dir=papers_dir,
                explicit_paper=args.paper,
            )
            for path in files
        ]
    else:
        items = [review_file(path, output_dir) for path in files]

    if args.format == "json":
        print(json.dumps({"total_files": len(items), "items": items}, indent=2))
    else:
        _print_text_summary(items)

    return 1 if any(not item["ok"] for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
