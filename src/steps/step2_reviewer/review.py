"""Deterministic review over the paper-first schema (Phase C). Produces
`MethodReview` from a `MethodSpec` -- NOT wired into `src.pipeline` yet
(see docs/methodspec-v2-plan.md section 9; the original `ReviewGate` in
`src/steps/step2_reviewer/__init__.py` remains the live reviewer until
Step3+ also consume these new artifacts).

Two independent things happen here, deliberately kept separate (design
principle 4, "论文词汇与引擎菜单分离"):

1. Evidence-status-driven findings (D2): every high-impact `SourcedValue`
   field is looked up in `DISPOSITION_MATRIX`; anything that isn't
   `AUTO_APPROVE` becomes a `Finding` of kind "ambiguous"/"inconsistent".
2. Engine-capability findings (D4): construction type, sort-dimension count,
   sort group type, weighting scheme, and return-combination scheme are
   checked against the CURRENT engine capability menu, independent of how
   clearly the paper stated them -- a paper can be perfectly clear about
   using a capped-VW scheme and it is still `kind="unsupported"`,
   `disposition=BLOCKED`.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from src.infra.models.method_spec import (
    CAPABILITY_VERSION_V1,
    DISPOSITION_MATRIX,
    EMPIRICAL_IMPACT_HIGH,
    MAX_SUPPORTED_SORT_DIMENSIONS,
    ConstructionType,
    Disposition,
    EvidenceCitation,
    EvidenceStatus,
    Finding,
    GroupType,
    MethodReview,
    MethodSpec,
    SourcedValue,
)

_LLM_REVIEW_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "review_gate" / "llm_review.md"
)

_LLM_REVIEW_USER_TEMPLATE = """\
Paper text:

{paper_text}

High-impact fields the extractor already assigned an evidence status to
(only these `field_path`s are eligible for re-assessment via
`field_assessments` -- do not invent new ones here):

{fields_json}

Full MethodSpec, for context only. You may cite ANY `field_path` in here
when raising an `additional_findings` entry, but never put one of these
in `field_assessments` unless it also appears in the snapshot above:

{full_spec_json}

Deterministic findings already produced from those statuses (for context
only; re-assessing a field's evidence status is how you change its
disposition, you cannot set `disposition` directly):

{findings_json}

