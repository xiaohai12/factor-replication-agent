"""Persist the deterministic AssetGrowth MVP synthetic data as parquet files.

Writes:
- data/synthetic_data/mvp_v1/crsp_msf.parquet     (returns panel + snapshot table)
- data/synthetic_data/mvp_v1/comp_funda.parquet   (declarative signal source)
- data/synthetic_data/mvp_v1/ccm_lnkhist.parquet  (CCM link table, keyed on lpermno)
- data/synthetic_data/local/msf.parquet           (dashboard/script CRSP input compatibility)

Run with: python3 scripts/build_synthetic_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.synthetic_data.asset_growth_synthetic_data import (  # noqa: E402
    build_ccm_link,
    build_compustat_funda,
    build_crsp_msf,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "synthetic_data"
    snapshot_dir = root / "mvp_v1"
    local_dir = root / "local"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)

    crsp = build_crsp_msf()
    crsp.to_parquet(snapshot_dir / "crsp_msf.parquet", index=False)
    crsp.to_parquet(local_dir / "msf.parquet", index=False)
    build_compustat_funda().to_parquet(snapshot_dir / "comp_funda.parquet", index=False)
    build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
        snapshot_dir / "ccm_lnkhist.parquet", index=False
    )

    print(f"Wrote synthetic data to {snapshot_dir} and {local_dir}")


if __name__ == "__main__":
    main()
