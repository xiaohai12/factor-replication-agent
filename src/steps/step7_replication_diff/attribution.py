"""Shapley-value / paired / joint attribution over full-factorial tracks.

Sibling to `bundle.py` -- same discipline (pure arithmetic over already-run
tracks' persisted metrics/return series, no LLM call, every "can't compute"
path returns `{"available": False, "reason": ...}` instead of raising or
silently reporting a zero).

Consumes `RunRecord.switches_flipped` (docs/step7-8.md Part V, Q2 -- derived
by `run_from_matrix` from `ExperimentSpec.resolved_diff`, NOT parsed from a
track's name), so this module never has to know or guess a track's naming
convention. Three independent pieces, each usable without the others:

- `compute_shapley_effects`: order-independent decomposition of the total
  `mean_return` gap across the switches a full-factorial batch varied.
  Requires ALL 2^n corners of the factorial cube to be present (exact
  subset match on `switches_flipped`'s key set), else reports exactly which
  subsets are missing.
- `paired_switch_significance`: for each single-switch track, a paired
  Newey-West test (differenced monthly return series, restricted to the
  months in-sample for both tracks) of whether that switch's effect is
  distinguishable from zero -- not just "the numbers differ".
- `joint_switch_wald_test`: a single joint test across ALL single-switch
  contrasts at once (Wald statistic against a HAC covariance matrix that
  includes the cross-covariances between contrasts, since they share the
  same baseline and heavily overlapping months). Answers "do these switches
  collectively explain more than noise", guarding against picking whichever
  single switch happens to look biggest out of several (docs/step7-8.md
  Part V).
"""

from __future__ import annotations

from itertools import combinations
from math import factorial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# Purely a sanity valve against pathological/malformed data (e.g. a bug
# upstream produces many more distinct `switches_flipped` combinations than
# any real batch should) -- NOT the same knob as step6's
# `MAX_FACTORIAL_SWITCHES` (currently 3), which caps how many switches a
# REAL batch is allowed to vary. Kept independent and deliberately more
# generous so this module doesn't silently need updating every time that
# constant changes.
_MAX_SWITCHES_FOR_SHAPLEY = 6


def _in_sample_mean_return(metrics: dict[str, Any] | None) -> float | None:
    """Prefer `by_sample_period.insamp.mean_monthly_return` (the paper's own
    sample window) over the top-level `mean_return` (this engine's full
    extended history, often decades past the paper's publication year) --
    same preference `bundle.py`'s `_in_sample_metrics` already applies for
    `vs_paper`/`ForestPlot`; falls back to the top-level value when
    `by_sample_period` wasn't configured for this run."""
    metrics = metrics or {}
    insamp = (metrics.get("by_sample_period") or {}).get("insamp") or {}
    return insamp.get("mean_monthly_return", metrics.get("mean_return"))


