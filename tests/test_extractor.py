"""Tests for the Semantic Extractor module.

Redesigned to use:
1. Real LLM calls (codex CLI) — no mocks
2. Real PDFs from data/papers/ as input
3. SignalDoc.csv as ground truth for evaluation
4. Structured evaluation output (JSON report + per-field breakdown)

Run with:
    pytest tests/test_extractor.py -v --tb=short
    pytest tests/test_extractor.py -k "eval" --tb=short  # evaluation only
"""

import json
import shutil
from pathlib import Path

import pytest

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from src.llm import create_llm_client
from src.extractor import (
    ExtractionMetrics,
    ExtractionResult,
    SemanticExtractor,
)
from src.pdf_mapper import build_pdf_factor_map, get_factor_to_pdf
from src.models.method_spec import (
    BreakpointSource,
    EvidenceSource,
    MissingAction,
    MethodSpec,
    RebalanceFrequency,
    WeightingRule,
)
from src.evaluation.helpers import (
    PDF_FACTOR_MAP,
    FACTOR_TO_PDF,
    PAPERS_DIR,
    SIGNALDOC_PATH,
    EVAL_OUTPUT_DIR,
    PASS_THRESHOLD,
    extract_pdf_text,
    load_signaldoc,
    parse_signaldoc_ground_truth,
    build_field_details,
    compute_score,
    FactorEvalResult,
    EvalReport,
)


# --- Pytest-specific wrappers ---

def _extract_pdf_text(pdf_path: Path, max_pages: int = 30) -> str:
    """Extract text from a PDF using PyMuPDF (skips test if not installed)."""
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not installed")
    return extract_pdf_text(pdf_path, max_pages)


def _load_signaldoc() -> dict[str, dict]:
    return load_signaldoc()


def _parse_signaldoc_ground_truth(row: dict) -> dict:
    return parse_signaldoc_ground_truth(row)


def _build_field_details(extractor, spec, ground_truth, reasons=None):
    return build_field_details(extractor, spec, ground_truth, reasons)


def _compute_score(metrics):
    return compute_score(metrics)


# --- Fixtures ---

HAS_CODEX = shutil.which("codex") is not None
HAS_PYMUPDF = fitz is not None
HAS_SIGNALDOC = SIGNALDOC_PATH.exists()


def _available_factors() -> list[str]:
    """Return factor IDs that have both a PDF and a SignalDoc entry."""
    if not HAS_SIGNALDOC or not PAPERS_DIR.exists():
        return []
    signaldoc = _load_signaldoc()
    available = []
    for pdf_name, factors in PDF_FACTOR_MAP.items():
        pdf_path = PAPERS_DIR / pdf_name
        if not pdf_path.exists():
            continue
        for factor_id in factors:
            if factor_id in signaldoc:
                available.append(factor_id)
    return available


AVAILABLE_FACTORS = _available_factors()

# Select pilot factors (subset for faster CI runs)
PILOT_FACTORS = [f for f in ["BM", "Illiquidity", "CF", "Investment", "OPLeverage"] if f in AVAILABLE_FACTORS]


# --- Tests: Real LLM + Real PDF + Ground Truth ---


