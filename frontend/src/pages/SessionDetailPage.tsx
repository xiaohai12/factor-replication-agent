import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { StepStepper } from "@/components/StepStepper"
import { JobLogPanel } from "@/components/JobLogPanel"
import { StepOutputView } from "@/components/StepOutputView"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { JsonTree } from "@/components/JsonTree"
import { CodeView } from "@/components/CodeView"
import { sessionApi } from "@/lib/sessionApi"
import { stepDefinition } from "@/lib/steps"
import { useJobStream } from "@/lib/useJobStream"
import { ApiError } from "@/lib/api"
import { PROVIDER_MODELS, useLlm } from "@/lib/llmContext"
import {
  getMethodSpecWorkflowState,
  setMethodSpecWorkflowState,
  type MethodSpecWorkflowState,
  type ReviewRound,
} from "@/lib/methodSpecStore"
import type { SessionManifest } from "@/lib/types"

/** Auto-fills a step's request body from whatever this SAME session has
 * already recorded upstream, so the user never has to hand-copy a spec/
 * plugin/script hash between steps (the friction that caused a real 422 in
 * testing: step2's `spec` field was left as the empty template default).
 * Best-effort only -- any fetch failure just leaves the template default in
 * place, since every step can still be run standalone by pasting JSON. */
async function buildAutoFilledRequest(
  sessionId: string,
  step: number,
  manifest: SessionManifest,
  template: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = { ...template, expected_revision: manifest.revision }

  const latestSuccess = (n: number) => {
    const attempts = manifest.steps[String(n)]?.attempts ?? []
    return [...attempts].reverse().find((a) => a.status === "success")
  }

  async function fetchArtifactJson(atStep: number, filename: string): Promise<unknown> {
    const artifact = await sessionApi.getStepArtifact(sessionId, atStep, filename)
    return JSON.parse(artifact.content)
  }

  const step1 = latestSuccess(1)
  const step3 = latestSuccess(3)
  const step4 = latestSuccess(4)

  if ("spec" in body && step1?.output_refs.methodspec_ref) {
    try {
      body.spec = await fetchArtifactJson(1, step1.output_refs.methodspec_ref)
    } catch {
      // leave the template default; the user can still paste it manually.
    }
  } else if ("spec" in body && step3?.output_refs.spec_ref) {
    // Sessions that skip step1/2 (e.g. loaded an already-resolved MethodSpec
    // straight into step3 via MethodSpecPicker) have no step1 methodspec_ref
    // for step4/5's spec to be auto-filled from -- fall back to the spec
    // step3 itself persisted alongside its plugin/script artifacts.
    try {
      body.spec = await fetchArtifactJson(3, step3.output_refs.spec_ref)
    } catch {
      // same fallback as above.
    }
  } else if ("spec" in body) {
    // Sessions are not owned steps 1/2 anymore (see
    // docs/known-gaps-paper-first-v2.md) -- their output lives in
    // sessionStorage via MethodSpecWorkflowPanel instead of a session artifact.
    const resolved = getMethodSpecWorkflowState(sessionId).resolved
    if (resolved) body.spec = resolved
  }
  let pluginFilled = false
  if ("plugin" in body && step === 5 && step4?.output_refs.plugin_ref) {
    // Step4's technical RepairLoop (src/infra/repair.py) may have changed
    // the plugin's code to fix a validation/execution failure -- when it
    // did, step4 records its OWN plugin_ref (the repaired plugin, which is
    // what was actually validated) and that must win over step3's original
    // (possibly-buggy) plugin for step5's execute call.
    try {
      body.plugin = await fetchArtifactJson(4, step4.output_refs.plugin_ref)
      pluginFilled = true
    } catch {
      // fall through to step3's plugin below.
    }
  }
  if ("plugin" in body && !pluginFilled && step3?.output_refs.plugin_ref) {
    try {
      body.plugin = await fetchArtifactJson(3, step3.output_refs.plugin_ref)
    } catch {
      // same fallback as above.
    }
  }
  // step4 validates step3's freshly-built (not-yet-validated) script hash;
  // step5 execute requires step4's ALREADY-validated hash specifically --
  // both templates happen to share the same `script_sha256` key, so this
  // must branch on the step number, not just key presence.
  if (step === 4 && step3?.output_refs.script_sha256) {
    body.script_sha256 = step3.output_refs.script_sha256
  }
  if (step === 5 && step4?.output_refs.validated_script_sha256) {
    body.script_sha256 = step4.output_refs.validated_script_sha256
  }
  if (step === 7) {
    const step6 = latestSuccess(6)
    if (step6?.output_refs.experiment_batch_id) {
      body.experiment_batch_id = step6.output_refs.experiment_batch_id
    }
  }
  return body
}

/** Whether a step's own result body signals a real failure (as opposed to
 * "the HTTP call didn't throw") -- e.g. step4 validate can 200 with
 * `passed: false`, step2 resolve can 200 with `is_ready: false`. Drives
 * auto-advance: a clean result with none of these fields set false counts
 * as success. */
function isFailureResult(result: unknown): boolean {
  if (!result || typeof result !== "object") return false
  const r = result as Record<string, unknown>
  if ("passed" in r) return r.passed === false
  if ("is_ready" in r) return r.is_ready === false
  if ("success" in r) return r.success === false
  if (typeof r.status === "string") return r.status === "failed" || r.status === "blocked"
  return false
}

