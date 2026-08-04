"""Run the LLM replication-diagnosis layer (step 8) over a comparison bundle.

Reads `runs/backtest_scripts/results/<factor_id>/comparison.json` (schema v2,
i.e. it must already carry the deterministic `evidence_keys` bundle) and writes
`diagnosis.json` + `diagnosis.md` next to it.

    python scripts/analyze_comparison.py --factor-id asset_growth_us_equity_vw --dry-run
    python scripts/analyze_comparison.py --factor-id asset_growth_us_equity_vw

`--dry-run` skips the LLM entirely and just prints the deterministic evidence,
which is the fast way to check the bundle before spending a call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infra.llm import create_llm_client  # noqa: E402
from src.steps.step8_diagnosis import ReplicationDiagnoser  # noqa: E402
from src.steps.step8_diagnosis.render import render_markdown, write_diagnosis  # noqa: E402

DEFAULT_RESULTS_ROOT = Path("runs/backtest_scripts/results")


def resolve_comparison_path(args: argparse.Namespace) -> Path:
    if args.comparison_path:
        return Path(args.comparison_path)
    if not args.factor_id:
        raise SystemExit("Provide either --factor-id or --comparison-path")
    return Path(args.results_root) / args.factor_id / "comparison.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-id", help="Factor id under the results root")
    parser.add_argument("--comparison-path", help="Explicit path to a comparison.json")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--provider", default="codex", help="LLM provider (default: codex)")
    parser.add_argument("--model", default=None, help="Model override for the provider")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the deterministic evidence without calling the LLM",
    )
    args = parser.parse_args()

    path = resolve_comparison_path(args)
    if not path.exists():
        raise SystemExit(f"No comparison.json at {path}")

    bundle = json.loads(path.read_text())
    if "evidence_keys" not in bundle:
        raise SystemExit(
            f"{path} is schema v{bundle.get('schema_version', 1)} (no evidence bundle). "
            "Re-run the experiment to regenerate it."
        )

    derived = bundle.get("derived") or {}
    print(f"factor_id:   {bundle.get('factor_id')}")
    print(f"verdict:     {derived.get('overall_tag')}")
    print(f"baseline:    {derived.get('baseline_track')}")
    print(f"tracks:      {', '.join((bundle.get('tracks') or {}).keys()) or 'none'}")
    print(f"evidence:    {len(bundle['evidence_keys'])} citable keys")

    if args.dry_run:
        for track, d in (derived.get("tracks") or {}).items():
            print(f"\n--- {track} vs paper ---")
            print(json.dumps(d.get("vs_paper"), indent=2, default=str))
        print("\n--- config diff ---")
        print(json.dumps(bundle.get("config_diff"), indent=2, default=str))
        print("\n--- gap decomposition ---")
        print(json.dumps(bundle.get("gap_decomposition"), indent=2, default=str))
        return 0

    client = create_llm_client(provider=args.provider, model=args.model)
    diagnoser = ReplicationDiagnoser(llm_client=client, model=args.model or args.provider)
    report = diagnoser.diagnose(bundle)

    json_path, md_path = write_diagnosis(report, bundle, path.parent)
    print(
        f"\naccepted {len(report.claims)} claim(s), "
        f"rejected {len(report.rejected_claims)}"
    )
    for rejected in report.rejected_claims:
        print(f"  rejected: {rejected.reason}")
    print(f"\nwrote {json_path}\nwrote {md_path}\n")
    print(render_markdown(report, bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
