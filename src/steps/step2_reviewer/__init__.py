"""Review Gate - Validate MethodSpec before code generation.

Implements the Review Decision Matrix from docs/architecture.md Section 4.3:
- LLM Reviewer (default picky: reject over approve when uncertain)
- Evidence × Impact classification
- Disposition: auto_approve | needs_llm_review | needs_human_confirmation
- Sensible defaults for unspecified fields
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.infra.data_layer import DataDictionary
from src.infra.models.method_spec import (
    BreakpointSource,
    EvidenceCitation,
    EmpiricalImpact,
    EvidenceSource,
    MethodSpec,
    MissingAction,
    PortfolioConstructionType,
    RebalanceFrequency,
    RemediationMode,
    ReturnCombinationType,
    WeightingRule,
)

DEFAULT_REVIEW_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "review_gate" / "methodspec_audit.md"

_LLM_REVIEW_CONTRACT = """
Return exactly one JSON object with this shape:
{
  "review_id": "string",
  "methodspec_version": "string",
  "reviewer": "string",
  "disposition": "approved|revision_required|blocked",
  "remediation_mode": "patch_existing_json|targeted_reextraction|full_regeneration",
  "codegen_ready": true,
  "paper_faithful": true,
  "approved": true,
  "issues": ["string"],
  "warnings": ["string"],
  "field_notes": [
    {
      "field": "dotted.path",
      "severity": "P0|P1|P2|P3",
      "status": "auto_approve|auto_approve_with_flag|approve_with_default|needs_llm_review|needs_human_confirmation",
      "reason": "string",
      "current_value": "any JSON value",
      "candidate_value": "any JSON value",
      "empirical_impact": "high|low",
      "evidence": [{"location": "string", "quote": "string", "interpretation": "string", "source_type": "paper"}]
    }
  ],
  "blocked_fields": ["dotted.path"],
  "requires_human": true,
  "markdown_report": "full markdown review report"
}
Rules:
- blocked_fields must equal the subset of field_notes whose status is needs_human_confirmation.
- approved must be true iff disposition is approved.
- codegen_ready must be false for blocked or revision_required outputs.
- If a field is paper-silent but high-impact, mark status needs_human_confirmation.
- Respond with JSON only.
""".strip()


# --- Review Decision Matrix ---

# High-impact fields: changes materially affect empirical results
HIGH_IMPACT_FIELDS = {
    "signal.formula",
    "signal.sign",
    "signal.timing.accounting_lag",
    "timing.accounting_lag_months",
    "signal.timing.formation_month",
    "signal.timing.rebalance_frequency",
    "signal.timing.holding_period",
    "signal.missing_policy",
    "portfolio.sort.breakpoint_source",
    "portfolio.sort.ls_quantile",
    "portfolio.weighting",
    "portfolio.universe",
    "portfolio.universe_filters",
    "portfolio.long_leg",
    "portfolio.short_leg",
    "portfolio.implied_factor_direction",
    "portfolio.construction_type",
    "portfolio.return_combination",
    "reported_results.return_horizon",
    "reported_results.spreads",
}

# Field-level defaults for a paper-SILENT field — the per-field convention used
# to keep `original_method` faithful to the paper when the paper doesn't state a
# value. Keyed by dotted MethodSpec path (NOT engine-config keys). This is a
# DIFFERENT concept from step6's HXZ_STANDARD_CONFIG, which deliberately forces
# every factor onto ONE uniform house standard; here we only fill a gap with the
# field's own convention. The two legitimately disagree where the field-level
# default differs from the standardized protocol — most notably rebalance is
# "annual" here (the usual default for an unspecified accounting-factor
# rebalance, Fama-French/C&Z convention) vs "monthly" in the standardized track
# (HXZ protocol). Provenance: 6-month accounting lag = Fama-French (1992);
# NYSE breakpoints + value weighting = Hou, Xue & Zhang (2020). Do not merge
# with HXZ_STANDARD_CONFIG. See docs/cz-reference.md §7.
SENSIBLE_DEFAULTS = {
    "signal.timing.accounting_lag": 6,
    "signal.missing_policy.action": "drop",
    "signal.timing.formation_month": 6,
    "portfolio.sort.breakpoint_source": "nyse",
    "portfolio.weighting": "vw",
    "signal.timing.rebalance_frequency": "annual",
}


def _is_invalid_ls_quantile(value: float | None) -> bool:
    """True when `portfolio.sort.ls_quantile` is either unset (`None`) or a
    numerically invalid/degenerate value for a long-short breakpoint sort:
    `<= 0`, a `> 1` value that doesn't round to at least 2 whole groups
    (e.g. `1.5` -> 2 groups is fine, but `1` or `1.4` -> < 2 is not), or a
    fraction outside `(0, 0.5]` (a fraction `> 0.5` would mean fewer than 2
    groups). Kept independent of (not imported from)
    `registry._resolve_ls_quantile`, which silently CLAMPS exactly these
    same invalid values to the standard 10-group default -- that clamp
    keeps `build_config` crash-safe for an already-approved spec, but an
    EXPLICIT invalid value (e.g. `-1`, not just an unset `None`) should never
    have been approved as `paper_faithful` in the first place. See
    docs/decision-log.md for the gap this closes.
    """
    if value is None:
        return True
    if value > 1:
        return round(value) < 2
    return not (0 < value <= 0.5)


def _is_invalid_formation_month(value: int | None) -> bool:
    """True when `signal.timing.formation_month` is either unset (`None`) or
    outside the valid calendar-month range 1-12. Like `_is_invalid_ls_quantile`,
    this catches an EXPLICIT out-of-range value (e.g. `13`) that
    `registry.build_config` would otherwise pass through / default silently,
    approving a nonsensical formation calendar as `paper_faithful`. See
    docs/decision-log.md for the gap this closes."""
    if value is None:
        return True
    return not (1 <= value <= 12)


class Disposition(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_APPROVE_WITH_FLAG = "auto_approve_with_flag"
    APPROVE_WITH_DEFAULT = "approve_with_default"
    NEEDS_LLM_REVIEW = "needs_llm_review"
    NEEDS_HUMAN_CONFIRMATION = "needs_human_confirmation"


@dataclass
class FieldReviewNote:
    """Review note for a single field."""

    field: str
    status: Disposition
    reason: str = ""
    current_value: object = None
    candidate_value: object = None
    empirical_impact: str = ""
    evidence: list[EvidenceCitation] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Result of MethodSpec review."""

    review_id: str = ""
    methodspec_version: str = "v1"
    reviewer: str = "llm"  # llm | human
    disposition: str = "pending"  # approved | revision_required | blocked
    remediation_mode: str = RemediationMode.RESOLVE_EXISTING_JSON.value
    codegen_ready: bool = False
    paper_faithful: bool = False
    approved: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_notes: list[FieldReviewNote] = field(default_factory=list)
    blocked_fields: list[str] = field(default_factory=list)
    requires_human: bool = False


