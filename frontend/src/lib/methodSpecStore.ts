// Local persistence for the standalone paper-first MethodSpec lifecycle
// (extract/review/resolve -- backend/routers/methodspecs.py). These stages
// are NOT session-scoped on the backend (see docs/known-gaps-paper-first-v2.md),
// so the session detail page keeps its own progress here instead of
// re-fetching non-existent session-owned artifacts.
//
// Uses `localStorage` (NOT `sessionStorage`): the latter is cleared on tab
// close and isolated per-tab, so reopening the same session in a new tab or
// after closing the browser looked like Step 1 had never run, even though
// the backend still had the artifact/job. `extractJobId`/`reviewJobId` are
// persisted here too so a remount (tab switch, navigation away and back)
// can resume watching a still-running -- or fetch the result of an
// already-finished -- backend job instead of losing track of it.

import type { ToolResult } from "@/lib/types"

export interface ReviewRound {
  round_num: number
  error_log: string
  spec_before: Record<string, unknown>
  spec_after: Record<string, unknown> | null
  diff: Array<{ field_path: string; old: unknown; new: unknown }>
  call_error: string | null
}

export interface MethodSpecWorkflowState {
  //: `document_id`/`target_name` used for the extraction -- persisted so
  //: the Step2 page (a separate mount) can later kick off `runReviewLoop`
  //: against the same identifiers without the user re-entering them.
  documentId?: string
  targetName?: string
  //: Step1's own raw LLM output (unreviewed, may not even validate) --
  //: shown on the Step1 page. Distinct from `paper`, which is Step2's
  //: converged result and belongs on the Step2/review page.
  rawSpec?: Record<string, unknown>
  paper?: Record<string, unknown>
  paperText?: string
  review?: Record<string, unknown>
  reviewSource?: "rules" | "llm" | "human"
  //: Mechanical before/after diff, Step1 raw dict -> final converged spec
  //: (see `spec_build.SpecBuildOutcome.total_diff`) -- every field the LLM
  //: review loop changed, trusted directly (2026-08-11: no more merge
  //: guardrail), shown to the human for visual verification instead.
  totalDiff?: Array<{ field_path: string; old: unknown; new: unknown }>
  //: Per-round before/after/diff breakdown, for "what changed in round N".
  history?: ReviewRound[]
  resolved?: Record<string, unknown>
  //: Transient UI flag: an LLM review loop or rules-only re-review request
  //: is currently in flight -- lets `StepStepper` show "running" for Step 2
  //: while `review`/`resolved` are (deliberately) cleared for a re-run,
  //: instead of falling back to "not_started".
  reviewRunning?: boolean
  //: `job_id` of an in-flight (or just-finished) Step1 extract / Step2
  //: review-loop job, persisted so a remount can re-subscribe to it via
  //: `useJobStream` instead of losing track of the backend job entirely.
  //: Cleared once that job's terminal (completed/failed) result has been
  //: processed.
  extractJobId?: string
  reviewJobId?: string
  //: Tool Prelude results (docs/tools-plus-llm-plan.md) already computed by
  //: the backend before each LLM call -- `ExtractionResult.tool_results` /
  //: the final round's `SpecBuildOutcome.tool_results`. Rendered via
  //: `ToolResultsPanel`.
  extractToolResults?: ToolResult[]
  reviewToolResults?: ToolResult[]
}

const key = (sessionId: string) => `methodspec-workflow:${sessionId}`

export function getMethodSpecWorkflowState(sessionId: string): MethodSpecWorkflowState {
  try {
    const raw = localStorage.getItem(key(sessionId))
    return raw ? (JSON.parse(raw) as MethodSpecWorkflowState) : {}
  } catch {
    return {}
  }
}

export function setMethodSpecWorkflowState(sessionId: string, patch: MethodSpecWorkflowState): MethodSpecWorkflowState {
  const next = { ...getMethodSpecWorkflowState(sessionId), ...patch }
  localStorage.setItem(key(sessionId), JSON.stringify(next))
  return next
}
