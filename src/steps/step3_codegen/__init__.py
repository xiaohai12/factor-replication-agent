"""Controlled Meta-Coder - Generate factor signal plugins from approved MethodSpec.

Generated plugins are pure formula-computation functions:
- Accept an intermediate data DataFrame keyed on [permno, time_avail_m]
- Perform only signal formula computation (no data download, no lag handling, no portfolio logic)
- Output: [permno, yyyymm, signal]
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.infra.market_equity_policy import assert_market_equity_contract
from src.infra.models.method_spec import FieldRole, ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord
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

PLUGIN_OUTPUT_COLS = ["permno", "yyyymm", "signal"]

# Prompt file paths
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "meta_coder"
_SIGNAL_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "signal_plugin_system.md"
_REPAIR_PROMPT_PATH = _PROMPTS_DIR / "repair_plugin.md"
_FILTER_DERIVATION_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "filter_derivation_plugin_system.md"


def _load_prompt(path: Path, fallback: str = "") -> str:
    """Load prompt from file, fall back to inline string."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return fallback


# Load prompts from files (with inline fallbacks for backward compat)
METACODER_SYSTEM_PROMPT = _load_prompt(_SIGNAL_SYSTEM_PROMPT_PATH)
FILTER_DERIVATION_SYSTEM_PROMPT = _load_prompt(_FILTER_DERIVATION_SYSTEM_PROMPT_PATH)


_UNICODE_QUOTE_MAP = str.maketrans({
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "′": "'",  # prime
    "″": '"',  # double prime
})


_PYTHON_START = re.compile(
    r"^(import |from |def |class |#|@|\"\"\"|\'\'\').*",
    re.MULTILINE,
)

_TEMPORAL_SYMBOL = re.compile(
    r"\b(?P<base>[A-Za-z_][A-Za-z0-9_]*?)_(?P<clock>[tm])"
    r"(?:(?P<direction>_minus_|_plus_)(?P<distance>\d+))?\b"
)


def _formula_relative_observation_guidance(expression: str) -> list[str]:
    """Describe formula-relative row shifts without assuming a factor or cadence.

    Availability dates are already handled upstream. Temporal suffixes here
    only describe ordering among source observations used by the formula. For
    each base symbol, anchor its most recent referenced suffix to the current
    point-in-time row and express older references as relative row shifts.
    """
    symbols_by_base: dict[str, dict[str, int]] = {}
    for match in _TEMPORAL_SYMBOL.finditer(expression):
        distance = int(match.group("distance") or 0)
        direction = match.group("direction")
        offset = -distance if direction == "_minus_" else distance if direction == "_plus_" else 0
        symbols_by_base.setdefault(match.group("base"), {})[match.group(0)] = offset

    lines: list[str] = []
    for base, symbols in sorted(symbols_by_base.items()):
        if len(set(symbols.values())) < 2:
            continue
        newest_offset = max(symbols.values())
        ordered = sorted(symbols.items(), key=lambda item: (-item[1], item[0]))
        alignments = []
        for symbol, offset in ordered:
            shift = newest_offset - offset
            alignment = "current mapped value" if shift == 0 else f"groupby(permno).shift({shift})"
            alignments.append(f"{symbol} = {alignment}")
        lines.append(f"  - {base}: " + "; ".join(alignments))
    return lines


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences, prose preambles, and normalize Unicode quotes."""
    text = text.strip().translate(_UNICODE_QUOTE_MAP)
    # Remove markdown fences
    text = re.sub(r"^```(?:python)?\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # If the whole block parses cleanly, return as-is
    try:
        import ast as _ast
        _ast.parse(text)
        return text
    except SyntaxError:
        pass
    # Find first line that looks like a Python statement and take from there
    m = _PYTHON_START.search(text)
    if m:
        text = text[m.start():].strip()
    return text


@dataclass
class Step3ToolContext(ToolContext):
    resolved_spec: ResolvedMethodSpec | None = None


def _signal_input_fields(resolved: ResolvedMethodSpec):
    """The `data.fields[]` entries the formula actually references (same
    filter `_build_prompt_from_resolved` uses) -- shared so the
    `column_mapping` tool and the prompt builder can't silently drift."""
    formula_inputs = set(resolved.paper.signal.formula.inputs)
    return [
        f for f in resolved.paper.data.fields
        if FieldRole.SIGNAL_INPUT in f.roles and f.concept_id in formula_inputs
    ]


