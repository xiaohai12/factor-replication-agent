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


def build_bridge_comparison(
    tracks: dict[str, dict], paper_reported: dict[str, Any]
) -> dict[str, Any]:
    """Evidence for a `signal_reproducibility` claim: pairs a bridge track
    (the C&Z reference signal run through our identical downstream config,
    `RunRecord.is_bridge_track`) with a companion track, and compares
    whether each independently reproduces the paper's headline sign.
    """
    bridge_name = next((n for n, p in tracks.items() if p.get("is_bridge_track")), None)
    if bridge_name is None:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "no bridge track (cz_bridge) registered for this factor",
        }
    own_name = BASELINE_TRACK if BASELINE_TRACK in tracks else next(
        (n for n in tracks if n != bridge_name), None
    )
    if own_name is None:
        return {
            "available": False,
            "identification_level": MISSING_IDENTIFICATION,
            "reason": "bridge track exists but no companion track to compare it against",
        }
    bridge_vs_paper = build_track_vs_paper(paper_reported, tracks[bridge_name].get("metrics") or {})
    own_vs_paper = build_track_vs_paper(paper_reported, tracks[own_name].get("metrics") or {})
    bridge_reproduces = bridge_vs_paper.get("sign_agrees")
    own_reproduces = own_vs_paper.get("sign_agrees")
    if bridge_reproduces is None or own_reproduces is None:
        agreement = "unavailable"
    elif bridge_reproduces and own_reproduces:
        agreement = "both_reproduce"
    elif bridge_reproduces and not own_reproduces:
        agreement = "only_bridge"
    elif own_reproduces and not bridge_reproduces:
        agreement = "only_own"
    else:
        agreement = "neither"
    return {
        "available": True,
        "bridge_track": bridge_name,
        "own_track": own_name,
        "bridge_reproduces_paper": bridge_reproduces,
        "own_reproduces_paper": own_reproduces,
        "signal_implementation_agreement": agreement,
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


def build_evidence_bundle(
    paper_reported: dict[str, Any],
    tracks: dict[str, dict],
    diff_result: ReplicationDiffResult | None = None,
    spec: "ResolvedMethodSpec | None" = None,
    results_dir: "Path | None" = None,
) -> dict[str, Any]:
    """Assemble the full deterministic evidence bundle.

    Returns the `derived` / `config_diff` / `gap_decomposition` sections plus
    the newer `spec_quality` / `menu_deviations` / `bridge_comparison` /
    `publication_decay` / `robustness_summary` / `shapley_attribution` /
    `paired_tests` / `joint_test` sections, plus `evidence_keys`, the flat
    whitelist of every citable scalar.

    `spec`, when supplied, is the `ResolvedMethodSpec` this comparison was
    built from -- required for `spec_quality`/`menu_deviations` (both read
    `spec.paper`); omitted, both sections report `available=False` rather
    than raising.

    `results_dir`, when supplied, is the on-disk directory holding each
    track's own `<track>.csv` monthly return series (see
    `write_comparison_summary`, which already computes this path) --
    required for `paired_tests`/`joint_test` (docs/step7-8.md Part V);
    omitted, both report `available=False` rather than raising.
    """
    derived: dict[str, Any] = {"tracks": {}}
    for name, payload in tracks.items():
        metrics = payload.get("metrics") or {}
        vs_paper_metrics = _in_sample_metrics(metrics)
        derived["tracks"][name] = {
            "vs_paper": build_track_vs_paper(paper_reported, vs_paper_metrics),
            "n_months": vs_paper_metrics.get("n_months"),
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
    spec_quality = build_spec_quality(spec)
    menu_deviations = build_menu_deviations(spec, tracks)
    bridge_comparison = build_bridge_comparison(tracks, paper_reported)
    publication_decay = build_publication_decay(tracks)
    robustness_summary = build_robustness_summary(tracks)
    shapley_and_significance = build_shapley_and_significance(tracks, results_dir, baseline)

    citable = {
        "paper_reported": paper_reported,
        "tracks": tracks,
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
        "spec_quality": spec_quality,
        "menu_deviations": menu_deviations,
        "bridge_comparison": bridge_comparison,
        "publication_decay": publication_decay,
        "robustness_summary": robustness_summary,
        **shapley_and_significance,
    }
    return {
        "derived": derived,
        "config_diff": config_diff,
        "gap_decomposition": gap_decomposition,
        "spec_quality": spec_quality,
        "menu_deviations": menu_deviations,
        "bridge_comparison": bridge_comparison,
        "publication_decay": publication_decay,
        "robustness_summary": robustness_summary,
        **shapley_and_significance,
        "evidence_keys": flatten(citable),
    }
