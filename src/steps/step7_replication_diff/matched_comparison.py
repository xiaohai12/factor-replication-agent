"""Deterministic matched-sample signal comparison utilities (Phase C/D,
docs/multi-config-evidence-plan.md): "matched-sample signal coverage,
Pearson/Spearman correlation, sign agreement, and extreme-portfolio overlap"
between two firm-month signal series.

SCOPE, stated plainly: these functions consume two ALREADY-LOADED signal
DataFrames (each `[permno, yyyymm, signal]`, the same shape our own
generated scripts now write to `<track>.signal.parquet` -- see
`src/steps/step3_codegen/script_generator.py`). They do NOT fetch or compute
a real C&Z firm-level signal series themselves -- no adapter for that exists
yet (would require running C&Z's own Predictors/*.py or Portfolios/Code/*.R
source under `data/CZ code/` against real WRDS data, a separate,
substantial task). This module is the deterministic comparison MATH the
bridge experiment (Phase C/D "E2") will need the moment such an adapter
exists; it is fully testable today with any two synthetic signal series.

No LLM involvement anywhere in this module -- every number here is plain
pandas/numpy arithmetic, matching the project's LLM-boundary rule (LLM never
computes or decides a number that enters a conclusion).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def matched_sample_stats(
    signal_a: pd.DataFrame,
    signal_b: pd.DataFrame,
    key_cols: tuple[str, str] = ("permno", "yyyymm"),
    value_col: str = "signal",
    extreme_quantile: float = 0.1,
) -> dict[str, Any]:
    """Compare two `[*, key_cols, value_col]` signal panels on their matched
    (inner-joined) firm-months.

    Returns a dict:
      - `n_a`, `n_b`: row counts of each input panel (coverage context).
      - `n_matched`: rows present in BOTH panels on `key_cols`.
      - `coverage_ratio_a`, `coverage_ratio_b`: `n_matched / n_a` /
        `n_matched / n_b` -- how much of each panel's universe the other
        panel actually covers (a low ratio means the two panels disagree on
        WHICH firm-months even have a signal, before values are compared at
        all).
      - `pearson_corr`, `spearman_corr`: correlation of the matched values
        (`None` if fewer than 2 matched rows, since correlation is
        undefined).
      - `sign_agreement_rate`: fraction of matched rows where
        `sign(signal_a) == sign(signal_b)` (rows where either value is
        exactly 0 are excluded -- sign agreement is undefined for a
        zero-valued signal).
      - `top_decile_overlap`, `bottom_decile_overlap`: for each panel
        independently ranked by `value_col` within EACH yyyymm (cross-
        sectionally, matching how a portfolio sort actually forms), the
        fraction of firm-months in panel A's extreme group (top/bottom
        `extreme_quantile`) that are ALSO in panel B's same extreme group
        that month, averaged across months. `None` if there are no matched
        rows.

    Every quantity here is purely descriptive (`observational`
    identification level per the same convention as
    `src.steps.step7_replication_diff.bundle`) -- it does not itself decide
    "close" vs "not close"; that classification, if wanted, is the caller's
    job using the SAME fixed thresholds pattern as
    `bundle.SIGNIFICANCE_T_THRESHOLD`/`CLOSE_REPLICATION_RATIO_BAND`.
    """
    key_a, key_b = key_cols
    a = signal_a[[key_a, key_b, value_col]].rename(columns={value_col: "value_a"})
    b = signal_b[[key_a, key_b, value_col]].rename(columns={value_col: "value_b"})
    merged = a.merge(b, on=[key_a, key_b], how="inner")

    n_a, n_b, n_matched = len(a), len(b), len(merged)
    result: dict[str, Any] = {
        "n_a": n_a,
        "n_b": n_b,
        "n_matched": n_matched,
        "coverage_ratio_a": (n_matched / n_a) if n_a else None,
        "coverage_ratio_b": (n_matched / n_b) if n_b else None,
        "pearson_corr": None,
        "spearman_corr": None,
        "sign_agreement_rate": None,
        "top_decile_overlap": None,
        "bottom_decile_overlap": None,
    }
    if n_matched < 2:
        return result

    result["pearson_corr"] = float(merged["value_a"].corr(merged["value_b"], method="pearson"))
    result["spearman_corr"] = float(merged["value_a"].corr(merged["value_b"], method="spearman"))

    nonzero = merged[(merged["value_a"] != 0) & (merged["value_b"] != 0)]
    if len(nonzero):
        agree = (nonzero["value_a"] > 0) == (nonzero["value_b"] > 0)
        result["sign_agreement_rate"] = float(agree.mean())

    top_overlaps: list[float] = []
    bottom_overlaps: list[float] = []
    for _month, group in merged.groupby(key_b):
        if len(group) < 2:
            continue
        n_extreme = max(1, int(round(len(group) * extreme_quantile)))
        top_a = set(group.nlargest(n_extreme, "value_a").index)
        top_b = set(group.nlargest(n_extreme, "value_b").index)
        bottom_a = set(group.nsmallest(n_extreme, "value_a").index)
        bottom_b = set(group.nsmallest(n_extreme, "value_b").index)
        top_overlaps.append(len(top_a & top_b) / len(top_a))
        bottom_overlaps.append(len(bottom_a & bottom_b) / len(bottom_a))

    if top_overlaps:
        result["top_decile_overlap"] = float(sum(top_overlaps) / len(top_overlaps))
        result["bottom_decile_overlap"] = float(sum(bottom_overlaps) / len(bottom_overlaps))

    return result