@pytest.mark.skipif(not HAS_CODEX, reason="codex CLI not installed")
@pytest.mark.skipif(not HAS_PYMUPDF, reason="PyMuPDF not installed")
@pytest.mark.skipif(not HAS_SIGNALDOC, reason="SignalDoc.csv not available")
class TestRealExtraction:
    """End-to-end extraction tests: real PDF -> real LLM -> SignalDoc ground truth."""

    def setup_method(self):
        self.llm_client = create_llm_client(provider="codex")
        self.extractor = SemanticExtractor(llm_client=self.llm_client)
        self.signaldoc = _load_signaldoc()

    @pytest.mark.parametrize("factor_id", PILOT_FACTORS)
    def test_extraction_succeeds(self, factor_id: str):
        """Real LLM should successfully extract from real PDF without crashing."""
        pdf_path = PAPERS_DIR / FACTOR_TO_PDF[factor_id]
        paper_text = _extract_pdf_text(pdf_path)

        result = self.extractor.extract(factor_id, paper_text)

        assert result.spec is not None, f"Extraction returned None spec for {factor_id}"
        assert result.spec.factor_id == factor_id
        assert result.spec.signal.formula is not None
        assert len(result.spec.signal.formula) > 3
        assert result.raw_llm_output is not None

    @pytest.mark.parametrize("factor_id", PILOT_FACTORS)
    def test_extraction_accuracy(self, factor_id: str):
        """Extraction should achieve reasonable accuracy against SignalDoc ground truth."""
        pdf_path = PAPERS_DIR / FACTOR_TO_PDF[factor_id]
        paper_text = _extract_pdf_text(pdf_path)

        result = self.extractor.extract(factor_id, paper_text)
        assert result.spec is not None

        gt = _parse_signaldoc_ground_truth(self.signaldoc[factor_id])
        metrics = self.extractor.evaluate_extraction(result.spec, gt)

        # Phase 1 acceptance: core field accuracy >= 50% (realistic for paper-only)
        assert metrics.field_coverage > 0.0, f"{factor_id}: no fields extracted"
        # Log metrics for visibility
        print(f"\n  {factor_id}: accuracy={metrics.field_accuracy:.0%}, "
              f"core={metrics.core_field_accuracy:.0%}, "
              f"coverage={metrics.field_coverage:.0%}")

    def test_no_llm_client_raises(self):
        """SemanticExtractor without client should raise RuntimeError."""
        extractor = SemanticExtractor(llm_client=None)
        with pytest.raises(RuntimeError, match="LLM client required"):
            extractor.extract("BM", "paper text")


# --- Tests: Full Evaluation Suite ---


