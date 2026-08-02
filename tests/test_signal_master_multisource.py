"""Tests for the declarative multi-source signal-input data loader:

- MethodSpec.resolved_sources() grouping (richer + legacy mapping forms)
- data_layer.link_to_permno() point-in-time key->permno for each source
- data_layer.assemble_signal_master_table() single- and multi-source assembly
- ReviewGate blocks a spec whose mapping references an unregistered source

Uses the synthetic WRDS-shaped data in data/synthetic_data/test_papers_v1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.infra.data_layer import (
    SIGNAL_SOURCES,
    assemble_signal_master_table,
    link_to_permno,
)
from src.infra.models.method_spec import MethodSpec
from src.steps.step2_reviewer import ReviewGate

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "synthetic_data" / "test_papers_v1"
ACCRUALS = (
    REPO_ROOT / "tests" / "fixtures" / "method_specs"
    / "sloan_1996_accruals.resolved.methodspec.json"
)

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "crsp_msf.parquet").exists(),
    reason="run scripts/build_test_papers_synthetic_data.py first",
)


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


# --- Phase 1: resolved_sources() -----------------------------------------

def test_resolved_sources_legacy_plain_string():
    spec = MethodSpec.model_validate(json.loads(ACCRUALS.read_text()))
    groups = spec.resolved_sources()
    # accounting fields -> comp_funda; return/market/exchange -> crsp_msf
    assert set(dict(groups["comp_funda"]).values()) >= {"act", "lct", "che", "dlc", "dp", "at"}
    assert set(dict(groups["crsp_msf"]).values()) >= {"ret", "me"}


def test_resolved_sources_richer_form():
    spec = MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": ["fa"], "formula": {"expression": "fa"}},
        "data": {"normalized_mapping": {
            "fa": {"source": "ibes_statsumu", "column": "meanest"},
        }},
    })
    assert spec.resolved_sources() == {"ibes_statsumu": [("fa", "meanest")]}


# --- Phase 2: link_to_permno() -------------------------------------------

@pytest.mark.parametrize("source,table", [
    ("comp_funda", "comp_funda"),
    ("ibes_statsumu", "ibes_statsumu"),
])
def test_link_to_permno_no_row_explosion(source, table):
    r = _read
    links = {
        "ccm": r("ccm_lnkhist"),
        "ibes_crsp_link": r("ibes_crsp_link"),
    }
    df = r(table)
    out = link_to_permno(df, source, links)
    assert "permno" in out.columns
    assert out["permno"].notna().all()
    assert len(out) <= len(df)          # point-in-time filter, never explodes


def test_link_to_permno_noop_for_permno_keyed_source():
    # crsp_msf is registered with link=None (already permno-keyed) --
    # link_to_permno must pass such a source's rows through unchanged.
    df = pd.DataFrame({"permno": [1, 2], "yyyymm": [200003, 200006]})
    out = link_to_permno(df, "crsp_msf", {})
    assert out.equals(df)               # link=None -> unchanged


# --- Phase 3: assemble_signal_master_table() -----------------------------

def test_master_table_single_source_accruals():
    spec = MethodSpec.model_validate(json.loads(ACCRUALS.read_text()))
    m = assemble_signal_master_table(spec, DATA_DIR)
    assert {"permno", "time_avail_m"}.issubset(m.columns)
    # all six accounting formula columns present; CRSP engine-side fields excluded
    assert {"act", "lct", "che", "dlc", "dp", "at"}.issubset(m.columns)
    assert "me" not in m.columns and "ret" not in m.columns
    assert len(m) > 0


def test_master_table_multi_source_merges_on_permno_time():
    spec = MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": ["total_assets", "analyst_forecast"],
                   "formula": {"expression": "total_assets"}},
        "data": {"normalized_mapping": {
            "total_assets": {"source": "comp_funda", "column": "at"},
            "analyst_forecast": {"source": "ibes_statsumu", "column": "meanest"},
        }},
    })
    m = assemble_signal_master_table(spec, DATA_DIR)
    assert {"permno", "time_avail_m", "at", "meanest"}.issubset(m.columns)
    assert int(m["at"].notna().sum()) > 0
    assert int(m["meanest"].notna().sum()) > 0


def test_master_table_reads_only_needed_columns():
    # a spec needing only `at` must not pull the whole funda schema
    spec = MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": ["ta"], "formula": {"expression": "ta"}},
        "data": {"normalized_mapping": {"ta": {"source": "comp_funda", "column": "at"}}},
    })
    m = assemble_signal_master_table(spec, DATA_DIR)
    assert set(m.columns) == {"permno", "time_avail_m", "at"}


# --- Phase 4: ReviewGate unknown-source block ----------------------------

def test_review_blocks_unknown_source():
    spec = MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": ["weird"], "formula": {"expression": "weird"}},
        "data": {"normalized_mapping": {
            "weird": {"source": "bloomberg_terminal", "column": "px_last"},
        }},
    })
    result = ReviewGate().review(spec)
    assert any("bloomberg_terminal" in i for i in result.issues)
    assert result.disposition == "blocked"


def test_review_allows_known_sources():
    spec = MethodSpec.model_validate(json.loads(ACCRUALS.read_text()))
    result = ReviewGate().review(spec)
    # accruals maps only to comp_funda / crsp_msf, both registered
    assert not any("SIGNAL_SOURCES" in i for i in result.issues)


def test_all_registry_link_tables_are_known():
    # every SIGNAL_SOURCES link references a table the loader can load
    from src.infra.data_layer import LINK_TABLES
    for src in SIGNAL_SOURCES.values():
        if src["link"] is not None:
            assert src["link"] in LINK_TABLES


# --- Regression tests: 2026-07-25 data-loader fixes ----------------------

def test_link_to_permno_drops_bad_linktype_and_prefers_primary():
    # gvkey 1: only a non-researched linktype ("LX") is offered -> must be
    # dropped entirely (the link-table registry enforces the LC/LU-only rule).
    # gvkey 2: two valid, overlapping candidate links (linkprim 'C' and 'P')
    # -> the primary ('P', permno 202) must win, not the smaller permno (201).
    ccm = pd.DataFrame([
        {"gvkey": "0001", "lpermno": 101, "linktype": "LX", "linkprim": "P",
         "linkdt": "2000-01-01", "linkenddt": None},
        {"gvkey": "0002", "lpermno": 201, "linktype": "LC", "linkprim": "C",
         "linkdt": "2000-01-01", "linkenddt": None},
        {"gvkey": "0002", "lpermno": 202, "linktype": "LU", "linkprim": "P",
         "linkdt": "2000-01-01", "linkenddt": None},
    ])
    df = pd.DataFrame([
        {"gvkey": "0001", "datadate": "2010-06-30", "at": 100.0},
        {"gvkey": "0002", "datadate": "2010-06-30", "at": 200.0},
    ])
    out = link_to_permno(df, "comp_funda", {"ccm": ccm}, date_col="datadate")

    assert list(out["gvkey"]) == ["0002"]          # gvkey 0001 (bad linktype) dropped
    assert int(out.iloc[0]["permno"]) == 202        # primary link wins, not smallest permno
    assert "linktype" not in out.columns and "linkprim" not in out.columns


def test_load_source_frame_raises_for_source_without_date_column(monkeypatch):
    # Any source registered with observation_date=None must fail loud, not
    # silently return zero rows (regression for the patents_nber bug fixed
    # 2026-07-25 -- patents_nber itself was removed from the registry
    # 2026-07-31 since no NBER patents data exists in this project, so a
    # temporary fake SignalSource is registered here to keep exercising this
    # behavior generically; see docs/decision-log.md 2026-07-31 entry).
    from src.infra.data_layer import _load_source_frame
    from src.infra.data_layer import sources as S

    fake_spec = S.SourceSpec(
        name="_test_no_date_source", role="signal", raw_file=None,
        physical_columns={"gvkey", "npats"}, concept_columns={"npats": "npats"},
        source_key="gvkey", observation_date=None, lag=0,
        crsp_link=S.CrspLinkSpec(native_key="gvkey", link_table="ccm"),
    )
    S.register(S.SignalSource(fake_spec))
    try:
        ccm = pd.DataFrame([
            {"gvkey": "0001", "lpermno": 101, "linktype": "LC", "linkprim": "P",
             "linkdt": "2000-01-01", "linkenddt": None},
        ])
        fake = pd.DataFrame([{"gvkey": "0001", "npats": 5}])
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fake.to_parquet(Path(d) / "_test_no_date_source.parquet")
            with pytest.raises(ValueError, match="no usable observation-date column"):
                _load_source_frame(Path(d), "_test_no_date_source", ["npats"], 6, {"ccm": ccm})
    finally:
        S._REGISTRY.pop("_test_no_date_source", None)


# NOTE (2026-07-31): `test_apply_pit_attrs_fallback_for_coverage_gap` was
# removed here -- it directly exercised `assemble_panel()`/the legacy 3-table
# crsp_msf/crsp_msenames/crsp_msedelist assembler, which was deleted in favor
# of standardizing on the real WRDS CIZ format (`build_crsp_monthly_panel_ciz`,
# which needs no point-in-time attrs-window join at all since every CIZ row
# is already point-in-time). See docs/decision-log.md (2026-07-31 entry).


# --- codegen wiring: mode picker + runnable multi_source script -----------

def test_pick_mode_binary_specs_unchanged():
    from src.steps.step3_codegen.script_generator import pick_signal_input_mode
    accr = MethodSpec.model_validate(json.loads(ACCRUALS.read_text()))
    assert pick_signal_input_mode(accr) == "compustat"


def test_pick_mode_multi_source_for_ibes():
    from src.steps.step3_codegen.script_generator import pick_signal_input_mode
    spec = MethodSpec.model_validate({
        "factor_id": "x", "factor_name": "X",
        "signal": {"required_fields": ["af"], "formula": {"expression": "af"}},
        "data": {"normalized_mapping": {"af": {"source": "ibes_statsumu", "column": "meanest"}}},
    })
    assert pick_signal_input_mode(spec) == "multi_source"


# NOTE (2026-07-31): `test_generated_multi_source_script_runs` was removed --
# it generated a multi_source script and executed it against
# data/synthetic_data/test_papers_v1's legacy 3-table CRSP synthetic data
# (crsp_msf/crsp_msenames/crsp_msedelist), which the generated script's
# multi_source template no longer reads (it now calls
# `build_crsp_monthly_panel_ciz`, expecting a real WRDS CIZ export). See
# docs/decision-log.md (2026-07-31 entry).

