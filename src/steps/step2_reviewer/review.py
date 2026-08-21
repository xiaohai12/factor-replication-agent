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

from src.infra.market_equity_policy import (
    market_equity_contract_errors,
    requires_crsp_fiscal_year_end_market_equity,
)
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


def _evidence_status_finding(
    field_path: str, sourced_value: SourcedValue, *, always: bool = False
) -> Finding | None:
    disposition = DISPOSITION_MATRIX.get(
        (sourced_value.status, EMPIRICAL_IMPACT_HIGH), Disposition.NEEDS_HUMAN_CONFIRMATION
    )
    if disposition == Disposition.AUTO_APPROVE and not always:
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


def high_impact_sourced_values(paper: MethodSpec) -> list[tuple[str, SourcedValue]]:
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
        checks.append((f"portfolio.sorts[{i}].group_type", sort.group_type))
        checks.append((f"portfolio.sorts[{i}].mode", sort.mode))
    for i, policy in enumerate(paper.portfolio.missing_policies):
        checks.append((f"portfolio.missing_policies[{i}].action", policy.action))
    for i, f in enumerate(paper.data.fields):
        checks.append((f"data.fields[{i}].source_table", f.source_table))
        checks.append((f"data.fields[{i}].source_column", f.source_column))
    return checks


def _citation_key(citation: EvidenceCitation) -> tuple[str, ...] | None:
    """Stable, deliberately literal key for universe-evidence coverage.

    The extractor is required to reuse a restriction's original citation on
    the corresponding ``FilterSpec``.  We therefore compare the quoted text
    (or, for table-only evidence, the complete table coordinate), rather than
    trying to infer a restriction's meaning from keywords such as ``NYSE`` or
    ``SIC``.  A citation with neither form cannot establish coverage.
    """
    quote = " ".join(citation.quote.lower().split())
    if quote:
        return ("quote", quote)
    if citation.table_ref is not None:
        return (
            "table",
            citation.table_ref.table.strip().lower(),
            citation.table_ref.row.strip().lower(),
            citation.table_ref.column.strip().lower(),
        )
    return None


def _universe_evidence_coverage_findings(paper: MethodSpec) -> list[Finding]:
    """Require each cited universe restriction to be represented by a filter.

    This is intentionally generic: it never identifies exchanges, industries,
    share classes, or any other particular screen.  Instead it enforces the
    structural contract that a paper citation used to support the universe
    description must also be carried by an executable ``FilterSpec``. A cited
    filter is executable only when its corresponding data field has a real
    source-table/column mapping; a made-up filter with an ``other`` source is
    not evidence coverage. An explicitly ``accepted_unapplied`` filter remains
    a valid documented human decision. An unmatched citation is a high-impact
    human-review decision, never an automatic rewrite.
    """
    fields_by_concept = {field.concept_id: field for field in paper.data.fields}

    def is_covered_filter(filt: Any) -> bool:
        if filt.accepted_unapplied:
            return bool(filt.unapplied_reason.strip())
        field = fields_by_concept.get(filt.concept_id)
        if field is None:
            return False
        source_table = _unwrap_enum_value(field.source_table.value)
        return source_table not in {"other", "unspecified"} and field.source_column.value is not None

    covered = {
        key
        for filt in paper.universe.filters
        if is_covered_filter(filt)
        for citation in filt.evidence
        if (key := _citation_key(citation)) is not None
    }
    findings: list[Finding] = []
    for i, citation in enumerate(paper.universe.description.evidence):
        key = _citation_key(citation)
        if key is None or key in covered:
            continue
        findings.append(
            Finding(
                field_path=f"universe.description.evidence[{i}]",
                kind="incomplete",
                reason=(
                    "Universe evidence is not attached to an executable universe.filters entry. "
                    "Add a cited filter with a real data.fields source/column mapping, or record "
                    "the stated restriction as accepted_unapplied with a reason."
                ),
                empirical_impact="high",
                disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                paper_value=citation.quote or citation.table_ref.model_dump(),
                evidence=[citation],
            )
        )
    return findings


