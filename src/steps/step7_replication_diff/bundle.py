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

import math
from typing import Any, TYPE_CHECKING

from src.steps.step3_codegen.registry import (
    CONFIG_KEY_STAGE,  # noqa: F401 -- re-exported for existing `from .bundle import CONFIG_KEY_STAGE` call sites
    stage_of,
)
from src.steps.step7_replication_diff import ReplicationDiffResult
from src.steps.step7_replication_diff.attribution import (
    compute_shapley_effects,
    joint_switch_wald_test,
    paired_switch_significance,
    split_tracks_by_comparison_line,
)

if TYPE_CHECKING:
    from pathlib import Path
    from src.infra.models.method_spec import ResolvedMethodSpec


# |t| at which a spread is called statistically distinguishable from zero.
# Deliberately a module constant rather than a prompt instruction. Kept as a
# standalone scalar (not folded into SIGNIFICANCE_T_THRESHOLDS below) since
# tests import and compare against it directly -- do not rename or retype.
SIGNIFICANCE_T_THRESHOLD = 1.96

# HXZ's own three-tier hurdle (docs/step7-8.md Q7; verified against
# `docs/Hou 等 - 2020 - Replicating Anomalies.pdf`: "a, b, and c indicate
# absolute t-values exceeding the thresholds of 1.96, 2.78, and 3.39,
# respectively") -- the Harvey-Liu-Zhu (2016) multiple-testing-adjusted
# significance tiers used throughout the anomaly-replication literature.
# Independent of `SIGNIFICANCE_T_THRESHOLD` above (a separate, coarser
# binary cut some existing fields/tests rely on) -- populates the new
# `paper_significance_tier`/`track_significance_tier` fields only, not a
# replacement for the boolean `*_significant` fields.
SIGNIFICANCE_T_THRESHOLDS = (1.96, 2.78, 3.39)


def _significance_tier(t: float | None) -> int | None:
    """0 = not significant even at the loosest tier, 1/2/3 = cleared that
    many of `SIGNIFICANCE_T_THRESHOLDS` in order. `None` in, `None` out --
    distinguishing "tier 0" (measured, not significant) from "unknown"."""
    if t is None:
        return None
    tier = 0
    for threshold in SIGNIFICANCE_T_THRESHOLDS:
        if abs(t) >= threshold:
            tier += 1
    return tier

# Ratio band (|ours| / |paper's|) inside which a same-signed spread counts as
# a "close" replication rather than merely sign-agreeing.
CLOSE_REPLICATION_RATIO_BAND = (0.5, 2.0)

# docs/step7-8.md readability follow-up (2026-08-22): `overall_tag`/
# `classify_overall` is sign+significance only and BLIND to magnitude -- a
# real MeanRankRevGrowth batch showed a track tagged "reproduced" whose
# spread was only 0.22x the paper's own, which reads as misleadingly
# generous. `magnitude_tier` is a SEPARATE, parallel field (never replaces
# `overall_tag`, same non-destructive precedent as Q7's tiered significance
# alongside the existing boolean) purely on `abs_spread_ratio` + sign:
# `"clean"` reuses the existing `CLOSE_REPLICATION_RATIO_BAND` (0.5x-2.0x,
# already an established, tested constant, not a new number); `"partial"`
# widens symmetrically to 0.2x-5x (this project's own cutoff, not sourced
# from an external standard -- flagged here as needing to be argued for
# explicitly wherever it's cited in the paper's methodology section, not
# just asserted as an engineering default); anything wider than that, or an
# opposite sign, is `"failed"`.
MAGNITUDE_TIER_BANDS = {"clean": CLOSE_REPLICATION_RATIO_BAND, "partial": (0.2, 5.0)}


def _magnitude_tier(ratio: float | None, sign_agrees: bool | None) -> str | None:
    """`"clean"` (same sign, ratio inside `MAGNITUDE_TIER_BANDS["clean"]`) /
    `"partial"` (same sign, ratio inside the wider `["partial"]` band but
    outside `["clean"]`) / `"failed"` (opposite sign, or ratio outside even
    the wider band) / `None` when the ratio or sign itself is unknown."""
    if ratio is None or sign_agrees is None:
        return None
    if not sign_agrees:
        return "failed"
    clean_lo, clean_hi = MAGNITUDE_TIER_BANDS["clean"]
    if clean_lo <= ratio <= clean_hi:
        return "clean"
    partial_lo, partial_hi = MAGNITUDE_TIER_BANDS["partial"]
    if partial_lo <= ratio <= partial_hi:
        return "partial"
    return "failed"

# `CONFIG_KEY_STAGE`/`stage_of` moved to `src.steps.step3_codegen.registry`
# 2026-08-03 (single source of truth for the per-key stage taxonomy, now also
# consumed by `registry.build_config`'s override validation) -- re-imported
# here so existing `from .bundle import CONFIG_KEY_STAGE / stage_of` call
# sites (step8_diagnosis, tests) keep working unchanged.

BASELINE_TRACK = "original_method"

# docs/step7-8.md Part VI: the C&Z comparison line's config always lands on
# this exact track name (mirrors step8_diagnosis.summary's own constant,
# duplicated rather than imported to keep step7 independent of step8).
CZ_ACTUAL_CONFIG_TRACK = "cz_actual_config"

# The HXZ comparison line's counterpart to `CZ_ACTUAL_CONFIG_TRACK`: agent
# signal under the HXZ standardized config (`A_hxz` in
# docs/paper-outline.md's notation).
STANDARDIZED_HXZ_TRACK = "standardized_hxz"

