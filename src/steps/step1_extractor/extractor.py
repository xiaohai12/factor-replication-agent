"""Paper-first MethodSpec extraction (Phase B). Produces a **raw dict**
straight from the LLM -- NOT a validated `MethodSpec` (see
docs/step1-step2-refactor-plan.md). All correctness work (schema
validation, menu-vocabulary classification, structural repair) now lives
in Step2's `src.steps.step2_reviewer.spec_build.build_reviewed_method_spec`,
not here: Step1 is a single LLM call, nothing else.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.infra.models.schema_render import splice_schema_skeleton

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "extractor" / "method_spec_extractor.md"
)

RAW_SPEC_DIR = Path(__file__).resolve().parents[3] / "runs" / "method_specs" / "raw"


def load_extraction_system_prompt() -> str:
    """Load `method_spec_extractor.md`, splicing in the current
    `MethodSpec` JSON skeleton so the prompt can never structurally
    drift from the model (same pattern as
    `field_contract.splice_allowed_values` for v1's Allowed Values block).
    """
    text = _PROMPT_PATH.read_text()
    return splice_schema_skeleton(text)


def persist_raw_spec(document_id: str, target_name: str, raw: dict) -> Path:
    """Persist Step1's raw LLM JSON to `runs/method_specs/raw/<factor>.raw.json`,
    keyed by a filesystem-safe slug (not `MethodSpec.make_factor_id`, since the
    raw dict is not guaranteed to validate yet and shouldn't need to -- this
    is just an evidence artifact, not the canonical identifier).
    """
    RAW_SPEC_DIR.mkdir(parents=True, exist_ok=True)
    slug = f"{document_id}__{target_name}".replace("/", "_")
    out_path = RAW_SPEC_DIR / f"{slug}.raw.json"
    out_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return out_path


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

    raw_spec: Optional[dict] = None
    error: Optional[str] = None
    token_usage: Optional[dict] = None


class MethodSpecExtractor:
    """LLM-driven extraction of a raw MethodSpec-shaped dict (Phase B,
    paper-first schema). Same call/retry machinery as
    `step1_extractor.SemanticExtractor` (JSON-mode chat completion,
    PDF-attachment passthrough when the client supports it, rate-limit
    detection), but does no validation/normalization of its own -- see
    module docstring.

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
        """Extract a raw MethodSpec-shaped dict from paper text (or native
        PDF bytes when the client supports it). No validation is performed
        here -- see `src.steps.step2_reviewer.spec_build`.
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = ExtractionResult()
        self._last_error = None
        self._last_usage = None
        raw = self._call_llm_extract(document_id, target_name, paper_text, pdf_bytes=pdf_bytes)
        result.raw_spec = raw
        result.token_usage = self._last_usage

        if not raw:
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