def classify_disposition(
    evidence: EvidenceSource, impact: EmpiricalImpact
) -> Disposition:
    """Apply the Review Decision Matrix to determine disposition.

    | Evidence \\ Impact  | Low impact                | High impact                    |
    |---------------------|---------------------------|--------------------------------|
    | Clear               | auto_approve              | auto_approve                   |
    | Single              | auto_approve_with_flag    | needs_llm_review               |
    | Inferred            | approve_with_default+flag | needs_human_confirmation       |
    | Conflicting         | needs_llm_review          | needs_human_confirmation       |
    """
    matrix = {
        (EvidenceSource.CLEAR, EmpiricalImpact.LOW): Disposition.AUTO_APPROVE,
        (EvidenceSource.CLEAR, EmpiricalImpact.HIGH): Disposition.AUTO_APPROVE,
        (EvidenceSource.SINGLE, EmpiricalImpact.LOW): Disposition.AUTO_APPROVE_WITH_FLAG,
        (EvidenceSource.SINGLE, EmpiricalImpact.HIGH): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.INFERRED, EmpiricalImpact.LOW): Disposition.APPROVE_WITH_DEFAULT,
        (EvidenceSource.INFERRED, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.UNSPECIFIED, EmpiricalImpact.LOW): Disposition.APPROVE_WITH_DEFAULT,
        (EvidenceSource.UNSPECIFIED, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.WEAK_OR_CONFLICTING, EmpiricalImpact.LOW): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.WEAK_OR_CONFLICTING, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
        (EvidenceSource.CONFLICTING, EmpiricalImpact.LOW): Disposition.NEEDS_LLM_REVIEW,
        (EvidenceSource.CONFLICTING, EmpiricalImpact.HIGH): Disposition.NEEDS_HUMAN_CONFIRMATION,
    }
    return matrix[(evidence, impact)]


