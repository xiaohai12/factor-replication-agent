"""LLM replication-diagnosis layer (step 8).

Consumes the deterministic evidence bundle written into
`results/<factor_id>/comparison.json` by step 5/7 and returns a
`ReplicationDiagnosisReport`: structured narrative fragments, each citing keys
from that bundle.

The discipline (Phase E of docs/multi-config-evidence-plan.md) is that the LLM
contributes wording and attribution only:

  * it may cite only keys present in `bundle["evidence_keys"]`;
  * it may not write any digit -- `render.render_markdown` re-inserts every
    figure straight from the bundle;
  * each claim type must cite evidence of the shape declared in
    `CLAIM_EVIDENCE_REQUIREMENTS` (a "significance" claim must cite the
    deterministic significance flag, an attribution claim must cite a measured
    OAT contribution, and so on);
  * the verdict (`overall_tag`) is copied from the bundle, never authored.

Claims failing any of those checks are dropped into `rejected_claims` with a
reason rather than silently discarded, so a reviewer can see what the model
tried to assert.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.infra.models.diagnosis import (
    CAUSAL_TERM_RE,
    CLAIM_EVIDENCE_REQUIREMENTS,
    CLAIM_EVIDENCE_SUBSTRINGS,
    CLAIM_RELATIONS,
    EVIDENCE_STRENGTH_BY_IDENTIFICATION,
    IDENTIFICATION_BY_CLAIM_TYPE,
    DiagnosisClaim,
    RejectedClaim,
    ReplicationDiagnosisReport,
)
from src.steps.step7_replication_diff.bundle import CLOSE_REPLICATION_RATIO_BAND, stage_of


_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "analysis" / "replication_diagnosis.md"
)

DIAGNOSIS_SYSTEM_PROMPT = (
    _PROMPT_PATH.read_text(encoding="utf-8").strip() if _PROMPT_PATH.exists() else ""
)

_DIGIT_RE = re.compile(r"\d")

_TRACK_FROM_VS_PAPER_KEY = re.compile(r"^derived\.tracks\.([^.]+)\.vs_paper\.")
_TRACK_FROM_CONFIG_DIFF_KEY = re.compile(r"^config_diff\.pairs\.([^.]+)\.details\.")
_SWITCH_FROM_CONTRIBUTION_KEY = re.compile(r"\.contributions\.([^.]+)$")

# An ablation_<switch> track's n_months collapsing relative to the baseline
# (e.g. an annual signal losing its forward-fill once rebalance_frequency
# turns monthly) makes its t-stat -- and therefore its OAT contribution --
# incomparable to the baseline's. Reject gap_attribution claims built on such
# a pair rather than let a real, whitelisted contribution value be cited as
# if the two tracks shared a sample.
GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD = 2.0

# Sections of comparison.json the model needs in order to reason. The full file
# also carries `evidence_keys`, which is passed separately as the citation
# whitelist.
_BUNDLE_SECTIONS = (
    "factor_id",
    "paper_ref",
    "paper_reported",
    "tracks",
    "derived",
    "config_diff",
    "gap_decomposition",
)


class ReplicationDiagnoser:
    """Turns a deterministic evidence bundle into evidence-cited narrative."""

    def __init__(self, llm_client: Any, model: str | None = None):
        self.llm_client = llm_client
        self.model = model

    def diagnose(self, bundle: dict[str, Any]) -> ReplicationDiagnosisReport:
        """Produce a validated diagnosis report for one comparison bundle.

        `bundle` is the parsed `comparison.json` (schema v2), which must
        already contain the deterministic `derived` / `config_diff` /
        `gap_decomposition` / `evidence_keys` sections.
        """
        evidence_keys = bundle.get("evidence_keys") or {}
        report = ReplicationDiagnosisReport(
            factor_id=bundle.get("factor_id", "unknown"),
            llm_model=self.model,
            overall_tag=(bundle.get("derived") or {}).get("overall_tag", "inconclusive"),
        )

        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": DIAGNOSIS_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_prompt(bundle)},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        raw_claims = _parse_claims(raw)

        accepted, rejected = validate_claims(raw_claims, evidence_keys)
        report.claims = accepted
        report.rejected_claims = rejected
        return report

    def _build_prompt(self, bundle: dict[str, Any]) -> str:
        facts = {k: bundle[k] for k in _BUNDLE_SECTIONS if k in bundle}
        whitelist = sorted((bundle.get("evidence_keys") or {}).keys())
        return "\n".join(
            [
                "## Deterministic results",
                "```json",
                json.dumps(facts, indent=2, default=str),
                "```",
                "",
                "## Citable evidence keys (the ONLY keys you may reference)",
                "```json",
                json.dumps(whitelist, indent=2),
                "```",
                "",
                "Return the JSON object of claims described in your instructions.",
            ]
        )


def _parse_claims(raw: str) -> list[dict]:
    """Extract the claim list from the model's raw response."""
    from src.infra.llm import extract_json_object_text

    try:
        payload = json.loads(extract_json_object_text(raw))
    except (ValueError, TypeError):
        return []
    if isinstance(payload, dict):
        claims = payload.get("claims", [])
        return [c for c in claims if isinstance(c, dict)]
    return []


