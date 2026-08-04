"""Deterministic evidence bundle for the replication-diagnosis layer.

Everything in this module is pure arithmetic over already-computed numbers:
the paper's own reported results (`MethodSpec.reported_results`), each
executed track's resolved config (`registry.build_config`) + metrics
(`RunMetrics`), and the optional OAT decomposition
(`ReplicationDiff.diff_ablation`).

It exists so the LLM diagnosis layer (step 8) never has to compute anything.
The LLM is handed `evidence_keys` -- a flat dotted-key -> scalar whitelist of
every number this module derived -- and may only *reference* those keys; the
numbers themselves are re-inserted by the deterministic renderer. Thresholds
(`SIGNIFICANCE_T_THRESHOLD`, `CLOSE_REPLICATION_RATIO_BAND`) and the
`overall_tag` classification live here, in code, never in a prompt: per
AGENTS.md the LLM must not produce any number or threshold that enters a
conclusion, and every conclusion must be reproducible with the LLM switched
off.
"""

from __future__ import annotations

from typing import Any

from src.steps.step3_codegen.registry import (
    CONFIG_KEY_STAGE,  # noqa: F401 -- re-exported for existing `from .bundle import CONFIG_KEY_STAGE` call sites
    stage_of,
)
from src.steps.step7_replication_diff import ReplicationDiffResult


# |t| at which a spread is called statistically distinguishable from zero.
# Deliberately a module constant rather than a prompt instruction.
SIGNIFICANCE_T_THRESHOLD = 1.96

# Ratio band (|ours| / |paper's|) inside which a same-signed spread counts as
# a "close" replication rather than merely sign-agreeing.
CLOSE_REPLICATION_RATIO_BAND = (0.5, 2.0)

# `CONFIG_KEY_STAGE`/`stage_of` moved to `src.steps.step3_codegen.registry`
# 2026-08-03 (single source of truth for the per-key stage taxonomy, now also
# consumed by `registry.build_config`'s override validation) -- re-imported
# here so existing `from .bundle import CONFIG_KEY_STAGE / stage_of` call
# sites (step8_diagnosis, tests) keep working unchanged.

BASELINE_TRACK = "original_method"

# How strongly each evidence section identifies a configuration's effect.
# A config diff only *observes* that two runs differ; a one-at-a-time ablation
# measures a change with everything else held fixed, but OAT effects need not
# be additive and can depend on switch order and on which endpoint is the
# baseline. Neither licenses causal wording -- see docs/multi-config-evidence-plan.md.
CONFIG_DIFF_IDENTIFICATION = "observational"
OAT_IDENTIFICATION = "harmonized"
MISSING_IDENTIFICATION = "unidentified"

OAT_INTERACTION_CAVEAT = (
    "one-at-a-time from a single baseline: contributions need not be additive, "
    "may depend on switch order, and do not identify interactions"
)


def _sign(value: float | None) -> int | None:
    if value is None:
        return None
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts/lists into dotted keys mapping to scalars.

    Lists become ``key[i]``. Only scalars land in the output, so every entry
    is something a diagnosis claim can cite and the renderer can format.
    """
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _resolve_track_spread(
    metrics: dict[str, Any], paper_return_type: str | None
) -> tuple[str, float | None]:
    """Pick the track metric that is comparable to the paper's headline spread.

    A paper reporting an *alpha* headline must be compared against one of our
    alphas, not against the raw mean spread. Preference order mirrors the
    usual headline in the anomaly literature (FF3 first). The chosen key is
    always recorded in the bundle so the comparison basis is auditable.
    """
    rt = (paper_return_type or "").lower()
    if "alpha" in rt:
        for key in ("alpha_ff3", "alpha_capm", "alpha_ff5"):
            if _as_float(metrics.get(key)) is not None:
                return key, _as_float(metrics.get(key))
    return "mean_return", _as_float(metrics.get("mean_return"))


def build_track_vs_paper(
    paper_reported: dict[str, Any], metrics: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic one-track-vs-paper comparison."""
    paper_return_type = paper_reported.get("return_type")
    paper_spread = _as_float(paper_reported.get("main_spread"))
    paper_t = _as_float(paper_reported.get("main_t_stat"))

    metric_key, track_spread = _resolve_track_spread(metrics, paper_return_type)
    track_t = _as_float(metrics.get("t_stat"))

    paper_sign = _sign(paper_spread)
    track_sign = _sign(track_spread)
    sign_agrees = (
        None
        if paper_sign is None or track_sign is None or 0 in (paper_sign, track_sign)
        else paper_sign == track_sign
    )

    spread_delta = (
        None if paper_spread is None or track_spread is None else track_spread - paper_spread
    )
    abs_spread_ratio = (
        None
        if paper_spread in (None, 0.0) or track_spread is None
        else abs(track_spread) / abs(paper_spread)
    )

    # Our RunMetrics only carries the t-stat of the RAW spread series -- we do
    # not currently store alpha t-stats. So when the paper's headline t-stat is
    # on an alpha basis the two t-stats are not like-for-like, and we say so
    # rather than silently differencing them.
    t_stat_comparable = paper_t is not None and "alpha" not in (paper_return_type or "").lower()
    t_stat_delta = (
        track_t - paper_t if t_stat_comparable and track_t is not None else None
    )

    paper_significant = None if paper_t is None else abs(paper_t) >= SIGNIFICANCE_T_THRESHOLD
    track_significant = None if track_t is None else abs(track_t) >= SIGNIFICANCE_T_THRESHOLD
    significance_agrees = (
        None
        if paper_significant is None or track_significant is None
        else paper_significant == track_significant
    )

    return {
        "paper_return_type": paper_return_type,
        "paper_main_spread": paper_spread,
        "paper_main_t_stat": paper_t,
        "track_spread_metric": metric_key,
        "track_spread": track_spread,
        "track_raw_t_stat": track_t,
        "spread_delta": spread_delta,
        "abs_spread_ratio": abs_spread_ratio,
        "sign_agrees": sign_agrees,
        "t_stat_comparable": t_stat_comparable,
        "t_stat_delta": t_stat_delta,
        "significance_threshold": SIGNIFICANCE_T_THRESHOLD,
        "paper_significant": paper_significant,
        "track_significant": track_significant,
        "significance_agrees": significance_agrees,
    }


