"""Tests for the Semantic Extractor module.

Tests cover:
1. _build_method_spec_from_llm: JSON → MethodSpec conversion
2. _parse_enum: safe enum parsing
3. evaluate_extraction: accuracy metrics against ground truth
4. extract(): end-to-end with REAL LLM (codex CLI)
5. Ambiguity auto-tagging for "unspecified" fields
6. SignalDoc.csv ground truth evaluation (integration)
"""

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.llm import create_llm_client

from src.extractor import (
    ExtractionMetrics,
    ExtractionResult,
    SemanticExtractor,
)
from src.models.method_spec import (
    BreakpointSource,
    EvidenceSource,
    MissingAction,
    MethodSpec,
    RebalanceFrequency,
    WeightingRule,
)


# --- Fixtures ---


MOCK_LLM_RESPONSE_BM = {
    "factor_name": "Book-to-Market",
    "economic_intuition": "Value stocks (high BE/ME) earn higher returns than growth stocks.",
    "detailed_definition": "Log of tangible book equity over market equity",
    "formula": "ceq / (csho * prcc_f)",
    "required_fields": ["ceq", "csho", "prcc_f"],
    "cat_form": "continuous",
    "sign": 1,
    "formation_month": 6,
    "rebalance_frequency": "annual",
    "holding_period": 12,
    "accounting_lag": 6,
    "skip_month": None,
    "stock_weight": "vw",
    "ls_quantile": 0.1,
    "breakpoint_source": "nyse",
    "long_leg": "high",
    "short_leg": "low",
    "filter": "exchcd%in%c(1,2)",
    "universe": "NYSE, AMEX, NASDAQ common stocks",
    "missing_policy": "drop",
    "sample_start_year": 1962,
    "sample_end_year": 1976,
    "paper_ref": "Fama and French (1993)",
    "paper_sections": ["Section III", "Table 1"],
    "ambiguous_fields": [],
}

MOCK_LLM_RESPONSE_WITH_AMBIGUITY = {
    "factor_name": "Accruals",
    "economic_intuition": "Firms with high accruals tend to have lower future returns.",
    "detailed_definition": "Annual change in working capital accruals divided by average total assets",
    "formula": "(act - lct - che + dlc - dp) / at",
    "required_fields": ["act", "lct", "che", "dlc", "dp", "at"],
    "cat_form": "continuous",
    "sign": -1,
    "formation_month": 6,
    "rebalance_frequency": "annual",
    "holding_period": 12,
    "accounting_lag": 6,
    "skip_month": None,
    "stock_weight": "unspecified",
    "ls_quantile": 0.1,
    "breakpoint_source": "unspecified",
    "long_leg": "low",
    "short_leg": "high",
    "filter": "abs(prc)>5",
    "universe": "NYSE, AMEX, NASDAQ",
    "missing_policy": "unspecified",
    "sample_start_year": 1962,
    "sample_end_year": 1991,
    "paper_ref": "Sloan (1996)",
    "paper_sections": ["Section 2"],
    "ambiguous_fields": [
        {"field": "skip_month", "reason": "Paper does not mention skip month"}
    ],
}


def _make_mock_llm(response_dict: dict):
    """Create a mock OpenAI client that returns a fixed JSON response."""
    client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = json.dumps(response_dict)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client.chat.completions.create.return_value = mock_response
    return client


# Check if codex CLI is available
HAS_CODEX = shutil.which("codex") is not None


# --- Tests: _build_method_spec_from_llm ---


