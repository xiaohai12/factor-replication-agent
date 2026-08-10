"""Paper-first MethodSpec extraction (Phase B). Produces `MethodSpec`
directly -- NOT wired into `src.pipeline` yet (see
docs/methodspec-v2-plan.md section 9; `src/steps/step1_extractor/__init__.py`'s
original `SemanticExtractor` remains the live extractor until Step2/Step3 also
consume these new artifacts).

Because `MethodSpec` uses `extra="forbid"` and the prompt's JSON shape
is generated directly from the same model (`schema_render`), there is no
`normalize_curated_schema`-style flattening layer here: if the LLM's output
matches the prompt, `MethodSpec.model_validate()` accepts it as-is; if it
doesn't, validation fails loudly instead of silently dropping fields (plan
section 3.1's root-cause fix).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from src.infra.models.method_spec import MethodSpec
from src.infra.models.schema_render import splice_schema_skeleton
from src.steps.step2_reviewer.review import ENGINE_RETURN_COMBINATION_MENU

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "extractor" / "method_spec_extractor.md"
)

# Known free-text synonyms the extractor sometimes emits instead of the exact
# ENGINE_WEIGHTING_MENU token (docs/known-gaps-paper-first-v2.md gap #1).
# Matched case/punctuation-insensitively; anything not recognized here maps to
# `WeightingScheme.OTHER` (the field is a real enum, so an arbitrary string
# would fail `MethodSpec.model_validate()` rather than just get flagged
# unsupported at review) -- review's D4 check still blocks OTHER the same way.
_WEIGHTING_SYNONYMS: dict[str, str] = {
    "vw": "vw",
    "value weighted": "vw",
    "value weighting": "vw",
    "market cap weighted": "vw",
    "market value weighted": "vw",
    "cap weighted": "vw",
    "ew": "ew",
    "equal weighted": "ew",
    "equally weighted": "ew",
    "equal weighting": "ew",
}


def _normalize_weighting(value: str) -> str:
    key = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    return _WEIGHTING_SYNONYMS.get(key, "other")


# Keyword-based (not exact-synonym) since the paper's own wording for "drop"
# is far more varied than weighting's -- e.g. "excluded", "removed from the
# sample", "require nonzero ... in both years" (a nonmissing precondition
# that amounts to dropping firms failing it). Anything not matching one of
# these drop-shaped keywords maps to `MissingActionScheme.OTHER` (the field
# is now a real enum -- see method_spec.py -- so an arbitrary sentence would
# fail validation instead of just getting flagged unsupported at review).
_DROP_KEYWORDS = ("drop", "exclud", "remov", "require", "omit", "discard")


def _normalize_missing_action(value: str) -> str:
    if value == "drop":
        return value
    text = value.lower()
    return "drop" if any(k in text for k in _DROP_KEYWORDS) else "other"


# Same exact-synonym approach as weighting -- "NYSE" wording is fairly
# consistent across papers, unlike missing-action's wording.
_BREAKPOINT_BASIS_SYNONYMS: dict[str, str] = {
    "full sample": "full_sample",
    "all stocks": "full_sample",
    "all eligible stocks": "full_sample",
    "all sample stocks": "full_sample",
    "entire sample": "full_sample",
    "entire universe": "full_sample",
    "whole sample": "full_sample",
    "full universe": "full_sample",
    "nyse": "nyse",
    "nyse stocks": "nyse",
    "nyse firms": "nyse",
    "nyse breakpoints": "nyse",
}


def _normalize_breakpoint_basis(value: str) -> str:
    key = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    return _BREAKPOINT_BASIS_SYNONYMS.get(key, "other")


def _normalize_return_combination(value: str) -> str:
    """Map an obvious long/short-spread description to `extreme_group_spread`
    or `average_leg_spread`. Purely a vocabulary canonicalization over text
    the paper already stated -- if the wording doesn't clearly imply one of
    the menu's combination types, the value is left unchanged so review's D4
    check still blocks it rather than guessing an empirical choice.
    """
    if value in ENGINE_RETURN_COMBINATION_MENU:
        return value
    text = value.lower()
    if "long" not in text or "short" not in text:
        return value
    averages_multiple = "average" in text and any(
        w in text for w in ("portfolios", "deciles", "quintiles", "quantiles", "groups")
    )
    return "average_leg_spread" if averages_multiple else "extreme_group_spread"


def normalize_engine_vocabulary(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize `portfolio.weighting`/`portfolio.return_combination`/
    `portfolio.missing_policies[].action`/`portfolio.sorts[].breakpoints.
    basis` free text into the engine's exact menu tokens before
    validation.

    Without this, a wording mismatch (e.g. "value-weighted" instead of "vw")
    makes review's D4 check block the spec, and if a human clamps past that,
    `registry.build_config`'s `_clamp_with_provenance` would silently replace
    the paper's real choice with the engine default -- a correctness bug, not
    just a review annoyance. See docs/known-gaps-paper-first-v2.md gap #1.
    """
    portfolio = payload.get("portfolio")
    if not isinstance(portfolio, dict):
        return payload
    portfolio = dict(portfolio)

    weighting = portfolio.get("weighting")
    if isinstance(weighting, dict) and isinstance(weighting.get("value"), str):
        weighting = dict(weighting)
        weighting["value"] = _normalize_weighting(weighting["value"])
        portfolio["weighting"] = weighting

    return_combination = portfolio.get("return_combination")
    if isinstance(return_combination, dict) and isinstance(return_combination.get("value"), str):
        return_combination = dict(return_combination)
        return_combination["value"] = _normalize_return_combination(return_combination["value"])
        portfolio["return_combination"] = return_combination

    missing_policies = portfolio.get("missing_policies")
    if isinstance(missing_policies, list):
        new_policies = []
        for mp in missing_policies:
            if isinstance(mp, dict) and isinstance(mp.get("action"), dict) and isinstance(mp["action"].get("value"), str):
                mp = dict(mp)
                action = dict(mp["action"])
                action["value"] = _normalize_missing_action(action["value"])
                mp["action"] = action
            new_policies.append(mp)
        portfolio["missing_policies"] = new_policies

    sorts = portfolio.get("sorts")
    if isinstance(sorts, list):
        new_sorts = []
        for s in sorts:
            if (
                isinstance(s, dict)
                and isinstance(s.get("breakpoints"), dict)
                and isinstance(s["breakpoints"].get("basis"), dict)
                and isinstance(s["breakpoints"]["basis"].get("value"), str)
            ):
                s = dict(s)
                breakpoints = dict(s["breakpoints"])
                basis = dict(breakpoints["basis"])
                basis["value"] = _normalize_breakpoint_basis(basis["value"])
                breakpoints["basis"] = basis
                s["breakpoints"] = breakpoints
            new_sorts.append(s)
        portfolio["sorts"] = new_sorts

    payload = dict(payload)
    payload["portfolio"] = portfolio
    return payload


