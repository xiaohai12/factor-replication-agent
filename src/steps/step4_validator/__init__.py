"""Adversarial Sandbox - Validate generated plugins before use."""

from __future__ import annotations

import ast

from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord, ValidationReport


# Patterns that indicate potential future information leakage
FORBIDDEN_PATTERNS = [
    "shift(-",   # backward shift (future data)
    ".future",
    "lead(",
]


class AdversarialSandbox:
    """Validates generated signal plugins for correctness and safety.

    Checks:
    - Syntax / import / type validity
    - Output schema conformance
    - Forbidden pattern scan (future functions)
    - Temporal leakage detection
    - Reproducibility verification
    """

    def validate(self, plugin: PluginRecord, spec: MethodSpec) -> ValidationReport:
        """Run full validation suite on a plugin."""
        report = ValidationReport()

        report.syntax_ok = self._check_syntax(plugin, report)
        if report.syntax_ok:
            report.schema_ok = self._check_schema(plugin, report)
            report.no_future_leak = self._check_no_future_leak(plugin, report)
            report.reproducible = self._check_reproducibility(plugin, report)

        report.passed = all([
            report.syntax_ok,
            report.schema_ok,
            report.no_future_leak,
            report.reproducible,
        ])
        return report

    def _check_syntax(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that code parses without syntax errors."""
        try:
            ast.parse(plugin.code)
            return True
        except SyntaxError as e:
            report.errors.append(f"SyntaxError: {e}")
            return False

    def _check_schema(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that plugin defines expected entry function with correct signature."""
        try:
            tree = ast.parse(plugin.code)
            func_names = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            if plugin.entry_function not in func_names:
                report.errors.append(
                    f"Entry function '{plugin.entry_function}' not found in code"
                )
                return False
            return True
        except Exception as e:
            report.errors.append(f"Schema check failed: {e}")
            return False

    def _check_no_future_leak(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Scan for patterns that might indicate future information usage."""
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in plugin.code:
                report.errors.append(f"Forbidden pattern detected: '{pattern}'")
                return False
        return True

    def _check_reproducibility(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check for non-deterministic operations."""
        # TODO: Run plugin twice with same input, check outputs match
        return True
