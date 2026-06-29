"""Shared evaluation helpers used by both app.py and tests.

This module contains no pytest dependency — safe to import from Streamlit.
"""

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from src.steps.extractor import ExtractionMetrics, SemanticExtractor
from src.infra.models.method_spec import MethodSpec
from src.infra.pdf_mapper import build_pdf_factor_map, get_factor_to_pdf


# --- Paths ---

PAPERS_DIR = Path(__file__).parent.parent.parent / "data" / "papers"
PAPERS_MD_DIR = Path(__file__).parent.parent.parent / "data" / "papers_md"
SIGNALDOC_PATH = Path(__file__).parent.parent.parent / "data" / "osap" / "SignalDoc.csv"
EVAL_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "eval_output"


# --- PDF → Factor mapping ---

PDF_FACTOR_MAP: dict[str, list[str]] = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH)
FACTOR_TO_PDF: dict[str, str] = {
    factor: pdf
    for pdf, factors in PDF_FACTOR_MAP.items()
    for factor in factors
}


# --- Constants ---

PASS_THRESHOLD = 80  # Score >= 80 means pass


# --- Helpers ---


def extract_pdf_text(pdf_path: Path, max_pages: int = 30) -> str:
    """Get paper text — prefers pre-converted MD file, falls back to PyMuPDF extraction."""
    # Check for pre-converted markdown
    md_path = PAPERS_MD_DIR / pdf_path.with_suffix(".md").name
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")

    # Fallback: extract from PDF directly
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) not installed — pip install pymupdf")
    doc = fitz.open(str(pdf_path))
    text_parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def load_signaldoc(signaldoc_path: Path | None = None) -> dict[str, dict]:
    """Load SignalDoc.csv into {Acronym: row_dict}."""
    path = signaldoc_path or SIGNALDOC_PATH
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[row["Acronym"]] = row
    return rows


# Common Compustat/CRSP variable names to extract from Detailed Definition
_KNOWN_VARIABLES = {
    "at", "ceq", "csho", "prcc_f", "ib", "oancf", "act", "che", "lct", "dlc",
    "dp", "txp", "sale", "revt", "cogs", "xsga", "ni", "ebitda", "ppegt",
    "ppent", "invt", "rect", "lt", "dltt", "pstk", "mib", "seq", "txditc",
    "pstkrv", "pstkl", "re", "bkvlps", "dvc", "dvp", "prc", "ret", "vol",
    "shrout", "me", "mktrf", "rf", "fopt", "xrd", "capx", "ivao", "dlt",
}


def _extract_formula_keywords(detailed_def: str) -> list[str]:
    """Extract Compustat/CRSP variable names from SignalDoc Detailed Definition."""
    if not detailed_def:
        return []
    text_lower = detailed_def.lower()
    found = []

    paren_matches = re.findall(r"\(([a-z_]+)\)", text_lower)
    for m in paren_matches:
        if m in _KNOWN_VARIABLES:
            found.append(m)

    tokens = set(re.findall(r"\b([a-z_]+)\b", text_lower))
    for var in _KNOWN_VARIABLES:
        if var in tokens and var not in found:
            found.append(var)

    return sorted(set(found))


def parse_signaldoc_ground_truth(row: dict) -> dict:
    """Convert a SignalDoc.csv row into ground truth dict for evaluation."""
    gt = {}

    if row.get("Stock Weight"):
        gt["stock_weight"] = row["Stock Weight"].lower().strip()

    formation_month = None
    if row.get("Start Month"):
        try:
            formation_month = int(float(row["Start Month"]))
            gt["formation_month"] = str(formation_month)
        except (ValueError, TypeError):
            pass

    holding_period = None
    if row.get("Portfolio Period"):
        try:
            holding_period = int(float(row["Portfolio Period"]))
            gt["holding_period"] = str(holding_period)
        except (ValueError, TypeError):
            pass

    if row.get("Sign"):
        try:
            sign = int(float(row["Sign"]))
            gt["sign"] = str(sign)
            gt["long_leg"] = "high" if sign == 1 else "low"
            gt["short_leg"] = "low" if sign == 1 else "high"
        except (ValueError, TypeError):
            pass

    if row.get("LS Quantile"):
        try:
            gt["ls_quantile"] = str(float(row["LS Quantile"]))
        except (ValueError, TypeError):
            pass

    if row.get("Filter"):
        gt["filter"] = row["Filter"].strip()

    if row.get("Cat.Form"):
        gt["cat_form"] = row["Cat.Form"].strip().lower()

    detailed_def = row.get("Detailed Definition", "")
    keywords = _extract_formula_keywords(detailed_def)
    if keywords:
        gt["formula_keywords"] = ",".join(keywords)

    if row.get("SampleStartYear"):
        try:
            gt["sample_start_year"] = str(int(float(row["SampleStartYear"])))
        except (ValueError, TypeError):
            pass

    if row.get("SampleEndYear"):
        try:
            gt["sample_end_year"] = str(int(float(row["SampleEndYear"])))
        except (ValueError, TypeError):
            pass

    if holding_period is not None:
        if holding_period == 1:
            gt["rebalance_frequency"] = "monthly"
        elif holding_period == 12:
            gt["rebalance_frequency"] = "annual"
        elif holding_period == 3:
            gt["rebalance_frequency"] = "quarterly"

    if formation_month == 6:
        gt["accounting_lag"] = "6"

    return gt


