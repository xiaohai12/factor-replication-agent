"""Per-step readiness + diagnostics -- deliberately NOT a unified 0-100
quality score.

Rev1 of the session-centric UI plan proposed a single `StepScore`; external
review (docs/decision-log.md 2026-08-04) correctly rejected that: several of
the obvious signals do not actually mean "better" --

- fewer `blocked_fields` != a more accurate MethodSpec (step2)
- fewer repair attempts != a correct compute_signal formula (step3)
- higher `coverage`/`n_months` != more faithful to the paper (step5)
- a higher step8 claim-acceptance rate != a better explanation, only better
  FORMAT compliance
- `ValidationReport.executes_ok` defaults `True` and STAYS `True` when the
  execution smoke test was skipped entirely (see
  `src/infra/models/plugin.py`) -- must be rendered tri-state
  (pass/fail/skipped), never as a bare green check.

So this module produces three distinct things per step, never blended into
one number:

- `readiness`: `"ready" | "not_ready" | "blocked"` -- purely "can the
  pipeline / UI advance past this step", nothing about quality.
- `counters`: raw observable counts already computed elsewhere in the
  pipeline (never re-derives empirical results itself).
- `flags`: short human-readable strings calling out anything worth a
  reviewer's attention (e.g. "execution smoke test was skipped").

A genuine `evaluation_score` (a number that means "better") is computed only
where an INDEPENDENT reference exists -- today that's step1 alone, against
SignalDoc/human-labeled MethodSpecs, and it lives in a separate, isolated
code path (see `src/evaluation/extraction_eval.py`), never mixed into a
normal session's step1 diagnostics.
"""

from __future__ import annotations

from typing import Any, Optional

from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord, ValidationReport
from src.infra.models.run_record import RunRecord
from src.steps.step2_reviewer import ReviewResult


def _diagnostics(readiness: str, counters: dict[str, Any], flags: Optional[list[str]] = None) -> dict:
    return {"readiness": readiness, "counters": counters, "flags": flags or []}


def step1_diagnostics(spec: MethodSpec) -> dict:
    ambiguous = len(spec.ambiguous_fields)
    flags = []
    if ambiguous:
        flags.append(f"{ambiguous} ambiguous field(s) -- may need human review at step2")
    return _diagnostics(
        readiness="ready",  # extraction always produces SOME spec to review next
        counters={
            "ambiguous_field_count": ambiguous,
            "unsupported_field_count": len(spec.unsupported_fields),
            "reextraction_attempts": spec.reextraction_attempts,
        },
        flags=flags,
    )


def step2_diagnostics(review: ReviewResult) -> dict:
    disposition_counts: dict[str, int] = {}
    for note in review.field_notes:
        key = note.status.value if hasattr(note.status, "value") else str(note.status)
        disposition_counts[key] = disposition_counts.get(key, 0) + 1

    if review.requires_human or review.disposition == "blocked":
        readiness = "blocked"
    elif review.disposition == "approved" or review.codegen_ready:
        readiness = "ready"
    else:
        readiness = "not_ready"

    flags = []
    if review.blocked_fields:
        flags.append(f"{len(review.blocked_fields)} field(s) blocked pending human resolution")
    if not review.paper_faithful:
        flags.append("review marked this spec as not paper-faithful")

    return _diagnostics(
        readiness=readiness,
        counters={
            "blocked_field_count": len(review.blocked_fields),
            "issue_count": len(review.issues),
            "warning_count": len(review.warnings),
            "disposition_histogram": disposition_counts,
            "requires_human": review.requires_human,
        },
        flags=flags,
    )


def step3_diagnostics(plugin: PluginRecord, config: dict) -> dict:
    repair_attempts = len(plugin.repair_trace)
    # `config["substitutions"]` (registry.build_config) is the existing,
    # already-computed "paper said X, engine ran Y" audit trail for
    # unsupported-field substitutions -- surfaced here as a diagnostic flag
    # list rather than recomputed; see this module's docstring for why no
    # NEW silent-clamp instrumentation was added on top of it (the genuinely
    # silent case -- an unspecified field falling back to its documented
    # default -- is normal, expected behavior, not an anomaly worth flagging).
    substitutions = config.get("substitutions") or []
    flags = [
        f"config substitution: paper stated {s['field']}={s['paper_value']!r}, "
        f"engine ran {s['engine_value']!r} ({s['reason']})"
        for s in substitutions
    ]
    if repair_attempts:
        flags.append(f"{repair_attempts} technical repair attempt(s) were needed before this plugin validated")
    return _diagnostics(
        readiness="ready" if plugin.validation_status in ("passed", "pending") else "not_ready",
        counters={
            "repair_attempt_count": repair_attempts,
            "substitution_count": len(substitutions),
            "validation_status": plugin.validation_status,
        },
        flags=flags,
    )


