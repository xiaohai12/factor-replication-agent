import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { JsonTree } from "@/components/JsonTree"
import { DiffView } from "@/components/DiffView"
import { GapWaterfallChart } from "@/components/GapWaterfallChart"
import { Step3Output } from "@/components/steps/Step3Output"
import { Step4Output } from "@/components/steps/Step4Output"
import { Step5Output } from "@/components/steps/Step5Output"
import { Step6Output } from "@/components/steps/Step6Output"
import { api } from "@/lib/api"
import { sessionApi } from "@/lib/sessionApi"
import type { SessionManifest, StepAttempt } from "@/lib/types"

/** Per-step specialized output visualization -- Phase E of the
 * session-centric UI redesign. Falls back to a plain `JsonTree` of
 * whatever the step's own sync/job result already contains when no richer
 * view applies, so every step always shows SOMETHING even before its
 * dedicated panel is built out further. */
export function StepOutputView({
  step,
  sessionId,
  attempt,
  syncResult,
  manifest,
  paperReported,
  czReported,
}: {
  step: number
  sessionId: string
  attempt: StepAttempt | undefined
  syncResult: unknown
  manifest: SessionManifest | undefined
  paperReported?: { mean_return?: number; t_stat?: number } | null
  czReported?: { mean_return: number | null; t_stat: number | null } | null
}) {
  const refs = attempt?.output_refs ?? {}

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

  if (step === 3) {
    return <Step3Output sessionId={sessionId} attempt={attempt} />
  }

  if (step === 4) {
    return <Step4Output sessionId={sessionId} attempt={attempt} syncResult={syncResult} />
  }

  if (step === 5) {
    return <Step5Output sessionId={sessionId} attempt={attempt} manifest={manifest} />
  }

  if (step === 6) {
    return (
      <Step6Output sessionId={sessionId} attempt={attempt} paperReported={paperReported} czReported={czReported} />
    )
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