def _universe_filter_high_impact_entries(paper: MethodSpec) -> list[Finding]:
    """Surface every declared universe filter in the human-review panel."""
    return [
        Finding(
            field_path=f"universe.filters[{i}]",
            kind="universe_filter",
            reason="Universe membership restriction; confirm its evidence and runtime applicability.",
            empirical_impact="high",
            disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
            paper_value={"concept_id": filt.concept_id, "op": filt.op.value, "value": filt.value},
            evidence=filt.evidence,
        )
        for i, filt in enumerate(paper.universe.filters)
    ]


#: field_paths whose classified value is checked against a fixed engine
#: menu (docs/resolve-diagnostics-gaps.md problem 2) -- any of these ending
#: up "other" gets an UNCONDITIONAL Finding (regardless of `EvidenceStatus`),
#: since `DISPOSITION_MATRIX` alone would miss it whenever `status` is
#: `clear`/`table_only` (the LLM being confident the paper said something
#: off-menu is not the same as the field being auto-approved). `sort.mode`
#: is included even though `within_group` (a DIFFERENT, non-"other" value)
#: is also unsupported today -- that case is handled separately by
#: `registry.build_config`'s pass-through + engine fail-loud, not here,
#: since it's a known/named value, not a paper-vocabulary classification
#: gap (see `SortMode`'s docstring).
_ENGINE_MENU_FIELD_PATHS: frozenset[str] = frozenset({
    "portfolio.weighting",
    "portfolio.return_combination",
    "portfolio.construction_type",
})


def _is_engine_menu_field(field_path: str) -> bool:
    if field_path in _ENGINE_MENU_FIELD_PATHS:
        return True
    return field_path.endswith((".breakpoints.basis", ".group_type", ".mode", ".action", ".source_table"))


def _unwrap_enum_value(value: Any) -> str:
    """Same purpose as `registry.ev()` (unwrap an Enum member's `.value`,
    or return a plain string as-is) -- duplicated here rather than imported
    to avoid step2_reviewer depending on step3_codegen."""
    if hasattr(value, "value"):
        return value.value
    return str(value) if value is not None else "unspecified"


def _engine_menu_unsupported_finding(field_path: str, sourced_value: SourcedValue) -> Finding | None:
    """Unconditional counterpart to `_evidence_status_finding` for engine-menu
    fields: fires whenever `value == "other"`, independent of `status` (see
    `_ENGINE_MENU_FIELD_PATHS` docstring). `paper_value` uses
    `unsupported_value` (the paper's literal wording) when available --
    plain `"other"` carries no information on its own.
    """
    if _unwrap_enum_value(sourced_value.value) != "other":
        return None
    unsupported_value = getattr(sourced_value, "unsupported_value", None)
    return Finding(
        field_path=field_path,
        kind="unsupported",
        reason=(
            f"paper's stated method ({unsupported_value!r}) is not in the engine's "
            "menu; the backtest will use a documented default unless corrected "
            "(see resolved config's defaults_applied)."
        ),
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value=unsupported_value if unsupported_value is not None else "other",
        evidence=sourced_value.evidence,
    )


def _rebalance_frequency_capability_finding(paper: MethodSpec) -> Finding | None:
    """`timing.rebalance_frequency` is a `TimeUnit`, not a menu enum with
    `OTHER` -- `DAY` is a specific, known, unimplemented value (see
    docs/resolve-diagnostics-gaps.md problem 2), not free text. Checked here
    (paper-only data, no `resolution.concept_mapping` needed) so a human
    sees it at review time, same posture as the engine-menu check above."""
    from src.infra.models.method_spec import TimeUnit

    freq = paper.timing.rebalance_frequency
    if freq.value != TimeUnit.DAY:
        return None
    return Finding(
        field_path="timing.rebalance_frequency",
        kind="unsupported",
        reason=(
            "paper specifies daily rebalancing, which the engine's "
            "rebalance_frequency config (annual/quarterly/monthly) can't "
            "represent -- will default to monthly unless corrected."
        ),
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value="day",
        evidence=freq.evidence,
    )


