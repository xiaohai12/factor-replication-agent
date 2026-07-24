"""No silent default data source (signal side): the source of every signal
input must come from the reviewed MethodSpec / registered catalog, never a
silent CRSP/Compustat fallback. Covers Phases A/B/C.
"""

from __future__ import annotations

import pytest

from src.infra.models.method_spec import MethodSpec
from src.steps.step2_reviewer import ReviewGate, ReviewResult
from src.steps.step3_codegen.script_generator import pick_signal_input_mode


def _spec(mapping: dict) -> MethodSpec:
    # signal_input_sources() keeps only mapping entries whose concept is a
    # formula field, so required_fields must cover the mapping keys.
    fields = list(mapping.keys()) or ["f"]
    return MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": fields, "formula": {"expression": "f"}},
        "data": {"normalized_mapping": mapping},
    })


# --- Phase A: catalog-backed source inference ----------------------------

def test_unknown_column_is_unresolved_not_compustat():
    spec = _spec({"f": "totally_unknown_col"})
    # old behavior silently returned comp_funda; now source is "" (unresolved)
    assert spec.resolved_sources().get("") == [("f", "totally_unknown_col")]
    assert spec.unresolved_source_fields() == [("f", "totally_unknown_col")]


def test_known_columns_still_resolve():
    spec = _spec({"a": "at", "r": "ret", "fa": {"source": "ibes_statsumu", "column": "meanest"}})
    groups = spec.resolved_sources()
    assert groups["comp_funda"] == [("a", "at")]
    assert groups["crsp_msf"] == [("r", "ret")]
    assert groups["ibes_statsumu"] == [("fa", "meanest")]
    assert spec.unresolved_source_fields() == []


# --- Phase C: codegen fail-loud ------------------------------------------

def test_pick_mode_raises_on_empty_mapping():
    with pytest.raises(ValueError, match="never defaults"):
        pick_signal_input_mode(_spec({}))


def test_pick_mode_raises_on_unresolved_column():
    with pytest.raises(ValueError, match="no .*registered data source"):
        pick_signal_input_mode(_spec({"f": "totally_unknown_col"}))


def test_pick_mode_source_driven():
    assert pick_signal_input_mode(_spec({"r": "ret"})) == "crsp_only"
    assert pick_signal_input_mode(_spec({"a": "at"})) == "compustat"
    assert pick_signal_input_mode(_spec({"a": "at", "r": "ret"})) == "compustat"
    assert pick_signal_input_mode(
        _spec({"fa": {"source": "ibes_statsumu", "column": "meanest"}})
    ) == "multi_source"


# --- Phase B: reviewer hard-block ----------------------------------------

def test_reviewer_blocks_unresolved_column():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    gate._check_source_mapping_resolved(_spec({"f": "totally_unknown_col"}), result)
    assert any("no registered data source" in i for i in result.issues)
    assert result.blocked_fields


def test_reviewer_blocks_unknown_source():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    spec = _spec({"f": {"source": "made_up_vendor", "column": "foo"}})
    gate._check_source_mapping_resolved(spec, result)
    assert any("no registered join" in i for i in result.issues)
    assert "data.normalized_mapping[source=made_up_vendor]" in result.blocked_fields


def test_reviewer_passes_known_sources():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    gate._check_source_mapping_resolved(_spec({"a": "at", "r": "ret"}), result)
    assert result.blocked_fields == []
    assert result.issues == []


# --- Phase F: returns universe from spec (no default CRSP panel) ----------

def test_load_data_raises_without_returns_universe():
    from src.infra.backtest_engine import BacktestExecutor
    with pytest.raises(ValueError, match="never defaults to a CRSP returns panel"):
        BacktestExecutor()._load_data({})


def test_load_data_does_not_fall_back_to_crsp_for_a_different_returns_table(tmp_path):
    """The legacy `<data_path>/local/msf.parquet` file-location shim is scoped
    to `returns_table == "crsp_msf"` only. A different (e.g. future non-CRSP)
    returns universe whose raw/ file is missing must fail loud -- never
    silently substitute the CRSP legacy file, even if one happens to exist on
    disk at the legacy path."""
    import pandas as pd
    from src.infra.backtest_engine import BacktestExecutor

    local_dir = tmp_path / "local"
    local_dir.mkdir(parents=True)
    # A real CRSP legacy file IS present on disk, but returns_table names a
    # different, unrelated universe -- it must not be used.
    pd.DataFrame({"permno": [1], "yyyymm": [200001], "ret": [0.01]}).to_parquet(
        local_dir / "msf.parquet", index=False
    )

    executor = BacktestExecutor(data_path=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="no legacy fallback"):
        executor._load_data({"returns_table": "some_other_equity_universe"})


def test_build_config_sets_returns_table_from_universe():
    from src.steps.step3_codegen.registry import build_config
    spec = _spec({"a": "at"})
    spec.returns_universe = "us_equity_crsp"
    config = build_config(spec, None)
    assert config["returns_table"] == "crsp_msf"
    assert config["returns_layout"] == "panel"


def test_build_config_defaults_returns_table_to_crsp_when_universe_unset():
    from src.steps.step3_codegen.registry import build_config
    spec = _spec({"a": "at"})  # returns_universe unset -> standardized CRSP default
    config = build_config(spec, None)
    assert config["returns_table"] == "crsp_msf"
    assert config["returns_layout"] == "panel"


def test_reviewer_warns_not_blocks_unset_returns_universe():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    gate._check_returns_universe(_spec({"a": "at"}), result)
    assert "returns_universe" not in result.blocked_fields
    assert any("defaulting to the standardized CRSP" in w for w in result.warnings)


def test_reviewer_blocks_unregistered_returns_universe():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    spec = _spec({"a": "at"})
    spec.returns_universe = "tokyo_stock_exchange"
    gate._check_returns_universe(spec, result)
    assert "returns_universe" in result.blocked_fields
    assert any("not registered" in i for i in result.issues)


def test_reviewer_passes_registered_returns_universe():
    gate = ReviewGate(data_dictionary=None)
    result = ReviewResult()
    spec = _spec({"a": "at"})
    spec.returns_universe = "us_equity_crsp"
    gate._check_returns_universe(spec, result)
    assert result.blocked_fields == []
    assert result.issues == []

