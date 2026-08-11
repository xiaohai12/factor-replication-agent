// Session-local persistence for the standalone paper-first MethodSpec
// lifecycle (extract/review/resolve -- backend/routers/methodspecs.py).
// These stages are NOT session-scoped on the backend (see
// docs/known-gaps-paper-first-v2.md), so the session detail page keeps its
// own progress here (sessionStorage, cleared on tab close) instead of
// re-fetching non-existent session-owned artifacts.

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
}

const key = (sessionId: string) => `methodspec-workflow:${sessionId}`

export function getMethodSpecWorkflowState(sessionId: string): MethodSpecWorkflowState {
  try {
    const raw = sessionStorage.getItem(key(sessionId))
    return raw ? (JSON.parse(raw) as MethodSpecWorkflowState) : {}
  } catch {
    return {}
  }
}

export function setMethodSpecWorkflowState(sessionId: string, patch: MethodSpecWorkflowState): MethodSpecWorkflowState {
  const next = { ...getMethodSpecWorkflowState(sessionId), ...patch }
  sessionStorage.setItem(key(sessionId), JSON.stringify(next))
  return next
}