class TestBuildMethodSpec:
    """Test JSON → MethodSpec conversion."""

    def setup_method(self):
        self.extractor = SemanticExtractor(llm_client=MagicMock())

    def test_basic_bm_spec(self):
        spec = self.extractor._build_method_spec_from_llm("BM", MOCK_LLM_RESPONSE_BM)

        assert spec.factor_id == "BM"
        assert spec.factor_name == "Book-to-Market"
        assert spec.paper_ref == "Fama and French (1993)"
        assert spec.signal.formula == "ceq / (csho * prcc_f)"
        assert spec.signal.required_fields == ["ceq", "csho", "prcc_f"]
        assert spec.signal.timing.formation_month == 6
        assert spec.signal.timing.rebalance_frequency == RebalanceFrequency.ANNUAL
        assert spec.signal.timing.holding_period == 12
        assert spec.signal.timing.accounting_lag == 6
        assert spec.signal.missing_policy.action == MissingAction.DROP
        assert spec.portfolio.breakpoints.source == BreakpointSource.NYSE
        assert spec.portfolio.breakpoints.quantiles == [30, 70]
        assert spec.portfolio.weighting == WeightingRule.VALUE_WEIGHTED
        assert spec.portfolio.long_leg == "high"
        assert spec.portfolio.short_leg == "low"
        assert spec.review_status == "pending"
        assert len(spec.ambiguous_fields) == 0

    def test_extraction_sources_populated(self):
        spec = self.extractor._build_method_spec_from_llm("BM", MOCK_LLM_RESPONSE_BM)

        assert len(spec.extraction_sources) == 1
        assert spec.extraction_sources[0].type == "paper"
        assert spec.extraction_sources[0].ref == "Fama and French (1993)"
        assert "Section III" in spec.extraction_sources[0].sections

    def test_ambiguity_auto_tagging(self):
        spec = self.extractor._build_method_spec_from_llm("Accruals", MOCK_LLM_RESPONSE_WITH_AMBIGUITY)

        # Should have: 1 from LLM + 3 auto-tagged (missing_policy, breakpoint_source, weighting)
        assert len(spec.ambiguous_fields) == 4

        field_names = [af.field for af in spec.ambiguous_fields]
        assert "skip_month" in field_names
        assert "missing_policy" in field_names
        assert "breakpoint_source" in field_names
        assert "stock_weight" in field_names

        # Auto-tagged should have INFERRED source
        for af in spec.ambiguous_fields:
            assert af.source == EvidenceSource.INFERRED

    def test_defaults_for_missing_fields(self):
        """When LLM returns minimal response, defaults should be sensible."""
        minimal = {
            "factor_name": "TestFactor",
            "formula": "x / y",
        }
        spec = self.extractor._build_method_spec_from_llm("TEST", minimal)

        assert spec.factor_id == "TEST"
        assert spec.signal.timing.accounting_lag == 6  # default
        assert spec.signal.timing.holding_period == 12  # default
        assert spec.signal.timing.rebalance_frequency == RebalanceFrequency.ANNUAL
        assert spec.portfolio.weighting == WeightingRule.VALUE_WEIGHTED
        assert spec.portfolio.breakpoints.source == BreakpointSource.NYSE

    def test_economic_intuition_preserved(self):
        spec = self.extractor._build_method_spec_from_llm("BM", MOCK_LLM_RESPONSE_BM)
        assert "Value stocks" in spec.economic_intuition


# --- Tests: _parse_enum ---


class TestParseEnum:
    def setup_method(self):
        self.extractor = SemanticExtractor(llm_client=MagicMock())

    def test_exact_match(self):
        result = self.extractor._parse_enum(RebalanceFrequency, "annual", RebalanceFrequency.MONTHLY)
        assert result == RebalanceFrequency.ANNUAL

    def test_case_insensitive(self):
        result = self.extractor._parse_enum(WeightingRule, "EW", WeightingRule.VALUE_WEIGHTED)
        assert result == WeightingRule.EQUAL_WEIGHTED

    def test_none_returns_default(self):
        result = self.extractor._parse_enum(MissingAction, None, MissingAction.DROP)
        assert result == MissingAction.DROP

    def test_unspecified_returns_default(self):
        result = self.extractor._parse_enum(BreakpointSource, "unspecified", BreakpointSource.NYSE)
        assert result == BreakpointSource.NYSE

    def test_invalid_value_returns_default(self):
        result = self.extractor._parse_enum(WeightingRule, "invalid_value", WeightingRule.VALUE_WEIGHTED)
        assert result == WeightingRule.VALUE_WEIGHTED


# --- Tests: evaluate_extraction ---


