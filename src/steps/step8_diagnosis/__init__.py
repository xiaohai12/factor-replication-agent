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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.infra.models.diagnosis import (
    ANALYSIS_STAGE_BY_CLAIM_TYPE,
    CAUSAL_TERM_RE,
    CLAIM_EVIDENCE_REQUIREMENTS,
    CLAIM_EVIDENCE_SUBSTRINGS,
    CLAIM_RELATIONS,
    EVIDENCE_STRENGTH_BY_IDENTIFICATION,
    IDENTIFICATION_BY_CLAIM_TYPE,
    REASON_LAYER_BY_CLAIM_TYPE,
    DiagnosisClaim,
    RejectedClaim,
    ReplicationDiagnosisReport,
)
from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.tooling import (
    Tool,
    ToolContext,
    ToolPolicy,
    ToolResult,
    ToolRunner,
    render_tool_catalog,
    render_tool_results,
    splice_tool_catalog,
)
from src.steps.step7_replication_diff.bundle import (
    CLOSE_REPLICATION_RATIO_BAND,
    SIGNIFICANCE_T_THRESHOLD,
    stage_of,
)
from src.steps.step8_diagnosis.summary import build_deterministic_summary, build_spec_quality_summary, build_vs_paper_summary


_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "analysis" / "replication_diagnosis.md"
)

DIAGNOSIS_SYSTEM_PROMPT = (
    _PROMPT_PATH.read_text(encoding="utf-8").strip() if _PROMPT_PATH.exists() else ""
)

_DIGIT_RE = re.compile(r"\d")

_TRACK_FROM_VS_PAPER_KEY = re.compile(r"^derived\.tracks\.([^.]+)\.vs_paper\.")
_TRACK_FROM_CONFIG_DIFF_KEY = re.compile(r"^config_diff\.pairs\.([^.]+)\.details\.")
_TRACK_FROM_PUBLICATION_DECAY_KEY = re.compile(r"^publication_decay\.tracks\.([^.]+)\.")
_SWITCH_FROM_CONTRIBUTION_KEY = re.compile(r"\.contributions\.([^.]+)$")

# docs/step7-8.md Part VIII §8.1: `shapley_attribution`/`paired_tests`/`joint_test`
# are nested one level by comparison line (`to_hxz`/`to_cz`) when more than one
# line's tracks are present in the same batch -- this extracts that segment,
# mirroring `_TRACK_FROM_*_KEY` above for `comparison_line` instead of `subject_track`.
# `three_term_identity` nests the same way, keyed by external reference
# (`cz`/`hxz`) rather than by track line.
_LINE_FROM_NESTED_KEY = re.compile(
    r"^(?:shapley_attribution|paired_tests|joint_test|three_term_identity)\.([^.]+)\."
)
_SWITCH_FROM_SHAPLEY_KEY = re.compile(r"\.shapley_effects\.([^.]+)$")

# Bounded rounds for the claim-rejection retry loop (docs/tools-plus-llm-plan.md
# §4.3): round 1 drafts claims from scratch; any additional round resubmits
# ONLY the rejected ones with their rejection reason, never re-asks about
# already-accepted claims.
MAX_DIAGNOSIS_ROUNDS = 2

# An ablation_<switch> track's n_months collapsing relative to the baseline
# (e.g. an annual signal losing its forward-fill once rebalance_frequency
# turns monthly) makes its t-stat -- and therefore its OAT contribution --
# incomparable to the baseline's. Reject gap_attribution claims built on such
# a pair rather than let a real, whitelisted contribution value be cited as
# if the two tracks shared a sample.
GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD = 2.0

# joint_switch_wald_test's own significance threshold (docs/step7-8.md Part
# VIII §8.3) -- deliberately NOT Q7's `SIGNIFICANCE_T_THRESHOLDS` tiers, which
# are scoped to "track vs paper" only; the joint test is a p-value against a
# chi2 null, an unrelated question.
JOINT_TEST_ALPHA = 0.05