def compute_shapley_effects(
    tracks: dict[str, dict],
    baseline_track: str = "original_method",
) -> dict[str, Any]:
    """Order-independent decomposition of the `mean_return` gap between
    `baseline_track` and the full-factorial corner that flips every known
    switch, using each track's `switches_flipped` (not its name) to place it
    in the factorial cube.

    Returns `identification_level="controlled"` (see
    `src/infra/models/diagnosis.py`'s `IdentificationLevel` docstring, which
    already reserves this level for exactly this design) only when every
    2^n corner is present; otherwise `available=False` with the specific
    missing subsets, never a partial/best-effort decomposition.
    """
    baseline = tracks.get(baseline_track)
    if baseline is None:
        return {"available": False, "reason": f"baseline track {baseline_track!r} not found"}
    baseline_mean = _in_sample_mean_return(baseline.get("metrics"))
    if baseline_mean is None:
        return {"available": False, "reason": f"baseline track {baseline_track!r} has no mean_return"}

    switch_sets: dict[frozenset, float] = {frozenset(): float(baseline_mean)}
    for name, payload in tracks.items():
        if name == baseline_track:
            continue
        flipped = payload.get("switches_flipped") or {}
        if not flipped:
            continue
        mean_return = _in_sample_mean_return(payload.get("metrics"))
        if mean_return is None:
            continue
        key = frozenset(flipped.keys())
        if key in switch_sets:
            return {
                "available": False,
                "reason": (
                    f"multiple tracks map to the same switch subset {sorted(key)} "
                    f"(at least one is {name!r}) -- ambiguous, refusing to pick one"
                ),
            }
        switch_sets[key] = float(mean_return)

    switches = sorted({s for key in switch_sets for s in key})
    n = len(switches)
    if n == 0:
        return {"available": False, "reason": "no non-baseline track has switches_flipped set"}
    if n > _MAX_SWITCHES_FOR_SHAPLEY:
        return {
            "available": False,
            "reason": f"{n} distinct switches exceeds the sanity cap ({_MAX_SWITCHES_FOR_SHAPLEY})",
        }

    all_subsets = [frozenset(c) for r in range(n + 1) for c in combinations(switches, r)]
    missing = [sorted(s) for s in all_subsets if s not in switch_sets]
    if missing:
        return {
            "available": False,
            "reason": f"incomplete factorial grid, missing subsets: {missing}",
            "switches": switches,
        }

    full = frozenset(switches)
    total_gap = switch_sets[full] - switch_sets[frozenset()]

    shapley: dict[str, float] = {}
    for i in switches:
        others = [s for s in switches if s != i]
        contribution = 0.0
        for r in range(len(others) + 1):
            weight = factorial(r) * factorial(n - r - 1) / factorial(n)
            for combo in combinations(others, r):
                s = frozenset(combo)
                marginal = switch_sets[s | {i}] - switch_sets[s]
                contribution += weight * marginal
        shapley[i] = contribution

    return {
        "available": True,
        "identification_level": "controlled",
        "baseline_track": baseline_track,
        "switches": switches,
        "total_gap": total_gap,
        "shapley_effects": shapley,
        # Exact by construction (Shapley's efficiency property) -- kept as a
        # visible check rather than trusted silently, since a bug in the
        # weight formula would otherwise be invisible.
        "shapley_sum_check": sum(shapley.values()),
    }


def _load_insample_series(
    results_dir: Path, track: str, start: int | None, end: int | None
) -> pd.Series | None:
    """Read `<track>.csv` (written alongside `comparison.json` by
    `write_comparison_summary`'s caller -- every track's own standalone
    script writes its full monthly `yyyymm`/`ls_return` series there) and
    restrict it to the paper's in-sample window. Returns `None` (not an
    empty Series) when the file is missing or malformed, so callers can
    tell "no data" apart from "zero months in range"."""
    path = results_dir / f"{track}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None
    if "yyyymm" not in df.columns or "ls_return" not in df.columns:
        return None
    if start is not None or end is not None:
        year = df["yyyymm"] // 100
        lo = start if start is not None else -np.inf
        hi = end if end is not None else np.inf
        df = df[(year >= lo) & (year <= hi)]
    return df.set_index("yyyymm")["ls_return"]


def _newey_west_var(x: np.ndarray, lags: int) -> float:
    """Same formula as `BacktestExecutor._newey_west_var` -- duplicated
    rather than imported to keep this module's only dependency on the
    engine at zero (it already depends on `tracks`/`results_dir` data the
    engine produced, not on the engine's code)."""
    n = len(x)
    xd = x - x.mean()
    nw = float(np.dot(xd, xd)) / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma = float(np.dot(xd[lag:], xd[:-lag])) / n
        nw += 2.0 * w * gamma
    return max(nw, 0.0)


def _insample_window(tracks: dict[str, dict], baseline_track: str) -> tuple[int | None, int | None]:
    baseline_config = (tracks.get(baseline_track) or {}).get("config") or {}
    return baseline_config.get("sample_start_year"), baseline_config.get("sample_end_year")


