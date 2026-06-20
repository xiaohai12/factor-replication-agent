"""Controlled Meta-Coder - Generate factor signal plugins from approved MethodSpec.

Uses OSAP Predictors/*.py as few-shot examples to guide LLM code generation.
Generated plugins follow the C&Z unified pattern:
- Read from intermediate parquet (SignalMasterTable keyed on [permno, time_avail_m])
- Only do formula computation (no data download, no lag handling, no portfolio logic)
- Output: [permno, yyyymm, SignalName]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.models.method_spec import MethodSpec
from src.models.plugin import PluginRecord


# Expected plugin output schema
PLUGIN_OUTPUT_COLS = ["permno", "yyyymm", "signal"]


class MetaCoder:
    """Generates factor-specific signal construction plugins.

    The Meta-Coder is ONLY allowed to generate signal construction code.
    It CANNOT:
    - Compute portfolio returns
    - Decide breakpoints or weighting
    - Construct long-short portfolios
    - Modify universe filters
    - Change missing-value policy
    - Alter lag assumptions (lag is in Data Layer via time_avail_m)

    Uses C&Z Predictors/*.py as few-shot examples to enforce the
    unified code pattern (see docs/cz-reference.md Section 2).
    """

    def __init__(self, llm_client=None, reference_code_path: Optional[str] = None):
        self.llm_client = llm_client
        self.reference_code_path = Path(reference_code_path) if reference_code_path else None

    def generate_plugin(self, spec: MethodSpec) -> PluginRecord:
        """Generate a signal construction plugin from an approved MethodSpec.

        The generated plugin must:
        1. Read from SignalMasterTable (keyed on [permno, time_avail_m])
        2. Map raw fields to semantic variables
        3. Construct the raw signal (formula only)
        4. Output: DataFrame with columns [permno, yyyymm, signal]
        """
        review_status = getattr(spec.review_status, "value", spec.review_status)
        if review_status != "approved" or not spec.codegen_ready:
            raise ValueError("Cannot generate plugin from unapproved MethodSpec")
        # TODO: Build prompt with MethodSpec + few-shot examples, call LLM
        raise NotImplementedError

    def repair_plugin(self, plugin: PluginRecord, errors: list[str]) -> PluginRecord:
        """Attempt bounded repair of a failed plugin (technical errors only).

        Empirical assumption changes must go back through Review Gate.
        Max 3 repair attempts enforced by Pipeline.
        """
        # TODO: Implement bounded repair with error context
        raise NotImplementedError

    def load_few_shot_examples(self, n: int = 3) -> list[str]:
        """Load N reference predictor files as few-shot examples.

        Selects representative examples (e.g. BM.py, Accruals.py, Mom12m.py)
        to demonstrate the expected code pattern.
        """
        if not self.reference_code_path:
            return []

        # Default example files (simple, well-known factors)
        example_files = ["BM.py", "Accruals.py", "Mom12m.py"]
        examples = []
        for fname in example_files[:n]:
            path = self.reference_code_path / fname
            if path.exists():
                examples.append(path.read_text())
        return examples