def step4_diagnostics(report: ValidationReport, execution_check_supplied: bool) -> dict:
    """`execution_check_supplied` must be passed explicitly by the caller
    (True iff a `script_text`/data slice was actually given to
    `AdversarialSandbox.validate`) -- `report.executes_ok` alone cannot tell
    a genuine pass apart from a skipped check (it defaults `True` either
    way), so this function refuses to guess and requires the caller to say
    which case it is.
    """
    executes_ok_state = "skipped" if not execution_check_supplied else ("pass" if report.executes_ok else "fail")
    flags = list(report.errors) + list(report.warnings)
    if executes_ok_state == "skipped":
        flags.append("execution smoke test was skipped (no script/data slice supplied) -- not a pass")
    return _diagnostics(
        readiness="ready" if report.passed else "blocked",
        counters={
            "syntax_ok": report.syntax_ok,
            "schema_ok": report.schema_ok,
            "no_future_leak": report.no_future_leak,
            "reproducible": report.reproducible,
            "executes_ok": executes_ok_state,
            "error_count": len(report.errors),
            "warning_count": len(report.warnings),
        },
        flags=flags,
    )


def step5_diagnostics(run: RunRecord) -> dict:
    metrics = run.metrics
    flags = []
    if run.status != "success":
        flags.append(f"run status = {run.status!r}")
    if metrics and metrics.microcap_share is not None and metrics.microcap_share > 0.5:
        flags.append(f"microcap_share={metrics.microcap_share:.2f} -- majority-microcap sample")
    return _diagnostics(
        readiness="ready" if run.status == "success" else "not_ready",
        counters={
            "status": run.status,
            "coverage": metrics.coverage if metrics else None,
            "n_months": metrics.n_months if metrics else None,
            "microcap_share": metrics.microcap_share if metrics else None,
            "repair_attempt_count": len(run.repair_history),
        },
        flags=flags,
    )


def step6_diagnostics(runs: list[RunRecord]) -> dict:
    success = [r for r in runs if r.status == "success"]
    invalidated = any(r.batch_invalidated for r in runs)
    flags = []
    if invalidated:
        flags.append(runs[0].batch_invalidation_reason if runs else "batch invalidated")
    if len(success) < len(runs):
        flags.append(f"{len(runs) - len(success)} of {len(runs)} track(s) did not succeed")
    return _diagnostics(
        readiness="blocked" if invalidated else ("ready" if success else "not_ready"),
        counters={
            "track_count": len(runs),
            "success_count": len(success),
            "batch_invalidated": invalidated,
        },
        flags=flags,
    )


def step7_diagnostics(bundle: dict) -> dict:
    derived = bundle.get("derived") or {}
    overall_tag = derived.get("overall_tag", "inconclusive")
    gap = bundle.get("gap_decomposition") or {}
    flags = []
    if overall_tag == "sign_mismatch":
        flags.append("sign mismatch vs paper-reported result")
    if not gap.get("available", True):
        flags.append("gap decomposition unavailable for this batch")
    return _diagnostics(
        readiness="ready",  # a comparison, once recorded, is always "done"
        counters={
            "overall_tag": overall_tag,
            "sign_agrees": derived.get("sign_agrees"),
            "significance_agrees": derived.get("significance_agrees"),
            "abs_spread_ratio": derived.get("abs_spread_ratio"),
            "explained_fraction": gap.get("explained_fraction"),
            "residual": gap.get("residual"),
        },
        flags=flags,
    )


def step8_diagnostics(report) -> dict:
    accepted = len(report.claims)
    rejected = len(report.rejected_claims)
    flags = [f"{rejected} claim(s) rejected by the validator" for _ in [None] if rejected]
    return _diagnostics(
        readiness="ready",
        counters={
            "accepted_claim_count": accepted,
            "rejected_claim_count": rejected,
            # Deliberately NOT an "acceptance rate quality score" -- a high
            # rate only means the model complied with the citation/format
            # rules better, not that its explanation is more correct. See
            # module docstring.
        },
        flags=flags,
    )
