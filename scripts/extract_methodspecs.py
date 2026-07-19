"""Extract MethodSpec JSON from paper PDFs using the SemanticExtractor.

Usage examples:

  # Single paper, single factor
  python scripts/extract_methodspecs.py --paper data/test_papers/foo.pdf --factor AssetGrowth

  # Single paper, multiple factors defined in it
  python scripts/extract_methodspecs.py --paper data/test_papers/foo.pdf --factor AB1998_AQ,AB1998_AR

  # Batch: all PDFs in a directory (one factor per PDF, name inferred from filename)
  python scripts/extract_methodspecs.py --dir data/papers/ --out-dir runs/method_specs/unreviewed/

  # Use Copilot CLI instead of Codex
  python scripts/extract_methodspecs.py --paper foo.pdf --factor BM --provider copilot

  # Use Claude Code CLI
  python scripts/extract_methodspecs.py --paper foo.pdf --factor BM --provider claude
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.steps.extractor import RateLimitExhausted, SemanticExtractor
from src.infra.llm import create_llm_client

DEFAULT_OUTPUT_DIR = Path("runs/method_specs/unreviewed")
DEFAULT_PAPERS_DIR = Path("data/papers")


def _extract_pdf_text(pdf_path: Path) -> str:
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


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _write_methodspec(spec_dict: dict, factor_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{_slug(factor_id)}.methodspec.json"
    out_path.write_text(json.dumps(spec_dict, indent=2, ensure_ascii=False) + "\n")
    return out_path


def extract_paper(
    pdf_path: Path,
    factor_ids: list[str],
    output_dir: Path,
    provider: str,
    model: str | None,
) -> list[dict[str, Any]]:
    """Extract one or more factors from a single paper PDF."""
    try:
        paper_text = _extract_pdf_text(pdf_path)
    except Exception as exc:
        return [
            {
                "pdf": str(pdf_path),
                "factor_id": fid,
                "ok": False,
                "error": str(exc),
                "output_path": "",
            }
            for fid in factor_ids
        ]

    client = create_llm_client(provider=provider, model=model or None)
    extractor = SemanticExtractor(llm_client=client)

    items: list[dict[str, Any]] = []

    if len(factor_ids) == 1:
        factor_id = factor_ids[0]
        try:
            result = extractor.extract(factor_id, paper_text)
            if result.spec is None:
                items.append({
                    "pdf": str(pdf_path),
                    "factor_id": factor_id,
                    "ok": False,
                    "error": result.error or "Extraction returned no spec",
                    "output_path": "",
                })
            else:
                out_path = _write_methodspec(
                    result.spec.model_dump(mode="json"), factor_id, output_dir
                )
                items.append({
                    "pdf": str(pdf_path),
                    "factor_id": factor_id,
                    "ok": True,
                    "error": "",
                    "output_path": str(out_path),
                })
        except RateLimitExhausted as exc:
            items.append({
                "pdf": str(pdf_path),
                "factor_id": factor_id,
                "ok": False,
                "error": f"Rate limit: {exc}",
                "output_path": "",
            })
    else:
        try:
            batch = extractor.extract_batch(factor_ids, paper_text)
            for factor_id in factor_ids:
                result = batch.get(factor_id)
                if result is None or result.spec is None:
                    items.append({
                        "pdf": str(pdf_path),
                        "factor_id": factor_id,
                        "ok": False,
                        "error": (result.error if result else "Missing from batch output") or "No spec returned",
                        "output_path": "",
                    })
                else:
                    out_path = _write_methodspec(
                        result.spec.model_dump(mode="json"), factor_id, output_dir
                    )
                    items.append({
                        "pdf": str(pdf_path),
                        "factor_id": factor_id,
                        "ok": True,
                        "error": "",
                        "output_path": str(out_path),
                    })
        except RateLimitExhausted as exc:
            for factor_id in factor_ids:
                items.append({
                    "pdf": str(pdf_path),
                    "factor_id": factor_id,
                    "ok": False,
                    "error": f"Rate limit: {exc}",
                    "output_path": "",
                })

    return items


def _iter_batch_inputs(args: argparse.Namespace) -> list[tuple[Path, list[str]]]:
    """Return list of (pdf_path, [factor_ids]) pairs to process."""
    if args.paper:
        pdf_path = Path(args.paper)
        if not pdf_path.is_absolute():
            pdf_path = (REPO_ROOT / pdf_path).resolve()
        factor_ids = [f.strip() for f in args.factor.split(",") if f.strip()]
        if not factor_ids:
            factor_ids = [pdf_path.stem]
        return [(pdf_path, factor_ids)]

    papers_dir = Path(args.dir)
    pdfs = sorted(papers_dir.glob("*.pdf"))
    return [(pdf, [pdf.stem]) for pdf in pdfs]


def _print_text_summary(items: list[dict[str, Any]]) -> None:
    total = len(items)
    ok = sum(1 for i in items if i["ok"])
    print("Extraction summary")
    print("==================")
    print(f"total_factors: {total}")
    print(f"succeeded: {ok}")
    print(f"failed: {total - ok}")
    if items:
        print("\nResults")
        print("-------")
        for item in items:
            status = "ok" if item["ok"] else f"FAILED ({item['error'][:80]})"
            print(f"- {item['factor_id']} ({Path(item['pdf']).name}): {status}")
            if item["output_path"]:
                print(f"    -> {item['output_path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper", default="", help="Path to a single paper PDF")
    group.add_argument("--dir", default="", help="Directory of PDFs to process in batch")
    parser.add_argument("--factor", default="", help="Factor ID(s) to extract, comma-separated (required with --paper)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--provider", choices=["codex", "copilot", "claude", "openrouter"], default="codex")
    parser.add_argument("--model", default="")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.paper and not args.factor:
        parser.error("--factor is required when using --paper")

    inputs = _iter_batch_inputs(args)
    if not inputs:
        print("No PDFs found.")
        return 1

    output_dir = Path(args.out_dir)
    all_items: list[dict[str, Any]] = []

    for pdf_path, factor_ids in inputs:
        items = extract_paper(
            pdf_path=pdf_path,
            factor_ids=factor_ids,
            output_dir=output_dir,
            provider=args.provider,
            model=args.model or None,
        )
        all_items.extend(items)
        if any(i["error"].startswith("Rate limit") for i in items):
            print("Rate limit hit — stopping early. Re-run to continue.")
            break

    if args.format == "json":
        print(json.dumps({"total": len(all_items), "items": all_items}, indent=2))
    else:
        _print_text_summary(all_items)

    return 1 if any(not i["ok"] for i in all_items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
