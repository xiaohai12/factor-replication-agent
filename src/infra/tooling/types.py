"""Core types for the Tool Prelude pattern (docs/tools-plus-llm-plan.md).

Deterministic tools run BEFORE an LLM call (CLI providers can't do real
mid-inference tool calling, see the plan's §0), and their results are
rendered into the prompt alongside a catalog describing what each one is
and its limits. `Tool` is deliberately a single concrete class (no
Protocol + wrapper split) -- it is both the "spec sheet" (`description`/
`produces`, rendered into the catalog) and the executable unit (`fn`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Literal, TypeVar


@dataclass
class ToolContext:
    """Shared base; each step defines its own subclass with the fields its
    tools need (e.g. `Step2ToolContext` adds `spec_dict`)."""

    results: dict[str, "ToolResult"] = field(default_factory=dict)
    #: Set by the CALLER's loop, never computed here -- what counts as
    #: "the previous round failed" differs per step (schema validation vs.
    #: sandbox/execution errors), so `ToolRunner` only consumes this flag.
    prior_round_failed: bool = False


@dataclass
class ToolResult:
    name: str
    status: Literal["ok", "error", "skipped"]
    payload: dict = field(default_factory=dict)
    error: str | None = None
    #: Reserved for a future payload-size cap (see ToolPolicy.max_payload_chars);
    #: always False for now -- truncation logic is deliberately deferred.
    truncated: bool = False


CtxT = TypeVar("CtxT", bound=ToolContext)


@dataclass
class Tool(Generic[CtxT]):
    name: str
    description: str  # what it does -- rendered into the prompt catalog
    produces: str  # what its output means + its limits -- also rendered
    fn: Callable[[CtxT], ToolResult]
    tier: Literal["always", "on_failure", "opt_in"] = "always"

    def run(self, ctx: CtxT) -> ToolResult:
        return self.fn(ctx)


@dataclass
class ToolPolicy:
    enable: set[str] | None = None  # None = default by tier
    disable: frozenset[str] = frozenset()
    max_payload_chars: int = 4000  # reserved, not enforced yet
    allow_llm_requests: bool = True