# Which hybrid track pairs with which external reference endpoint in
# `build_three_term_identity`. Both are "agent signal + that implementer's
# config", so differencing an external endpoint against its hybrid track
# holds the CONFIG fixed and isolates the signal-side difference.
THREE_TERM_HYBRID_TRACKS = {"cz": CZ_ACTUAL_CONFIG_TRACK, "hxz": STANDARDIZED_HXZ_TRACK}

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


def _in_sample_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Prefer `by_sample_period.insamp` (the paper's OWN sample window, when
    the run's config carried `sample_start_year`/`sample_end_year`) over the
    top-level metrics, which cover this engine's full extended history --
    often decades past the paper's publication year (e.g. 882 vs 432
    months in a real AssetGrowth run). A paper's headline number was never
    computed over that extra post-publication history, so comparing our
    full-history number against it is apples-to-oranges. Merges key by key
    (not all-or-nothing) since `insamp` doesn't carry every top-level key
    (e.g. `coverage`) and renames its `mean_monthly_return` to `mean_return`
    to match `_resolve_track_spread`'s expected key. Returns `metrics`
    unchanged when no in-sample window was configured."""
    insamp = (metrics.get("by_sample_period") or {}).get("insamp") or {}
    if not insamp:
        return metrics
    merged = {**metrics, **insamp}
    if "mean_monthly_return" in insamp:
        merged["mean_return"] = insamp["mean_monthly_return"]
    return merged


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
        "significance_thresholds_tiered": SIGNIFICANCE_T_THRESHOLDS,
        "paper_significance_tier": _significance_tier(paper_t),
        "track_significance_tier": _significance_tier(track_t),
        "magnitude_tier": _magnitude_tier(abs_spread_ratio, sign_agrees),
    }


def classify_overall(vs_paper: dict[str, Any]) -> str:
    """Deterministic replication verdict for the baseline track, axed on
    SIGNIFICANCE first and sign second -- NOT sign alone (the previous
    scheme's `sign_mismatch` conflated "we found nothing" with "we found the
    opposite effect", two very different findings for a reader).

    The LLM never sets this; it may only cite it.

    - `reproduced` -- same sign; both sides significant, OR (when neither
      t-stat is significant) they at least agree on direction and no
      significant paper effect was contradicted.
    - `not_reproduced` -- the paper found a significant effect but we did
      not: our estimate is statistically indistinguishable from zero, so its
      sign carries no information and must not be read as a "reversed"
      result.
    - `contradicted` -- both sides are significant and disagree in sign: a
      real, reportable conflict between two significant estimates.
    - `inconclusive` -- sign undeterminable (missing/zero spread), or
      neither side's significance can be established and sign disagrees.

    When the paper's headline is on an alpha basis and our own t-stat is not
    alpha-comparable (`t_stat_comparable=False`), significance cannot be
    assessed at all here -- the verdict falls back to sign alone:
    `reproduced` when signs agree, `contradicted` when they don't.
    """
    sign_agrees = vs_paper.get("sign_agrees")
    if sign_agrees is None:
        return "inconclusive"

    paper_significant = vs_paper.get("paper_significant")
    track_significant = vs_paper.get("track_significant")
    if not vs_paper.get("t_stat_comparable") or paper_significant is None or track_significant is None:
        return "reproduced" if sign_agrees else "contradicted"

    if paper_significant and track_significant:
        return "reproduced" if sign_agrees else "contradicted"
    if paper_significant and not track_significant:
        # Our estimate is noise -- a failure to detect, not a reversed sign.
        return "not_reproduced"
    if not paper_significant and track_significant:
        return "reproduced" if sign_agrees else "inconclusive"
    return "inconclusive"


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


def build_spec_quality(spec: "ResolvedMethodSpec | None") -> dict[str, Any]:
    """Layer 1 of step8's diagnosis: which high-impact MethodSpec fields are
    only our best guess (`unspecified`/`inferred`/`conflicting`), not
    something the paper stated clearly.

    Recomputes `review_method_spec` fresh from `spec.paper` -- that function
    is pure and deterministic, so nothing new needs to be persisted to
    expose this to step8; it is simply never called again after Step2 today.
    """
    if spec is None:
        return {"available": False, "reason": "no resolved spec supplied", "weak_fields": []}
    from src.steps.step2_reviewer.review import review_method_spec

    review = review_method_spec(spec.paper)
    weak_fields = [
        {"field_path": f.field_path, "reason": f.reason, "disposition": f.disposition.value}
        for f in review.findings
        if f.kind == "ambiguous"
    ]
    return {"available": True, "weak_fields": weak_fields}


def build_universe_description(spec: "ResolvedMethodSpec | None") -> dict[str, Any]:
    """docs/step7-8.md Part XIII: the paper's OWN natural-language universe
    description (`spec.paper.universe.description`, a `SourcedValue[str]`
    already extracted -- with its own paper-quote evidence -- by step1).

    Exists so step8 can quote what the paper actually said about its
    universe instead of us re-deriving a plain-English description from the
    resolved `universe_filters` config -- a hardcoded per-value lookup table
    (SIC/share-code/exchange-code combinations) cannot generalize to every
    future paper's own filter choices, but the paper's own extracted text
    already does, for any paper, by construction.
    """
    if spec is None:
        return {"available": False, "reason": "no resolved spec supplied"}
    description = spec.paper.universe.description
    return {"available": True, "text": description.value}


def build_menu_deviations(
    spec: "ResolvedMethodSpec | None", tracks: dict[str, dict]
) -> dict[str, Any]:
    """Layer 2 of step8's diagnosis: where the paper's stated method fell
    off the engine's fixed menu (`SourcedValue.unsupported_value`) and,
    per track, which config keys got clamped to a menu default
    (`defaults_applied`, already inside each track's resolved config --
    see `registry.build_config`). Neither piece needs new persistence:
    `unsupported_value` lives on `spec.paper` and `defaults_applied` is
    already threaded into `tracks[name]["config"]`.
    """
    if spec is None:
        return {
            "available": False,
            "reason": "no resolved spec supplied",
            "unsupported_paper_fields": [],
            "clamped_by_track": {},
        }
    from src.steps.step2_reviewer.review import high_impact_sourced_values

    unsupported = [
        {"field_path": path, "unsupported_value": sv.unsupported_value}
        for path, sv in high_impact_sourced_values(spec.paper)
        if getattr(sv, "unsupported_value", None)
    ]
    clamped_by_track = {
        name: payload["config"]["defaults_applied"]
        for name, payload in tracks.items()
        if (payload.get("config") or {}).get("defaults_applied")
    }
    return {
        "available": True,
        "unsupported_paper_fields": unsupported,
        "clamped_by_track": clamped_by_track,
    }


def build_publication_decay(tracks: dict[str, dict]) -> dict[str, Any]:
    """Evidence for a `publication_decay` claim: in-sample vs
    post-publication t-stat per track, when `by_sample_period` was
    configured (`RunMetrics.by_sample_period`, requires
    `sample_start_year`/`sample_end_year`/`publication_year` in the run's
    config)."""
    per_track: dict[str, Any] = {}
    for name, payload in tracks.items():
        by_period = (payload.get("metrics") or {}).get("by_sample_period")
        if not by_period:
            continue
        insamp_t = _as_float((by_period.get("insamp") or {}).get("t_stat"))
        postpub_t = _as_float((by_period.get("postpub") or {}).get("t_stat"))
        insamp_sig = None if insamp_t is None else abs(insamp_t) >= SIGNIFICANCE_T_THRESHOLD
        postpub_sig = None if postpub_t is None else abs(postpub_t) >= SIGNIFICANCE_T_THRESHOLD
        decayed = (
            None if insamp_sig is None or postpub_sig is None else (insamp_sig and not postpub_sig)
        )
        per_track[name] = {
            "insamp_t_stat": insamp_t,
            "postpub_t_stat": postpub_t,
            "insamp_significant": insamp_sig,
            "postpub_significant": postpub_sig,
            "decayed": decayed,
        }
    if not per_track:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "no track configured sample_start_year/sample_end_year/publication_year",
        }
    return {"available": True, "tracks": per_track}


def build_robustness_summary(tracks: dict[str, dict]) -> dict[str, Any]:
    """Evidence for an `implementation_robustness` claim: aggregates every
    `ablation_*` track's t-stat against the baseline (`original_method`) --
    the range, how many sign flips, and how many significance-threshold
    flips -- into a single robust/fragile verdict."""
    baseline_name = BASELINE_TRACK if BASELINE_TRACK in tracks else None
    ablation_names = [n for n in tracks if n.startswith("ablation_")]
    if baseline_name is None or not ablation_names:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "requires a baseline (original_method) track plus at least one ablation_* track",
        }
    baseline_t = _as_float((tracks[baseline_name].get("metrics") or {}).get("t_stat"))
    baseline_sign = _sign(baseline_t)
    baseline_sig = None if baseline_t is None else abs(baseline_t) >= SIGNIFICANCE_T_THRESHOLD

    t_stats = [baseline_t] if baseline_t is not None else []
    sign_flips = 0
    significance_flips = 0
    for name in ablation_names:
        t = _as_float((tracks[name].get("metrics") or {}).get("t_stat"))
        if t is None:
            continue
        t_stats.append(t)
        if baseline_sign is not None and _sign(t) is not None and _sign(t) != baseline_sign:
            sign_flips += 1
        if baseline_sig is not None:
            sig = abs(t) >= SIGNIFICANCE_T_THRESHOLD
            if sig != baseline_sig:
                significance_flips += 1

    if not t_stats:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "no t-stat available on baseline or ablation tracks",
        }
    return {
        "available": True,
        "n_ablation_tracks": len(ablation_names),
        "t_stat_range": max(t_stats) - min(t_stats),
        "sign_flips": sign_flips,
        "significance_flips": significance_flips,
        "robust": sign_flips == 0 and significance_flips == 0,
    }


def build_t_channel_decomposition(
    tracks: dict[str, dict], baseline: str | None = None
) -> dict[str, Any]:
    """docs/step7-8.md Q1/Q5: the t-stat's OWN exact-identity decomposition,
    a companion to `gap_decomposition`/Shapley (which operate on
    `mean_return`, the only additive quantity) -- NOT an alternative to
    them, per Q1's decision to keep the two dimensions as separate,
    unmerged evidence blocks.

    Uses ONLY (mean_return, t_stat, n_months), already in `RunMetrics` --
    no persisted std-dev needed, since sigma is back-solved from the exact
    identity `t = mean_return / (sigma / sqrt(n_months))`:

        log(t_track) - log(t_baseline)
          = [log(mean_return_track) - log(mean_return_baseline)]     (mean_return channel)
          - [log(sigma_track)       - log(sigma_baseline)]           (volatility channel)
          + 0.5 * [log(n_months_track) - log(n_months_baseline)]     (sample_size channel)

    Each channel needs a STANDALONE log(mean_return_*)/log(sigma_*), which
    requires `mean_return > 0` for BOTH the track and the baseline -- not
    merely same-signed: log of an individual negative value is undefined
    even though the ratio of two negatives would be positive (docs/step7-8.md
    Q5's "mu<0 -> log undefined" case). Degenerates per-track to a bare
    `t_stat_abs_delta` (|t_track| - |t_baseline|) instead, tagged
    `degenerate: True` with a `reason`, when this fails -- never silently
    drops the track or fabricates a channel split.
    """
    if not tracks:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "no tracks",
            "baseline_track": None,
            "tracks": {},
        }
    base_name = baseline if baseline in tracks else (
        BASELINE_TRACK if BASELINE_TRACK in tracks else next(iter(tracks))
    )
    base_metrics = tracks[base_name].get("metrics") or {}
    base_mu = _as_float(base_metrics.get("mean_return"))
    base_t = _as_float(base_metrics.get("t_stat"))
    base_n = _as_float(base_metrics.get("n_months"))

    per_track: dict[str, Any] = {}
    for name, payload in tracks.items():
        if name == base_name:
            continue
        metrics = payload.get("metrics") or {}
        mu = _as_float(metrics.get("mean_return"))
        t = _as_float(metrics.get("t_stat"))
        n = _as_float(metrics.get("n_months"))

        abs_t = None if t is None else abs(t)
        abs_base_t = None if base_t is None else abs(base_t)
        t_stat_abs_delta = None if abs_t is None or abs_base_t is None else abs_t - abs_base_t

        reason: str | None = None
        if base_mu is None or mu is None:
            reason = "mean_return missing on baseline or track"
        elif base_mu <= 0 or mu <= 0:
            reason = "mean_return must be positive on both baseline and track for a log decomposition"
        elif base_t is None or t is None or base_t == 0 or t == 0:
            reason = "t_stat missing or zero on baseline or track"
        elif base_n is None or n is None or base_n <= 0 or n <= 0:
            reason = "n_months missing or non-positive on baseline or track"
        elif _sign(base_t) != _sign(base_mu) or _sign(t) != _sign(mu):
            reason = "t_stat and mean_return signs are inconsistent (cannot back-solve a positive implied volatility)"

        if reason is not None:
            per_track[name] = {
                "degenerate": True,
                "reason": reason,
                "t_stat_abs_delta": t_stat_abs_delta,
            }
            continue

        base_sigma = base_mu * (base_n**0.5) / base_t
        sigma = mu * (n**0.5) / t
        mean_return_channel = math.log(mu) - math.log(base_mu)
        volatility_channel = -(math.log(sigma) - math.log(base_sigma))
        sample_size_channel = 0.5 * (math.log(n) - math.log(base_n))

        per_track[name] = {
            "degenerate": False,
            "log_t_ratio": math.log(t) - math.log(base_t),
            "channels": {
                "mean_return": mean_return_channel,
                "volatility": volatility_channel,
                "sample_size": sample_size_channel,
            },
            "channel_sum_check": mean_return_channel + volatility_channel + sample_size_channel,
            "implied_sigma": sigma,
            "implied_baseline_sigma": base_sigma,
            "t_stat_abs_delta": t_stat_abs_delta,
        }

    return {
        "available": True,
        "identification_level": CONFIG_DIFF_IDENTIFICATION,
        "baseline_track": base_name,
        "tracks": per_track,
    }


def build_shapley_and_significance(
    tracks: dict[str, dict], results_dir: "Path | None", baseline: str | None
) -> dict[str, Any]:
    """Wraps `attribution.compute_shapley_effects`/`paired_switch_significance`/
    `joint_switch_wald_test` for `build_evidence_bundle`, run ONCE PER
    comparison line (`attribution.split_tracks_by_comparison_line`) rather
    than once for the whole batch.

    Why per-line: a batch that ran BOTH ①→② (`cz_factorial_*`) and ①→③
    (`factorial_*`) auto-attribution can have two DIFFERENT tracks that
    both touch only e.g. "universe" (flipped to two different target
    values) -- found in production, see docs/step7-8.md Part V. Splitting
    by line means the two never enter the same calculation, so the
    ambiguity this used to trigger (`switches_flipped` key collision)
    cannot occur at all, rather than being detected and one switch
    excluded.

    Output shape: `{"shapley_attribution": {"to_hxz": {...}, "to_cz":
    {...}}, "paired_tests": {...same...}, "joint_test": {...same...}}` --
    a batch with only one line present (the common case: most sessions
    never set `cz_config_override`) only has that one key nested inside
    each of the three. `results_dir` is optional (unlike the other
    builders here, these three need the on-disk `<track>.csv` monthly
    return series, not just `tracks`' own config/metrics dicts) -- when
    it's `None`, `paired_tests`/`joint_test` report `available=False` with
    that reason per line; `shapley_attribution` doesn't need `results_dir`
    at all (it only reads `mean_return`, already in `tracks`).
    """
    baseline_track = baseline or "original_method"
    lines = split_tracks_by_comparison_line(tracks, baseline_track=baseline_track)
    if not lines:
        unavailable = {"available": False, "reason": "no factorial/ablation switches_flipped tracks found"}
        return {"shapley_attribution": unavailable, "paired_tests": unavailable, "joint_test": unavailable}

    shapley_attribution: dict[str, Any] = {}
    paired_tests: dict[str, Any] = {}
    joint_test: dict[str, Any] = {}
    no_results_dir = {"available": False, "reason": "no results_dir supplied"}
    for line, line_tracks in lines.items():
        shapley_attribution[line] = compute_shapley_effects(line_tracks, baseline_track=baseline_track)
        if results_dir is None:
            paired_tests[line] = no_results_dir
            joint_test[line] = no_results_dir
        else:
            paired_tests[line] = paired_switch_significance(results_dir, line_tracks, baseline_track=baseline_track)
            joint_test[line] = joint_switch_wald_test(results_dir, line_tracks, baseline_track=baseline_track)
    return {
        "shapley_attribution": shapley_attribution,
        "paired_tests": paired_tests,
        "joint_test": joint_test,
    }


def build_gap_closure(derived: dict[str, Any], paired_tests: dict[str, Any]) -> dict[str, Any]:
    """Whether the catalogued config differences to C&Z actually EXPLAIN the
    total to_cz gap, or leave a residual not produced by any of them --
    since no C&Z bridge track exists to separate a signal-formula difference
    from a convention difference directly (removed 2026-08-18, see
    CHANGELOG), this residual is the only evidence available for "how much
    of the gap is NOT explained by known settings".

    `total_gap` = baseline's spread minus `cz_actual_config`'s spread (both
    already `derived.tracks.*.vs_paper.track_spread`, so on the SAME basis
    `build_track_vs_paper` chose for this paper). `sum_of_switch_effects` is
    the sum of every AVAILABLE `paired_tests["to_cz"].per_switch.*.mean_diff`
    -- one-at-a-time, harmonized evidence (`OAT_INTERACTION_CAVEAT` applies:
    not additive, order-dependent, no interactions identified), so the
    residual is only a lower bound on "unexplained", not a precise figure.
    """
    baseline_track = derived.get("baseline_track")
    tracks_derived = derived.get("tracks") or {}
    baseline_spread = ((tracks_derived.get(baseline_track) or {}).get("vs_paper") or {}).get("track_spread")
    cz_spread = ((tracks_derived.get(CZ_ACTUAL_CONFIG_TRACK) or {}).get("vs_paper") or {}).get("track_spread")
    if baseline_track is None or CZ_ACTUAL_CONFIG_TRACK not in tracks_derived or baseline_spread is None or cz_spread is None:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "requires both the baseline track and the cz_actual_config track to have a resolvable spread",
        }
    total_gap = baseline_spread - cz_spread

    per_switch = ((paired_tests.get("to_cz") or {}).get("per_switch")) or {}
    contributions = {
        switch: entry["mean_diff"]
        for switch, entry in per_switch.items()
        if entry.get("available") is True and entry.get("mean_diff") is not None
    }
    if not contributions:
        return {
            "available": True,
            "identification_level": OAT_IDENTIFICATION,
            "interaction_caveat": OAT_INTERACTION_CAVEAT,
            "total_gap": total_gap,
            "contributions": {},
            "sum_of_switch_effects": None,
            "residual": None,
            "explained_fraction": None,
            "reason": "no per-switch paired-test evidence available on the to_cz line",
        }

    sum_of_switch_effects = sum(contributions.values())
    residual = total_gap - sum_of_switch_effects
    explained_fraction = (sum_of_switch_effects / total_gap) if total_gap not in (None, 0.0) else None
    return {
        "available": True,
        "identification_level": OAT_IDENTIFICATION,
        "interaction_caveat": OAT_INTERACTION_CAVEAT,
        "total_gap": total_gap,
        "contributions": contributions,
        "sum_of_switch_effects": sum_of_switch_effects,
        "residual": residual,
        "explained_fraction": explained_fraction,
    }


# Each three-term component answers a different question and carries a
# DIFFERENT kind of noise -- reported alongside the numbers so no reader (or
# step8 claim) can treat them as one homogeneous "error".
THREE_TERM_PURITY_NOTES = {
    "signal_and_environment": (
        "config held fixed, so this isolates the signal-side difference -- but it also "
        "absorbs data-vintage and engine differences between this project and the external "
        "implementer, so it is a signal+environment residual, not a pure signal effect"
    ),
    "config": (
        "signal held fixed (both sides run the agent's own signal), so this is the one "
        "genuinely clean term: it is exactly the effect of adopting that implementer's "
        "configuration, and is the term the field-level gap decomposition splits further"
    ),
    "agent_replication_residual": (
        "how far the agent's paper-faithful run lands from the paper's own reported number; "
        "this is the agent's replication error, NOT paper ambiguity, and it caps how much "
        "of the other two terms can be read as a statement about the paper"
    ),
}

THREE_TERM_WINDOW_CAVEAT = (
    "the four endpoints are not on a common sample window or statistical basis: the paper's "
    "number comes from its own sample and its own era's estimator, this engine's tracks use "
    "its own data coverage with Newey-West standard errors, and each external endpoint "
    "carries its own window (see window_basis) -- the identity still holds exactly by "
    "construction, but the window/basis mismatch is absorbed into the signal_and_environment "
    "term rather than being separately identified"
)


def build_three_term_identity(
    derived: dict[str, Any],
    paper_reported: dict[str, Any],
    external_reference: dict[str, Any] | None,
    hybrid_track: str,
    reference_label: str,
) -> dict[str, Any]:
    """Decompose one external implementer's distance from the PAPER's own
    reported number into signal, config, and agent-replication components
    (docs/paper-outline.md C1):

        X - P = (X - A_hybrid) + (A_hybrid - A) + (A - P)

    where `P` is the paper's reported spread, `A` the agent's paper-faithful
    baseline track, `A_hybrid` the agent's signal run under the external
    implementer's config (`cz_actual_config` / `standardized_hxz`), and `X`
    that implementer's OWN measured result.

    The identity telescopes, so `residual` is zero by construction -- it is
    emitted anyway as an arithmetic audit check, exactly like
    `gap_decomposition.residual`. What is NOT free is interpretation: the
    three terms have different noise content (`THREE_TERM_PURITY_NOTES`) and
    the endpoints do not share a sample window (`THREE_TERM_WINDOW_CAVEAT`),
    both of which travel with the numbers so step8 cannot quietly drop them.

    Identification is `observational`: nothing here is a controlled
    contrast between two runs of THIS engine except the config term, and
    even that is a single pair rather than an ablation grid.
    """
    tracks_derived = derived.get("tracks") or {}
    baseline_track = derived.get("baseline_track")
    baseline_spread = ((tracks_derived.get(baseline_track) or {}).get("vs_paper") or {}).get("track_spread")
    hybrid_spread = ((tracks_derived.get(hybrid_track) or {}).get("vs_paper") or {}).get("track_spread")
    paper_spread = _as_float(paper_reported.get("main_spread"))
    external_spread = _as_float((external_reference or {}).get("spread"))

    missing = [
        name
        for name, value in (
            ("paper_reported.main_spread", paper_spread),
            (f"baseline track {baseline_track!r} spread", baseline_spread),
            (f"hybrid track {hybrid_track!r} spread", hybrid_spread),
            (f"external {reference_label} reference spread", external_spread),
        )
        if value is None
    ]
    if missing:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reference_label": reference_label,
            "hybrid_track": hybrid_track,
            "reason": f"three-term identity needs all four endpoints; missing: {', '.join(missing)}",
        }

    signal_and_environment = external_spread - hybrid_spread
    config = hybrid_spread - baseline_spread
    agent_replication_residual = baseline_spread - paper_spread
    total_gap = external_spread - paper_spread
    terms_sum = signal_and_environment + config + agent_replication_residual

    return {
        "available": True,
        "identification_level": CONFIG_DIFF_IDENTIFICATION,
        "reference_label": reference_label,
        "hybrid_track": hybrid_track,
        "endpoints": {
            "paper_reported_spread": paper_spread,
            "agent_baseline_spread": baseline_spread,
            "agent_hybrid_spread": hybrid_spread,
            "external_reference_spread": external_spread,
            "baseline_track": baseline_track,
        },
        "total_gap": total_gap,
        "terms": {
            "signal_and_environment": signal_and_environment,
            "config": config,
            "agent_replication_residual": agent_replication_residual,
        },
        "terms_sum_check": terms_sum,
        "residual": total_gap - terms_sum,
        "largest_term": max(
            ("signal_and_environment", "config", "agent_replication_residual"),
            key=lambda name: abs(
                {
                    "signal_and_environment": signal_and_environment,
                    "config": config,
                    "agent_replication_residual": agent_replication_residual,
                }[name]
            ),
        ),
        "term_purity_notes": THREE_TERM_PURITY_NOTES,
        "window_basis": {
            "paper_sample_start_year": paper_reported.get("sample_start_year"),
            "paper_sample_end_year": paper_reported.get("sample_end_year"),
            "external_sample_start_year": (external_reference or {}).get("sample_start_year"),
            "external_sample_end_year": (external_reference or {}).get("sample_end_year"),
            "external_window_adjustable": (external_reference or {}).get("window_adjustable"),
            "window_sensitivity_spread": (external_reference or {}).get("window_sensitivity_spread"),
            "external_source": (external_reference or {}).get("source"),
            "caveat": THREE_TERM_WINDOW_CAVEAT,
        },
    }


def build_three_term_identities(
    derived: dict[str, Any],
    paper_reported: dict[str, Any],
    external_references: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """`build_three_term_identity` for every external endpoint that has a
    hybrid track paired with it (`THREE_TERM_HYBRID_TRACKS`), keyed the same
    way `shapley_attribution`/`paired_tests` key their comparison lines.

    An endpoint absent from `external_references` still gets an entry, with
    `available=False` and the reason -- an unresolvable external reference
    must never read as "the gap was zero".
    """
    external_references = external_references or {}
    return {
        label: build_three_term_identity(
            derived, paper_reported, external_references.get(label), hybrid_track, label
        )
        for label, hybrid_track in THREE_TERM_HYBRID_TRACKS.items()
    }


def _external_performance_entry(reference: dict[str, Any] | None) -> dict[str, Any]:
    if reference is None:
        return {"available": False, "reason": "no external reference resolved for this acronym"}
    return {
        "available": True,
        "mean_return": reference.get("spread"),
        "t_stat": reference.get("t_stat"),
        "sample_start_year": reference.get("sample_start_year"),
        "sample_end_year": reference.get("sample_end_year"),
        "source": reference.get("source"),
    }


def _verdict_vs_external_reference(
    track_entry: dict[str, Any] | None, reference_entry: dict[str, Any], track_name: str | None
) -> dict[str, Any]:
    """Deterministic sign/ratio/significance verdict for one agent TRACK's
    own measured result against an EXTERNAL implementer's (C&Z/HXZ) own
    self-reported number for the SAME factor -- docs/step7-8.md "Step A":
    "we ran C&Z's/HXZ's exact config through our engine; does the number we
    got match the number THEY got?" A different question from both
    `build_track_vs_paper` (agent vs the PAPER's own text) and
    `three_term_identity` (an accounting split of X - P, not a verdict).

    Reuses `build_track_vs_paper`/`classify_overall` verbatim by packaging
    the external reference as a synthetic `paper_reported`-shaped dict --
    identical sign/ratio/significance math, a different endpoint. Field
    names in the returned dict are renamed away from the reused function's
    `paper_*` vocabulary (which would misleadingly say "paper" for what is
    actually C&Z's or HXZ's own number) to `reference_*`.
    """
    if (
        track_entry is None
        or track_entry.get("mean_return") is None
        or track_entry.get("t_stat") is None
        or reference_entry.get("available") is not True
    ):
        return {"available": False, "reason": "agent track or external reference missing mean_return/t_stat"}
    fake_paper_reported = {
        "return_type": "mean_return",
        "main_spread": reference_entry.get("mean_return"),
        "main_t_stat": reference_entry.get("t_stat"),
    }
    fake_metrics = {"mean_return": track_entry.get("mean_return"), "t_stat": track_entry.get("t_stat")}
    vs_reference = build_track_vs_paper(fake_paper_reported, fake_metrics)
    return {
        "available": True,
        "track": track_name,
        "track_spread": vs_reference["track_spread"],
        "track_t_stat": vs_reference["track_raw_t_stat"],
        "reference_spread": vs_reference["paper_main_spread"],
        "reference_t_stat": vs_reference["paper_main_t_stat"],
        "sign_agrees": vs_reference["sign_agrees"],
        "abs_spread_ratio": vs_reference["abs_spread_ratio"],
        "reference_significant": vs_reference["paper_significant"],
        "track_significant": vs_reference["track_significant"],
        "significance_agrees": vs_reference["significance_agrees"],
        "verdict": classify_overall(vs_reference),
    }


def build_external_performance_comparison(
    derived: dict[str, Any], external_references: dict[str, dict[str, Any]] | None
) -> dict[str, Any]:
    """Direct multi-way comparison of every agent track's OWN `mean_return`/
    `t_stat` against C&Z's and HXZ's own reported numbers (`external_
    references`, see `src.infra.reference.external_references_for_results_
    dir`) -- deliberately NOT routed through `paper_reported` the way
    `three_term_identity` is.

    Exists because `paper_reported` is sometimes an incomplete or
    non-comparable statistic (not `mean_return`, missing a t-stat, or
    describing a different specification than what this engine tracks) --
    forcing everything through a `X - paper` identity either breaks or
    silently degrades. This section just lays the numbers side by side: no
    subtraction, no identity, nothing requires all fields to be present at
    once. `mean_return`/`t_stat` missing on either side simply means that
    field is `None` for that point -- the whole section still renders.

    `agent_vs_cz`/`agent_vs_hxz` (docs/step7-8.md "Step A") go one step
    further than the raw side-by-side: a deterministic verdict on whether
    running that implementer's OWN config through this engine (the
    `cz_actual_config`/`standardized_hxz` tracks) reproduces what they
    themselves report, using the same sign/ratio/significance machinery as
    `derived.tracks.*.vs_paper`.

    Deliberately reads `derived.tracks.*.raw_mean_return`/`raw_t_stat`, NOT
    `vs_paper.track_spread`/`track_raw_t_stat` -- the former is always the
    raw long-short spread, the latter's `track_spread` half may silently be
    an ALPHA when `paper_reported.return_type` is alpha-based (see
    `_resolve_track_spread`). C&Z's/HXZ's own numbers this section compares
    against are always the raw spread (never alpha), so using the
    paper-comparison basis here would silently compare an alpha to a raw
    return for any alpha-headline paper. `spread_basis` names this
    explicitly so a reader never has to guess.
    """
    agent_tracks = {
        name: {
            "mean_return": track.get("raw_mean_return"),
            "t_stat": track.get("raw_t_stat"),
            "n_months": track.get("n_months"),
            "significance_tier": (track.get("vs_paper") or {}).get("track_significance_tier"),
            "spread_basis": "raw_mean_return",
        }
        for name, track in (derived.get("tracks") or {}).items()
    }
    external_references = external_references or {}
    cz_entry = _external_performance_entry(external_references.get("cz"))
    hxz_entry = _external_performance_entry(external_references.get("hxz"))
    return {
        "agent_tracks": agent_tracks,
        "cz": cz_entry,
        "hxz": hxz_entry,
        "agent_vs_cz": _verdict_vs_external_reference(
            agent_tracks.get(CZ_ACTUAL_CONFIG_TRACK), cz_entry, CZ_ACTUAL_CONFIG_TRACK
        ),
        "agent_vs_hxz": _verdict_vs_external_reference(
            agent_tracks.get(STANDARDIZED_HXZ_TRACK), hxz_entry, STANDARDIZED_HXZ_TRACK
        ),
    }


def build_paper_verdict_agreement(external_references: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """docs/step7-8.md "Step B": do C&Z's and HXZ's own self-reported
    numbers for this factor agree or conflict with EACH OTHER -- a question
    entirely upstream of "did WE replicate", answerable before this engine
    ran a single track. A plain sign+significance comparison of two
    external numbers (same `SIGNIFICANCE_T_THRESHOLD` cut as everywhere
    else in this module), not an accounting split like `three_term_
    identity` and not itself a claim about this project's own replication.

    `verdict`:
    - `agree_significant`   -- both sides clear the significance bar, same sign.
    - `agree_insignificant` -- neither side clears the significance bar.
    - `conflict`            -- exactly one side is significant, or both are
                               significant with opposite signs.
    - `unavailable`         -- one or both external references are missing.
    """
    external_references = external_references or {}
    cz = external_references.get("cz")
    hxz = external_references.get("hxz")
    if not cz or not hxz:
        return {"available": False, "reason": "requires both a resolved C&Z and HXZ external reference", "verdict": "unavailable"}
    cz_spread, cz_t = cz.get("spread"), cz.get("t_stat")
    hxz_spread, hxz_t = hxz.get("spread"), hxz.get("t_stat")
    if cz_spread is None or cz_t is None or hxz_spread is None or hxz_t is None:
        return {"available": False, "reason": "one side is missing a spread or t-stat", "verdict": "unavailable"}

    cz_significant = abs(cz_t) >= SIGNIFICANCE_T_THRESHOLD
    hxz_significant = abs(hxz_t) >= SIGNIFICANCE_T_THRESHOLD
    sign_agrees = _sign(cz_spread) == _sign(hxz_spread)

    if cz_significant and hxz_significant:
        verdict = "agree_significant" if sign_agrees else "conflict"
    elif not cz_significant and not hxz_significant:
        verdict = "agree_insignificant"
    else:
        verdict = "conflict"

    return {
        "available": True,
        "cz_spread": cz_spread,
        "cz_t_stat": cz_t,
        "cz_significant": cz_significant,
        "hxz_spread": hxz_spread,
        "hxz_t_stat": hxz_t,
        "hxz_significant": hxz_significant,
        "sign_agrees": sign_agrees,
        "significance_threshold": SIGNIFICANCE_T_THRESHOLD,
        "verdict": verdict,
    }


def build_evidence_bundle(
    paper_reported: dict[str, Any],
    tracks: dict[str, dict],
    diff_result: ReplicationDiffResult | None = None,
    spec: "ResolvedMethodSpec | None" = None,
    results_dir: "Path | None" = None,
    external_references: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the full deterministic evidence bundle.

    Returns the `derived` / `config_diff` / `gap_decomposition` sections plus
    the newer `spec_quality` / `menu_deviations` /
    `publication_decay` / `robustness_summary` / `shapley_attribution` /
    `paired_tests` / `joint_test` / `gap_closure` / `three_term_identity` /
    `external_performance_comparison` / `paper_verdict_agreement` sections,
    plus `evidence_keys`, the flat whitelist of every citable scalar.

    `spec`, when supplied, is the `ResolvedMethodSpec` this comparison was
    built from -- required for `spec_quality`/`menu_deviations` (both read
    `spec.paper`); omitted, both sections report `available=False` rather
    than raising.

    `results_dir`, when supplied, is the on-disk directory holding each
    track's own `<track>.csv` monthly return series (see
    `write_comparison_summary`, which already computes this path) --
    required for `paired_tests`/`joint_test` (docs/step7-8.md Part V);
    omitted, both report `available=False` rather than raising.

    `external_references`, when supplied, holds the OTHER implementers' OWN
    measured results keyed `"cz"`/`"hxz"` (built by
    `src.infra.reference.external_reference_endpoints`) -- required for
    `three_term_identity`, which is the only section that compares against
    an endpoint this engine did not itself run; omitted, that section
    reports `available=False` per endpoint rather than raising.
    """
    derived: dict[str, Any] = {"tracks": {}}
    for name, payload in tracks.items():
        metrics = payload.get("metrics") or {}
        vs_paper_metrics = _in_sample_metrics(metrics)
        derived["tracks"][name] = {
            "vs_paper": build_track_vs_paper(paper_reported, vs_paper_metrics),
            "n_months": vs_paper_metrics.get("n_months"),
            # ALWAYS the raw long-short mean_return/t_stat -- unlike
            # `vs_paper.track_spread`, which `_resolve_track_spread` swaps
            # for an alpha (alpha_ff3/alpha_capm/alpha_ff5) whenever
            # `paper_reported.return_type` is alpha-based. C&Z's/HXZ's own
            # self-reported numbers (`CZReferenceProfile.mean_return`'s own
            # docstring; `hxz_bridge`'s recomputation from raw
            # decile-portfolio returns) are ALWAYS the raw long-short
            # spread, never an alpha -- so any comparison against them
            # (`external_performance_comparison`) must read THIS pair, not
            # `vs_paper.track_spread`/`track_raw_t_stat`. (`track_raw_
            # t_stat` happens to already be safe -- RunMetrics never stores
            # an alpha's own t-stat -- but `track_spread` is not.)
            "raw_mean_return": _as_float(vs_paper_metrics.get("mean_return")),
            "raw_t_stat": _as_float(vs_paper_metrics.get("t_stat")),
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
    t_channel_decomposition = build_t_channel_decomposition(tracks, baseline)
    spec_quality = build_spec_quality(spec)
    universe_description = build_universe_description(spec)
    menu_deviations = build_menu_deviations(spec, tracks)
    publication_decay = build_publication_decay(tracks)
    robustness_summary = build_robustness_summary(tracks)
    shapley_and_significance = build_shapley_and_significance(tracks, results_dir, baseline)
    gap_closure = {"to_cz": build_gap_closure(derived, shapley_and_significance["paired_tests"])}
    three_term_identity = build_three_term_identities(derived, paper_reported, external_references)
    external_performance_comparison = build_external_performance_comparison(derived, external_references)
    paper_verdict_agreement = build_paper_verdict_agreement(external_references)

    citable = {
        "paper_reported": paper_reported,
        "tracks": tracks,
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
        "t_channel_decomposition": t_channel_decomposition,
        "spec_quality": spec_quality,
        "universe_description": universe_description,
        "menu_deviations": menu_deviations,
        "publication_decay": publication_decay,
        "robustness_summary": robustness_summary,
        "gap_closure": gap_closure,
        "three_term_identity": three_term_identity,
        "external_performance_comparison": external_performance_comparison,
        "paper_verdict_agreement": paper_verdict_agreement,
        **shapley_and_significance,
    }
    return {
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
        "t_channel_decomposition": t_channel_decomposition,
        "spec_quality": spec_quality,
        "universe_description": universe_description,
        "menu_deviations": menu_deviations,
        "publication_decay": publication_decay,
        "robustness_summary": robustness_summary,
        "gap_closure": gap_closure,
        "three_term_identity": three_term_identity,
        "external_performance_comparison": external_performance_comparison,
        "paper_verdict_agreement": paper_verdict_agreement,
        **shapley_and_significance,
        "evidence_keys": flatten(citable),
    }
