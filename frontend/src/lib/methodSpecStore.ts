// Session-local persistence for the standalone paper-first MethodSpec
// lifecycle (extract/review/resolve -- backend/routers/methodspecs.py).
// These stages are NOT session-scoped on the backend (see
// docs/known-gaps-paper-first-v2.md), so the session detail page keeps its
// own progress here (sessionStorage, cleared on tab close) instead of
// re-fetching non-existent session-owned artifacts.

export interface MethodSpecWorkflowState {
  paper?: Record<string, unknown>
  paperText?: string
  review?: Record<string, unknown>
  reviewSource?: "rules" | "llm" | "human"
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
