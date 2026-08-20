"""Deterministic per-comparison-line rollup over already-validated claims,
plus (docs/step7-8.md Part XI) a richer, still 100% template-generated
narrative built DIRECTLY from the bundle's own step7 sections
(`config_diff`/`spec_quality`/`paired_tests`/`joint_test`/
`shapley_attribution`/`publication_decay`/`menu_deviations`) rather than only
from whatever claims the LLM happened to produce and get validated -- this
makes the narrative's depth independent of the LLM's own output quality,
strictly MORE deterministic than the claim-based fields, not less: every
section it reads is pure step7 arithmetic, zero LLM involvement anywhere in
this module.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.infra.models.diagnosis import DiagnosisClaim, DiagnosisSummary
from src.steps.step7_replication_diff.bundle import OAT_INTERACTION_CAVEAT, SIGNIFICANCE_T_THRESHOLD

_SWITCH_FROM_SHAPLEY_OR_PAIRED = re.compile(r"\.(?:shapley_effects|per_switch)\.([^.]+)(?:\.|$)")


def _switch_from_claim(claim: DiagnosisClaim) -> str | None:
    for key in claim.evidence_keys:
        m = _SWITCH_FROM_SHAPLEY_OR_PAIRED.search(key)
        if m:
            return m.group(1)
    return None


# docs/step7-8.md Part VI: the C&Z comparison line's config always lands on
# this exact track name (`cz_profile_to_config_override`'s consumer,
# `MultiTrackController`); a stable, factor-independent fact about how the
# codebase builds this track, not something specific to any one paper.
CZ_ACTUAL_CONFIG_TRACK = "cz_actual_config"

# Config keys `cz_profile_to_config_override` (src/infra/reference)
# unconditionally overrides for EVERY C&Z factor, regardless of what that
# factor's own SignalDoc entry says -- a structural fact about how the
# `cz_actual_config` track itself is assembled, not a per-paper judgement
# call. Mirrors that function's own override dict keys (the unconditional
# ones only; `holding_period_months`/`rebalance_frequency`/`formation_month`/
# `sample_start_year`/`sample_end_year` are profile-dependent and excluded).
CZ_HOUSE_CONVENTION_KEYS = frozenset(
    {
        "weighting_rule",
        "breakpoint_quantiles",
        "breakpoint_source",
        "accounting_lag_months",
        "missing_action",
        "formation_lag_months",
        "universe_filters",
    }
)

# Mirrors step6_dual_track_controller's `_CONFIG_KEY_TO_SWITCH` -- duplicated
# rather than imported, to avoid step7/8 depending on step6 internals. This
# set is stable (the same handful of ablation switches used throughout the
# repo); update both places together if a new switch is ever added there.
# `missing_action` is deliberately absent (2026-08-19): it can never actually
# differ between any two tracks this pipeline produces (see step6's own
# comment on `_ABLATION_SWITCH_TO_CONFIG_KEY`), so it is not a real
# attribution switch.
_CONFIG_KEY_TO_SWITCH_NAME = {
    "breakpoint_source": "breakpoint",
    "weighting_rule": "weighting",
    "accounting_lag_months": "lag",
    "rebalance_frequency": "rebalance",
    "universe_filters": "universe",
}
_SWITCH_NAME_TO_CONFIG_KEY = {v: k for k, v in _CONFIG_KEY_TO_SWITCH_NAME.items()}

# docs/step7-8.md Part XI (readability follow-up) + Part XIII (plain-language
# follow-up): raw config-key/track-name identifiers must never appear in
# reader-facing narrative text -- only in `evidence_keys` (meant for
# citation, not prose). `CONFIG_KEY_LABELS` is the LONG, zero-background
# explanation of what the setting does and, where non-obvious, why it
# exists -- no longer inlined into every sentence (docs/step7-8.md Part
# XVI: repeating a 20-33-word phrase every time a key is mentioned drowned
# out the actual numbers); it is now glossary/tooltip content, surfaced via
# each section's `glossary` field (`_glossary_for_keys`). Every key this
# module can mention needs an entry here so the glossary has something to
# show; a key missing from `_SHORT_KEY_LABELS` falls back to a generic
# underscore->space humanization, so a new config key never crashes, it
# just reads a little more mechanically until both are added.
CONFIG_KEY_LABELS: dict[str, str] = {
    "weighting_rule": "whether bigger companies count for more in the portfolio, or every stock counts equally",
    "breakpoint_quantiles": "how many groups stocks are split into",
    "breakpoint_source": "which group of stocks is used to decide the cutoffs between portfolio groups",
    "accounting_lag_months": (
        "how many months we wait after a company's fiscal year ends before using its "
        "accounting data (real investors can't see the numbers the instant the year ends)"
    ),
    "missing_action": "what to do with a stock that's missing a required data point",
    "formation_lag_months": (
        "how long after picking which stocks go in a portfolio before that portfolio "
        "actually starts trading (a safety delay so the strategy can't accidentally use "
        "information before it was realistically available)"
    ),
    "universe_filters": "which stocks are allowed into consideration at all",
    "rebalance_frequency": "how often the portfolio is updated with new picks",
    "holding_period_months": "how long each portfolio is held before being replaced",
    "formation_month": "which calendar month new portfolios are formed",
    "sample_start_year": "the first year of data used",
    "sample_end_year": "the last year of data used",
}

# Short, plain-language names used INLINE in prose -- the long
# `CONFIG_KEY_LABELS` explanation for the same key is available as a
# glossary/tooltip entry instead (`_glossary_for_keys`), not repeated every
# time the setting is mentioned.
_SHORT_KEY_LABELS: dict[str, str] = {
    "weighting_rule": "portfolio weighting",
    "breakpoint_quantiles": "number of portfolio groups",
    "breakpoint_source": "breakpoint source",
    "accounting_lag_months": "accounting lag",
    "missing_action": "missing-data policy",
    "formation_lag_months": "formation lag",
    "universe_filters": "stock universe",
    "rebalance_frequency": "rebalance frequency",
    "holding_period_months": "holding period",
    "formation_month": "formation month",
    "sample_start_year": "sample start year",
    "sample_end_year": "sample end year",
}

# Friendlier names for the fixed set of tracks this module ever mentions by
# name -- never printed as raw identifiers (docs/step7-8.md Part XI).
TRACK_LABELS: dict[str, str] = {
    "original_method": "our reviewed implementation of the paper's method",
    "standardized_hxz": "the HXZ fully standardized configuration",
    CZ_ACTUAL_CONFIG_TRACK: "C&Z's own independent replication",
}

_OP_LABELS = {
    "not_between": "not between",
    "between": "between",
    "in": "one of",
    "gte": "at least",
    "lte": "at most",
    "gt": "greater than",
    "lt": "less than",
    "eq": "equal to",
}

# docs/step7-8.md Part XIII: plain-language names for the CRSP/Compustat
# field codes universe filters actually reference in this codebase -- not a
# general code encyclopedia, just enough for `_readable_field` to fall back
# to something better than the bare column name.
_FIELD_LABELS = {
    "siccd": "industry classification (SIC code)",
    "shrcd": "share type code",
    "exchcd": "stock exchange code",
}

# Well-known (field, op, value) combinations -> a complete plain-English
# sentence fragment -- FALLBACK ONLY, used when the paper's own extracted
# universe description (`bundle["universe_description"]`, from
# `spec.paper.universe.description`) isn't available (e.g. no resolved spec
# was supplied to `build_evidence_bundle`). Prefer the paper's own words:
# this table can never enumerate every future paper's own filter choices,
# but the paper's own extracted description already generalizes to any
# paper by construction (docs/step7-8.md Part XIII).
_KNOWN_FILTER_DESCRIPTIONS: dict[tuple[str, str, tuple], str] = {
    ("siccd", "not_between", (6000, 6999)): (
        "excludes financial companies such as banks, insurers, and real estate firms "
        "(identified by SIC industry codes 6000-6999)"
    ),
    ("shrcd", "in", (10, 11, 12)): (
        "includes only ordinary common shares (not REITs, ADRs, or other special share types)"
    ),
    ("exchcd", "in", (1, 2, 3)): "includes only stocks listed on the NYSE, AMEX, or Nasdaq exchanges",
}

# docs/step7-8.md Part XIII: C&Z's house universe convention is a FIXED
# constant (`cz_profile_to_config_override` always sets `shrcd in [10, 11,
# 12]` + `exchcd in [1, 2, 3]`, identically for every C&Z factor) -- unlike
# the paper's own universe, it never varies per paper, so a single static
# description is correct here, not something that needs to "scale" to new
# papers the way a per-paper lookup table couldn't.
_CZ_HOUSE_UNIVERSE_DESCRIPTION = (
    "ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own "
    "fixed cross-factor universe convention, applied identically to every C&Z factor "
    "regardless of what any individual paper's own universe description says"
)


def _readable_key(key: str) -> str:
    return _SHORT_KEY_LABELS.get(key, key.replace("_", " "))


def _glossary_for_keys(keys: Iterable[str]) -> dict[str, str]:
    """{short label: long explanation} for every key in `keys` that has a
    `CONFIG_KEY_LABELS` entry -- the tooltip/glossary content for a
    section's short inline mentions (`_readable_key`). Keys without a long
    explanation are omitted rather than duplicating the short label as its
    own definition.
    """
    glossary: dict[str, str] = {}
    for key in keys:
        long_text = CONFIG_KEY_LABELS.get(key)
        if long_text:
            glossary[_readable_key(key)] = long_text
    return glossary


def _readable_track(track: str) -> str:
    return TRACK_LABELS.get(track, track.replace("_", " "))


def _sentence_case(s: str) -> str:
    """Uppercases only the first character -- unlike `str.capitalize()`,
    never lowercases the rest of the string (which would mangle an embedded
    acronym like "NYSE")."""
    return s[:1].upper() + s[1:] if s else s


def _readable_field(field: str) -> str:
    return _FIELD_LABELS.get(field, field.replace("_", " "))


def _readable_filter_value(value: Any) -> str:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return f"{value[0]} to {value[1]}"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _readable_filter(f: dict[str, Any]) -> str:
    """One `{field, op, value}` universe-filter dict -> a plain-English
    sentence fragment. FALLBACK ONLY (see `_KNOWN_FILTER_DESCRIPTIONS`)."""
    field = f.get("field")
    op = f.get("op")
    value = f.get("value")
    lookup_value = tuple(value) if isinstance(value, list) else value
    known = _KNOWN_FILTER_DESCRIPTIONS.get((field, op, lookup_value))
    if known is not None:
        return known
    op_label = _OP_LABELS.get(op, str(op))
    return f"{_readable_field(field)} {op_label} {_readable_filter_value(value)}"


# Menu-governed keys (`STANDARD` in `src/steps/step3_codegen/registry.py`) ->
# raw menu value -> a plain-language name for that actual setting. Read
# ONLY by `_readable_value` to answer the user's follow-up request: the
# `CONFIG_KEY_LABELS` sentence explains what the SETTING is; this table
# supplies what the ACTUAL VALUE on each side of the comparison is, in the
# same plain register (e.g. "value-weighted", not the raw menu token "vw").
_VALUE_LABELS: dict[str, dict[Any, str]] = {
    "weighting_rule": {"vw": "value-weighted", "ew": "equal-weighted"},
    "breakpoint_source": {
        "nyse": "NYSE-only breakpoints",
        "full_sample": "all-exchange breakpoints",
    },
    "missing_action": {
        "drop": "drops the stock for that period",
        "unspecified": "the engine's default (drops the stock for that period)",
    },
    "return_combination_type": {
        "extreme_group_spread": "the top-minus-bottom portfolio spread",
        "single_signal_portfolio_return": "a single portfolio's own return",
        "average_leg_spread": "the average of multiple portfolios per leg",
        "full_portfolio_return": "the whole portfolio's return",
        "unspecified": "the engine's default (top-minus-bottom spread)",
    },
}

# `breakpoint_quantiles` is a raw group count (`registry.py`'s
# `target_sort.group_count`); the common counts have a well-known name.
_QUANTILE_NAMES = {2: "a median split", 3: "terciles", 4: "quartiles", 5: "quintiles", 10: "deciles"}


def _quantile_label(value: Any) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    name = _QUANTILE_NAMES.get(n)
    return f"{n} groups ({name})" if name else f"{n} groups"


def _readable_value(key: str, value: Any) -> str:
    """Turns a raw config value into prose -- special-cased for
    `universe_filters` (a list of `{field, op, value}` filter dicts, which
    would otherwise print as an unreadable Python repr), `breakpoint_
    quantiles` (a raw group count), and menu-governed keys (`_VALUE_LABELS`,
    e.g. raw `"vw"` -> "value-weighted"). This is the FALLBACK path for
    universe_filters -- `_universe_filters_clause` prefers the paper's own
    extracted description when one is available."""
    if key == "universe_filters" and isinstance(value, list):
        parts = [_readable_filter(f) if isinstance(f, dict) else str(f) for f in value]
        return " and ".join(parts) if parts else "no filters"
    if key == "breakpoint_quantiles":
        return _quantile_label(value)
    if key in ("accounting_lag_months", "formation_lag_months"):
        try:
            n = int(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{n} month{'s' if n != 1 else ''}"
    labels = _VALUE_LABELS.get(key)
    if labels is not None and value in labels:
        return labels[value]
    return str(value)


# `universe_filters`' readable value is already a full verb clause ("excludes
# financial companies..."), unlike a plain scalar ("0", "annual") -- so it
# needs "our version {clause}" instead of "we use {value}", or the sentence
# reads as broken English ("we use excludes financial companies").
_CLAUSE_VALUED_KEYS = frozenset({"universe_filters"})


def _value_clause(key: str, value: Any, *, ours: bool) -> str:
    rendered = _readable_value(key, value)
    if key in _CLAUSE_VALUED_KEYS:
        return f"our version {rendered}" if ours else f"C&Z's version {rendered}"
    return f"we use {rendered}" if ours else f"C&Z uses {rendered}"


def _universe_filters_clause(bundle: dict[str, Any], detail: dict[str, Any], *, ours: bool) -> str:
    """docs/step7-8.md Part XIII: prefers the paper's own extracted universe
    description (`bundle["universe_description"]`, straight from the
    MethodSpec's `SourcedValue[str]`) for OUR side -- this generalizes to
    any future paper automatically, since extraction always populates this
    field, unlike a hardcoded per-value lookup table. C&Z's side is a fixed
    constant (`_CZ_HOUSE_UNIVERSE_DESCRIPTION`), never per-paper. Falls back
    to `_value_clause`'s generic filter decoding only when no resolved spec
    was supplied to `build_evidence_bundle` (`universe_description`
    unavailable).
    """
    if not ours:
        return f"C&Z's version is {_CZ_HOUSE_UNIVERSE_DESCRIPTION}"
    paper_text = (bundle.get("universe_description") or {}).get("text")
    if paper_text:
        return f'the paper describes its universe as: "{paper_text}"'
    return _value_clause("universe_filters", detail.get("baseline_value"), ours=True)


def _is_weak_in_paper(config_key: str, spec_quality: dict[str, Any] | None) -> bool:
    weak_fields = (spec_quality or {}).get("weak_fields") or []
    switch_name = _CONFIG_KEY_TO_SWITCH_NAME.get(config_key, config_key)
    needles = {config_key, switch_name}
    return any(
        any(needle in (wf.get("field_path") or "") for needle in needles) for wf in weak_fields
    )


def _divergence_reason(config_key: str, spec_quality: dict[str, Any] | None) -> str:
    """One of `"house_convention"` / `"paper_ambiguous"` / `"unresolved"`
    (docs/step7-8.md Part XI) -- `house_convention` is checked first since
    it's a structural fact about `cz_actual_config`, independent of whether
    `spec_quality` happens to also flag the same field."""
    if config_key in CZ_HOUSE_CONVENTION_KEYS:
        return "house_convention"
    if _is_weak_in_paper(config_key, spec_quality):
        return "paper_ambiguous"
    return "unresolved"


_DIVERGENCE_REASON_TEXT = {
    "house_convention": (
        "is one of the settings C&Z always overrides with their own cross-factor house "
        "convention, regardless of what this paper's own description says -- this divergence "
        "reflects C&Z's own standardization choice, not an ambiguity in the paper or a "
        "likely implementation error"
    ),
    "paper_ambiguous": (
        "was flagged by our own review as weakly specified in the paper -- this divergence "
        "is plausibly explained by the paper itself not stating this clearly enough for "
        "two independent readers to agree"
    ),
    "unresolved": (
        "was not flagged as weak/ambiguous in the paper, and is not one of C&Z's known "
        "house-convention overrides -- this divergence is not explained by either paper "
        "ambiguity or a catalogued C&Z convention, and should be treated as an open "
        "question warranting human review"
    ),
}


def _format_paired_effect(switch_name: str, paired_tests_line: dict[str, Any]) -> str:
    entry = (paired_tests_line.get("per_switch") or {}).get(switch_name)
    if not entry or entry.get("available") is not True:
        return "no paired-test evidence is available for this setting"
    t = entry.get("t_stat")
    mean_diff = entry.get("mean_diff")
    if t is None or mean_diff is None:
        return "no paired-test evidence is available for this setting"
    sig = "statistically significant" if abs(t) >= SIGNIFICANCE_T_THRESHOLD else "not statistically significant"
    sign = "+" if mean_diff >= 0 else ""
    return f"{sign}{mean_diff:.5f}/month (t={t:.2f}), {sig}"


def _cz_level_and_gap_bullets(bundle: dict[str, Any]) -> list[str]:
    """docs/step7-8.md Part XVI: the two bullets a plain config-diff walk
    never gave -- the actual LEVEL on each side (not just per-setting
    deltas), and whether the catalogued differences below actually add up
    to the total gap. Reads `derived.tracks.*.vs_paper` (previously unused
    by this module entirely) and the new `gap_closure.to_cz` (bundle.py).
    Returns `[]` when either track's spread is unresolvable, rather than
    printing a broken sentence.
    """
    derived = bundle.get("derived") or {}
    baseline_track = derived.get("baseline_track")
    tracks_derived = derived.get("tracks") or {}
    baseline_vs_paper = (tracks_derived.get(baseline_track) or {}).get("vs_paper") or {}
    cz_vs_paper = (tracks_derived.get(CZ_ACTUAL_CONFIG_TRACK) or {}).get("vs_paper") or {}
    baseline_spread = baseline_vs_paper.get("track_spread")
    baseline_t = baseline_vs_paper.get("track_raw_t_stat")
    cz_spread = cz_vs_paper.get("track_spread")
    cz_t = cz_vs_paper.get("track_raw_t_stat")
    if None in (baseline_spread, baseline_t, cz_spread, cz_t):
        return []

    bullets = [
        f"Our spread: {baseline_spread:+.5f}/month (t={baseline_t:.2f}). "
        f"C&Z's: {cz_spread:+.5f}/month (t={cz_t:.2f}). "
        f"Total difference: {baseline_spread - cz_spread:+.5f}/month."
    ]

    gap_closure = ((bundle.get("gap_closure") or {}).get("to_cz")) or {}
    if gap_closure.get("available") and gap_closure.get("sum_of_switch_effects") is not None:
        total_gap = gap_closure["total_gap"]
        explained = gap_closure["explained_fraction"]
        residual = gap_closure["residual"]
        if explained is not None:
            bullets.append(
                f"The catalogued setting(s) below have a combined isolated effect of "
                f"{gap_closure['sum_of_switch_effects']:+.5f}/month ({explained * 100:.0f}% of the "
                f"total). The remaining {residual:+.5f}/month ({(1 - explained) * 100:.0f}%) is not "
                f"produced by any of them -- {OAT_INTERACTION_CAVEAT}."
            )
        else:
            bullets.append(
                f"The catalogued setting(s) below have a combined isolated effect of "
                f"{gap_closure['sum_of_switch_effects']:+.5f}/month; the total gap is "
                f"{total_gap:+.5f}/month, so a residual of {residual:+.5f}/month is not produced "
                f"by any of them -- {OAT_INTERACTION_CAVEAT}."
            )
    return bullets


def _build_cz_summary(bundle: dict[str, Any]) -> tuple[str, list[str], str, dict[str, str]]:
    """docs/step7-8.md Part XII: `(headline, details, footnote, glossary)` for
    the PRIMARY comparison -- the project's core research question (AGENTS.md)
    is inter-implementer agreement between our agent and C&Z, not sensitivity
    to implementation choices in general. `headline` names the comparison
    target itself ("Compared with C&Z's independent replication...") so no
    separate "vs. C&Z" title is needed. One `details` entry per diverging
    config key, each with WHY it diverged (`_divergence_reason`) and its
    effect size/significance; `footnote` carries joint-test availability;
    `glossary` is the tooltip text for every setting mentioned by short name.
    """
    pairs = (bundle.get("config_diff") or {}).get("pairs") or {}
    cz_pair = pairs.get(CZ_ACTUAL_CONFIG_TRACK)
    if not cz_pair or not cz_pair.get("changed_keys"):
        return "", [], "", {}

    spec_quality = bundle.get("spec_quality")
    paired_tests_line = (bundle.get("paired_tests") or {}).get("to_cz") or {}
    publication_decay = (bundle.get("publication_decay") or {}).get("tracks") or {}
    detail_map = cz_pair.get("details") or {}
    # Most informative first: by |t-stat| of the setting's own isolated
    # effect, descending; a setting with no paired-test evidence at all
    # (t unknown) sorts last rather than in its arbitrary config-key order.
    def _abs_t(key: str) -> float:
        switch_name = _CONFIG_KEY_TO_SWITCH_NAME.get(key, key)
        entry = (paired_tests_line.get("per_switch") or {}).get(switch_name)
        t = entry.get("t_stat") if entry and entry.get("available") is True else None
        return abs(t) if t is not None else -1.0
    changed_keys = sorted(cz_pair.get("changed_keys") or [], key=_abs_t, reverse=True)

    details: list[str] = _cz_level_and_gap_bullets(bundle)
    all_reasons: set[str] = set()
    for key in changed_keys:
        detail = detail_map.get(key) or {}
        reason = _divergence_reason(key, spec_quality)
        all_reasons.add(reason)
        switch_name = _CONFIG_KEY_TO_SWITCH_NAME.get(key, key)
        effect_text = _format_paired_effect(switch_name, paired_tests_line)
        if key == "universe_filters":
            ours_clause = _universe_filters_clause(bundle, detail, ours=True)
            theirs_clause = _universe_filters_clause(bundle, detail, ours=False)
        else:
            ours_clause = _value_clause(key, detail.get("baseline_value"), ours=True)
            theirs_clause = _value_clause(key, detail.get("track_value"), ours=False)
        entry = (
            f"{_sentence_case(_readable_key(key))}: {ours_clause}, {theirs_clause} -- "
            f"{_DIVERGENCE_REASON_TEXT[reason]}. Effect: {effect_text}."
        )
        # Cross-line callout: does the SAME choice, examined on the HXZ line,
        # survive post-publication (docs/step7-8.md Part VII example 6)? --
        # only worth reporting when THIS switch's own effect is itself
        # statistically significant; a decay/no-decay verdict on a noise-level
        # effect (e.g. t=0.56) has nothing to say.
        this_switch_t = (paired_tests_line.get("per_switch") or {}).get(switch_name, {}).get("t_stat")
        this_switch_significant = this_switch_t is not None and abs(this_switch_t) >= SIGNIFICANCE_T_THRESHOLD
        hxz_track = f"factorial_{switch_name}"
        decay_entry = publication_decay.get(hxz_track)
        if this_switch_significant and decay_entry is not None and decay_entry.get("decayed") is not None:
            stability = "does NOT decay" if not decay_entry["decayed"] else "DOES decay"
            entry += (
                f" On the standardized-HXZ comparison, this same setting's isolated effect "
                f"{stability} after publication."
            )
        details.append(entry)

    joint_test_line = (bundle.get("joint_test") or {}).get("to_cz") or {}
    any_individually_significant = any(
        (paired_tests_line.get("per_switch") or {}).get(_CONFIG_KEY_TO_SWITCH_NAME.get(k, k), {}).get(
            "t_stat"
        )
        is not None
        and abs((paired_tests_line["per_switch"][_CONFIG_KEY_TO_SWITCH_NAME.get(k, k)])["t_stat"])
        >= SIGNIFICANCE_T_THRESHOLD
        for k in changed_keys
        if _CONFIG_KEY_TO_SWITCH_NAME.get(k, k) in (paired_tests_line.get("per_switch") or {})
    )

    explained = all_reasons <= {"house_convention", "paper_ambiguous"}
    if explained and not any_individually_significant:
        headline = (
            "Compared with C&Z's independent replication of this paper, the only differences "
            "are explained by paper ambiguity or C&Z's own conventions, and none has a "
            "statistically significant effect."
        )
    elif explained:
        headline = (
            "Compared with C&Z's independent replication of this paper, the differences are "
            "explained by paper ambiguity or C&Z's own conventions, but at least one has a "
            "statistically significant effect."
        )
    else:
        headline = (
            "Compared with C&Z's independent replication of this paper, at least one "
            "difference is NOT explained by paper ambiguity or a catalogued C&Z convention "
            "-- this warrants human review rather than being written off as expected variation."
        )

    footnote = (
        f"Joint test unavailable on this line: {joint_test_line.get('reason', 'n/a')}."
        if joint_test_line.get("available") is False
        else ""
    )
    footnote = (
        f"{footnote} " if footnote else ""
    ) + (
        "No C&Z signal bridge track was run for this factor, so any residual gap above cannot "
        "be attributed between a difference in how the signal formula itself was read and a "
        "difference in data or sample -- this report cannot separate the two."
    )
    glossary = _glossary_for_keys(changed_keys)
    return headline, details, footnote, glossary


def _build_sensitivity_summary(line: str, bundle: dict[str, Any]) -> tuple[str, list[str], str, dict[str, str]]:
    """docs/step7-8.md Part XII: `(headline, details, footnote, glossary)`
    for a SUPPORTING comparison line (in practice, `to_hxz`) -- how
    sensitive the result is to implementation choices in general, not why
    two implementers disagreed (that question is `to_cz`-specific,
    `_build_cz_summary`). Folded into the "robustness" section
    (`_build_robustness_summary`) rather than shown as its own top-level
    card.
    """
    shapley = (bundle.get("shapley_attribution") or {}).get(line) or {}
    if shapley.get("available") is not True:
        return "", [], "", {}
    effects: dict[str, float] = shapley.get("shapley_effects") or {}
    total_gap = shapley.get("total_gap")
    paired_tests_line = (bundle.get("paired_tests") or {}).get(line) or {}
    joint_test_line = (bundle.get("joint_test") or {}).get(line) or {}

    ordered = sorted(effects.items(), key=lambda kv: abs(kv[1]), reverse=True)
    joint_available = joint_test_line.get("available") is True
    joint_p = joint_test_line.get("p_value")
    joint_significant = joint_available and joint_p is not None and joint_p < 0.05

    magnitude = f"{abs(total_gap):.4f}/month" if total_gap is not None else "an unmeasured amount"
    confirm = (
        f", confirmed by a joint significance test (p={joint_p:.2g})"
        if joint_significant
        else ", though a joint test does not confirm this" if joint_available
        else ""
    )
    headline = (
        f"Compared with the fully standardized HXZ protocol, our implementation's effect "
        f"differs by {magnitude}{confirm}."
    )

    # Per-switch contribution SHARES are only reported when the joint test
    # actually confirms the total change is more than noise -- a "158% of
    # the change" figure is false precision when the change itself isn't
    # statistically distinguishable from zero (docs/step7-8.md Part XVI).
    show_shares = joint_significant
    details = []
    for key, effect in ordered:
        if show_shares and total_gap:
            pct_text = f"accounts for {(effect / total_gap) * 100:.0f}% of the change"
        else:
            pct_text = "contribution share not shown (the total change is not statistically confirmed)"
        label = _readable_key(_SWITCH_NAME_TO_CONFIG_KEY.get(key, key))
        details.append(f"{_sentence_case(label)}: {pct_text}. Effect: {_format_paired_effect(key, paired_tests_line)}.")

    footnote = "Used as sensitivity context, not itself the reproducibility question."
    if not joint_available:
        footnote += f" Joint test unavailable: {joint_test_line.get('reason', 'n/a')}."
    glossary = _glossary_for_keys(_SWITCH_NAME_TO_CONFIG_KEY.get(k, k) for k in effects)
    return headline, details, footnote, glossary


def _build_robustness_summary(bundle: dict[str, Any]) -> tuple[str, list[str], str, dict[str, str]]:
    """docs/step7-8.md Part XVI: how STABLE the result is under reasonable
    implementation variation in general -- NOT why two implementers
    disagreed (that's `_build_cz_summary`'s job, the separate "vs_cz"
    section). Folds together `robustness_summary` (ablation sign/
    significance flips), the fully standardized HXZ protocol as one NAMED
    case within this section (previously its own separate top-level card),
    the baseline's own in-sample-vs-post-publication decay, and whether a
    t-stat gap vs the standardized protocol is a mean-return story or a
    volatility/sample-size one. Populated independently of whether the HXZ
    factorial grid exists at all -- this section is never empty just
    because no Shapley grid was run, as long as ANY of these has evidence.
    """
    headline_parts: list[str] = []
    details: list[str] = []
    footnotes: list[str] = []
    glossary: dict[str, str] = {}

    robustness = bundle.get("robustness_summary") or {}
    if robustness.get("available"):
        verdict = "the result is stable" if robustness.get("robust") else "the result is NOT fully stable"
        headline_parts.append(
            f"Across {robustness['n_ablation_tracks']} alternative implementation choice(s), "
            f"{verdict}: {robustness['sign_flips']} sign flip(s), "
            f"{robustness['significance_flips']} significance-threshold crossing(s) "
            f"(t-stat range {robustness['t_stat_range']:.2f})."
        )

    hxz_headline, hxz_details, hxz_footnote, hxz_glossary = _build_sensitivity_summary("to_hxz", bundle)
    if hxz_headline:
        lead = hxz_headline[0].lower() + hxz_headline[1:]
        details.append(f"Standardized HXZ protocol (a named case, not a competing replication): {lead}")
        details.extend(hxz_details)
        if hxz_footnote:
            footnotes.append(hxz_footnote)
        glossary.update(hxz_glossary)

    derived = bundle.get("derived") or {}
    baseline_track = derived.get("baseline_track")
    decay = ((bundle.get("publication_decay") or {}).get("tracks") or {}).get(baseline_track)
    if decay is not None and decay.get("decayed") is not None:
        if not decay.get("insamp_significant"):
            details.append(
                "Post-publication decay is not identifiable here: our own replication was "
                "already not statistically significant in-sample."
            )
        else:
            verdict = "DOES decay after publication" if decay["decayed"] else "does NOT decay after publication"
            details.append(
                f"Our own replication {verdict} (in-sample t={decay['insamp_t_stat']:.2f}, "
                f"post-publication t={decay['postpub_t_stat']:.2f})."
            )

    t_channel = ((bundle.get("t_channel_decomposition") or {}).get("tracks") or {}).get("standardized_hxz")
    if t_channel is not None and not t_channel.get("degenerate") and t_channel.get("channels"):
        channels = t_channel["channels"]
        dominant = max(channels, key=lambda k: abs(channels[k]))
        label = {
            "mean_return": "the mean-return channel",
            "volatility": "the volatility channel",
            "sample_size": "the sample-size channel",
        }.get(dominant, dominant)
        details.append(
            f"The t-stat gap vs the standardized HXZ protocol is driven mainly by {label}, "
            "not the others -- so it is not simply an artefact of a misaligned sample window."
        )

    if not headline_parts and not details:
        return "", [], "", {}

    headline = " ".join(headline_parts) if headline_parts else "Sensitivity/stability evidence for this replication:"
    footnote = " ".join(footnotes) if footnotes else "Used as sensitivity context, not itself the reproducibility question."
    return headline, details, footnote, glossary


def _dispatch_summary_parts(line: str | None, bundle: dict[str, Any]) -> tuple[str, list[str], str, dict[str, str]]:
    if line == "to_cz":
        return _build_cz_summary(bundle)
    if line == "to_hxz":
        return _build_robustness_summary(bundle)
    if line is not None:
        return _build_sensitivity_summary(line, bundle)
    return "", [], "", {}


#: Reader-facing name per `three_term_identity` reference key and per named
#: component. The component labels deliberately avoid "cause"/"driver"
#: wording -- this section is an accounting split, not an experiment.
_THREE_TERM_REFERENCE_LABELS = {
    "cz": "C&Z's own published result",
    "hxz": "HXZ's own published result",
}

_THREE_TERM_COMPONENT_LABELS = {
    "signal_and_environment": "how the signal itself was computed (plus data-vintage and engine differences)",
    "config": "portfolio-construction settings alone",
    "agent_replication_residual": "our own run's distance from the paper's number",
}


def build_three_term_summaries(bundle: dict[str, Any]) -> list[DiagnosisSummary]:
    """docs/paper-outline.md C1, rendered for a reader: how far each external
    implementer's published number sits from the PAPER's own reported number,
    and how that distance splits between the signal, the settings, and our own
    replication error.

    Built straight from `bundle["three_term_identity"]` like every other
    builder here -- no LLM involvement, and produced even when the LLM made
    zero claims about it, so a section this project's core argument depends on
    can never silently go missing.

    An endpoint the bundle could not resolve is skipped entirely rather than
    rendered as a zero gap.
    """
    sections = bundle.get("three_term_identity") or {}
    summaries: list[DiagnosisSummary] = []
    for reference, section in sorted(sections.items()):
        if not section.get("available"):
            continue
        terms = section.get("terms") or {}
        reference_label = _THREE_TERM_REFERENCE_LABELS.get(reference, reference)
        largest = section.get("largest_term")

        details = [
            f"{_sentence_case(_THREE_TERM_COMPONENT_LABELS.get(name, name))}: {value:+.4f} per month"
            for name, value in sorted(terms.items(), key=lambda kv: abs(kv[1]), reverse=True)
        ]
        if largest:
            details.append(
                f"The largest single component is {_THREE_TERM_COMPONENT_LABELS.get(largest, largest)}. "
                "This is an exact arithmetic split of the total distance, not a controlled experiment: "
                "it shows where the distance sits, not what caused it."
            )
        window = section.get("window_basis") or {}
        sensitivity = window.get("window_sensitivity_spread")
        if sensitivity is not None:
            details.append(
                f"Recomputing {reference_label} over its own paper's sample window instead of this "
                f"paper's moves it by {sensitivity:+.4f} per month -- a measure of how much the "
                "choice of sample window alone matters here."
            )

        summaries.append(
            DiagnosisSummary(
                comparison_line=reference,
                section="gap_split",
                overall_tag=(bundle.get("derived") or {}).get("overall_tag", "inconclusive"),
                headline=(
                    f"{reference_label} differs from the paper's own reported spread by "
                    f"{section.get('total_gap', 0.0):+.4f} per month."
                ),
                details=details,
                footnote=(
                    "The three components are not equally clean: only the settings component holds the "
                    "signal fixed on both sides. The first also absorbs data-vintage and engine "
                    "differences, and the last is our own replication error rather than anything the "
                    "paper left ambiguous. The four numbers being compared also do not share a common "
                    "sample window or estimator."
                ),
            )
        )
    return summaries


def build_spec_quality_summary(bundle: dict[str, Any]) -> DiagnosisSummary:
    """docs/step7-8.md Part XVI: how clearly the paper specified its own
    method -- one bullet per field `spec_quality.weak_fields` flagged,
    quoting the review's OWN reason (not just a pass/fail boolean, which
    gives a reader no way to judge whether the ambiguity call was
    reasonable), plus any setting the paper required that the engine's menu
    cannot express at all (`menu_deviations.unsupported_paper_fields`).
    """
    weak_fields = ((bundle.get("spec_quality") or {}).get("weak_fields")) or []
    unsupported = ((bundle.get("menu_deviations") or {}).get("unsupported_paper_fields")) or []
    if not weak_fields and not unsupported:
        return DiagnosisSummary(section="spec_quality")

    details: list[str] = []
    for wf in weak_fields:
        field_path = wf.get("field_path", "")
        reason = wf.get("reason", "")
        disposition = wf.get("disposition", "")
        entry = f"{_sentence_case(_readable_key(field_path))}: {reason}"
        if disposition:
            entry += f" (resolved as: {disposition})"
        details.append(entry + ".")
    for u in unsupported:
        field_path = u.get("field_path", "")
        value = u.get("unsupported_value")
        details.append(
            f"{_sentence_case(_readable_key(field_path))}: the paper's stated value "
            f"({value!r}) could not be expressed by the engine's fixed menu; clamped to "
            "the menu default rather than code-generated."
        )

    headline = (
        f"{len(weak_fields)} setting(s) were flagged as weakly specified by the paper, and "
        f"{len(unsupported)} setting(s) the paper required fall outside the engine's menu."
        if weak_fields or unsupported
        else ""
    )
    glossary = _glossary_for_keys(
        [wf.get("field_path", "") for wf in weak_fields] + [u.get("field_path", "") for u in unsupported]
    )
    return DiagnosisSummary(section="spec_quality", headline=headline, details=details, glossary=glossary)


def build_vs_paper_summary(bundle: dict[str, Any]) -> "VsPaperSummary":
    """docs/step7-8.md Part XII: the baseline track vs the paper's own
    reported number, with the honest caveat that part of any magnitude gap
    may come from config fields the paper never specified at ALL (silently
    filled by an engine default, `menu_deviations.clamped_by_track`) rather
    than from how the paper's own STATED method was implemented -- this
    comparison structurally cannot separate the two.
    """
    from src.infra.models.diagnosis import VsPaperSummary

    derived = bundle.get("derived") or {}
    baseline_track = derived.get("baseline_track")
    if not baseline_track:
        return VsPaperSummary()
    vs_paper = (derived.get("tracks") or {}).get(baseline_track, {}).get("vs_paper") or {}
    sign_agrees = vs_paper.get("sign_agrees")
    ratio = vs_paper.get("abs_spread_ratio")
    if sign_agrees is None:
        return VsPaperSummary()

    sign_text = "agrees in sign with" if sign_agrees else "has the OPPOSITE sign from"
    ratio_text = f"{ratio:.2f}x larger" if ratio is not None and ratio >= 1 else (
        f"{ratio:.2f}x the paper's own reported spread" if ratio is not None else "an unknown ratio to the paper's own spread"
    )
    headline = f"Compared with the paper's own reported result, {_readable_track(baseline_track)} {sign_text} it; its magnitude is {ratio_text}."

    clamped = ((bundle.get("menu_deviations") or {}).get("clamped_by_track") or {}).get(baseline_track) or []
    paper_silent = [c for c in clamped if c.get("paper_value") in (None, "unspecified")]
    details = []
    footnote = ""
    if paper_silent:
        keys = ", ".join(_readable_key(c["config_key"]) for c in paper_silent)
        details.append(
            f"{len(paper_silent)} setting(s) were never specified by the paper at all and "
            f"were filled by an engine default: {keys}."
        )
        footnote = (
            "Part of this magnitude gap may reflect these silent defaults rather than a "
            "difference in how the paper's stated method was implemented -- this comparison "
            "cannot separate the two."
        )
    glossary = _glossary_for_keys(c["config_key"] for c in paper_silent)
    return VsPaperSummary(headline=headline, details=details, footnote=footnote, glossary=glossary)


def _deterministic_dominant_switch(bundle: dict[str, Any], line: str | None) -> str | None:
    """The single largest-\\|t\\| switch on this comparison line, per the SAME
    deterministic paired-test evidence `_build_cz_summary`/
    `_build_sensitivity_summary` already rank their own bullets by -- used
    only to flag when the LLM's `dominant_switches` pick disagrees with it,
    never to restate it (that would just repeat the per-setting bullet)."""
    if line is None:
        return None
    per_switch = ((bundle.get("paired_tests") or {}).get(line) or {}).get("per_switch") or {}
    ranked = [
        (switch, abs(entry["t_stat"]))
        for switch, entry in per_switch.items()
        if entry.get("available") is True and entry.get("t_stat") is not None
    ]
    if not ranked:
        return None
    return max(ranked, key=lambda kv: kv[1])[0]


def _fold_claim_evidence_into_details(
    details: list[str],
    bundle: dict[str, Any],
    line: str | None,
    dominant_switches: list[str],
) -> list[str]:
    """docs/step7-8.md Part XVI: `dominant_switches`/`per_switch_summary`/
    `joint_supported` (LLM-claim-derived) are kept as their own
    `DiagnosisSummary` fields for evidence_keys/citation, but are no longer
    restated as prose here -- they only repeated numbers the deterministic
    per-setting bullets (their own "Effect: ..." text) and the joint-test
    headline/footnote already show, and the restatement's "LLM-reviewed"
    phrasing implied the LLM was judging significance, which it never does
    (AGENTS.md: the LLM never decides a number that enters a conclusion).
    The only prose added here is a CONFLICT flag: if the LLM's own
    dominant-driver pick disagrees with the single largest-\\|t\\| switch on
    this line, that disagreement is worth a reader's attention; agreement
    is not, since it would just repeat the per-setting bullet above it.
    """
    if not dominant_switches:
        return details
    llm_pick = dominant_switches[0]
    deterministic_pick = _deterministic_dominant_switch(bundle, line)
    if deterministic_pick is None or llm_pick == deterministic_pick:
        return details
    llm_label = _readable_key(_SWITCH_NAME_TO_CONFIG_KEY.get(llm_pick, llm_pick))
    det_label = _readable_key(_SWITCH_NAME_TO_CONFIG_KEY.get(deterministic_pick, deterministic_pick))
    return details + [
        f'Note: the LLM flagged "{llm_label}" as the dominant driver, which differs from the '
        f'setting with the largest measured effect on this line ("{det_label}") -- worth a '
        "second look."
    ]


def _section_for_line(line: str | None) -> str | None:
    """docs/step7-8.md Part XVI: which of the reader-facing sections a
    per-line `DiagnosisSummary` belongs to. `to_cz` is the project's core
    research question (AGENTS.md); `to_hxz` and any other named line are
    sensitivity/stability evidence, folded into the same "robustness"
    bucket the frontend groups together. `None` (the legacy claim-only
    overflow entry) has no section of its own -- it predates this grouping
    and is not one of the sections.
    """
    if line == "to_cz":
        return "vs_cz"
    if line is not None:
        return "robustness"
    return None


#: `three_term_identity` nests by external reference, not by track line, so
#: these keys must never be treated as comparison lines by the per-line loop
#: below -- they get their own `build_three_term_summaries` section instead.
_THREE_TERM_REFERENCE_KEYS = frozenset(_THREE_TERM_REFERENCE_LABELS)


def build_deterministic_summary(
    claims: list[DiagnosisClaim], bundle: dict[str, Any]
) -> list[DiagnosisSummary]:
    """One `DiagnosisSummary` per comparison line present among `claims`
    (`[None]` -- a single line-less summary -- when no per_switch/joint_gate
    claim was made at all, e.g. a batch with only vs_paper/auxiliary claims).
    """
    overall_tag = (bundle.get("derived") or {}).get("overall_tag", "inconclusive")
    shapley = bundle.get("shapley_attribution") or {}

    lines = {
        c.comparison_line
        for c in claims
        if c.comparison_line and c.comparison_line not in _THREE_TERM_REFERENCE_KEYS
    }
    # Narratives are built straight from `bundle` (see module docstring), so
    # every line the bundle itself computed evidence for must get a summary
    # even when the LLM produced zero claims about it -- not just the lines
    # claims happen to mention. `to_cz` doubly-so: it's the project's core
    # research question (AGENTS.md), never allowed to go missing just because
    # `config_diff` (not one of these three line-nested sections) is where
    # its only evidence lives for a single-choice line with no Shapley grid.
    for section_name in ("shapley_attribution", "paired_tests", "joint_test"):
        section = bundle.get(section_name) or {}
        if "available" not in section:  # nested-by-line shape, not the flat "no lines" shape
            lines.update(section.keys())
    if bundle.get("config_diff", {}).get("pairs", {}).get(CZ_ACTUAL_CONFIG_TRACK):
        lines.add("to_cz")
    ordered_lines = sorted(lines)
    # A line-less claim (e.g. `sign_agreement`, which is track-scoped, not
    # line-scoped) always needs its own `comparison_line=None` summary too,
    # even when named lines also exist -- and when NO named lines exist at
    # all (pre-Part-XI batches with neither Shapley/paired/joint data nor a
    # cz_actual_config pair), `None` is the only summary produced.
    if not ordered_lines or any(c.comparison_line is None for c in claims):
        ordered_lines = [None] + ordered_lines
    summaries: list[DiagnosisSummary] = []

    for line in ordered_lines:
        line_claims = [c for c in claims if c.comparison_line == line]

        per_switch_summary: dict[str, str] = {}
        for c in line_claims:
            if c.claim_type != "switch_significance":
                continue
            switch = _switch_from_claim(c)
            if switch:
                per_switch_summary[switch] = c.relation

        joint_supported: bool | None = None
        for c in line_claims:
            if c.claim_type == "joint_attribution_support":
                joint_supported = c.relation == "significant"

        dominant_switches = [
            switch
            for c in line_claims
            if c.claim_type == "gap_attribution_shapley"
            and c.relation == "associated_change"
            and c.evidence_strength != "low"
            and (switch := _switch_from_claim(c))
        ]
        line_effects = ((shapley.get(line) or {}).get("shapley_effects") or {}) if line else {}
        dominant_switches.sort(key=lambda s: abs(line_effects.get(s, 0.0)), reverse=True)

        headline, details, footnote, glossary = _dispatch_summary_parts(line, bundle)
        details = _fold_claim_evidence_into_details(details, bundle, line, dominant_switches)

        summaries.append(
            DiagnosisSummary(
                comparison_line=line,
                section=_section_for_line(line),
                overall_tag=overall_tag,
                per_switch_summary=per_switch_summary,
                joint_supported=joint_supported,
                dominant_switches=dominant_switches,
                headline=headline,
                details=details,
                footnote=footnote,
                glossary=glossary,
            )
        )

    return summaries + build_three_term_summaries(bundle)
