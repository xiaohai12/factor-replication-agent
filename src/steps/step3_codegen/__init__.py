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

from src.infra.models.method_spec import MethodSpec
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

    def generate_plugin(self, spec: MethodSpec) -> PluginRecord:
        """Generate a signal construction plugin from an approved MethodSpec.

        Column mapping is read from spec.data.normalized_mapping (populated by
        DataDictionary.normalize_fields() during resolution).
        Implementation decisions are read from resolved MethodSpec fields.

        Args:
            spec: Approved MethodSpec (codegen_ready=True, normalized_mapping populated)
        """
        review_status = getattr(spec.review_status, "value", spec.review_status)
        if review_status != "approved" or not spec.codegen_ready:
            raise ValueError("Cannot generate plugin from unapproved MethodSpec")
        if not self.llm_client:
            raise RuntimeError("llm_client required for MetaCoder.generate_plugin()")

        user_prompt = self._build_prompt(spec)

        from src.infra.llm import extract_usage

        # Generate compute_signal() — the pure formula function. The engine is
        # fully standardized (no hook code): all portfolio-construction choices
        # are selected from a fixed menu by build_config, so the LLM only
        # produces the signal formula.
        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": METACODER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        code = _strip_code_fences(response.choices[0].message.content or "")
        token_usage = extract_usage(response)

        spec_hash = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:16]
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]

        record = PluginRecord(
            plugin_id=f"{spec.factor_id}_v{spec.version}",
            factor_id=spec.factor_id,
            method_spec_version=spec.version,
            method_spec_hash=spec_hash,
            code=code,
            code_hash=code_hash,
        )
        record.__dict__["_token_usage"] = token_usage
        return record

    def _build_prompt(self, spec: MethodSpec) -> str:
        """Build the code generation prompt from the MethodSpec."""
        formula = spec.signal.formula
        if hasattr(formula, "expression"):
            formula_str = formula.expression
            paper_formula = getattr(formula, "paper_expression", "")
        else:
            formula_str = str(formula)
            paper_formula = ""

        timing = spec.signal.timing
        lag = getattr(timing, "accounting_lag", None)
        formation = getattr(timing, "formation_month", None)
        rebalance = getattr(timing, "rebalance_frequency", None)
        if hasattr(rebalance, "value"):
            rebalance = rebalance.value

        missing = spec.signal.missing_policy
        missing_action = getattr(missing, "action", None)
        if hasattr(missing_action, "value"):
            missing_action = missing_action.value

        lines = [
            f"Generate a Python signal plugin for factor: {spec.factor_name}",
            f"Factor ID: {spec.factor_id}",
            "",
            "## Signal Formula",
            f"Python expression: {formula_str}",
        ]
        if paper_formula:
            lines.append(f"Paper notation:    {paper_formula}")

        data_fields = spec.data.required_fields or []
        if data_fields:
            lines += ["", "## Data Fields"]
            for f in data_fields:
                lines.append(f"  - {f.field}: {f.concept} (source: {f.source_detail})")

        lines += ["", "## Timing"]
        if formation:
            lines.append(f"  - Portfolio formation: end of month {formation}")
        if rebalance:
            lines.append(f"  - Rebalance frequency: {rebalance}")
        if lag is not None:
            lines.append(
                f"  - Accounting lag: {lag} months (already applied upstream — do NOT re-apply)"
            )

        if missing_action and missing_action not in ("unspecified", None):
            lines += ["", f"## Missing Data\n  - Action: {missing_action}"]
            threshold = getattr(missing, "threshold", None)
            if threshold:
                lines.append(f"  - Threshold: {threshold}")
            for ev in getattr(missing, "evidence", []):
                quote = ev.quote if hasattr(ev, "quote") else ev.get("quote", "")
                if quote:
                    lines.append(f"  - Paper evidence: \"{quote}\"")
                    break

        col_map = spec.data.normalized_mapping or {}
        if col_map:
            lines += ["", "## Column Mapping (paper field → physical DataFrame column)"]
            for paper_field, col_name in col_map.items():
                lines.append(f"  - {paper_field} → df[\"{col_name}\"]")

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
            method_spec_version=plugin.method_spec_version,
            method_spec_hash=plugin.method_spec_hash,
            code=new_code,
            code_hash=new_hash,
            repair_trace=plugin.repair_trace + [f"Repair: {'; '.join(errors[:2])}"],
        )