def _lag_unit_capability_finding(paper: MethodSpec) -> Finding | None:
    """Same posture as `_rebalance_frequency_capability_finding`, for
    `timing.data_availability.lag_unit` -- `DAY` is specific and known, the
    accounting_lag_months config field just can't represent it (month
    granularity)."""
    from src.infra.models.method_spec import TimeUnit

    availability = paper.timing.data_availability
    if availability.lag_value is None or availability.lag_unit != TimeUnit.DAY:
        return None
    return Finding(
        field_path="timing.data_availability.lag_unit",
        kind="unsupported",
        reason=(
            f"paper specifies a {availability.lag_value}-day accounting lag, which "
            "this month-granularity config field can't represent -- will default "
            "to 6 months unless corrected."
        ),
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value=f"{availability.lag_value} day(s)",
        evidence=availability.evidence,
    )


def _sort_dimension_count_finding(paper: MethodSpec) -> Finding | None:
    """`portfolio.sorts` count > `MAX_SUPPORTED_SORT_DIMENSIONS` -- structural,
    not an enum, so there's no `unsupported_value` to report (the paper's
    full sort list is already preserved as-is in `paper.portfolio.sorts`,
    no information loss)."""
    from src.infra.models.method_spec import MAX_SUPPORTED_SORT_DIMENSIONS

    sorts = paper.portfolio.sorts
    if len(sorts) <= MAX_SUPPORTED_SORT_DIMENSIONS:
        return None
    return Finding(
        field_path="portfolio.sorts",
        kind="unsupported",
        reason=(
            f"{len(sorts)} sort dimensions declared, but the engine supports at most "
            f"{MAX_SUPPORTED_SORT_DIMENSIONS} -- the target dimension plus the "
            "lowest-order control dimension(s) will be kept, the rest dropped, "
            "unless corrected."
        ),
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value=len(sorts),
    )


def _primary_metric_weighting_finding(paper: MethodSpec) -> Finding | None:
    """`reported_results.primary_metric_id` drives what Step7 compares our
    backtest track against (see `_spec_paper_reported` in
    step5_backtest_runner); if that metric's own `weighting` disagrees with
    `portfolio.weighting` (the weighting the engine will actually run),
    Step7 silently compares our vw track against the paper's ew column (or
    vice versa) -- a metadata mismatch, not a real replication gap. Only
    fires when the metric actually carries a `weighting` tag (never guess
    when the extractor/reviewer left it unset)."""
    rr = paper.reported_results
    primary = rr.primary_comparison_metric()
    if primary is None or primary.weighting is None:
        return None
    if primary.weighting == paper.portfolio.weighting.value:
        return None
    return Finding(
        field_path="reported_results.primary_metric_id",
        kind="inconsistent",
        reason=(
            f"primary_metric_id={primary.metric_id!r} is tagged weighting="
            f"{primary.weighting.value!r}, but portfolio.weighting="
            f"{paper.portfolio.weighting.value!r} -- Step7 would compare the "
            "backtest track against the wrong paper column. Point primary_metric_id "
            "at the metric matching portfolio.weighting, or confirm the paper only "
            "reports the other weighting (methodologically non-comparable)."
        ),
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value=primary.weighting.value,
    )


