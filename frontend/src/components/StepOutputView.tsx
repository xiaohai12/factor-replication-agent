import { useState } from "react"
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { JsonTree } from "@/components/JsonTree"
import { CodeView } from "@/components/CodeView"
import { DiffView } from "@/components/DiffView"
import { GapWaterfallChart } from "@/components/GapWaterfallChart"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { MultiTrackChart, type TrackSeries } from "@/components/MultiTrackChart"
import { ReturnChart, type ReturnRow } from "@/components/ReturnChart"
import { api } from "@/lib/api"
import { parseSimpleCsv } from "@/lib/csv"
import { sessionApi } from "@/lib/sessionApi"
import type { StepAttempt } from "@/lib/types"
import { parseResolutionValue, splitIssuesBySeverity } from "@/lib/utils"

interface FieldReviewNote {
  field: string
  status: string
  reason: string
  current_value: unknown
  candidate_value: unknown
}

interface ReviewResult {
  disposition: string
  reviewer: string
  issues: string[]
  warnings: string[]
  blocked_fields: string[]
  field_notes: FieldReviewNote[]
}

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
  sessionRevision,
  onResolved,
}: {
  step: number
  sessionId: string
  factorId: string
  attempt: StepAttempt | undefined
  syncResult: unknown
  sessionRevision?: number
  onResolved?: () => void
}) {
  const refs = attempt?.output_refs ?? {}
  const queryClient = useQueryClient()

  // --- step2: resolution form state (blocked-field confirmation UI) ---
  const [resolutionValues, setResolutionValues] = useState<Record<string, string>>({})
  const [resolutionReasons, setResolutionReasons] = useState<Record<string, string>>({})
  const [useOtherFor, setUseOtherFor] = useState<Record<string, boolean>>({})

  // --- step1: extracted MethodSpec tree, ambiguous fields highlighted ---
  const step1Artifact = useQuery({
    queryKey: ["step-artifact", sessionId, 1, refs.methodspec_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 1, refs.methodspec_ref),
    enabled: step === 1 && !!refs.methodspec_ref,
  })

  // --- step2: review result + blocked-field resolution form. The spec
  // being reviewed always lives at step1's fixed "methodspec.json" filename
  // (there is exactly one live copy per session -- resolve step2 overwrites
  // it in place), so this doesn't depend on step2's own output_refs. ---
  const step2Spec = useQuery({
    queryKey: ["step-artifact", sessionId, 1, "methodspec.json"],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 1, "methodspec.json"),
    enabled: step === 2,
  })
  const step2Review = useQuery({
    queryKey: ["step-artifact", sessionId, 2, refs.review_report_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 2, refs.review_report_ref),
    enabled: step === 2 && !!refs.review_report_ref,
  })
  const fieldHelp = useQuery({
    queryKey: ["field-help"],
    queryFn: () => sessionApi.getFieldHelp(),
    enabled: step === 2,
  })
  const resolveMutation = useMutation({
    mutationFn: (decisions: Record<string, unknown>[]) => {
      const spec = JSON.parse(step2Spec.data!.content)
      return sessionApi.resolveStep2(sessionId, sessionRevision ?? 0, spec, decisions)
    },
    onSuccess: () => {
      setResolutionValues({})
      setResolutionReasons({})
      setUseOtherFor({})
      queryClient.invalidateQueries({ queryKey: ["step-artifact", sessionId, 1, "methodspec.json"] })
      onResolved?.()
    },
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
    return <MethodSpecBoard spec={JSON.parse(step1Artifact.data.content)} />
  }

  if (step === 2 && step2Review.data) {
    const review = JSON.parse(step2Review.data.content) as ReviewResult
    const isBlocked = review.blocked_fields.length > 0
    // More than one `_check_*` rule (or the LLM's own note plus a merged
    // deterministic precheck note) can independently flag the SAME field --
    // dedupe by field path so React never sees two list items with the same
    // key, and so a resolution decision isn't submitted twice for one field.
    const seenBlockedFields = new Set<string>()
    const blockedNotes = review.field_notes.filter((n) => {
      if (!review.blocked_fields.includes(n.field) || seenBlockedFields.has(n.field)) return false
      seenBlockedFields.add(n.field)
      return true
    })
    const { required: requiredIssues, advisory: advisoryIssues } = splitIssuesBySeverity(review.issues)
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Badge variant={review.disposition === "approved" ? "default" : isBlocked ? "destructive" : "secondary"}>
            {review.disposition}
          </Badge>
          <Badge variant="outline">{review.reviewer === "rules" ? "Rules-based review" : "LLM-backed review"}</Badge>
        </div>
        {requiredIssues.length > 0 && (
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium text-destructive">Must resolve ({requiredIssues.length})</p>
            {requiredIssues.map((issue, i) => (
              <p key={i} className="text-xs text-destructive">
                ⚠ {issue}
              </p>
            ))}
          </div>
        )}
        {advisoryIssues.length > 0 && (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Advisory notes ({advisoryIssues.length}) -- don't block approval</summary>
            {advisoryIssues.map((issue, i) => (
              <p key={i} className="pl-4">
                ℹ {issue}
              </p>
            ))}
          </details>
        )}
        {review.warnings.length > 0 && (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Warnings ({review.warnings.length})</summary>
            {review.warnings.map((warning, i) => (
              <p key={i} className="pl-4">
                ℹ {warning}
              </p>
            ))}
          </details>
        )}
        {isBlocked && step2Spec.data && (
          <div className="flex flex-col gap-3 rounded-md border border-border p-3">
            <p className="text-sm font-medium">Resolve blocked fields</p>
            <p className="text-xs text-muted-foreground">
              Leave a field blank to skip it -- it stays blocked and can be resolved later.
            </p>
            {blockedNotes.map((note) => {
              const help = fieldHelp.data?.[note.field]
              const hasOptions = !!help?.options?.length
              const usingOther = useOtherFor[note.field] ?? false
              return (
                <div key={note.field} className="flex flex-col gap-1">
                  <Label>{note.field}</Label>
                  {help?.description && <p className="text-xs text-muted-foreground">ℹ {help.description}</p>}
                  {help?.example && (
                    <p className="text-xs text-muted-foreground">
                      📝 Example: <code>{help.example}</code>
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">Why it's blocked: {note.reason}</p>
                  {note.candidate_value != null && (
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-emerald-600">
                        💡 Suggested value: <code>{String(note.candidate_value)}</code> (pre-filled below -- review it,
                        don't just accept it blindly)
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setResolutionValues((prev) => ({ ...prev, [note.field]: String(note.candidate_value) }))
                          setResolutionReasons((prev) => ({
                            ...prev,
                            [note.field]:
                              prev[note.field] ||
                              "Paper does not state this; using the project's standard convention.",
                          }))
                        }}
                      >
                        Use suggested value
                      </Button>
                    </div>
                  )}
                  {hasOptions && !usingOther ? (
                    <Select
                      value={resolutionValues[note.field] ?? (note.candidate_value != null ? String(note.candidate_value) : "")}
                      onValueChange={(v) => {
                        if (v === "__other__") {
                          setUseOtherFor((prev) => ({ ...prev, [note.field]: true }))
                          setResolutionValues((prev) => ({ ...prev, [note.field]: "" }))
                        } else {
                          setResolutionValues((prev) => ({ ...prev, [note.field]: v }))
                        }
                      }}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Select a value" />
                      </SelectTrigger>
                      <SelectContent>
                        {help!.options.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {opt}
                          </SelectItem>
                        ))}
                        <SelectItem value="__other__">Other (type my own)</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="flex flex-col gap-1">
                      <Input
                        placeholder={help?.example ? `e.g. ${help.example} (leave blank to skip)` : "New value (leave blank to skip)"}
                        value={resolutionValues[note.field] ?? (note.candidate_value != null ? String(note.candidate_value) : "")}
                        onChange={(e) => setResolutionValues((prev) => ({ ...prev, [note.field]: e.target.value }))}
                      />
                      {hasOptions && (
                        <button
                          type="button"
                          className="text-left text-xs text-muted-foreground underline"
                          onClick={() => setUseOtherFor((prev) => ({ ...prev, [note.field]: false }))}
                        >
                          Choose from the list instead
                        </button>
                      )}
                    </div>
                  )}
                  <Input
                    placeholder="Reason (optional -- cite the paper if you have a quote)"
                    value={resolutionReasons[note.field] ?? ""}
                    onChange={(e) => setResolutionReasons((prev) => ({ ...prev, [note.field]: e.target.value }))}
                  />
                </div>
              )
            })}
            <Button
              disabled={resolveMutation.isPending}
              onClick={() => {
                const decisions = blockedNotes
                  .map((note) => {
                    const hasTyped = note.field in resolutionValues
                    const value = hasTyped ? parseResolutionValue(resolutionValues[note.field]) : note.candidate_value
                    return { note, value }
                  })
                  // A field the user never touched AND has no candidate default,
                  // or one the user explicitly cleared to blank, is left blocked
                  // -- "leave blank to skip" instead of forcing a fabricated
                  // "unspecified" string (which crashes validation for
                  // dict/list-typed fields like data.normalized_mapping).
                  .filter(({ value }) => value !== undefined && value !== null && value !== "")
                  .map(({ note, value }) => ({
                    field_path: note.field,
                    canonical_field_path: note.field,
                    old_value: note.current_value ?? null,
                    new_value: value,
                    decision_type: "human_empirical_assumption",
                    reason: resolutionReasons[note.field] || "Resolved via session step2 wizard.",
                    reviewer: "human",
                    paper_evidence: [],
                  }))
                resolveMutation.mutate(decisions)
              }}
            >
              {resolveMutation.isPending ? "Submitting…" : "Submit resolution"}
            </Button>
            {resolveMutation.isError && (
              <p className="text-xs text-destructive">{String(resolveMutation.error)}</p>
            )}
          </div>
        )}
      </div>
    )
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