def compute_score(metrics: Optional[ExtractionMetrics]) -> float:
    """Compute a 0-100 score from ExtractionMetrics."""
    if metrics is None:
        return 0.0
    return round(metrics.field_accuracy * 100, 1)


@dataclass
class FactorEvalResult:
    """Evaluation result for a single factor."""

    factor_id: str
    pdf_file: str
    metrics: Optional[ExtractionMetrics] = None
    field_details: dict = None
    extraction_success: bool = False
    error: Optional[str] = None
    score: float = 0.0
    passed: bool = False

    def __post_init__(self):
        if self.field_details is None:
            self.field_details = {}
        if self.metrics and self.score == 0.0:
            self.score = compute_score(self.metrics)
            self.passed = self.score >= PASS_THRESHOLD


@dataclass
class EvalReport:
    """Aggregate evaluation report across all factors."""

    total_factors: int = 0
    successful_extractions: int = 0
    avg_field_accuracy: float = 0.0
    avg_core_accuracy: float = 0.0
    avg_field_coverage: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    per_factor: list = None

    def __post_init__(self):
        if self.per_factor is None:
            self.per_factor = []

    def compute_aggregates(self):
        if not self.per_factor:
            return
        self.passed_count = sum(1 for r in self.per_factor if r.passed)
        self.failed_count = self.total_factors - self.passed_count
        self.pass_rate = self.passed_count / self.total_factors if self.total_factors else 0.0
        scores = [r.score for r in self.per_factor if r.extraction_success]
        self.avg_score = sum(scores) / len(scores) if scores else 0.0

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "EXTRACTION EVALUATION REPORT",
            "=" * 60,
            f"Total factors tested:     {self.total_factors}",
            f"Successful extractions:   {self.successful_extractions}",
            f"Passed (>={PASS_THRESHOLD}):          {self.passed_count}",
            f"Failed (<{PASS_THRESHOLD}):            {self.failed_count}",
            f"Pass rate:                {self.pass_rate:.1%}",
            f"Avg score:                {self.avg_score:.1f}/100",
            f"Avg field accuracy:       {self.avg_field_accuracy:.1%}",
            f"Avg core field accuracy:  {self.avg_core_accuracy:.1%}",
            f"Avg field coverage:       {self.avg_field_coverage:.1%}",
            "-" * 60,
        ]
        for r in self.per_factor:
            status = "PASS" if r.passed else "FAIL"
            acc = f"{r.score:.0f}/100" if r.extraction_success else "N/A"
            lines.append(f"  [{status}] {r.factor_id:<20} score={acc}  pdf={r.pdf_file}")
            if r.field_details:
                for field_name, detail in r.field_details.items():
                    mark = "v" if detail["match"] else "x"
                    lines.append(
                        f"        {mark} {field_name}: expected={detail['expected']}, got={detail['actual']}"
                    )
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "total_factors": self.total_factors,
            "successful_extractions": self.successful_extractions,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "avg_field_accuracy": self.avg_field_accuracy,
            "avg_core_accuracy": self.avg_core_accuracy,
            "avg_field_coverage": self.avg_field_coverage,
            "per_factor": [
                {
                    "factor_id": r.factor_id,
                    "pdf_file": r.pdf_file,
                    "extraction_success": r.extraction_success,
                    "score": r.score,
                    "passed": r.passed,
                    "error": r.error,
                    "metrics": asdict(r.metrics) if r.metrics else None,
                    "field_details": r.field_details,
                }
                for r in self.per_factor
            ],
        }


def build_field_details(
    extractor: SemanticExtractor, spec: MethodSpec, ground_truth: dict,
    reasons: dict[str, str] | None = None,
) -> dict:
    """Build per-field comparison detail dict."""
    reasons = reasons or {}
    details = {}
    for key, expected in ground_truth.items():
        if expected is None or str(expected).strip().lower() in ("", "none", "unspecified", "n/a", "nan"):
            details[key] = {
                "expected": expected,
                "actual": "N/A (ground truth unspecified)",
                "match": True,
                "reason": reasons.get(key, ""),
            }
            continue

        actual = extractor._get_spec_field(spec, key)
        match = extractor._values_match(actual, expected, field_key=key) if actual is not None else False
        details[key] = {
            "expected": expected,
            "actual": str(actual) if actual is not None else None,
            "match": match,
            "reason": reasons.get(key, ""),
        }
    return details
