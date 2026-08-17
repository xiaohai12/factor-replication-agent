// Single source of truth for the 8-step pipeline, mirroring
// src/infra/models/session.py's STEP_NAMES/STEP_IO_CONTRACT. Drives the
// stepper UI, routing, and each step's default request-body template --
// do NOT duplicate this list elsewhere (Phase 4, docs/decision-log.md
// 2026-08-04).

export interface StepDefinition {
  step: number
  name: string
  label: string
  /** Whether this step's action endpoint runs as a background job (SSE) vs
   * a plain synchronous request/response. */
  isJob: boolean
  endpoint: (sessionId: string) => string
  /** A pretty-printed JSON template shown in the request-body editor. */
  requestTemplate: Record<string, unknown>
}

export const STEP_REGISTRY: StepDefinition[] = [
  {
    step: 1,
    name: "extract",
    label: "1. Extract MethodSpec",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/1/extract`,
    requestTemplate: { expected_revision: 0, paper_text: "", llm_provider: "codex" },
  },
  {
    step: 2,
    name: "review",
    label: "2. Review (LLM-backed)",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/2/review`,
    requestTemplate: { expected_revision: 0, spec: {}, llm_provider: "codex" },
  },
  {
    step: 3,
    name: "codegen",
    label: "3. Codegen (build script)",
    isJob: false,
    endpoint: (sid) => `/api/sessions/${sid}/steps/3/script`,
    requestTemplate: {
      expected_revision: 0,
      spec: {},
      plugin: {},
      track: "original_method",
    },
  },
  {
    step: 4,
    name: "validate",
    label: "4. Validate script",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/4/validate`,
    requestTemplate: {
      expected_revision: 0,
      script_sha256: "",
    },
  },
  {
    step: 5,
    name: "execute",
    label: "5. Execute backtest",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/5/execute`,
    requestTemplate: {
      expected_revision: 0,
      script_sha256: "",
      track: "original_method",
    },
  },
  {
    step: 6,
    name: "experiment",
    label: "6. Multi-track experiment",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/6/experiment`,
    requestTemplate: {
      expected_revision: 0,
      spec: {},
      plugin: {},
      // Real WRDS data (backend/state.py's REAL_WRDS_SNAPSHOT_ID) -- same
      // snapshot step5 always runs against, not the synthetic demo data.
      snapshot_id: "real_wrds_local_v1",
      run_original: true,
      run_standardized: true,
      // Per-field ablation/factorial switches have no UI control (2026-08-16,
      // the ①②③ picker is the whole "which versions to run" model) -- default
      // to none so nothing runs that isn't visibly chosen on screen. Still
      // settable via the raw request body for other (e.g. yaml matrix) callers.
      ablation_switches: [],
      factorial_switches: [],
      // docs/step6.md §4a default: when both switch lists above are empty,
      // auto-derive factorial (<=5 differing fields, exact) or OAT (>5)
      // attribution tracks from the real config diff -- see the "Auto
      // attribution" checkbox in the versions picker below.
      auto_attribution: true,
    },
  },
  {
    step: 7,
    name: "replication_diff",
    label: "7. Replication comparison",
    isJob: false,
    endpoint: (sid) => `/api/sessions/${sid}/steps/7/comparison`,
    requestTemplate: { expected_revision: 0, experiment_batch_id: "" },
  },
  {
    step: 8,
    name: "diagnosis",
    label: "8. Diagnosis (opt-in, LLM)",
    isJob: true,
    endpoint: (sid) => `/api/sessions/${sid}/steps/8/diagnosis`,
    requestTemplate: { expected_revision: 0, llm_provider: "codex" },
  },
]

export function stepDefinition(step: number): StepDefinition {
  const def = STEP_REGISTRY.find((s) => s.step === step)
  if (!def) throw new Error(`Unknown step ${step}`)
  return def
}