class ReviewGate:
    """Validates MethodSpec for completeness, consistency, and correctness.

    Implements a picky LLM Reviewer that defaults to rejection when uncertain.
    Key principle: empirical choices (lag, missing policy, sample restriction)
    are NOT bug fixes — they must be explicitly specified and reviewed.

    Checks:
    - Format correctness
    - Citation backing for key assumptions
    - Field existence in data dictionaries
    - Timing consistency
    - Missing-value policy clarity
    - Lag and reporting-date alignment
    - Conflicts between paper/metadata/reference code
    - Review Decision Matrix for ambiguous fields
    """

    def __init__(
        self,
        data_dictionary: Optional[DataDictionary] = None,
        llm_client=None,
    ):
        self.data_dictionary = data_dictionary
        self.llm_client = llm_client

    def review(self, spec: MethodSpec) -> ReviewResult:
        """Run all review checks on a MethodSpec."""
        result = ReviewResult(methodspec_version=spec.schema_version)

        self._check_required_fields(spec, result)
        self._check_paper_evidence(spec, result)
        self._check_data_fields_exist(spec, result)
        self._check_source_mapping_resolved(spec, result)
        self._check_returns_universe(spec, result)
        self._check_timing_consistency(spec, result)
        self._check_reported_results_contract(spec, result)
        self._check_portfolio_structure_consistency(spec, result)
        self._check_ambiguous_fields(spec, result)
        self._check_silent_high_impact_fields(spec, result)
        self._check_unsupported_fields(spec, result)

        # Determine overall disposition
        if result.blocked_fields:
            result.disposition = "blocked"
            result.requires_human = True
            result.approved = False
        elif result.issues:
            result.disposition = "revision_required"
            result.remediation_mode = RemediationMode.RESOLVE_EXISTING_JSON.value
            result.approved = False
        else:
            result.disposition = "approved"
            result.approved = True
            result.codegen_ready = True
            result.paper_faithful = True

        return result

    def _check_required_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that critical fields are populated."""
        if not spec.signal.formula_expression:
            result.issues.append("signal.formula is empty")
        if not spec.required_fields:
            result.issues.append("signal.required_fields is empty")
        if not spec.portfolio.long_leg or not spec.portfolio.short_leg:
            result.issues.append("portfolio.long_leg / short_leg not specified")

    def _check_paper_evidence(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check methodspec.v1 audit fields without blocking early drafts."""
        if not spec.extraction_sources:
            result.warnings.append("No extraction_sources recorded")
        if not spec.data.required_fields:
            result.warnings.append("data.required_fields is empty; normalizer has no source hints")
        formula = spec.signal.formula
        evidence = getattr(formula, "evidence", []) if not isinstance(formula, str) else []
        if not evidence:
            result.warnings.append("signal.formula has no field-level paper evidence")

    def _check_data_fields_exist(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check that required fields exist in data dictionary."""
        if not self.data_dictionary:
            result.warnings.append("No data dictionary provided, skipping field check")
            return
        for f in spec.required_fields:
            if not self.data_dictionary.exists(f):
                result.issues.append(f"Field '{f}' not found in data dictionary")

    def _check_source_mapping_resolved(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Block signal fields whose physical data source is not registered.

        `data.normalized_mapping` says which physical source each field comes
        from; `spec.resolved_sources()` groups those by source. The data loader
        can only join a source it has a registered join for (`SIGNAL_SOURCES`:
        key/link/date/lag). A field mapped to a source the loader DOESN'T know
        would silently fail or guess at run time — exactly the "new data
        source appears" case. Block here so a human registers the source ONCE
        (a per-source, reusable-forever step) before approval, rather than
        letting the loader improvise per paper.

        Hard-blocks two cases, so no signal input ever silently defaults to a
        source the paper didn't state:
          1. UNRESOLVED source: a plain-column mapping whose physical column no
             registered catalog source declares (source==""). The source must
             come from the reviewed spec / catalog, never a silent guess.
          2. UNKNOWN source: a mapping that names a source with no registered
             join in `SIGNAL_SOURCES` (data catalog).
        """
        from src.infra.data_layer import SIGNAL_SOURCES

        unresolved = spec.unresolved_source_fields()
        if unresolved:
            cols = ", ".join(sorted({col for _concept, col in unresolved}))
            result.blocked_fields.append("data.normalized_mapping[source=unresolved]")
            result.issues.append(
                f"data.normalized_mapping has columns with no registered data source: "
                f"{cols}. The signal source/columns must come from the paper and be "
                "registered in the data catalog (src/infra/data_layer/catalog.py) — "
                "the pipeline never silently defaults a source (e.g. to Compustat). "
                "Map each column to an explicit {source, column} or register the "
                "source/column in the catalog before approval."
            )

        for source in spec.resolved_sources():
            if source == "":  # handled above as the unresolved case
                continue
            if source not in SIGNAL_SOURCES:
                field_path = f"data.normalized_mapping[source={source}]"
                result.blocked_fields.append(field_path)
                result.issues.append(
                    f"data.normalized_mapping references source '{source}', which the "
                    "data loader has no registered join for (not in SIGNAL_SOURCES). "
                    "Register the source once (key/link/date/lag, + link table if "
                    "needed) before approval — then every future paper using it is "
                    "handled automatically."
                )

    def _check_returns_universe(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check the returns universe (the stock-return panel the
        portfolio-construction side runs on).

        `MethodSpec.returns_universe` may name an entry registered in
        `catalog.RETURNS_UNIVERSES` (e.g. "us_equity_crsp"). When left unset it
        defaults to the standardized CRSP monthly panel
        (`catalog.DEFAULT_RETURNS_UNIVERSE`) — no longer a hard block. An
        explicitly-set but unregistered name is still blocked (register it once
        in the catalog before approval).
        """
        from src.infra.data_layer import catalog

        universe = getattr(spec, "returns_universe", None)
        if not universe:
            result.warnings.append(
                "returns_universe is not set: defaulting to the standardized CRSP "
                f"monthly panel ('{catalog.DEFAULT_RETURNS_UNIVERSE}'). Set "
                "returns_universe explicitly to use a different registered universe."
            )
        elif universe not in catalog.RETURNS_UNIVERSES:
            result.blocked_fields.append("returns_universe")
            result.issues.append(
                f"returns_universe '{universe}' is not registered in "
                "catalog.RETURNS_UNIVERSES. Register the returns universe once "
                "(returns_table + returns_layout) before approval."
            )

    def _check_timing_consistency(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Check timing assumptions are internally consistent."""
        timing = spec.signal.timing
        if timing.accounting_lag is not None and timing.accounting_lag < 0:
            result.issues.append("accounting_lag cannot be negative")
        if timing.holding_period is not None and timing.holding_period <= 0:
            result.issues.append("holding_period must be positive")
        if timing.accounting_lag is not None and timing.accounting_lag < 4:
            result.warnings.append(
                f"accounting_lag={timing.accounting_lag} months is unusually short"
            )

    def _check_reported_results_contract(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Sanity-check the reported_results block against the flat portfolio
        construction fields."""
        rr = spec.reported_results
        if (
            rr.main_spread is not None
            and not rr.spreads
            and rr.main_t_stat is None
        ):
            result.warnings.append(
                "reported_results.main_spread is set but no spreads/t-stat context is recorded"
            )

    def _check_portfolio_structure_consistency(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Warn (don't block) when the prose fields suggest a double-sort or
        multi-leg construction that the structured `portfolio`
        (construction_type/return_combination) fields leave unpopulated.

        The engine is standardized to a single-dimension continuous sort: a
        construction outside that (or an unpopulated structured field) is
        clamped to the menu default (extreme_group_spread) rather than
        code-generated. That default may not match the paper, so surface it
        as a review warning for a human to populate the structured field —
        but it is not a hard block, and any residual gap is decomposed
        downstream by step7's replication-gap analysis.
        """
        portfolio_return = spec.portfolio

        sort_text = " ".join([
            str(spec.portfolio.long_leg or ""),
            str(spec.portfolio.short_leg or ""),
        ]).lower()
        sort_signal_words = ("double", "conditional", "interact", "two-way", "average of", " and ")
        sort_structure_populated = (
            portfolio_return.construction_type != PortfolioConstructionType.UNSPECIFIED
            or portfolio_return.return_combination.type != ReturnCombinationType.UNSPECIFIED
        )
        if any(k in sort_text for k in sort_signal_words) and not sort_structure_populated:
            result.warnings.append(
                "portfolio.long_leg/short_leg suggest a double-sort or multi-leg "
                "construction, but portfolio.construction_type/return_combination "
                "is unpopulated -- the standardized engine only supports a "
                "single-dimension sort and will run it with the menu default "
                "combination. Populate portfolio.return_combination if the "
                "paper's construction should be captured."
            )

    def _check_ambiguous_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Apply Review Decision Matrix to ambiguous fields."""
        for amb in spec.ambiguous_fields:
            impact = (
                EmpiricalImpact.HIGH
                if amb.field in HIGH_IMPACT_FIELDS or amb.empirical_impact == EmpiricalImpact.HIGH
                else EmpiricalImpact.LOW
            )
            disposition = classify_disposition(amb.source, impact)

            note = FieldReviewNote(
                field=amb.field,
                status=disposition,
                reason=amb.reason,
                current_value=self._get_field_value(spec, amb.field),
                candidate_value=amb.candidate_value,
                empirical_impact=impact.value,
                evidence=amb.evidence,
            )
            result.field_notes.append(note)

            if disposition == Disposition.NEEDS_HUMAN_CONFIRMATION:
                result.blocked_fields.append(amb.field)
            elif disposition == Disposition.NEEDS_LLM_REVIEW:
                result.warnings.append(
                    f"Field '{amb.field}' needs LLM review: {amb.reason}"
                )

    def _check_silent_high_impact_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Deterministic backstop for HIGH_IMPACT_FIELDS the extractor never
        reported via `ambiguous_fields` at all.

        `_check_ambiguous_fields` only reacts to fields the extractor
        proactively flagged as uncertain -- a MethodSpec with an EMPTY
        `ambiguous_fields` list (a hand-built spec, or an extractor that
        silently omitted a field instead of flagging it) sails through
        `review()` with every empirical field clamped to its
        `registry.build_config` menu default AND `result.paper_faithful =
        True`, even when core portfolio-construction choices were never
        actually specified. This check inspects a fixed subset of
        HIGH_IMPACT_FIELDS whose "unspecified" sentinel is unambiguous (an
        explicit UNSPECIFIED enum member, or None/empty for a plain
        Optional/list field) and, for each one left silent with no matching
        `ambiguous_fields` entry, applies the Review Decision Matrix as
        (EvidenceSource.UNSPECIFIED, EmpiricalImpact.HIGH) --
        `needs_human_confirmation` per that matrix -- blocking approval (and
        the `paper_faithful` stamp) instead of silently defaulting (e.g.
        `registry.build_config` would otherwise silently default an unset
        `ls_quantile` to a decile sort).

        Deliberately NOT exhaustive over all of HIGH_IMPACT_FIELDS: fields
        whose default value is itself a plausible affirmative choice rather
        than an unambiguous "nothing was said" sentinel (e.g.
        `portfolio.long_leg`/`short_leg` default to "high"/"low",
        `portfolio.construction_type`) can't be judged silent by value alone
        -- those still rely on the extractor's own `ambiguous_fields`
        reporting via `_check_ambiguous_fields`. See docs/decision-log.md
        (2026-07-28 entry) for the gap this closes.
        """
        already_flagged = {amb.field for amb in spec.ambiguous_fields}
        silent_checks = [
            ("portfolio.sort.breakpoint_source", spec.breakpoint_source == BreakpointSource.UNSPECIFIED),
            ("portfolio.weighting", spec.weighting_rule == WeightingRule.UNSPECIFIED),
            ("signal.missing_policy", spec.missing_action == MissingAction.UNSPECIFIED),
            ("signal.timing.rebalance_frequency", spec.rebalance_frequency == RebalanceFrequency.UNSPECIFIED),
            ("signal.timing.formation_month", _is_invalid_formation_month(spec.formation_month)),
            ("signal.timing.holding_period", spec.holding_period_months is None),
            ("signal.timing.accounting_lag", spec.accounting_lag_months is None),
            ("signal.sign", spec.sign is None),
            ("portfolio.universe", spec.universe_description == "unspecified"),
            ("portfolio.universe_filters", not spec.portfolio.universe_filters),
            (
                "portfolio.return_combination",
                spec.portfolio.return_combination.type == ReturnCombinationType.UNSPECIFIED,
            ),
            ("portfolio.sort.ls_quantile", _is_invalid_ls_quantile(spec.portfolio.sort.ls_quantile)),
        ]
        for field_path, is_silent in silent_checks:
            if not is_silent or field_path in already_flagged:
                continue
            result.blocked_fields.append(field_path)
            result.field_notes.append(FieldReviewNote(
                field=field_path,
                status=Disposition.NEEDS_HUMAN_CONFIRMATION,
                reason=(
                    "High-impact empirical field left unspecified, or set to a "
                    "numerically invalid value, with no ambiguous_fields entry "
                    "-- registry.build_config would silently clamp this to its "
                    "menu default. Confirm the paper's actual choice (or that it "
                    "is genuinely silent and the standard default is acceptable) "
                    "before this spec can be approved."
                ),
                current_value=self._get_field_value(spec, field_path),
                empirical_impact=EmpiricalImpact.HIGH.value,
            ))

    def _check_unsupported_fields(self, spec: MethodSpec, result: ReviewResult) -> None:
        """Flag fields the paper states EXPLICITLY but whose value isn't an
        engine menu member (`MethodSpec.unsupported_fields`, e.g.
        `weighting="capped_vw"` normalized to `WeightingRule.OTHER` --
        see `UnsupportedField`/`_record_unsupported` in method_spec.py).

        Deliberately a SEPARATE check from `_check_silent_high_impact_fields`
        (which reacts to the `UNSPECIFIED` sentinel, i.e. "paper never said").
        Here the paper is unambiguous; the engine simply has no menu member
        for that scheme, so `registry.build_config` will substitute the
        standard default and record it in `config["substitutions"]` (a
        deterministic, non-LLM decision -- see registry.py). This check only
        surfaces that substitution for human confirmation; it never decides
        what the substitute should be.
        """
        already_flagged = {amb.field for amb in spec.ambiguous_fields}
        for uf in spec.unsupported_fields:
            if uf.field in already_flagged:
                continue
            result.blocked_fields.append(uf.field)
            impact = uf.empirical_impact.value if hasattr(uf.empirical_impact, "value") else str(uf.empirical_impact)
            result.field_notes.append(FieldReviewNote(
                field=uf.field,
                status=Disposition.NEEDS_HUMAN_CONFIRMATION,
                reason=(
                    f"Paper explicitly states {uf.paper_value!r} for this field, which "
                    "is not in the engine's standard menu (this is NOT a paper-silent "
                    "default -- registry.build_config will substitute the standard menu "
                    "default and record the substitution). Confirm the substitution is "
                    "acceptable before approving."
                ),
                current_value=uf.paper_value,
                empirical_impact=impact,
            ))

    def review_with_llm(
        self,
        spec: MethodSpec,
        paper_text: str,
        prompt_path: Path | None = None,
        pdf_bytes: bytes | None = None,
    ) -> tuple[ReviewResult, dict[str, Any]]:
        """Run LLM-backed review of a MethodSpec against its source paper.

        If pdf_bytes is provided and the client supports native PDF (claude),
        sends the PDF directly. Otherwise sends full paper_text as-is.

        Returns:
            (ReviewResult, raw_llm_dict) — raw dict is the full LLM JSON response,
            useful for writing the markdown_report artifact.
        """
        if not self.llm_client:
            raise RuntimeError("llm_client required for review_with_llm; pass one to ReviewGate()")

        resolved_prompt_path = prompt_path or DEFAULT_REVIEW_PROMPT_PATH
        system_prompt = resolved_prompt_path.read_text() if resolved_prompt_path.exists() else (
            "You are a MethodSpec auditor. Review the spec against the paper and return JSON."
        )

        spec_json = json.dumps(spec.model_dump(mode='json'), indent=2, ensure_ascii=False)
        client_supports_pdf = hasattr(self.llm_client, "_create_with_pdf")

        if pdf_bytes and client_supports_pdf:
            paper_ref = "[See attached PDF document above]"
        else:
            paper_ref = paper_text
            pdf_bytes = None

        user_msg = (
            f"Audit this MethodSpec against the original paper.\n\n"
            f"[METHODSPEC JSON]\n{spec_json}\n\n"
            f"[PAPER TEXT]\n{paper_ref}\n\n"
            f"{_LLM_REVIEW_CONTRACT}"
        )

        from src.infra.llm import extract_usage
        response = self.llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            **({"pdf_bytes": pdf_bytes} if pdf_bytes else {}),
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("LLM returned empty response for review — try a different provider or model")
        raw: dict[str, Any] = json.loads(content)
        raw["_token_usage"] = extract_usage(response)
        return self._raw_to_review_result(raw, spec), raw

    def _raw_to_review_result(self, raw: dict[str, Any], spec: MethodSpec) -> ReviewResult:
        """Convert a raw LLM JSON response into a structured ReviewResult."""
        remediation_mode = raw.get("remediation_mode", RemediationMode.RESOLVE_EXISTING_JSON.value)
        if remediation_mode == "patch_existing_json":
            remediation_mode = RemediationMode.RESOLVE_EXISTING_JSON.value

        result = ReviewResult(
            review_id=raw.get("review_id", ""),
            methodspec_version=raw.get("methodspec_version", spec.schema_version),
            reviewer=raw.get("reviewer", "llm"),
            disposition=raw.get("disposition", "pending"),
            remediation_mode=remediation_mode,
            codegen_ready=bool(raw.get("codegen_ready", False)),
            paper_faithful=bool(raw.get("paper_faithful", False)),
            approved=bool(raw.get("approved", False)),
            issues=raw.get("issues", []),
            warnings=raw.get("warnings", []),
            blocked_fields=raw.get("blocked_fields", []),
            requires_human=bool(raw.get("requires_human", False)),
        )
        for note in raw.get("field_notes", []):
            result.field_notes.append(FieldReviewNote(
                field=note.get("field", ""),
                status=note.get("status", Disposition.NEEDS_LLM_REVIEW),
                reason=note.get("reason", ""),
                current_value=note.get("current_value"),
                candidate_value=note.get("candidate_value"),
                empirical_impact=note.get("empirical_impact", ""),
                evidence=[
                    EvidenceCitation(**e) if isinstance(e, dict) else e
                    for e in note.get("evidence", [])
                ],
            ))
        return result

    def _get_field_value(self, spec: MethodSpec, field_path: str):
        """Best-effort dotted-path lookup for review context."""
        path_aliases = {
            "universe.missing_policy.action": "signal.missing_policy.action",
            "universe.winsorize_bounds": "signal.missing_policy.winsorize_bounds",
        }
        field_path = path_aliases.get(field_path, field_path)
        current = spec
        for part in field_path.split("."):
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
        return getattr(current, "value", current)
