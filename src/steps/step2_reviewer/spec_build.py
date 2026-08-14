"""Step2's single bounded review loop: raw Step1 dict -> validated,
LLM-reviewed `MethodSpec` (see docs/step1-step2-refactor-plan.md and the
2026-08-11 follow-up in docs/decision-log.md).

Each round: **validate before LLM review** (including round 1, against
Step1's raw dict -- almost certainly fails since menu fields aren't
classified yet), so every round has the same shape ("look at the latest
`ValidationError` text, then review"). The LLM reviews the *entire* spec
against the paper text and the current `error_log`, and its rewritten spec
is trusted **wholesale** (2026-08-11 decision: replaced the earlier
"only merge explicitly declared fields" guardrail) -- except for
`factor_id`/`schema_version`/`paper.document_id` (D7), which are always
re-injected deterministically and never taken from the LLM's output.
Every field-level change the LLM makes is captured as a mechanical
before/after diff (`ReviewRound.diff`) so a human can see exactly what
changed each round, rather than the system silently discarding undeclared
changes.

Loop exit: `model_validate` passes AND this round's LLM rewrite produced
no diff at all (nothing left to change) -> exit to rule-based review
(`review_method_spec`, D2 only). Budget exhausted (`MAX_REVIEW_ROUNDS`
rounds, each one full validate+LLM-review cycle) -> return an
`error`-carrying outcome (never raises), for a human to resolve.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.infra.data_layer import catalog_menu_text
from src.infra.models.method_spec import MethodReview, MethodSpec
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
from src.steps.step2_reviewer.review import load_llm_review_system_prompt, review_method_spec

MAX_REVIEW_ROUNDS = 3

_MISSING = object()  # sentinel: a path present on one side of a diff but not the other

_USER_TEMPLATE = """\
Paper text:

{paper_text}

Current MethodSpec JSON (round {round_num} of at most {total_rounds}):

{spec_json}

{tool_results_block}

