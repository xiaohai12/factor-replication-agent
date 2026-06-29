"""Validate curated MethodSpec JSON files against the current Pydantic model."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infra.models.method_spec import (
    BreakpointSource,
    MethodSpec,
    MissingAction,
    RebalanceFrequency,
    WeightingRule,
)


DEFAULT_METHODSPEC_DIR = Path("data/method_specs/curated")


@dataclass
class ValidationItem:
    path: Path
    ok: bool
    factor_id: str = ""
    codegen_ready: bool = False
    missing_high_impact: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _is_unspecified(value: Any) -> bool:
    if value is None:
        return True
    value = _enum_value(value)
    if isinstance(value, str):
        return value.strip().lower() in {"", "unspecified", "none", "null", "n/a", "nan"}
    return False


def _check_high_impact_fields(spec: MethodSpec) -> list[str]:
    missing: list[str] = []

    checks = {
        "factor_id": spec.factor_id,
        "factor_name": spec.factor_name,
        "signal.formula.expression": spec.signal_formula,
        "signal.required_fields": spec.required_fields,
        "signal.sign": spec.sign,
        "signal.timing.accounting_lag": spec.accounting_lag_months,
        "signal.timing.rebalance_frequency": spec.rebalance_frequency,
        "signal.timing.holding_period": spec.holding_period_months,
        "signal.missing_policy.action": spec.missing_action,
        "portfolio.universe": spec.universe_description,
        "portfolio.breakpoints.source": spec.breakpoint_source,
        "portfolio.breakpoints.ls_quantile": spec.portfolio.breakpoints.ls_quantile,
        "portfolio.weighting": spec.weighting_rule,
        "portfolio.long_leg": spec.portfolio.long_leg,
        "portfolio.short_leg": spec.portfolio.short_leg,
    }

    for field_path, value in checks.items():
        if _is_unspecified(value) or value == []:
            missing.append(field_path)

    if spec.rebalance_frequency == RebalanceFrequency.UNSPECIFIED:
        missing.append("signal.timing.rebalance_frequency")
    if spec.missing_action == MissingAction.UNSPECIFIED:
        missing.append("signal.missing_policy.action")
    if spec.breakpoint_source == BreakpointSource.UNSPECIFIED:
        missing.append("portfolio.breakpoints.source")
    if spec.weighting_rule == WeightingRule.UNSPECIFIED:
        missing.append("portfolio.weighting")

    return sorted(set(missing))


def _check_warnings(spec: MethodSpec) -> list[str]:
    warnings: list[str] = []
    if not spec.extraction_sources:
        warnings.append("missing extraction_sources")
    if not spec.data.required_fields:
        warnings.append("missing data.required_fields")
    if spec.reported_results.main_spread is None and not spec.reported_results.spreads:
        warnings.append("missing reported return spread")
    if spec.reported_results.main_t_stat is None and not spec.reported_results.t_stats:
        warnings.append("missing reported t-stat")
    return warnings


def validate_file(path: Path) -> ValidationItem:
    try:
        spec = MethodSpec.model_validate_json(path.read_text())
    except (ValidationError, json.JSONDecodeError, OSError) as exc:
        return ValidationItem(path=path, ok=False, error=str(exc))

    return ValidationItem(
        path=path,
        ok=True,
        factor_id=spec.factor_id,
        codegen_ready=spec.codegen_ready,
        missing_high_impact=_check_high_impact_fields(spec),
        warnings=_check_warnings(spec),
    )


def _iter_files(args: argparse.Namespace) -> list[Path]:
    if args.file:
        return [Path(args.file)]
    directory = Path(args.dir)
    return sorted(directory.glob("*.methodspec.json"))


def _print_text_report(items: list[ValidationItem]) -> None:
    total = len(items)
    passed = sum(1 for item in items if item.ok)
    failed_items = [item for item in items if not item.ok]
    warning_items = [item for item in items if item.ok and item.missing_high_impact]
    codegen_ready = sum(1 for item in items if item.ok and item.codegen_ready)

    print("MethodSpec validation summary")
    print("=============================")
    print(f"total_files: {total}")
    print(f"parse_success: {passed}")
    print(f"parse_failed: {len(failed_items)}")
    print(f"codegen_ready: {codegen_ready}")
    print(f"missing_high_impact_warnings: {len(warning_items)}")

    if failed_items:
        print("\nParse failures")
        print("--------------")
        for item in failed_items:
            print(f"- {item.path}: {item.error.splitlines()[0]}")

    if warning_items:
        print("\nMissing high-impact fields")
        print("--------------------------")
        for item in warning_items:
            fields = ", ".join(item.missing_high_impact)
            factor = item.factor_id or item.path.stem
            print(f"- {factor} ({item.path.name}): {fields}")

    other_warnings = [item for item in items if item.ok and item.warnings]
    if other_warnings:
        print("\nOther warnings")
        print("--------------")
        for item in other_warnings:
            factor = item.factor_id or item.path.stem
            print(f"- {factor} ({item.path.name}): {', '.join(item.warnings)}")


def _print_json_report(items: list[ValidationItem]) -> None:
    payload = {
        "total_files": len(items),
        "parse_success": sum(1 for item in items if item.ok),
        "parse_failed": sum(1 for item in items if not item.ok),
        "codegen_ready": sum(1 for item in items if item.ok and item.codegen_ready),
        "items": [
            {
                "path": str(item.path),
                "ok": item.ok,
                "factor_id": item.factor_id,
                "codegen_ready": item.codegen_ready,
                "missing_high_impact": item.missing_high_impact,
                "warnings": item.warnings,
                "error": item.error,
            }
            for item in items
        ],
    }
    print(json.dumps(payload, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(DEFAULT_METHODSPEC_DIR))
    parser.add_argument("--file", default="")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    files = _iter_files(args)
    if not files:
        print("No MethodSpec files found.")
        return 1

    items = [validate_file(path) for path in files]
    if args.format == "json":
        _print_json_report(items)
    else:
        _print_text_report(items)

    return 1 if any(not item.ok for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