def _repair_bare_sourced_scalars(payload: dict[str, Any]) -> dict[str, Any]:
    """Salvage a `SourcedValue`-wrapped field the LLM emitted as a bare
    scalar instead (docs/known-gaps-paper-first-v2.md-style drift, seen for
    `timing.formation_month`), rather than losing the whole extraction to a
    validation error. `status="unspecified"` since no evidence was captured,
    which forces human review of the salvaged value.
    """
    payload = dict(payload)
    timing = payload.get("timing")
    if isinstance(timing, dict) and isinstance(timing.get("formation_month"), int):
        timing = dict(timing)
        timing["formation_month"] = {
            "value": timing["formation_month"],
            "evidence": [],
            "status": "unspecified",
        }
        payload["timing"] = timing
    return payload


def load_extraction_system_prompt() -> str:
    """Load `method_spec_extractor.md`, splicing in the current
    `MethodSpec` JSON skeleton so the prompt can never structurally
    drift from the model (same pattern as
    `field_contract.splice_allowed_values` for v1's Allowed Values block).
    """
    text = _PROMPT_PATH.read_text()
    return splice_schema_skeleton(text)


def build_method_spec(document_id: str, target_name: str, raw: dict[str, Any]) -> MethodSpec:
    """Turn a raw LLM JSON dict into a validated `MethodSpec`.

    `factor_id` and `schema_version` are never taken from the LLM (D7): they
    are computed/fixed here so the LLM can't invent an unstable identifier.
    `paper.document_id` is filled from the caller-supplied `document_id` if
    the LLM didn't already set it identically.
    """
    payload = normalize_engine_vocabulary(dict(raw))
    payload = _repair_bare_sourced_scalars(payload)
    payload["factor_id"] = MethodSpec.make_factor_id(document_id, target_name)
    payload["target_name"] = target_name
    payload["schema_version"] = "methodspec.v2"

    paper_block = dict(payload.get("paper") or {})
    paper_block.setdefault("document_id", document_id)
    payload["paper"] = paper_block

    return MethodSpec.model_validate(payload)


