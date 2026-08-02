"""Semantic Extractor - Extract MethodSpec from papers and reference materials.

Implements paper-first extraction (docs/architecture.md Section 4.2):
1. Paper text as primary source (LLM extracts factor definition)
2. Ambiguity tagging for unresolved fields
3. Post-hoc evaluation against C&Z (not feedback)

IMPORTANT: SignalDoc.csv is NOT used as Extractor input (information leakage).
SignalDoc is only used post-hoc for extraction accuracy evaluation.
See docs/cz-reference.md Section 1 for details.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from src.infra.models.method_spec import (
    AmbiguousField,
    BreakpointSource,
    DataSourceHint,
    DataSpec,
    EvidenceSource,
    EvidenceCitation,
    ExtractionSource,
    MethodSpec,
    MissingAction,
    MissingPolicy,
    PortfolioSortSpec,
    PortfolioSpec,
    RebalanceFrequency,
    ReportedResultsSpec,
    RequiredFieldSpec,
    SignalSpec,
    SignalTiming,
    WeightingRule,
)

# Canonical prompt file — used as system prompt when available
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extractor" / "methodspec_extractor.md"


def _load_extraction_system_prompt() -> str:
    """Load system prompt from prompts/extractor/methodspec_extractor.md if present."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text()
    return _FALLBACK_EXTRACTION_SYSTEM_PROMPT


# --- Fallback system prompt (used only when prompts/ file is missing) ---


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
    ("sign", "1 or -1 (1 = high signal predicts high returns, -1 = low returns)"),
    ("formation_month", "null or int (month when portfolios are formed, e.g. 6 for June)"),
    ("rebalance_frequency", f'{_enum_choices(RebalanceFrequency)} | "unspecified"'),
    ("holding_period", "int (months the portfolio is held, typically 1 or 12)"),
    ("accounting_lag", "int (months between fiscal year-end and portfolio formation)"),
    ("stock_weight", f'{_enum_choices(WeightingRule)} | "unspecified"'),
    ("ls_quantile", "float (long-short cutoff: 0.1=deciles, 0.2=quintiles, 0.3=terciles)"),
    ("breakpoint_source", f'{_enum_choices(BreakpointSource)} | "unspecified"'),
    ("long_leg", '"high" | "low"'),
    ("short_leg", '"high" | "low"'),
    ("filter", 'string - stock-level filters (e.g. \'abs(prc)>5\') or "unspecified"'),
    ("universe", "string - sample universe description"),
    ("missing_policy", f'{_enum_choices(MissingAction)} | "unspecified"'),
    ("winsorize_bounds", 'null or string - winsorization bounds if applicable, e.g. "1,99" or "0.5,99.5"'),
    ("return_horizon", '"monthly" | "quarterly" | "annual" - time horizon of reported_return_spread'),
    ("sample_start_year", "null or int"),
    ("sample_end_year", "null or int"),
    ("reported_return_spread", "null or float - monthly long-short return spread (in %) reported in the paper's main results table (e.g. 0.43 means 0.43% per month)"),
    ("reported_t_stat", "null or float - t-statistic of the long-short return spread from the paper's main results table"),
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


_FALLBACK_EXTRACTION_SYSTEM_PROMPT = f"""\
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

#: Prepended to the extraction user message when the Review Gate sent this
#: factor back for TARGETED re-extraction (see src/pipeline.py's Review ->
#: Extractor loop). It tells the model WHICH fields the reviewer suspects were
#: mis-extracted and, crucially, quotes the paper passage the reviewer pointed
#: at so the model re-reads that exact text -- it never hands the model the
#: answer, only "re-check THIS field against THIS passage".
REEXTRACT_FEEDBACK_TEMPLATE = """\
IMPORTANT — TARGETED RE-EXTRACTION. A reviewer flagged the following field(s) from a
previous extraction of this same paper as likely MIS-READ. Re-read the quoted paper
passages carefully and correct these fields. Do NOT change fields that were not flagged
unless the paper clearly requires it. If, after re-reading, the paper genuinely does not
state a field, mark it "unspecified" — do not guess.

Flagged fields:
{feedback_block}