def _comparison_derivation_finding(paper: MethodSpec) -> Finding | None:
    """Ensure an opt-in table endpoint spread remains a valid, executable
    comparison instead of a convenient but incompatible subtraction."""
    rr = paper.reported_results
    derivation = rr.comparison_derivation
    if derivation is None:
        return None
    by_id = {metric.metric_id: metric for metric in rr.metrics}
    high = by_id[derivation.high_metric_id]
    low = by_id[derivation.low_metric_id]
    incompatible = [
        field
        for field in ("unit", "frequency", "weighting", "adjustment_model", "sample_period")
        if getattr(high, field) != getattr(low, field)
    ]
    target_sort = next(
        (
            sort
            for sort in paper.portfolio.sorts
            if high.portfolio_selector is not None
            and low.portfolio_selector is not None
            and sort.sort_id in high.portfolio_selector
            and sort.sort_id in low.portfolio_selector
        ),
        None,
    )
    endpoints_ok = (
        target_sort is not None
        and target_sort.group_count is not None
        and high.portfolio_selector == {target_sort.sort_id: target_sort.group_count - 1}
        and low.portfolio_selector == {target_sort.sort_id: 0}
    )
    leg_selectors = {(leg.side, tuple(sorted(leg.selector.items()))) for leg in paper.portfolio.legs}
    executable = (
        paper.portfolio.return_combination.value.value == "extreme_group_spread"
        and target_sort is not None
        and target_sort.group_count is not None
        and ("long", tuple(sorted({target_sort.sort_id: target_sort.group_count - 1}.items()))) in leg_selectors
        and ("short", tuple(sorted({target_sort.sort_id: 0}.items()))) in leg_selectors
    )
    if not incompatible and endpoints_ok and executable:
        return None
    reasons: list[str] = []
    if incompatible:
        reasons.append("endpoint metrics disagree on " + ", ".join(incompatible))
    if not endpoints_ok:
        reasons.append("endpoint metric selectors are not the target sort's low and high buckets")
    if not executable:
        reasons.append("portfolio legs/return combination do not implement the requested high-minus-low spread")
    return Finding(
        field_path="reported_results.comparison_derivation",
        kind="inconsistent",
        reason="; ".join(reasons) + ".",
        empirical_impact="high",
        disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
        paper_value=derivation.model_dump(mode="json"),
    )


