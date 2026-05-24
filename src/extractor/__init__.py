"""Semantic Extractor - Extract MethodSpec from papers and reference materials.

Implements paper-first extraction (architecture.md Section 4.2):
1. Paper text as primary source (LLM extracts factor definition)
2. Ambiguity tagging for unresolved fields
3. Post-hoc evaluation against C&Z (not feedback)

IMPORTANT: SignalDoc.csv is NOT used as Extractor input (information leakage).
SignalDoc is only used post-hoc for extraction accuracy evaluation.
See cz-reference.md Section 1 for details.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from src.models.method_spec import (
    AmbiguousField,
    BreakpointSource,
    BreakpointSpec,
    EvidenceSource,
    ExtractionSource,
    FieldSource,
    MethodSpec,
    MissingAction,
    MissingPolicy,
    PortfolioSpec,
    RebalanceFrequency,
    SignalSpec,
    SignalTiming,
    WeightingRule,
)


# --- System prompt for paper extraction ---

EXTRACTION_SYSTEM_PROMPT = """\
You are an expert financial economist. Your task is to extract a structured factor \
specification (MethodSpec) from an academic paper.

Extract the following fields from the paper text. If a field is not clearly stated, \
mark it as "unspecified" rather than guessing.

Output a JSON object with exactly these keys:
{
  "factor_name": "string - human-readable factor name",
  "economic_intuition": "string - brief economic rationale (1-2 sentences)",
  "formula": "string - signal construction formula using variable names",
  "required_fields": ["list of Compustat/CRSP field names used"],
  "formation_month": null or int (e.g. 6 for June),
  "rebalance_frequency": "annual" | "quarterly" | "monthly",
  "holding_period": int (months),
  "accounting_lag": int (months, minimum lag before data is available),
  "skip_month": null or int,
  "missing_policy": "drop" | "fill_zero" | "fill_median" | "fill_forward" | "unspecified",
  "universe": "string describing sample universe",
  "breakpoint_source": "nyse" | "full_sample" | "unspecified",
  "breakpoint_quantiles": [list of int percentiles, e.g. [30, 70] or [10, 90]],
  "weighting": "ew" | "vw" | "unspecified",
  "long_leg": "high" | "low" | description,
  "short_leg": "high" | "low" | description,
  "sign": 1 or -1 (long-short direction),
  "paper_sections": ["sections where key info was found"],
  "ambiguous_fields": [{"field": "name", "reason": "why ambiguous"}]
}

Rules:
- Only extract what is EXPLICITLY stated or clearly implied in the text.
- For accounting lag: if paper uses "fiscal year-end data available by June", lag = 6.
- For missing policy: if paper doesn't specify, mark "unspecified".
- Use Compustat field names where possible (ceq, at, lt, sale, ni, etc.).
- Do NOT infer from common practice if paper is silent on a detail.
"""

EXTRACTION_USER_TEMPLATE = """\
Paper text for factor "{factor_id}":

{paper_text}

Available data fields for reference (from data dictionary):
{data_fields}

