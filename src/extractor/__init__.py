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
import time
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


def _enum_choices(enum_cls) -> str:
    """Return pipe-separated enum values, e.g. '"annual" | "quarterly" | "monthly"'."""
    return " | ".join(f'"{m.value}"' for m in enum_cls)


# Schema field definitions — single source of truth for the extraction prompt.
# Each tuple: (key, type_description)
EXTRACTION_SCHEMA_FIELDS: list[tuple[str, str]] = [
    ("factor_name", "string - human-readable factor name"),
    ("economic_intuition", "string - brief economic rationale (1-2 sentences)"),
    ("detailed_definition", "string - exact signal formula in words, referencing variable names"),
    ("formula", "string - signal formula using database variable names (e.g. 'ceq / (csho * prcc_f)')"),
    ("required_fields", '[{"field": "variable name", "source": "dataset.table as stated in paper (e.g. compustat.funda, crsp.msf, ibes.detail)", "description": "what it represents"}]'),
    ("cat_form", '"continuous" | "discrete"'),
    ("sign", "1 or -1 (1 = high signal predicts high returns, -1 = low returns)"),
    ("formation_month", "null or int (month when portfolios are formed, e.g. 6 for June)"),
    ("rebalance_frequency", f'{_enum_choices(RebalanceFrequency)} | "unspecified"'),
    ("holding_period", "int (months the portfolio is held, typically 1 or 12)"),
    ("accounting_lag", "int (months between fiscal year-end and portfolio formation)"),
    ("skip_month", "null or int (months skipped between signal and formation)"),
    ("stock_weight", f'{_enum_choices(WeightingRule)} | "unspecified"'),
    ("ls_quantile", "float (long-short cutoff: 0.1=deciles, 0.2=quintiles, 0.3=terciles)"),
    ("breakpoint_source", f'{_enum_choices(BreakpointSource)} | "unspecified"'),
    ("long_leg", '"high" | "low"'),
    ("short_leg", '"high" | "low"'),
    ("filter", 'string - stock-level filters (e.g. \'abs(prc)>5\') or "unspecified"'),
    ("universe", "string - sample universe description"),
    ("missing_policy", f'{_enum_choices(MissingAction)} | "unspecified"'),
    ("sample_start_year", "null or int"),
    ("sample_end_year", "null or int"),
    ("paper_ref", "string - paper citation"),
    ("paper_sections", '["sections/tables where key info was found"]'),
    ("ambiguous_fields", '[{"field": "name", "reason": "why ambiguous"}]'),
    ("reasons", '{"field_name": "exact quote from paper supporting this value", ...} — for EVERY extracted field, provide the verbatim sentence(s) from the paper'),
]


def _build_extraction_schema() -> str:
    """Build the JSON schema block from EXTRACTION_SCHEMA_FIELDS."""
    lines = ["{"]
    for key, desc in EXTRACTION_SCHEMA_FIELDS:
        lines.append(f'  "{key}": {desc},')
    # Remove trailing comma on last entry
    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


EXTRACTION_SYSTEM_PROMPT = f"""\
You are an expert financial economist. Your task is to extract a structured factor \
specification from an academic paper.

Extract the following fields from the paper text. If a field is not clearly stated, \
mark it as "unspecified" rather than guessing.

Output a JSON object with exactly these keys:
{_build_extraction_schema()}

Rules:
- Only extract what is EXPLICITLY stated or clearly implied in the text.
- For "reasons": for EVERY field you extract, provide the exact sentence(s) from the paper that supports your choice. If inferred from context rather than explicit text, write "Inferred: <brief explanation>".
- For required_fields: extract the data source (database + table) as described in the paper. Common sources include Compustat (funda, fundq), CRSP (msf, dsf), IBES, Thomson Reuters, etc.
- For sign: +1 means high signal → high returns (value, profitability). -1 means high signal → low returns (investment, accruals).
- For ls_quantile: deciles = 0.1, quintiles = 0.2, terciles = 0.3, median = 0.5.
- For stock_weight: "ew" = equal-weighted, "vw" = value-weighted, "capped_vw" = value-weighted with max weight cap.
- For filter: express as R-style conditions (e.g. abs(prc)>5, exchcd%in%c(1,2)).
- For holding_period: 1 = monthly rebalancing, 12 = annual buy-and-hold.
- For accounting_lag: if paper says "fiscal year-end data used by June formation", lag = 6.
- Do NOT infer from common practice if paper is silent on a detail.
"""