def _single_switch_track_map(
    tracks: dict[str, dict], baseline_track: str
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Which track maps to each single-switch subset (a track whose
    `switches_flipped` has exactly one key), and which switches have MORE
    THAN ONE track mapping to them -- e.g. a batch with both `factorial_*`
    (target `HXZ_STANDARD_CONFIG`) and `cz_factorial_*` (target
    `cz_config_override`) auto-attribution tracks can produce two
    different single-switch corners for the same switch name (touching
    the same config key, but flipped to two DIFFERENT target values).

    Ambiguous switches are excluded from the returned mapping rather than
    silently resolved by picking whichever track happens to be iterated
    last (the previous behavior here) -- callers must report them, the
    same way `compute_shapley_effects` already refuses an ambiguous
    subset rather than picking one.
    """
    candidates: dict[str, list[str]] = {}
    for name, payload in tracks.items():
        if name == baseline_track:
            continue
        flipped = payload.get("switches_flipped") or {}
        if len(flipped) == 1:
            candidates.setdefault(next(iter(flipped)), []).append(name)
    resolved = {switch: names[0] for switch, names in candidates.items() if len(names) == 1}
    ambiguous = {switch: names for switch, names in candidates.items() if len(names) > 1}
    return resolved, ambiguous


def paired_switch_significance(
    results_dir: Path,
    tracks: dict[str, dict],
    baseline_track: str = "original_method",
    lags: int = 6,
) -> dict[str, Any]:
    """Paired Newey-West test of `baseline_track` vs each single-switch
    track (any track whose `switches_flipped` has exactly one key --
    covers both `ablation_*` tracks and the single-switch corners of a
    factorial cube), over the months both tracks report in-sample.

    A single switch missing its `.csv` or having no overlapping months is
    reported per-switch as `{"available": False, "reason": ...}` rather
    than dropping it silently or failing the whole call. Same treatment
    for a switch with more than one candidate track (see
    `_single_switch_track_map`) -- reported, not silently resolved.
    """
    start, end = _insample_window(tracks, baseline_track)
    baseline_series = _load_insample_series(results_dir, baseline_track, start, end)
    if baseline_series is None:
        return {
            "available": False,
            "reason": f"no monthly return series for baseline track {baseline_track!r}",
        }

    single_switch_tracks, ambiguous = _single_switch_track_map(tracks, baseline_track)
    per_switch: dict[str, dict[str, Any]] = {}
    for switch, names in ambiguous.items():
        per_switch[switch] = {
            "available": False,
            "reason": f"multiple tracks map to switch {switch!r} ({names!r}) -- ambiguous, refusing to pick one",
        }
    for switch, name in single_switch_tracks.items():
        series = _load_insample_series(results_dir, name, start, end)
        if series is None:
            per_switch[switch] = {
                "available": False,
                "reason": f"no monthly return series for track {name!r}",
            }
            continue
        common = baseline_series.index.intersection(series.index)
        if len(common) == 0:
            per_switch[switch] = {"available": False, "reason": "no overlapping in-sample months"}
            continue
        diff = (baseline_series.loc[common] - series.loc[common]).to_numpy()
        mean_diff = float(diff.mean())
        var = _newey_west_var(diff, lags)
        se = (var / len(diff)) ** 0.5
        per_switch[switch] = {
            "available": True,
            "track": name,
            "mean_diff": mean_diff,
            "t_stat": mean_diff / se if se > 0 else None,
            "n_overlap_months": int(len(common)),
        }

    if not per_switch:
        return {"available": False, "reason": "no single-switch tracks found"}
    return {"available": True, "lags": lags, "per_switch": per_switch}


def joint_switch_wald_test(
    results_dir: Path,
    tracks: dict[str, dict],
    baseline_track: str = "original_method",
    lags: int = 6,
) -> dict[str, Any]:
    """Joint Wald test across ALL single-switch contrasts at once: builds a
    k x n_months matrix of `baseline - single_switch_track` series (one row
    per switch, restricted to the months common to the baseline and EVERY
    single-switch track), estimates the k x k HAC covariance matrix of the
    row means (including cross terms -- the contrasts are correlated since
    they share the same baseline and heavily overlapping months, so they
    must NOT be tested independently), and computes the Wald statistic
    `means' @ inv(cov) @ means ~ chi2(df=k)` under H0: all k contrasts are
    zero.

    This is the gate described in docs/step7-8.md Part V: individual
    `shapley_effects`/`paired_switch_significance` numbers should not be
    read as "this switch matters" unless this joint test itself rejects H0
    -- picking whichever single switch looks biggest out of several,
    without this check, is exactly the multiple-comparisons trap ANOVA's
    omnibus F-test exists to guard against.

    A switch with more than one candidate single-switch track (see
    `_single_switch_track_map`) is EXCLUDED from the test entirely (listed
    in `ambiguous_switches_excluded`) rather than arbitrarily resolved --
    the test still runs on the remaining unambiguous switches if there are
    at least 2 of them.
    """
    start, end = _insample_window(tracks, baseline_track)
    baseline_series = _load_insample_series(results_dir, baseline_track, start, end)
    if baseline_series is None:
        return {
            "available": False,
            "reason": f"no monthly return series for baseline track {baseline_track!r}",
        }

    single_switch_tracks, ambiguous = _single_switch_track_map(tracks, baseline_track)

    switch_series: dict[str, pd.Series] = {}
    for switch, name in single_switch_tracks.items():
        series = _load_insample_series(results_dir, name, start, end)
        if series is not None:
            switch_series[switch] = series

    if len(switch_series) < 2:
        return {
            "available": False,
            "reason": (
                f"need >=2 single-switch tracks with a loadable return series for a joint "
                f"test, found {len(switch_series)}"
            ),
            "ambiguous_switches_excluded": sorted(ambiguous),
        }

    common = baseline_series.index
    for series in switch_series.values():
        common = common.intersection(series.index)
    if len(common) < 2:
        return {
            "available": False,
            "reason": "fewer than 2 overlapping in-sample months across baseline and all switch tracks",
        }

    switches = sorted(switch_series)
    contrasts = np.vstack(
        [(baseline_series.loc[common] - switch_series[s].loc[common]).to_numpy() for s in switches]
    )
    n_months = contrasts.shape[1]
    means = contrasts.mean(axis=1)
    centered = contrasts - means[:, None]
    cov = (centered @ centered.T) / n_months
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1)
        gamma = (centered[:, lag:] @ centered[:, :-lag].T) / n_months
        cov += weight * (gamma + gamma.T)
    cov_of_means = cov / n_months
    try:
        inv_cov = np.linalg.inv(cov_of_means)
    except np.linalg.LinAlgError:
        return {"available": False, "reason": "HAC covariance matrix of the contrast means is singular"}

    wald_stat = float(means @ inv_cov @ means)
    df = len(switches)
    return {
        "available": True,
        "switches": switches,
        "n_overlap_months": int(n_months),
        "lags": lags,
        "wald_stat": wald_stat,
        "df": df,
        "p_value": float(1.0 - stats.chi2.cdf(wald_stat, df=df)),
        "ambiguous_switches_excluded": sorted(ambiguous),
    }


# `cz_`-prefixed vs plain track names is an existing, load-bearing naming
# split (not a fragile ad-hoc parse like the switch-name parsing rejected
# in docs/step7-8.md Q2): `_factorial_track_specs`/`_auto_attribution_specs`
# already deliberately name ①→② tracks `cz_factorial_*`/`cz_ablation_*`
# specifically so they can never collide with the ①→③ `factorial_*`/
# `ablation_*` names (see CHANGELOG's 2026-08-16 "auto-generates cz_factorial_*
# tracks" entry) -- this only reuses that same, already-documented split.
_CZ_LINE_PREFIXES = ("cz_",)


def split_tracks_by_comparison_line(
    tracks: dict[str, dict], baseline_track: str = "original_method"
) -> dict[str, dict[str, dict]]:
    """Split a batch's `tracks` into its (up to two) independent
    auto-attribution comparison lines -- \u2460\u2192\u2461 (`to_cz`, `cz_actual_config`/
    `cz_factorial_*`/`cz_ablation_*`) and \u2460\u2192\u2462 (`to_hxz`, `standardized_hxz`/
    `factorial_*`/`ablation_*`) -- so `compute_shapley_effects`/
    `paired_switch_significance`/`joint_switch_wald_test` are each run
    PER LINE instead of on the whole batch at once.

    This is the fix for a real ambiguity found in production: a batch
    with BOTH lines present can have two DIFFERENT tracks touching the
    same switch name (e.g. `factorial_universe` and `cz_factorial_universe`
    both touch only "universe", flipped to two different target values) --
    splitting by line means the two tracks are never compared in the same
    calculation in the first place, rather than being detected as
    ambiguous and excluded (docs/step7-8.md Part V).

    Each returned sub-dict includes the baseline PLUS only that line's own
    tracks; a track belonging to neither line (e.g. a bridge track, which
    carries no `switches_flipped`) is harmless to include or omit since the
    three consuming functions already skip anything without
    `switches_flipped`, so it is simply left out here.

    A batch with only one line present (the common case: most sessions
    never set `cz_config_override`) returns just that one key -- callers
    must not assume both are always present.
    """
    lines: dict[str, dict[str, dict]] = {}
    baseline = tracks.get(baseline_track)
    for name, payload in tracks.items():
        if name == baseline_track:
            continue
        if not payload.get("switches_flipped"):
            continue
        line = "to_cz" if name.startswith(_CZ_LINE_PREFIXES) else "to_hxz"
        if line not in lines:
            lines[line] = {baseline_track: baseline} if baseline is not None else {}
        lines[line][name] = payload
    return lines