class TestEvaluateExtraction:
    def setup_method(self):
        self.extractor = SemanticExtractor(llm_client=MagicMock())

    def _make_bm_spec(self):
        return self.extractor._build_method_spec_from_llm("BM", MOCK_LLM_RESPONSE_BM)

    def test_perfect_match(self):
        spec = self._make_bm_spec()
        ground_truth = {
            "formula": "ceq / (csho * prcc_f)",
            "accounting_lag": "6",
            "breakpoint_source": "nyse",
            "stock_weight": "vw",
        }
        metrics = self.extractor.evaluate_extraction(spec, ground_truth)

        assert metrics.field_accuracy == 1.0
        assert metrics.core_field_accuracy == 1.0
        assert metrics.field_coverage == 1.0

    def test_partial_match(self):
        spec = self._make_bm_spec()
        ground_truth = {
            "formula": "ceq / (csho * prcc_f)",
            "accounting_lag": "6",
            "breakpoint_source": "full_sample",  # Mismatch
            "stock_weight": "ew",             # Mismatch
        }
        metrics = self.extractor.evaluate_extraction(spec, ground_truth)

        assert metrics.field_accuracy == 0.5  # 2 out of 4 match
        # core fields here: formula, accounting_lag, breakpoint_source, stock_weight (all 4 are core)
        # 2 match out of 4 core = 0.5
        assert metrics.core_field_accuracy == 0.5

    def test_empty_ground_truth(self):
        spec = self._make_bm_spec()
        metrics = self.extractor.evaluate_extraction(spec, {})
        assert metrics.field_accuracy == 0.0
        assert metrics.field_coverage == 0.0

    def test_ambiguity_rate(self):
        spec = self.extractor._build_method_spec_from_llm("Accruals", MOCK_LLM_RESPONSE_WITH_AMBIGUITY)
        ground_truth = {
            "formula": "(act - lct - che + dlc - dp) / at",
            "accounting_lag": "6",
            "breakpoint_source": "nyse",
            "stock_weight": "vw",
        }
        metrics = self.extractor.evaluate_extraction(spec, ground_truth)

        # 4 ambiguous fields / 4 ground truth fields = 1.0
        assert metrics.ambiguity_rate == 1.0

    def test_formation_month_evaluation(self):
        spec = self._make_bm_spec()
        ground_truth = {
            "formation_month": "6",
        }
        metrics = self.extractor.evaluate_extraction(spec, ground_truth)
        assert metrics.field_accuracy == 1.0


# --- Tests: extract() end-to-end with REAL LLM ---

SAMPLE_BM_PAPER_TEXT = """
Fama and French (1993) "Common Risk Factors in the Returns on Stocks and Bonds"

We form portfolios based on book-to-market equity (BE/ME). Book equity is measured
as total stockholders' equity (Compustat item ceq) from fiscal year-end in calendar year t-1.
Market equity is shares outstanding (csho) times stock price (prcc_f) at December of year t-1.

Portfolios are formed in June of each year t using NYSE breakpoints for BE/ME.
Stocks are sorted into deciles based on NYSE breakpoints. The value-weighted (or equal-weighted)
returns of the top 30% (High) minus the bottom 30% (Low) form the HML factor.

We hold portfolios for 12 months from July of year t to June of year t+1.
We require at least 6 months between fiscal year-end and portfolio formation to ensure
data availability (accounting lag of 6 months).

Stocks with negative book equity are excluded. Universe includes NYSE, AMEX, and NASDAQ
common shares (CRSP share codes 10 and 11).
"""


@pytest.mark.skipif(not HAS_CODEX, reason="codex CLI not installed")
class TestExtractEndToEnd:
    """End-to-end extraction tests using REAL codex CLI LLM."""

    def setup_method(self):
        self.llm_client = create_llm_client(provider="codex")
        self.extractor = SemanticExtractor(llm_client=self.llm_client)

    def test_successful_extraction_bm(self):
        """Real LLM should extract BM factor from paper text."""
        result = self.extractor.extract("BM", SAMPLE_BM_PAPER_TEXT)

        assert result.spec is not None
        assert result.spec.factor_id == "BM"
        assert result.spec.signal.formula is not None
        assert len(result.spec.signal.formula) > 3
        assert result.sources_used == ["paper"]
        assert result.raw_llm_output is not None

    def test_extraction_produces_valid_fields(self):
        """Real LLM extraction should have reasonable field values for BM."""
        result = self.extractor.extract("BM", SAMPLE_BM_PAPER_TEXT)

        assert result.spec is not None
        spec = result.spec

        # Formation month should be June (6) based on paper text
        assert spec.signal.timing.formation_month == 6
        # Holding period should be 12
        assert spec.signal.timing.holding_period == 12
        # Accounting lag should be 6
        assert spec.signal.timing.accounting_lag == 6
        # Rebalance should be annual
        from src.models.method_spec import RebalanceFrequency
        assert spec.signal.timing.rebalance_frequency == RebalanceFrequency.ANNUAL

    def test_extraction_captures_required_fields(self):
        """Real LLM should identify key Compustat/CRSP fields."""
        result = self.extractor.extract("BM", SAMPLE_BM_PAPER_TEXT)

        assert result.spec is not None
        fields = result.spec.signal.required_fields

        # Should identify at least some key fields from the paper text
        assert len(fields) >= 2
        # ceq, csho, prcc_f are all mentioned in the text
        field_str = " ".join(fields).lower()
        assert "ceq" in field_str or "book" in field_str

    def test_no_llm_client_raises(self):
        extractor = SemanticExtractor(llm_client=None)
        with pytest.raises(RuntimeError, match="LLM client required"):
            extractor.extract("BM", "paper text")

    def test_extraction_with_minimal_text(self):
        """Even with minimal text, extraction should not crash."""
        result = self.extractor.extract("TEST", "A simple factor: return on equity = net income / book equity.")

        # Should either succeed or gracefully return None spec
        if result.spec is not None:
            assert result.spec.factor_id == "TEST"
            assert result.spec.signal.formula is not None


