"""Structured output of the LLM replication-diagnosis layer (step 8).

The LLM writes only WORDING and a STRUCTURED RELATION here. Each claim is a
`(claim_type, subject_track, relation, evidence_keys)` tuple plus optional
prose. It never writes a number -- the renderer re-inserts every figure from
the bundle -- and it never sets the verdict (`overall_tag`, computed by
`bundle.classify_overall`). The whole report is permanently tagged
`llm_assisted_proposal` so it can never be mistaken for an automatic empirical
conclusion (AGENTS.md; Phase E of docs/multi-config-evidence-plan.md).

Why the relation is structured rather than free text: citing a real key does
not make a sentence true. "The signs are opposite" citing a `sign_agrees` key
whose value is `true` passes any citation-shape check. Encoding the relation
as an enum lets the validator compare the asserted relation against the cited
value (claim entailment), and lets `render.py` generate the sentence
deterministically.

`stage`, `identification_level` and `evidence_strength` are NOT LLM-authored:
they are derived deterministically from the cited evidence in
`src.steps.step8_diagnosis`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ClaimType = Literal[
    "sign_agreement",
    "magnitude_gap",
    "significance",
    "config_divergence",
    "gap_attribution",
    "evidence_limitation",
    "publication_decay",
    "implementation_robustness",
    "gap_attribution_shapley",
    "switch_significance",
    "joint_attribution_support",
    # docs/paper-outline.md C1: which of signal / config / agent-replication
    # residual dominates an EXTERNAL implementer's distance from the paper's
    # own reported number. The only claim type whose evidence involves an
    # endpoint this engine did not itself run.
    "three_term_gap_component",
]

#: Which of the two reason layers (docs/tools-plus-llm-plan.md §4.3) a
#: claim_type belongs to -- NOT LLM-authored, derived from claim_type alone.
#: `temporal_pattern` (publication_decay) is deliberately its own layer: it's
#: orthogonal to "did we replicate correctly", it's a property of the
#: factor's own time series.
ReasonLayer = Literal["config_sensitivity", "temporal_pattern"]

REASON_LAYER_BY_CLAIM_TYPE: dict[str, str] = {
    "sign_agreement": "config_sensitivity",
    "magnitude_gap": "config_sensitivity",
    "significance": "config_sensitivity",
    "config_divergence": "config_sensitivity",
    "gap_attribution": "config_sensitivity",
    "evidence_limitation": "config_sensitivity",
    "publication_decay": "temporal_pattern",
    "implementation_robustness": "config_sensitivity",
    "gap_attribution_shapley": "config_sensitivity",
    "switch_significance": "config_sensitivity",
    "joint_attribution_support": "config_sensitivity",
    "three_term_gap_component": "config_sensitivity",
}

#: docs/step7-8.md Part IX (scheme B): a dependency-ordered narrative stage,
#: orthogonal to `ReasonLayer` above (which stays unchanged). `per_switch` ->
#: `joint_gate` -> `vs_paper` is a real dependency chain (the joint gate caps
#: per-switch evidence_strength, see `_derive_claim_fields`); `auxiliary`
#: claim types are intentionally NOT part of that chain (Part IX §9.6).
#: `gap_attribution` (the old OAT-only type) is deliberately absent -- it gets
#: `analysis_stage=None` ("unstaged"), not lumped into `per_switch`, so an
#: incomplete-grid OAT contribution is never presented at the same narrative
#: tier as a complete-grid Shapley one.
AnalysisStage = Literal["per_switch", "joint_gate", "vs_paper", "auxiliary"]

ANALYSIS_STAGE_BY_CLAIM_TYPE: dict[str, str] = {
    "switch_significance": "per_switch",
    "gap_attribution_shapley": "per_switch",
    "joint_attribution_support": "joint_gate",
    "sign_agreement": "vs_paper",
    "magnitude_gap": "vs_paper",
    "significance": "vs_paper",
    "config_divergence": "vs_paper",
    # Also anchored on the paper's own reported number, so it belongs with
    # the other `vs_paper` claims rather than the per-switch chain.
    "three_term_gap_component": "vs_paper",
    "publication_decay": "auxiliary",
    "implementation_robustness": "auxiliary",
    "evidence_limitation": "auxiliary",
}

#: The directional assertion a claim makes. Deliberately non-causal: even
#: `associated_change` says only "this switch is associated with a measured
#: change", never "this switch caused the gap".
Relation = Literal[
    "agrees",
    "disagrees",
    "larger",
    "smaller",
    "similar",
    "significant",
    "insignificant",
    "differs",
    "associated_change",
    "unavailable",
    "decayed",
    "stable",
    "robust",
    "fragile",
]

Stage = Literal[
    "signal_input",
    "portfolio",
    "universe",
    "sample",
    "estimator",
    "unclassified",
]

#: How strongly the cited design identifies what the claim asserts.
#:
#: - ``controlled``    -- a factorial/Shapley design isolating the switch,
#:                        interactions accounted for.
#: - ``harmonized``    -- measured under an otherwise-held-fixed config, but
#:                        one-at-a-time: effects need not be additive and may
#:                        depend on switch order and baseline endpoint.
#: - ``observational`` -- differences merely observed (e.g. a config diff),
#:                        with no experiment isolating them.
#: - ``unidentified``  -- the evidence needed was not produced at all.
IdentificationLevel = Literal["controlled", "harmonized", "observational", "unidentified"]

#: Which relations are meaningful for each claim type.
CLAIM_RELATIONS: dict[str, tuple[str, ...]] = {
    "sign_agreement": ("agrees", "disagrees"),
    "magnitude_gap": ("larger", "smaller", "similar"),
    "significance": ("significant", "insignificant"),
    "config_divergence": ("differs",),
    "gap_attribution": ("associated_change",),
    "evidence_limitation": ("unavailable",),
    "publication_decay": ("decayed", "stable"),
    "implementation_robustness": ("robust", "fragile"),
    "gap_attribution_shapley": ("associated_change",),
    "switch_significance": ("significant", "insignificant"),
    "joint_attribution_support": ("significant", "insignificant"),
    # "larger"/"smaller" compare one term against the others; "similar" says
    # no term dominates. Deliberately NOT `associated_change`: the identity is
    # an accounting split, it does not identify an effect.
    "three_term_gap_component": ("larger", "smaller", "similar"),
}

#: Every claim type must cite at least one key whose dotted path starts with
#: one of these prefixes. This is the "allowed evidence schema per claim type"
#: from Phase E: a claim about significance may not be justified by, say, a
#: config key, and an attribution claim may not be made without the OAT
#: decomposition actually being present.
CLAIM_EVIDENCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "sign_agreement": ("derived.tracks.", "paper_reported.main_spread"),
    "magnitude_gap": ("derived.tracks.",),
    "significance": ("derived.tracks.",),
    "config_divergence": ("config_diff.",),
    "gap_attribution": ("gap_decomposition.contributions.",),
    "evidence_limitation": ("gap_decomposition.", "derived.tracks."),
    "publication_decay": ("publication_decay.",),
    "implementation_robustness": ("robustness_summary.",),
    # docs/step7-8.md Part VIII: full-factorial Shapley attribution / per-switch
    # paired Newey-West test / joint Wald test, nested one level by comparison
    # line (`to_hxz`/`to_cz`) -- see `comparison_line` on `DiagnosisClaim`.
    "gap_attribution_shapley": ("shapley_attribution.",),
    "switch_significance": ("paired_tests.",),
    "joint_attribution_support": ("joint_test.",),
    "three_term_gap_component": ("three_term_identity.",),
}

#: Additional per-claim-type substring requirement, checked against the same
#: cited keys. Keeps "significant"-flavoured wording tied to the deterministic
#: significance test rather than to any nearby number.
CLAIM_EVIDENCE_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "sign_agreement": ("sign_agrees",),
    "magnitude_gap": ("spread",),
    "significance": ("significant",),
    "publication_decay": ("decayed",),
    "implementation_robustness": ("robust",),
    "gap_attribution_shapley": ("shapley_effects",),
    "switch_significance": ("t_stat",),
    "joint_attribution_support": ("p_value",),
    # Forces the claim onto one of the three named components rather than the
    # section's endpoints or its window_basis metadata.
    "three_term_gap_component": ("terms.",),
}

#: Identification level implied by each claim type's evidence. Attribution is
#: the only type whose level varies at runtime (it follows the decomposition's
#: own `identification_level`).
IDENTIFICATION_BY_CLAIM_TYPE: dict[str, str] = {
    "sign_agreement": "observational",
    "magnitude_gap": "observational",
    "significance": "observational",
    "config_divergence": "observational",
    "gap_attribution": "harmonized",
    "evidence_limitation": "unidentified",
    "publication_decay": "observational",
    "implementation_robustness": "harmonized",
    # Default before the runtime override in `_derive_claim_fields`, which reads
    # the cited `shapley_attribution.<line>.identification_level` ("controlled"
    # only when the full 2^n factorial grid is present, see attribution.py).
    "gap_attribution_shapley": "controlled",
    # A single-switch track vs baseline, same identification tier as an
    # ablation_* track -- doesn't require a complete factorial grid.
    "switch_significance": "harmonized",
    # The Wald test only needs >=2 single-switch tracks, not the full grid
    # Shapley requires -- stays "harmonized", never "controlled".
    "joint_attribution_support": "harmonized",
    # An accounting split across four endpoints, two of which this engine did
    # not run and none of which share a sample window -- nothing here is a
    # controlled contrast, so it can never rise above "observational".
    "three_term_gap_component": "observational",
}

#: Deterministic map from identification level to reported strength. Replaces
#: the model's former self-scored `confidence`, which was an unconstrained LLM
#: opinion dressed up as a reliability signal.
EVIDENCE_STRENGTH_BY_IDENTIFICATION: dict[str, str] = {
    "controlled": "high",
    "harmonized": "medium",
    "observational": "low",
    "unidentified": "low",
}

#: Causal vocabulary permitted only at `identification_level == "controlled"`.
#: One-at-a-time evidence supports "associated with a measured change", never
#: "explains" or "is caused by".
CAUSAL_TERM_RE = re.compile(
    r"\b(drives?|driven|drove|explains?|explained|causes?|caused|causal|because|"
    r"responsible\s+for|attributable\s+to|results?\s+in|resulted\s+in|"
    r"leads?\s+to|leading\s+to|due\s+to|owing\s+to|stems?\s+from|arises?\s+from)\b",
    re.IGNORECASE,
)


class DiagnosisClaim(BaseModel):
    """One narrative fragment produced by the LLM."""

    claim_type: ClaimType
    #: The structured assertion. Checked against the cited value, so a claim
    #: cannot say "opposite" while citing a key whose value is `true`.
    relation: Relation
    #: Which track the claim is about, for track-scoped claim types. Must match
    #: the track segment of the cited `derived.tracks.*` / `config_diff.pairs.*`
    #: key, so the subject cannot be swapped either.
    subject_track: str | None = None
    #: Which comparison line (①→③ `to_hxz` vs ①→② `to_cz`) the claim is about,
    #: for claims citing the line-nested `shapley_attribution`/`paired_tests`/
    #: `joint_test` sections (docs/step7-8.md Part VI/VIII). `None` for claims
    #: that don't cite line-nested evidence. Derived, not LLM-authored.
    #: `cz`/`hxz` are `three_term_identity`'s own nesting keys -- that section
    #: nests by EXTERNAL REFERENCE (whose measured result is the endpoint),
    #: not by track line, so they are deliberately distinct values rather
    #: than aliases of `to_cz`/`to_hxz`.
    comparison_line: Literal["to_hxz", "to_cz", "cz", "hxz"] | None = None
    #: Optional supporting prose. Must contain no digits -- the renderer emits
    #: the sentence and appends the cited values, so a number written here
    #: would be an unverifiable LLM figure.
    text: str = ""
    #: Dotted keys into `bundle["evidence_keys"]`. Validated against that
    #: whitelist; unknown keys get the whole claim rejected.
    evidence_keys: list[str] = Field(default_factory=list)
    #: Derived deterministically from the cited config key's own `stage`, not
    #: guessed by the model. `None` for claims that are not stage-scoped.
    stage: Stage | None = None
    #: Derived deterministically from the cited evidence design.
    identification_level: IdentificationLevel = "observational"
    #: Derived deterministically from `identification_level`.
    evidence_strength: Literal["low", "medium", "high"] = "low"
    #: Which of the three reason layers this claim belongs to -- derived
    #: from `claim_type` alone via `REASON_LAYER_BY_CLAIM_TYPE`, never
    #: authored by the LLM.
    reason_layer: ReasonLayer = "config_sensitivity"
    #: Which dependency-ordered narrative stage (docs/step7-8.md Part IX) this
    #: claim belongs to -- derived from `claim_type` alone via
    #: `ANALYSIS_STAGE_BY_CLAIM_TYPE`, never authored by the LLM. `None` for
    #: claim types not yet assigned a stage (currently only `gap_attribution`,
    #: the old OAT-only type).
    analysis_stage: AnalysisStage | None = None


class RejectedClaim(BaseModel):
    """A claim the validator threw out, kept for audit."""

    reason: str
    claim: dict


class DiagnosisSummary(BaseModel):
    """Deterministic rollup for one comparison line (docs/step7-8.md Part IX
    §9.3 "option 1" -- NOT a second LLM-authored free-text layer; Part XII's
    `headline`/`details`/`footnote` are built straight from `bundle`, same
    discipline as everything else step7/8 produces: pure template generation,
    zero LLM involvement).

    Inverted-pyramid layout (docs/step7-8.md Part XII, user-requested
    redesign): `headline` is the one-sentence bottom line, always shown
    first; `details` are supporting points in decreasing importance, one per
    item (e.g. one per diverging implementation choice), never merged into
    one long paragraph; `footnote` is de-emphasized technical caveats (e.g.
    joint-test availability). No "vs. X"/line-label title is needed -- each
    `headline` names its own comparison target in plain language.
    """

    #: `None` when no line-scoped (per_switch/joint_gate) claim exists at all
    #: -- e.g. a batch with only vs_paper/auxiliary claims.
    comparison_line: Literal["to_hxz", "to_cz", "cz", "hxz"] | None = None
    #: Which of the reader-facing sections (docs/step7-8.md Part XVI) this
    #: entry belongs to -- "vs_cz" for `comparison_line=="to_cz"`,
    #: "robustness" for `comparison_line=="to_hxz"` (and any other named
    #: line, folded into the same bucket), "spec_quality" for the dedicated
    #: paper-clarity summary, "gap_split" for the three-term split of an
    #: external implementer's distance from the paper's own number,
    #: `None` for the legacy claim-only overflow bucket (a
    #: `comparison_line=None` entry with no bundle-derived content
    #: of its own). Frontend groups/orders/badges by THIS field, not
    #: `comparison_line` -- keeps a pre-2026-08-18 persisted `diagnosis.json`
    #: (section always `None`) rendering as a single undifferentiated list
    #: rather than crashing.
    section: Literal["reproduction", "robustness", "vs_cz", "spec_quality", "gap_split"] | None = None
    #: Copied from `bundle["derived"]["overall_tag"]`, never recomputed --
    #: this is a whole-factor verdict, not itself per-line.
    overall_tag: str = "inconclusive"
    #: {switch: "significant" | "insignificant"}, read directly from each
    #: `switch_significance` claim's own `relation` on this line.
    per_switch_summary: dict[str, str] = Field(default_factory=dict)
    #: From this line's `joint_attribution_support` claim's `relation`, if any
    #: was made. `None` means "not tested", NOT "tested and insignificant" --
    #: those are different states and must not be conflated.
    joint_supported: bool | None = None
    #: Switches with an accepted `gap_attribution_shapley` claim whose
    #: `evidence_strength` was NOT capped to "low" by the joint-test gate,
    #: ordered by the switch's own Shapley effect magnitude (read from the
    #: bundle, not authored).
    dominant_switches: list[str] = Field(default_factory=list)
    #: One-sentence bottom-line verdict, always shown first (docs/step7-8.md
    #: Part XII). Names its own comparison target in plain language --
    #: e.g. "Compared with C&Z's independent replication of this paper, ...".
    headline: str = ""
    #: Supporting points in decreasing importance, one entry per item (e.g.
    #: one per diverging implementation choice) -- never merged into a
    #: single run-on paragraph.
    details: list[str] = Field(default_factory=list)
    #: De-emphasized technical caveat (e.g. joint-test availability/result),
    #: shown last and visually de-emphasized by the renderer/frontend.
    footnote: str = ""
    #: {short label: long explanation} for every setting mentioned by SHORT
    #: name in `headline`/`details` (docs/step7-8.md Part XVI) -- the long,
    #: zero-background `CONFIG_KEY_LABELS` explanation is tooltip/glossary
    #: content now, not inlined into every sentence.
    glossary: dict[str, str] = Field(default_factory=dict)


class VsPaperSummary(BaseModel):
    """docs/step7-8.md Part XII: the baseline track vs. the paper's own
    reported number, same `headline`/`details`/`footnote` layout as
    `DiagnosisSummary` -- a small dedicated model rather than three loose
    fields on `ReplicationDiagnosisReport`, since this is one coherent unit
    (report-level, not per-comparison-line). Always section="reproduction"
    (docs/step7-8.md Part XVI) -- this IS the reproduction section, not one
    instance among several.
    """

    section: Literal["reproduction"] = "reproduction"
    headline: str = ""
    details: list[str] = Field(default_factory=list)
    footnote: str = ""
    glossary: dict[str, str] = Field(default_factory=dict)


class ReplicationDiagnosisReport(BaseModel):
    """LLM-assisted proposal explaining an already-computed replication gap."""

    factor_id: str
    schema_version: int = 2
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    llm_model: str | None = None
    #: Fixed by design -- this artifact is never an automatic conclusion.
    status: Literal["llm_assisted_proposal"] = "llm_assisted_proposal"
    #: Deterministic verdict copied from the bundle. Not LLM-authored.
    overall_tag: str = "inconclusive"
    claims: list[DiagnosisClaim] = Field(default_factory=list)
    rejected_claims: list[RejectedClaim] = Field(default_factory=list)
    #: Deterministic rollup (docs/step7-8.md Part IX), one entry per
    #: comparison line present among `claims` (or a single `comparison_line
    #: is None` entry when no line-scoped claim exists). Computed by
    #: `build_deterministic_summary`, never LLM-authored.
    summary: list[DiagnosisSummary] = Field(default_factory=list)
    #: Track-level (not per-line) summary comparing the baseline track
    #: against the paper's own reported number (docs/step7-8.md Part XII).
    #: Built by `summary.py::build_vs_paper_summary`, template-generated,
    #: never LLM-authored. This is the "reproduction" section (Part XVI).
    vs_paper_summary: VsPaperSummary = Field(default_factory=VsPaperSummary)
    #: How clearly the paper specified its method -- one bullet per field
    #: `spec_quality.weak_fields` flagged, quoting the review's own reason.
    #: Built by `summary.py::build_spec_quality_summary`, `section=
    #: "spec_quality"` always. Template-generated, never LLM-authored.
    spec_quality_summary: DiagnosisSummary = Field(
        default_factory=lambda: DiagnosisSummary(section="spec_quality")
    )
