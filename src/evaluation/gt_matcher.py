"""Ground Truth Matcher — match agent-extracted MethodSpec to ground truth.

Uses the spec_paper_mapping.json to find ground truth specs given:
  1. The uploaded PDF filename (finds all factors from that paper)
  2. The agent-extracted factor_id or formula (narrows to the specific signal)

Usage:
    from src.evaluation.gt_matcher import GroundTruthMatcher

    matcher = GroundTruthMatcher()
    matches = matcher.match_by_pdf("Asset Growth and the Cross Section of Stock Returns.pdf")
    # → [{"factor_id": "AssetGrowth", "spec": {...}, "spec_file": "..."}]

    best = matcher.match_extracted(extracted_spec_dict, pdf_filename="Asset Growth...")
    # → [{"factor_id": "AssetGrowth", "score": 0.95, "spec": {...}, "comparisons": [...]}]
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_PATH = _PROJECT_ROOT / "data" / "test_method_specs" / "spec_paper_mapping.json"
_SPECS_DIR = _PROJECT_ROOT / "data" / "test_method_specs"


def _normalize(s: str) -> str:
    """Lowercase, strip non-alphanumeric for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _load_mapping() -> dict:
    if _MAPPING_PATH.exists():
        return json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    return {"factors": {}, "paper_to_factors": {}, "filename_to_factors": {}}


