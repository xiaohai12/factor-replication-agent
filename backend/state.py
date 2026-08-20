"""Shared backend state: one `Pipeline` instance for the whole process, plus
helpers to build per-request LLM-backed step objects (provider/model choice
is a per-request concern here, matching how app.py's sidebar dropdown works
today -- Pipeline itself is constructed once with llm_client=None and each
step that needs an LLM gets a freshly-built one for the request).
"""

from __future__ import annotations

import os
from pathlib import Path

from src.infra.data_layer import SnapshotMetadata
from src.infra.llm import create_llm_client
from src.pipeline import Pipeline
from src.steps.step1_extractor.extractor import MethodSpecExtractor
from src.steps.step3_codegen import MetaCoder

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
# Overridable so ad-hoc/manual test runs (e.g. FACTOR_AGENT_RUNS_DIR=.runs_scratch)
# can write session/methodspec/evidence/backtest_script artifacts somewhere
# other than the real runs/ dir, keeping them easy to bulk-delete without
# touching real work. A relative override is resolved against REPO_ROOT (not
# the process cwd, which may differ depending on how uvicorn/streamlit was
# launched). Defaults to the same runs/ as before when unset.
_runs_dir_override = os.environ.get("FACTOR_AGENT_RUNS_DIR")
RUNS_DIR = (REPO_ROOT / _runs_dir_override) if _runs_dir_override else REPO_ROOT / "runs"

PAPER_TEXT_CACHE_DIR = DATA_DIR / "paper_text_cache"
METHODSPEC_ROOT = RUNS_DIR / "method_specs"

# Paper-first (MethodSpec/MethodReview/ImplementationResolution/
# ResolvedMethodSpec) artifact dirs -- the v1 MethodSpec pipeline that used
# to own these names is gone, so this is now the only consumer of them.
UNREVIEWED_DIR = METHODSPEC_ROOT / "unreviewed"
REVIEWED_DIR = METHODSPEC_ROOT / "reviewed"
RESOLUTIONS_DIR = METHODSPEC_ROOT / "resolutions"
RESOLVED_DIR = METHODSPEC_ROOT / "resolved"

for _dir in (
    PAPER_TEXT_CACHE_DIR,
    UNREVIEWED_DIR,
    REVIEWED_DIR,
    RESOLUTIONS_DIR,
    RESOLVED_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)

pipeline = Pipeline(
    data_path=str(DATA_DIR),
    evidence_path=str(RUNS_DIR / "evidence"),
    scripts_path=str(RUNS_DIR / "backtest_scripts"),
)

SYNTHETIC_SNAPSHOT_ID = "synthetic_demo_v1"
_SYNTHETIC_SNAPSHOT_DIR = DATA_DIR / "synthetic_data" / "mvp_v1"

LOCAL_SNAPSHOT_ID = "local_data_v1"
_LOCAL_DATA_DIR = DATA_DIR / "local"


def ensure_synthetic_snapshot() -> None:
    """Register the bundled synthetic demo dataset as a snapshot, generating
    it on the fly if needed (mirrors app.py's `_ensure_synthetic_data`)."""
    if pipeline.data_layer.snapshots.get_snapshot(SYNTHETIC_SNAPSHOT_ID) is not None:
        return
    # The declarative signal-master loader reads
    # `compustat_fundamental_annual.parquet` + `ccm_lnkhist.parquet` (CCM keyed
    # on `lpermno`). Regenerate if that file is missing (e.g. a stale older
    # snapshot dir).
    if not (_SYNTHETIC_SNAPSHOT_DIR / "compustat_fundamental_annual.parquet").exists():
        from tests.synthetic_data.asset_growth_synthetic_data import (
            build_ccm_link,
            build_compustat_funda,
            build_crsp_msf,
        )

        _SYNTHETIC_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        build_crsp_msf().to_parquet(_SYNTHETIC_SNAPSHOT_DIR / "crsp_msf.parquet", index=False)
        build_compustat_funda().to_parquet(
            _SYNTHETIC_SNAPSHOT_DIR / "compustat_fundamental_annual.parquet", index=False
        )
        build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
            _SYNTHETIC_SNAPSHOT_DIR / "ccm_lnkhist.parquet", index=False
        )
    pipeline.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=SYNTHETIC_SNAPSHOT_ID,
            pull_date="synthetic",
            crsp_end_date="synthetic",
            compustat_end_date="synthetic",
            storage_path=str(_SYNTHETIC_SNAPSHOT_DIR),
        )
    )