def classify_overall(vs_paper: dict[str, Any]) -> str:
    """Deterministic replication verdict for the baseline track.

    The LLM never sets this; it may only cite it.
    """
    sign_agrees = vs_paper.get("sign_agrees")
    if sign_agrees is None:
        return "inconclusive"
    if not sign_agrees:
        return "sign_mismatch"
    ratio = vs_paper.get("abs_spread_ratio")
    lo, hi = CLOSE_REPLICATION_RATIO_BAND
    if ratio is not None and lo <= ratio <= hi and vs_paper.get("significance_agrees") is True:
        return "close_replication"
    return "sign_agrees_magnitude_differs"


def build_config_diff(
    tracks: dict[str, dict], baseline: str | None = None
) -> dict[str, Any]:
    """Diff every track's resolved config against the baseline track.

    Baseline-vs-each rather than all-pairs: the question this file answers is
    "why does this track differ from the paper-faithful run", and all-pairs
    grows quadratically once an ablation plan is in play.
    """
    if not tracks:
        return {"baseline_track": None, "identification_level": CONFIG_DIFF_IDENTIFICATION, "pairs": {}}

    base_name = baseline if baseline in tracks else (
        BASELINE_TRACK if BASELINE_TRACK in tracks else next(iter(tracks))
    )
    base_config = tracks[base_name].get("config") or {}

    pairs: dict[str, Any] = {}
    for name, payload in tracks.items():
        if name == base_name:
            continue
        config = payload.get("config") or {}
        details: dict[str, Any] = {}
        for key in sorted(set(base_config) | set(config)):
            base_val = base_config.get(key)
            val = config.get(key)
            if base_val != val:
                details[key] = {
                    "stage": stage_of(key),
                    "baseline_value": base_val,
                    "track_value": val,
                }
        by_stage: dict[str, list[str]] = {}
        for key, d in details.items():
            by_stage.setdefault(d["stage"], []).append(key)
        pairs[name] = {
            "changed_keys": sorted(details),
            "changed_stages": sorted(by_stage),
            "keys_by_stage": {k: sorted(v) for k, v in sorted(by_stage.items())},
            "identification_level": CONFIG_DIFF_IDENTIFICATION,
            "details": details,
        }

    return {
        "baseline_track": base_name,
        "identification_level": CONFIG_DIFF_IDENTIFICATION,
        "pairs": pairs,
    }


def build_gap_decomposition(
    diff_result: ReplicationDiffResult | None,
) -> dict[str, Any]:
    """Expose the OAT decomposition, or say explicitly why it is missing.

    An absent decomposition must never read as "every switch contributed
    zero" -- that is missing evidence, not a measured null, and the LLM has to
    be able to tell the two apart.
    """
    if diff_result is None:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": (
                "replication diff not computed (requires both an original_method "
                "and a standardized_hxz run)"
            ),
        }
    if not diff_result.contributions:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "no ablation_* tracks executed, so per-switch contributions are unmeasured",
            "original_tstat": diff_result.original_tstat,
            "standardized_tstat": diff_result.standardized_tstat,
            "total_gap": diff_result.total_gap,
        }
    return {
        "available": True,
        "identification_level": OAT_IDENTIFICATION,
        "interaction_caveat": OAT_INTERACTION_CAVEAT,
        "original_tstat": diff_result.original_tstat,
        "standardized_tstat": diff_result.standardized_tstat,
        "total_gap": diff_result.total_gap,
        "contributions": dict(diff_result.contributions),
        "explained_fraction": diff_result.explained_fraction,
        "residual": diff_result.residual,
    }


def build_evidence_bundle(
    paper_reported: dict[str, Any],
    tracks: dict[str, dict],
    diff_result: ReplicationDiffResult | None = None,
) -> dict[str, Any]:
    """Assemble the full deterministic evidence bundle.

    Returns the `derived` / `config_diff` / `gap_decomposition` sections plus
    `evidence_keys`, the flat whitelist of every citable scalar (spanning the
    paper's numbers, each track's config + metrics, and everything derived
    here).
    """
    derived: dict[str, Any] = {"tracks": {}}
    for name, payload in tracks.items():
        metrics = payload.get("metrics") or {}
        derived["tracks"][name] = {
            "vs_paper": build_track_vs_paper(paper_reported, metrics),
            "n_months": metrics.get("n_months"),
        }

    baseline = BASELINE_TRACK if BASELINE_TRACK in tracks else (
        next(iter(tracks)) if tracks else None
    )
    derived["baseline_track"] = baseline
    derived["overall_tag"] = (
        classify_overall(derived["tracks"][baseline]["vs_paper"]) if baseline else "inconclusive"
    )

    config_diff = build_config_diff(tracks, baseline)
    gap_decomposition = build_gap_decomposition(diff_result)

    citable = {
        "paper_reported": paper_reported,
        "tracks": tracks,
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
    }
    return {
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
        "evidence_keys": flatten(citable),
    }