def _missing_mapping_findings(paper: MethodSpec) -> list[Finding]:
    """A universe filter concept_id that isn't ALSO declared as a data.fields
    entry can never resolve to a physical column: build_implementation_
    resolution only runs the catalog matcher on filter concepts as a bare
    `{"field": concept_id}` shim (no name_in_paper/source_hint to match
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
                        "it (with a real name_in_paper/paper_source_hint) or drop the filter"
                    ),
                    empirical_impact="high",
                    disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                    paper_value=filt.concept_id,
                )
            )
    return findings


def _disjoint_between_filter_findings(paper: MethodSpec) -> list[Finding]:
    """Flag same-field interval intersections that make the universe empty.

    The filter list is intentionally AND-only. Disjoint ranges in one paper
    clause normally mean an allowed-range union, but this reviewer must never
    silently rewrite paper facts, so it asks for human confirmation of the
    explicit ``intervals`` predicate instead.
    """
    by_concept: dict[str, list[tuple[int, list[float]]]] = {}
    for i, filt in enumerate(paper.universe.filters):
        value = filt.value
        if (
            not filt.accepted_unapplied
            and filt.op.value == "between"
            and isinstance(value, list)
            and len(value) == 2
            and all(isinstance(bound, (int, float)) and not isinstance(bound, bool) for bound in value)
            and value[0] <= value[1]
        ):
            by_concept.setdefault(filt.concept_id, []).append((i, value))

    findings: list[Finding] = []
    for concept_id, intervals in by_concept.items():
        if len(intervals) < 2:
            continue
        ordered = sorted(intervals, key=lambda item: item[1][0])
        if any(right[1][0] > left[1][1] for left, right in zip(ordered, ordered[1:])):
            indices = [i for i, _ in intervals]
            findings.append(
                Finding(
                    field_path=f"universe.filters[{indices[0]}]",
                    kind="inconsistent",
                    reason=(
                        f"{concept_id!r} has disjoint top-level 'between' filters at indices {indices}. "
                        "Top-level universe filters are combined with AND, so this produces an empty universe. "
                        "If the paper means a union of allowed intervals, replace them with one "
                        "FilterOp.intervals value such as [[low1, high1], [low2, high2]]."
                    ),
                    empirical_impact="high",
                    disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                    paper_value=[value for _, value in intervals],
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
        all_high_impact_fields=_all_high_impact_field_findings(paper),
    )


def _all_high_impact_field_findings(paper: MethodSpec) -> list[Finding]:
    """Same per-field disposition logic `_compute_findings` uses, but
    ALWAYS emits one `Finding` per `high_impact_sourced_values` entry --
    including `AUTO_APPROVE` ones `_compute_findings` skips -- so the review
    UI can list every high-impact field's current value and gate its
    dropdown/input on `disposition` instead of on whether it produced a
    finding at all."""
    entries: list[Finding] = []
    for field_path, sourced_value in high_impact_sourced_values(paper):
        if _is_engine_menu_field(field_path):
            menu_finding = _engine_menu_unsupported_finding(field_path, sourced_value)
            if menu_finding is not None:
                entries.append(menu_finding)
                continue
        finding = _evidence_status_finding(field_path, sourced_value, always=True)
        if finding is not None:
            entries.append(finding)
    entries.extend(_universe_filter_high_impact_entries(paper))
    return entries


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
    for field_path, sourced_value in high_impact_sourced_values(paper):
        effective_status = status_overrides.get(field_path, sourced_value.status)
        effective_value = (
            sourced_value
            if field_path not in status_overrides
            else SourcedValue(value=sourced_value.value, evidence=sourced_value.evidence, status=effective_status)
        )
        # Engine-menu fields classified "other" get the unconditional check
        # below INSTEAD of the status-based D2 check -- otherwise a field
        # that's both "other" and e.g. `status=inferred` would produce two
        # separate Findings for the same field_path (docs/resolve-
        # diagnostics-gaps.md problem 2, "实现前复查" section A).
        if _is_engine_menu_field(field_path):
            menu_finding = _engine_menu_unsupported_finding(field_path, effective_value)
            if menu_finding is not None:
                findings.append(menu_finding)
                continue
        finding = _evidence_status_finding(field_path, effective_value)
        if finding is not None:
            findings.append(finding)

    for capability_finding in (
        _rebalance_frequency_capability_finding(paper),
        _lag_unit_capability_finding(paper),
        _sort_dimension_count_finding(paper),
        _primary_metric_weighting_finding(paper),
        _comparison_derivation_finding(paper),
    ):
        if capability_finding is not None:
            findings.append(capability_finding)

    findings.extend(_missing_mapping_findings(paper))
    findings.extend(_disjoint_between_filter_findings(paper))
    findings.extend(_universe_evidence_coverage_findings(paper))
    if requires_crsp_fiscal_year_end_market_equity(paper):
        for error in market_equity_contract_errors(paper):
            findings.append(
                Finding(
                    field_path="signal.formula",
                    kind="unsupported",
                    reason=(
                        "Approved implementation policy for Dichev Z-score requires CCM-aligned "
                        "CRSP abs(prc) * shrout / 1000 at fiscal year end and Compustat lt: " + error
                    ),
                    empirical_impact="high",
                    disposition=Disposition.NEEDS_HUMAN_CONFIRMATION,
                    paper_value="CRSP fiscal-year-end market equity",
                )
            )
    return findings


def apply_value_patches(
    paper: MethodSpec,
    patches: dict[str, Any],
    reason: str = "",
    source: str = "human",
    unsupported_values: dict[str, str] | None = None,
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

    `unsupported_values` (field_path -> the paper's literal wording) is only
    honored when that same `field_path` is being patched TO the enum's
    `other` member -- it fills `SourcedValue.unsupported_value`, whose own
    model validator otherwise rejects a non-null `unsupported_value` on a
    non-"other" value. Patching a field AWAY FROM "other" clears any stale
    `unsupported_value` it was carrying, so a later re-review doesn't see a
    contradictory combination.

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
    patchable = dict(high_impact_sourced_values(patched))
    unsupported_values = unsupported_values or {}
    for field_path, new_value in patches.items():
        if field_path not in patchable:
            raise ValueError(
                f"{field_path!r} is not a patchable high-impact field "
                f"(must be one of {sorted(patchable)})"
            )
        sourced_value = patchable[field_path]
        sourced_value.value = _coerce_to_current_type(sourced_value.value, new_value, field_path)
        is_other = str(getattr(sourced_value.value, "value", sourced_value.value)) == "other"
        sourced_value.unsupported_value = unsupported_values.get(field_path) if is_other else None
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
        for field_path, sourced_value in high_impact_sourced_values(paper)
    }