def _load_spec(spec_file: str) -> dict | None:
    """Load a ground truth spec by its relative path."""
    path = _PROJECT_ROOT / spec_file
    if not path.exists():
        # Try just the filename in test_method_specs/
        path = _SPECS_DIR / Path(spec_file).name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _get_nested(d: dict, path: str) -> Any:
    """Get nested value by dot-separated path."""
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def _formula_similarity(a: str | None, b: str | None) -> float:
    """Simple token-overlap similarity between two formula strings."""
    if not a or not b:
        return 0.0
    tokens_a = set(re.findall(r"[a-z_][a-z0-9_]*", a.lower()))
    tokens_b = set(re.findall(r"[a-z_][a-z0-9_]*", b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = tokens_a & tokens_b
    return len(overlap) / max(len(tokens_a), len(tokens_b))


class GroundTruthMatcher:
    """Match agent-extracted specs to ground truth from test_method_specs/."""

    def __init__(self):
        self._mapping = _load_mapping()
        self._factors = self._mapping.get("factors", {})
        self._paper_to_factors = self._mapping.get("paper_to_factors", {})
        self._filename_to_factors = self._mapping.get("filename_to_factors", {})

    @property
    def all_factor_ids(self) -> list[str]:
        return list(self._factors.keys())

    @property
    def all_papers(self) -> list[str]:
        return list(self._filename_to_factors.keys())

    def match_by_pdf(self, pdf_filename: str) -> list[dict]:
        """Find all ground truth factors associated with a PDF filename.

        Args:
            pdf_filename: The PDF filename (just the name, not full path).

        Returns:
            List of dicts with keys: factor_id, spec_file, paper_title, spec (loaded JSON).
        """
        # Try exact filename match
        filename = Path(pdf_filename).name
        factor_ids = self._filename_to_factors.get(filename, [])

        # Try normalized fuzzy match if exact fails
        if not factor_ids:
            norm_input = _normalize(filename)
            for fname, fids in self._filename_to_factors.items():
                norm_fname = _normalize(fname)
                if norm_input in norm_fname or norm_fname in norm_input:
                    factor_ids = fids
                    break

        results = []
        for fid in factor_ids:
            info = self._factors.get(fid, {})
            spec = _load_spec(info.get("spec_file", ""))
            results.append({
                "factor_id": fid,
                "spec_file": info.get("spec_file", ""),
                "paper_title": info.get("paper_title", ""),
                "citation": info.get("citation", ""),
                "spec": spec,
            })
        return results

    def match_by_factor_id(self, factor_id: str) -> dict | None:
        """Look up ground truth by exact factor_id."""
        info = self._factors.get(factor_id)
        if not info:
            # Try normalized match
            norm = _normalize(factor_id)
            for fid, finfo in self._factors.items():
                if _normalize(fid) == norm:
                    info = finfo
                    factor_id = fid
                    break
        if not info:
            return None
        spec = _load_spec(info.get("spec_file", ""))
        return {
            "factor_id": factor_id,
            "spec_file": info.get("spec_file", ""),
            "paper_title": info.get("paper_title", ""),
            "spec": spec,
        }

    def match_extracted(
        self,
        extracted: dict,
        pdf_filename: str | None = None,
    ) -> list[dict]:
        """Match an agent-extracted MethodSpec to the best ground truth(s).

        Strategy:
          1. If pdf_filename given → narrow candidates to that paper's factors
          2. Try exact factor_id match
          3. Try paper_variable_name match
          4. Score by formula similarity

        Args:
            extracted: The agent-extracted MethodSpec as a dict.
            pdf_filename: The PDF filename used for extraction (optional but recommended).

        Returns:
            List of matches sorted by score (highest first), each with:
              factor_id, score, match_method, spec, comparisons
        """
        # Determine candidates
        if pdf_filename:
            candidates = self.match_by_pdf(pdf_filename)
        else:
            # Use all factors as candidates
            candidates = []
            for fid in self._factors:
                info = self._factors[fid]
                spec = _load_spec(info.get("spec_file", ""))
                candidates.append({"factor_id": fid, "spec": spec, **info})

        if not candidates:
            return []

        ext_factor_id = extracted.get("factor_id", "")
        ext_formula = _get_nested(extracted, "signal.formula.expression") or ""
        ext_var_name = _get_nested(extracted, "signal.paper_variable_name") or ""

        scored = []
        for cand in candidates:
            gt = cand.get("spec") or {}
            gt_fid = cand["factor_id"]
            score = 0.0
            match_method = "formula_similarity"

            # Method 1: exact factor_id match
            if _normalize(ext_factor_id) == _normalize(gt_fid):
                score = 1.0
                match_method = "exact_factor_id"

            # Method 2: paper_variable_name match
            gt_var_name = _get_nested(gt, "signal.paper_variable_name") or ""
            if ext_var_name and gt_var_name:
                if _normalize(ext_var_name) == _normalize(gt_var_name):
                    score = max(score, 0.95)
                    if match_method != "exact_factor_id":
                        match_method = "variable_name"

            # Method 3: formula similarity
            gt_formula = _get_nested(gt, "signal.formula.expression") or ""
            formula_sim = _formula_similarity(ext_formula, gt_formula)
            if formula_sim > score and match_method not in ("exact_factor_id", "variable_name"):
                score = formula_sim
                match_method = "formula_similarity"
            elif match_method in ("exact_factor_id", "variable_name"):
                pass  # keep existing high score
            else:
                score = max(score, formula_sim)

            # Method 4: factor_id substring match (e.g. "asset_growth" in "AssetGrowth")
            if score < 0.5:
                norm_ext = _normalize(ext_factor_id)
                norm_gt = _normalize(gt_fid)
                if norm_ext and norm_gt and (norm_ext in norm_gt or norm_gt in norm_ext):
                    score = max(score, 0.7)
                    match_method = "factor_id_substring"

            # Field-by-field comparison
            comparisons = _field_comparisons(extracted, gt)

            scored.append({
                "factor_id": gt_fid,
                "score": round(score, 3),
                "match_method": match_method,
                "spec_file": cand.get("spec_file", ""),
                "paper_title": cand.get("paper_title", ""),
                "spec": gt,
                "comparisons": comparisons,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored


def _field_comparisons(extracted: dict, ground_truth: dict) -> list[dict]:
    """Compare key fields between extracted and ground truth specs."""
    fields = [
        ("signal.formula.expression", "signal.formula.expression"),
        ("signal.formula.paper_expression", "signal.formula.paper_expression"),
        ("signal.paper_variable_name", "signal.paper_variable_name"),
        ("signal.timing.formation_month", "signal.timing.formation_month"),
        ("signal.timing.rebalance_frequency", "signal.timing.rebalance_frequency"),
        ("signal.timing.holding_period", "signal.timing.holding_period"),
        ("signal.timing.accounting_lag", "signal.timing.accounting_lag"),
        ("signal.timing.skip_month", "signal.timing.skip_month"),
        ("signal.missing_policy.action", "signal.missing_policy.action"),
        ("portfolio.sort.breakpoint_source", "portfolio.sort.breakpoint_source"),
        ("portfolio.weighting", "portfolio.weighting"),
        ("portfolio.long_leg", "portfolio.long_leg"),
        ("portfolio.short_leg", "portfolio.short_leg"),
        ("sign", "signal.sign"),
    ]
    results = []
    for ext_path, gt_path in fields:
        ext_val = _get_nested(extracted, ext_path)
        gt_val = _get_nested(ground_truth, gt_path)
        match = _values_match(ext_val, gt_val)
        results.append({
            "field": ext_path,
            "extracted": ext_val,
            "ground_truth": gt_val,
            "match": match,
        })
    return results


def _values_match(a: Any, b: Any) -> bool:
    """Flexibly compare two values."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    sa = str(a).strip().lower()
    sb = str(b).strip().lower()
    if sa == sb:
        return True
    # Strip enum prefixes
    for prefix in ("breakpointsource.", "weightingrule.", "missingaction.",
                   "rebalancefrequency.", "weighingrule."):
        sa = sa.replace(prefix, "")
        sb = sb.replace(prefix, "")
    return sa == sb


# ─── Convenience functions for use in app.py ───


def find_ground_truth_for_pdf(pdf_filename: str) -> list[dict]:
    """Given a PDF filename, return all matching ground truth specs."""
    return GroundTruthMatcher().match_by_pdf(pdf_filename)


def evaluate_extraction(
    extracted_spec: dict,
    pdf_filename: str | None = None,
) -> list[dict]:
    """Evaluate an extracted spec against ground truth.

    Returns list of matches with scores and field comparisons.
    """
    return GroundTruthMatcher().match_extracted(extracted_spec, pdf_filename)


def compute_eval_summary(comparisons: list[dict]) -> dict:
    """Compute summary metrics from field comparisons."""
    total = len(comparisons)
    if total == 0:
        return {"accuracy": 0, "coverage": 0, "matched": 0, "total": 0}
    matched = sum(1 for c in comparisons if c["match"])
    gt_present = sum(1 for c in comparisons if c["ground_truth"] is not None)
    ext_present = sum(1 for c in comparisons if c["extracted"] is not None)
    return {
        "accuracy": matched / total,
        "coverage": ext_present / gt_present if gt_present > 0 else 0,
        "matched": matched,
        "total": total,
        "gt_fields_present": gt_present,
        "ext_fields_present": ext_present,
    }
