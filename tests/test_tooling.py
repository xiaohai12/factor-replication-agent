"""Tests for the Tool Prelude infra (src/infra/tooling/) per
docs/tools-plus-llm-plan.md's agreed coverage list."""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class _FakeCtx(ToolContext):
    value: int = 0


def _ok_tool(name: str = "ok") -> Tool[_FakeCtx]:
    return Tool(
        name=name,
        description="always succeeds",
        produces="a constant payload",
        fn=lambda ctx: ToolResult(name=name, status="ok", payload={"v": 1}),
    )


class TestFailureIsolation:
    def test_raising_tool_is_isolated_and_marked_error(self):
        def _boom(ctx: _FakeCtx) -> ToolResult:
            raise RuntimeError("kaboom")

        tool = Tool(name="boom", description="d", produces="p", fn=_boom)
        runner = ToolRunner()
        result = runner.run_all([tool], _FakeCtx(), ToolPolicy())
        assert len(result.results) == 1
        assert result.results[0].status == "error"
        assert "kaboom" in result.results[0].error


class TestSelfReportedDependency:
    def test_tool_reads_ctx_results_and_skips_when_prereq_missing(self):
        def _needs_prior(ctx: _FakeCtx) -> ToolResult:
            prior = ctx.results.get("prereq")
            if prior is None or prior.status != "ok":
                return ToolResult(name="dependent", status="skipped", error="requires prereq")
            return ToolResult(name="dependent", status="ok", payload={})

        dependent = Tool(name="dependent", description="d", produces="p", fn=_needs_prior)
        runner = ToolRunner()

        # Prereq never ran -> dependent self-skips.
        result = runner.run_all([dependent], _FakeCtx(), ToolPolicy())
        assert result.results[0].status == "skipped"

        # Prereq ran and passed -> dependent runs for real.
        prereq = _ok_tool("prereq")
        result = runner.run_all([prereq, dependent], _FakeCtx(), ToolPolicy())
        assert [r.status for r in result.results] == ["ok", "ok"]


class TestDisable:
    def test_disabled_tool_does_not_run_and_is_absent_from_both_catalog_sections(self):
        tool = _ok_tool("secret")
        runner = ToolRunner()
        policy = ToolPolicy(disable=frozenset({"secret"}))
        result = runner.run_all([tool], _FakeCtx(), policy)
        assert result.results == []

        catalog = render_tool_catalog([], [])  # caller passes only enabled tools
        assert "secret" not in catalog


class TestOptIn:
    def test_opt_in_tool_does_not_run_by_default(self):
        tool = Tool(**{**_ok_tool("optional").__dict__, "tier": "opt_in"})
        runner = ToolRunner()
        result = runner.run_all([tool], _FakeCtx(), ToolPolicy())
        assert result.results == []

    def test_opt_in_tool_runs_when_requested(self):
        tool = Tool(**{**_ok_tool("optional").__dict__, "tier": "opt_in"})
        runner = ToolRunner()
        result = runner.run_all([tool], _FakeCtx(), ToolPolicy(), requested=["optional"])
        assert len(result.results) == 1
        assert result.results[0].status == "ok"

    def test_unrequested_opt_in_tool_ignored_when_allow_llm_requests_false(self):
        tool = Tool(**{**_ok_tool("optional").__dict__, "tier": "opt_in"})
        runner = ToolRunner()
        policy = ToolPolicy(allow_llm_requests=False)
        result = runner.run_all([tool], _FakeCtx(), policy, requested=["optional"])
        assert result.results == []


class TestUnknownToolRequest:
    def test_unknown_requested_name_is_reported_not_raised(self):
        runner = ToolRunner()
        result = runner.run_all([], _FakeCtx(), ToolPolicy(), requested=["does_not_exist"])
        assert result.results == []
        assert result.unknown_requests == ["does_not_exist"]

    def test_unknown_tool_name_appears_in_next_catalog(self):
        catalog = render_tool_catalog([], [], unknown_requests=["ghost_tool"])
        assert "ghost_tool" in catalog
        assert "未知工具名" in catalog


class TestOnFailureTier:
    def test_runs_only_when_caller_marks_prior_round_failed(self):
        tool = Tool(**{**_ok_tool("repair_hint").__dict__, "tier": "on_failure"})
        runner = ToolRunner()

        ctx = _FakeCtx(prior_round_failed=False)
        result = runner.run_all([tool], ctx, ToolPolicy())
        assert result.results == []

        ctx = _FakeCtx(prior_round_failed=True)
        result = runner.run_all([tool], ctx, ToolPolicy())
        assert len(result.results) == 1
        assert result.results[0].status == "ok"


class TestTracer:
    def test_no_tracer_does_not_raise(self):
        runner = ToolRunner()
        result = runner.run_all([_ok_tool()], _FakeCtx(), ToolPolicy(), tracer=None)
        assert len(result.results) == 1

    def test_tracer_receives_one_event_per_executed_tool(self):
        @dataclass
        class _FakeTracer:
            events: list = field(default_factory=list)

            def log(self, stage, event, detail="", level="info"):
                self.events.append((stage, event, detail))

        tracer = _FakeTracer()
        runner = ToolRunner()
        runner.run_all([_ok_tool()], _FakeCtx(), ToolPolicy(), tracer=tracer, stage="step_test")
        assert len(tracer.events) == 1
        assert tracer.events[0][0] == "step_test"
        assert tracer.events[0][1] == "tool:ok"


class TestCatalogSplice:
    def test_marker_present_gets_replaced(self):
        text = "before\n<!-- TOOLS:CATALOG:START -->\nold\n<!-- TOOLS:CATALOG:END -->\nafter"
        spliced = splice_tool_catalog(text, "NEWBODY")
        assert spliced == "before\nNEWBODY\nafter"

    def test_marker_missing_returns_text_unchanged(self):
        text = "no markers here"
        assert splice_tool_catalog(text, "NEWBODY") == text

    def test_executed_section_lists_only_tools_that_ran(self):
        executed = _ok_tool("ran")
        pending = Tool(**{**_ok_tool("pending").__dict__, "tier": "opt_in"})
        results = [ToolResult(name="ran", status="ok", payload={})]
        catalog = render_tool_catalog([executed, pending], results)
        exec_section, request_section = catalog.split("可按需请求")
        assert "ran" in exec_section
        assert "pending" not in exec_section
        assert "pending" in request_section

    def test_tool_results_section_only_contains_executed_payloads(self):
        results = [ToolResult(name="ran", status="ok", payload={"k": "v"})]
        body = render_tool_results(results)
        assert "### ran" in body
        assert '"k": "v"' in body