def validate_claims(
    raw_claims: list[dict], evidence_keys: dict[str, Any]
) -> tuple[list[DiagnosisClaim], list[RejectedClaim]]:
    """Split proposed claims into accepted and rejected.

    Rejection reasons are deliberately specific so a reviewer can tell an
    honest schema slip apart from the model trying to smuggle in a number, an
    uncited cause, or a relation that contradicts the value it cites.
    """
    accepted: list[DiagnosisClaim] = []
    rejected: list[RejectedClaim] = []

    for raw in raw_claims:
        reason = _rejection_reason(raw, evidence_keys)
        if reason:
            rejected.append(RejectedClaim(reason=reason, claim=raw))
            continue
        enriched = {**raw, **_derive_claim_fields(raw, evidence_keys)}
        try:
            accepted.append(DiagnosisClaim(**enriched))
        except Exception as exc:  # pydantic validation of type/relation enums
            rejected.append(RejectedClaim(reason=f"schema error: {exc}", claim=raw))

    return accepted, rejected


def _rejection_reason(raw: dict, evidence_keys: dict[str, Any]) -> str | None:
    text = raw.get("text") or ""
    claim_type = raw.get("claim_type")
    relation = raw.get("relation")
    keys = raw.get("evidence_keys")

    if not isinstance(text, str):
        return "text must be a string"
    if _DIGIT_RE.search(text):
        return "text contains a digit; numbers must come from the bundle, not the LLM"
    if CAUSAL_TERM_RE.search(text):
        return (
            "text uses causal wording (drives/explains/caused by/...); this pipeline only "
            "produces observational or one-at-a-time evidence, never a controlled design, "
            "so no claim may assert causation"
        )
    if not isinstance(keys, list) or not keys:
        return "no evidence_keys cited"

    unknown = [k for k in keys if k not in evidence_keys]
    if unknown:
        return f"cites keys absent from the evidence whitelist: {unknown}"

    required = CLAIM_EVIDENCE_REQUIREMENTS.get(claim_type)
    if required is None:
        return f"unknown claim_type: {claim_type!r}"
    if not any(k.startswith(p) for k in keys for p in required):
        return f"claim_type {claim_type!r} must cite evidence under one of {list(required)}"

    substrings = CLAIM_EVIDENCE_SUBSTRINGS.get(claim_type)
    if substrings and not any(s in k for k in keys for s in substrings):
        return f"claim_type {claim_type!r} must cite a key containing one of {list(substrings)}"

    allowed_relations = CLAIM_RELATIONS.get(claim_type, ())
    if relation not in allowed_relations:
        return f"claim_type {claim_type!r} must use relation in {list(allowed_relations)}"

    subject_reason = _subject_track_reason(raw, keys)
    if subject_reason:
        return subject_reason

    return _entailment_reason(claim_type, relation, keys, evidence_keys)


def _cited_tracks(keys: list[str]) -> set[str]:
    tracks: set[str] = set()
    for k in keys:
        m = _TRACK_FROM_VS_PAPER_KEY.match(k) or _TRACK_FROM_CONFIG_DIFF_KEY.match(k)
        if m:
            tracks.add(m.group(1))
    return tracks


def _subject_track_reason(raw: dict, keys: list[str]) -> str | None:
    """Reject a claim whose declared subject doesn't match its own citations.

    Prevents citing evidence about one track while naming another as the
    subject -- a subtler version of the same "real key, wrong sentence" risk
    the relation check guards against.
    """
    cited_tracks = _cited_tracks(keys)
    subject_track = raw.get("subject_track")
    if not cited_tracks:
        return None
    if subject_track is None:
        if len(cited_tracks) == 1:
            return None
        return "claim cites more than one track's evidence but names no subject_track"
    if subject_track not in cited_tracks:
        return (
            f"subject_track {subject_track!r} does not match the cited evidence's "
            f"track(s) {sorted(cited_tracks)}"
        )
    return None


def _n_months_mismatch_reason(contribution_key: str, evidence_keys: dict[str, Any]) -> str | None:
    """Block a gap_attribution claim whose two tracks have incomparable sample sizes.

    `contribution_key` looks like `gap_decomposition.contributions.<switch>`.
    The ablation track measuring that switch is `ablation_<switch>` by
    construction (see step7_replication_diff: `switch_name = run.track.replace
    ("ablation_", "")`). If its `n_months` differs from the baseline track's by
    more than `GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD`, the two t-stats being
    differenced were not computed over comparable samples, so the contribution
    number cannot honestly be attributed to the switch alone.
    """
    match = _SWITCH_FROM_CONTRIBUTION_KEY.search(contribution_key)
    if match is None:
        return None
    switch = match.group(1)
    track = f"ablation_{switch}"
    baseline_track = evidence_keys.get("derived.baseline_track")
    if not baseline_track:
        return None
    track_months = evidence_keys.get(f"derived.tracks.{track}.n_months")
    baseline_months = evidence_keys.get(f"derived.tracks.{baseline_track}.n_months")
    if not track_months or not baseline_months:
        return None
    ratio = max(track_months, baseline_months) / min(track_months, baseline_months)
    if ratio > GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD:
        return (
            f"gap_attribution for switch {switch!r} compares {track} "
            f"(n_months={track_months}) against baseline {baseline_track!r} "
            f"(n_months={baseline_months}), a {ratio:.1f}x sample-size mismatch; "
            "the contribution is not a like-for-like comparison and must not be cited "
            "as evidence of the switch's effect (file an evidence_limitation claim instead)"
        )
    return None


