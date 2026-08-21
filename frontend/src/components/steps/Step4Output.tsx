import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { CodeView } from "@/components/CodeView"
import { JsonTree } from "@/components/JsonTree"
import { MetricsTable } from "@/components/MetricsTable"
import { latestSuccessRef } from "@/lib/manifestArtifacts"
import { sessionApi } from "@/lib/sessionApi"
import type { SessionManifest, StepAttempt } from "@/lib/types"

interface ValidationReport {
  passed: boolean
  syntax_ok: boolean
  schema_ok: boolean
  no_future_leak: boolean
  reproducible: boolean
  executes_ok: boolean
  faithful_ok: boolean
  errors: string[]
  warnings: string[]
  technical_metrics: Record<string, unknown>
}

interface RepairAttempt {
  attempt_index: number
  trigger_stage: string
  trigger_error: string
  code_hash_before: string
  code_hash_after: string
  passed: boolean
}

function usePluginCode(sessionId: string, step: number, pluginRef: string | undefined) {
  const query = useQuery({
    queryKey: ["step-artifact", sessionId, step, pluginRef],
    queryFn: () => sessionApi.getStepArtifact(sessionId, step, pluginRef!),
    enabled: !!pluginRef,
  })
  const code = query.data ? (JSON.parse(query.data.content) as { code?: string }).code : undefined
  return { code, isLoading: query.isLoading }
}

/** Renders in the request/result grid's "Result" slot for step4 -- shows the
 * technical repair's before/after code (both fully reconstructable from
 * persisted artifacts: step3's own `plugin_ref` vs. step4's, only present
 * when a repair actually rewrote the code) instead of a generic JSON blob. */
export function Step4RepairCard({
  sessionId,
  attempt,
  manifest,
}: {
  sessionId: string
  attempt: StepAttempt | undefined
  manifest: SessionManifest
}) {
  const step3PluginRef = latestSuccessRef(manifest, 3, "plugin_ref")
  const step4PluginRef = attempt?.output_refs.plugin_ref
  const before = usePluginCode(sessionId, 3, step3PluginRef)
  const after = usePluginCode(sessionId, 4, step4PluginRef)

  if (before.isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (!before.code) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>

  if (!step4PluginRef) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-xs text-muted-foreground">No repair was needed -- code unchanged from step3.</p>
        <CodeView code={before.code} language="python" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="flex flex-col gap-1">
        <p className="text-xs font-medium">Before repair (step3)</p>
        <CodeView code={before.code} language="python" />
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-xs font-medium">After repair (step4)</p>
        <CodeView code={after.code ?? ""} language="python" />
      </div>
    </div>
  )
}

function StageBadge({ status }: { status: "pass" | "fail" | "not_run" }) {
  const variant = status === "pass" ? "default" : status === "fail" ? "destructive" : "outline"
  const text = status === "not_run" ? "not run" : status
  return <Badge variant={variant}>{text}</Badge>
}

/** Renders in the "Step output" card below the request/result grid. Stage1
 * vs. stage2 pass/fail is DERIVED, never a literal backend field -- both
 * stages share the same `ValidationReport.passed`, which stage2's run
 * overwrites after stage1 already succeeded (see `/steps/4/validate` in
 * backend/routers/sessions.py). `repair_history[-1].passed` (when a repair
 * happened) already tells stage1's own outcome independent of whatever
 * stage2 later does to `report.passed`; empty history means stage1 passed
 * on the first try (the backend only enters the repair loop on failure). */
