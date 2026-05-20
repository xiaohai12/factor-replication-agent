"""Controlled Meta-Coder - Generate factor signal plugins from approved MethodSpec."""

from __future__ import annotations

from src.models.method_spec import MethodSpec
from src.models.plugin import PluginRecord


class MetaCoder:
    """Generates factor-specific signal construction plugins.

    The Meta-Coder is ONLY allowed to generate signal construction code.
    It CANNOT:
    - Compute portfolio returns
    - Decide breakpoints or weighting
    - Construct long-short portfolios
    - Modify universe filters
    - Change missing-value policy
    - Alter lag assumptions
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def generate_plugin(self, spec: MethodSpec) -> PluginRecord:
        """Generate a signal construction plugin from an approved MethodSpec.

        The generated plugin must:
        1. Declare required fields
        2. Map raw fields to semantic variables
        3. Construct the raw signal
        4. Output a formation-level signal table (permno × date → signal)
        """
        if spec.review_status != "approved":
            raise ValueError("Cannot generate plugin from unapproved MethodSpec")
        # TODO: Implement LLM-based code generation
        raise NotImplementedError

    def repair_plugin(self, plugin: PluginRecord, errors: list[str]) -> PluginRecord:
        """Attempt bounded repair of a failed plugin (technical errors only).

        Empirical assumption changes must go back through Review Gate.
        """
        # TODO: Implement bounded repair
        raise NotImplementedError
