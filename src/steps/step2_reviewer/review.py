"""Deterministic review over the paper-first schema (Phase C). Produces
`MethodReview` from a `MethodSpec` -- NOT wired into `src.pipeline` yet
(see docs/methodspec-v2-plan.md section 9; the original `ReviewGate` in
`src/steps/step2_reviewer/__init__.py` remains the live reviewer until
Step3+ also consume these new artifacts).

D4 (engine-capability blocking) was removed 2026-08-10 (see
docs/step1-step2-refactor-plan.md): menu-vocabulary classification
(`weighting`/`construction_type`/`breakpoints.basis`/
`missing_policies[].action`) now happens inside the LLM review loop
(`src/steps/step2_reviewer/spec_build.py`), which writes an out-of-menu
choice as the enum's `OTHER` member plus `SourcedValue.unsupported_value`
carrying the paper's literal wording -- recorded, never blocked. Only
D2 (evidence-status-driven findings) remains here: every high-impact
`SourcedValue` field is looked up in `DISPOSITION_MATRIX`; anything that
isn't `AUTO_APPROVE` becomes a `Finding` of kind "ambiguous". The one
exception kept from the old D4 pass is the `universe.filters[].concept_id
⊄ data.fields` check -- refiled as `kind="missing_mapping"` /
`NEEDS_HUMAN_CONFIRMATION` since it prevents a hard Step3 crash (an
unmappable concept), not an engine-capability gap.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from src.infra.models.method_spec import (
    CAPABILITY_VERSION_V1,
    DISPOSITION_MATRIX,
    EMPIRICAL_IMPACT_HIGH,
    Disposition,
    EvidenceCitation,
    EvidenceStatus,
    Finding,
    MethodReview,
    MethodSpec,
    SourcedValue,
)

_LLM_REVIEW_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "review_gate" / "llm_review.md"
)


def load_llm_review_system_prompt() -> str:
    """Load `llm_review.md`, splicing in the current `MethodSpec` JSON
    skeleton (same mechanism as Step1's `load_extraction_system_prompt`).
    Used by `src.steps.step2_reviewer.spec_build`'s review loop.
    """
    from src.infra.models.schema_render import splice_schema_skeleton

    return splice_schema_skeleton(_LLM_REVIEW_PROMPT_PATH.read_text())

# Engine menus, kept as the LLM review prompt's reference for which token
# each menu field should be classified into (see spec_build.py/llm_review.md)
# -- no longer used for a deterministic normalize/blocking pass here.
ENGINE_WEIGHTING_MENU: frozenset[str] = frozenset({"ew", "vw"})
ENGINE_RETURN_COMBINATION_MENU: frozenset[str] = frozenset(
    {
        "extreme_group_spread",
        "average_leg_spread",
        "single_signal_portfolio_return",
        "full_portfolio_return",
    }
)
ENGINE_MISSING_ACTION_MENU: frozenset[str] = frozenset({"drop"})
ENGINE_BREAKPOINT_SOURCE_MENU: frozenset[str] = frozenset({"full_sample", "nyse"})


def _evidence_status_finding(field_path: str, sourced_value: SourcedValue) -> Finding | None:
    disposition = DISPOSITION_MATRIX.get(
        (sourced_value.status, EMPIRICAL_IMPACT_HIGH), Disposition.NEEDS_HUMAN_CONFIRMATION
    )
    if disposition == Disposition.AUTO_APPROVE:
        return None
    return Finding(
        field_path=field_path,
        kind="ambiguous",
        reason=f"evidence_status={sourced_value.status.value}",
        empirical_impact="high",
        disposition=disposition,
        paper_value=sourced_value.value,
        evidence=sourced_value.evidence,
    )


def _high_impact_sourced_values(paper: MethodSpec) -> list[tuple[str, SourcedValue]]:
    checks: list[tuple[str, SourcedValue]] = [
        ("signal.direction", paper.signal.direction),
        ("timing.formation_rule", paper.timing.formation_rule),
        ("timing.rebalance_frequency", paper.timing.rebalance_frequency),
        ("timing.holding_period", paper.timing.holding_period),
        ("portfolio.weighting", paper.portfolio.weighting),
        ("portfolio.return_combination", paper.portfolio.return_combination),
        ("portfolio.construction_type", paper.portfolio.construction_type),
        ("universe.description", paper.universe.description),
    ]
    for i, sort in enumerate(paper.portfolio.sorts):
        checks.append((f"portfolio.sorts[{i}].breakpoints.basis", sort.breakpoints.basis))
    return checks


def _missing_mapping_findings(paper: MethodSpec) -> list[Finding]:
    """A universe filter concept_id that isn't ALSO declared as a data.fields
    entry can never resolve to a physical column: build_implementation_
    resolution only runs the catalog matcher on filter concepts as a bare
    `{"field": concept_id}` shim (no paper_name/source_hint to match
    against), and a lag-suffixed pseudo-name the extractor invented for a
    formula step (e.g. "total_assets_t_minus_1") never matches any real
    catalog alias. Previously this passed review silently and only
    surfaced as a confusing step3 "no physical column mapping" 400 (see
    docs/known-gaps-paper-first-v2.md gap #3) -- catch it here as a
    `NEEDS_HUMAN_CONFIRMATION` finding instead of blocking (see module
    docstring: this is not an engine-capability gap, just a missing
    cross-reference a human needs to fill in or remove).
    """
    findings: list[Finding] = []
    data_field_concept_ids = {f.concept_id for f in paper.data.fields}
    for i, filt in enumerate(paper.universe.filters):
        if filt.concept_id not in data_field_concept_ids:
            findings.append(
                Finding(
                    field_path=f"universe.filters[{i}].concept_id",
                    kind="missing_mapping",
                    reason=(
                        "universe filter concept is not declared in data.fields, so it can "
                        "never resolve to a physical column -- add a data.fields entry for "
                        "it (with a real paper_name/paper_source_hint) or drop the filter"
                    ),
                    empirical_impact="high",
                    disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                    paper_value=filt.concept_id,
                )
            )
    return findings


def review_method_spec(
    paper: MethodSpec, capability_version: str = CAPABILITY_VERSION_V1
) -> MethodReview:
    """Deterministic Step2 review: evidence-status findings (D2) +
    missing-mapping findings. No LLM call here -- this is the rule-based
    pass, run both standalone (`/review`) and as the loop-exit check inside
    `spec_build.build_reviewed_method_spec`.
    """
    return MethodReview(
        factor_id=paper.factor_id,
        capability_version=capability_version,
        findings=_compute_findings(paper),
    )


def _compute_findings(
    paper: MethodSpec, status_overrides: dict[str, EvidenceStatus] | None = None
) -> list[Finding]:
    """D2 (evidence-status) + missing-mapping findings, with any
    `status_overrides` substituted in for the extractor's own evidence
    status before the D2 lookup (used by the LLM review loop's
    `field_assessments` handling).
    """
    status_overrides = status_overrides or {}
    findings: list[Finding] = []
    for field_path, sourced_value in _high_impact_sourced_values(paper):
        effective_status = status_overrides.get(field_path, sourced_value.status)
        effective_value = (
            sourced_value
            if field_path not in status_overrides
            else SourcedValue(value=sourced_value.value, evidence=sourced_value.evidence, status=effective_status)
        )
        finding = _evidence_status_finding(field_path, effective_value)
        if finding is not None:
            findings.append(finding)

    findings.extend(_missing_mapping_findings(paper))
    return findings


def apply_value_patches(
    paper: MethodSpec, patches: dict[str, Any], reason: str = "", source: str = "human"
) -> MethodSpec:
    """Correct the extracted VALUE of one or more high-impact fields (e.g.
    the extractor wrote "quarterly" but the paper actually says "annual").
    Called from the human `/patch-value` endpoint with `source="human"` --
    the only caller today. `source` is kept as a parameter (rather than
    hardcoded) so a future non-human caller can still be attributed
    correctly in the evidence citation; the Step2 LLM review loop
    (`spec_build.py`) does NOT call this anymore (2026-08-11: its
    full-trust redesign writes corrected values directly into the spec it
    returns each round, with no separate merge/patch step -- see
    docs/decision-log.md). Only fields `_high_impact_sourced_values`
    already knows about can be patched -- `field_path` comes from the
    client, so this deliberately does NOT do generic attribute-path
    traversal on arbitrary user input; it looks the path up in that fixed,
    known set instead (never reaches an attacker-chosen attribute).

    Returns a NEW `MethodSpec` (the original `paper` is untouched) with each
    patched field's `status` set to `EvidenceStatus.CLEAR` (patching a value
    is itself an affirmation of it, regardless of who did the patching) and
    an evidence citation recording the correction and its `source`. Any
    existing `MethodReview`/`ImplementationResolution` computed against the
    OLD content should be re-run against this new paper -- there is no
    automatic staleness detection forcing that anymore (see
    docs/decision-log.md 2026-08-09 "Removed the paper/review hash-binding
    staleness check").
    """
    patched = paper.model_copy(deep=True)
    patchable = dict(_high_impact_sourced_values(patched))
    for field_path, new_value in patches.items():
        if field_path not in patchable:
            raise ValueError(
                f"{field_path!r} is not a patchable high-impact field "
                f"(must be one of {sorted(patchable)})"
            )
        sourced_value = patchable[field_path]
        sourced_value.value = _coerce_to_current_type(sourced_value.value, new_value, field_path)
        sourced_value.status = EvidenceStatus.CLEAR
        sourced_value.evidence.append(
            EvidenceCitation(interpretation=f"{source} correction: {reason}" if reason else f"{source} correction")
        )
    return patched


def _coerce_to_current_type(current: Any, new_value: Any, field_path: str) -> Any:
    """A UI text input always sends a plain string; several high-impact
    fields are actually `int`/`Enum`-typed (`timing.holding_period`,
    `signal.direction`, ...). Model attribute assignment doesn't re-validate
    types on its own, so a raw string would silently corrupt those fields --
    coerce a string input back to the field's existing type, failing loud
    (not guessing) if it doesn't fit.
    """
    if not isinstance(new_value, str) or current is None:
        return new_value
    if isinstance(current, Enum):
        # Check Enum before the plain-str case below: this project's enums
        # are all `class X(str, Enum)`, so an enum member IS also a `str`
        # instance -- checking `isinstance(current, str)` first would never
        # fire for them.
        try:
            return type(current)(new_value)
        except ValueError:
            raise ValueError(
                f"{field_path!r} expects one of {[m.value for m in type(current)]}, got {new_value!r}"
            ) from None
    if isinstance(current, str):
        return new_value
    if isinstance(current, bool):
        return new_value  # bool is a subclass of int -- never guess true/false from free text
    if isinstance(current, int):
        try:
            return int(new_value)
        except ValueError:
            raise ValueError(f"{field_path!r} expects an integer, got {new_value!r}") from None
    if isinstance(current, float):
        try:
            return float(new_value)
        except ValueError:
            raise ValueError(f"{field_path!r} expects a number, got {new_value!r}") from None
    return new_value


def _field_snapshot(paper: MethodSpec) -> dict[str, dict]:
    return {
        field_path: {
            "value": sourced_value.value,
            "status": sourced_value.status.value,
            "evidence": [c.model_dump(mode="json") for c in sourced_value.evidence],
        }
        for field_path, sourced_value in _high_impact_sourced_values(paper)
    }

