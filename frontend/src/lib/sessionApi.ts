// Typed API layer for the Session control plane (Phase 4). Existing pages
// (PipelineE2EPage/BacktestExperimentsPage) call `api.get`/`api.post`
// directly with locally-declared response shapes; this module gives the
// NEW session pages one typed surface instead of repeating that pattern.

import { api } from "@/lib/api"
import type { SessionEvent, SessionManifest, StepIoContract } from "@/lib/types"

export interface StepResponse {
  record: {
    step: number
    name: string
    attempts: SessionManifest["steps"][string]["attempts"]
    stale: boolean
  }
  contract: StepIoContract
  missing_input_refs: string[]
}

export const sessionApi = {
  create: (factor_id: string, paper_id?: string) =>
    api.post<SessionManifest>("/api/sessions", { factor_id, paper_id }),

  list: () => api.get<SessionManifest[]>("/api/sessions"),

  get: (sessionId: string) => api.get<SessionManifest>(`/api/sessions/${sessionId}`),

  getStep: (sessionId: string, step: number) =>
    api.get<StepResponse>(`/api/sessions/${sessionId}/steps/${step}`),

  getEvents: (sessionId: string, sinceSeq = -1) =>
    api.get<SessionEvent[]>(`/api/sessions/${sessionId}/events?since_seq=${sinceSeq}`),

  getDiagnostics: (sessionId: string) =>
    api.get<Record<string, unknown>>(`/api/sessions/${sessionId}/diagnostics`),

  archive: (sessionId: string, expected_revision: number) =>
    api.post<SessionManifest>(`/api/sessions/${sessionId}/archive`, { expected_revision }),

  /** Physically deletes the session's own directory (writes a tombstone
   * first); never touches EvidenceStore/comparison.json/diagnosis.json. */
  hardDelete: (sessionId: string, expected_revision: number) =>
    api.del<{ session_id: string; deleted: boolean }>(`/api/sessions/${sessionId}`, {
      expected_revision,
      confirm: true,
    }),

  extractFromPdf: (sessionId: string, file: File, expectedRevision: number, llmProvider: string) =>
    api.postForm<{ job_id: string }>(`/api/sessions/${sessionId}/steps/1/extract-pdf`, file, {
      expected_revision: String(expectedRevision),
      llm_provider: llmProvider,
    }),

  getStepArtifact: (sessionId: string, step: number, filename: string) =>
    api.get<{ filename: string; content: string }>(
      `/api/sessions/${sessionId}/steps/${step}/artifact/${encodeURIComponent(filename)}`,
    ),

  getComparison: (sessionId: string) =>
    api.get<Record<string, unknown>>(`/api/sessions/${sessionId}/steps/7/comparison`),

  /** Generic "run this step's action" call -- every step's request body
   * shape differs (see lib/steps.ts's requestTemplate), so this stays
   * untyped on the request side; the response is either `{job_id}` (job
   * steps) or the step's own sync result (non-job steps). */
  runStep: (endpoint: string, body: unknown) => api.post<{ job_id?: string } & Record<string, unknown>>(endpoint, body),

  // -- helpers for step3's "pick an existing MethodSpec, then codegen"
  // shortcut, reusing the EXISTING (non-session) endpoints rather than
  // duplicating them.
  listResolvedMethodSpecs: () => api.get<string[]>("/api/methodspecs/resolved"),
  getResolvedMethodSpec: (factorId: string) =>
    api.get<Record<string, unknown>>(`/api/methodspecs/resolved/${factorId}`),
  generatePlugin: (spec: Record<string, unknown>, llmProvider: string) =>
    api.post<{ job_id: string }>("/api/codegen", { spec, llm_provider: llmProvider }),

  listSnapshots: () => api.get<{ snapshot_id: string }[]>("/api/backtest/snapshots"),
}