/** Session-scoped step detail page: stepper + a generic request/response
 * JSON panel for whichever step is selected (Phase 4's D1-D4 scope --
 * per-step deep visualization panels are explicit future work, see
 * /memories/session/plan.md Phase E). Every step is reachable directly from
 * the URL, and can be run standalone as long as its declared input refs are
 * already present on the session (surfaced via `missing_input_refs`). */
export function SessionDetailPage() {
  const params = useParams<{ sessionId: string; step: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const sessionId = params.sessionId!
  const step = Number(params.step ?? "1")
  const def = stepDefinition(step)

  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => sessionApi.get(sessionId),
  })
  const stepQuery = useQuery({
    queryKey: ["session-step", sessionId, step],
    queryFn: () => sessionApi.getStep(sessionId, step),
  })
  const eventsQuery = useQuery({
    queryKey: ["session-events", sessionId],
    queryFn: () => sessionApi.getEvents(sessionId),
    refetchInterval: 4000,
  })

  const [requestText, setRequestText] = useState("")
  const [requestError, setRequestError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [syncResult, setSyncResult] = useState<unknown>(null)
  const { provider: llmProvider, model: llmModel } = useLlm()

  // Steps 1/2's own progress (`MethodSpecWorkflowPanel`) lives in
  // sessionStorage, not the session manifest's step attempts -- lifted up
  // here so the stepper's step-1/2 color coding reacts to it the same way
  // steps 3-8 react to `sessionQuery.data.steps[n]`.
  const [specState, setSpecState] = useState<MethodSpecWorkflowState>(() => getMethodSpecWorkflowState(sessionId))
  useEffect(() => {
    setSpecState(getMethodSpecWorkflowState(sessionId))
  }, [sessionId])

  // Any step whose request template carries an `llm_provider` key (steps 1/2,
  // the only two that actually call an LLM) tracks the SAME sidebar-selected
  // provider/model everywhere else in the app -- there is deliberately only
  // ONE provider/model picker in this app, not a per-step one.
  const withLlmSelection = (body: Record<string, unknown>): Record<string, unknown> =>
    "llm_provider" in body ? { ...body, llm_provider: llmProvider, llm_model: llmModel } : body

  useEffect(() => {
    let cancelled = false
    setRequestText(JSON.stringify(withLlmSelection(def.requestTemplate), null, 2))
    setJobId(null)
    setSyncResult(null)
    setRequestError(null)
    ;(async () => {
      try {
        const manifest = await sessionApi.get(sessionId)
        const body = await buildAutoFilledRequest(sessionId, step, manifest, def.requestTemplate)
        if (!cancelled) setRequestText(JSON.stringify(withLlmSelection(body), null, 2))
      } catch {
        // Session not found yet, or an artifact fetch failed -- the plain
        // template (already set above) is still a usable starting point.
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, sessionId])

  // If the user changes the sidebar provider/model WHILE already looking at
  // a step's request editor, keep the JSON in sync rather than silently
  // going stale (only touches the two llm_provider/llm_model keys, never
  // clobbers spec/plugin/etc. the user may have hand-edited).
  useEffect(() => {
    setRequestText((prev) => {
      if (!prev) return prev
      try {
        const parsed = JSON.parse(prev)
        if (!("llm_provider" in parsed)) return prev
        return JSON.stringify({ ...parsed, llm_provider: llmProvider, llm_model: llmModel }, null, 2)
      } catch {
        return prev
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [llmProvider, llmModel])

  const job = useJobStream(jobId)

  const runMutation = useMutation({
    mutationFn: async () => {
      const body = JSON.parse(requestText)
      return sessionApi.runStep(def.endpoint(sessionId), body)
    },
    onSuccess: (response) => {
      setRequestError(null)
      if (typeof response.job_id === "string") {
        setJobId(response.job_id)
      } else {
        setSyncResult(response)
        queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
        queryClient.invalidateQueries({ queryKey: ["session-step", sessionId, step] })
        queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
        advanceIfSuccessful(response)
      }
    },
    onError: (err) => {
      setRequestError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
  })

  // Auto-advance to the next step once THIS step's own result looks like a
  // real success -- not just "the HTTP call didn't throw" (e.g. step4
  // validate can 200 with `passed: false`, step2 resolve can 200 with
  // `is_ready: false`). Anything with an explicit failure-shaped field wins;
  // otherwise a clean response/completed job counts as success.
  const advanceIfSuccessful = (result: unknown) => {
    if (step >= 8 || isFailureResult(result)) return
    navigate(`/sessions/${sessionId}/steps/${step + 1}`)
  }

  useEffect(() => {
    if (job.status === "completed" || job.status === "failed") {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["session-step", sessionId, step] })
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
      if (job.status === "completed") advanceIfSuccessful(job.result)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status])

  const missingRefs = stepQuery.data?.missing_input_refs ?? []
  const latestAttempt = useMemo(() => {
    const attempts = stepQuery.data?.record.attempts ?? []
    return attempts[attempts.length - 1]
  }, [stepQuery.data])

  const archiveMutation = useMutation({
    mutationFn: () => sessionApi.archive(sessionId, sessionQuery.data?.revision ?? 0),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["session", sessionId] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => sessionApi.hardDelete(sessionId, sessionQuery.data?.revision ?? 0),
    onSuccess: () => navigate("/sessions"),
  })

  if (sessionQuery.isLoading) return <div className="p-6">Loading session…</div>
  if (sessionQuery.isError || !sessionQuery.data) {
    return <div className="p-6 text-destructive">Session not found.</div>
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{sessionQuery.data.factor_id}</h2>
          <p className="text-xs text-muted-foreground">
            session {sessionId} · state <Badge variant="outline">{sessionQuery.data.state}</Badge>
          </p>
        </div>
        <div className="flex gap-2">
          {sessionQuery.data.state !== "archived" && (
            <Button variant="outline" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>
              Archive
            </Button>
          )}
          <Button
            variant="destructive"
            disabled={deleteMutation.isPending}
            onClick={() => {
              if (window.confirm("Permanently delete this session? This cannot be undone.")) {
                deleteMutation.mutate()
              }
            }}
          >
            Delete
          </Button>
          <Button variant="outline" onClick={() => navigate("/sessions")}>
            All sessions
          </Button>
        </div>
      </div>

      <StepStepper
        manifest={sessionQuery.data}
        activeStep={step}
        specState={specState}
        onSelect={(s) => navigate(`/sessions/${sessionId}/steps/${s}`)}
      />

      {(() => {
        const eventsCard = (
          <Card>
            <CardHeader>
              <CardTitle>Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-48 overflow-auto font-mono text-xs">
                {(eventsQuery.data ?? []).map((e) => (
                  <div key={e.seq} className={e.level === "error" ? "text-destructive" : undefined}>
                    [{e.step ?? "-"}] {e.stage}.{e.event} {e.detail}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )

        const resultCard = (
          <Card>
            <CardHeader>
              <CardTitle>Result</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {step > 2 && def.isJob ? <JobLogPanel job={job} /> : null}
              {latestAttempt?.diagnostics && "readiness" in latestAttempt.diagnostics && (
                <div className="flex flex-col gap-1 rounded-md border border-border p-2 text-xs">
                  <span>
                    readiness: <Badge variant="outline">{latestAttempt.diagnostics.readiness}</Badge>
                  </span>
                  <pre className="overflow-auto">{JSON.stringify(latestAttempt.diagnostics.counters, null, 2)}</pre>
                  {latestAttempt.diagnostics.flags.map((f, i) => (
                    <p key={i} className="text-muted-foreground">
                      ⚑ {f}
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )

        // Steps 1/2 get a single, full-width column (Events -> Extract/Review
        // -> Result) instead of the 2-col request/result grid used by steps
        // 3-8 -- `MethodSpecBoard` inside the panel is dense/tall, and a
        // half-width column left it cramped. Events also moves ABOVE the
        // panel here specifically because it's the first thing worth
        // checking on these two steps (extraction/review job progress).
        if (step === 1 || step === 2) {
          return (
            <>
              {eventsCard}
              <Card>
                <CardHeader>
                  <CardTitle>{def.label}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {missingRefs.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Missing upstream refs: {missingRefs.join(", ")} -- this step may fail until an
                      earlier step provides them.
                    </p>
                  )}
                  <MethodSpecWorkflowPanel
                    sessionId={sessionId}
                    step={step}
                    defaultTargetName={sessionQuery.data.factor_id}
                    onStateChange={setSpecState}
                  />
                  {requestError && <p className="text-xs text-destructive">{requestError}</p>}
                </CardContent>
              </Card>
              {resultCard}
            </>
          )
        }

        return (
          <>
            {eventsCard}
            <div className="grid grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>{def.label} — request</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {missingRefs.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Missing upstream refs: {missingRefs.join(", ")} -- this step may fail until an earlier
                      step provides them.
                    </p>
                  )}
                  {"llm_provider" in def.requestTemplate && (
                    <p className="text-xs text-muted-foreground">
                      Uses the LLM Provider / Model picked in the sidebar (bottom-left) -- change it there, not
                      just in this JSON, or it'll be overwritten on your next edit.
                    </p>
                  )}
                  {step === 3 && (
                    <MethodSpecPicker
                      onSpecPluginReady={(spec, plugin) => {
                        const current = JSON.parse(requestText)
                        setRequestText(JSON.stringify({ ...current, spec, plugin }, null, 2))
                      }}
                    />
                  )}
                  {"snapshot_id" in def.requestTemplate && (
                    <SnapshotPicker
                      onSelect={(snapshotId) => {
                        const current = JSON.parse(requestText)
                        setRequestText(JSON.stringify({ ...current, snapshot_id: snapshotId }, null, 2))
                      }}
                    />
                  )}
                  <Textarea
                    className="h-64 font-mono text-xs"
                    value={requestText}
                    onChange={(e) => setRequestText(e.target.value)}
                  />
                  <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
                    Run {def.label}
                  </Button>
                  {requestError && <p className="text-xs text-destructive">{requestError}</p>}
                </CardContent>
              </Card>

              {resultCard}
            </div>

            {step > 2 && (
              <Card>
                <CardHeader>
                  <CardTitle>Step output</CardTitle>
                </CardHeader>
                <CardContent>
                  <StepOutputView
                    step={step}
                    sessionId={sessionId}
                    factorId={sessionQuery.data.factor_id}
                    attempt={latestAttempt}
                    syncResult={def.isJob ? job.result : syncResult}
                  />
                </CardContent>
              </Card>
            )}
          </>
        )
      })()}
    </div>
  )
}

/** Steps 1+2's combined UI: the standalone paper-first MethodSpec lifecycle
 * (extract -> review -> resolve, backend/routers/methodspecs.py) is
 * NOT session-scoped anymore (see docs/known-gaps-paper-first-v2.md -- a
 * session only starts owning artifacts from step3 onward), so this renders
 * for BOTH step 1 and step 2 and keeps its own progress in sessionStorage
 * (via lib/methodSpecStore) instead of session attempts/artifacts. Once a
 * spec resolves, step3's `spec` field auto-fills from that same store (see
 * `buildAutoFilledRequest`'s "spec" fallback above).
 *
 * Auto-advances like every other step: extract success jumps 1 -> 2, and a
 * ready resolve jumps straight to step 3 -- `onStateChange` also mirrors
 * every state change up to `SessionDetailPage` so the stepper's step-1/2
 * badges recolor immediately, the same way steps 3-8 do from their own
 * session-recorded attempt status. */

/** Renders a mechanical field-level diff (`spec_build._diff_json`'s output
 * shape) as a table with the changed value highlighted red -- the
 * human-facing safety net for the 2026-08-11 "trust the LLM's rewrite
 * directly" design (see docs/decision-log.md): nothing is silently
 * discarded, so this is where a human actually sees everything that
 * changed. */
function DiffTable({ diff }: { diff: Array<{ field_path: string; old: unknown; new: unknown }> }) {
  if (diff.length === 0) {
    return <p className="text-xs text-muted-foreground">No changes.</p>
  }
  return (
    <div className="flex flex-col gap-1 text-xs">
      {diff.map((d, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-2 rounded border border-border/60 p-1.5">
          <span className="truncate font-mono text-muted-foreground" title={d.field_path}>
            {d.field_path}
          </span>
          <span className="truncate text-muted-foreground line-through" title={JSON.stringify(d.old)}>
            {d.old === null ? "(none)" : JSON.stringify(d.old)}
          </span>
          <span className="truncate font-medium text-red-600" title={JSON.stringify(d.new)}>
            {d.new === null ? "(removed)" : JSON.stringify(d.new)}
          </span>
        </div>
      ))}
    </div>
  )
}

function MethodSpecWorkflowPanel({
  sessionId,
  step,
  defaultTargetName,
  onStateChange,
}: {
  sessionId: string
  step: number
  defaultTargetName: string
  onStateChange: (state: MethodSpecWorkflowState) => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [state, setState] = useState<MethodSpecWorkflowState>(() => getMethodSpecWorkflowState(sessionId))
  const [file, setFile] = useState<File | null>(null)
  const [targetName, setTargetName] = useState(defaultTargetName)
  const [extractJobId, setExtractJobId] = useState<string | null>(null)
  const [reviewJobId, setReviewJobId] = useState<string | null>(null)
  const [valuePatchDrafts, setValuePatchDrafts] = useState<Record<string, string>>({})
  const [useOtherValueFor, setUseOtherValueFor] = useState<Record<string, boolean>>({})
  //: null = "total diff" (Step1 raw -> final spec); otherwise an index into
  //: `state.history` for that single round's before/after.
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const [showRawJson, setShowRawJson] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { provider, model, setProvider, setModel } = useLlm()
  const schemaQuery = useQuery({ queryKey: ["methodspec-schema"], queryFn: sessionApi.getSchemaReference })
  // Step1 (extraction) and Step2 (the LLM review loop,
  // `spec_build.build_reviewed_method_spec`) are two SEPARATE jobs now --
  // Step1 shows "succeeded" as soon as extraction itself returns, and the
  // review loop is kicked off right after (see the effect below), with its
  // own progress/log scoped to this same component instance (navigating
  // step1 -> step2 does not unmount it, see SessionDetailPage's render).
  const extractJob = useJobStream<{
    raw_spec?: Record<string, unknown>
    error?: string
    paper_text?: string
    token_usage?: unknown
  }>(extractJobId)
  const reviewJob = useJobStream<{
    spec?: Record<string, unknown>
    error?: string
    review?: Record<string, unknown>
    total_diff?: Array<{ field_path: string; old: unknown; new: unknown }>
    history?: ReviewRound[]
  }>(reviewJobId)

  useEffect(() => {
    onStateChange(state)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const patch = (p: MethodSpecWorkflowState) => {
    const next = setMethodSpecWorkflowState(sessionId, p)
    setState(next)
    onStateChange(next)
  }

  const reviewLoopMutation = useMutation({
    mutationFn: (vars: { rawSpec: Record<string, unknown>; documentId: string; targetName: string; paperText: string }) =>
      sessionApi.runReviewLoop(vars.rawSpec, vars.documentId, vars.targetName, vars.paperText, provider, model, sessionId),
    onSuccess: (res) => setReviewJobId(res.job_id),
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  useEffect(() => {
    if (extractJob.status === "completed") {
      if (extractJob.result?.raw_spec) {
        const rawSpec = extractJob.result.raw_spec
        const paperText = extractJob.result.paper_text
        // Re-extracting invalidates whatever Step2 result was there before.
        patch({
          rawSpec,
          paperText,
          paper: undefined,
          review: undefined,
          reviewSource: undefined,
          totalDiff: undefined,
          history: undefined,
          resolved: undefined,
        })
        setError(null)
        if (step === 1) navigate(`/sessions/${sessionId}/steps/2`)
        if (state.documentId && state.targetName && paperText) {
          reviewLoopMutation.mutate({ rawSpec, documentId: state.documentId, targetName: state.targetName, paperText })
        }
      } else {
        setError(extractJob.result?.error ?? "Extraction returned no output")
      }
    } else if (extractJob.status === "failed") {
      setError(extractJob.error)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extractJob.status])

  useEffect(() => {
    if (reviewJob.status === "completed") {
      if (reviewJob.result?.spec) {
        patch({
          paper: reviewJob.result.spec,
          review: reviewJob.result.review,
          reviewSource: reviewJob.result.review ? "llm" : undefined,
          totalDiff: reviewJob.result.total_diff,
          history: reviewJob.result.history,
          resolved: undefined,
        })
        setError(null)
      } else {
        setError(reviewJob.result?.error ?? "Step2 review loop did not converge on a valid MethodSpec")
      }
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
    } else if (reviewJob.status === "failed") {
      setError(reviewJob.error)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewJob.status])

  const extractMutation = useMutation({
    mutationFn: () => {
      patch({ documentId: file!.name, targetName })
      return sessionApi.extractPaperPdf(file!.name, targetName, file!, provider, model, sessionId)
    },
    onSuccess: (res) => {
      setError(null)
      setExtractJobId(res.job_id)
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  // Rules-only re-review (`review_method_spec`'s D2/missing-mapping findings,
  // no LLM call) -- used after a human value patch, since a patch clears the
  // stored review and there's no separate LLM-review endpoint to fall back
  // to (that ran once already, via `runReviewLoop` above).
  const reviewMutation = useMutation({
    mutationFn: () => sessionApi.reviewPaperSpec(state.paper!, sessionId),
    onSuccess: (review) => {
      patch({ review, reviewSource: "rules", resolved: undefined })
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  // Corrects the extracted VALUE itself. Produces a NEW paper, so the
  // stored review/resolved state is cleared -- there's no automatic
  // staleness detection forcing a re-review anymore (docs/decision-log.md
  // 2026-08-09), so we clear it here as the deliberate "you must redo this"
  // signal instead.
  const patchValueMutation = useMutation({
    mutationFn: () => sessionApi.patchPaperValue(state.paper!, valuePatchDrafts, "", sessionId),
    onSuccess: (paperSpec) => {
      patch({ paper: paperSpec, review: undefined, reviewSource: undefined, resolved: undefined })
      setValuePatchDrafts({})
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  const resolveMutation = useMutation({
    mutationFn: async () => {
      // Deterministic concept-mapping is tried first either way (see
      // `build_implementation_resolution`) -- passing provider/model only
      // adds an LLM fallback attempt for concepts that are STILL unresolved
      // after that, so this never changes behavior for a spec that already
      // resolves cleanly.
      const { is_ready, unmapped_concepts, llm_matched_concepts } = await sessionApi.resolvePaperSpec(
        state.paper!,
        state.review!,
        "us_equity_crsp",
        sessionId,
        provider,
        model,
      )
      if (!is_ready) return { is_ready, unmapped_concepts, llm_matched_concepts, resolved: null }
      const resolved = await sessionApi.getResolvedMethodSpec((state.paper as { factor_id: string }).factor_id)
      return { is_ready, unmapped_concepts, llm_matched_concepts, resolved }
    },
    onSuccess: ({ is_ready, resolved }) => {
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
      if (resolved) {
        patch({ resolved })
        navigate(`/sessions/${sessionId}/steps/3`)
      } else if (!is_ready) {
        setError("Resolved spec is not codegen-ready yet -- see the blocking fields below.")
      }
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  const findings = (state.review?.findings as Array<Record<string, unknown>> | undefined) ?? []
  const isBlocked = findings.some((f) => f.disposition === "blocked")
  // Schema reference is keyed by the STATIC dotted path (no `[i]` sort
  // index) -- strip it before lookup; falls back to no info for the one
  // field this can't match (`portfolio.sorts[i].breakpoints.basis`, nested
  // two levels inside a list item the schema walker doesn't recurse into).
  const schemaFieldInfo = (fieldPath: string) => schemaQuery.data?.fields[fieldPath.replace(/\[\d+\]/g, "")]

  // Step 1 is extract-only; step 2 is review+resolve over whatever step 1
  // already produced -- two distinct pages now, not the same combined panel
  // rendered twice under different labels.
  if (step === 1) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-sm font-medium">Extract MethodSpec from paper</p>
          <label
            htmlFor="session-pdf-upload-input"
            className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-border p-4 text-center transition-colors hover:border-primary hover:bg-muted/50"
          >
            <span className="text-sm font-medium">
              {file ? file.name : "Click to choose a PDF, or drag one here"}
            </span>
            <span className="text-xs text-muted-foreground">
              {file ? `${(file.size / 1024).toFixed(0)} KB -- click to change` : "PDF files only"}
            </span>
          </label>
          <input
            id="session-pdf-upload-input"
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="hidden"
          />
          <input
            className="rounded-md border border-border bg-transparent px-2 py-1 text-xs"
            value={targetName}
            onChange={(e) => setTargetName(e.target.value)}
            placeholder="target_name (factor label for the extractor)"
          />
          <div className="flex gap-2">
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.keys(PROVIDER_MODELS).map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(PROVIDER_MODELS[provider] ?? []).map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button disabled={!file || extractMutation.isPending} onClick={() => extractMutation.mutate()}>
            Extract MethodSpec from PDF
          </Button>
          {extractJobId && <JobLogPanel job={extractJob} />}
        </div>

        {state.rawSpec && (
          <div className="flex flex-col gap-2 rounded-md border border-border p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Step1 succeeded -- raw, unreviewed LLM extraction</p>
              <Button size="sm" variant="outline" onClick={() => navigate(`/sessions/${sessionId}/steps/2`)}>
                Go to Step 2 — Review
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Not validated yet, and menu-vocabulary fields (weighting/breakpoints/etc.) are still written as
              the paper's own wording, not engine tokens -- shown below as-is. The Step2 review loop{" "}
              {reviewJob.status === "running" ? "is now running in the background" : reviewJob.status === "completed" ? "has already finished" : "starts automatically"}
              ; see its result (corrected spec, findings, and a before/after diff) on the Step2 page.
              Re-extracting above will replace this.
            </p>
            <MethodSpecBoard spec={state.rawSpec} />
            <button
              type="button"
              className="self-start text-xs text-muted-foreground underline"
              onClick={() => setShowRawJson((v) => !v)}
            >
              {showRawJson ? "hide raw JSON" : "show raw JSON"}
            </button>
            {showRawJson && <JsonTree name="step1_output" data={state.rawSpec} />}
          </div>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    )
  }

  // step === 2
  if (!state.rawSpec) {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm">
        <p>No MethodSpec extracted yet.</p>
        <Button size="sm" onClick={() => navigate(`/sessions/${sessionId}/steps/1`)}>
          Go to Step 1 — Extract
        </Button>
      </div>
    )
  }

  if (!state.paper) {
    const canRetry = Boolean(state.documentId && state.targetName && state.paperText)
    return (
      <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm">
        <p>
          {reviewJob.status === "running"
            ? "Step2 review loop is running…"
            : reviewJob.status === "failed"
              ? "Step2 review loop failed to start."
              : error
                ? `Step2 review loop did not converge: ${error}`
                : "Step2 review loop hasn't started yet."}
        </p>
        {reviewJobId && <JobLogPanel job={reviewJob} title="Step2 review loop" />}
        {!reviewJobId && canRetry && (
          <Button
            size="sm"
            disabled={reviewLoopMutation.isPending}
            onClick={() =>
              reviewLoopMutation.mutate({
                rawSpec: state.rawSpec!,
                documentId: state.documentId!,
                targetName: state.targetName!,
                paperText: state.paperText!,
              })
            }
          >
            {reviewLoopMutation.isPending ? "Starting…" : "Run Step2 review loop"}
          </Button>
        )}
        {!canRetry && !reviewJobId && (
          <p className="text-xs text-muted-foreground">
            Missing document id/target name/paper text for this session (e.g. after a page reload lost
            in-progress state) -- re-extract from Step 1 instead.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-sm font-medium">
          Review — <span className="font-mono text-xs">{String(state.paper.factor_id)}</span>
        </p>
        {reviewJobId && <JobLogPanel job={reviewJob} title="Step2 review loop" />}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate()}>
            {reviewMutation.isPending ? "Reviewing…" : "Re-run rules-only review"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          The LLM-backed review (full-spec check + menu-vocabulary classification) already ran once as part of
          extraction (`spec_build.build_reviewed_method_spec`). This button only re-runs the deterministic
          rules pass (`MethodReview`'s D2/missing-mapping findings, no LLM call) -- use it after applying a
          value correction below, since a patch clears the stored review.
        </p>
        {state.review && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Badge variant={isBlocked ? "destructive" : "default"}>
                {findings.length === 0 ? "no findings -- every field looks fine" : `${findings.length} field(s) flagged`}
              </Badge>
              <Badge variant="outline">
                {state.reviewSource === "llm"
                  ? "LLM-backed review"
                  : state.reviewSource === "human"
                    ? "human override applied"
                    : "Rules-based review"}
              </Badge>
            </div>
            {findings.map((f, i) => {
              const fieldPath = String(f.field_path)
              const canPatch = f.kind !== "missing_mapping" && f.disposition === "needs_human_confirmation"
              const info = schemaFieldInfo(fieldPath)
              const allowedValues = info?.allowed_values ?? null
              const usingOther = useOtherValueFor[fieldPath] ?? false
              const evidence = (f.evidence as Array<Record<string, unknown>> | undefined) ?? []
              return (
                <div key={i} className="flex flex-col gap-1 rounded-md border border-border/60 p-2 text-xs">
                  <div className="flex items-start gap-2">
                    <Badge variant={f.disposition === "blocked" ? "destructive" : "outline"} className="shrink-0">
                      {String(f.disposition)}
                    </Badge>
                    <div>
                      <span className="font-mono font-medium">{fieldPath}</span>{" "}
                      <span className="text-muted-foreground">({String(f.kind)})</span>
                      <p className="text-muted-foreground">{String(f.reason)}</p>
                    </div>
                  </div>
                  {/* §5.1 four-item human-review contract: 字段解释 */}
                  {canPatch && info?.description && (
                    <p className="pl-1 text-muted-foreground">ℹ {info.description}</p>
                  )}
                  {/* §5.1: source -- the field's own evidence citations */}
                  {canPatch && evidence.length > 0 && (
                    <div className="flex flex-col gap-0.5 pl-1">
                      <span className="text-muted-foreground">Source:</span>
                      {evidence.map((c, j) => (
                        <p key={j} className="pl-2 text-muted-foreground">
                          {c.quote ? `“${String(c.quote)}”` : null}
                          {c.table_ref ? ` [${JSON.stringify(c.table_ref)}]` : null}
                          {c.interpretation ? ` -- ${String(c.interpretation)}` : null}
                        </p>
                      ))}
                    </div>
                  )}
                  {canPatch && (
                    <div className="flex items-center gap-2 pl-1">
                      <span className="text-muted-foreground">Confirm or correct the value:</span>
                      {allowedValues && allowedValues.length > 0 && !usingOther ? (
                        <Select
                          value={valuePatchDrafts[fieldPath] ?? ""}
                          onValueChange={(v) => {
                            if (v === "__other__") {
                              setUseOtherValueFor((prev) => ({ ...prev, [fieldPath]: true }))
                              setValuePatchDrafts((prev) => ({ ...prev, [fieldPath]: "" }))
                            } else {
                              setValuePatchDrafts((prev) => ({ ...prev, [fieldPath]: v }))
                            }
                          }}
                        >
                          <SelectTrigger className="h-7 w-56 text-xs">
                            <SelectValue placeholder={`current: ${JSON.stringify(f.paper_value)}`} />
                          </SelectTrigger>
                          <SelectContent>
                            {allowedValues.map((v) => (
                              <SelectItem key={v} value={v}>
                                {v}
                              </SelectItem>
                            ))}
                            <SelectItem value="__other__">Other (type my own)</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <div className="flex items-center gap-1">
                          <Input
                            className="h-7 w-56 text-xs"
                            placeholder={`current: ${JSON.stringify(f.paper_value)}`}
                            value={valuePatchDrafts[fieldPath] ?? ""}
                            onChange={(e) => setValuePatchDrafts((prev) => ({ ...prev, [fieldPath]: e.target.value }))}
                          />
                          {allowedValues && allowedValues.length > 0 && (
                            <button
                              type="button"
                              className="text-muted-foreground underline"
                              onClick={() => setUseOtherValueFor((prev) => ({ ...prev, [fieldPath]: false }))}
                            >
                              choose from list
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {Object.keys(valuePatchDrafts).length > 0 && (
              <Button size="sm" variant="outline" disabled={patchValueMutation.isPending} onClick={() => patchValueMutation.mutate()}>
                {patchValueMutation.isPending
                  ? "Patching…"
                  : `Apply ${Object.keys(valuePatchDrafts).length} value correction(s) -- re-run review after`}
              </Button>
            )}
            <p className="text-xs text-muted-foreground">
              Only "needs_human_confirmation" findings can be corrected this way -- "missing_mapping" findings
              can't (fix `data.fields`/`universe.filters` and re-extract instead). A value correction replaces
              the extracted content itself (marks it "clear" and records your reason as evidence) and clears
              the current review -- re-run review afterward.
            </p>
          </div>
        )}
      </div>

      {((state.totalDiff?.length ?? 0) > 0 || (state.history?.length ?? 0) > 0) && (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-sm font-medium">
            Change log -- what the LLM review loop actually changed
          </p>
          <p className="text-xs text-muted-foreground">
            The review loop trusts the LLM's rewritten spec directly (no field is silently discarded) -- this
            is the mechanical before/after diff so you can verify exactly what it touched.
          </p>
          {(state.history?.length ?? 0) > 1 && (
            <div className="flex flex-wrap items-center gap-1 text-xs">
              <span className="text-muted-foreground">View:</span>
              <button
                type="button"
                className={`rounded px-2 py-0.5 ${selectedRound === null ? "bg-primary text-primary-foreground" : "border border-border"}`}
                onClick={() => setSelectedRound(null)}
              >
                total ({state.totalDiff?.length ?? 0})
              </button>
              {state.history!.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  className={`rounded px-2 py-0.5 ${selectedRound === i ? "bg-primary text-primary-foreground" : "border border-border"}`}
                  onClick={() => setSelectedRound(i)}
                >
                  round {r.round_num} ({r.diff.length})
                </button>
              ))}
            </div>
          )}
          <DiffTable diff={selectedRound === null ? (state.totalDiff ?? []) : state.history![selectedRound]!.diff} />
        </div>
      )}

      {state.review && (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-sm font-medium">Resolve</p>
          <Button size="sm" disabled={resolveMutation.isPending} onClick={() => resolveMutation.mutate()}>
            {resolveMutation.isPending ? "Resolving…" : "Resolve to a codegen-ready MethodSpec"}
          </Button>
          {resolveMutation.data && (
            <Badge variant={resolveMutation.data.is_ready ? "default" : "destructive"}>
              is_ready: {String(resolveMutation.data.is_ready)}
            </Badge>
          )}
          {(resolveMutation.data?.llm_matched_concepts?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
              <p className="font-medium">
                LLM-matched concept(s) -- re-check these, the deterministic catalog matcher couldn't resolve them on its own:
              </p>
              {resolveMutation.data!.llm_matched_concepts.map((c) => (
                <span key={c} className="font-mono">
                  {c}
                </span>
              ))}
            </div>
          )}
          {resolveMutation.data && !resolveMutation.data.is_ready && (
            <div className="flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs">
              <p className="font-medium">This needs human resolution before codegen can run:</p>
              {findings
                .filter((f) => f.disposition === "blocked")
                .map((f, i) => (
                  <div key={`blocked-${i}`} className="flex items-start gap-2">
                    <Badge variant="destructive" className="shrink-0">
                      review
                    </Badge>
                    <div>
                      <span className="font-mono font-medium">{String(f.field_path)}</span>{" "}
                      <span className="text-muted-foreground">({String(f.kind)})</span>
                      <p className="text-muted-foreground">{String(f.reason)}</p>
                    </div>
                  </div>
                ))}
              {(resolveMutation.data.unmapped_concepts ?? []).map((c, i) => (
                <div key={`unmapped-${i}`} className="flex items-start gap-2">
                  <Badge variant="destructive" className="shrink-0">
                    unmapped
                  </Badge>
                  <div>
                    <span className="font-mono font-medium">{c}</span>
                    <p className="text-muted-foreground">
                      concept has no physical column mapping in the data catalog -- it can't be resolved
                      automatically. Fix the paper's `data.fields`/`universe.filters` for this concept (e.g.
                      register a real source column) and re-extract/re-review, or remove the filter/field if
                      it's not truly needed.
                    </p>
                  </div>
                </div>
              ))}
              <p className="text-muted-foreground">
                Note: D4 (engine-capability blocking) was removed 2026-08-10 -- an out-of-menu choice
                (weighting/construction_type/breakpoints.basis/missing_policies) is now recorded as
                `SourcedValue.unsupported_value` and clamped to an engine default, not blocked here. What
                remains blocking at this point is a `missing_mapping` finding you haven't resolved yet, or an
                unmapped concept above -- fix the paper's `data.fields`/`universe.filters` and re-extract, or
                pick a value correction in the review panel above.
              </p>
            </div>
          )}
          {state.resolved && (
            <>
              <JsonTree name="resolved" data={state.resolved} />
              <Button size="sm" onClick={() => navigate(`/sessions/${sessionId}/steps/3`)}>
                Use this spec — go to Step 3
              </Button>
            </>
          )}
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

/** Step3 helper: pick an already-REVIEWED MethodSpec (the existing
 * `/api/methodspecs/resolved` list -- unrelated to session state) and
 * generate a plugin for it on the spot via the existing `/api/codegen`
 * job, instead of hand-pasting both JSON blobs. */
function MethodSpecPicker({
  onSpecPluginReady,
}: {
  onSpecPluginReady: (spec: Record<string, unknown>, plugin: Record<string, unknown>) => void
}) {
  const [factorId, setFactorId] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [pendingSpec, setPendingSpec] = useState<Record<string, unknown> | null>(null)
  const listQuery = useQuery({ queryKey: ["resolved-methodspecs"], queryFn: sessionApi.listResolvedMethodSpecs })
  const job = useJobStream<Record<string, unknown>>(jobId)

  const generateMutation = useMutation({
    mutationFn: async () => {
      const spec = await sessionApi.getResolvedMethodSpec(factorId!)
      const { job_id } = await sessionApi.generatePlugin(spec, "codex")
      return { spec, job_id }
    },
    onSuccess: ({ spec, job_id }) => {
      setPendingSpec(spec)
      setJobId(job_id)
    },
  })

  useEffect(() => {
    if (job.status === "completed" && job.result && pendingSpec) {
      onSpecPluginReady(pendingSpec, job.result)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status])

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <p className="text-xs font-medium">Load a resolved MethodSpec + generate a plugin</p>
      <div className="flex gap-2">
        <Select value={factorId ?? undefined} onValueChange={setFactorId}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Select a resolved MethodSpec" />
          </SelectTrigger>
          <SelectContent>
            {(listQuery.data ?? []).map((id) => (
              <SelectItem key={id} value={id}>
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" disabled={!factorId || generateMutation.isPending} onClick={() => generateMutation.mutate()}>
          Load + generate plugin
        </Button>
      </div>
      {job.status !== "idle" && <JobLogPanel job={job} title="codegen" />}
      {job.status === "completed" && job.result && (
        <div>
          <p className="mb-1 text-xs font-medium">Generated compute_signal plugin</p>
          <CodeView code={String((job.result as { code?: string }).code ?? "")} language="python" />
        </div>
      )}
    </div>
  )
}

/** Step3/5/6 helper: `snapshot_id` is a data-vintage identifier (which
 * registered CRSP/Compustat snapshot to run against), not something to
 * type by hand -- reuses the existing `/api/backtest/snapshots` listing
 * (same endpoint `BacktestExperimentsPage` already uses). */
function SnapshotPicker({ onSelect }: { onSelect: (snapshotId: string) => void }) {
  const snapshotsQuery = useQuery({ queryKey: ["snapshots"], queryFn: sessionApi.listSnapshots })
  return (
    <Select onValueChange={onSelect}>
      <SelectTrigger className="w-64">
        <SelectValue placeholder="Select a data snapshot" />
      </SelectTrigger>
      <SelectContent>
        {(snapshotsQuery.data ?? []).map((s) => (
          <SelectItem key={s.snapshot_id} value={s.snapshot_id}>
            {s.snapshot_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