Return the JSON object described in the system prompt.
"""


def load_llm_review_system_prompt() -> str:
    return _LLM_REVIEW_PROMPT_PATH.read_text()

# Engine capability menus (D4) -- deliberately separate from the schema's own
# vocabulary. A value outside these menus is `kind="unsupported"`, not
# "ambiguous": the paper may be perfectly clear, the engine just can't run it.
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


def _capability_findings(paper: MethodSpec) -> list[Finding]:
    findings: list[Finding] = []

    construction_type = paper.portfolio.construction_type.value
    if construction_type is not None and construction_type != ConstructionType.CHARACTERISTIC_SORT:
        findings.append(
            Finding(
                field_path="portfolio.construction_type",
                kind="unsupported",
                reason="engine capability v1 only implements characteristic_sort",
                empirical_impact="high",
                disposition=Disposition.BLOCKED,
                paper_value=construction_type.value,
            )
        )

    if len(paper.portfolio.sorts) > MAX_SUPPORTED_SORT_DIMENSIONS:
        findings.append(
            Finding(
                field_path="portfolio.sorts",
                kind="unsupported",
                reason=f"engine capability v1 supports at most {MAX_SUPPORTED_SORT_DIMENSIONS} sort dimensions",
                empirical_impact="high",
                disposition=Disposition.BLOCKED,
                paper_value=len(paper.portfolio.sorts),
            )
        )

    for i, sort in enumerate(paper.portfolio.sorts):
        if sort.group_type != GroupType.QUANTILE:
            findings.append(
                Finding(
                    field_path=f"portfolio.sorts[{i}].group_type",
                    kind="unsupported",
                    reason="engine capability v1 only implements quantile grouping",
                    empirical_impact="high",
                    disposition=Disposition.BLOCKED,
                    paper_value=sort.group_type.value,
                )
            )

        basis = sort.breakpoints.basis.value
        if basis is not None and basis not in ENGINE_BREAKPOINT_SOURCE_MENU:
            findings.append(
                Finding(
                    field_path=f"portfolio.sorts[{i}].breakpoints.basis",
                    kind="unsupported",
                    reason="not a member of the engine breakpoint-source menu (full_sample/nyse)",
                    empirical_impact="high",
                    disposition=Disposition.BLOCKED,
                    paper_value=getattr(basis, "value", basis),
                )
            )

    # A universe filter concept_id that isn't ALSO declared as a data.fields
    # entry can never resolve to a physical column: build_implementation_
    # resolution only runs the catalog matcher on filter concepts as a bare
    # `{"field": concept_id}` shim (no paper_name/source_hint to match
    # against), and a lag-suffixed pseudo-name the extractor invented for a
    # formula step (e.g. "total_assets_t_minus_1") never matches any real
    # catalog alias. Previously this passed review silently and only
    # surfaced as a confusing step3 "no physical column mapping" 400 (see
    # docs/known-gaps-paper-first-v2.md gap #3) -- catch it here instead.
    data_field_concept_ids = {f.concept_id for f in paper.data.fields}
    for i, filt in enumerate(paper.universe.filters):
        if filt.concept_id not in data_field_concept_ids:
            findings.append(
                Finding(
                    field_path=f"universe.filters[{i}].concept_id",
                    kind="unsupported",
                    reason=(
                        "universe filter concept is not declared in data.fields, so it can "
                        "never resolve to a physical column -- add a data.fields entry for "
                        "it (with a real paper_name/paper_source_hint) or drop the filter"
                    ),
                    empirical_impact="high",
                    disposition=Disposition.BLOCKED,
                    paper_value=filt.concept_id,
                )
            )

    weighting = paper.portfolio.weighting.value
    if weighting is not None and weighting not in ENGINE_WEIGHTING_MENU:
        findings.append(
            Finding(
                field_path="portfolio.weighting",
                kind="unsupported",
                reason="not a member of the engine weighting menu (ew/vw)",
                empirical_impact="high",
                disposition=Disposition.BLOCKED,
                paper_value=getattr(weighting, "value", weighting),
            )
        )

    return_combination = paper.portfolio.return_combination.value
    if return_combination and return_combination not in ENGINE_RETURN_COMBINATION_MENU:
        findings.append(
            Finding(
                field_path="portfolio.return_combination",
                kind="unsupported",
                reason="not a member of the engine return-combination menu",
                empirical_impact="high",
                disposition=Disposition.BLOCKED,
                paper_value=return_combination,
            )
        )

    for i, mp in enumerate(paper.portfolio.missing_policies):
        action = mp.action.value
        if action is not None and action not in ENGINE_MISSING_ACTION_MENU:
            findings.append(
                Finding(
                    field_path=f"portfolio.missing_policies[{i}].action",
                    kind="unsupported",
                    reason="not a member of the engine missing-data-action menu (drop)",
                    empirical_impact="high",
                    disposition=Disposition.BLOCKED,
                    paper_value=getattr(action, "value", action),
                )
            )

    return findings


def review_method_spec(
    paper: MethodSpec, capability_version: str = CAPABILITY_VERSION_V1
) -> MethodReview:
    """Deterministic Step2 review: evidence-status findings (D2) + engine
    capability findings (D4). No LLM call here -- this is the rule-based
    pass; `review_method_spec_with_llm`/`apply_human_status_overrides` below
    are the LLM-assisted and human-override passes (mirror v1's
    `review_with_llm`).
    """
    return MethodReview(
        factor_id=paper.factor_id,
        capability_version=capability_version,
        findings=_compute_findings(paper),
    )


def _compute_findings(
    paper: MethodSpec, status_overrides: dict[str, EvidenceStatus] | None = None
) -> list[Finding]:
    """D2 (evidence-status) + D4 (engine-capability) findings, with any
    `status_overrides` substituted in for the extractor's own evidence
    status before the D2 lookup -- shared by the rule-based, LLM-assisted,
    and human-override review passes so all three run the exact same
    deterministic `DISPOSITION_MATRIX` logic.
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

    findings.extend(_capability_findings(paper))
    return findings


def apply_human_status_overrides(
    paper: MethodSpec,
    status_overrides: dict[str, EvidenceStatus],
    capability_version: str = CAPABILITY_VERSION_V1,
) -> MethodReview:
    """A human reviewer directly asserts a corrected `EvidenceStatus` for one
    or more high-impact fields (e.g. "I re-read Section 3, the paper does
    state this clearly") -- no LLM call, but the same deterministic
    `DISPOSITION_MATRIX` decides the resulting finding/disposition. This is
    the manual-resolution path for D2 (evidence-status) findings; D4
    (engine-capability/"unsupported") findings can never be overridden this
    way (see `AGENTS.md` hard constraints -- an out-of-menu construction
    choice is a fixed engine-capability gap, not an evidence dispute).
    """
    return MethodReview(
        factor_id=paper.factor_id,
        capability_version=capability_version,
        findings=_compute_findings(paper, status_overrides),
        status_overrides=status_overrides,
    )


