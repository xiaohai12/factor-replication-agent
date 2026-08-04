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

_CLAIM_TYPE_HEADINGS = {
    "sign_agreement": "Sign agreement",
    "magnitude_gap": "Magnitude gap",
    "significance": "Statistical significance",
    "config_divergence": "Configuration divergence",
    "gap_attribution": "Gap attribution",
    "evidence_limitation": "Evidence limitations",
}

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
}


def _switch_subject(claim: DiagnosisClaim, evidence: dict[str, Any]) -> str:
    for key in claim.evidence_keys:
        if ".contributions." in key:
            return key.rsplit(".", 1)[-1]
    return "this switch"


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
    if claim.claim_type == "gap_attribution":
        subject = _switch_subject(claim, evidence)
    elif claim.claim_type == "evidence_limitation":
        subject = "the requested comparison"
    else:
        subject = claim.subject_track or "track"
    return template.format(subject=subject)


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

    lines += ["## Findings", ""]
    if not report.claims:
        lines += ["No claims survived evidence validation.", ""]
    else:
        by_type: dict[str, list] = {}
        for claim in report.claims:
            by_type.setdefault(claim.claim_type, []).append(claim)
        for claim_type, claims in by_type.items():
            lines.append(f"### {_CLAIM_TYPE_HEADINGS.get(claim_type, claim_type)}")
            lines.append("")
            for claim in claims:
                cited = ", ".join(
                    f"`{key}` = {format_value(evidence.get(key))}" for key in claim.evidence_keys
                )
                stage = f" _[stage: {claim.stage}]_" if claim.stage else ""
                sentence = deterministic_sentence(claim, evidence)
                lines.append(f"- {sentence}{stage}")
                if claim.text and claim.text.strip() and claim.text.strip() != sentence.strip():
                    lines.append(f"  - model wording (not authoritative): {claim.text}")
                lines.append(f"  - evidence: {cited}")
                lines.append(
                    f"  - identification: {claim.identification_level} · "
                    f"evidence strength: {claim.evidence_strength}"
                )
            lines.append("")

    if report.rejected_claims:
        lines += ["## Rejected claims (audit)", ""]
        for rejected in report.rejected_claims:
            lines.append(f"- {rejected.reason}")
            lines.append(f"  - raw: `{json.dumps(rejected.claim, default=str)}`")
        lines.append("")

    return "\n".join(lines)


def write_diagnosis(
    report: ReplicationDiagnosisReport, bundle: dict[str, Any], results_dir: str | Path
) -> tuple[Path, Path]:
    """Write `diagnosis.json` + `diagnosis.md` next to `comparison.json`."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    json_path = results_dir / "diagnosis.json"
    json_path.write_text(json.dumps(report.model_dump(), indent=2, default=str))

    md_path = results_dir / "diagnosis.md"
    md_path.write_text(render_markdown(report, bundle))
    return json_path, md_path
