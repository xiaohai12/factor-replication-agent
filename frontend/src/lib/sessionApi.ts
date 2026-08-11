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

export type MethodSpecStage = "drafts" | "reviews" | "resolutions" | "resolved"

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

  // -- standalone paper-first MethodSpec lifecycle (backend/routers/
  // methodspecs.py). NOT session-scoped -- a session only consumes
  // the RESULTING ResolvedMethodSpec from step3 onward (see
  // docs/known-gaps-paper-first-v2.md). `extractPaperPdf`'s `document_id`/
  // `target_name` have no session equivalent; callers pass the session's
  // own factor_id/paper_id as a reasonable default.
  extractPaperPdf: (
    documentId: string,
    targetName: string,
    file: File,
    llmProvider: string,
    llmModel?: string,
    sessionId?: string,
  ) =>
    api.postForm<{ job_id: string }>("/api/methodspecs/extract-pdf", file, {
      document_id: documentId,
      target_name: targetName,
      llm_provider: llmProvider,
      ...(llmModel ? { llm_model: llmModel } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
    }),
  /** Step2's LLM review loop (`spec_build.build_reviewed_method_spec`),
   * run as its OWN job -- separate from `extractPaperPdf` so Step1 can
   * show "succeeded" as soon as extraction itself returns, without waiting
   * for the (much slower) review loop too. */
  runReviewLoop: (
    rawSpec: Record<string, unknown>,
    documentId: string,
    targetName: string,
    paperText: string,
    llmProvider: string,
    llmModel?: string,
    sessionId?: string,
  ) =>
    api.post<{ job_id: string }>("/api/methodspecs/review-loop", {
      raw_spec: rawSpec,
      document_id: documentId,
      target_name: targetName,
      paper_text: paperText,
      llm_provider: llmProvider,
      ...(llmModel ? { llm_model: llmModel } : {}),
      session_id: sessionId,
    }),
  reviewPaperSpec: (paper: Record<string, unknown>, sessionId?: string) =>
    api.post<Record<string, unknown>>("/api/methodspecs/review", { paper, session_id: sessionId }),
  /** Corrects the extracted VALUE of one or more fields. Human-only --
   * `apply_human_status_overrides`/`/review/override` (evidence-status-only
   * corrections) were removed 2026-08-10; a human now only ever confirms/
   * corrects a field's final `value`, status is auto-stamped `clear` server
   * side. Returns a NEW paper; caller should re-run review/resolve against
   * it afterward. */
  patchPaperValue: (
    paper: Record<string, unknown>,
    patches: Record<string, unknown>,
    reason?: string,
    sessionId?: string,
  ) =>
    api.post<Record<string, unknown>>("/api/methodspecs/patch-value", {
      paper,
      patches,
      reason: reason ?? "",
      session_id: sessionId,
    }),
  /** Cached full text for a paper, keyed by `document_id` -- populated by
   * `/api/methodspecs/extract`/`extract-pdf` (and `/api/papers/upload`) so a
   * later LLM-backed review can recover it even after sessionStorage/the
   * extraction job itself is gone. 404s if nothing was ever cached for it. */
  getPaperText: (documentId: string) =>
    api.get<{ paper_id: string; paper_text: string; text_length: number }>(
      `/api/papers/${encodeURIComponent(documentId)}`,
    ),
  resolvePaperSpec: (
    paper: Record<string, unknown>,
    review: Record<string, unknown>,
    returnsSource = "us_equity_crsp",
    sessionId?: string,
    llmProvider?: string,
    llmModel?: string,
  ) =>
    api.post<{
      resolution: Record<string, unknown>
      is_ready: boolean
      unmapped_concepts: string[]
      llm_matched_concepts: string[]
    }>("/api/methodspecs/resolve", {
      paper,
      review,
      returns_source: returnsSource,
      session_id: sessionId,
      ...(llmProvider ? { llm_provider: llmProvider, llm_model: llmModel } : {}),
    }),
  listMethodSpecs: (stage: MethodSpecStage) => api.get<string[]>(`/api/methodspecs/${stage}`),
  getMethodSpec: (stage: MethodSpecStage, factorId: string) =>
    api.get<Record<string, unknown>>(`/api/methodspecs/${stage}/${encodeURIComponent(factorId)}`),

  /** Mechanically-derived per-field reference (description/example/
   * allowed_values/usage), generated straight from the `MethodSpec` pydantic
   * model -- see `SchemaReferencePage.tsx` for the other consumer. */
  getSchemaReference: () =>
    api.get<{
      fields: Record<
        string,
        { description: string; example: string; allowed_values: string[] | null; usage: string }
      >
    }>("/api/methodspecs/schema"),

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
  // shortcut, reusing the paper-first (v2) resolved-spec listing rather
  // than the deleted v1 `/api/methodspecs/resolved*` endpoints.
  listResolvedMethodSpecs: () => api.get<string[]>("/api/methodspecs/resolved"),
  getResolvedMethodSpec: (factorId: string) =>
    api.get<Record<string, unknown>>(`/api/methodspecs/resolved/${factorId}`),
  generatePlugin: (spec: Record<string, unknown>, llmProvider: string) =>
    api.post<{ job_id: string }>("/api/codegen", { spec, llm_provider: llmProvider }),

  listSnapshots: () => api.get<{ snapshot_id: string }[]>("/api/backtest/snapshots"),
}