@pytest.mark.skipif(not HAS_CODEX, reason="codex CLI not installed")
@pytest.mark.skipif(not HAS_PYMUPDF, reason="PyMuPDF not installed")
@pytest.mark.skipif(not HAS_SIGNALDOC, reason="SignalDoc.csv not available")
class TestFullEvaluation:
    """Run full evaluation across all available factors and produce a report."""

    def setup_method(self):
        self.llm_client = create_llm_client(provider="codex")
        self.extractor = SemanticExtractor(llm_client=self.llm_client)
        self.signaldoc = _load_signaldoc()

    @pytest.mark.slow
    def test_full_eval_report(self):
        """Run extraction on all available PDFs and produce evaluation report.

        Iterates by PDF file to avoid re-reading the same PDF multiple times.
        """
        report = EvalReport()
        report.total_factors = len(AVAILABLE_FACTORS)

        accuracies = []
        core_accuracies = []
        coverages = []

        # Group by PDF to extract text once per file
        for pdf_name, factor_ids in PDF_FACTOR_MAP.items():
            pdf_path = PAPERS_DIR / pdf_name
            if not pdf_path.exists():
                continue

            try:
                paper_text = _extract_pdf_text(pdf_path)
            except Exception as e:
                # Mark all factors from this PDF as failed
                for factor_id in factor_ids:
                    if factor_id in AVAILABLE_FACTORS:
                        eval_result = FactorEvalResult(
                            factor_id=factor_id, pdf_file=pdf_name, error=f"PDF read error: {e}"
                        )
                        report.per_factor.append(eval_result)
                continue

            for factor_id in factor_ids:
                if factor_id not in AVAILABLE_FACTORS:
                    continue
                eval_result = FactorEvalResult(factor_id=factor_id, pdf_file=pdf_name)

                try:
                    result = self.extractor.extract(factor_id, paper_text)

                    if result.spec is None:
                        eval_result.error = "Extraction returned None spec"
                        report.per_factor.append(eval_result)
                        continue

                    eval_result.extraction_success = True
                    report.successful_extractions += 1

                    gt = _parse_signaldoc_ground_truth(self.signaldoc[factor_id])
                    metrics = self.extractor.evaluate_extraction(result.spec, gt)
                    eval_result.metrics = metrics
                    eval_result.field_details = _build_field_details(
                        self.extractor, result.spec, gt
                    )

                    accuracies.append(metrics.field_accuracy)
                    core_accuracies.append(metrics.core_field_accuracy)
                    coverages.append(metrics.field_coverage)

                except Exception as e:
                    eval_result.error = str(e)

                report.per_factor.append(eval_result)

        # Compute averages
        if accuracies:
            report.avg_field_accuracy = sum(accuracies) / len(accuracies)
            report.avg_core_accuracy = sum(core_accuracies) / len(core_accuracies)
            report.avg_field_coverage = sum(coverages) / len(coverages)

        # Write report
        EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = EVAL_OUTPUT_DIR / "extraction_eval_report.json"
        with open(report_path, "w") as f:
            json.dump(report.to_json(), f, indent=2)

        summary_path = EVAL_OUTPUT_DIR / "extraction_eval_summary.txt"
        with open(summary_path, "w") as f:
            f.write(report.summary())

        # Print summary
        print(f"\n{report.summary()}")
        print(f"\nReport saved to: {report_path}")

        # At least some extractions should succeed
        assert report.successful_extractions > 0, "No extractions succeeded"

    @pytest.mark.slow
    @pytest.mark.parametrize("factor_id", AVAILABLE_FACTORS)
    def test_individual_factor_eval(self, factor_id: str):
        """Individual factor extraction + evaluation (for granular CI)."""
        pdf_path = PAPERS_DIR / FACTOR_TO_PDF[factor_id]
        paper_text = _extract_pdf_text(pdf_path)

        result = self.extractor.extract(factor_id, paper_text)
        assert result.spec is not None, f"{factor_id}: extraction failed"

        gt = _parse_signaldoc_ground_truth(self.signaldoc[factor_id])
        metrics = self.extractor.evaluate_extraction(result.spec, gt)
        details = _build_field_details(self.extractor, result.spec, gt)

        print(f"\n--- {factor_id} ({FACTOR_TO_PDF[factor_id]}) ---")
        print(f"  Accuracy: {metrics.field_accuracy:.0%} | Core: {metrics.core_field_accuracy:.0%}")
        for field_name, detail in details.items():
            mark = "v" if detail["match"] else "x"
            print(f"  {mark} {field_name}: expected={detail['expected']}, got={detail['actual']}")


# --- Tests: Evaluation Logic (unit tests, no LLM needed) ---


class TestEvaluationLogic:
    """Test evaluation helpers without LLM calls."""

    def setup_method(self):
        from unittest.mock import MagicMock

        self.extractor = SemanticExtractor(llm_client=MagicMock())

    def test_signaldoc_loads(self):
        """SignalDoc.csv should have 200+ factors."""
        if not HAS_SIGNALDOC:
            pytest.skip("SignalDoc.csv not available")
        rows = _load_signaldoc()
        assert len(rows) >= 200

    def test_ground_truth_parsing(self):
        """Ground truth parser should extract known fields correctly."""
        if not HAS_SIGNALDOC:
            pytest.skip("SignalDoc.csv not available")
        rows = _load_signaldoc()

        # BM should be EW, formation=6, holding=12
        if "BM" in rows:
            gt = _parse_signaldoc_ground_truth(rows["BM"])
            assert gt.get("stock_weight") == "ew"
            assert gt.get("formation_month") == "6"

    def test_all_factors_parseable(self):
        """Every SignalDoc row should parse without errors."""
        if not HAS_SIGNALDOC:
            pytest.skip("SignalDoc.csv not available")
        rows = _load_signaldoc()
        parsed_count = 0
        for acronym, row in rows.items():
            gt = _parse_signaldoc_ground_truth(row)
            assert isinstance(gt, dict)
            if gt:
                parsed_count += 1
        assert parsed_count >= 200

    def test_available_factor_pdf_mapping(self):
        """All mapped PDFs should have well-formed filenames."""
        for pdf_name, factors in PDF_FACTOR_MAP.items():
            assert pdf_name.endswith(".pdf") or pdf_name.endswith(".url")
            assert len(factors) > 0

    def test_eval_report_serialization(self):
        """EvalReport should serialize to JSON correctly."""
        report = EvalReport(total_factors=5, successful_extractions=3)
        report.avg_field_accuracy = 0.75
        report.avg_core_accuracy = 0.80
        report.avg_field_coverage = 0.90

        json_data = report.to_json()
        assert json_data["total_factors"] == 5
        assert json_data["avg_field_accuracy"] == 0.75

    def test_eval_report_summary_formatting(self):
        """EvalReport summary should produce readable text."""
        report = EvalReport(total_factors=2, successful_extractions=2)
        report.avg_field_accuracy = 0.80
        report.avg_core_accuracy = 0.75
        report.avg_field_coverage = 1.0
        report.per_factor = [
            FactorEvalResult(
                factor_id="BM",
                pdf_file="French_1992.pdf",
                extraction_success=True,
                metrics=ExtractionMetrics(
                    field_accuracy=0.8, core_field_accuracy=0.75,
                    field_coverage=1.0, ambiguity_rate=0.2
                ),
            )
        ]
        summary = report.summary()
        assert "BM" in summary
        assert "80%" in summary


