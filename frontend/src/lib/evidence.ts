import { api } from "@/lib/api"
import { parseSimpleCsv } from "@/lib/csv"
import type { ReturnRow } from "@/components/ReturnChart"

/** Loose RunRecord shape shared by the step5/6/7 output views -- mirrors
 * `src/infra/models/run_record.py`'s `RunRecord`/`RunMetrics`, but kept as a
 * plain untyped-ish interface since the frontend only ever reads a subset. */
export interface RunRecord {
  run_id: string
  factor_id: string
  track: string
  status: string
  code_hash?: string
  data_snapshot_hash?: string
  config_hash?: string
  method_spec_hash?: string
  is_bridge_track?: boolean
  switches_flipped?: Record<string, unknown> | null
  runtime_provenance?: Record<string, unknown>
  metrics?: Record<string, unknown>
  experiment_batch_id?: string
  frozen_plugin_hash?: string
  batch_invalidated?: boolean
  batch_invalidation_reason?: string
  repair_history?: { attempt_index: number; trigger_stage: string; passed: boolean }[]
}

// `run.factor_id` (from `spec.paper.factor_id`) can legitimately differ from
// the SESSION's own `factor_id` (a freeform string typed when the run was
// created, src/steps/step5_backtest_runner/__init__.py's `_spec_factor_id`)
// -- there is no enforced link between the two. Looking a run up by
// `/api/runs/{sessionFactorId}` silently returns nothing whenever they
// don't match byte-for-byte. `fetchRuns()` therefore hits the GLOBAL
// `/api/runs` (unscoped) and callers filter by `run_id`, which is always
// known from `execution_ids` -- then use the found run's OWN `factor_id`
// for any evidence/download call, never the session's.
export async function fetchRuns(): Promise<RunRecord[]> {
  const res = await api.get<{ summary: unknown; runs: RunRecord[] }>("/api/runs")
  return res.runs
}

export async function fetchReturnSeries(factorId: string, runId: string): Promise<ReturnRow[]> {
  const text = await api.getText(`/api/evidence/${factorId}/${runId}/download/return_series.csv`)
  return parseSimpleCsv(text).map((row) => ({
    yyyymm: Number(row.yyyymm),
    ls_return: Number(row.ls_return ?? row.monthly_return ?? 0),
  }))
}

export async function fetchEvidenceFiles(factorId: string, runId: string): Promise<string[]> {
  const res = await api.get<{ files: string[] }>(`/api/evidence/${factorId}/${runId}`)
  return res.files
}