class ReplicationDiagnoser:
    """Turns a deterministic evidence bundle into evidence-cited narrative."""

    def __init__(self, llm_client: Any, model: str | None = None):
        self.llm_client = llm_client
        self.model = model

    def diagnose(
        self,
        bundle: dict[str, Any],
        resolved_spec: ResolvedMethodSpec | None = None,
        tool_policy: ToolPolicy | None = None,
        max_rounds: int = MAX_DIAGNOSIS_ROUNDS,
    ) -> ReplicationDiagnosisReport:
        """Produce a validated diagnosis report for one comparison bundle.

        `bundle` is the parsed `comparison.json` (schema v2+), which must
        already contain the deterministic `derived` / `config_diff` /
        `gap_decomposition` / `evidence_keys` sections (and, when present,
        the newer `spec_quality`/`menu_deviations`/
        `publication_decay`/`robustness_summary` sections -- see
        `src.steps.step7_replication_diff.bundle`).

        `resolved_spec`, when supplied, powers the opt_in
        `field_evidence_detail` tool (reads `SourcedValue.evidence[]`);
        without it that tool is unavailable (any request for it is ignored,
        same as an unknown tool name).

        Bounded retry (docs/tools-plus-llm-plan.md §4.3): if round 1 has any
        rejected claims, one further round resubmits ONLY those (with their
        rejection reason) for a chance to fix or drop them -- never re-asks
        about already-accepted claims. Accepted claims are deduped across
        rounds by content, so a client that resubmits its whole answer
        verbatim (rather than only the fixed subset) never double-counts.
        """
        policy = tool_policy or ToolPolicy()
        evidence_keys = bundle.get("evidence_keys") or {}
        report = ReplicationDiagnosisReport(
            factor_id=bundle.get("factor_id", "unknown"),
            llm_model=self.model,
            overall_tag=(bundle.get("derived") or {}).get("overall_tag", "inconclusive"),
        )

        ctx = Step8ToolContext(bundle=bundle, resolved_spec=resolved_spec)
        requested: list[str] = []
        accepted: list[DiagnosisClaim] = []
        rejected: list[RejectedClaim] = []
        seen: set[str] = set()

        for round_num in range(1, max_rounds + 1):
            run = ToolRunner().run_all(STEP8_TOOLS, ctx, policy, requested=requested)
            system_prompt = splice_tool_catalog(
                DIAGNOSIS_SYSTEM_PROMPT, render_tool_catalog(STEP8_TOOLS, run.results, run.unknown_requests),
            )
            if round_num == 1:
                user_prompt = self._build_prompt(bundle, run.results)
            else:
                if not rejected:
                    break
                user_prompt = self._build_retry_prompt(rejected, run.results)

            response = self.llm_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            payload = _parse_payload(response.choices[0].message.content or "")
            raw_claims = payload.get("claims") or []
            requested = (payload.get("tool_requests") or []) if policy.allow_llm_requests else []

            new_accepted, rejected = validate_claims(raw_claims, evidence_keys)
            for claim in new_accepted:
                key = json.dumps(claim.model_dump(mode="json"), sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                accepted.append(claim)

            if not rejected:
                break

        report.claims = accepted
        report.rejected_claims = rejected
        report.summary = build_deterministic_summary(accepted, bundle)
        report.vs_paper_summary = build_vs_paper_summary(bundle)
        report.spec_quality_summary = build_spec_quality_summary(bundle)
        return report

    def _build_prompt(self, bundle: dict[str, Any], tool_results: list[ToolResult]) -> str:
        whitelist = sorted((bundle.get("evidence_keys") or {}).keys())
        return "\n".join(
            [
                render_tool_results(tool_results),
                "",
                "## Citable evidence keys (the ONLY keys you may reference)",
                "```json",
                json.dumps(whitelist, indent=2),
                "```",
                "",
                "Return the JSON object of claims described in your instructions.",
            ]
        )

    def _build_retry_prompt(self, rejected: list[RejectedClaim], tool_results: list[ToolResult]) -> str:
        """Round 2+: resubmit ONLY the previously-rejected claims, each with
        its rejection reason, and ask for revised (or dropped) versions --
        never re-ask about claims that already passed. Also carries any
        newly-run tool results (e.g. a requested `field_evidence_detail`),
        so an opt_in tool's payload actually reaches the LLM here too, not
        only in round 1's prompt."""
        lines = [
            "## Previously rejected claims",
            "",
            "Each of these was rejected by the deterministic validator for the "
            "reason shown. Return a revised version of each you can fix (same "
            "JSON shape as before), or omit it entirely if it cannot be fixed. "
            "Do not resubmit claims that were not listed here.",
            "",
        ]
        for i, r in enumerate(rejected, start=1):
            lines += [
                f"### Rejected claim {i}",
                f"Reason: {r.reason}",
                "```json",
                json.dumps(r.claim, indent=2, default=str),
                "```",
                "",
            ]
        lines.append(render_tool_results(tool_results))
        lines.append("")
        lines.append('Return the same JSON object shape: {"claims": [...], "tool_requests": []}.')
        return "\n".join(lines)


@dataclass
class Step8ToolContext(ToolContext):
    bundle: dict = field(default_factory=dict)
    #: Only needed by the opt_in `field_evidence_detail` tool -- unavailable
    #: (tool self-skips) when not supplied.
    resolved_spec: ResolvedMethodSpec | None = None


def _bundle_section_tool(name: str, description: str, produces: str) -> Tool[Step8ToolContext]:
    """Most of Step8's tools are placeholders in the same sense as Step1's
    `schema_skeleton`: the actual computation already happened in Step7's
    `build_evidence_bundle()` (see docs/tools-plus-llm-plan.md §4.3) --
    `fn` here just reads the already-computed section out of `ctx.bundle`,
    it never computes anything itself.
    """
    def fn(ctx: Step8ToolContext) -> ToolResult:
        section = ctx.bundle.get(name)
        if section is None:
            return ToolResult(name=name, status="skipped", error=f"bundle has no {name!r} section")
        return ToolResult(name=name, status="ok", payload=section)
    return Tool(name=name, description=description, produces=produces, fn=fn, tier="always")


SPEC_QUALITY_TOOL = _bundle_section_tool(
    "spec_quality",
    "paper spec fields with weak evidence (unspecified/inferred/conflicting)",
    "field_path + evidence status summary; does not mean the field is wrong, only that it's our best guess",
)
MENU_DEVIATIONS_TOOL = _bundle_section_tool(
    "menu_deviations",
    "where the paper's method fell off the engine's menu (unsupported_value) + per-track clamped config defaults (defaults_applied)",
    "may be incomplete (empty on an older comparison.json without this section)",
)
DERIVED_TOOL = _bundle_section_tool(
    "derived",
    "each track vs the paper (sign_agrees/abs_spread_ratio/significance/etc) + the overall_tag verdict",
    "observational comparison only, never implies causation",
)
CONFIG_DIFF_TOOL = _bundle_section_tool(
    "config_diff", "config differences between tracks (which keys differ, by how much)", "observational, not a controlled experiment"
)
GAP_DECOMPOSITION_TOOL = _bundle_section_tool(
    "gap_decomposition", "one-at-a-time (OAT) per-switch contribution decomposition", "harmonized evidence, non-additive, not guaranteed to sum"
)
GAP_CLOSURE_TOOL = _bundle_section_tool(
    "gap_closure",
    "to_cz total gap (baseline vs cz_actual_config spread) vs the sum of catalogued per-switch effects, plus the unexplained residual",
    "harmonized (OAT) evidence, same non-additivity caveat as gap_decomposition; unavailable without both the baseline and cz_actual_config tracks",
)
PUBLICATION_DECAY_TOOL = _bundle_section_tool(
    "publication_decay",
    "per-track in-sample vs post-publication t-stat comparison (McLean-Pontiff style decay)",
    "unavailable when no track configured a publication-year sample split; orthogonal to replication quality, a property of the factor's own time series",
)
ROBUSTNESS_SUMMARY_TOOL = _bundle_section_tool(
    "robustness_summary",
    "aggregate sign-flip/significance-flip count across all ablation_* tracks vs baseline",
    "requires a baseline track plus at least one ablation_* track",
)
SHAPLEY_ATTRIBUTION_TOOL = _bundle_section_tool(
    "shapley_attribution",
    "per-switch Shapley-value decomposition of the mean_return gap across a full-factorial batch, nested by comparison line (to_hxz/to_cz)",
    "requires all 2^n corners of the factorial grid for a line to be present; unavailable (with the missing subsets named) otherwise",
)
PAIRED_TESTS_TOOL = _bundle_section_tool(
    "paired_tests",
    "per-switch paired Newey-West significance test of a single-switch track vs baseline, nested by comparison line",
    "requires the on-disk monthly return series (<track>.csv); unavailable without results_dir or a missing CSV",
)
JOINT_TEST_TOOL = _bundle_section_tool(
    "joint_test",
    "joint Wald test across all single-switch contrasts on one comparison line -- whether they collectively explain more than noise",
    "requires >=2 single-switch tracks with a loadable return series on that line",
)
THREE_TERM_IDENTITY_TOOL = _bundle_section_tool(
    "three_term_identity",
    "an external implementer's (C&Z / HXZ) distance from the PAPER's own reported spread, split into signal+environment, config, and agent-replication residual, nested by reference (cz/hxz)",
    "an accounting split, not an experiment: the endpoints do not share a sample window (see window_basis.caveat) and the three terms carry different noise (see term_purity_notes); unavailable when the external reference or either track's spread is missing",
)


def _field_evidence_detail_fn(ctx: Step8ToolContext) -> ToolResult:
    """Opt_in: full `SourcedValue.evidence[]` citations for every field
    `spec_quality` flagged as weak -- the summary (`weak_fields`) only lists
    field_path+status, this expands to the actual paper quotes when the LLM
    requests it (needs `resolved_spec`, unlike the always-tier tools).
    """
    if ctx.resolved_spec is None:
        return ToolResult(name="field_evidence_detail", status="skipped", error="no resolved_spec supplied")
    weak_fields = ((ctx.bundle.get("spec_quality") or {}).get("weak_fields")) or []
    detail = {}
    for entry in weak_fields:
        field_path = entry.get("field_path")
        if not field_path:
            continue
        try:
            obj: Any = ctx.resolved_spec.paper
            for part in field_path.replace("]", "").replace("[", ".").split("."):
                obj = obj[int(part)] if part.isdigit() else getattr(obj, part)
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
        evidence = getattr(obj, "evidence", None)
        if evidence:
            detail[field_path] = [
                {"quote": e.quote, "table_ref": e.table_ref.model_dump() if e.table_ref else None}
                for e in evidence
            ]
    return ToolResult(name="field_evidence_detail", status="ok", payload=detail)


FIELD_EVIDENCE_DETAIL_TOOL: Tool[Step8ToolContext] = Tool(
    name="field_evidence_detail",
    description="full paper-quote citations for one weak field (spec_quality only gives a summary)",
    produces="{field_path: [{quote, table_ref}]}; requires resolved_spec to be supplied",
    fn=_field_evidence_detail_fn,
    tier="opt_in",
)

STEP8_TOOLS: list[Tool[Step8ToolContext]] = [
    SPEC_QUALITY_TOOL,
    MENU_DEVIATIONS_TOOL,
    DERIVED_TOOL,
    CONFIG_DIFF_TOOL,
    GAP_DECOMPOSITION_TOOL,
    GAP_CLOSURE_TOOL,
    PUBLICATION_DECAY_TOOL,
    ROBUSTNESS_SUMMARY_TOOL,
    SHAPLEY_ATTRIBUTION_TOOL,
    PAIRED_TESTS_TOOL,
    JOINT_TEST_TOOL,
    THREE_TERM_IDENTITY_TOOL,
    FIELD_EVIDENCE_DETAIL_TOOL,
]


def _parse_payload(raw: str) -> dict[str, Any]:
    """Extract the full response object (`claims` + optional `tool_requests`)
    from the model's raw response."""
    from src.infra.llm import extract_json_object_text

    try:
        payload = json.loads(extract_json_object_text(raw))
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_claims(raw: str) -> list[dict]:
    """Extract just the claim list from the model's raw response."""
    claims = _parse_payload(raw).get("claims", [])
    return [c for c in claims if isinstance(c, dict)]


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

    line_reason = _comparison_line_reason(raw, keys)
    if line_reason:
        return line_reason

    return _entailment_reason(claim_type, relation, keys, evidence_keys, raw)


def _cited_tracks(keys: list[str]) -> set[str]:
    tracks: set[str] = set()
    for k in keys:
        m = (
            _TRACK_FROM_VS_PAPER_KEY.match(k)
            or _TRACK_FROM_CONFIG_DIFF_KEY.match(k)
            or _TRACK_FROM_PUBLICATION_DECAY_KEY.match(k)
        )
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


def _cited_lines(keys: list[str]) -> set[str]:
    lines: set[str] = set()
    for k in keys:
        m = _LINE_FROM_NESTED_KEY.match(k)
        if m:
            lines.add(m.group(1))
    return lines


def _comparison_line_reason(raw: dict, keys: list[str]) -> str | None:
    """docs/step7-8.md Part VIII §8.1: mirrors `_subject_track_reason` exactly,
    but for `comparison_line` (`to_hxz`/`to_cz`) against `shapley_attribution`/
    `paired_tests`/`joint_test` citations, which are organized by switch, not
    by track, so `subject_track` cannot do this job for them.
    """
    cited_lines = _cited_lines(keys)
    comparison_line = raw.get("comparison_line")
    if not cited_lines:
        return None
    if comparison_line is None:
        if len(cited_lines) == 1:
            return None
        return "claim cites more than one comparison line's evidence but names no comparison_line"
    if comparison_line not in cited_lines:
        return (
            f"comparison_line {comparison_line!r} does not match the cited evidence's "
            f"line(s) {sorted(cited_lines)}"
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
    claim_type: str, relation: str, keys: list[str], evidence_keys: dict[str, Any], raw: dict | None = None,
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

    elif claim_type == "publication_decay":
        decay_key = next((k for k in keys if k.endswith(".decayed")), None)
        if decay_key is None:
            return "publication_decay must cite a publication_decay.tracks.<track>.decayed value"
        value = evidence_keys.get(decay_key)
        if value is None:
            return "publication_decay's cited .decayed value is null; cite evidence_limitation instead"
        expected = "decayed" if value else "stable"
        if relation != expected:
            return f"relation {relation!r} contradicts the cited decayed value ({value!r})"

    elif claim_type == "implementation_robustness":
        robust_key = next((k for k in keys if k.endswith(".robust")), None)
        if robust_key is None:
            return "implementation_robustness must cite a robustness_summary.robust value"
        value = evidence_keys.get(robust_key)
        if value is None:
            return "implementation_robustness's cited .robust value is null"
        expected = "robust" if value else "fragile"
        if relation != expected:
            return f"relation {relation!r} contradicts the cited robust value ({value!r})"

    elif claim_type == "gap_attribution_shapley":
        effect_key = next((k for k in keys if ".shapley_effects." in k), None)
        if effect_key is None:
            return (
                "gap_attribution_shapley must cite a "
                "shapley_attribution.<line>.shapley_effects.<switch> value"
            )
        if evidence_keys.get(effect_key) is None:
            return "gap_attribution_shapley's cited shapley_effects value is null"

    elif claim_type == "switch_significance":
        t_key = next(
            (k for k in keys if k.endswith(".t_stat") and ".per_switch." in k), None
        )
        if t_key is None:
            return (
                "switch_significance must cite a "
                "paired_tests.<line>.per_switch.<switch>.t_stat value"
            )
        t = evidence_keys.get(t_key)
        if t is None:
            return "switch_significance's cited t_stat is null; cite evidence_limitation instead"
        expected = "significant" if abs(t) >= SIGNIFICANCE_T_THRESHOLD else "insignificant"
        if relation != expected:
            return f"relation {relation!r} contradicts the cited t_stat value ({t!r})"

    elif claim_type == "joint_attribution_support":
        p_key = next((k for k in keys if k.endswith(".p_value")), None)
        if p_key is None:
            return "joint_attribution_support must cite a joint_test.<line>.p_value value"
        p = evidence_keys.get(p_key)
        if p is None:
            return "joint_attribution_support's cited p_value is null; cite evidence_limitation instead"
        expected = "significant" if p < JOINT_TEST_ALPHA else "insignificant"
        if relation != expected:
            return f"relation {relation!r} contradicts the cited p_value ({p!r})"

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

    cited_lines = _cited_lines(keys)
    comparison_line = raw.get("comparison_line") or (
        next(iter(cited_lines)) if len(cited_lines) == 1 else None
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
    elif claim_type == "gap_attribution_shapley":
        switches = {
            m.group(1)
            for k in keys
            if (m := _SWITCH_FROM_SHAPLEY_KEY.search(k))
        }
        stages = {stage_of(s) for s in switches}
        stage = next(iter(stages)) if len(stages) == 1 else None

    identification_level = IDENTIFICATION_BY_CLAIM_TYPE.get(claim_type, "observational")
    if claim_type == "gap_attribution":
        found = evidence_keys.get("gap_decomposition.identification_level")
        identification_level = found or identification_level
    elif claim_type == "gap_attribution_shapley" and comparison_line:
        found = evidence_keys.get(f"shapley_attribution.{comparison_line}.identification_level")
        identification_level = found or identification_level

    evidence_strength = EVIDENCE_STRENGTH_BY_IDENTIFICATION.get(identification_level, "low")

    # docs/step7-8.md Part VIII \u00a78.4: joint-test gate. A per-switch Shapley
    # claim's evidence_strength is capped to "low" when the SAME comparison
    # line's joint test is available but not significant -- data-layer
    # equivalent of the frontend ShapleyAttributionTable's dim+badge behavior,
    # not a rejection (the number is still real, just not jointly supported).
    if claim_type == "gap_attribution_shapley" and comparison_line:
        joint_p = evidence_keys.get(f"joint_test.{comparison_line}.p_value")
        if joint_p is not None and joint_p >= JOINT_TEST_ALPHA:
            evidence_strength = "low"

    reason_layer = REASON_LAYER_BY_CLAIM_TYPE.get(claim_type, "config_sensitivity")

    return {
        "subject_track": subject_track,
        "comparison_line": comparison_line,
        "stage": stage,
        "identification_level": identification_level,
        "evidence_strength": evidence_strength,
        "reason_layer": reason_layer,
        "analysis_stage": ANALYSIS_STAGE_BY_CLAIM_TYPE.get(claim_type),
    }
