"""`ToolRunner` -- executes a step's registered tools before an LLM call.

No dependency graph / topological sort (see docs/tools-plus-llm-plan.md §2):
tools run in the exact order the caller lists them. A tool that needs a
prior tool's result reads it from `ctx.results` and self-reports
`status="skipped"` if it isn't there -- `ToolRunner` never reasons about
"what depends on what".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.infra.tooling.types import CtxT, Tool, ToolPolicy, ToolResult

if TYPE_CHECKING:
    from src.infra.trace import PipelineTracer


@dataclass
class RunAllResult:
    results: list[ToolResult] = field(default_factory=list)
    #: Names the LLM requested via `tool_requests` that aren't in the
    #: registry passed to `run_all` -- surfaced so the next round's catalog
    #: can append a "unknown tool name: xxx" notice instead of silently
    #: dropping the request.
    unknown_requests: list[str] = field(default_factory=list)


class ToolRunner:
    def run_all(
        self,
        tools: list[Tool[CtxT]],
        ctx: CtxT,
        policy: ToolPolicy,
        requested: list[str] | None = None,
        tracer: "PipelineTracer | None" = None,
        stage: str = "",
        round_num: int | None = None,
    ) -> RunAllResult:
        requested = requested or []
        registry_names = {t.name for t in tools}
        unknown_requests = [n for n in requested if n not in registry_names]

        results: list[ToolResult] = []
        for tool in tools:
            if tool.name in policy.disable:
                continue
            if not self._should_run(tool, ctx, policy, requested):
                continue
            result = self._run_one(tool, ctx)
            ctx.results[tool.name] = result
            results.append(result)
            if tracer is not None:
                tracer.log(
                    stage,
                    f"tool:{tool.name}",
                    detail=(
                        f"round={round_num} status={result.status} "
                        f"error={result.error or ''}"
                    ),
                )
        return RunAllResult(results=results, unknown_requests=unknown_requests)

    def _should_run(
        self, tool: Tool[CtxT], ctx: CtxT, policy: ToolPolicy, requested: list[str]
    ) -> bool:
        if tool.tier == "always":
            return True
        if tool.tier == "on_failure":
            return ctx.prior_round_failed
        if tool.tier == "opt_in":
            if policy.enable is not None and tool.name in policy.enable:
                return True
            return policy.allow_llm_requests and tool.name in requested
        return False

    def _run_one(self, tool: Tool[CtxT], ctx: CtxT) -> ToolResult:
        try:
            return tool.run(ctx)
        except Exception as exc:  # tool failures must never crash the pipeline
            return ToolResult(name=tool.name, status="error", error=str(exc))
