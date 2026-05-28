"""Convert PDFs in data/papers/ to Markdown files in data/papers_md/.

Uses pymupdf4llm for structured markdown extraction (headings, tables, equations).
Only converts PDFs that don't already have a corresponding .md file (incremental).

Usage:
    python scripts/convert_papers_to_md.py
    python scripts/convert_papers_to_md.py --force  # re-convert all
"""

import argparse
import sys
from pathlib import Path

import pymupdf4llm


PAPERS_DIR = Path(__file__).parent.parent / "data" / "papers"
MD_DIR = Path(__file__).parent.parent / "data" / "papers_md"


def convert_pdf_to_md(pdf_path: Path, md_path: Path) -> None:
    """Convert a single PDF to markdown."""
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    md_path.write_text(md_text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Convert PDFs to Markdown")
    parser.add_argument("--force", action="store_true", help="Re-convert all PDFs")
    args = parser.parse_args()

    MD_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(PAPERS_DIR.glob("*.pdf"))
    if not pdf_files:
        print("No PDFs found in data/papers/")
        return

    converted = 0
    skipped = 0
    errors = 0

    for pdf_path in pdf_files:
        md_path = MD_DIR / pdf_path.with_suffix(".md").name
        if md_path.exists() and not args.force:
            skipped += 1
            continue

        try:
            print(f"  Converting: {pdf_path.name}")
            convert_pdf_to_md(pdf_path, md_path)
            converted += 1
        except Exception as e:
            print(f"  ERROR: {pdf_path.name}: {e}", file=sys.stderr)
            errors += 1

    print(f"\nDone: {converted} converted, {skipped} skipped, {errors} errors")
    print(f"Output: {MD_DIR}")


if __name__ == "__main__":
    main()
