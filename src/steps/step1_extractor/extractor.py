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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.infra.data_layer import catalog_menu_text
from src.infra.models.schema_render import splice_schema_skeleton
from src.infra.tooling import (
    Tool,
    ToolContext,
    ToolPolicy,
    ToolResult,
    ToolRunner,
    render_tool_catalog,
    render_tool_results,
    splice_tool_catalog,
)

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


@dataclass
class Step1ToolContext(ToolContext):
    """Step1 is architecturally a single LLM call (see module docstring) --
    no round loop, no `tool_requests`: tools here are pure prelude, run once
    before the one call."""


def _schema_skeleton_fn(ctx: Step1ToolContext) -> ToolResult:
    """Placeholder tool -- the actual JSON skeleton is spliced directly into
    the prompt's "Required JSON Shape" section (`load_extraction_system_
    prompt`), which is the one source of truth; this only registers it in
    the catalog for cross-step consistency (see docs/tools-plus-llm-plan.md
    §4.1) without duplicating the skeleton body a second time.
    """
    return ToolResult(
        name="schema_skeleton",
        status="ok",
        payload={"note": "full skeleton is inlined in the system prompt's Required JSON Shape section, not repeated here"},
    )


SCHEMA_SKELETON_TOOL: Tool[Step1ToolContext] = Tool(
    name="schema_skeleton",
    description="MethodSpec 的 JSON 骨架结构（从 Pydantic 模型自动生成）",
    produces="完整骨架内嵌在系统提示的 Required JSON Shape 示例里，跟当前论文内容无关，是结构约束不是分析结果",
    fn=_schema_skeleton_fn,
    tier="always",
)


def _catalog_menu_fn(ctx: Step1ToolContext) -> ToolResult:
    """Real (non-placeholder) tool: the live data-catalog menu (every
    registered source + column + description), so the extraction LLM can
    fill `RequiredField.source_table`/`source_column` against real,
    already-registered options instead of guessing (see docs/decision-log.md
    2026-08-13 -- this is the point where `MethodSpec` stopped being
    catalog-agnostic)."""
    return ToolResult(name="data_catalog", status="ok", payload={"menu": catalog_menu_text()})


CATALOG_MENU_TOOL: Tool[Step1ToolContext] = Tool(
    name="data_catalog",
    description="当前已注册的数据源清单：每个数据源 + 每一列 + 列的WRDS定义",
    produces="纯信息性列表，用于填 RequiredField.source_table/source_column；跟当前论文内容无关",
    fn=_catalog_menu_fn,
    tier="always",
)

#: Step1's tool registry. Add new prelude tools here (see
#: docs/tools-plus-llm-plan.md §4.1 for candidates deferred so far, e.g.
#: keyword_locate).
STEP1_TOOLS: list[Tool[Step1ToolContext]] = [SCHEMA_SKELETON_TOOL, CATALOG_MENU_TOOL]


def _run_step1_tools(policy: ToolPolicy) -> tuple[list[ToolResult], str]:
    """Runs `STEP1_TOOLS` once (prelude only, no round loop) and returns
    `(tool_results, tool_results_json_block)` -- the latter is appended to
    the user message so the results actually reach the LLM, not just get
    recorded for audit."""
    ctx = Step1ToolContext()
    run = ToolRunner().run_all(STEP1_TOOLS, ctx, policy)
    return run.results, render_tool_results(run.results)


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
    #: Results of Step1's prelude tools (see `STEP1_TOOLS`) -- `schema_skeleton`
    #: (placeholder) + `data_catalog` (real menu, see `_catalog_menu_fn`).
    #: Additive/audit-only; not fed back into any decision (Step1 has no
    #: round loop, see module docstring).
    tool_results: list[ToolResult] = field(default_factory=list)


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
        self._last_tool_results: list[ToolResult] = []

    def extract(
        self,
        document_id: str,
        target_name: str,
        paper_text: str,
        pdf_bytes: bytes | None = None,
        tool_policy: ToolPolicy | None = None,
    ) -> ExtractionResult:
        """Extract a raw MethodSpec-shaped dict from paper text (or native
        PDF bytes when the client supports it). No validation is performed
        here -- see `src.steps.step2_reviewer.spec_build`.

        `tool_policy` defaults to running every registered prelude tool
        (see `STEP1_TOOLS`) -- pass a custom `ToolPolicy` (e.g. to disable
        a tool) if needed; existing callers passing nothing are unaffected.
        """
        if not self.llm_client:
            raise RuntimeError("LLM client required for extraction")

        result = ExtractionResult()
        self._last_error = None
        self._last_usage = None
        raw = self._call_llm_extract(
            document_id, target_name, paper_text, pdf_bytes=pdf_bytes, tool_policy=tool_policy,
        )
        result.raw_spec = raw
        result.token_usage = self._last_usage
        result.tool_results = self._last_tool_results

        if not raw:
            result.error = self._last_error or "LLM returned empty response"

        return result

    def _call_llm_extract(
        self,
        document_id: str,
        target_name: str,
        paper_text: str,
        pdf_bytes: bytes | None = None,
        tool_policy: ToolPolicy | None = None,
    ) -> dict | None:
        client_supports_pdf = hasattr(self.llm_client, "_create_with_pdf") or hasattr(self.llm_client, "_pdf_to_text")
        tool_results, tool_results_block = _run_step1_tools(tool_policy or ToolPolicy())
        self._last_tool_results = tool_results

        system_prompt = splice_tool_catalog(
            load_extraction_system_prompt(),
            render_tool_catalog(STEP1_TOOLS, tool_results),
        )
        user_msg = PAPER_EXTRACTION_USER_TEMPLATE.format(
            document_id=document_id,
            target_name=target_name,
            paper_text="[See attached PDF document above]" if (pdf_bytes and client_supports_pdf) else paper_text,
        )
        user_msg = f"{user_msg}\n\n{tool_results_block}"
        messages = [
            {"role": "system", "content": system_prompt},
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
