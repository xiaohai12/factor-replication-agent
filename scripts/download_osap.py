"""Download OSAP reference data from Chen & Zimmermann's GitHub repo.

Downloads:
1. SignalDoc.csv - Factor metadata (used as evaluation ground truth)
2. Predictors/*.py - Signal construction code (used as few-shot examples)

Usage:
    python scripts/download_osap.py [--output-dir PATH]
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path


# Raw file URLs from OpenSourceAP/CrossSection repo
SIGNAL_DOC_URL = "https://raw.githubusercontent.com/OpenSourceAP/CrossSection/master/SignalDoc.csv"

# GitHub API for listing Predictors directory
PREDICTORS_API_URL = "https://api.github.com/repos/OpenSourceAP/CrossSection/contents/Signals/pyCode/Predictors"

# Alternative: direct raw URL pattern for individual predictor files
PREDICTORS_RAW_BASE = "https://raw.githubusercontent.com/OpenSourceAP/CrossSection/master/Signals/pyCode/Predictors"


def download_file(url: str, output_path: Path, description: str = "") -> bool:
    """Download a single file from URL."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "FactorReplicationAgent/0.3 (research)")
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            size_kb = len(content) / 1024
            print(f"  ✓ {description or output_path.name} ({size_kb:.1f} KB)")
            return True
    except Exception as e:
        print(f"  ✗ Failed to download {description or url}: {e}")
        return False


def download_signal_doc(output_dir: Path) -> bool:
    """Download SignalDoc.csv."""
    print("Downloading SignalDoc.csv...")
    output_path = output_dir / "SignalDoc.csv"
    if output_path.exists():
        print(f"  Already exists: {output_path}")
        return True
    return download_file(SIGNAL_DOC_URL, output_path, "SignalDoc.csv")


def list_predictor_files() -> list[str]:
    """List .py files in the Predictors directory via GitHub API."""
    try:
        req = urllib.request.Request(PREDICTORS_API_URL)
        req.add_header("User-Agent", "FactorReplicationAgent/0.3 (research)")
        # Use token if available for higher rate limits
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            req.add_header("Authorization", f"token {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return [
                item["name"]
                for item in data
                if item["name"].endswith(".py")
            ]
    except Exception as e:
        print(f"  [WARN] Could not list predictors via API: {e}")
        print("  Falling back to known predictor list...")
        return _fallback_predictor_list()


def _fallback_predictor_list() -> list[str]:
    """Known subset of predictor files if API fails."""
    return [
        "Accruals.py", "AssetGrowth.py", "BM.py", "Beta.py",
        "CashFlow.py", "DivYield.py", "EP.py", "GrProf.py",
        "IdioVol.py", "Illiquidity.py", "InvGrowth.py", "Mom12m.py",
        "Mom6m.py", "NetIssuance.py", "OperProf.py", "RoE.py",
        "SP.py", "ShareIss5Y.py", "Size.py", "TotalVol.py",
    ]


def download_predictors(output_dir: Path, limit: int | None = None) -> int:
    """Download Predictor .py files."""
    predictors_dir = output_dir / "Predictors"
    predictors_dir.mkdir(parents=True, exist_ok=True)

    print("Listing predictor files...")
    files = list_predictor_files()
    print(f"  Found {len(files)} predictor files")

    if limit:
        files = files[:limit]
        print(f"  Limiting to first {limit}")

    downloaded = 0
    for i, fname in enumerate(files, 1):
        output_path = predictors_dir / fname
        if output_path.exists():
            continue
        url = f"{PREDICTORS_RAW_BASE}/{fname}"
        print(f"  [{i}/{len(files)}] {fname}")
        if download_file(url, output_path, fname):
            downloaded += 1

    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Download OSAP reference data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/osap"),
        help="Output directory (default: data/osap)",
    )
    parser.add_argument(
        "--predictors-limit",
        type=int,
        default=None,
        help="Max predictor files to download (for testing)",
    )
    parser.add_argument(
        "--skip-predictors",
        action="store_true",
        help="Only download SignalDoc.csv, skip predictor code",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {args.output_dir.resolve()}\n")

    # 1. Download SignalDoc.csv
    if not download_signal_doc(args.output_dir):
        print("\nERROR: Failed to download SignalDoc.csv. Check network connection.")
        return

    # 2. Download Predictors
    if not args.skip_predictors:
        print(f"\nDownloading predictor files...")
        n = download_predictors(args.output_dir, limit=args.predictors_limit)
        print(f"\nDownloaded {n} new predictor files to {args.output_dir / 'Predictors'}")

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
