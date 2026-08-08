"""Paper-first MethodSpec extraction (Phase B). Produces `PaperMethodSpec`
directly -- NOT wired into `src.pipeline` yet (see
docs/methodspec-v2-plan.md section 9; `src/steps/step1_extractor/__init__.py`'s
original `SemanticExtractor` remains the live extractor until Step2/Step3 also
consume these new artifacts).

Because `PaperMethodSpec` uses `extra="forbid"` and the prompt's JSON shape
is generated directly from the same model (`schema_render`), there is no
`normalize_curated_schema`-style flattening layer here: if the LLM's output
matches the prompt, `PaperMethodSpec.model_validate()` accepts it as-is; if it
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

from src.infra.models.paper_method_spec import PaperMethodSpec
from src.infra.models.schema_render import splice_schema_skeleton

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "extractor" / "paper_method_spec_extractor.md"
)


def load_extraction_system_prompt() -> str:
    """Load `paper_method_spec_extractor.md`, splicing in the current
    `PaperMethodSpec` JSON skeleton so the prompt can never structurally
    drift from the model (same pattern as
    `field_contract.splice_allowed_values` for v1's Allowed Values block).
    """
    text = _PROMPT_PATH.read_text()
    return splice_schema_skeleton(text)


def build_paper_method_spec(document_id: str, target_name: str, raw: dict[str, Any]) -> PaperMethodSpec:
    """Turn a raw LLM JSON dict into a validated `PaperMethodSpec`.

    `factor_id` and `schema_version` are never taken from the LLM (D7): they
    are computed/fixed here so the LLM can't invent an unstable identifier.
    `paper.document_id` is filled from the caller-supplied `document_id` if
    the LLM didn't already set it identically.
    """
    payload = dict(raw)
    payload["factor_id"] = PaperMethodSpec.make_factor_id(document_id, target_name)
    payload["target_name"] = target_name
    payload["schema_version"] = "methodspec.v2"

    paper_block = dict(payload.get("paper") or {})
    paper_block.setdefault("document_id", document_id)
    payload["paper"] = paper_block

    return PaperMethodSpec.model_validate(payload)


DEFAULT_CALL_DELAY = 1.0  # seconds between successful calls, mirrors SemanticExtractor

PAPER_EXTRACTION_USER_TEMPLATE = """\
Paper text for target factor "{target_name}" (document "{document_id}"):

{paper_text}

Extract the PaperMethodSpec as JSON, following the schema in the system prompt exactly.
"""


class RateLimitExhausted(Exception):
    """Raised when the LLM call fails due to rate limiting/quota exhaustion."""


@dataclass
class PaperExtractionResult:
    """Result of one `PaperExtractor.extract()` call."""

    spec: Optional[PaperMethodSpec] = None
    raw_llm_output: Optional[dict] = None
    error: Optional[str] = None
    token_usage: Optional[dict] = None


class PaperExtractor:
    """LLM-driven extraction of `PaperMethodSpec` (Phase B, paper-first
    schema). Same call/retry machinery as `step1_extractor.SemanticExtractor`
    (JSON-mode chat completion, PDF-attachment passthrough when the client
    supports it, rate-limit detection) but targets `PaperMethodSpec` via
    `build_paper_method_spec` instead of the flat v1 `MethodSpec`.

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
    ) -> PaperExtractionResult:
        """Extract a `PaperMethodSpec` from paper text (or native PDF bytes
        when the client supports it)."""
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = PaperExtractionResult()
        self._last_error = None
        self._last_usage = None
        raw = self._call_llm_extract(document_id, target_name, paper_text, pdf_bytes=pdf_bytes)
        result.raw_llm_output = raw
        result.token_usage = self._last_usage

        if raw:
            try:
                result.spec = build_paper_method_spec(document_id, target_name, raw)
            except ValidationError as exc:
                result.error = f"LLM output did not match PaperMethodSpec schema: {exc}"
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
