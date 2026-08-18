"""Deterministic renderer for the replication-diagnosis report.

Every number that reaches the reader is formatted here, straight out of the
evidence bundle -- the LLM's claims contribute only prose and the list of keys
to look up. That is what makes `diagnosis.md` reproducible: swap the LLM out
and the figures are unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.infra.models.diagnosis import DiagnosisClaim, ReplicationDiagnosisReport


_BANNER = (
    "> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; "
    "every figure is inserted by a deterministic renderer from the evidence bundle. "
    "This is a hypothesis for human review, not an automatic empirical conclusion."
)

#: Friendlier labels for the comparison-line values used by
#: `shapley_attribution`/`paired_tests`/`joint_test` (docs/step7-8.md Part VI).
#: docs/step7-8.md Part XI: dropped the "①→②"/"①→③" prefix (internal-jargon
#: shorthand, confusing to show in a UI meant for a general reader) -- keep
#: only the descriptive part. Falls back to the raw value.
_LINE_LABELS = {
    "to_hxz": "vs. HXZ standardized config",
    "to_cz": "vs. C&Z actual config",
}

#: docs/step7-8.md Part XV §15.4: the whole per-analysis_stage "## Findings"
#: listing (every stage, not just per_switch/joint_gate) duplicated evidence
#: the Summary section already states in prose -- `_build_cz_summary`/
#: `_build_sensitivity_summary`/`build_vs_paper_summary` are all built
#: directly from the bundle (module docstring in `summary.py`), so Findings
#: never carried information Summary structurally couldn't. `report.claims`
#: is unchanged (still returned by the API, `rendered_sentence` still
#: computed by `report_to_jsonable`) -- only this markdown listing is gone.

#: Canonical sentence per (claim_type, relation). The LLM contributes only the
#: `subject_track`/evidence selection (validated against the bundle); the
#: actual sentence is generated here so wording cannot drift from what the
#: cited evidence + relation actually established. Any optional LLM `text` is
#: shown separately, clearly labelled, never in place of this sentence.
_RELATION_TEMPLATES: dict[str, dict[str, str]] = {
    "sign_agreement": {
        "agrees": "The {subject} track's spread sign agrees with the paper's headline sign.",
        "disagrees": "The {subject} track's spread sign is opposite to the paper's headline sign.",
    },
    "significance": {
        "significant": (
            "The {subject} track's spread is statistically significant by the "
            "deterministic significance threshold."
        ),
        "insignificant": (
            "The {subject} track's spread is not statistically significant by the "
            "deterministic significance threshold."
        ),
    },
    "magnitude_gap": {
        "larger": "The {subject} track's spread magnitude is larger than the paper's headline spread.",
        "smaller": "The {subject} track's spread magnitude is smaller than the paper's headline spread.",
        "similar": "The {subject} track's spread magnitude is similar to the paper's headline spread.",
    },
    "config_divergence": {
        "differs": "The {subject} track's configuration differs from the baseline track.",
    },
    "gap_attribution": {
        "associated_change": (
            "A measured change in the gap is associated with the {subject} switch "
            "(one-at-a-time, harmonized evidence: not necessarily additive, order-independent, "
            "or free of interaction effects)."
        ),
    },
    "evidence_limitation": {
        "unavailable": "The evidence needed to determine {subject} is not available.",
    },
    "signal_reproducibility": {
        "reproduces": "The {subject} track's signal reproduces the paper's headline sign.",
        "diverges": "The {subject} track's signal diverges from the paper's headline sign.",
    },
    "publication_decay": {
        "decayed": (
            "The {subject} track's spread is significant in-sample but not statistically "
            "significant post-publication."
        ),
        "stable": "The {subject} track's significance is stable across the in-sample/post-publication split.",
    },
    "implementation_robustness": {
        "robust": (
            "Across the one-at-a-time ablation tracks, the result shows no sign flip and no "
            "significance-threshold flip relative to the baseline."
        ),
        "fragile": (
            "Across the one-at-a-time ablation tracks, the result flips sign or crosses the "
            "significance threshold relative to the baseline for at least one implementation choice."
        ),
    },
    "gap_attribution_shapley": {
        "associated_change": (
            "On the {line} line, a Shapley-attributed share of the mean-return gap is "
            "associated with the {subject} switch (full-factorial evidence: the switches' "
            "Shapley effects sum exactly to the total gap, but this alone does not establish that "
            "the {subject} switch's own effect is statistically distinguishable from noise)."
        ),
    },
    "switch_significance": {
        "significant": (
            "On the {line} line, the {subject} switch's own paired effect (vs. baseline) "
            "is statistically significant."
        ),
        "insignificant": (
            "On the {line} line, the {subject} switch's own paired effect (vs. baseline) "
            "is not statistically significant."
        ),
    },
    "joint_attribution_support": {
        "significant": (
            "On the {line} line, the switches varied jointly explain a statistically "
            "significant share of the gap (joint Wald test)."
        ),
        "insignificant": (
            "On the {line} line, the switches varied jointly do not explain a "
            "statistically significant share of the gap (joint Wald test) -- any single-switch "
            "Shapley attribution on this line lacks joint support."
        ),
    },
}


def _switch_subject(claim: DiagnosisClaim, evidence: dict[str, Any]) -> str:
    for key in claim.evidence_keys:
        if ".contributions." in key or ".shapley_effects." in key:
            return key.rsplit(".", 1)[-1]
    return "this switch"


def _per_switch_subject(claim: DiagnosisClaim) -> str:
    for key in claim.evidence_keys:
        if ".per_switch." in key:
            # paired_tests.<line>.per_switch.<switch>.t_stat
            return key.split(".per_switch.", 1)[1].split(".", 1)[0]
    return "this switch"


def _line_label(comparison_line: str | None) -> str:
    if comparison_line is None:
        return "this comparison"
    return _LINE_LABELS.get(comparison_line, comparison_line)


def deterministic_sentence(claim: DiagnosisClaim, evidence: dict[str, Any]) -> str:
    """Generate the claim's sentence from its structured relation, not its prose.

    This is what makes claim wording auditable: swapping the cited evidence or
    the relation changes the sentence, and the LLM's own `text` can never
    override it.
    """
    templates = _RELATION_TEMPLATES.get(claim.claim_type, {})
    template = templates.get(claim.relation)
    if template is None:
        return claim.text or f"{claim.claim_type}: {claim.relation}"
    if claim.claim_type in ("gap_attribution", "gap_attribution_shapley"):
        subject = _switch_subject(claim, evidence)
    elif claim.claim_type == "switch_significance":
        subject = _per_switch_subject(claim)
    elif claim.claim_type == "evidence_limitation":
        subject = "the requested comparison"
    else:
        subject = claim.subject_track or "track"
    return template.format(subject=subject, line=_line_label(claim.comparison_line))


def format_value(value: Any) -> str:
    """Format one bundle value for display."""
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:  # NaN
            return "n/a"
        if value == 0:
            return "0"
        return f"{value:.6g}"
    return str(value)


def _paper_vs_tracks_table(bundle: dict[str, Any]) -> list[str]:
    derived_tracks = (bundle.get("derived") or {}).get("tracks") or {}
    if not derived_tracks:
        return []

    lines = [
        "| Track | Comparable metric | Our value | Paper value | Delta "
        "| Sign agrees | Our t-stat | Months |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, d in derived_tracks.items():
        vp = d.get("vs_paper") or {}
        lines.append(
            "| {track} | {metric} | {ours} | {paper} | {delta} | {sign} | {t} | {n} |".format(
                track=name,
                metric=format_value(vp.get("track_spread_metric")),
                ours=format_value(vp.get("track_spread")),
                paper=format_value(vp.get("paper_main_spread")),
                delta=format_value(vp.get("spread_delta")),
                sign=format_value(vp.get("sign_agrees")),
                t=format_value(vp.get("track_raw_t_stat")),
                n=format_value(d.get("n_months")),
            )
        )
    return lines


def _gap_section(bundle: dict[str, Any]) -> list[str]:
    gap = bundle.get("gap_decomposition") or {}
    if not gap.get("available"):
        return [
            "## Gap decomposition",
            "",
            f"Not available — {gap.get('reason', 'unknown reason')}.",
            "",
        ]
    lines = ["## Gap decomposition", "", "| Switch | Contribution (t-stat) |", "|---|---|"]
    for switch, contrib in sorted(
        (gap.get("contributions") or {}).items(), key=lambda kv: abs(kv[1] or 0), reverse=True
    ):
        lines.append(f"| {switch} | {format_value(contrib)} |")
    lines += [
        "",
        f"Total gap: {format_value(gap.get('total_gap'))} · "
        f"explained fraction: {format_value(gap.get('explained_fraction'))} · "
        f"residual: {format_value(gap.get('residual'))}",
        "",
    ]
    return lines


def _summary_line_priority(comparison_line: str | None) -> int:
    """docs/step7-8.md Part XI: `to_cz` is the project's core research
    question (AGENTS.md -- inter-implementer agreement), always shown
    first; `to_hxz` is supporting sensitivity context, shown second; any
    other/unrecognized line follows; the line-less ("Overall") summary
    goes last, since it's about the baseline track, not a comparison line.
    """
    order = {"to_cz": 0, "to_hxz": 1}
    if comparison_line is None:
        return 3
    return order.get(comparison_line, 2)


def _summary_section(report: ReplicationDiagnosisReport) -> list[str]:
    """docs/step7-8.md Part XII: renders the deterministic rollup in
    inverted-pyramid order -- `headline` (bottom line, always first), then
    `details` (one bullet per supporting point, decreasing importance), then
    `footnote` (de-emphasized technical caveat). No "vs. X" line-label
    heading -- `headline` names its own comparison target in plain language
    (user-requested redesign, docs/step7-8.md Part XII).
    """
    lines = ["## Summary", ""]
    if not report.summary and not report.vs_paper_summary.headline:
        return lines + ["No deterministic summary available.", ""]
    for s in sorted(report.summary, key=lambda s: _summary_line_priority(s.comparison_line)):
        if s.headline:
            lines.append(f"**{s.headline}**")
            lines.append("")
        for detail in s.details:
            lines.append(f"- {detail}")
        if s.details:
            lines.append("")
        lines.append(f"- Verdict: `{s.overall_tag}`")
        if s.footnote:
            lines.append(f"- _{s.footnote}_")
        lines.append("")
    if report.vs_paper_summary.headline:
        lines.append(f"**{report.vs_paper_summary.headline}**")
        lines.append("")
        for detail in report.vs_paper_summary.details:
            lines.append(f"- {detail}")
        if report.vs_paper_summary.footnote:
            lines.append(f"- _{report.vs_paper_summary.footnote}_")
        lines.append("")
    return lines


def render_markdown(report: ReplicationDiagnosisReport, bundle: dict[str, Any]) -> str:
    """Render a human-readable diagnosis with all figures taken from `bundle`."""
    evidence = bundle.get("evidence_keys") or {}
    lines: list[str] = [
        f"# Replication Diagnosis: {report.factor_id}",
        "",
        _BANNER,
        "",
        f"- Verdict (deterministic): `{report.overall_tag}`",
        f"- Paper: {bundle.get('paper_ref') or 'n/a'}",
        f"- Generated: {report.generated_at}",
        f"- Diagnosis model: {report.llm_model or 'n/a'}",
        "",
        "## Paper vs. tracks",
        "",
    ]
    table = _paper_vs_tracks_table(bundle)
    lines += table if table else ["No successful tracks to compare.", ""]
    lines.append("")
    lines += _gap_section(bundle)

    lines += _summary_section(report)

    if report.rejected_claims:
        lines += ["## Rejected claims (audit)", ""]
        for rejected in report.rejected_claims:
            lines.append(f"- {rejected.reason}")
            lines.append(f"  - raw: `{json.dumps(rejected.claim, default=str)}`")
        lines.append("")

    return "\n".join(lines)


def report_to_jsonable(report: ReplicationDiagnosisReport, bundle: dict[str, Any]) -> dict[str, Any]:
    """`report.model_dump()` with each claim's `deterministic_sentence(...)` spliced
    in as `rendered_sentence` -- the same sentence `diagnosis.md` shows, exposed to
    JSON consumers (the frontend) too, so they never have to re-derive or duplicate
    the `_RELATION_TEMPLATES` wording logic themselves.
    """
    evidence = bundle.get("evidence_keys") or {}
    data = report.model_dump(mode="json")
    for claim, claim_data in zip(report.claims, data["claims"]):
        claim_data["rendered_sentence"] = deterministic_sentence(claim, evidence)
    return data


def write_diagnosis(
    report: ReplicationDiagnosisReport, bundle: dict[str, Any], results_dir: str | Path
) -> tuple[Path, Path]:
    """Write `diagnosis.json` + `diagnosis.md` next to `comparison.json`."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    json_path = results_dir / "diagnosis.json"
    json_path.write_text(json.dumps(report_to_jsonable(report, bundle), indent=2, default=str))

    md_path = results_dir / "diagnosis.md"
    md_path.write_text(render_markdown(report, bundle))
    return json_path, md_path