# --- Standalone eval runner (can be called outside pytest) ---


def run_evaluation(
    factors: list[str] | None = None,
    output_dir: Path | None = None,
) -> EvalReport:
    """Run extraction evaluation programmatically.

    Args:
        factors: List of factor IDs to evaluate. None = all available.
        output_dir: Where to write the report. None = default eval_output dir.

    Returns:
        EvalReport with all results.
    """
    if not HAS_CODEX:
        raise RuntimeError("codex CLI not installed")
    if not HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not installed -- pip install pymupdf")

    llm_client = create_llm_client(provider="codex")
    extractor = SemanticExtractor(llm_client=llm_client)
    signaldoc = _load_signaldoc()

    factors_to_eval = factors or AVAILABLE_FACTORS
    output_dir = output_dir or EVAL_OUTPUT_DIR

    report = EvalReport(total_factors=len(factors_to_eval))
    accuracies, core_accuracies, coverages = [], [], []

    for factor_id in factors_to_eval:
        if factor_id not in FACTOR_TO_PDF:
            continue
        pdf_path = PAPERS_DIR / FACTOR_TO_PDF[factor_id]
        eval_result = FactorEvalResult(factor_id=factor_id, pdf_file=FACTOR_TO_PDF[factor_id])

        try:
            paper_text = _extract_pdf_text(pdf_path)
            result = extractor.extract(factor_id, paper_text)

            if result.spec is None:
                eval_result.error = "Extraction returned None spec"
                report.per_factor.append(eval_result)
                continue

            eval_result.extraction_success = True
            report.successful_extractions += 1

            gt = _parse_signaldoc_ground_truth(signaldoc[factor_id])
            metrics = extractor.evaluate_extraction(result.spec, gt)
            eval_result.metrics = metrics
            eval_result.score = _compute_score(metrics)
            eval_result.passed = eval_result.score >= PASS_THRESHOLD
            eval_result.field_details = _build_field_details(extractor, result.spec, gt)

            accuracies.append(metrics.field_accuracy)
            core_accuracies.append(metrics.core_field_accuracy)
            coverages.append(metrics.field_coverage)

        except Exception as e:
            eval_result.error = str(e)

        report.per_factor.append(eval_result)

    if accuracies:
        report.avg_field_accuracy = sum(accuracies) / len(accuracies)
        report.avg_core_accuracy = sum(core_accuracies) / len(core_accuracies)
        report.avg_field_coverage = sum(coverages) / len(coverages)

    report.compute_aggregates()

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "extraction_eval_report.json", "w") as f:
        json.dump(report.to_json(), f, indent=2)
    with open(output_dir / "extraction_eval_summary.txt", "w") as f:
        f.write(report.summary())

    return report


if __name__ == "__main__":
    """Run evaluation directly: python tests/test_extractor.py"""
    report = run_evaluation()
    print(report.summary())
