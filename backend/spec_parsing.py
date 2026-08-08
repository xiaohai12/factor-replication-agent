"""Shared request-body spec parsing for the codegen/backtest/experiments
routers.
"""

from __future__ import annotations

from src.infra.models.paper_method_spec import ResolvedMethodSpec


def parse_spec(raw: dict) -> ResolvedMethodSpec:
    """Parse a request body's `spec` dict into a `ResolvedMethodSpec`."""
    return ResolvedMethodSpec.model_validate(raw)


def spec_factor_id(spec: ResolvedMethodSpec) -> str:
    """Identity accessor, for logging/plan construction."""
    return spec.paper.factor_id