DEFAULT_CALL_DELAY = 1.0  # seconds between successful calls, mirrors SemanticExtractor

PAPER_EXTRACTION_USER_TEMPLATE = """\
Paper text for target factor "{target_name}" (document "{document_id}"):

{paper_text}

Extract the MethodSpec as JSON, following the schema in the system prompt exactly.
"""


class RateLimitExhausted(Exception):
    """Raised when the LLM call fails due to rate limiting/quota exhaustion."""


@dataclass
class ExtractionResult:
    """Result of one `MethodSpecExtractor.extract()` call."""

    spec: Optional[MethodSpec] = None
    raw_llm_output: Optional[dict] = None
    error: Optional[str] = None
    token_usage: Optional[dict] = None


class MethodSpecExtractor:
    """LLM-driven extraction of `MethodSpec` (Phase B, paper-first
    schema). Same call/retry machinery as `step1_extractor.SemanticExtractor`
    (JSON-mode chat completion, PDF-attachment passthrough when the client
    supports it, rate-limit detection) but targets `MethodSpec` via
    `build_method_spec` instead of the flat v1 `MethodSpec`.

    Not wired into `src.pipeline`/`SemanticExtractor`'s callers -- this is a
    parallel, additive extraction path for the paper-first workflow's own
    UI/API surface (see docs/methodspec-v2-plan.md section 9).
    """

    def __init__(self, llm_client=None, call_delay: float = DEFAULT_CALL_DELAY):
        self.llm_client = llm_client
        self.call_delay = call_delay
        self._last_call_time: float = 0.0
        self._last_error: Optional[str] = None
        self._last_usage: Optional[dict] = None

    def extract(
        self,
        document_id: str,
        target_name: str,
        paper_text: str,
        pdf_bytes: bytes | None = None,
    ) -> ExtractionResult:
        """Extract a `MethodSpec` from paper text (or native PDF bytes
        when the client supports it)."""
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = ExtractionResult()
        self._last_error = None
        self._last_usage = None
        raw = self._call_llm_extract(document_id, target_name, paper_text, pdf_bytes=pdf_bytes)
        result.raw_llm_output = raw
        result.token_usage = self._last_usage

        if raw:
            try:
                result.spec = build_method_spec(document_id, target_name, raw)
            except ValidationError as exc:
                result.error = f"LLM output did not match MethodSpec schema: {exc}"
        else:
            result.error = self._last_error or "LLM returned empty response"

        return result

    def _call_llm_extract(
        self, document_id: str, target_name: str, paper_text: str, pdf_bytes: bytes | None = None,
    ) -> dict | None:
        client_supports_pdf = hasattr(self.llm_client, "_create_with_pdf") or hasattr(self.llm_client, "_pdf_to_text")
        user_msg = PAPER_EXTRACTION_USER_TEMPLATE.format(
            document_id=document_id,
            target_name=target_name,
            paper_text="[See attached PDF document above]" if (pdf_bytes and client_supports_pdf) else paper_text,
        )
        messages = [
            {"role": "system", "content": load_extraction_system_prompt()},
            {"role": "user", "content": user_msg},
        ]
        return self._call_llm_with_retry(messages, pdf_bytes=pdf_bytes if client_supports_pdf else None)

    def _call_llm_with_retry(self, messages: list[dict], pdf_bytes: bytes | None = None) -> dict | None:
        """Call LLM with inter-call delay. Raises RateLimitExhausted on quota exhaustion."""
        from src.infra.llm import extract_usage

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
            return None
