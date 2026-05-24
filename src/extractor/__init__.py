"""Semantic Extractor - Extract MethodSpec from papers and reference materials.

Implements multi-source triangulation (architecture.md Section 4.2):
1. Structured source first (C&Z metadata, OSAP code)
2. Paper fill-in for missing/ambiguous fields
3. Ambiguity tagging for unresolved fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.data_layer import DataDictionary
from src.models.method_spec import (
    AmbiguousField,
    EvidenceSource,
    ExtractionSource,
    MethodSpec,
    SignalSpec,
)


@dataclass
class ExtractionMetrics:
    """Metrics for evaluating extraction quality (Section 4.2).

    Used against C&Z metadata as ground truth for pilot factors.
    """

    field_coverage: float = 0.0       # non-empty fields / total fields
    field_accuracy: float = 0.0       # fields matching C&Z / comparable fields
    ambiguity_rate: float = 0.0       # ambiguous_fields count / total fields
    core_field_accuracy: float = 0.0  # formula, lag, breakpoints, weighting accuracy


@dataclass
class ExtractionResult:
    """Result from a single extraction attempt."""

    spec: Optional[MethodSpec] = None
    metrics: Optional[ExtractionMetrics] = None
    sources_used: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


class SemanticExtractor:
    """Extracts structured MethodSpec from unstructured paper text and reference code.

    Strategy: Multi-source triangulation
    1. Structured source first: C&Z metadata and OSAP reference code (high accuracy)
    2. Paper fill-in: For missing/ambiguous fields (lag, missing policy, skip month)
    3. Ambiguity tagging: Unresolved fields marked with source and confidence

    Acceptance criteria (Phase 1): Core field accuracy >= 80% on pilot factors.
    """

    def __init__(self, llm_client=None, data_dictionary: Optional[DataDictionary] = None):
        self.llm_client = llm_client
        self.data_dictionary = data_dictionary

    def extract(
        self,
        factor_id: str,
        paper_text: str | None = None,
        cz_metadata: dict | None = None,
        osap_code: str | None = None,
    ) -> ExtractionResult:
        """Full multi-source extraction pipeline.

        Args:
            factor_id: Unique factor identifier
            paper_text: Raw paper text (optional)
            cz_metadata: C&Z SignalDoc metadata row (optional)
            osap_code: OSAP reference implementation code (optional)

        Returns:
            ExtractionResult with MethodSpec and quality metrics
        """
        result = ExtractionResult()

        # Step 1: Extract from structured sources first
        structured_fields = {}
        if cz_metadata:
            structured_fields.update(self._extract_from_cz(cz_metadata))
            result.sources_used.append("cz_metadata")
        if osap_code:
            code_fields = self._extract_from_osap(osap_code)
            # Detect conflicts with structured_fields
            for key, val in code_fields.items():
                if key in structured_fields and structured_fields[key] != val:
                    result.conflicts.append(
                        f"{key}: cz='{structured_fields[key]}' vs osap='{val}'"
                    )
            structured_fields.update(code_fields)
            result.sources_used.append("osap_code")

        # Step 2: Paper fill-in for missing fields
        paper_fields = {}
        if paper_text:
            paper_fields = self._extract_from_paper(paper_text, factor_id)
            result.sources_used.append("paper")

        # Step 3: Merge and tag ambiguities
        result.spec = self._build_method_spec(
            factor_id, structured_fields, paper_fields, result.conflicts
        )

        return result

    def _extract_from_cz(self, metadata: dict) -> dict:
        """Extract fields from C&Z SignalDoc metadata (structured, high accuracy)."""
        # TODO: Parse C&Z metadata CSV row into field dict
        raise NotImplementedError

    def _extract_from_osap(self, code: str) -> dict:
        """Extract implementation details from OSAP reference code."""
        # TODO: Use LLM to parse SAS/R/Stata code
        raise NotImplementedError

    def _extract_from_paper(self, paper_text: str, factor_id: str) -> dict:
        """Extract fields from paper text using LLM (for missing fields)."""
        # TODO: LLM-based extraction with structured prompting
        raise NotImplementedError

    def _build_method_spec(
        self,
        factor_id: str,
        structured: dict,
        paper: dict,
        conflicts: list[str],
    ) -> MethodSpec:
        """Merge sources into final MethodSpec, tagging ambiguities."""
        # TODO: Implement merge logic with ambiguity tagging
        raise NotImplementedError

    def evaluate_extraction(
        self, spec: MethodSpec, ground_truth: dict
    ) -> ExtractionMetrics:
        """Evaluate extraction quality against C&Z ground truth.

        Used for pilot factor validation.
        """
        total_fields = len(ground_truth)
        if total_fields == 0:
            return ExtractionMetrics()

        matching = 0
        core_fields = ["formula", "accounting_lag", "breakpoints", "weighting"]
        core_matching = 0
        core_total = 0

        for key, expected in ground_truth.items():
            actual = self._get_spec_field(spec, key)
            if actual is not None:
                if str(actual) == str(expected):
                    matching += 1
            if key in core_fields:
                core_total += 1
                if actual is not None and str(actual) == str(expected):
                    core_matching += 1

        return ExtractionMetrics(
            field_coverage=1.0,  # TODO: count non-empty
            field_accuracy=matching / total_fields if total_fields else 0,
            ambiguity_rate=len(spec.ambiguous_fields) / total_fields if total_fields else 0,
            core_field_accuracy=core_matching / core_total if core_total else 0,
        )

    def _get_spec_field(self, spec: MethodSpec, key: str) -> object:
        """Get a field value from MethodSpec by key name."""
        # Simple accessor for evaluation
        field_map = {
            "formula": spec.signal.formula,
            "accounting_lag": spec.signal.timing.accounting_lag,
            "breakpoints": spec.portfolio.breakpoints.source.value,
            "weighting": spec.portfolio.weighting.value,
            "formation_month": spec.signal.timing.formation_month,
            "missing_policy": spec.signal.missing_policy.action.value,
        }
        return field_map.get(key)
