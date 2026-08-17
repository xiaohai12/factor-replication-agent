// Local persistence for step6's ②/③ preview-only queries (`GET
// /steps/6/cz-config`, `GET /steps/6/hxz-config` -- backend/routers/
// replication.py). Both endpoints are deliberately stateless on the
// backend (never mutate the session, docs on those handlers), so their
// results only ever lived in React `useState` -- a page reload (which
// commonly follows a dev-server backend restart) silently reset them to
// "never queried", forcing a re-query (a live network call for ②, a CSV
// re-download for ③) to see numbers that were already fetched moments ago.
//
// Uses `localStorage` (not `sessionStorage`) for the same reason as
// `methodSpecStore.ts`: survives tab close/reopen, not just the current tab.

export interface Step6CzPreviewCache {
  acronym: string
  raw: Record<string, unknown>
  config_override: Record<string, unknown>
  cz_reported: { mean_return: number | null; t_stat: number | null; sign: number | null }
}

export interface Step6HxzPreviewCache {
  acronym: string
  originalInsample: Record<string, unknown> | null
  hxzPaperSample: Record<string, unknown> | null
}

export interface Step6PreviewState {
  czSelected?: string
  czPreview?: Step6CzPreviewCache
  configDiff?: {
    original: Record<string, unknown>
    cz: Record<string, unknown>
    std: Record<string, unknown>
    raw: Record<string, unknown>
    czReported: { mean_return: number | null; t_stat: number | null }
  }
  hxzSelected?: string
  hxzPreview?: Step6HxzPreviewCache
}

const key = (sessionId: string) => `step6-preview:${sessionId}`

export function getStep6PreviewState(sessionId: string): Step6PreviewState {
  try {
    const raw = localStorage.getItem(key(sessionId))
    return raw ? (JSON.parse(raw) as Step6PreviewState) : {}
  } catch {
    return {}
  }
}

export function setStep6PreviewState(sessionId: string, patch: Step6PreviewState): Step6PreviewState {
  const next = { ...getStep6PreviewState(sessionId), ...patch }
  localStorage.setItem(key(sessionId), JSON.stringify(next))
  return next
}
