"""Tests for `backend.spec_parsing.parse_spec`/`spec_factor_id`, used by the
codegen/backtest/experiments routers.
"""

from __future__ import annotations

import json

from backend.spec_parsing import parse_spec, spec_factor_id
from src.infra.models.paper_method_spec import ResolvedMethodSpec
from tests.test_meta_coder_resolved_method_spec import _resolved_spec


def test_parses_resolved_method_spec_payload():
    resolved = _resolved_spec()
    payload = json.loads(resolved.model_dump_json())
    parsed = parse_spec(payload)
    assert isinstance(parsed, ResolvedMethodSpec)
    assert spec_factor_id(parsed) == resolved.paper.factor_id
