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
    "signal_reproducibility",
    "publication_decay",
    "implementation_robustness",
]

#: Which of the three reason layers (docs/tools-plus-llm-plan.md §4.3) a
#: claim_type belongs to -- NOT LLM-authored, derived from claim_type alone.
#: `temporal_pattern` (publication_decay) is deliberately its own layer: it's
#: orthogonal to "did we replicate correctly", it's a property of the
#: factor's own time series.
ReasonLayer = Literal["config_sensitivity", "signal_fidelity", "temporal_pattern"]

REASON_LAYER_BY_CLAIM_TYPE: dict[str, str] = {
    "sign_agreement": "config_sensitivity",
    "magnitude_gap": "config_sensitivity",
    "significance": "config_sensitivity",
    "config_divergence": "config_sensitivity",
    "gap_attribution": "config_sensitivity",
    "evidence_limitation": "config_sensitivity",
    "signal_reproducibility": "signal_fidelity",
    "publication_decay": "temporal_pattern",
    "implementation_robustness": "config_sensitivity",
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
    "reproduces",
    "diverges",
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
    "signal_reproducibility": ("reproduces", "diverges"),
    "publication_decay": ("decayed", "stable"),
    "implementation_robustness": ("robust", "fragile"),
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
    "signal_reproducibility": ("bridge_comparison.",),
    "publication_decay": ("publication_decay.",),
    "implementation_robustness": ("robustness_summary.",),
}

#: Additional per-claim-type substring requirement, checked against the same
#: cited keys. Keeps "significant"-flavoured wording tied to the deterministic
#: significance test rather than to any nearby number.
CLAIM_EVIDENCE_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "sign_agreement": ("sign_agrees",),
    "magnitude_gap": ("spread",),
    "significance": ("significant",),
    "signal_reproducibility": ("signal_implementation_agreement",),
    "publication_decay": ("decayed",),
    "implementation_robustness": ("robust",),
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
    "signal_reproducibility": "observational",
    "publication_decay": "observational",
    "implementation_robustness": "harmonized",
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


class RejectedClaim(BaseModel):
    """A claim the validator threw out, kept for audit."""

    reason: str
    claim: dict


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