def _entailment_reason(
    claim_type: str, relation: str, keys: list[str], evidence_keys: dict[str, Any]
) -> str | None:
    """Reject a claim whose asserted relation contradicts the value it cites.

    This is the check a pure "is the key on the whitelist" validator cannot
    perform: a real, whitelisted `sign_agrees` key does not make "the signs
    are opposite" true if that key's value is `True`.
    """
    if claim_type == "sign_agreement":
        value = next((evidence_keys[k] for k in keys if k.endswith(".sign_agrees")), None)
        if value is None:
            return "sign_agreement must cite a sign_agrees key with a known (non-null) value"
        expected = "agrees" if value else "disagrees"
        if relation != expected:
            return f"relation {relation!r} contradicts the cited sign_agrees value ({value!r})"

    elif claim_type == "significance":
        value = next((evidence_keys[k] for k in keys if k.endswith(".track_significant")), None)
        if value is None:
            return "significance must cite a track_significant key with a known (non-null) value"
        expected = "significant" if value else "insignificant"
        if relation != expected:
            return (
                f"relation {relation!r} contradicts the cited track_significant value ({value!r})"
            )

    elif claim_type == "magnitude_gap":
        ratio = next((evidence_keys[k] for k in keys if k.endswith(".abs_spread_ratio")), None)
        if ratio is None:
            return (
                "magnitude_gap must cite an abs_spread_ratio key so the asserted relation "
                "(larger/smaller/similar) can be checked against a value"
            )
        lo, hi = CLOSE_REPLICATION_RATIO_BAND
        expected = "similar" if lo <= ratio <= hi else ("larger" if ratio > hi else "smaller")
        if relation != expected:
            return f"relation {relation!r} contradicts the cited abs_spread_ratio value ({ratio!r})"

    elif claim_type == "config_divergence":
        has_baseline = any(k.endswith(".baseline_value") for k in keys)
        has_track = any(k.endswith(".track_value") for k in keys)
        if not (has_baseline and has_track):
            return (
                "config_divergence must cite both the .baseline_value and the .track_value "
                "of a changed key, so the difference is shown from both ends"
            )

    elif claim_type == "gap_attribution":
        contribution_key = next((k for k in keys if ".contributions." in k), None)
        if contribution_key is None:
            return "gap_attribution must cite a gap_decomposition.contributions.* value"
        mismatch_reason = _n_months_mismatch_reason(contribution_key, evidence_keys)
        if mismatch_reason:
            return mismatch_reason

    elif claim_type == "evidence_limitation":
        if not any(
            k.endswith((".available", ".reason")) or evidence_keys.get(k) is None for k in keys
        ):
            return (
                "evidence_limitation must cite an availability/reason key or a key whose "
                "value is null (i.e. genuinely missing evidence), not an arbitrary result"
            )

    return None


def _derive_claim_fields(raw: dict, evidence_keys: dict[str, Any]) -> dict[str, Any]:
    """Compute `stage`, `identification_level`, `evidence_strength`, `subject_track`.

    None of these are trusted from the LLM's output -- they are derived here
    from the cited evidence itself, so the model cannot claim a stage or a
    confidence level the evidence doesn't support.
    """
    claim_type = raw["claim_type"]
    keys: list[str] = raw["evidence_keys"]

    cited_tracks = _cited_tracks(keys)
    subject_track = raw.get("subject_track") or (
        next(iter(cited_tracks)) if len(cited_tracks) == 1 else None
    )

    stage = None
    if claim_type == "config_divergence":
        stages = {
            evidence_keys[re.sub(r"\.(baseline_value|track_value)$", ".stage", k)]
            for k in keys
            if k.endswith((".baseline_value", ".track_value"))
        }
        stage = next(iter(stages)) if len(stages) == 1 else None
    elif claim_type == "gap_attribution":
        switches = {k.rsplit(".", 1)[-1] for k in keys if ".contributions." in k}
        stages = {stage_of(s) for s in switches}
        stage = next(iter(stages)) if len(stages) == 1 else None

    identification_level = IDENTIFICATION_BY_CLAIM_TYPE.get(claim_type, "observational")
    if claim_type == "gap_attribution":
        found = evidence_keys.get("gap_decomposition.identification_level")
        identification_level = found or identification_level

    evidence_strength = EVIDENCE_STRENGTH_BY_IDENTIFICATION.get(identification_level, "low")

    return {
        "subject_track": subject_track,
        "stage": stage,
        "identification_level": identification_level,
        "evidence_strength": evidence_strength,
    }