def _column_mapping_fn(ctx: Step3ToolContext) -> ToolResult:
    if ctx.resolved_spec is None:
        return ToolResult(name="column_mapping", status="skipped", error="no resolved spec supplied")
    mapping = {}
    for f in _signal_input_fields(ctx.resolved_spec):
        source_column = ctx.resolved_spec.resolution.concept_mapping.get(f.concept_id)
        if source_column is not None:
            mapping[f.concept_id] = {"source": source_column.source, "column": source_column.column}
    return ToolResult(name="column_mapping", status="ok", payload={"concept_to_column": mapping})


COLUMN_MAPPING_TOOL: Tool[Step3ToolContext] = Tool(
    name="column_mapping",
    description="论文概念(concept_id) 到实际 DataFrame 列名的对照表",
    produces="{concept_id: {source, column}} -- compute_signal 写公式时引用哪列就看这份映射，不要自己猜列名",
    fn=_column_mapping_fn,
    tier="always",
)

#: Step3's tool registry (generate_plugin() is a single LLM call per
#: invocation, same prelude-only shape as Step1 -- see
#: docs/tools-plus-llm-plan.md §4.2/§4).
STEP3_TOOLS: list[Tool[Step3ToolContext]] = [COLUMN_MAPPING_TOOL]


class MetaCoder:
    """Generates factor-specific signal construction plugins, and (see
    `generate_filter_derivation_plugin`) universe-filter-concept derivation
    plugins -- same codegen infrastructure (LLM call, code-fence stripping,
    repair loop), different system prompt per generation kind.

    For SIGNAL plugins, the Meta-Coder is ONLY allowed to generate signal
    construction code. It CANNOT:
    - Compute portfolio returns
    - Decide breakpoints or weighting
    - Construct long-short portfolios
    - Modify universe filters
    - Change missing-value policy
    - Alter lag assumptions (lag is handled upstream via time_avail_m)
    """

    def __init__(self, llm_client=None, reference_code_path: Optional[str] = None):
        self.llm_client = llm_client
        self.reference_code_path = Path(reference_code_path) if reference_code_path else None

    def generate_plugin(self, spec: ResolvedMethodSpec, tool_policy: ToolPolicy | None = None) -> PluginRecord:
        """Generate a signal construction plugin from an approved, ready
        `ResolvedMethodSpec` (`spec.is_ready` gates readiness -- see
        `ResolvedMethodSpec.is_ready`). Implementation decisions (timing,
        missing-data policy) are read from the resolved paper/resolution
        fields via `_build_prompt_from_resolved`; physical column mapping is
        the `column_mapping` prelude tool (`STEP3_TOOLS`), run once before
        this single LLM call (same prelude-only shape as Step1 -- see
        docs/tools-plus-llm-plan.md §4.2).
        """
        if not spec.is_ready:
            raise ValueError("Cannot generate plugin from a ResolvedMethodSpec that isn't ready")
        assert_market_equity_contract(spec)
        if not self.llm_client:
            raise RuntimeError("llm_client required for MetaCoder.generate_plugin()")

        ctx = Step3ToolContext(resolved_spec=spec)
        run = ToolRunner().run_all(STEP3_TOOLS, ctx, tool_policy or ToolPolicy())
        system_prompt = splice_tool_catalog(
            METACODER_SYSTEM_PROMPT, render_tool_catalog(STEP3_TOOLS, run.results),
        )
        user_prompt = self._build_prompt_from_resolved(spec)
        user_prompt = f"{user_prompt}\n\n{render_tool_results(run.results)}"

        from src.infra.llm import extract_usage

        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        code = _strip_code_fences(response.choices[0].message.content or "")
        token_usage = extract_usage(response)

        spec_hash = spec.paper.content_hash()[:16]
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]

        record = PluginRecord(
            plugin_id=spec.paper.factor_id,
            factor_id=spec.paper.factor_id,
            method_spec_hash=spec_hash,
            code=code,
            code_hash=code_hash,
        )
        record.__dict__["_token_usage"] = token_usage
        return record

    def _build_prompt_from_resolved(self, resolved: ResolvedMethodSpec) -> str:
        """Reads
        `signal.formula.steps`/`paper_expression`/`timing.*` -- physical
        column mapping is now the `column_mapping` prelude tool
        (`STEP3_TOOLS`), not rendered here (see docs/tools-plus-llm-plan.md
        §4.2).
        """
        paper = resolved.paper
        formula = paper.signal.formula

        formula_str = formula.paper_expression
        step_lines = [f"  {i}. {s.description}" + (f" ({s.expression})" if s.expression else "") for i, s in enumerate(formula.steps, start=1)]

        timing = paper.timing
        lag_months = timing.data_availability.lag_value
        formation_month = timing.formation_month.value if timing.formation_month else None
        rebalance = timing.rebalance_frequency.value.value if timing.rebalance_frequency.value else None

        missing_entry = next(
            (mp for mp in paper.portfolio.missing_policies if mp.stage.value == "signal"), None
        )

        lines = [
            f"Generate a Python signal plugin for factor: {paper.target_name}",
            f"Factor ID: {paper.factor_id}",
            "",
            "## Signal Formula",
            f"Paper notation:    {formula_str}",
        ]
        if step_lines:
            lines += ["", "## Calculation Steps"] + step_lines

        formula_inputs = set(formula.inputs)
        signal_input_fields = _signal_input_fields(resolved)
        if signal_input_fields:
            lines += ["", "## Data Fields"]
            for f in signal_input_fields:
                lines.append(f"  - {f.concept_id}: {f.name_in_paper} (source: {f.paper_source_hint})")

        lines += [
            "",
            "## Universe / Sample Membership",
            "Do NOT filter by exchange, SIC/industry code, or listing history inside "
            "compute_signal -- the engine applies portfolio.universe_filters "
            "separately, on the CRSP-only panel, after compute_signal runs. Only "
            "apply a row filter here if it's a genuine FORMULA computability "
            "precondition (e.g. a required input must be non-missing/non-zero to "
            "even calculate the signal), never a sample-eligibility rule.",
        ]
        lines += ["", "## Timing"]
        if formation_month:
            lines.append(f"  - Portfolio formation: end of month {formation_month}")
        if rebalance:
            lines.append(f"  - Rebalance frequency: {rebalance}")
        if lag_months is not None:
            lines.append(
                f"  - Accounting lag: {lag_months} months (already applied upstream — do NOT re-apply)"
            )
        relative_observation_lines = _formula_relative_observation_guidance(formula_str)
        if relative_observation_lines:
            lines += [
                "  - Formula-relative observation alignment (independent of availability lag):",
                "    Anchor each base field's most recent referenced temporal suffix to the "
                "current point-in-time mapped value. Older suffixes use relative source-row "
                "shifts; do not add the accounting lag again.",
                *relative_observation_lines,
            ]

        if missing_entry is not None and missing_entry.action.value not in ("unspecified", None):
            lines += ["", f"## Missing Data\n  - Action: {missing_entry.action.value}"]
            if missing_entry.threshold:
                lines.append(f"  - Threshold: {missing_entry.threshold}")
            for ev in missing_entry.action.evidence:
                if ev.quote:
                    lines.append(f"  - Paper evidence: \"{ev.quote}\"")
                    break

        lines += [
            "",
            "## Instructions",
            "Write the complete `compute_signal(df)` function. Output ONLY the Python code, no explanation.",
        ]
        return "\n".join(lines)

    def generate_filter_derivation_plugin(self, spec: ResolvedMethodSpec, filter_index: int) -> PluginRecord:
        """Generate a small plugin computing ONE universe filter's derived
        value from its `resolution.concept_mapping` physical column, per
        `paper.universe.filters[filter_index].derivation` (a `FormulaSpec`,
        same shape/review posture as `signal.formula` -- see
        docs/resolve-diagnostics-gaps.md problem 1/3). Not yet wired into
        `script_generator`/Step4/Step5 -- this is the codegen entry point
        only, mirroring `generate_plugin`'s LLM-call/repair infrastructure
        with a dedicated system prompt (filter derivation has different
        rules than signal computation: return a derived Series, not a mask
        or a signal column).
        """
        filt = spec.paper.universe.filters[filter_index]
        if filt.derivation is None:
            raise ValueError(f"universe.filters[{filter_index}] ({filt.concept_id!r}) has no derivation to codegen")
        if not self.llm_client:
            raise RuntimeError("llm_client required for MetaCoder.generate_filter_derivation_plugin()")

        user_prompt = self._build_prompt_for_filter_derivation(spec, filter_index)

        from src.infra.llm import extract_usage

        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": FILTER_DERIVATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        code = _strip_code_fences(response.choices[0].message.content or "")
        token_usage = extract_usage(response)

        spec_hash = spec.paper.content_hash()[:16]
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]

        record = PluginRecord(
            plugin_id=f"{spec.paper.factor_id}::filter_derivation::{filt.concept_id}",
            factor_id=spec.paper.factor_id,
            method_spec_hash=spec_hash,
            code=code,
            code_hash=code_hash,
            entry_function="compute_filter_value",
        )
        record.__dict__["_token_usage"] = token_usage
        return record

    def _build_prompt_for_filter_derivation(self, spec: ResolvedMethodSpec, filter_index: int) -> str:
        """Mirrors `_build_prompt_from_resolved`: reads `derivation.steps`/
        `paper_expression` (paper side, reviewed) + the physical column via
        `resolution.concept_mapping` (resolution side) -- combined here at
        codegen time only, same division of labor as compute_signal.
        """
        paper = spec.paper
        resolution = spec.resolution
        filt = paper.universe.filters[filter_index]
        derivation = filt.derivation
        assert derivation is not None

        mapping = resolution.concept_mapping.get(filt.concept_id)
        if mapping is None:
            raise ValueError(f"universe.filters[{filter_index}] ({filt.concept_id!r}) has no concept_mapping entry")

        step_lines = [
            f"  {i}. {s.description}" + (f" ({s.expression})" if s.expression else "")
            for i, s in enumerate(derivation.steps, start=1)
        ]

        lines = [
            f"Generate a Python filter-derivation plugin for factor: {paper.target_name}",
            f"Factor ID: {paper.factor_id}",
            f"Universe filter concept: {filt.concept_id}",
            "",
            "## Derivation",
            f"Paper notation:    {derivation.paper_expression}",
        ]
        if step_lines:
            lines += ["", "## Calculation Steps"] + step_lines
        lines += [
            "",
            "## Column Mapping (underlying physical column)",
            f"  - {filt.concept_id} -> df[\"{mapping.column}\"]",
            "",
            "## Instructions",
            "Write the complete `compute_filter_value(df)` function. Output ONLY the Python code, no explanation.",
        ]
        return "\n".join(lines)

    def repair_plugin(self, plugin: PluginRecord, errors: list[str]) -> PluginRecord:
        """Attempt bounded repair of a failed plugin (technical errors only).

        Empirical assumption changes must go back through Review Gate.
        Max 3 repair attempts enforced by Pipeline.
        """
        if not self.llm_client:
            raise RuntimeError("llm_client required for repair_plugin()")

        error_block = "\n".join(f"  - {e}" for e in errors)
        repair_template = _load_prompt(_REPAIR_PROMPT_PATH)
        if repair_template and "{errors}" in repair_template:
            repair_prompt = repair_template.replace("{errors}", error_block).replace("{code}", plugin.code)
        else:
            repair_prompt = (
                f"Fix the following Python signal plugin. Correct ONLY syntax errors, "
                f"schema issues, and faithfulness-to-approved-formula bugs.\n"
                f"Do NOT change the empirical formula or any data assumptions.\n\n"
                f"## Errors to fix\n{error_block}\n\n"
                f"## Current code\n{plugin.code}\n\n"
                f"Output ONLY the corrected Python code."
            )
        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": METACODER_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.0,
        )
        raw_code = response.choices[0].message.content or ""
        new_code = _strip_code_fences(raw_code)
        new_hash = hashlib.sha256(new_code.encode()).hexdigest()[:16]

        return PluginRecord(
            plugin_id=plugin.plugin_id,
            factor_id=plugin.factor_id,
            method_spec_hash=plugin.method_spec_hash,
            code=new_code,
            code_hash=new_hash,
            repair_trace=plugin.repair_trace + [f"Repair: {'; '.join(errors[:2])}"],
        )
