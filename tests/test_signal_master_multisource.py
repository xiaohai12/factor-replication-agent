"""Tests for the declarative multi-source signal-input data loader:

- data_layer.link_to_permno() point-in-time key->permno for each source
- data_layer.assemble_signal_master_table() single- and multi-source assembly

Uses the synthetic WRDS-shaped data in data/synthetic_data/test_papers_v1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.infra.data_layer import (
    SIGNAL_SOURCES,
    assemble_signal_master_table,
    link_to_permno,
)
from src.infra.data_layer.sources import _read_raw_link_table_csv

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "synthetic_data" / "test_papers_v1"

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "crsp_msf.parquet").exists(),
    reason="run scripts/build_test_papers_synthetic_data.py first",
)


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / f"{name}.parquet")


# --- Phase 2: link_to_permno() -------------------------------------------

@pytest.mark.parametrize("source,table", [
    ("compustat_fundamental_annual", "compustat_fundamental_annual"),
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

def test_master_table_dispatches_on_resolved_method_spec():
    """`assemble_signal_master_table` sourced off
    `ImplementationResolution.concept_mapping`."""
    from tests._spec_test_helpers import minimal_resolved_spec

    spec = minimal_resolved_spec(concept_source="compustat_fundamental_annual", concept_column="at")
    m = assemble_signal_master_table(spec, DATA_DIR)
    assert {"permno", "time_avail_m", "at"}.issubset(m.columns)
    assert len(m) > 0


# --- registry link-table sanity -------------------------------------------
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
    out = link_to_permno(df, "compustat_fundamental_annual", {"ccm": ccm}, date_col="datadate")

    assert list(out["gvkey"]) == ["0002"]          # gvkey 0001 (bad linktype) dropped
    assert int(out.iloc[0]["permno"]) == 202        # primary link wins, not smallest permno
    assert "linktype" not in out.columns and "linkprim" not in out.columns


def test_raw_ccm_csv_preserves_zero_padded_gvkey_for_linking(tmp_path):
    """CSV inference must not turn CCM's ``001000`` identifier into ``1000``."""
    path = tmp_path / "CRSP_COMPUSTAT_LINK.csv"
    path.write_text(
        "gvkey,lpermno,linkdt,linkenddt,linktype,linkprim\n"
        "001000,12345,1980-01-01,E,LC,P\n"
    )

    ccm = _read_raw_link_table_csv(path, "ccm")
    assert ccm.loc[0, "gvkey"] == "001000"

    source = pd.DataFrame([{"gvkey": "001000", "datadate": "1981-12-31", "at": 1.0}])
    linked = link_to_permno(source, "compustat_fundamental_annual", {"ccm": ccm})
    assert linked.loc[0, "permno"] == 12345


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
# (crsp_msf/crsp_msenames/crsp_msedelist), which the generated script's
# multi_source template no longer reads (it now calls
# `build_crsp_monthly_panel_ciz`, expecting a real WRDS CIZ export). See
# docs/decision-log.md (2026-07-31 entry).
