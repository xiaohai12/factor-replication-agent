import { useQueries, useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { JsonTree } from "@/components/JsonTree"
import { CodeView } from "@/components/CodeView"
import { DiffView } from "@/components/DiffView"
import { GapWaterfallChart } from "@/components/GapWaterfallChart"
import { MultiTrackChart, type TrackSeries } from "@/components/MultiTrackChart"
import { ReturnChart, type ReturnRow } from "@/components/ReturnChart"
import { api } from "@/lib/api"
import { parseSimpleCsv } from "@/lib/csv"
import { sessionApi } from "@/lib/sessionApi"
import type { StepAttempt } from "@/lib/types"

interface RunRecordLike {
  run_id: string
  track: string
  factor_id: string
  status: string
}

async function fetchReturnSeries(factorId: string, runId: string): Promise<ReturnRow[]> {
  const text = await api.getText(`/api/evidence/${factorId}/${runId}/download/return_series.csv`)
  return parseSimpleCsv(text).map((row) => ({
    yyyymm: Number(row.yyyymm),
    ls_return: Number(row.ls_return ?? row.monthly_return ?? 0),
  }))
}

/** Per-step specialized output visualization -- Phase E of the
 * session-centric UI redesign. Falls back to a plain `JsonTree` of
 * whatever the step's own sync/job result already contains when no richer
 * view applies, so every step always shows SOMETHING even before its
 * dedicated panel is built out further. */
export function StepOutputView({
  step,
  sessionId,
  factorId,
  attempt,
  syncResult,
}: {
  step: number
  sessionId: string
  factorId: string
  attempt: StepAttempt | undefined
  syncResult: unknown
}) {
  const refs = attempt?.output_refs ?? {}

  // --- step1: extracted MethodSpec tree, ambiguous fields highlighted ---
  const step1Artifact = useQuery({
    queryKey: ["step-artifact", sessionId, 1, refs.methodspec_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 1, refs.methodspec_ref),
    enabled: step === 1 && !!refs.methodspec_ref,
  })

  // --- step3: plugin code + assembled script ---
  const step3Plugin = useQuery({
    queryKey: ["step-artifact", sessionId, 3, refs.plugin_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, refs.plugin_ref),
    enabled: step === 3 && !!refs.plugin_ref,
  })
  const step3Script = useQuery({
    queryKey: ["step-artifact", sessionId, 3, refs.script_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, refs.script_ref),
    enabled: step === 3 && !!refs.script_ref,
  })

  // --- step4: validation report ---
  const step4Report = useQuery({
    queryKey: ["step-artifact", sessionId, 4, refs.validation_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 4, refs.validation_ref),
    enabled: step === 4 && !!refs.validation_ref,
  })

  // --- step5: return series for the single execution ---
  const step5ExecutionIds: string[] = step === 5 && refs.execution_ids ? JSON.parse(refs.execution_ids) : []
  const step5Series = useQuery({
    queryKey: ["return-series", factorId, step5ExecutionIds[0]],
    queryFn: () => fetchReturnSeries(factorId, step5ExecutionIds[0]),
    enabled: step === 5 && step5ExecutionIds.length > 0,
  })

  // --- step6: multi-track overlay ---
  const step6ExecutionIds: string[] = step === 6 && refs.execution_ids ? JSON.parse(refs.execution_ids) : []
  const step6Runs = useQuery({
    queryKey: ["runs", factorId],
    queryFn: () => api.get<RunRecordLike[]>(`/api/runs/${factorId}`),
    enabled: step === 6 && step6ExecutionIds.length > 0,
  })
  const relevantRuns = (step6Runs.data ?? []).filter((r) => step6ExecutionIds.includes(r.run_id))
  const step6Series = useQueries({
    queries: relevantRuns.map((run) => ({
      queryKey: ["return-series", factorId, run.run_id],
      queryFn: () => fetchReturnSeries(factorId, run.run_id),
      enabled: step === 6,
    })),
  })

  // --- step7: comparison bundle (gap decomposition, config diff) ---
  const step7Bundle = useQuery({
    queryKey: ["comparison", sessionId],
    queryFn: () => sessionApi.getComparison(sessionId),
    enabled: step === 7 && !!refs.comparison_ref,
  })

  // --- step8: diagnosis claims ---
  const step8Diagnosis = useQuery({
    queryKey: ["diagnosis", sessionId],
    queryFn: () => api.get<Record<string, unknown>>(`/api/sessions/${sessionId}/steps/8/diagnosis`),
    enabled: step === 8 && !!refs.diagnosis_ref,
  })

  if (step === 1 && step1Artifact.data) {
    return <JsonTree name="MethodSpec" data={JSON.parse(step1Artifact.data.content)} />
  }

  if (step === 3 && (step3Plugin.data || step3Script.data)) {
    return (
      <div className="flex flex-col gap-3">
        {step3Plugin.data && (
          <div>
            <p className="mb-1 text-xs font-medium">compute_signal plugin</p>
            <CodeView code={JSON.parse(step3Plugin.data.content).code ?? ""} language="python" />
          </div>
        )}
        {step3Script.data && (
          <div>
            <p className="mb-1 text-xs font-medium">Assembled backtest script</p>
            <CodeView code={step3Script.data.content} language="python" />
          </div>
        )}
      </div>
    )
  }

  if (step === 4 && step4Report.data) {
    const report = JSON.parse(step4Report.data.content)
    const checks: [string, boolean | string][] = [
      ["syntax_ok", report.syntax_ok],
      ["schema_ok", report.schema_ok],
      ["no_future_leak", report.no_future_leak],
      ["reproducible", report.reproducible],
      ["executes_ok", report.executes_ok],
    ]
    return (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-1">
          {checks.map(([label, value]) => (
            <Badge key={label} variant={value ? "default" : "destructive"}>
              {label}: {String(value)}
            </Badge>
          ))}
        </div>
        {(report.errors ?? []).map((e: string, i: number) => (
          <p key={i} className="text-xs text-destructive">
            {e}
          </p>
        ))}
      </div>
    )
  }

  if (step === 5 && step5Series.data) {
    return <ReturnChart data={step5Series.data} />
  }

  if (step === 6 && relevantRuns.length > 0) {
    const series: TrackSeries[] = relevantRuns
      .map((run, i) => ({ track: run.track, rows: step6Series[i]?.data ?? [] }))
      .filter((s) => s.rows.length > 0)
    return <MultiTrackChart series={series} />
  }

  if (step === 7 && step7Bundle.data) {
    const bundle = step7Bundle.data
    const derived = (bundle.derived as Record<string, unknown>) ?? {}
    const gap = (bundle.gap_decomposition as Record<string, unknown>) ?? {}
    const configDiff = (bundle.config_diff as { baseline_track?: string; pairs?: Record<string, unknown> }) ?? {}
    const tracks = (bundle.tracks as Record<string, { config?: Record<string, unknown> }>) ?? {}
    const baselineTrack = configDiff.baseline_track
    const baselineConfig = (baselineTrack && tracks[baselineTrack]?.config) || {}
    const pairTrackNames = Object.keys(configDiff.pairs ?? {})
    return (
      <div className="flex flex-col gap-3">
        <Badge variant="outline">overall_tag: {String(derived.overall_tag ?? "inconclusive")}</Badge>
        <GapWaterfallChart gapDecomposition={gap} />
        {baselineTrack &&
          pairTrackNames.map((track) => (
            <div key={track}>
              <p className="mb-1 text-xs font-medium">
                {track} vs {baselineTrack} config
              </p>
              <DiffView
                left={baselineConfig}
                right={tracks[track]?.config ?? {}}
                leftLabel={baselineTrack}
                rightLabel={track}
              />
            </div>
          ))}
      </div>
    )
  }

  if (step === 8 && step8Diagnosis.data) {
    const claims = (step8Diagnosis.data.claims as Record<string, unknown>[]) ?? []
    const rejected = (step8Diagnosis.data.rejected_claims as Record<string, unknown>[]) ?? []
    return (
      <div className="flex flex-col gap-2">
        <Badge variant="outline">{String(step8Diagnosis.data.status)}</Badge>
        {claims.map((c, i) => (
          <p key={i} className="rounded-md border border-border p-2 text-xs">
            {String(c.text)}
          </p>
        ))}
        {rejected.length > 0 && (
          <div className="rounded-md border border-destructive/40 p-2 text-xs">
            <p className="font-medium text-destructive">Rejected claims (audit)</p>
            {rejected.map((r, i) => (
              <p key={i} className="text-muted-foreground">
                ⚑ {String(r.reason)}
              </p>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Fallback: whatever the step just returned (or nothing yet).
  if (syncResult != null) {
    return <JsonTree name="result" data={syncResult} />
  }
  return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
}
