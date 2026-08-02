"""Batch extraction accuracy evaluation across the 10 papers in data/test_papers/.

For each paper in data/test_papers/paper_spec_mapping.json, extracts all of its
mapped factors (one LLM call per paper via SemanticExtractor.extract_batch when a
paper defines more than one factor) and compares the result field-by-field against
the curated references in data/test_method_specs_human_labeled/, using the same
comparison logic as app.py's Extractor eval panel (field_accuracy / field_coverage).

No SignalDoc.csv / C&Z data is given to the extractor as input (paper text only) —
curated references are used only post-hoc here, for scoring.

Usage:
    python3 scripts/run_extraction_eval.py
    python3 scripts/run_extraction_eval.py --provider copilot --model claude-opus-4-6
    python3 scripts/run_extraction_eval.py --papers "Asset Growth and the Cross Section of Stock Returns.pdf"
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.steps.step1_extractor import RateLimitExhausted, SemanticExtractor  # noqa: E402
from src.infra.llm import create_llm_client  # noqa: E402
from src.infra.models.method_spec import MethodSpec  # noqa: E402

PAPERS_DIR = REPO_ROOT / "data" / "test_papers"
MAPPING_PATH = PAPERS_DIR / "paper_spec_mapping.json"
GT_DIR = REPO_ROOT / "data" / "test_method_specs_human_labeled"
OUT_DIR = REPO_ROOT / "data" / "eval_history"

# Same field set app.py's Extractor eval panel compares (extracted path, ground-truth path)
FIELDS_TO_COMPARE = [
    ("signal.formula.expression", "signal.formula.expression"),
    ("signal.formula.paper_expression", "signal.formula.paper_expression"),
    ("signal.timing.formation_month", "signal.timing.formation_month"),
    ("signal.timing.rebalance_frequency", "signal.timing.rebalance_frequency"),
    ("signal.timing.holding_period", "signal.timing.holding_period"),
    ("signal.timing.accounting_lag", "signal.timing.accounting_lag"),
    ("signal.missing_policy.action", "signal.missing_policy.action"),
    ("portfolio.sort.breakpoint_source", "portfolio.sort.breakpoint_source"),
    ("portfolio.weighting", "portfolio.weighting"),
    ("portfolio.long_leg", "portfolio.long_leg"),
    ("portfolio.short_leg", "portfolio.short_leg"),
    ("sign", "signal.sign"),
]


def extract_pdf_text(pdf_path: Path) -> str:
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    import fitz  # type: ignore

    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def get_nested(d: dict, path: str) -> Any:
    cur: Any = d
    for key in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def values_match(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    sa, sb = str(a).strip().lower(), str(b).strip().lower()
    if sa == sb:
        return True
    for prefix in ("breakpointsource.", "weightingrule.", "missingaction.", "rebalancefrequency."):
        sa = sa.replace(prefix, "")
        sb = sb.replace(prefix, "")
    return sa == sb


def compare_specs(extracted: dict, reference: dict) -> list[dict]:
    results = []
    for ext_path, gt_path in FIELDS_TO_COMPARE:
        ext_val = get_nested(extracted, ext_path)
        gt_val = get_nested(reference, gt_path)
        results.append({
            "field": ext_path,
            "extracted": "" if ext_val is None else str(ext_val),
            "reference": "" if gt_val is None else str(gt_val),
            "match": values_match(ext_val, gt_val),
        })
    return results


def compute_metrics(comparisons: list[dict]) -> dict:
    total = len(comparisons)
    matched = sum(1 for c in comparisons if c["match"])
    reference_present = sum(1 for c in comparisons if c["reference"])
    extracted_present = sum(1 for c in comparisons if c["extracted"])
    return {
        "field_accuracy": matched / total if total else 0.0,
        "field_coverage": extracted_present / reference_present if reference_present else 0.0,
        "matched": matched,
        "total": total,
    }


def load_curated_reference(factor_id: str) -> dict:
    """Load a curated MethodSpec reference, normalized to the flat schema.

    Reference files use the richer "curated annotation" schema (top-level
    ``timing``/``universe``/``portfolio``/``sample`` keys, value/source-wrapped
    fields). ``MethodSpec.normalize_curated_schema`` coerces that into the same
    flat shape ``SemanticExtractor.extract()`` produces, so dotted-path
    comparisons in ``compare_specs()`` actually line up on both sides instead of
    silently comparing incompatible schemas (which previously produced bogus
    accuracy/coverage numbers for every field except the two that happen to
    share a literal path in both schemas: signal.formula.expression/paper_expression).
    """
    gt_path = GT_DIR / f"{factor_id}.methodspec.json"
    if not gt_path.exists():
        return {}
    raw = json.loads(gt_path.read_text(encoding="utf-8"))
    try:
        return MethodSpec.model_validate(raw).model_dump(mode="json")
    except Exception:
        # Fall back to the raw shape rather than failing the whole eval run.
        return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["codex", "copilot", "claude", "openrouter"], default="codex")
    parser.add_argument("--model", default="")
    parser.add_argument("--papers", default="", help="Comma-separated subset of PDF filenames (default: all 10)")
    args = parser.parse_args()

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    papers: dict[str, Any] = mapping["papers"]
    if args.papers:
        wanted = {p.strip() for p in args.papers.split(",") if p.strip()}
        papers = {k: v for k, v in papers.items() if k in wanted}

    client = create_llm_client(provider=args.provider, model=args.model or None)
    extractor = SemanticExtractor(llm_client=client)

    per_factor: list[dict] = []

    for pdf_filename, info in papers.items():
        pdf_path = PAPERS_DIR / pdf_filename
        factor_ids = [s.replace(".methodspec.json", "") for s in info["method_specs"]]
        print(f"\n=== {pdf_filename} ({len(factor_ids)} factor(s)) ===", flush=True)

        if not pdf_path.exists():
            for fid in factor_ids:
                per_factor.append({"factor_id": fid, "pdf": pdf_filename, "error": "PDF not found"})
            print("  PDF not found, skipping.")
            continue

        try:
            paper_text = extract_pdf_text(pdf_path)
        except Exception as exc:
            for fid in factor_ids:
                per_factor.append({"factor_id": fid, "pdf": pdf_filename, "error": f"PDF read error: {exc}"})
            print(f"  PDF read error: {exc}")
            continue

        try:
            if len(factor_ids) == 1:
                batch = {factor_ids[0]: extractor.extract(factor_ids[0], paper_text)}
            else:
                batch = extractor.extract_batch(factor_ids, paper_text)
        except RateLimitExhausted as exc:
            for fid in factor_ids:
                per_factor.append({"factor_id": fid, "pdf": pdf_filename, "error": f"Rate limit: {exc}"})
            print(f"  Rate limit hit: {exc}")
            continue
        except Exception as exc:
            for fid in factor_ids:
                per_factor.append({"factor_id": fid, "pdf": pdf_filename, "error": f"Extraction error: {exc}"})
            print(f"  Extraction error: {exc}")
            continue

        for fid in factor_ids:
            result = batch.get(fid)
            reference = load_curated_reference(fid)

            if result is None or result.spec is None:
                err = (result.error if result else None) or "No spec returned"
                per_factor.append({"factor_id": fid, "pdf": pdf_filename, "error": err})
                print(f"  [{fid}] FAILED: {err}")
                continue

            ext_dict = result.spec.model_dump(mode="json")
            comparisons = compare_specs(ext_dict, reference)
            metrics = compute_metrics(comparisons)
            per_factor.append({
                "factor_id": fid,
                "pdf": pdf_filename,
                "field_accuracy": metrics["field_accuracy"],
                "field_coverage": metrics["field_coverage"],
                "matched": metrics["matched"],
                "total": metrics["total"],
                "comparisons": comparisons,
            })
            print(
                f"  [{fid}] accuracy={metrics['field_accuracy']:.0%} "
                f"coverage={metrics['field_coverage']:.0%} "
                f"({metrics['matched']}/{metrics['total']} fields)"
            )

    ok = [r for r in per_factor if "error" not in r]
    failed = [r for r in per_factor if "error" in r]
    avg_accuracy = sum(r["field_accuracy"] for r in ok) / len(ok) if ok else 0.0
    avg_coverage = sum(r["field_coverage"] for r in ok) / len(ok) if ok else 0.0

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "model": args.model or None,
        "total_factors": len(per_factor),
        "succeeded": len(ok),
        "failed": len(failed),
        "avg_field_accuracy": avg_accuracy,
        "avg_field_coverage": avg_coverage,
        "per_factor": per_factor,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "extraction_eval_10papers.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Summary ===")
    print(f"total_factors:      {len(per_factor)}")
    print(f"succeeded:          {len(ok)}")
    print(f"failed:             {len(failed)}")
    print(f"avg_field_accuracy: {avg_accuracy:.0%}")
    print(f"avg_field_coverage: {avg_coverage:.0%}")
    if failed:
        print("\nFailed factors:")
        for r in failed:
            print(f"  - {r['factor_id']} ({r['pdf']}): {r['error']}")
    print(f"\nFull report: {report_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
