"""Convert gold_standard.csv to gold_standard.json.

Parses flat CSV format into nested JSON structure matching MethodSpec schema.
Handles:
- required_fields: "field:dataset.table:description; ..." → list of dicts
- paper_sections: "Section A; Table 1" → list of strings
- numeric fields: int/float conversion
- null handling: empty string → null

Usage:
    python scripts/csv_to_gold_standard.py
    python scripts/csv_to_gold_standard.py --input data/gold_standard/gold_standard.csv --output data/gold_standard/gold_standard.json
"""

import csv
import json
import argparse
from pathlib import Path


def parse_required_fields(raw: str) -> list[dict]:
    """Parse 'field:dataset.table:description; ...' into structured list."""
    if not raw.strip():
        return []
    fields = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        field_name = parts[0].strip() if len(parts) > 0 else ""
        source = parts[1].strip() if len(parts) > 1 else ""
        description = parts[2].strip() if len(parts) > 2 else ""
        fields.append({
            "field": field_name,
            "source": source,
            "description": description,
        })
    return fields


def parse_sections(raw: str) -> list[str]:
    """Parse 'Section A; Table 1' into list of strings."""
    if not raw.strip():
        return []
    return [s.strip() for s in raw.split(";") if s.strip()]


def safe_int(val: str):
    """Convert to int or return None."""
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val: str):
    """Convert to float or return None."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_winsorize_bounds(raw: str):
    """Parse '1,99' or '0.5,99.5' into [low, high] or None."""
    if not raw or not raw.strip():
        return None
    try:
        parts = raw.split(",")
        return [float(parts[0].strip()), float(parts[1].strip())]
    except (ValueError, IndexError):
        return None


def parse_bool_or_none(raw: str):
    """Parse 'true'/'false' into bool or None if empty."""
    if not raw or not raw.strip():
        return None
    return raw.strip().lower() == "true"


def convert_row(row: dict) -> dict:
    """Convert a single CSV row to gold standard JSON entry."""
    factor_id = row.get("factor_id", "")
    cz_acronym = row.get("cz_acronym", "").strip() or factor_id  # fall back to factor_id
    return {
        "factor_name": row.get("factor_name", ""),
        "economic_intuition": row.get("economic_intuition", ""),
        "detailed_definition": row.get("detailed_definition", ""),
        "formula": row.get("formula", ""),
        "required_fields": parse_required_fields(row.get("required_fields", "")),
        "cat_form": row.get("cat_form", "continuous"),
        "sign": safe_int(row.get("sign", "")),
        "formation_month": safe_int(row.get("formation_month", "")),
        "rebalance_frequency": row.get("rebalance_frequency", "") or None,
        "holding_period": safe_int(row.get("holding_period", "")),
        "accounting_lag": safe_int(row.get("accounting_lag", "")),
        "skip_month": safe_int(row.get("skip_month", "")),
        "stock_weight": row.get("stock_weight", "") or None,
        "ls_quantile": safe_float(row.get("ls_quantile", "")),
        "breakpoint_source": row.get("breakpoint_source", "") or None,
        "long_leg": row.get("long_leg", "") or None,
        "short_leg": row.get("short_leg", "") or None,
        "universe": row.get("universe", "") or None,
        "filter": row.get("filter", "") or None,
        "missing_policy": row.get("missing_policy", "") or None,
        "winsorize_bounds": parse_winsorize_bounds(row.get("winsorize_bounds", "")),
        "overlapping_portfolios": parse_bool_or_none(row.get("overlapping_portfolios", "")),
        "return_horizon": row.get("return_horizon", "") or "monthly",
        "cz_acronym": cz_acronym,
        "reported_return_spread": safe_float(row.get("reported_return_spread", "")),
        "reported_t_stat": safe_float(row.get("reported_t_stat", "")),
        "return_type": row.get("return_type", "") or None,
        "data_frequency": row.get("data_frequency", "") or None,
        "sample_start_year": safe_int(row.get("sample_start_year", "")),
        "sample_end_year": safe_int(row.get("sample_end_year", "")),
        "paper_ref": row.get("paper_ref", ""),
        "paper_sections": parse_sections(row.get("paper_sections", "")),
        "pdf_file": row.get("pdf_file", ""),
        "annotator_notes": row.get("annotator_notes", "") or None,
    }


def main():
    parser = argparse.ArgumentParser(description="Convert gold_standard.csv to JSON")
    parser.add_argument(
        "--input", "-i",
        default="data/gold_standard/gold_standard.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/gold_standard/gold_standard.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return

    # Read CSV
    gold_standard = {}
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            factor_id = row.get("factor_id", "").strip()
            if not factor_id:
                continue
            gold_standard[factor_id] = convert_row(row)

    # Write JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(gold_standard, f, indent=2, ensure_ascii=False)

    print(f"Converted {len(gold_standard)} factors: {input_path} → {output_path}")
    for fid in gold_standard:
        print(f"  - {fid}")


if __name__ == "__main__":
    main()
