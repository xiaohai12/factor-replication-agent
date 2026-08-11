"""Step2's single bounded review loop: raw Step1 dict -> validated,
LLM-reviewed `MethodSpec` (see docs/step1-step2-refactor-plan.md and the
2026-08-11 follow-up in docs/decision-log.md).

Each round: **validate before LLM review** (including round 1, against
Step1's raw dict -- almost certainly fails since menu fields aren't
classified yet), so every round has the same shape ("look at the latest
`ValidationError` text, then review"). The LLM reviews the *entire* spec
against the paper text and the current `error_log`, and its rewritten spec
is trusted **wholesale** (2026-08-11 decision: replaced the earlier
"only merge explicitly declared fields" guardrail) -- except for
`factor_id`/`schema_version`/`paper.document_id` (D7), which are always
re-injected deterministically and never taken from the LLM's output.
Every field-level change the LLM makes is captured as a mechanical
before/after diff (`ReviewRound.diff`) so a human can see exactly what
changed each round, rather than the system silently discarding undeclared
changes.

Loop exit: `model_validate` passes AND this round's LLM rewrite produced
no diff at all (nothing left to change) -> exit to rule-based review
(`review_method_spec`, D2 only). Budget exhausted (`MAX_REVIEW_ROUNDS`
rounds, each one full validate+LLM-review cycle) -> return an
`error`-carrying outcome (never raises), for a human to resolve.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.infra.models.method_spec import MethodReview, MethodSpec
from src.steps.step2_reviewer.review import load_llm_review_system_prompt, review_method_spec

MAX_REVIEW_ROUNDS = 3

_MISSING = object()  # sentinel: a path present on one side of a diff but not the other

_USER_TEMPLATE = """\
Paper text:

{paper_text}

Current MethodSpec JSON (round {round_num} of at most {total_rounds}):

{spec_json}

Latest model_validate() error (empty string means the spec above already
validates against the schema):

{error_log}

