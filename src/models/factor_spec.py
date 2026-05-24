"""FactorSpec - High-level factor metadata."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FactorSpec(BaseModel):
    """High-level factor metadata linking paper, method spec, and plugins."""

    factor_id: str = Field(..., description="Unique factor identifier")
    factor_name: str = Field(..., description="Human-readable factor name")
    paper_title: str = Field(default="")
    paper_authors: list[str] = Field(default_factory=list)
    paper_year: int = Field(default=0)
    category: str = Field(default="", description="Factor category (value/momentum/etc)")
    cz_id: Optional[str] = Field(default=None, description="Chen-Zimmermann identifier")
    osap_code_path: Optional[str] = Field(
        default=None, description="Path to OSAP reference code"
    )
    method_spec_ids: list[str] = Field(
        default_factory=list, description="Associated MethodSpec versions"
    )
    plugin_ids: list[str] = Field(
        default_factory=list, description="Associated plugin IDs"
    )
