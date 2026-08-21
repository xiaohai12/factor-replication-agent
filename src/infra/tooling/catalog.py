"""Prompt rendering for the tool catalog + results (docs/tools-plus-llm-plan.md
§2 "Prompt 渲染"). Catalog splice mirrors `schema_render.splice_schema_skeleton`:
plain find/slice replacement, missing markers -> text returned unchanged, no
error raised.
"""

from __future__ import annotations

import json

from src.infra.tooling.types import Tool, ToolResult

TOOLS_CATALOG_START = "<!-- TOOLS:CATALOG:START -->"
TOOLS_CATALOG_END = "<!-- TOOLS:CATALOG:END -->"


def render_tool_catalog(
    all_tools: list[Tool],
    executed_results: list[ToolResult],
    unknown_requests: list[str] | None = None,
) -> str:
    """Two sections: tools that ran THIS round (results live in
    `render_tool_results`, this only lists name/description/limits) and
    tools that exist but didn't run (opt_in, requestable via
    `tool_requests` -- the LLM must know a tool's name to ever request it).
    """
    executed_names = {r.name for r in executed_results}
    executed = [t for t in all_tools if t.name in executed_names]
    requestable = [t for t in all_tools if t.name not in executed_names]

    lines = [f"{TOOLS_CATALOG_START}", "## TOOL CATALOG", ""]
    lines.append("### 本轮已执行（结果见下方 TOOL RESULTS）")
    for t in executed:
        lines.append(f"- {t.name}: {t.description}. {t.produces}")
    lines.append("")
    lines.append("### 可按需请求（在 tool_requests 里写工具名，下一轮执行）")
    if requestable:
        for t in requestable:
            lines.append(f"- {t.name}: {t.description}. {t.produces}")
    else:
        lines.append("(none)")
    for name in unknown_requests or []:
        lines.append(f"\n未知工具名：{name!r}（未注册，忽略）")
    lines.append(TOOLS_CATALOG_END)
    return "\n".join(lines)


def render_tool_results(executed_results: list[ToolResult]) -> str:
    """The JSON payload section -- only tools that actually ran this round."""
    lines = ["## TOOL RESULTS"]
    for r in executed_results:
        lines.append(f"\n### {r.name}")
        lines.append(f"status: {r.status}")
        if r.error:
            lines.append(f"error: {r.error}")
        lines.append("```json")
        lines.append(json.dumps(r.payload, indent=2, default=str))
        lines.append("```")
    return "\n".join(lines)


def splice_tool_catalog(markdown_text: str, catalog_body: str) -> str:
    start = markdown_text.find(TOOLS_CATALOG_START)
    end = markdown_text.find(TOOLS_CATALOG_END)
    if start == -1 or end == -1 or end < start:
        return markdown_text
    end += len(TOOLS_CATALOG_END)
    return markdown_text[:start] + catalog_body + markdown_text[end:]
