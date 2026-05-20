"""Semantic Extractor - Extract MethodSpec from papers and reference materials."""

from __future__ import annotations

from src.models.method_spec import MethodSpec


class SemanticExtractor:
    """Extracts structured MethodSpec from unstructured paper text and reference code.

    Uses LLM to parse:
    - Factor definition and formula
    - Data requirements
    - Timing assumptions
    - Portfolio construction rules
    - Missing-value policies
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def extract_from_paper(self, paper_text: str, factor_id: str) -> MethodSpec:
        """Extract MethodSpec from paper text using LLM."""
        # TODO: Implement LLM-based extraction
        raise NotImplementedError

    def extract_from_reference_code(self, code: str, factor_id: str) -> dict:
        """Extract implementation details from reference code (C&Z / OSAP)."""
        # TODO: Implement code analysis
        raise NotImplementedError

    def merge_sources(
        self,
        paper_spec: MethodSpec,
        code_details: dict,
        metadata: dict | None = None,
    ) -> MethodSpec:
        """Merge information from multiple sources, flagging conflicts."""
        # TODO: Implement source merging with conflict detection
        raise NotImplementedError
