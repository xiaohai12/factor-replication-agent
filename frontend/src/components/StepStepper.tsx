import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { STEP_REGISTRY } from "@/lib/steps"
import type { MethodSpecWorkflowState } from "@/lib/methodSpecStore"
import type { SessionManifest, StepStatus } from "@/lib/types"

const STATUS_VARIANT: Record<StepStatus, "default" | "secondary" | "destructive" | "outline"> = {
  not_started: "outline",
  running: "secondary",
  success: "default",
  failed: "destructive",
  blocked: "destructive",
}

/** Steps 1/2's own progress lives client-side in `MethodSpecWorkflowState`
 * (sessionStorage), not the session manifest's step attempts (see
 * `docs/known-gaps-paper-first-v2.md`) -- derive an equivalent `StepStatus`
 * from it so those two nodes color the same way steps 3-8 do. */
function specStepStatus(specState: MethodSpecWorkflowState | undefined, step: number): StepStatus | undefined {
  if (!specState) return undefined
  if (step === 1) return specState.paper ? "success" : "not_started"
  if (step === 2) {
    if (specState.resolved) return "success"
    if (specState.review) {
      const findings = (specState.review.findings as Array<Record<string, unknown>> | undefined) ?? []
      return findings.some((f) => f.disposition === "blocked") ? "blocked" : "running"
    }
    return "not_started"
  }
  return undefined
}

/** Session-owned stepper driven entirely by session state, except steps 1/2
 * which fall back to `specState` (see `specStepStatus` above) since the
 * paper-first MethodSpec lifecycle is global and persisted under
 * runs/method_specs, not as session step attempts.
 *
 * Readiness/status
 * badges come from the session's own recorded diagnostics/attempts, never
 * a client-side guess. Clicking a node is always allowed (per Phase 1's
 * "every step can run standalone from a stored upstream artifact"
 * requirement) -- there is no disabled/locked state here. */
export function StepStepper({
  manifest,
  activeStep,
  specState,
  onSelect,
}: {
  manifest: SessionManifest
  activeStep: number
  specState?: MethodSpecWorkflowState
  onSelect: (step: number) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {STEP_REGISTRY.map((def) => {
        const record = manifest.steps[String(def.step)]
        const latest = record?.attempts[record.attempts.length - 1]
        const status: StepStatus = specStepStatus(specState, def.step) ?? latest?.status ?? "not_started"
        const readiness = latest?.diagnostics && "readiness" in latest.diagnostics ? latest.diagnostics.readiness : undefined

        return (
          <button
            key={def.step}
            type="button"
            onClick={() => onSelect(def.step)}
            className={cn(
              "flex flex-col items-start gap-1 rounded-lg border border-border px-3 py-2 text-left transition-colors",
              activeStep === def.step ? "bg-muted" : "hover:bg-muted/50",
            )}
          >
            <span className="text-xs font-medium">{def.label}</span>
            <div className="flex items-center gap-1">
              <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>
              {record?.stale && <Badge variant="outline">stale</Badge>}
              {readiness && readiness !== "ready" && <Badge variant="outline">{readiness}</Badge>}
            </div>
          </button>
        )
      })}
    </div>
  )
}