EXTRACTION_USER_TEMPLATE = """\
Paper text for factor "{factor_id}":

{paper_text}

Extract the MethodSpec as JSON.
"""

BATCH_EXTRACTION_USER_TEMPLATE = """\
Paper text:

{paper_text}

This paper defines the following factors: {factor_ids}

Extract a MethodSpec for EACH factor listed above. Output a JSON object with factor IDs \
as top-level keys, each containing the full extraction schema.

Example output structure:
{{
  "FactorA": {{ ... full schema ... }},
  "FactorB": {{ ... full schema ... }}
}}
"""

# Rate limiting defaults
DEFAULT_CALL_DELAY = 1.0  # seconds between successful calls


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
    reasons: dict[str, str] = field(default_factory=dict)  # field_name -> quote from paper


class SemanticExtractor:
    """Extracts structured MethodSpec from unstructured paper text.

    Strategy: Paper-first extraction (architecture.md Section 4.2)
    1. LLM extracts from paper text (factor definition, data sources, portfolio rules)
    2. Ambiguity tagging for unspecified fields
    3. NO SignalDoc input — that's evaluation only

    One paper may define multiple factors (e.g. Soliman 2008 defines PM,
    AssetTurnover, ChPM, etc.). Each factor requires a separate extract() call
    with a distinct factor_id — one call produces exactly one MethodSpec.
    The same paper_text is passed each time; the factor_id tells the LLM
    which specific signal to focus on.

    For batch processing, use extract_batch() to extract all factors from
    a paper in a single LLM call (saves tokens and avoids rate limits).

    Acceptance criteria (Phase 1): Core field accuracy >= 80% on pilot factors.
    """

    def __init__(self, llm_client=None, call_delay: float = DEFAULT_CALL_DELAY):
        """
        Args:
            llm_client: OpenAI-compatible client (must have .chat.completions.create)
            call_delay: Delay between successful API calls (seconds)
        """
        self.llm_client = llm_client
        self.call_delay = call_delay
        self._last_call_time: float = 0

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

        # Call LLM for extraction
        raw = self._call_llm_extract(factor_id, paper_text)
        result.raw_llm_output = raw

        if raw:
            result.spec = self._build_method_spec_from_llm(factor_id, raw)
            result.reasons = raw.get("reasons", {})

        return result

    def extract_batch(
        self,
        factor_ids: list[str],
        paper_text: str,
    ) -> dict[str, ExtractionResult]:
        """Extract MethodSpecs for multiple factors from the same paper in one LLM call.

        This is more efficient when a paper defines multiple factors — one API call
        instead of N separate calls. Saves tokens and reduces rate limit risk.

        Args:
            factor_ids: List of factor IDs defined in this paper
            paper_text: Raw paper text

        Returns:
            Dict mapping factor_id -> ExtractionResult
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        # If only 1 factor, use regular extract
        if len(factor_ids) == 1:
            result = self.extract(factor_ids[0], paper_text)
            return {factor_ids[0]: result}

        # Call LLM for batch extraction
        raw_batch = self._call_llm_extract_batch(factor_ids, paper_text)

        results: dict[str, ExtractionResult] = {}
        for factor_id in factor_ids:
            result = ExtractionResult(sources_used=["paper"])
            if raw_batch and factor_id in raw_batch:
                raw = raw_batch[factor_id]
                result.raw_llm_output = raw
                result.spec = self._build_method_spec_from_llm(factor_id, raw)
                result.reasons = raw.get("reasons", {})
            elif raw_batch:
                # Try case-insensitive lookup
                for key, val in raw_batch.items():
                    if key.lower() == factor_id.lower():
                        result.raw_llm_output = val
                        result.spec = self._build_method_spec_from_llm(factor_id, val)
                        result.reasons = val.get("reasons", {})
                        break
            results[factor_id] = result

        return results

    def _call_llm_extract(
        self, factor_id: str, paper_text: str
    ) -> dict | None:
        """Call LLM to extract structured fields from paper text (with retry)."""
        user_msg = EXTRACTION_USER_TEMPLATE.format(
            factor_id=factor_id,
            paper_text=paper_text[:30000],  # Truncate to fit context
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return self._call_llm_with_retry(messages)

    def _call_llm_extract_batch(
        self, factor_ids: list[str], paper_text: str
    ) -> dict | None:
        """Call LLM to extract multiple factors from one paper (with retry)."""
        user_msg = BATCH_EXTRACTION_USER_TEMPLATE.format(
            factor_ids=", ".join(factor_ids),
            paper_text=paper_text[:30000],
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        return self._call_llm_with_retry(messages)

    def _call_llm_with_retry(self, messages: list[dict]) -> dict | None:
        """Call LLM with inter-call delay. Raises RateLimitError on quota exhaustion."""
        # Respect call_delay between requests
        elapsed = time.time() - self._last_call_time
        if elapsed < self.call_delay:
            time.sleep(self.call_delay - elapsed)

        try:
            response = self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            self._last_call_time = time.time()
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = (
                "rate_limit" in error_str
                or "rate limit" in error_str
                or "429" in error_str
                or "quota" in error_str
                or "too many requests" in error_str
            )
            if is_rate_limit:
                raise RateLimitExhausted(str(e)) from e
            print(f"  [WARN] LLM extraction failed: {e}")
            return None


class RateLimitExhausted(Exception):
    """Raised when API quota/rate limit is hit — caller should checkpoint and stop."""
    pass

    def _build_method_spec_from_llm(
        self, factor_id: str, raw: dict
    ) -> MethodSpec:
        """Convert raw LLM JSON output to a validated MethodSpec."""

        def _safe_int(val, default=None):
            """Convert value to int, returning default if not a valid integer."""
            if val is None or val == "unspecified" or val == "":
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        # Parse timing
        timing = SignalTiming(
            formation_month=_safe_int(raw.get("formation_month")),
            rebalance_frequency=self._parse_enum(
                RebalanceFrequency, raw.get("rebalance_frequency"), RebalanceFrequency.ANNUAL
            ),
            holding_period=_safe_int(raw.get("holding_period"), 12),
            accounting_lag=_safe_int(raw.get("accounting_lag"), 6),
            skip_month=_safe_int(raw.get("skip_month")),
        )

        # Parse missing policy
        missing_action = self._parse_enum(
            MissingAction, raw.get("missing_policy"), MissingAction.DROP
        )
        missing_policy = MissingPolicy(action=missing_action)

        # Parse signal spec — extract field_sources from structured required_fields
        raw_fields = raw.get("required_fields", [])
        field_names: list[str] = []
        field_sources: dict[str, FieldSource] = {}
        for item in raw_fields:
            if isinstance(item, dict):
                name = item.get("field", "")
                field_names.append(name)
                source_str = item.get("source", "")
                parts = source_str.split(".", 1)
                field_sources[name] = FieldSource(
                    dataset=parts[0] if parts else "",
                    table=parts[1] if len(parts) > 1 else "",
                    description=item.get("description", ""),
                )
            elif isinstance(item, str):
                field_names.append(item)

        signal = SignalSpec(
            formula=raw.get("formula", "unspecified"),
            required_fields=field_names,
            field_sources=field_sources,
            timing=timing,
            missing_policy=missing_policy,
        )

        # Parse portfolio spec
        bp_source = self._parse_enum(
            BreakpointSource, raw.get("breakpoint_source"), BreakpointSource.NYSE
        )
        # Convert ls_quantile to quantile percentiles list for backward compat
        ls_quantile = raw.get("ls_quantile")
        if ls_quantile is not None and ls_quantile != "unspecified":
            try:
                ls_quantile = float(ls_quantile)
            except (ValueError, TypeError):
                ls_quantile = None
        else:
            ls_quantile = None

        quantiles = raw.get("breakpoint_quantiles", [30, 70])
        if not isinstance(quantiles, list):
            # Derive from ls_quantile if available
            if ls_quantile:
                low_pct = int(ls_quantile * 100)
                quantiles = [low_pct, 100 - low_pct]
            else:
                quantiles = [30, 70]

        weighting = self._parse_enum(
            WeightingRule, raw.get("stock_weight", raw.get("weighting")), WeightingRule.VALUE_WEIGHTED
        )

        # Parse filter
        raw_filter = raw.get("filter", "")
        if raw_filter == "unspecified":
            raw_filter = ""

        portfolio = PortfolioSpec(
            universe=raw.get("universe", "NYSE + AMEX + NASDAQ, common shares only"),
            breakpoints=BreakpointSpec(source=bp_source, quantiles=quantiles, ls_quantile=ls_quantile),
            weighting=weighting,
            long_leg=raw.get("long_leg", "high"),
            short_leg=raw.get("short_leg", "low"),
            filter=raw_filter,
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
        if raw.get("stock_weight", raw.get("weighting")) == "unspecified":
            ambiguous.append(AmbiguousField(
                field="stock_weight",
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

        # Parse sign
        sign_val = raw.get("sign", 1)
        try:
            sign_val = int(sign_val)
        except (ValueError, TypeError):
            sign_val = 1

        return MethodSpec(
            factor_id=factor_id,
            factor_name=raw.get("factor_name", factor_id),
            paper_ref=raw.get("paper_ref", ""),
            economic_intuition=raw.get("economic_intuition", ""),
            detailed_definition=raw.get("detailed_definition", ""),
            cat_form=raw.get("cat_form", "continuous"),
            sign=sign_val,
            sample_start_year=_safe_int(raw.get("sample_start_year")),
            sample_end_year=_safe_int(raw.get("sample_end_year")),
            signal=signal,
            portfolio=portfolio,
            extraction_sources=sources,
            ambiguous_fields=ambiguous,
            review_status="pending",
        )

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
        core_fields = {"formula_keywords", "accounting_lag", "stock_weight",
                       "sign", "ls_quantile", "holding_period", "formation_month",
                       "rebalance_frequency", "sample_start_year", "sample_end_year"}
        core_matching = 0
        core_total = 0

        for key, expected in ground_truth.items():
            # If ground truth is unspecified/None, treat as correct (don't penalize)
            if expected is None or str(expected).strip().lower() in ("", "none", "unspecified", "n/a", "nan"):
                matching += 1
                non_empty += 1
                if key in core_fields:
                    core_total += 1
                    core_matching += 1
                continue

            actual = self._get_spec_field(spec, key)
            if actual is not None and str(actual) != "":
                non_empty += 1
                if self._values_match(actual, expected, field_key=key):
                    matching += 1
            if key in core_fields:
                core_total += 1
                if actual is not None and self._values_match(actual, expected, field_key=key):
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
            "formula_keywords": spec.signal.formula,  # Will be keyword-matched
            "detailed_definition": spec.detailed_definition,
            "accounting_lag": spec.signal.timing.accounting_lag,
            "breakpoints": spec.portfolio.breakpoints.source.value,
            "breakpoint_source": spec.portfolio.breakpoints.source.value,
            "weighting": spec.portfolio.weighting.value,
            "stock_weight": spec.portfolio.weighting.value,
            "formation_month": spec.signal.timing.formation_month,
            "start_month": spec.signal.timing.formation_month,
            "missing_policy": spec.signal.missing_policy.action.value,
            "holding_period": spec.signal.timing.holding_period,
            "portfolio_period": spec.signal.timing.holding_period,
            "rebalance_frequency": spec.signal.timing.rebalance_frequency.value,
            "long_leg": spec.portfolio.long_leg,
            "short_leg": spec.portfolio.short_leg,
            "universe": spec.portfolio.universe,
            "sign": spec.sign,
            "ls_quantile": spec.portfolio.breakpoints.ls_quantile,
            "filter": spec.portfolio.filter,
            "cat_form": spec.cat_form,
            "sample_start_year": spec.sample_start_year,
            "sample_end_year": spec.sample_end_year,
        }
        return field_map.get(key)

    def _values_match(self, actual, expected, field_key: str = "") -> bool:
        """Fuzzy match for evaluation.

        For formula_keywords: checks if >= 50% of expected keywords appear in actual.
        For other fields: case-insensitive string match.
        """
        if field_key == "formula_keywords":
            # expected is comma-separated keywords, actual is the formula string
            keywords = [k.strip() for k in str(expected).split(",") if k.strip()]
            if not keywords:
                return True
            formula_lower = str(actual).lower()
            matched = sum(1 for kw in keywords if kw in formula_lower)
            # Pass if >= 50% of keywords found
            return matched >= len(keywords) * 0.5

        a = str(actual).lower().strip()
        e = str(expected).lower().strip()
        return a == e