Return the JSON object described in the system prompt.
"""


def _diff_json(old: Any, new: Any, path: str = "") -> list[dict]:
    """Flat list of every leaf-level change between two JSON-shaped
    dicts/lists, as `{"field_path": ..., "old": ..., "new": ...}` -- the
    mechanical basis for both the loop's convergence check (no diff = LLM
    made no further changes) and the human-facing before/after view
    (frontend highlights each entry in red). Compares dicts key-by-key and
    lists index-by-index (the spec's lists -- sorts/legs/fields/etc. --
    are order-stable arrays, not sets).
    """
    diffs: list[dict] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            child_path = f"{path}.{key}" if path else key
            diffs.extend(_diff_json(old.get(key, _MISSING), new.get(key, _MISSING), child_path))
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            child_path = f"{path}[{i}]"
            old_item = old[i] if i < len(old) else _MISSING
            new_item = new[i] if i < len(new) else _MISSING
            diffs.extend(_diff_json(old_item, new_item, child_path))
    elif old != new:
        diffs.append({
            "field_path": path,
            "old": None if old is _MISSING else old,
            "new": None if new is _MISSING else new,
        })
    return diffs


@dataclass
class ReviewRound:
    round_num: int
    spec_before: dict
    tool_results: list[ToolResult] = field(default_factory=list)
    spec_after: dict | None = None
    llm_raw: dict | None = None
    diff: list[dict] = field(default_factory=list)
    call_error: str | None = None

    @property
    def error_log(self) -> str:
        """Renders `tool_results` back into the old `[tool_name]\\nreport`
        tagged-block text -- kept for the UI and existing tests
        ([tests/test_step2_reviewer_llm.py](../../../tests/test_step2_reviewer_llm.py)
        only asserts `==""`/`!=""`/substring, never the exact tag format, so
        this is a safe compatibility shim over the new `tool_results`."""
        parts = []
        for r in self.tool_results:
            report = r.payload.get("report")
            if report:
                parts.append(f"[{r.name}]\n{report}")
        return "\n\n".join(parts)


@dataclass
class SpecBuildOutcome:
    spec: MethodSpec | None = None
    review: MethodReview | None = None
    history: list[ReviewRound] = field(default_factory=list)
    error: str | None = None
    #: Mechanical diff between Step1's raw dict (post D7-injection) and the
    #: final converged spec -- the "total" before/after view; `history[i].
    #: diff` gives the same thing broken out per round.
    total_diff: list[dict] = field(default_factory=list)
    #: Last round's `value_corrections`/`additional_findings` annotations,
    #: if the LLM emitted any -- informational only (explains WHY a diff
    #: entry changed), never a merge gate. See module docstring.
    llm_notes: dict = field(default_factory=dict)
    #: Last round's tool results (same semantics as `spec`/`review`: the
    #: "final state"). Full per-round history is in `history[i].tool_results`.
    tool_results: list[ToolResult] = field(default_factory=list)


def _inject_deterministic_fields(raw: dict, document_id: str, target_name: str) -> dict:
    """D7: `factor_id`/`schema_version`/`paper.document_id` are never taken
    from the LLM, in every round (not just the first) -- this is the one
    guardrail that survived the 2026-08-11 "trust the LLM's rewrite
    wholesale" decision, since inventing an unstable identifier is a
    different failure mode than an empirical judgment call.
    """
    raw = copy.deepcopy(raw)
    raw["factor_id"] = MethodSpec.make_factor_id(document_id, target_name)
    raw["target_name"] = target_name
    raw["schema_version"] = "methodspec.v2"
    paper_block = dict(raw.get("paper") or {})
    paper_block["document_id"] = document_id
    raw["paper"] = paper_block
    return raw


def _call_llm_review(
    spec_dict: dict,
    paper_text: str,
    tool_results: list[ToolResult],
    unknown_requests: list[str],
    round_num: int,
    total_rounds: int,
    llm_client,
) -> dict:
    system_prompt = splice_tool_catalog(
        load_llm_review_system_prompt(),
        render_tool_catalog(STEP2_TOOLS, tool_results, unknown_requests),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                paper_text=paper_text,
                round_num=round_num,
                total_rounds=total_rounds,
                spec_json=json.dumps(spec_dict, indent=2, default=str),
                tool_results_block=render_tool_results(tool_results),
            ),
        },
    ]
    response = llm_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


@dataclass
class Step2ToolContext(ToolContext):
    spec_dict: dict = field(default_factory=dict)
    #: Written by `_schema_validation_fn` so `_engine_menu_fn` can read a
    #: real `MethodSpec` instead of a possibly-invalid raw dict -- a
    #: dedicated field rather than `ctx.results` (which is typed
    #: `dict[str, ToolResult]`, not a place for arbitrary objects).
    parsed_spec: MethodSpec | None = None


def _schema_validation_tool(spec_dict: dict) -> tuple[MethodSpec | None, str]:
    """Pydantic structural validation. Returns the parsed `MethodSpec` (so
    later tools can run on a real object, not a raw dict) plus a report
    string (empty when it passes).
    """
    try:
        return MethodSpec.model_validate(spec_dict), ""
    except ValidationError as exc:
        return None, str(exc)


def _engine_menu_and_capability_tool(spec: MethodSpec) -> str:
    """Every `review_method_spec` Finding (D2 evidence-status + missing_
    mapping + the engine-menu/capability checks) -- informational only,
    never gates loop convergence (see `build_reviewed_method_spec`'s
    docstring).
    """
    findings = review_method_spec(spec).findings
    if not findings:
        return ""
    lines = [f"- [{f.kind}/{f.disposition.value}] {f.field_path}: {f.reason}" for f in findings]
    return "\n".join(lines)


def _schema_validation_fn(ctx: Step2ToolContext) -> ToolResult:
    spec, report = _schema_validation_tool(ctx.spec_dict)
    ctx.parsed_spec = spec
    return ToolResult(
        name="schema_validation",
        status="ok" if spec is not None else "error",
        payload={"report": report} if report else {},
    )


def _engine_menu_fn(ctx: Step2ToolContext) -> ToolResult:
    if ctx.parsed_spec is None:
        return ToolResult(
            name="engine_menu_and_capability",
            status="skipped",
            error="requires a validated MethodSpec (schema_validation must pass first)",
        )
    report = _engine_menu_and_capability_tool(ctx.parsed_spec)
    return ToolResult(
        name="engine_menu_and_capability",
        status="ok",
        payload={"report": report} if report else {},
    )


SCHEMA_VALIDATION_TOOL: Tool[Step2ToolContext] = Tool(
    name="schema_validation",
    description="Pydantic 结构校验 MethodSpec",
    produces="校验通过与否 + 错误列表。局限：只查结构，不查经验参数合理性",
    fn=_schema_validation_fn,
    tier="always",
)

ENGINE_MENU_TOOL: Tool[Step2ToolContext] = Tool(
    name="engine_menu_and_capability",
    description="review_method_spec 的全部 Finding（D2证据状态 + missing_mapping + 引擎菜单/能力检查）",
    produces="字段级 finding 列表，仅供参考，从不阻塞循环收敛",
    fn=_engine_menu_fn,
    tier="always",
)


def _catalog_menu_fn(ctx: Step2ToolContext) -> ToolResult:
    """Live data-catalog menu (every registered source + column + WRDS
    definition), SAME text `Step1`'s `data_catalog` tool exposes -- lets the
    review LLM check/correct `data.fields[].source_table`/`source_column`
    against real options (see prompts/review_gate/llm_review.md). This is
    just a static reference listing (cheap, no LLM cost, safe to recompute
    every round) -- NOT a live `build_implementation_resolution` attempt,
    which is deliberately still excluded from this loop (see `STEP2_TOOLS`
    docstring: a real resolve attempt on a still-changing spec would be
    wasted work)."""
    return ToolResult(name="data_catalog", status="ok", payload={"menu": catalog_menu_text()})


CATALOG_MENU_TOOL: Tool[Step2ToolContext] = Tool(
    name="data_catalog",
    description="当前已注册的数据源清单：每个数据源 + 每一列 + 列的WRDS定义",
    produces="纯信息性列表，用于核对/纠正 data.fields[].source_table/source_column；跟具体spec无关，是静态参考",
    fn=_catalog_menu_fn,
    tier="always",
)

#: Step2's tool registry. `data_catalog` is a static reference menu (safe
#: every round, zero extra LLM cost) -- but an actual `build_implementation_
#: resolution` RESOLVE ATTEMPT is still deliberately excluded from this loop
#: (see docs/tools-plus-llm-plan.md §5): the spec is still being rewritten
#: round to round, so a real resolve attempt here would be wasted/stale
#: work. `tool_requests` parsing still runs uniformly (see §5's “circuit
#: stays consistent across steps” decision) for any future `opt_in` tool.
STEP2_TOOLS: list[Tool[Step2ToolContext]] = [SCHEMA_VALIDATION_TOOL, ENGINE_MENU_TOOL, CATALOG_MENU_TOOL]


def _run_step2_tools(
    spec_dict: dict, policy: ToolPolicy, requested: list[str] | None = None
) -> tuple[bool, list[ToolResult], list[str]]:
    """Runs `STEP2_TOOLS` (schema validation first, since
    `engine_menu_and_capability` needs a validated `MethodSpec`) and returns
    `(validate_passed, tool_results, unknown_requests)` -- `validate_passed`
    still means ONLY "schema validation passed" (the loop's convergence
    check depends only on this; findings are informational, see module
    docstring)."""
    ctx = Step2ToolContext(spec_dict=spec_dict)
    run = ToolRunner().run_all(STEP2_TOOLS, ctx, policy, requested=requested)
    return ctx.parsed_spec is not None, run.results, run.unknown_requests


def build_reviewed_method_spec(
    raw: dict,
    document_id: str,
    target_name: str,
    paper_text: str,
    llm_client,
    max_rounds: int = MAX_REVIEW_ROUNDS,
    log=None,
    tool_policy: ToolPolicy | None = None,
) -> SpecBuildOutcome:
    log = log or (lambda msg: None)
    policy = tool_policy or ToolPolicy()
    total_rounds = max_rounds  # exactly max_rounds validate+LLM-review cycles, no +1
    outcome = SpecBuildOutcome()
    log("Injecting deterministic fields (factor_id/schema_version/paper.document_id)...")
    initial_spec = _inject_deterministic_fields(raw, document_id, target_name)
    spec_dict = initial_spec
    requested: list[str] = []

    for round_num in range(1, total_rounds + 1):
        log(f"Round {round_num}/{total_rounds}: running pre-LLM tools (schema validation + engine-menu/capability findings)...")
        validate_passed, tool_results, unknown_requests = _run_step2_tools(spec_dict, policy, requested)
        log(f"Round {round_num}/{total_rounds}: pre-LLM tools done (validate_passed={validate_passed}).")

        round_record = ReviewRound(round_num=round_num, tool_results=tool_results, spec_before=spec_dict)
        log(f"Round {round_num}/{total_rounds}: calling LLM review...")
        try:
            llm_raw = _call_llm_review(
                spec_dict, paper_text, tool_results, unknown_requests, round_num, total_rounds, llm_client,
            )
        except Exception as exc:  # noqa: BLE001 - any LLM/client failure just ends this round with no progress
            round_record.call_error = str(exc)
            outcome.history.append(round_record)
            outcome.tool_results = tool_results
            log(f"Round {round_num}/{total_rounds}: LLM call failed: {exc}")
            if validate_passed:
                log(f"Round {round_num}/{total_rounds}: spec already valid -- stopping here despite the failed call.")
                break
            log(f"Round {round_num}/{total_rounds}: retrying (spec still invalid)...")
            continue

        log(f"Round {round_num}/{total_rounds}: LLM review returned, computing diff against the previous round...")
        round_record.llm_raw = llm_raw
        llm_spec = llm_raw.get("spec") if isinstance(llm_raw, dict) else None
        new_spec = _inject_deterministic_fields(llm_spec, document_id, target_name) if isinstance(llm_spec, dict) else spec_dict

        diff = _diff_json(spec_dict, new_spec)
        round_record.spec_after = new_spec
        round_record.diff = diff
        outcome.history.append(round_record)
        outcome.tool_results = tool_results
        outcome.llm_notes = {
            "value_corrections": (llm_raw or {}).get("value_corrections") or [],
            "additional_findings": (llm_raw or {}).get("additional_findings") or [],
        }
        # Step2 currently registers no `opt_in` tools (see STEP2_TOOLS), so
        # any request here always falls into next round's "unknown tool
        # name" catalog notice -- harmless, kept for cross-step loop-shape
        # consistency (docs/tools-plus-llm-plan.md §5).
        requested = (llm_raw or {}).get("tool_requests") or [] if policy.allow_llm_requests else []
        log(f"Round {round_num}/{total_rounds}: diff has {len(diff)} changed field(s).")

        spec_dict = new_spec

        if validate_passed and not diff:
            log(f"Round {round_num}/{total_rounds}: converged (validate passed, no further changes) -- exiting loop.")
            break
        log(f"Round {round_num}/{total_rounds}: not converged yet, continuing...")

    log("Running final model_validate() on the converged spec...")
    outcome.total_diff = _diff_json(initial_spec, spec_dict)

    try:
        final_spec = MethodSpec.model_validate(spec_dict)
    except ValidationError as exc:
        outcome.error = f"validation failed after {len(outcome.history)} review round(s): {exc}"
        log(f"Final model_validate() failed: {outcome.error}")
        return outcome

    log("Final model_validate() passed. Running rule-based review (D2/missing-mapping)...")
    outcome.spec = final_spec
    outcome.review = review_method_spec(final_spec)
    log(f"Rule-based review done: {len(outcome.review.findings)} finding(s).")
    return outcome
