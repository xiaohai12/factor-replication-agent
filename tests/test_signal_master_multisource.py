"""Tests for the declarative multi-source signal-input data loader (plan.md
data-loader Phases 1-4):

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
    ("optionm_vsurf", "optionm_vsurf"),
])
def test_link_to_permno_no_row_explosion(source, table):
    r = _read
    links = {
        "ccm": r("ccm_lnkhist"),
        "ibes_crsp_link": r("ibes_crsp_link"),
        "optionm_crsp_link": r("optionm_crsp_link"),
    }
    df = r(table)
    out = link_to_permno(df, source, links)
    assert "permno" in out.columns
    assert out["permno"].notna().all()
    assert len(out) <= len(df)          # point-in-time filter, never explodes


def test_link_to_permno_noop_for_permno_keyed_source():
    df = pd.DataFrame({"permno": [1, 2], "rdate": pd.to_datetime(["2000-03-31", "2000-06-30"])})
    out = link_to_permno(df, "tr_13f", {})
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


def test_generated_multi_source_script_runs(tmp_path):
    """Generate a multi_source backtest script for an IBES-based signal and
    actually execute it on the synthetic data (mirrors how the pipeline runs
    generated scripts: subprocess + repo root on PYTHONPATH)."""
    import subprocess
    import sys

    from src.steps.step3_codegen.script_generator import generate_backtest_script

    spec = MethodSpec.model_validate({
        "factor_id": "ibes_meanest_demo", "factor_name": "IBES Mean EPS Demo",
        "signal": {"required_fields": ["analyst_forecast"], "formula": {"expression": "analyst_forecast"}},
        "data": {"normalized_mapping": {
            "analyst_forecast": {"source": "ibes_statsumu", "column": "meanest"},
        }},
    })
    plugin_code = (
        "def compute_signal(df):\n"
        "    df = df.copy()\n"
        "    df['signal'] = df['meanest']\n"
        "    df['yyyymm'] = df['time_avail_m']\n"
        "    return df[['permno', 'yyyymm', 'signal']].dropna()\n"
    )
    out_csv = tmp_path / "out.csv"
    script = generate_backtest_script(
        spec, plugin_code,
        signal_data_dir=str(DATA_DIR),
        output_path=str(out_csv),
    )
    assert 'SIGNAL_INPUT_MODE = "multi_source"' in script
    script_path = tmp_path / "run.py"
    script_path.write_text(script)

    repo_root = Path(__file__).resolve().parents[1]
    env = {"PATH": __import__("os").environ.get("PATH", ""),
           "PYTHONPATH": str(repo_root)}
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, env=env, cwd=str(repo_root),
    )
    assert proc.returncode == 0, f"script failed:\n{proc.stdout}\n{proc.stderr}"
    assert out_csv.exists()