"""


def _format_reextract_feedback(reextract_feedback: list[dict]) -> str:
    """Render the reviewer feedback (field + reason + paper quote + prior value)
    into the block injected by REEXTRACT_FEEDBACK_TEMPLATE."""
    lines = []
    for item in reextract_feedback:
        field = item.get("field", "?")
        reason = item.get("reason", "")
        prior = item.get("prior_value")
        evidence = item.get("paper_evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        lines.append(f"- Field `{field}` (previously extracted as: {prior!r})")
        if reason:
            lines.append(f"    Reviewer concern: {reason}")
        for quote in evidence:
            quote_text = quote.get("quote") if isinstance(quote, dict) else quote
            if quote_text:
                lines.append(f"    Paper says: \"{quote_text}\"")
    return "\n".join(lines)


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


class RateLimitExhausted(Exception):
    """Raised when API quota/rate limit is hit — caller should checkpoint and stop."""
    pass


@dataclass
class ExtractionMetrics:
    """Metrics for evaluating extraction quality (Section 4.2).

    Used against C&Z metadata as a post-hoc reference for pilot factors.
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
    error: Optional[str] = None  # Error message if extraction failed
    token_usage: Optional[dict] = None  # {prompt_tokens, completion_tokens, total_tokens}


class SemanticExtractor:
    """Extracts structured MethodSpec from unstructured paper text.

    Strategy: Paper-first extraction (docs/architecture.md Section 4.2)
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

    def __init__(
        self,
        llm_client=None,
        call_delay: float = DEFAULT_CALL_DELAY,
        data_dictionary=None,
    ):
        """
        Args:
            llm_client: OpenAI-compatible client (must have .chat.completions.create)
            call_delay: Delay between successful API calls (seconds)
            data_dictionary: Optional field registry for prompt/review integration.
        """
        self.llm_client = llm_client
        self.call_delay = call_delay
        self.data_dictionary = data_dictionary
        self._last_call_time: float = 0

    def extract(
        self,
        factor_id: str,
        paper_text: str,
        pdf_bytes: bytes | None = None,
        reextract_feedback: list[dict] | None = None,
    ) -> ExtractionResult:
        """Extract MethodSpec from paper text only.

        This is the main extraction method. No C&Z metadata or OSAP code
        is provided to avoid information leakage.

        Args:
            factor_id: Unique factor identifier (e.g. "BM", "Mom12m")
            paper_text: Raw paper text (or relevant sections)
            pdf_bytes: Optional native PDF bytes (used when the client supports it)
            reextract_feedback: Optional reviewer feedback for a TARGETED
                re-extraction (see src/pipeline.py's Review -> Extractor loop).
                Each item = {field, reason, paper_evidence, prior_value}; it
                steers the model to re-read the quoted passages for the flagged
                fields. Never contains the answer -- only which fields to
                re-check against which paper text.

        Returns:
            ExtractionResult with MethodSpec and quality metrics
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = ExtractionResult(sources_used=["paper"])

        # Call LLM for extraction
        self._last_error = None
        self._last_usage = None
        raw = self._call_llm_extract(
            factor_id, paper_text, pdf_bytes=pdf_bytes, reextract_feedback=reextract_feedback
        )
        result.raw_llm_output = raw
        result.token_usage = getattr(self, "_last_usage", None)

        if raw:
            result.spec = self._build_method_spec_from_llm(factor_id, raw)
            result.reasons = raw.get("reasons", {})
        else:
            result.error = self._last_error or "LLM returned empty response"

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

    # Max paper text chars sent to LLM (~10k tokens, leaves room for system prompt + output)
    def _call_llm_extract(
        self, factor_id: str, paper_text: str, pdf_bytes: bytes | None = None,
        reextract_feedback: list[dict] | None = None,
    ) -> dict | None:
        """Call LLM to extract structured fields from paper text (with retry).

        If pdf_bytes is provided and the client supports it, sends the PDF directly
        as a base64 document block (preserves formulas and tables).
        Otherwise sends full paper text.

        When `reextract_feedback` is supplied, a TARGETED re-extraction
        instruction block (which fields to re-check + the paper quotes the
        reviewer pointed at) is prepended to the user message.
        """
        feedback_prefix = ""
        if reextract_feedback:
            feedback_prefix = REEXTRACT_FEEDBACK_TEMPLATE.format(
                feedback_block=_format_reextract_feedback(reextract_feedback)
            )

        client_supports_pdf = hasattr(self.llm_client, "_create_with_pdf") or hasattr(self.llm_client, "_pdf_to_text")
        if pdf_bytes and client_supports_pdf:
            user_msg = feedback_prefix + EXTRACTION_USER_TEMPLATE.format(
                factor_id=factor_id,
                paper_text="[See attached PDF document above]",
            )
            messages = [
                {"role": "system", "content": _load_extraction_system_prompt()},
                {"role": "user", "content": user_msg},
            ]
            return self._call_llm_with_retry(messages, pdf_bytes=pdf_bytes)

        user_msg = feedback_prefix + EXTRACTION_USER_TEMPLATE.format(
            factor_id=factor_id,
            paper_text=paper_text,
        )
        messages = [
            {"role": "system", "content": _load_extraction_system_prompt()},
            {"role": "user", "content": user_msg},
        ]
        return self._call_llm_with_retry(messages)

    def _call_llm_extract_batch(
        self, factor_ids: list[str], paper_text: str
    ) -> dict | None:
        """Call LLM to extract multiple factors from one paper (with retry)."""
        user_msg = BATCH_EXTRACTION_USER_TEMPLATE.format(
            factor_ids=", ".join(factor_ids),
            paper_text=paper_text,
        )
        messages = [
            {"role": "system", "content": _load_extraction_system_prompt()},
            {"role": "user", "content": user_msg},
        ]
        return self._call_llm_with_retry(messages)

    def _call_llm_with_retry(self, messages: list[dict], pdf_bytes: bytes | None = None) -> dict | None:
        """Call LLM with inter-call delay. Raises RateLimitError on quota exhaustion."""
        from src.infra.llm import extract_usage
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
                **({"pdf_bytes": pdf_bytes} if pdf_bytes else {}),
            )
            self._last_call_time = time.time()
            self._last_usage = extract_usage(response)
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
            self._last_error = str(e)
            print(f"  [WARN] LLM extraction failed: {e}")
            return None

    def _build_method_spec_from_llm(
        self, factor_id: str, raw: dict
    ) -> MethodSpec:
        """Convert raw LLM JSON output to a validated MethodSpec.

        Tries the rich schema path first (MethodSpec.model_validate on the raw dict,
        which works when the LLM output matches the prompts/ curated format).
        Falls back to manual construction from the legacy flat schema.
        """
        # Inject factor_id if missing (the rich schema requires it)
        enriched = dict(raw)
        enriched.setdefault("factor_id", factor_id)
        enriched.setdefault("factor_name", raw.get("factor_name") or factor_id)

        try:
            return MethodSpec.model_validate(enriched)
        except (ValidationError, Exception):
            pass  # Fall through to manual flat-schema construction

        def _safe_int(val, default=None):
            """Convert value to int, returning default if not a valid integer."""
            if val is None or val == "unspecified" or val == "":
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        timing = SignalTiming(
            formation_month=_safe_int(raw.get("formation_month")),
            rebalance_frequency=self._parse_enum(
                RebalanceFrequency,
                raw.get("rebalance_frequency"),
                RebalanceFrequency.UNSPECIFIED,
            ),
            holding_period=_safe_int(raw.get("holding_period")),
            accounting_lag=_safe_int(raw.get("accounting_lag")),
        )

        # Parse missing policy
        missing_action = self._parse_enum(
            MissingAction, raw.get("missing_policy"), MissingAction.UNSPECIFIED
        )
        raw_wbounds = raw.get("winsorize_bounds")
        winsorize_bounds = None
        if raw_wbounds and raw_wbounds != "unspecified":
            try:
                parts = str(raw_wbounds).split(",")
                winsorize_bounds = (float(parts[0].strip()), float(parts[1].strip()))
            except (ValueError, IndexError):
                winsorize_bounds = None
        missing_policy = MissingPolicy(action=missing_action, winsorize_bounds=winsorize_bounds)

        # Parse signal/data specs. Source details stay as paper wording; physical
        # table mapping belongs to the Data Catalog / Normalizer.
        raw_fields = raw.get("required_fields", [])
        field_names: list[str] = []
        required_field_specs: list[RequiredFieldSpec] = []
        data_source_hints: dict[str, DataSourceHint] = {}
        for item in raw_fields:
            if isinstance(item, dict):
                name = item.get("field", "")
                if not name:
                    continue
                field_names.append(name)
                source_str = item.get("source", "")
                parts = source_str.split(".", 1)
                required_field_specs.append(RequiredFieldSpec(
                    field=name,
                    concept=item.get("description", ""),
                    source_detail=source_str,
                ))
                if source_str:
                    dataset_name = parts[0] if parts else source_str
                    hint = data_source_hints.setdefault(
                        dataset_name,
                        DataSourceHint(name=dataset_name, source_details=[]),
                    )
                    if source_str not in hint.source_details:
                        hint.source_details.append(source_str)
            elif isinstance(item, str):
                field_names.append(item)
                required_field_specs.append(RequiredFieldSpec(field=item))

        signal = SignalSpec(
            formula=raw.get("formula", "unspecified"),
            required_fields=field_names,
            timing=timing,
            missing_policy=missing_policy,
        )

        # Parse portfolio spec
        bp_source = self._parse_enum(
            BreakpointSource,
            raw.get("breakpoint_source"),
            BreakpointSource.UNSPECIFIED,
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

        weighting = self._parse_enum(
            WeightingRule,
            raw.get("stock_weight", raw.get("weighting")),
            WeightingRule.UNSPECIFIED,
        )

        raw_universe = raw.get("universe", "NYSE + AMEX + NASDAQ, common shares only")
        if isinstance(raw_universe, dict):
            raw_universe = raw_universe.get("description") or raw_universe.get("value") or str(raw_universe)

        portfolio = PortfolioSpec(
            universe=raw_universe,
            sort=PortfolioSortSpec(breakpoint_source=bp_source, ls_quantile=ls_quantile),
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

        # Parse reported stats
        def _safe_float(val):
            if val is None or val == "unspecified" or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        raw_horizon = raw.get("return_horizon", "monthly")
        if not raw_horizon or raw_horizon == "unspecified":
            raw_horizon = "monthly"

        reasons = raw.get("reasons", {}) or {}
        field_evidence = [
            EvidenceCitation(
                location=", ".join(raw.get("paper_sections", [])),
                quote=str(reasons.get("formula", "")),
                interpretation="Supports the extracted signal formula.",
            )
        ] if reasons.get("formula") else []

        return MethodSpec(
            factor_id=factor_id,
            factor_name=raw.get("factor_name", factor_id),
            paper_ref=raw.get("paper_ref", ""),
            economic_intuition=raw.get("economic_intuition", ""),
            detailed_definition=raw.get("detailed_definition", ""),
            sign=sign_val,
            sample_start_year=_safe_int(raw.get("sample_start_year")),
            sample_end_year=_safe_int(raw.get("sample_end_year")),
            cz_acronym=raw.get("cz_acronym") or None,
            data=DataSpec(
                sources=list(data_source_hints.values()),
                required_fields=required_field_specs,
            ),
            signal=signal,
            portfolio=portfolio,
            reported_results=ReportedResultsSpec(
                return_horizon=raw_horizon,
                main_spread=_safe_float(raw.get("reported_return_spread")),
                main_t_stat=_safe_float(raw.get("reported_t_stat")),
                spreads=[
                    _safe_float(raw.get("reported_return_spread"))
                ] if _safe_float(raw.get("reported_return_spread")) is not None else [],
                t_stats=[
                    _safe_float(raw.get("reported_t_stat"))
                ] if _safe_float(raw.get("reported_t_stat")) is not None else [],
                evidence=field_evidence,
            ),
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
        self, spec: MethodSpec, reference: dict
    ) -> ExtractionMetrics:
        """Evaluate extraction quality against a C&Z reference profile.

        Used for pilot factor validation. This is POST-HOC only —
        results are NOT fed back to correct the MethodSpec.

        Args:
            spec: Extracted MethodSpec
            reference: Dict of field_name -> reference_value from SignalDoc.csv
        """
        total_fields = len(reference)
        if total_fields == 0:
            return ExtractionMetrics()

        matching = 0
        non_empty = 0
        core_fields = {"formula_keywords", "accounting_lag", "stock_weight",
                       "sign", "ls_quantile", "holding_period", "formation_month",
                       "rebalance_frequency", "sample_start_year", "sample_end_year"}
        core_matching = 0
        core_total = 0

        for key, expected in reference.items():
            # If the reference is unspecified/None, do not penalize the extractor.
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
            "breakpoints": spec.portfolio.sort.breakpoint_source.value,
            "breakpoint_source": spec.portfolio.sort.breakpoint_source.value,
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
            "ls_quantile": spec.portfolio.sort.ls_quantile,
            "sample_start_year": spec.sample_start_year,
            "sample_end_year": spec.sample_end_year,
            "return_horizon": spec.return_horizon,
            "winsorize_bounds": (
                ",".join(str(b) for b in spec.signal.missing_policy.winsorize_bounds)
                if spec.signal.missing_policy.winsorize_bounds else None
            ),
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
