// Types mirroring src/infra/models/session.py's SessionManifest/StepRecord/
// StepAttempt. Kept as the ONE typed surface the session pages/components
// use (Phase 4 of the session-centric UI redesign) instead of each page
// re-declaring its own ad hoc interface (the pre-existing pattern in
// PipelineE2EPage/BacktestExperimentsPage, which duplicated shapes).

export type SessionState =
  | "created"
  | "extracting"
  | "awaiting_review"
  | "ready_for_codegen"
  | "script_built"
  | "validated"
  | "executing"
  | "experiment_complete"
  | "comparison_complete"
  | "diagnosis_complete"
  | "blocked"
  | "failed"
  | "interrupted"
  | "cancelled"
  | "archived"

export type StepStatus = "not_started" | "running" | "success" | "failed" | "blocked"

// Deliberately NOT a unified quality score -- see src/evaluation/diagnostics.py's
// module docstring. `readiness` only answers "can the UI let the user advance".
export interface StepDiagnostics {
  readiness: "ready" | "not_ready" | "blocked"
  counters: Record<string, unknown>
  flags: string[]
}

export interface StepAttempt {
  attempt_index: number
  status: StepStatus
  started_at: string | null
  completed_at: string | null
  job_id: string | null
  error: string | null
  output_refs: Record<string, string>
  diagnostics: StepDiagnostics | Record<string, never>
  input_ref_snapshot: Record<string, string>
}

export interface StepRecord {
  step: number
  name: string
  attempts: StepAttempt[]
  stale: boolean
}

export interface SessionManifest {
  schema_version: number
  session_id: string
  factor_id: string
  paper_id: string | null
  state: SessionState
  revision: number
  created_at: string
  updated_at: string
  steps: Record<string, StepRecord>
  transition_log: Record<string, unknown>[]
}

export interface StepIoContract {
  input_refs: string[]
  output_refs: string[]
}

export interface SessionEvent {
  seq: number
  at: string
  step: number | null
  stage: string
  event: string
  detail: string
  level: "info" | "warning" | "error"
}