# --- Tests: SignalDoc.csv ground truth evaluation ---

SIGNALDOC_PATH = Path(__file__).parent.parent / "data" / "osap" / "SignalDoc.csv"


def _parse_signaldoc_row(row: dict) -> dict:
    """Convert a SignalDoc.csv row into ground truth dict for evaluate_extraction().

    Maps SignalDoc columns to MethodSpec field names.
    """
    gt = {}

    # Weighting: "EW" → "ew", "VW" → "vw"
    if row.get("Stock Weight"):
        gt["stock_weight"] = row["Stock Weight"].lower().strip()

    # Formation month
    if row.get("Start Month"):
        try:
            gt["formation_month"] = str(int(float(row["Start Month"])))
        except (ValueError, TypeError):
            pass

    # Holding period
    if row.get("Portfolio Period"):
        try:
            gt["holding_period"] = str(int(float(row["Portfolio Period"])))
        except (ValueError, TypeError):
            pass

    # Sign and long/short direction
    if row.get("Sign"):
        try:
            sign = int(float(row["Sign"]))
            gt["sign"] = str(sign)
            gt["long_leg"] = "high" if sign == 1 else "low"
            gt["short_leg"] = "low" if sign == 1 else "high"
        except (ValueError, TypeError):
            pass

    # LS Quantile
    if row.get("LS Quantile"):
        try:
            gt["ls_quantile"] = str(float(row["LS Quantile"]))
        except (ValueError, TypeError):
            pass

    # Filter
    if row.get("Filter"):
        gt["filter"] = row["Filter"].strip()

    # Cat.Form
    if row.get("Cat.Form"):
        gt["cat_form"] = row["Cat.Form"].strip().lower()

    return gt


def _mock_llm_response_from_signaldoc(row: dict) -> dict:
    """Create a simulated 'perfect' LLM response matching SignalDoc ground truth."""
    sign = 1
    try:
        sign = int(float(row.get("Sign", "1")))
    except (ValueError, TypeError):
        pass

    formation = None
    try:
        formation = int(float(row["Start Month"])) if row.get("Start Month") else None
    except (ValueError, TypeError):
        pass

    holding = 12
    try:
        holding = int(float(row["Portfolio Period"])) if row.get("Portfolio Period") else 12
    except (ValueError, TypeError):
        pass

    weighting = row.get("Stock Weight", "EW").strip().lower()
    if weighting not in ("ew", "vw"):
        weighting = "ew"

    ls_quantile = None
    try:
        ls_quantile = float(row["LS Quantile"]) if row.get("LS Quantile") else None
    except (ValueError, TypeError):
        pass

    return {
        "factor_name": row.get("LongDescription", row.get("Acronym", "")),
        "economic_intuition": "",
        "detailed_definition": row.get("Detailed Definition", "unspecified")[:200],
        "formula": row.get("Detailed Definition", "unspecified")[:200],
        "required_fields": [],
        "cat_form": row.get("Cat.Form", "continuous").strip().lower(),
        "sign": sign,
        "formation_month": formation,
        "rebalance_frequency": "annual",
        "holding_period": holding,
        "accounting_lag": 6,
        "skip_month": None,
        "stock_weight": weighting,
        "ls_quantile": ls_quantile,
        "breakpoint_source": "nyse",
        "long_leg": "high" if sign == 1 else "low",
        "short_leg": "low" if sign == 1 else "high",
        "filter": row.get("Filter", ""),
        "universe": "NYSE + AMEX + NASDAQ",
        "missing_policy": "drop",
        "sample_start_year": None,
        "sample_end_year": None,
        "paper_ref": f"{row.get('Authors', '')} ({row.get('Year', '')})",
        "paper_sections": [],
        "ambiguous_fields": [],
    }


