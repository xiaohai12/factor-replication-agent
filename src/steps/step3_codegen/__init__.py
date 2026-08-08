"""Controlled Meta-Coder - Generate factor signal plugins from approved MethodSpec.

Generated plugins are pure formula-computation functions:
- Accept an intermediate data DataFrame keyed on [permno, time_avail_m]
- Perform only signal formula computation (no data download, no lag handling, no portfolio logic)
- Output: [permno, yyyymm, signal]
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from src.infra.models.paper_method_spec import FieldRole, ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord


PLUGIN_OUTPUT_COLS = ["permno", "yyyymm", "signal"]

# Prompt file paths
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "meta_coder"
_SIGNAL_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "signal_plugin_system.md"
_REPAIR_PROMPT_PATH = _PROMPTS_DIR / "repair_plugin.md"


def _load_prompt(path: Path, fallback: str = "") -> str:
    """Load prompt from file, fall back to inline string."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return fallback


# Load prompts from files (with inline fallbacks for backward compat)
METACODER_SYSTEM_PROMPT = _load_prompt(_SIGNAL_SYSTEM_PROMPT_PATH)


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


class MetaCoder:
    """Generates factor-specific signal construction plugins.

    The Meta-Coder is ONLY allowed to generate signal construction code.
    It CANNOT:
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

    def generate_plugin(self, spec: ResolvedMethodSpec) -> PluginRecord:
        """Generate a signal construction plugin from an approved, ready
        `ResolvedMethodSpec` (`spec.is_ready` gates readiness -- see
        `ResolvedMethodSpec.is_ready`). Implementation decisions (physical
        column mapping, timing, missing-data policy) are read from the
        resolved paper/resolution fields via `_build_prompt_from_resolved`.
        """
        if not spec.is_ready:
            raise ValueError("Cannot generate plugin from a ResolvedMethodSpec that isn't ready")
        if not self.llm_client:
            raise RuntimeError("llm_client required for MetaCoder.generate_plugin()")

        user_prompt = self._build_prompt_from_resolved(spec)

        from src.infra.llm import extract_usage

        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": METACODER_SYSTEM_PROMPT},
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
        `signal.formula.steps`/`paper_expression`, `timing.*`, and physical
        columns via `resolution.concept_mapping` instead of v1's flat
        `formula.expression`/`normalized_mapping` fields.
        """
        paper = resolved.paper
        resolution = resolved.resolution
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
        signal_input_fields = [
            f for f in paper.data.fields if FieldRole.SIGNAL_INPUT in f.roles and f.concept_id in formula_inputs
        ]
        if signal_input_fields:
            lines += ["", "## Data Fields"]
            for f in signal_input_fields:
                lines.append(f"  - {f.concept_id}: {f.paper_name} (source: {f.paper_source_hint})")

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

        if signal_input_fields:
            lines += ["", "## Column Mapping (paper field → physical DataFrame column)"]
            for f in signal_input_fields:
                mapping = resolution.concept_mapping.get(f.concept_id)
                if mapping is None:
                    continue
                lines.append(f"  - {f.concept_id} → df[\"{mapping.column}\"]")

        lines += [
            "",
            "## Instructions",
            "Write the complete `compute_signal(df)` function. Output ONLY the Python code, no explanation.",
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
                f"Fix the following Python signal plugin. Correct ONLY syntax errors and schema issues.\n"
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