export function Step4Output({
  sessionId,
  attempt,
  syncResult,
}: {
  sessionId: string
  attempt: StepAttempt | undefined
  syncResult: unknown
}) {
  const refs = attempt?.output_refs ?? {}
  const reportQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 4, refs.validation_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 4, refs.validation_ref),
    enabled: !!refs.validation_ref,
  })

  if (!reportQuery.data) {
    return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
  }

  const report = JSON.parse(reportQuery.data.content) as ValidationReport
  // Only present in the job's just-completed result, never persisted as a
  // session artifact -- gone after a page reload once the job has finished.
  const repairHistory =
    ((syncResult as { repair_history?: RepairAttempt[] } | undefined)?.repair_history as RepairAttempt[]) ?? []

  const stage1Passed = repairHistory.length === 0 ? true : repairHistory[repairHistory.length - 1].passed
  const stage2Status: "pass" | "fail" | "not_run" = !stage1Passed ? "not_run" : report.passed ? "pass" : "fail"

  const checks: [string, boolean][] = [
    ["syntax_ok", report.syntax_ok],
    ["schema_ok", report.schema_ok],
    ["no_future_leak", report.no_future_leak],
    ["reproducible", report.reproducible],
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={report.passed ? "default" : "destructive"}>
          overall: {report.passed ? "passed" : "failed"}
        </Badge>
        {refs.validated_script_sha256 && (
          <span className="font-mono text-muted-foreground">
            validated script: {refs.validated_script_sha256.slice(0, 12)}…
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold">Stage 1 — signal smoke test (+ technical repair)</p>
          <StageBadge status={stage1Passed ? "pass" : "fail"} />
        </div>
        <div className="flex flex-wrap gap-1">
          {checks.map(([label, value]) => (
            <Badge key={label} variant={value ? "default" : "destructive"}>
              {label}: {String(value)}
            </Badge>
          ))}
          <Badge variant="outline">faithful_ok: {report.faithful_ok ? "skipped" : "false"}</Badge>
        </div>
        {Object.keys(report.technical_metrics ?? {}).length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium">Technical metrics</p>
            <MetricsTable metrics={report.technical_metrics} />
          </div>
        )}
        {repairHistory.length > 0 ? (
          <div>
            <p className="mb-1 text-xs font-medium">
              Repair attempts (this run only -- not persisted across reloads)
            </p>
            <table className="w-full border-collapse text-xs">
              <tbody>
                {repairHistory.map((r) => (
                  <tr key={r.attempt_index} className="border-b border-border/50 last:border-0">
                    <td className="py-1 pr-3">#{r.attempt_index}</td>
                    <td className="py-1 pr-3">{r.trigger_stage}</td>
                    <td className="py-1 pr-3 font-mono text-muted-foreground" title={r.trigger_error}>
                      {r.code_hash_before.slice(0, 8)} → {r.code_hash_after.slice(0, 8)}
                    </td>
                    <td className="py-1">
                      <Badge variant={r.passed ? "default" : "destructive"}>{r.passed ? "passed" : "failed"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No repair needed.</p>
        )}
      </div>

      <div className="flex items-center justify-between rounded-md border border-border p-3">
        <p className="text-xs font-semibold">Stage 2 — full script run on validation sample (no auto-repair)</p>
        <StageBadge status={stage2Status} />
      </div>

      {(report.errors.length > 0 || report.warnings.length > 0) && (
        <div className="flex flex-col gap-1">
          {report.errors.map((e, i) => (
            <p key={i} className="text-xs text-destructive">
              {e}
            </p>
          ))}
          {report.warnings.map((w, i) => (
            <p key={i} className="text-xs text-muted-foreground">
              ⚑ {w}
            </p>
          ))}
        </div>
      )}

      <details>
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Debug / provenance</summary>
        <div className="mt-2 flex flex-col gap-2">
          {attempt?.diagnostics && "readiness" in attempt.diagnostics && (
            <div className="flex flex-col gap-1 text-xs">
              <span>
                readiness: <Badge variant="outline">{attempt.diagnostics.readiness}</Badge>
              </span>
              {attempt.diagnostics.flags.map((f, i) => (
                <p key={i} className="text-muted-foreground">
                  ⚑ {f}
                </p>
              ))}
            </div>
          )}
          <JsonTree name="report" data={report} />
        </div>
      </details>
    </div>
  )
}
