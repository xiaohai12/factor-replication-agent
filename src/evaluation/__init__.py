"""Post-hoc evaluation against independent replication references.

Uses SignalDoc.csv and Firm-Level Characteristics as references for:
1. Extraction accuracy: MethodSpec fields vs SignalDoc.csv
2. Signal accuracy: Plugin output vs C&Z firm-level signals (correlation)
3. Portfolio accuracy: LS returns vs C&Z long-short returns

SignalDoc.csv is ONLY used here (post-hoc evaluation), never as Extractor input.
See docs/cz-reference.md for rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from src.infra.models.method_spec import MethodSpec


@dataclass
class ExtractionEvalResult:
    """Evaluation of MethodSpec extraction against the SignalDoc reference.

    Categorizes discrepancies:
    - paper_ambiguous: paper itself doesn't specify (not LLM's fault)
    - llm_misread: LLM extracted incorrectly from clear paper text
    - cz_supplemented: C&Z added info not in paper (their judgment call)
    - reasonable_divergence: both interpretations are defensible
    """

    factor_id: str
    fields_compared: int = 0
    fields_matching: int = 0
    accuracy: float = 0.0

    # Per-field breakdown
    matches: list[str] = field(default_factory=list)
    discrepancies: list[dict] = field(default_factory=list)
    # Each discrepancy: {field, extracted, reference, category}


@dataclass
class SignalEvalResult:
    """Evaluation of plugin signal output against C&Z firm-level characteristics."""

    factor_id: str
    correlation: Optional[float] = None  # Pearson corr of signal values
    rank_correlation: Optional[float] = None  # Spearman rank corr
    coverage_overlap: Optional[float] = None  # % of firm-months present in both
    n_observations: int = 0


@dataclass
class PortfolioEvalResult:
    """Evaluation of LS returns against C&Z long-short returns."""

    factor_id: str
    return_correlation: Optional[float] = None
    mean_return_ours: Optional[float] = None
    mean_return_cz: Optional[float] = None
    tstat_ours: Optional[float] = None
    tstat_cz: Optional[float] = None


class Evaluator:
    """Post-hoc evaluation against C&Z's independent replication.

    Three levels of evaluation:
    1. Extraction: MethodSpec fields vs SignalDoc.csv
    2. Signal: Plugin output vs C&Z firm-level signals
    3. Portfolio: LS returns vs C&Z long-short returns
    """

    def __init__(self, osap_data_path: str = "./data/osap"):
        self.osap_path = Path(osap_data_path)
        self._signal_doc: Optional[pd.DataFrame] = None

    @property
    def signal_doc(self) -> pd.DataFrame:
        """Lazy-load SignalDoc.csv."""
        if self._signal_doc is None:
            path = self.osap_path / "SignalDoc.csv"
            if not path.exists():
                raise FileNotFoundError(
                    f"SignalDoc.csv not found at {path}. Run download script first."
                )
            self._signal_doc = pd.read_csv(path)
        return self._signal_doc

    def evaluate_extraction(
        self, spec: MethodSpec, factor_id: str
    ) -> ExtractionEvalResult:
        """Compare extracted MethodSpec against the SignalDoc.csv reference.

        Maps MethodSpec fields to SignalDoc columns and compares values.
        """
        result = ExtractionEvalResult(factor_id=factor_id)

        # Resolve acronym: use spec.cz_acronym if set, otherwise fall back to factor_id
        lookup_id = getattr(spec, "cz_acronym", None) or factor_id
        row = self.signal_doc[self.signal_doc["Acronym"] == lookup_id]
        if row.empty:
            return result
        row = row.iloc[0]

        # Field mapping: MethodSpec field -> SignalDoc column
        comparisons = {
            "weighting": ("portfolio.weighting", row.get("Stock Weight", "")),
            "breakpoint_source": ("portfolio.sort.breakpoint_source", row.get("Quantile Filter", "")),
            "formation_month": ("signal.timing.formation_month", row.get("Start Month", "")),
            "holding_period": ("signal.timing.holding_period", row.get("Portfolio Period", "")),
        }

        for field_name, (spec_path, gt_value) in comparisons.items():
            if pd.isna(gt_value) or gt_value == "":
                continue
            result.fields_compared += 1
            extracted = self._get_nested_field(spec, spec_path)
            if self._values_match(extracted, gt_value):
                result.fields_matching += 1
                result.matches.append(field_name)
            else:
                result.discrepancies.append({
                    "field": field_name,
                    "extracted": str(extracted),
                    "reference": str(gt_value),
                    "category": "unknown",  # Categorized manually or by LLM later
                })

        if result.fields_compared > 0:
            result.accuracy = result.fields_matching / result.fields_compared
        return result

    def evaluate_signal(
        self,
        plugin_output: pd.DataFrame,
        factor_id: str,
        cz_signal: Optional[pd.DataFrame] = None,
    ) -> SignalEvalResult:
        """Compare plugin signal output vs C&Z firm-level characteristics.

        Args:
            plugin_output: DataFrame with [permno, yyyymm, signal]
            factor_id: Factor acronym (to load C&Z signal if not provided)
            cz_signal: Pre-loaded C&Z signal (optional)
        """
        # TODO: Load C&Z firm-level signal, merge on [permno, yyyymm], compute correlation
        raise NotImplementedError

    def evaluate_portfolio(
        self,
        our_ls_returns: pd.Series,
        factor_id: str,
    ) -> PortfolioEvalResult:
        """Compare our LS returns vs C&Z long-short returns."""
        # TODO: Load C&Z LS returns, compute correlation and compare t-stats
        raise NotImplementedError

    def _get_nested_field(self, spec: MethodSpec, path: str) -> object:
        """Get a nested field from MethodSpec by dotted path."""
        parts = path.split(".")
        obj = spec
        for part in parts:
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    def _values_match(self, extracted, reference) -> bool:
        """Fuzzy match between an extracted and reference value."""
        if extracted is None:
            return False
        # Normalize for comparison
        ext_str = str(extracted).lower().strip()
        gt_str = str(reference).lower().strip()
        return ext_str == gt_str