Return the JSON object described in the system prompt.
"""


def _diff_json(old: Any, new: Any, path: str = "") -> list[dict]:
    """Flat list of every leaf-level change between two JSON-shaped
    dicts/lists, as `{"field_path": ..., "old": ..., "new": ...}` -- the
    mechanical basis for both the loop's convergence check (no diff = LLM
    made no further changes) and the human-facing before/after view
    (frontend highlights each entry in red). Compares dicts key-by-key and
    lists index-by-index (the spec's lists -- sorts/legs/fields/etc. --
    are order-stable arrays, not sets).
    """
    diffs: list[dict] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            child_path = f"{path}.{key}" if path else key
            diffs.extend(_diff_json(old.get(key, _MISSING), new.get(key, _MISSING), child_path))
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            child_path = f"{path}[{i}]"
            old_item = old[i] if i < len(old) else _MISSING
            new_item = new[i] if i < len(new) else _MISSING
            diffs.extend(_diff_json(old_item, new_item, child_path))
    elif old != new:
        diffs.append({
            "field_path": path,
            "old": None if old is _MISSING else old,
            "new": None if new is _MISSING else new,
        })
    return diffs


@dataclass
class ReviewRound:
    round_num: int
    error_log: str
    spec_before: dict
    spec_after: dict | None = None
    llm_raw: dict | None = None
    diff: list[dict] = field(default_factory=list)
    call_error: str | None = None


@dataclass
class SpecBuildOutcome:
    spec: MethodSpec | None = None
    review: MethodReview | None = None
    history: list[ReviewRound] = field(default_factory=list)
    error: str | None = None
    #: Mechanical diff between Step1's raw dict (post D7-injection) and the
    #: final converged spec -- the "total" before/after view; `history[i].
    #: diff` gives the same thing broken out per round.
    total_diff: list[dict] = field(default_factory=list)
    #: Last round's `value_corrections`/`additional_findings` annotations,
    #: if the LLM emitted any -- informational only (explains WHY a diff
    #: entry changed), never a merge gate. See module docstring.
    llm_notes: dict = field(default_factory=dict)


def _inject_deterministic_fields(raw: dict, document_id: str, target_name: str) -> dict:
    """D7: `factor_id`/`schema_version`/`paper.document_id` are never taken
    from the LLM, in every round (not just the first) -- this is the one
    guardrail that survived the 2026-08-11 "trust the LLM's rewrite
    wholesale" decision, since inventing an unstable identifier is a
    different failure mode than an empirical judgment call.
    """
    raw = copy.deepcopy(raw)
    raw["factor_id"] = MethodSpec.make_factor_id(document_id, target_name)
    raw["target_name"] = target_name
    raw["schema_version"] = "methodspec.v2"
    paper_block = dict(raw.get("paper") or {})
    paper_block["document_id"] = document_id
    raw["paper"] = paper_block
    return raw


def _call_llm_review(
    spec_dict: dict, paper_text: str, error_log: str, round_num: int, total_rounds: int, llm_client
) -> dict:
    messages = [
        {"role": "system", "content": load_llm_review_system_prompt()},
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                paper_text=paper_text,
                round_num=round_num,
                total_rounds=total_rounds,
                spec_json=json.dumps(spec_dict, indent=2, default=str),
                error_log=error_log,
            ),
        },
    ]
    response = llm_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def build_reviewed_method_spec(
    raw: dict,
    document_id: str,
    target_name: str,
    paper_text: str,
    llm_client,
    max_rounds: int = MAX_REVIEW_ROUNDS,
    log=None,
) -> SpecBuildOutcome:
    log = log or (lambda msg: None)
    total_rounds = max_rounds  # exactly max_rounds validate+LLM-review cycles, no +1
    outcome = SpecBuildOutcome()
    log("Injecting deterministic fields (factor_id/schema_version/paper.document_id)...")
    initial_spec = _inject_deterministic_fields(raw, document_id, target_name)
    spec_dict = initial_spec

    for round_num in range(1, total_rounds + 1):
        log(f"Round {round_num}/{total_rounds}: running model_validate()...")
        try:
            MethodSpec.model_validate(spec_dict)
            validate_passed = True
            error_log = ""
            log(f"Round {round_num}/{total_rounds}: model_validate() passed.")
        except ValidationError as exc:
            validate_passed = False
            error_log = str(exc)
            log(f"Round {round_num}/{total_rounds}: model_validate() failed ({len(exc.errors())} error(s)).")

        round_record = ReviewRound(round_num=round_num, error_log=error_log, spec_before=spec_dict)
        log(f"Round {round_num}/{total_rounds}: calling LLM review...")
        try:
            llm_raw = _call_llm_review(spec_dict, paper_text, error_log, round_num, total_rounds, llm_client)
        except Exception as exc:  # noqa: BLE001 - any LLM/client failure just ends this round with no progress
            round_record.call_error = str(exc)
            outcome.history.append(round_record)
            log(f"Round {round_num}/{total_rounds}: LLM call failed: {exc}")
            if validate_passed:
                log(f"Round {round_num}/{total_rounds}: spec already valid -- stopping here despite the failed call.")
                break
            log(f"Round {round_num}/{total_rounds}: retrying (spec still invalid)...")
            continue

        log(f"Round {round_num}/{total_rounds}: LLM review returned, computing diff against the previous round...")
        round_record.llm_raw = llm_raw
        llm_spec = llm_raw.get("spec") if isinstance(llm_raw, dict) else None
        new_spec = _inject_deterministic_fields(llm_spec, document_id, target_name) if isinstance(llm_spec, dict) else spec_dict

        diff = _diff_json(spec_dict, new_spec)
        round_record.spec_after = new_spec
        round_record.diff = diff
        outcome.history.append(round_record)
        outcome.llm_notes = {
            "value_corrections": (llm_raw or {}).get("value_corrections") or [],
            "additional_findings": (llm_raw or {}).get("additional_findings") or [],
        }
        log(f"Round {round_num}/{total_rounds}: diff has {len(diff)} changed field(s).")

        spec_dict = new_spec

        if validate_passed and not diff:
            log(f"Round {round_num}/{total_rounds}: converged (validate passed, no further changes) -- exiting loop.")
            break
        log(f"Round {round_num}/{total_rounds}: not converged yet, continuing...")

    log("Running final model_validate() on the converged spec...")
    outcome.total_diff = _diff_json(initial_spec, spec_dict)

    try:
        final_spec = MethodSpec.model_validate(spec_dict)
    except ValidationError as exc:
        outcome.error = f"validation failed after {len(outcome.history)} review round(s): {exc}"
        log(f"Final model_validate() failed: {outcome.error}")
        return outcome

    log("Final model_validate() passed. Running rule-based review (D2/missing-mapping)...")
    outcome.spec = final_spec
    outcome.review = review_method_spec(final_spec)
    log(f"Rule-based review done: {len(outcome.review.findings)} finding(s).")
    return outcome
