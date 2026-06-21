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

from src.models.method_spec import MethodSpec
from src.models.plugin import PluginRecord


PLUGIN_OUTPUT_COLS = ["permno", "yyyymm", "signal"]

METACODER_SYSTEM_PROMPT = """You are a financial signal plugin generator for a factor replication pipeline.

Your task is to generate Python code that computes a raw factor signal from an intermediate data table.

## Plugin contract

Every plugin must define exactly one function:

```python
import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    ...
    return result[["permno", "yyyymm", "signal"]]
```

## Input table schema
- Columns: permno (int), time_avail_m (int, YYYYMM), plus accounting/market data columns
- time_avail_m already reflects the accounting lag — do NOT add additional lag offsets
- Compustat columns use standard mnemonics: at, sale, ceq, dltt, act, lct, dp, ib, etc.
- CRSP columns: ret, shrout, prc, exchcd, shrcd, siccd, etc.

## Hard rules
1. Compute ONLY the signal formula — no portfolio construction, no breakpoints, no weighting
2. NEVER use shift(-N), .future, or lead() — these introduce look-ahead bias
3. NEVER make network calls or read files
4. Rename time_avail_m → yyyymm in output
5. Return exactly the columns ["permno", "yyyymm", "signal"]
6. Drop rows where signal is NaN or infinite before returning
7. Output ONLY Python code — no prose, no markdown fences

## Example (book-to-market ratio)

import pandas as pd

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mktcap"] = df["shrout"] * df["prc"].abs() / 1000
    df["signal"] = df["ceq"] / df["mktcap"]
    df = df[df["signal"].notna() & df["ceq"].notna() & (df["ceq"] > 0)]
    return df[["permno", "time_avail_m", "signal"]].rename(columns={"time_avail_m": "yyyymm"})
"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:python)?\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


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

        The generated plugin must:
        1. Accept an intermediate data DataFrame (keyed on [permno, time_avail_m])
        2. Map raw fields to semantic variables
        3. Construct the raw signal (formula only)
        4. Output: DataFrame with columns [permno, yyyymm, signal]
        """
        review_status = getattr(spec.review_status, "value", spec.review_status)
        if review_status != "approved" or not spec.codegen_ready:
            raise ValueError("Cannot generate plugin from unapproved MethodSpec")
        if not self.llm_client:
            raise RuntimeError("llm_client required for MetaCoder.generate_plugin()")

        user_prompt = self._build_prompt(spec)

        from src.llm import extract_usage
        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": METACODER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        raw_code = response.choices[0].message.content or ""
        code = _strip_code_fences(raw_code)

        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        spec_hash = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:16]
        token_usage = extract_usage(response)

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