Extract the MethodSpec as JSON.
"""


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
    raw_llm_output: Optional[dict] = None


class SemanticExtractor:
    """Extracts structured MethodSpec from unstructured paper text.

    Strategy: Paper-first extraction (architecture.md Section 4.2)
    1. LLM extracts from paper text + data dictionary (field name validation)
    2. Ambiguity tagging for unspecified fields
    3. NO SignalDoc input — that's evaluation only

    Acceptance criteria (Phase 1): Core field accuracy >= 80% on pilot factors.
    """

    def __init__(self, llm_client=None, data_dictionary=None):
        """
        Args:
            llm_client: OpenAI-compatible client (must have .chat.completions.create)
            data_dictionary: DataDictionary instance for field validation
        """
        self.llm_client = llm_client
        self.data_dictionary = data_dictionary

    def extract(
        self,
        factor_id: str,
        paper_text: str,
    ) -> ExtractionResult:
        """Extract MethodSpec from paper text only.

        This is the main extraction method. No C&Z metadata or OSAP code
        is provided to avoid information leakage.

        Args:
            factor_id: Unique factor identifier (e.g. "BM", "Mom12m")
            paper_text: Raw paper text (or relevant sections)

        Returns:
            ExtractionResult with MethodSpec and quality metrics
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = ExtractionResult(sources_used=["paper"])

        # Build data dictionary context for field validation
        data_fields = self._get_data_fields_context()

        # Call LLM for extraction
        raw = self._call_llm_extract(factor_id, paper_text, data_fields)
        result.raw_llm_output = raw

        if raw:
            result.spec = self._build_method_spec_from_llm(factor_id, raw)

        return result

    def _call_llm_extract(
        self, factor_id: str, paper_text: str, data_fields: str
    ) -> dict | None:
        """Call LLM to extract structured fields from paper text."""
        user_msg = EXTRACTION_USER_TEMPLATE.format(
            factor_id=factor_id,
            paper_text=paper_text[:30000],  # Truncate to fit context
            data_fields=data_fields,
        )

        try:
            response = self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"  [WARN] LLM extraction failed: {e}")
            return None

    def _build_method_spec_from_llm(
        self, factor_id: str, raw: dict
    ) -> MethodSpec:
        """Convert raw LLM JSON output to a validated MethodSpec."""

        # Parse timing
        timing = SignalTiming(
            formation_month=raw.get("formation_month"),
            rebalance_frequency=self._parse_enum(
                RebalanceFrequency, raw.get("rebalance_frequency"), RebalanceFrequency.ANNUAL
            ),
            holding_period=raw.get("holding_period", 12),
            accounting_lag=raw.get("accounting_lag", 6),
            skip_month=raw.get("skip_month"),
        )

        # Parse missing policy
        missing_action = self._parse_enum(
            MissingAction, raw.get("missing_policy"), MissingAction.DROP
        )
        missing_policy = MissingPolicy(action=missing_action)

        # Parse signal spec
        signal = SignalSpec(
            formula=raw.get("formula", "unspecified"),
            required_fields=raw.get("required_fields", []),
            timing=timing,
            missing_policy=missing_policy,
        )

        # Parse portfolio spec
        bp_source = self._parse_enum(
            BreakpointSource, raw.get("breakpoint_source"), BreakpointSource.NYSE
        )
        quantiles = raw.get("breakpoint_quantiles", [30, 70])
        weighting = self._parse_enum(
            WeightingRule, raw.get("weighting"), WeightingRule.VALUE_WEIGHTED
        )

        portfolio = PortfolioSpec(
            universe=raw.get("universe", "NYSE + AMEX + NASDAQ, common shares only"),
            breakpoints=BreakpointSpec(source=bp_source, quantiles=quantiles),
            weighting=weighting,
            long_leg=raw.get("long_leg", "high"),
            short_leg=raw.get("short_leg", "low"),
        )

        # Parse ambiguous fields
        ambiguous = []
        for item in raw.get("ambiguous_fields", []):
            ambiguous.append(AmbiguousField(
                field=item.get("field", "unknown"),
                reason=item.get("reason", ""),
                source=EvidenceSource.INFERRED,
                confidence="low",
            ))

        # Mark "unspecified" fields as ambiguous too
        if raw.get("missing_policy") == "unspecified":
            ambiguous.append(AmbiguousField(
                field="missing_policy",
                reason="Paper does not specify missing-value handling",
                source=EvidenceSource.INFERRED,
            ))
        if raw.get("breakpoint_source") == "unspecified":
            ambiguous.append(AmbiguousField(
                field="breakpoint_source",
                reason="Paper does not specify breakpoint universe",
                source=EvidenceSource.INFERRED,
            ))
        if raw.get("weighting") == "unspecified":
            ambiguous.append(AmbiguousField(
                field="weighting",
                reason="Paper does not specify portfolio weighting",
                source=EvidenceSource.INFERRED,
            ))

        # Build extraction sources
        sources = [
            ExtractionSource(
                type="paper",
                ref=raw.get("paper_ref", f"Paper for {factor_id}"),
                sections=raw.get("paper_sections", []),
            )
        ]

        return MethodSpec(
            factor_id=factor_id,
            factor_name=raw.get("factor_name", factor_id),
            paper_ref=raw.get("paper_ref", ""),
            economic_intuition=raw.get("economic_intuition", ""),
            signal=signal,
            portfolio=portfolio,
            extraction_sources=sources,
            ambiguous_fields=ambiguous,
            review_status="pending",
        )

    def _get_data_fields_context(self) -> str:
        """Get data dictionary fields as context for LLM."""
        if self.data_dictionary:
            # Return formatted field list from dictionary
            entries = self.data_dictionary.list_fields()
            lines = []
            for entry in entries[:100]:  # Limit to avoid context overflow
                lines.append(
                    f"- {entry.field_name} ({entry.dataset}.{entry.table}): {entry.description}"
                )
            return "\n".join(lines)

        # Fallback: common Compustat/CRSP fields
        return """\
Common Compustat fields (funda): at (total assets), ceq (common equity), lt (total liabilities),
  sale (revenue), ni (net income), oiadp (operating income), dp (depreciation), xrd (R&D),
  capx (capital expenditure), act (current assets), lct (current liabilities), che (cash),
  txditc (deferred taxes), pstkrv/pstkl/pstk (preferred stock), csho (shares outstanding),
  prcc_f (fiscal year-end price), dltt (long-term debt), dlc (current debt)
Common CRSP fields (msf): ret (monthly return), prc (price), shrout (shares outstanding),
  vol (volume), cfacpr (price adjustment factor), cfacshr (share adjustment factor)
"""

    def _parse_enum(self, enum_cls, value, default):
        """Safely parse a string into an enum value."""
        if value is None or value == "unspecified":
            return default
        try:
            return enum_cls(value)
        except ValueError:
            # Try case-insensitive match
            for member in enum_cls:
                if member.value.lower() == str(value).lower():
                    return member
            return default

    # --- Evaluation ---

    def evaluate_extraction(
        self, spec: MethodSpec, ground_truth: dict
    ) -> ExtractionMetrics:
        """Evaluate extraction quality against C&Z ground truth.

        Used for pilot factor validation. This is POST-HOC only —
        results are NOT fed back to correct the MethodSpec.

        Args:
            spec: Extracted MethodSpec
            ground_truth: Dict of field_name -> expected_value from SignalDoc.csv
        """
        total_fields = len(ground_truth)
        if total_fields == 0:
            return ExtractionMetrics()

        matching = 0
        non_empty = 0
        core_fields = {"formula", "accounting_lag", "breakpoints", "weighting"}
        core_matching = 0
        core_total = 0

        for key, expected in ground_truth.items():
            actual = self._get_spec_field(spec, key)
            if actual is not None and str(actual) != "":
                non_empty += 1
                if self._values_match(actual, expected):
                    matching += 1
            if key in core_fields:
                core_total += 1
                if actual is not None and self._values_match(actual, expected):
                    core_matching += 1

        return ExtractionMetrics(
            field_coverage=non_empty / total_fields if total_fields else 0,
            field_accuracy=matching / total_fields if total_fields else 0,
            ambiguity_rate=len(spec.ambiguous_fields) / total_fields if total_fields else 0,
            core_field_accuracy=core_matching / core_total if core_total else 0,
        )

    def _get_spec_field(self, spec: MethodSpec, key: str) -> object:
        """Get a field value from MethodSpec by key name."""
        field_map = {
            "formula": spec.signal.formula,
            "accounting_lag": spec.signal.timing.accounting_lag,
            "breakpoints": spec.portfolio.breakpoints.source.value,
            "weighting": spec.portfolio.weighting.value,
            "formation_month": spec.signal.timing.formation_month,
            "missing_policy": spec.signal.missing_policy.action.value,
            "holding_period": spec.signal.timing.holding_period,
            "rebalance_frequency": spec.signal.timing.rebalance_frequency.value,
            "long_leg": spec.portfolio.long_leg,
            "short_leg": spec.portfolio.short_leg,
            "universe": spec.portfolio.universe,
        }
        return field_map.get(key)

    def _values_match(self, actual, expected) -> bool:
        """Fuzzy match for evaluation."""
        a = str(actual).lower().strip()
        e = str(expected).lower().strip()
        return a == e
