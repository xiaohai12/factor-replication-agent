"""Shared backend state: one `Pipeline` instance for the whole process, plus
helpers to build per-request LLM-backed step objects (provider/model choice
is a per-request concern here, matching how app.py's sidebar dropdown works
today -- Pipeline itself is constructed once with llm_client=None and each
step that needs an LLM gets a freshly-built one for the request).
"""

from __future__ import annotations

from pathlib import Path

from src.infra.data_layer import SnapshotMetadata
from src.infra.llm import create_llm_client
from src.pipeline import Pipeline
from src.steps.step1_extractor import SemanticExtractor
from src.steps.step2_reviewer import ReviewGate
from src.steps.step3_codegen import MetaCoder

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RUNS_DIR = REPO_ROOT / "runs"

PAPER_TEXT_CACHE_DIR = DATA_DIR / "paper_text_cache"
METHODSPEC_ROOT = RUNS_DIR / "method_specs"
UNREVIEWED_DIR = METHODSPEC_ROOT / "unreviewed"
REVIEWED_DIR = METHODSPEC_ROOT / "reviewed"
RESOLUTIONS_DIR = METHODSPEC_ROOT / "resolutions"
RESOLVED_DIR = METHODSPEC_ROOT / "resolved"

for _dir in (PAPER_TEXT_CACHE_DIR, UNREVIEWED_DIR, REVIEWED_DIR, RESOLUTIONS_DIR, RESOLVED_DIR):
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
    # The declarative signal-master loader reads `comp_funda.parquet` +
    # `ccm_lnkhist.parquet` (CCM keyed on `lpermno`). Regenerate if that file is
    # missing (e.g. a stale older snapshot dir).
    if not (_SYNTHETIC_SNAPSHOT_DIR / "comp_funda.parquet").exists():
        from tests.synthetic_data.asset_growth_synthetic_data import (
            build_ccm_link,
            build_compustat_funda,
            build_crsp_msf,
        )

        _SYNTHETIC_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        build_crsp_msf().to_parquet(_SYNTHETIC_SNAPSHOT_DIR / "crsp_msf.parquet", index=False)
        build_compustat_funda().to_parquet(_SYNTHETIC_SNAPSHOT_DIR / "comp_funda.parquet", index=False)
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
    required = ("crsp_msf.parquet", "comp_funda.parquet", "ccm_lnkhist.parquet")
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


def build_llm_client(provider: str, model: str | None):
    return create_llm_client(provider=provider, model=model)


def build_extractor(llm_client) -> SemanticExtractor:
    return SemanticExtractor(llm_client=llm_client, data_dictionary=pipeline.data_layer.dictionary)


def build_review_gate(llm_client) -> ReviewGate:
    return ReviewGate(data_dictionary=pipeline.data_layer.dictionary, llm_client=llm_client)


def build_meta_coder(llm_client) -> MetaCoder:
    return MetaCoder(llm_client=llm_client)
