"""Test pipeline steps 2 → 3 → 4 for a single factor.

Usage:
    python scripts/test_codegen.py [--factor FACTOR_ID]

Runs:
  2    Load resolved MethodSpec (normalized_mapping + all decisions already in spec)
  2.5b _detect_hooks() — identify non-standard backtest steps
  3    MetaCoder generates compute_signal() + hook functions via codex CLI (gpt-5.4)
  4    Future-Leak Scan validates the plugin

Saves plugin to runs/plugins/<factor_id>.py on success.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.steps.engine import BacktestEngine
from src.infra.llm import CodexCLIClient
from src.steps.codegen import MetaCoder
from src.infra.models.method_spec import MethodSpec
from src.steps.validator import AdversarialSandbox


RESOLVED_DIR = ROOT / "runs" / "method_specs" / "resolved"
FIXTURE_DIR  = ROOT / "tests" / "fixtures" / "method_specs"
PLUGINS_DIR  = ROOT / "runs" / "plugins"


def load_resolved_spec(factor_id: str) -> MethodSpec:
    filename = f"{factor_id}.resolved.methodspec.json"
    for directory in (RESOLVED_DIR, FIXTURE_DIR):
        path = directory / filename
        if path.exists():
            return MethodSpec(**json.loads(path.read_text()))
    raise FileNotFoundError(
        f"Resolved MethodSpec not found in runs/method_specs/resolved/ or tests/fixtures/method_specs/: {filename}"
    )


def run(factor_id: str) -> int:
    print(f"\n=== Factor: {factor_id} ===\n")

    # ── Step 2: load resolved MethodSpec ────────────────────────────────────
    print("[2]   Loading resolved MethodSpec...")
    spec = load_resolved_spec(factor_id)
    print(f"      codegen_ready    = {spec.codegen_ready}")
    print(f"      review_status    = {spec.review_status}")
    print(f"      normalized_map   = {spec.data.normalized_mapping}")
    print(f"      breakpoint_source= {spec.breakpoint_source}")
    print(f"      weighting        = {spec.weighting_rule}")
    print(f"      missing_action   = {spec.missing_action}")
    print()

    # ── Step 2.5b: hook detection ────────────────────────────────────────────
    print("[2.5b] Detecting non-standard backtest steps...")
    hooks_needed = BacktestEngine._detect_hooks(spec)
    if hooks_needed:
        for step, reason in hooks_needed.items():
            print(f"       HOOK needed: {step} — {reason}")
    else:
        print("       All steps STANDARD — no hooks needed")
    print()

    # ── Step 3: MetaCoder ────────────────────────────────────────────────────
    print("[3]   Calling MetaCoder via codex CLI (gpt-5.4)...")
    llm   = CodexCLIClient(model="gpt-5.4")
    coder = MetaCoder(llm_client=llm)
    plugin = coder.generate_plugin(spec)

    print(f"      plugin_id  = {plugin.plugin_id}")
    print(f"      code_hash  = {plugin.code_hash}")
    print(f"      hooks      = {plugin.hooks or 'none (all standard)'}")
    print()
    print("── Generated code ──────────────────────────────────────────────────")
    print(plugin.code)
    print("────────────────────────────────────────────────────────────────────")
    print()

    # ── Step 4: Future-Leak Scan ─────────────────────────────────────────────
    print("[4]   Running Future-Leak Scan...")
    sandbox = AdversarialSandbox()
    report  = sandbox.validate(plugin, spec)

    if report.passed:
        print("      PASS — no future-leak patterns detected")
    else:
        print("      FAIL")
        for err in report.errors:
            print(f"      ERROR: {err}")
        return 1

    # ── Save plugin ───────────────────────────────────────────────────────────
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    out = PLUGINS_DIR / f"{factor_id}.py"
    out.write_text(plugin.code)
    print(f"\n      Plugin saved → {out.relative_to(ROOT)}")
    print("\n=== ALL STEPS PASSED ===\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Test pipeline steps 2–4 for a factor")
    parser.add_argument("--factor", default="cooper_gulen_schill_2008_asset_growth")
    args = parser.parse_args()
    sys.exit(run(args.factor))


if __name__ == "__main__":
    main()