def apply_human_value_patches(
    paper: MethodSpec, patches: dict[str, Any], reason: str = ""
) -> MethodSpec:
    """A human directly corrects the extracted VALUE of one or more
    high-impact fields (e.g. the extractor wrote "quarterly" but the paper
    actually says "annual") -- distinct from `apply_human_status_overrides`,
    which only corrects how confidently we can attribute an ALREADY-CORRECT
    value to the paper. Only fields `_high_impact_sourced_values` already
    knows about can be patched -- `field_path` comes from the client, so
    this deliberately does NOT do generic attribute-path traversal on
    arbitrary user input; it looks the path up in that fixed, known set
    instead (never reaches an attacker-chosen attribute).

    Returns a NEW `MethodSpec` (the original `paper` is untouched) with each
    patched field's `status` set to `EvidenceStatus.CLEAR` (a human just
    affirmed it) and an evidence citation recording the correction. Any
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
            EvidenceCitation(interpretation=f"human correction: {reason}" if reason else "human correction")
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


def review_method_spec_with_llm(
    paper: MethodSpec,
    paper_text: str,
    llm_client,
    capability_version: str = CAPABILITY_VERSION_V1,
) -> tuple[MethodReview, dict]:
    """LLM-assisted Step2 pass: re-reads `paper_text` to double-check the
    extractor's `EvidenceStatus` call for each high-impact `SourcedValue`
    field (D2) -- e.g. the extractor labeled a field "unspecified" but the
    paper actually states it clearly, or labeled it "clear" but two passages
    conflict.

    The LLM does NOT get to decide `disposition` or approve/block anything
    directly: it may only propose a replacement `EvidenceStatus` per
    snapshot field (recorded in `MethodReview.status_overrides`), which is
    then run back through the same deterministic `DISPOSITION_MATRIX` used
    by `review_method_spec`. The full spec is also included (for context
    only) so the LLM can flag brand-new "inconsistent" `additional_findings`
    against ANY field_path, not just the snapshot -- these are always
    forced to `NEEDS_HUMAN_CONFIRMATION` (never auto-approved on the LLM's
    own authority). Engine-capability findings (D4) are untouched -- those
    are a fixed menu check, not evidence interpretation.
    """
    base_review = review_method_spec(paper, capability_version)
    snapshot = _field_snapshot(paper)

    messages = [
        {"role": "system", "content": load_llm_review_system_prompt()},
        {
            "role": "user",
            "content": _LLM_REVIEW_USER_TEMPLATE.format(
                paper_text=paper_text,
                fields_json=json.dumps(snapshot, indent=2, default=str),
                full_spec_json=json.dumps(paper.model_dump(mode="json"), indent=2, default=str),
                findings_json=json.dumps(
                    [f.model_dump(mode="json") for f in base_review.findings], indent=2
                ),
            ),
        },
    ]
    response = llm_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw: dict = json.loads(response.choices[0].message.content)

    status_overrides: dict[str, EvidenceStatus] = {}
    for item in raw.get("field_assessments") or []:
        field_path = item.get("field_path")
        if field_path not in snapshot:
            continue  # LLM can only re-assess a field it was actually shown
        try:
            status_overrides[field_path] = EvidenceStatus(item.get("evidence_status"))
        except ValueError:
            continue  # not a member of the fixed EvidenceStatus menu -- ignore

    findings = _compute_findings(paper, status_overrides)

    seen_paths = {f.field_path for f in findings}
    for item in raw.get("additional_findings") or []:
        field_path = item.get("field_path")
        if not field_path or field_path in seen_paths:
            continue
        findings.append(
            Finding(
                field_path=field_path,
                kind="inconsistent",
                reason=f"llm-flagged: {item.get('reason', '')}",
                empirical_impact="high",
                disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                paper_value=None,
            )
        )
        seen_paths.add(field_path)

    review = MethodReview(
        factor_id=paper.factor_id,
        capability_version=capability_version,
        findings=findings,
        status_overrides=status_overrides,
    )
    return review, raw