def ensure_local_snapshot() -> None:
    """Register data/local/ as a snapshot when it already has the 3 required
    tables on disk (real WRDS-derived data some setups place there) -- never
    auto-generated, unlike the synthetic snapshot."""
    if pipeline.data_layer.snapshots.get_snapshot(LOCAL_SNAPSHOT_ID) is not None:
        return
    required = ("crsp_msf.parquet", "compustat_fundamental_annual.parquet", "ccm_lnkhist.parquet")
    if not all((_LOCAL_DATA_DIR / name).exists() for name in required):
        return
    pipeline.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=LOCAL_SNAPSHOT_ID,
            pull_date="local",
            crsp_end_date="local",
            compustat_end_date="local",
            storage_path=str(_LOCAL_DATA_DIR),
        )
    )


VALIDATION_SAMPLE_SNAPSHOT_ID = "validation_sample_v1"
_VALIDATION_SAMPLE_DIR = DATA_DIR / "local" / "validation_sample"


def ensure_validation_sample_snapshot() -> None:
    """Register data/local/validation_sample/ as a snapshot -- a small (~50
    real, long-history companies), ID-aligned real-data sample built by
    scripts/build_real_wrds_samples.py, materialized as the SAME 3
    pre-flattened parquet tables `ensure_local_snapshot` requires (no nested
    `local/` raw-CSV fallback folder needed). Intended for Step4's execution
    smoke test / RepairLoop: fast (tens of thousands of rows, not the full
    real data/local export) but still genuinely real data, not synthetic.
    Same never-auto-generated gating as `ensure_local_snapshot`."""
    if pipeline.data_layer.snapshots.get_snapshot(VALIDATION_SAMPLE_SNAPSHOT_ID) is not None:
        return
    required = ("crsp_msf.parquet", "compustat_fundamental_annual.parquet", "ccm_lnkhist.parquet")
    if not all((_VALIDATION_SAMPLE_DIR / name).exists() for name in required):
        return
    pipeline.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=VALIDATION_SAMPLE_SNAPSHOT_ID,
            pull_date="validation_sample",
            crsp_end_date="validation_sample",
            compustat_end_date="validation_sample",
            storage_path=str(_VALIDATION_SAMPLE_DIR),
        )
    )


REAL_WRDS_SNAPSHOT_ID = "real_wrds_local_v1"

# The DataSource registry's raw-file fallback (src/infra/data_layer/sources.py)
# reads real WRDS-export CSVs directly out of a `local/` subfolder -- no
# parquet conversion needed. `storage_path` must be the PARENT of that
# `local/` folder (i.e. `data`, matching scripts/run_real_asset_growth_
# experiment.py's convention), never `data/local` itself.
_REAL_WRDS_REQUIRED_RAW_FILES = (
    "CRSP_STOCK_MONTH.csv",
    "COMPUSTAT_FUNDAMENTALS_ANNUAL.csv",
    "CRSP_COMPUSTAT_LINK.csv",
)


def ensure_real_wrds_snapshot() -> None:
    """Register data/ (parent of data/local/'s raw WRDS CSV exports) as a
    snapshot, so the frontend's SnapshotPicker can select real data straight
    off disk without any manual parquet-conversion step. Only registers when
    the raw CSVs are actually present (developer-local, gitignored) --
    never auto-generated, same gating pattern as `ensure_local_snapshot`."""
    if pipeline.data_layer.snapshots.get_snapshot(REAL_WRDS_SNAPSHOT_ID) is not None:
        return
    if not all((_LOCAL_DATA_DIR / name).exists() for name in _REAL_WRDS_REQUIRED_RAW_FILES):
        return
    pipeline.data_layer.snapshots.register_snapshot(
        SnapshotMetadata(
            snapshot_id=REAL_WRDS_SNAPSHOT_ID,
            pull_date="local_raw_wrds",
            crsp_end_date="local_raw_wrds",
            compustat_end_date="local_raw_wrds",
            storage_path=str(DATA_DIR),
        )
    )


def build_llm_client(provider: str, model: str | None):
    return create_llm_client(provider=provider, model=model)


def build_meta_coder(llm_client) -> MetaCoder:
    return MetaCoder(llm_client=llm_client)


def build_extractor(llm_client) -> MethodSpecExtractor:
    return MethodSpecExtractor(llm_client=llm_client)
