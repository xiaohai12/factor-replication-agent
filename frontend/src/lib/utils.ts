import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Mirrors scripts/resolve_review_blocks.py's `_parse_value`: the review
 * resolution `Input` fields are free-text, but some blocked fields (e.g.
 * `data.normalized_mapping`) need a real dict/number/bool/null, not a raw
 * string. Try JSON first (double-quoted, e.g. {"return": "ret"}) so the
 * resolved MethodSpec doesn't fail Pydantic validation with a `dict_type`
 * error; fall back to the raw string for genuinely-string fields. */
export function parseResolutionValue(raw: string): unknown {
  const trimmed = raw.trim()
  if (trimmed === "") return ""
  try {
    return JSON.parse(trimmed)
  } catch {
    return raw
  }
}

/** Mirrors the backend's own severity threshold (`ReviewGate.
 * _raw_to_review_result`'s `advisory_issues` regex): P2/P3-prefixed issues
 * are advisory (schema cleanliness, wording, minor auditability) and must
 * never look as blocking as an unprefixed/P0/P1 issue in the UI, even
 * though the backend already keeps them out of `codegen_ready` gating. */
const ADVISORY_ISSUE_RE = /^\s*P[23](?:\s*\/[^:]+)?\s*:/i

export function splitIssuesBySeverity(issues: string[]): { required: string[]; advisory: string[] } {
  const required: string[] = []
  const advisory: string[] = []
  for (const issue of issues) {
    ;(ADVISORY_ISSUE_RE.test(issue) ? advisory : required).push(issue)
  }
  return { required, advisory }
}