@pytest.mark.skipif(not SIGNALDOC_PATH.exists(), reason="SignalDoc.csv not available")
class TestSignalDocGroundTruth:
    """Integration tests using actual SignalDoc.csv as ground truth.

    Tests that when the LLM produces a 'perfect' extraction matching SignalDoc,
    evaluate_extraction() reports high accuracy. Also validates the ground truth
    parsing pipeline itself.
    """

    def setup_method(self):
        self.extractor = SemanticExtractor(llm_client=MagicMock())
        self.rows = {}
        with open(SIGNALDOC_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.rows[row["Acronym"]] = row

    def test_signaldoc_loads(self):
        """SignalDoc.csv should have 200+ factors."""
        assert len(self.rows) >= 200

    def test_bm_ground_truth_parsing(self):
        """BM row should parse to expected ground truth dict."""
        gt = _parse_signaldoc_row(self.rows["BM"])

        assert gt["stock_weight"] == "ew"
        assert gt["formation_month"] == "6"
        assert gt["holding_period"] == "12"
        assert gt["long_leg"] == "high"
        assert gt["short_leg"] == "low"

    def test_bm_perfect_extraction_scores_100(self):
        """If LLM perfectly matches SignalDoc, accuracy should be 1.0."""
        row = self.rows["BM"]
        llm_response = _mock_llm_response_from_signaldoc(row)
        spec = self.extractor._build_method_spec_from_llm("BM", llm_response)
        gt = _parse_signaldoc_row(row)

        metrics = self.extractor.evaluate_extraction(spec, gt)

        assert metrics.field_accuracy == 1.0
        assert metrics.field_coverage == 1.0

    def test_negative_sign_factor(self):
        """Factors with Sign=-1 should have long_leg=low, short_leg=high."""
        # Find a factor with Sign=-1
        neg_factor = None
        for acronym, row in self.rows.items():
            try:
                if int(float(row.get("Sign", "0"))) == -1:
                    neg_factor = (acronym, row)
                    break
            except (ValueError, TypeError):
                continue

        assert neg_factor is not None, "No negative-sign factor found in SignalDoc"
        acronym, row = neg_factor

        gt = _parse_signaldoc_row(row)
        assert gt["long_leg"] == "low"
        assert gt["short_leg"] == "high"

        # Perfect extraction should score 100%
        llm_response = _mock_llm_response_from_signaldoc(row)
        spec = self.extractor._build_method_spec_from_llm(acronym, llm_response)
        metrics = self.extractor.evaluate_extraction(spec, gt)
        assert metrics.field_accuracy == 1.0

    def test_batch_pilot_factors(self):
        """Test evaluation pipeline on several pilot factors."""
        pilot_factors = ["BM", "Mom12m", "GP", "EP", "Investment"]
        results = {}

        for factor_id in pilot_factors:
            if factor_id not in self.rows:
                continue
            row = self.rows[factor_id]
            llm_response = _mock_llm_response_from_signaldoc(row)
            spec = self.extractor._build_method_spec_from_llm(factor_id, llm_response)
            gt = _parse_signaldoc_row(row)
            metrics = self.extractor.evaluate_extraction(spec, gt)
            results[factor_id] = metrics

        # All available pilot factors should score perfectly with mock "perfect" LLM
        for factor_id, metrics in results.items():
            assert metrics.field_accuracy == 1.0, f"{factor_id} accuracy: {metrics.field_accuracy}"

    def test_imperfect_extraction_detected(self):
        """When LLM output disagrees with SignalDoc, accuracy should drop."""
        row = self.rows["BM"]
        llm_response = _mock_llm_response_from_signaldoc(row)
        # Deliberately introduce errors
        llm_response["stock_weight"] = "vw"  # BM in SignalDoc is EW
        llm_response["formation_month"] = 12  # Should be 6

        spec = self.extractor._build_method_spec_from_llm("BM", llm_response)
        gt = _parse_signaldoc_row(row)
        metrics = self.extractor.evaluate_extraction(spec, gt)

        # 2 out of 5 fields wrong
        assert metrics.field_accuracy < 1.0
        assert metrics.field_accuracy > 0.0

    def test_all_factors_parseable(self):
        """Every SignalDoc row should parse without errors."""
        parsed_count = 0
        for acronym, row in self.rows.items():
            gt = _parse_signaldoc_row(row)
            # Should be a valid dict (some rows may have empty fields)
            assert isinstance(gt, dict), f"{acronym} did not return dict"
            if gt:
                parsed_count += 1
        # Most factors should produce at least some ground truth fields
        assert parsed_count >= 200
