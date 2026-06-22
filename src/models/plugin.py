"""PluginRecord - Metadata for a generated and validated signal plugin."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ValidationReport(BaseModel):
    """Results from Adversarial Sandbox validation."""

    passed: bool = False
    syntax_ok: bool = False
    schema_ok: bool = False
    no_future_leak: bool = False
    reproducible: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PluginRecord(BaseModel):
    """Registry record for a generated factor signal plugin."""

    plugin_id: str = Field(..., description="Unique plugin identifier")
    factor_id: str = Field(..., description="Associated factor ID")
    method_spec_version: int = Field(default=1)
    method_spec_hash: str = Field(default="")

    # Code
    code: str = Field(..., description="Generated plugin source code")
    code_hash: str = Field(default="")
    entry_function: str = Field(default="compute_signal")

    # Hook functions generated for non-standard backtest steps
    # Maps step_name → function_name in the plugin code
    # e.g. {"compute_breakpoints": "compute_breakpoints_hook"}
    hooks: dict[str, str] = Field(default_factory=dict)

    # Validation
    validation_status: str = Field(
        default="pending", description="pending|passed|failed|needs_repair"
    )
    validation_report: Optional[ValidationReport] = None
    repair_trace: list[str] = Field(
        default_factory=list, description="History of repair attempts"
    )
