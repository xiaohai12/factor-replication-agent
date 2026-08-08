"""Deterministic review over the paper-first schema (Phase C). Produces
`MethodReview` from a `PaperMethodSpec` -- NOT wired into `src.pipeline` yet
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

from src.infra.models.paper_method_spec import (
    CAPABILITY_VERSION_V1,
    ConstructionType,
    DISPOSITION_MATRIX,
    Disposition,
    EMPIRICAL_IMPACT_HIGH,
    Finding,
    GroupType,
    MAX_SUPPORTED_SORT_DIMENSIONS,
    MethodReview,
    PaperMethodSpec,
    SourcedValue,
)

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


def _high_impact_sourced_values(paper: PaperMethodSpec) -> list[tuple[str, SourcedValue]]:
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
        checks.append((f"portfolio.sorts[{i}].breakpoints.population", sort.breakpoints.population))
    return checks


def _capability_findings(paper: PaperMethodSpec) -> list[Finding]:
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

    weighting = paper.portfolio.weighting.value
    if weighting and weighting not in ENGINE_WEIGHTING_MENU:
        findings.append(
            Finding(
                field_path="portfolio.weighting",
                kind="unsupported",
                reason="not a member of the engine weighting menu (ew/vw)",
                empirical_impact="high",
                disposition=Disposition.BLOCKED,
                paper_value=weighting,
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

    return findings


def review_paper_method_spec(
    paper: PaperMethodSpec, capability_version: str = CAPABILITY_VERSION_V1
) -> MethodReview:
    """Deterministic Step2 review: evidence-status findings (D2) + engine
    capability findings (D4). No LLM call here -- this is the rule-based
    pass; an optional LLM-assisted discovery pass (mirroring v1's
    `review_with_llm`) is deferred to a later iteration.
    """
    findings: list[Finding] = []
    for field_path, sourced_value in _high_impact_sourced_values(paper):
        finding = _evidence_status_finding(field_path, sourced_value)
        if finding is not None:
            findings.append(finding)

    findings.extend(_capability_findings(paper))

    return MethodReview(
        factor_id=paper.factor_id,
        paper_spec_hash=paper.content_hash(),
        capability_version=capability_version,
        findings=findings,
    )
