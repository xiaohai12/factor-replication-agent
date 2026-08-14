You are auditing a generated Python `compute_signal` function against an
ALREADY-APPROVED signal formula from a reviewed MethodSpec. You are NOT
reviewing whether the formula itself is the right economic choice -- that
was already decided by a human/rule-based review gate and is out of scope.
Your only job: does the code correctly implement this exact approved
formula, or does it silently compute something else (wrong sign, wrong lag
direction, missing a step, wrong aggregation, swapped operands, etc.)?

## Approved formula (do not question this -- only check the code against it)
{spec_text}

## Generated code
```python
{code}
```

## Output contract
Return ONLY a single strict JSON object, no prose, no code fences:

{{
  "faithful": true or false,
  "reason": "one sentence explaining the verdict",
  "quoted_code": "a short verbatim substring copied EXACTLY from the code above that is wrong (empty string \"\" if faithful=true)",
  "quoted_spec": "a short verbatim substring copied EXACTLY from the approved formula text above that the code contradicts (empty string \"\" if faithful=true)"
}}

Rules:
- `quoted_code` and `quoted_spec` MUST be copied character-for-character from
  the text above -- do not paraphrase or summarize them. A claim that can't
  be verified verbatim will be discarded.
- If you are unsure, or the mismatch is about something out of scope
  (empirical/economic judgment, e.g. missing-data policy or breakpoint
  choice), set `faithful=true` -- do not flag anything outside "does this
  code compute what the formula above says".
- Never propose a fix or alternative formula. You only report faithful or
  not, with the two quotes above.
