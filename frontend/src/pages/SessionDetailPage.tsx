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
import { ToolResultsPanel } from "@/components/ToolResultsPanel"
import { StepOutputView } from "@/components/StepOutputView"
import { Step3ComputeSignalCard } from "@/components/steps/Step3Output"
import { Step4Output, Step4RepairCard } from "@/components/steps/Step4Output"
import { Step5HeadlineCard } from "@/components/steps/Step5Output"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { JsonTree } from "@/components/JsonTree"
import { CodeView } from "@/components/CodeView"
import { sessionApi, type Step6PreviewTrack } from "@/lib/sessionApi"
import { stepDefinition } from "@/lib/steps"
import { useJobStream } from "@/lib/useJobStream"
import { ApiError, api } from "@/lib/api"
import { PROVIDER_MODELS, useLlm } from "@/lib/llmContext"
import { cn } from "@/lib/utils"
import {
  getMethodSpecWorkflowState,
  persistMethodSpecWorkflowState,
  type MethodSpecWorkflowState,
  type ReviewRound,
} from "@/lib/methodSpecStore"
import { getStep6PreviewState, setStep6PreviewState } from "@/lib/step6PreviewStore"
import type { SessionManifest, ToolResult } from "@/lib/types"

/** Step6's Cross-track comparison table wants the paper's OWN reported
 * headline number next to ①'s (and, separately, C&Z's reported number next
 * to ②'s) -- pulls it straight out of the request's `spec` JSON
 * (`MethodSpec.paper.reported_results`'s primary metric), no extra API
 * call needed. Returns null on any missing/malformed shape rather than
 * guessing. */
function extractPaperReported(
  spec: Record<string, unknown> | undefined,
): { mean_return?: number; t_stat?: number } | null {
  const paper = spec?.paper as Record<string, unknown> | undefined
  const reported = paper?.reported_results as Record<string, unknown> | undefined
  const metrics = reported?.metrics as Record<string, unknown>[] | undefined
  if (!reported || !metrics) return null
  const derivation = reported.comparison_derivation as {
    operation?: string; high_metric_id?: string; low_metric_id?: string; use_as_primary_comparison?: boolean
  } | undefined
  if (derivation?.use_as_primary_comparison && derivation.operation === "high_minus_low") {
    const high = metrics.find((m) => m.metric_id === derivation.high_metric_id)
    const low = metrics.find((m) => m.metric_id === derivation.low_metric_id)
    if (typeof high?.estimate === "number" && typeof low?.estimate === "number") {
      return { mean_return: high.estimate - low.estimate }
    }
  }
  const primary = metrics.find((m) => m.metric_id === reported.primary_metric_id)
  if (!primary) return null
  const statistic = primary.statistic as { kind?: string; value?: number } | undefined
  return {
    mean_return: typeof primary.estimate === "number" ? primary.estimate : undefined,
    t_stat: statistic?.kind === "t_stat" ? statistic.value : undefined,
  }
}

/** The replicated (target) paper's OWN sample window
 * (`MethodSpec.sample.reported_returns.start_year/end_year`) -- the SAME
 * window `extractPaperReported`'s number is scoped to, and what an HXZ
 * reference number needs restricting to for an apples-to-apples
 * comparison (HXZ's own 1967-2016 paper window would be a DIFFERENT,
 * wrong basis here). `spec.paper` here is the resolved MethodSpec itself
 * (same nesting `extractPaperReported` reads `.reported_results` from),
 * NOT `PaperRef` -- `sample` is a sibling field on it, not under `paper`
 * again. */
function extractPaperSampleWindow(
  spec: Record<string, unknown> | undefined,
): { startYear: number; endYear: number } | null {
  const methodSpec = spec?.paper as Record<string, unknown> | undefined
  const sample = methodSpec?.sample as Record<string, unknown> | undefined
  const reportedReturns = sample?.reported_returns as Record<string, unknown> | undefined
  const startYear = reportedReturns?.start_year
  const endYear = reportedReturns?.end_year
  return typeof startYear === "number" && typeof endYear === "number" ? { startYear, endYear } : null
}

interface RangeUnionSuggestion {
  conceptId: string
  indexes: number[]
  ranges: Array<[number, number]>
}

function disjointUniverseRangeSuggestions(paper: Record<string, unknown> | undefined): RangeUnionSuggestion[] {
  const filters = (paper?.universe as { filters?: Array<Record<string, unknown>> } | undefined)?.filters ?? []
  const byConcept = new Map<string, Array<{ index: number; range: [number, number] }>>()
  const legacyRangeUnionSuggestions: RangeUnionSuggestion[] = []
  filters.forEach((filter, index) => {
    const value = filter.value
    const isRangeUnion = (
      Array.isArray(value)
      && value.length > 0
      && value.every((interval) => (
        Array.isArray(interval)
        && interval.length === 2
        && interval.every((bound) => typeof bound === "number")
        && interval[0] <= interval[1]
      ))
    )
    if (filter.op === "in" && typeof filter.concept_id === "string" && isRangeUnion) {
      legacyRangeUnionSuggestions.push({
        conceptId: filter.concept_id,
        indexes: [index],
        ranges: value as Array<[number, number]>,
      })
      return
    }
    if (
      filter.op === "between"
      && typeof filter.concept_id === "string"
      && Array.isArray(value)
      && value.length === 2
      && value.every((bound) => typeof bound === "number")
      && value[0] <= value[1]
    ) {
      const entries = byConcept.get(filter.concept_id) ?? []
      entries.push({ index, range: [value[0], value[1]] })
      byConcept.set(filter.concept_id, entries)
    }
  })
  return [...byConcept.entries()].flatMap(([conceptId, entries]) => {
    const ordered = [...entries].sort((a, b) => a.range[0] - b.range[0])
    const disjoint = ordered.length > 1 && ordered.some((entry, i) => i > 0 && entry.range[0] > ordered[i - 1].range[1])
    return disjoint ? [{ conceptId, indexes: entries.map((entry) => entry.index), ranges: entries.map((entry) => entry.range) }] : []
  }).concat(legacyRangeUnionSuggestions)
}


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
  // Step6's ② toggle -- default checked, but only gates whether the C&Z
  // config section below is usable; ② itself only actually runs once a
  // config has ALSO been queried and confirmed there (see
  // Step6CzConfigPreview). Unchecking always clears any confirmed override.
  const [step6CzEnabled, setStep6CzEnabled] = useState(true)
  // Step6's pre-run confirmation: "Run" first previews the track count/names
  // (`preview_tracks`, no execution) instead of submitting the job directly;
  // the actual run only fires once the human clicks the second "Confirm &
  // Run" button that appears with the preview. Any edit to the request body
  // invalidates a stale preview (see the effect near `runMutation`).
  const [step6Preview, setStep6Preview] = useState<
    { track_count: number; tracks: Step6PreviewTrack[]; fromUpstream: boolean } | null
  >(null)
  // Lifted out of Step6CzConfigPreview so the ①②③ config diff AND the raw
  // C&Z query output can be shown ONLY in the Result panel (not duplicated
  // under "Run against C&Z's actual configuration") -- every value here is
  // already known client-side, no need to wait for the batch to actually
  // finish executing. Initialized from `step6PreviewStore` (localStorage)
  // and re-persisted on every change so a page reload doesn't force a
  // re-query of a live network call just to see the same numbers again.
  const [step6ConfigDiff, setStep6ConfigDiffState] = useState<{
    original: Record<string, unknown>
    cz: Record<string, unknown>
    std: Record<string, unknown>
    raw: Record<string, unknown>
    czReported: { mean_return: number | null; t_stat: number | null }
  } | null>(() => getStep6PreviewState(sessionId).configDiff ?? null)
  const setStep6ConfigDiff = (data: typeof step6ConfigDiff) => {
    setStep6ConfigDiffState(data)
    setStep6PreviewState(sessionId, { configDiff: data ?? undefined })
  }
  // HXZ's own reported number for the standardized_hxz track's "Reported
  // (reference)" column (docs/step6.md's N_hxz gap) -- separate from
  // step6ConfigDiff since it has no config-diff of its own, just a
  // mean_return/t_stat pulled from a downloaded HXZ testing-portfolio CSV.
  // Carries BOTH windows: the replicated factor's own paper sample
  // (`originalInsample`) and HXZ's own "Replicating Anomalies" paper
  // sample (`hxzPaperSample`, always 1967-2016) -- two different, both
  // useful, reference points. Also persisted, same reasoning as above.
  const [step6HxzReported, setStep6HxzReportedState] = useState<{
    originalInsample: HxzReportedPreview | null
    hxzPaperSample: HxzReportedPreview | null
  } | null>(() => {
    const cached = getStep6PreviewState(sessionId).hxzPreview
    if (!cached) return null
    return {
      originalInsample: cached.originalInsample as HxzReportedPreview | null,
      hxzPaperSample: cached.hxzPaperSample as HxzReportedPreview | null,
    }
  })
  const setStep6HxzReported = (data: typeof step6HxzReported) => {
    setStep6HxzReportedState(data)
    setStep6PreviewState(sessionId, {
      hxzPreview: data
        ? {
            acronym: getStep6PreviewState(sessionId).hxzSelected ?? "",
            originalInsample: data.originalInsample as Record<string, unknown> | null,
            hxzPaperSample: data.hxzPaperSample as Record<string, unknown> | null,
          }
        : undefined,
    })
  }

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

  // Resume watching a still-running step (navigated away mid-job, then back,
  // or a plain page reload) instead of only showing "not started" until the
  // user manually re-runs it. The backend attaches `job_id` to the attempt
  // in the SAME write as `start_attempt` (see `SessionStore.start_attempt`),
  // so `stepQuery`'s latest attempt already carries everything needed to
  // re-subscribe via `useJobStream` -- no separate persistence layer needed
  // here (unlike steps 1/2's sessionStorage-only `MethodSpecWorkflowPanel`,
  // this step's "running" truth already lives in the session manifest).
  // Only fires when nothing is already being tracked (`jobId` still null)
  // and the LATEST attempt is the one still running -- `runMutation`'s
  // `onMutate` already reset `jobId` to null before starting a fresh run, so
  // this won't clobber that.
  useEffect(() => {
    if (jobId) return
    const attempts = stepQuery.data?.record.attempts ?? []
    const attempt = attempts[attempts.length - 1]
    if (attempt?.status === "running" && attempt.job_id) {
      setJobId(attempt.job_id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepQuery.data, jobId])

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
    // `fromUpstream`: rebuild the request body fresh from whatever the
    // upstream step's LATEST successful output is right now (same
    // `buildAutoFilledRequest` the page uses on first load) instead of
    // whatever's currently sitting in the request-body textarea -- lets a
    // human re-run this step against a newer upstream result without
    // hand-editing refs/hashes back in.
    mutationFn: async (opts?: { fromUpstream?: boolean }) => {
      let body: Record<string, unknown>
      if (opts?.fromUpstream) {
        const manifest = await sessionApi.get(sessionId)
        body = withLlmSelection(await buildAutoFilledRequest(sessionId, step, manifest, def.requestTemplate))
        setRequestText(JSON.stringify(body, null, 2))
      } else {
        body = JSON.parse(requestText)
        // `requestText`'s `expected_revision` was only ever baked in once,
        // when this step/session first loaded (see the effect below) -- if
        // the session has been written since (another step ran, or this
        // SAME step was already re-run once), that value is stale and the
        // CAS in `SessionStore.update` rejects it with a 409. Re-read the
        // manifest fresh right before submitting so a plain "Run" always
        // targets the session's current revision, not whatever was current
        // when the textarea was last populated.
        if ("expected_revision" in body) {
          const manifest = await sessionApi.get(sessionId)
          body.expected_revision = manifest.revision
        }
      }
      return sessionApi.runStep(def.endpoint(sessionId), body)
    },
    // Clear THIS step's currently-displayed output right away -- otherwise
    // the previous job's logs/result/diagnostics stay on screen (job.result
    // only resets once `setJobId` below actually swaps in a new id) while
    // the new run is still in flight.
    onMutate: () => {
      setJobId(null)
      setSyncResult(null)
      setRequestError(null)
      // `setQueryData(key, undefined)` is a no-op in TanStack Query --
      // `removeQueries` is what actually drops the cached (stale) attempt.
      queryClient.removeQueries({ queryKey: ["session-step", sessionId, step], exact: true })
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
      }
    },
    onError: (err) => {
      setRequestError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
  })

  // Step6 only: computes the track count/names the plan currently in
  // `requestText` would run, WITHOUT executing anything -- gates the actual
  // `runMutation` behind a "Confirm & Run" step showing that count.
  const step6PreviewMutation = useMutation({
    mutationFn: async (opts?: { fromUpstream?: boolean }) => {
      const body = opts?.fromUpstream
        ? withLlmSelection(
            await buildAutoFilledRequest(sessionId, step, await sessionApi.get(sessionId), def.requestTemplate),
          )
        : JSON.parse(requestText)
      const response = await sessionApi.previewStep6Experiment(sessionId, body)
      return { ...response, fromUpstream: Boolean(opts?.fromUpstream) }
    },
    onSuccess: (response) => {
      setRequestError(null)
      setStep6Preview(response)
    },
    onError: (err) => {
      setStep6Preview(null)
      setRequestError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
  })

  // Any edit to the request body (switch toggles, C&Z-config confirmation,
  // hand-editing the textarea, etc.) invalidates a previously-fetched step6
  // preview -- otherwise a stale "Confirm & Run N experiments" could run a
  // DIFFERENT plan than the one it was previewed against.
  useEffect(() => {
    setStep6Preview(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestText])

  // True from the moment Run/Re-run is clicked until a fresh result lands --
  // gates the Result/Step-output panels below so they show a "running"
  // placeholder instead of the PREVIOUS run's still-cached content. Without
  // this, clicking re-run only clears `syncResult`/`jobId` (see
  // `onMutate`), but `session-step`'s background refetch can momentarily
  // re-populate `latestAttempt` with the OLD (still-current on the backend
  // until the new run actually completes) attempt, so the stale output
  // never visibly went away.
  const isRerunning = runMutation.isPending || job.status === "pending" || job.status === "running"

  useEffect(() => {
    if (job.status === "completed" || job.status === "failed") {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["session-step", sessionId, step] })
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
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
    onSuccess: () => navigate("/runs"),
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
          <Button variant="outline" onClick={() => navigate("/runs")}>
            All runs
          </Button>
        </div>
      </div>

      <StepStepper
        manifest={sessionQuery.data}
        activeStep={step}
        specState={specState}
        onSelect={(s) => navigate(`/runs/${sessionId}/step/${s}`)}
      />

      {(() => {
        const eventsCard = (
          <Card>
            <CardHeader>
              <CardTitle>Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-48 overflow-auto font-mono text-xs">
                {[...(eventsQuery.data ?? [])].reverse().map((e) => (
                  <div key={e.seq} className={e.level === "error" ? "text-destructive" : undefined}>
                    [{new Date(e.at).toLocaleString()}] [{e.step ?? "-"}] {e.stage}.{e.event} {e.detail}
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
              {step === 6 && step6ConfigDiff && (
                <div className="flex flex-col gap-2 rounded-md border border-border p-2 text-xs">
                  <Step6ConfigDiffTable
                    original={step6ConfigDiff.original}
                    cz={step6ConfigDiff.cz}
                    std={step6ConfigDiff.std}
                  />
                  <div>
                    <p className="font-medium">SignalDoc raw fields (② query)</p>
                    <div className="font-mono text-muted-foreground">
                      {Object.entries(step6ConfigDiff.raw).map(([k, v]) => (
                        <div key={k}>
                          {k}: {formatCzValue(v)}
                        </div>
                      ))}
                    </div>
                    <p className="mt-1 text-muted-foreground">
                      Not in SignalDoc, applied unconditionally to every C&amp;Z factor from{" "}
                      <code className="font-mono">Signals/pyCode/SignalMasterTable.py</code> instead (already
                      folded into ②'s <code className="font-mono">universe_filters</code> above): shrcd in{" "}
                      {"{10, 11, 12}"}, exchcd in {"{1, 2, 3}"}.
                    </p>
                  </div>
                  <div>
                    <p className="font-medium">C&amp;Z's own reported performance (reference only, not re-run here)</p>
                    <p className="text-muted-foreground">
                      mean return: {formatCzValue(step6ConfigDiff.czReported.mean_return)}, t-stat:{" "}
                      {formatCzValue(step6ConfigDiff.czReported.t_stat)}
                    </p>
                  </div>
                </div>
              )}
              {step === 6 && step6HxzReported && (
                <div className="flex flex-col gap-1 rounded-md border border-border p-2 text-xs">
                  {step6HxzReported.originalInsample && (
                    <div>
                      <p className="font-medium">
                        {step6HxzReported.originalInsample.label} (reference only, not re-run here) -- original
                        in-sample
                      </p>
                      <p className="text-muted-foreground">
                        mean return: {formatCzValue(step6HxzReported.originalInsample.mean_return)}, t-stat:{" "}
                        {formatCzValue(step6HxzReported.originalInsample.t_stat)}, start year:{" "}
                        {formatCzValue(step6HxzReported.originalInsample.start_year)}, end year:{" "}
                        {formatCzValue(step6HxzReported.originalInsample.end_year)}, n_months:{" "}
                        {formatCzValue(step6HxzReported.originalInsample.n_months)}
                      </p>
                    </div>
                  )}
                  {step6HxzReported.hxzPaperSample && (
                    <div>
                      <p className="font-medium">
                        {step6HxzReported.hxzPaperSample.label} (reference only, not re-run here) -- HXZ's own
                        paper sample
                      </p>
                      <p className="text-muted-foreground">
                        mean return: {formatCzValue(step6HxzReported.hxzPaperSample.mean_return)}, t-stat:{" "}
                        {formatCzValue(step6HxzReported.hxzPaperSample.t_stat)}, start year:{" "}
                        {formatCzValue(step6HxzReported.hxzPaperSample.start_year)}, end year:{" "}
                        {formatCzValue(step6HxzReported.hxzPaperSample.end_year)}, n_months:{" "}
                        {formatCzValue(step6HxzReported.hxzPaperSample.n_months)}
                      </p>
                    </div>
                  )}
                </div>
              )}
              {/* step4 gets its own dedicated JobLogPanel inside the "Repair
               * (before / after)" card below -- skip the generic one here so
               * the log doesn't render twice on the page. */}
              {step > 2 && step !== 4 && def.isJob ? <JobLogPanel job={job} /> : null}
              {!isRerunning && latestAttempt?.diagnostics && "readiness" in latestAttempt.diagnostics && (
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
                  {step === 4 && (
                    <div className="flex flex-col gap-2 rounded-md border border-border p-2 text-xs">
                      <p className="font-medium">What this step checks</p>
                      {[
                        { name: "Syntax", desc: "the generated compute_signal code parses as valid Python." },
                        {
                          name: "Schema",
                          desc: "the code actually defines a compute_signal function (not renamed/missing).",
                        },
                        {
                          name: "Future-leak scan",
                          desc: "the code text is checked for forbidden patterns that could look ahead at data not yet available at formation time.",
                        },
                        {
                          name: "Reproducibility",
                          desc: "placeholder check, not yet implemented -- always passes today.",
                        },
                        {
                          name: "Execution smoke test",
                          desc: "the exact backtest script Step 5 will run is imported and its compute_signal is called on a small real-data slice, just to confirm it runs without raising an exception -- it does not check the output values themselves.",
                        },
                        {
                          name: "Faithfulness",
                          desc: "only when an LLM provider is selected -- an LLM re-reads the paper's approved formula and the code side by side and flags whether the code implements that SAME formula; it never judges whether the formula itself is the right empirical choice.",
                        },
                      ].map(({ name, desc }) => (
                        <div key={name} className="flex gap-2">
                          <span className="w-32 shrink-0 font-medium text-muted-foreground">{name}</span>
                          <span className="text-muted-foreground">{desc}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {"llm_provider" in def.requestTemplate && (
                    <p className="text-xs text-muted-foreground">
                      Uses the LLM Provider / Model picked in the sidebar (bottom-left) -- change it there, not
                      just in this JSON, or it'll be overwritten on your next edit.
                    </p>
                  )}
                  {step === 3 && (
                    <MethodSpecPicker
                      // Default to THIS session's own Step2-resolved spec (if it has
                      // one) instead of always making the user find it again in the
                      // global resolved-specs list -- still overridable via the picker.
                      defaultFactorId={(specState.resolved as { paper?: { factor_id?: string } } | undefined)?.paper?.factor_id}
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
                  {step === 6 &&
                    (() => {
                      let current: Record<string, unknown> = {}
                      try {
                        current = JSON.parse(requestText)
                      } catch {
                        // leave the template default in place; the picker just won't reflect it yet.
                      }
                      return (
                        <>
                          <Step6VersionsPicker
                            runOriginal={Boolean(current.run_original)}
                            runStandardized={Boolean(current.run_standardized)}
                            czEnabled={step6CzEnabled}
                            autoAttribution={current.auto_attribution !== false}
                            onChange={(patch) => {
                              const parsed = JSON.parse(requestText)
                              setRequestText(JSON.stringify({ ...parsed, ...patch }, null, 2))
                            }}
                            onToggleCz={(enabled) => {
                              setStep6CzEnabled(enabled)
                              if (!enabled) {
                                const parsed = JSON.parse(requestText)
                                delete parsed.cz_config_override
                                setRequestText(JSON.stringify(parsed, null, 2))
                              }
                            }}
                          />
                          <div className={step6CzEnabled ? undefined : "pointer-events-none opacity-40"}>
                            <Step6CzConfigPreview
                              sessionId={sessionId}
                              sessionFactorId={sessionQuery.data?.factor_id}
                              spec={current.spec as Record<string, unknown> | undefined}
                              confirmedOverride={current.cz_config_override as Record<string, unknown> | undefined}
                              onConfirm={(override) => {
                                const parsed = JSON.parse(requestText)
                                if (override === undefined) {
                                  delete parsed.cz_config_override
                                } else {
                                  parsed.cz_config_override = override
                                }
                                setRequestText(JSON.stringify(parsed, null, 2))
                              }}
                              onDataChange={setStep6ConfigDiff}
                            />
                            <Step6HxzConfigPreview
                              sessionId={sessionId}
                              sessionFactorId={sessionQuery.data?.factor_id}
                              specFactorId={
                                (current.spec as { paper?: { factor_id?: string } } | undefined)?.paper?.factor_id
                              }
                              sampleWindow={extractPaperSampleWindow(current.spec as Record<string, unknown> | undefined)}
                              onDataChange={setStep6HxzReported}
                            />
                          </div>
                        </>
                      )
                    })()}
                  {step === 7 && (
                    <div className="flex flex-col gap-2 rounded-md border border-border p-2 text-xs">
                      <p className="font-medium">What this step computes</p>
                      {[
                        {
                          name: "Track vs paper",
                          desc: "each track's sign/magnitude/significance compared against the paper's own reported headline number, including the HXZ three-tier significance hurdle (1.96/2.78/3.39).",
                        },
                        {
                          name: "Config diff",
                          desc: "every track's resolved config diffed against the baseline (original_method), grouped by pipeline stage (signal input / portfolio construction / universe / \u2026).",
                        },
                        {
                          name: "Gap decomposition (OAT)",
                          desc: "one-at-a-time per-switch contributions -- only produced when the batch fell back to ablation_* tracks (more than 4 differing fields), not for a full-factorial batch.",
                        },
                        {
                          name: "Shapley attribution",
                          desc: "order-independent decomposition of the mean-return gap across a full-factorial batch's switches; requires every 2^n corner of the factorial cube to be present.",
                        },
                        {
                          name: "Paired significance test",
                          desc: "per single-switch track, a paired Newey-West test of that switch's effect against the baseline, using monthly returns restricted to the paper's in-sample window.",
                        },
                        {
                          name: "Joint Wald test",
                          desc: "one test across ALL single-switch contrasts at once, accounting for their correlation -- guards against reading a single switch's number as important without the switches collectively clearing significance.",
                        },
                        {
                          name: "Decay / robustness",
                          desc: "publication-decay and cross-sample-period robustness summaries.",
                        },
                      ].map(({ name, desc }) => (
                        <div key={name} className="flex gap-2">
                          <span className="w-40 shrink-0 font-medium text-muted-foreground">{name}</span>
                          <span className="text-muted-foreground">{desc}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {(step === 3 || step === 4 || step === 5) && <RequestFieldsSummary requestText={requestText} />}
                  {step !== 6 && step !== 3 && step !== 4 && step !== 5 && step !== 7 && step !== 8 && (
                    <Textarea
                      className="h-64 font-mono text-xs"
                      value={requestText}
                      onChange={(e) => setRequestText(e.target.value)}
                    />
                  )}
                  {(() => {
                    // ② enabled but not yet queried+confirmed -> block running
                    // the batch until it is, so a track_specs-less ② silently
                    // never runs is impossible to overlook.
                    let step6Blocked = false
                    if (step === 6 && step6CzEnabled) {
                      try {
                        step6Blocked = JSON.parse(requestText).cz_config_override === undefined
                      } catch {
                        // leave step6Blocked false; a malformed request body is caught elsewhere
                      }
                    }
                    if (step === 6) {
                      return (
                        <>
                          {step6Blocked && (
                            <p className="text-xs text-amber-600">
                              ② is checked above -- query C&amp;Z's config and confirm it below before running, or
                              uncheck ② to run without it.
                            </p>
                          )}
                          <div className="flex gap-2">
                            <Button
                              onClick={() => step6PreviewMutation.mutate(undefined)}
                              disabled={step6PreviewMutation.isPending || runMutation.isPending || step6Blocked}
                            >
                              {step6PreviewMutation.isPending ? "Counting…" : "Preview experiment count"}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => step6PreviewMutation.mutate({ fromUpstream: true })}
                              disabled={step6PreviewMutation.isPending || runMutation.isPending || step6Blocked}
                              title="Re-fetch the upstream step's latest output and preview a run against it, discarding whatever's in the request box above."
                            >
                              Preview from upstream output
                            </Button>
                            {step6Preview && (
                              <Button
                                onClick={() => runMutation.mutate({ fromUpstream: step6Preview.fromUpstream })}
                                disabled={runMutation.isPending}
                              >
                                Confirm & run {step6Preview.track_count} experiment
                                {step6Preview.track_count === 1 ? "" : "s"}
                              </Button>
                            )}
                          </div>
                          {step6Preview && (
                            <div className="flex flex-col gap-2">
                              <p className="text-xs font-medium">
                                This will run {step6Preview.track_count} experiment
                                {step6Preview.track_count === 1 ? "" : "s"}:
                              </p>
                              {step6Preview.tracks.map((track) => (
                                <Step6PreviewTrackCard key={track.name} track={track} />
                              ))}
                            </div>
                          )}
                        </>
                      )
                    }
                    return (
                      <>
                        <div className="flex gap-2">
                          <Button
                            onClick={() => runMutation.mutate(undefined)}
                            disabled={runMutation.isPending}
                          >
                            Run {def.label}
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => runMutation.mutate({ fromUpstream: true })}
                            disabled={runMutation.isPending}
                            title="Re-fetch the upstream step's latest output and re-run this step with it, discarding whatever's in the request box above."
                          >
                            Re-run from upstream output
                          </Button>
                        </div>
                      </>
                    )
                  })()}
                  {requestError && <p className="text-xs text-destructive">{requestError}</p>}
                  {step === 4 && !isRerunning && (
                    <Step4Output
                      sessionId={sessionId}
                      attempt={latestAttempt}
                      syncResult={def.isJob ? job.result : syncResult}
                    />
                  )}
                </CardContent>
              </Card>

              {step === 3 ? (
                <Card>
                  <CardHeader>
                    <CardTitle>compute_signal code</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {isRerunning ? (
                      <p className="text-xs text-muted-foreground">Running…</p>
                    ) : (
                      <Step3ComputeSignalCard sessionId={sessionId} attempt={latestAttempt} />
                    )}
                  </CardContent>
                </Card>
              ) : step === 4 ? (
                <Card>
                  <CardHeader>
                    <CardTitle>Repair (before / after)</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    {/* step4 is a job (repair loop + full validation-sample run
                     * can take a while) -- keep the live log visible instead of
                     * only showing the final diff once it completes. */}
                    <JobLogPanel job={job} />
                    {isRerunning ? (
                      <p className="text-xs text-muted-foreground">Running…</p>
                    ) : (
                      <Step4RepairCard sessionId={sessionId} attempt={latestAttempt} manifest={sessionQuery.data} />
                    )}
                  </CardContent>
                </Card>
              ) : step === 5 ? (
                <Card>
                  <CardHeader>
                    <CardTitle>Backtest run</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    <JobLogPanel job={job} />
                    {isRerunning ? (
                      <p className="text-xs text-muted-foreground">Running…</p>
                    ) : (
                      <Step5HeadlineCard attempt={latestAttempt} />
                    )}
                  </CardContent>
                </Card>
              ) : (
                resultCard
              )}
            </div>

            {step > 2 && (
              <Card>
                <CardHeader>
                  <CardTitle>Step output</CardTitle>
                </CardHeader>
                <CardContent>
                  {isRerunning ? (
                    <p className="text-xs text-muted-foreground">Running… previous result cleared.</p>
                  ) : (
                    <StepOutputView
                      step={step}
                      sessionId={sessionId}
                      attempt={latestAttempt}
                      syncResult={def.isJob ? job.result : syncResult}
                      manifest={sessionQuery.data}
                      paperReported={(() => {
                        try {
                          return extractPaperReported(JSON.parse(requestText).spec)
                        } catch {
                          return null
                        }
                      })()}
                      czReported={step6ConfigDiff?.czReported ?? null}
                      hxzReported={step6HxzReported}
                    />
                  )}
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
 * No longer auto-advances (2026-08-16): a human clicks the stepper to move
 * on -- `onStateChange` still mirrors every state change up to
 * `SessionDetailPage` so the stepper's step-1/2 badges recolor immediately,
 * the same way steps 3-8 do from their own session-recorded attempt status. */

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
  //: Staged whole-paper structural edits -- add/remove a universe filter,
  //: convert a disjoint range to `intervals`, add the default target sort,
  //: edit a sort's group_count/breakpoints_basis, edit a filter's
  //: derivation. These used to call `patch()` immediately on click
  //: (mutating `state.paper` AND clearing `review`/`resolved` on the very
  //: first click), so a human couldn't make several structural edits in one
  //: pass without the findings panel resetting after each one.
  //: `stagedPaperOverride` is the composable "next paper" these edits build
  //: on top of each other (each function reads `effectivePaper` below, not
  //: `state.paper`, so edits compose); nothing commits to `state.paper` or
  //: clears `review`/`resolved` until `applyPendingCorrections` runs.
  const [stagedPaperOverride, setStagedPaperOverride] = useState<Record<string, unknown> | undefined>(undefined)
  const effectivePaper = (stagedPaperOverride ?? state.paper) as Record<string, unknown> | undefined
  const rangeUnionSuggestions = useMemo(() => disjointUniverseRangeSuggestions(effectivePaper), [effectivePaper])
  const [file, setFile] = useState<File | null>(null)
  const [targetName, setTargetName] = useState(defaultTargetName)
  // Restore from persisted state on mount -- otherwise navigating away from
  // this page (or just switching Step 1 <-> Step 2) while a job is still
  // running loses track of it: the backend job keeps executing regardless,
  // but nothing is left to re-subscribe/poll for its result.
  const [extractJobId, setExtractJobId] = useState<string | null>(() => getMethodSpecWorkflowState(sessionId).extractJobId ?? null)
  const [reviewJobId, setReviewJobId] = useState<string | null>(() => getMethodSpecWorkflowState(sessionId).reviewJobId ?? null)
  const [valuePatchDrafts, setValuePatchDrafts] = useState<Record<string, string>>({})
  const [useOtherValueFor, setUseOtherValueFor] = useState<Record<string, boolean>>({})
  //: field_path -> the paper's literal wording, only shown/sent when that
  //: field_path's drafted value is the enum's "other" member.
  const [unsupportedValueDrafts, setUnsupportedValueDrafts] = useState<Record<string, string>>({})
  //: universe.filters index -> raw `FormulaSpec` JSON text for that
  //: filter's `derivation` -- client-side only edit (no dedicated backend
  //: endpoint; `state.paper` is resent wholesale on the next /review or
  //: /resolve call, same as every other in-session paper edit).
  const [derivationDrafts, setDerivationDrafts] = useState<Record<number, string>>({})
  const [derivationError, setDerivationError] = useState<string | null>(null)
  //: universe.filters index -> drafted `unapplied_reason` text, for the
  //: `accepted_unapplied` escape hatch (docs/todo.md item 2) -- same
  //: client-side-only pattern as `derivationDrafts` (no dedicated backend
  //: endpoint; `state.paper` is resent wholesale on the next /resolve call).
  const [unappliedReasonDrafts, setUnappliedReasonDrafts] = useState<Record<number, string>>({})
  const [unappliedError, setUnappliedError] = useState<string | null>(null)
  //: universe.filters index -> drafted `applied_reason` text, for the
  //: symmetric `human_confirmed_applied` escape hatch -- same client-side-
  //: only pattern as `unappliedReasonDrafts` (no dedicated backend
  //: endpoint; `state.paper` is resent wholesale on the next /resolve call).
  const [appliedReasonDrafts, setAppliedReasonDrafts] = useState<Record<number, string>>({})
  const [appliedError, setAppliedError] = useState<string | null>(null)
  //: universe.filters index -> staged accepted_unapplied/human_confirmed_applied
  //: decision. Deliberately staged, not applied immediately on click: the
  //: previous immediate-`patch()` behavior cleared `review`/`resolved` on the
  //: very first click, so the whole findings panel reset out from under a
  //: human still working through several filters. Now these fold into the
  //: SAME single "Apply N correction(s)" button as `filterFieldDrafts`/
  //: `valuePatchDrafts` below -- one commit, one review reset, after every
  //: decision on this page is made.
  type FilterStatusDraft =
    | { action: "mark_unapplied"; reason: string }
    | { action: "undo_unapplied" }
    | { action: "mark_applied"; reason: string }
    | { action: "undo_applied" }
  const [filterStatusDrafts, setFilterStatusDrafts] = useState<Record<number, FilterStatusDraft>>({})
  //: universe.filters index -> drafted {concept_id, op, value} text for that
  //: filter's own scalar fields. Same client-side-only pattern as
  //: `derivationDrafts` -- concept_id/op/value live on `FilterSpec`, not a
  //: `SourcedValue`, so `/patch-value` can't touch them either.
  const [filterFieldDrafts, setFilterFieldDrafts] = useState<
    Record<number, { concept_id?: string; op?: string; value?: string }>
  >({})
  const [filterFieldError, setFilterFieldError] = useState<string | null>(null)
  //: universe.filters index -> drafted reason text for that filter's edit
  //: or removal -- recorded as an `EvidenceCitation` (edit) or appended to
  //: `paper.notes` (removal, since the filter itself is gone afterward) so
  //: the correction has an audit trail, same spirit as `/patch-value`'s
  //: "human correction: <reason>" citation for scalar fields.
  const [filterReasonDrafts, setFilterReasonDrafts] = useState<Record<number, string>>({})
  const [addFilterReason, setAddFilterReason] = useState("")
  //: Set only when `addDefaultTargetSort` can't auto-pick a concept/direction
  //: (ambiguous or missing `signal.formula.output_concept`/`signal.direction`)
  //: -- surfaced next to the "Add default target sort" button instead of a
  //: silent no-op.
  const [sortDefaultError, setSortDefaultError] = useState<string | null>(null)
  //: null = "total diff" (Step1 raw -> final spec); otherwise an index into
  //: `state.history` for that single round's before/after.
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const [showRawJson, setShowRawJson] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { provider, model, setProvider, setModel } = useLlm()
  const schemaQuery = useQuery({ queryKey: ["methodspec-schema"], queryFn: sessionApi.getSchemaReference })
  //: Powers the `source_column` dropdown's options (filtered by whichever
  //: `source_table` a sibling `data.fields[i]` entry currently has) --
  //: `source_table` itself already gets a dropdown for free from
  //: `schemaQuery`'s dynamic-enum `allowed_values` (see `schemaFieldInfo`).
  const dataCatalogQuery = useQuery({ queryKey: ["data-catalog"], queryFn: sessionApi.getDataCatalog })
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
    tool_results?: ToolResult[]
  }>(extractJobId)
  const reviewJob = useJobStream<{
    spec?: Record<string, unknown>
    error?: string
    review?: Record<string, unknown>
    total_diff?: Array<{ field_path: string; old: unknown; new: unknown }>
    history?: ReviewRound[]
    tool_results?: ToolResult[]
  }>(reviewJobId)

  useEffect(() => {
    onStateChange(state)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const patch = (p: MethodSpecWorkflowState) => {
    // Merge against the latest PENDING in-memory state (functional update),
    // not a localStorage re-read: two `patch()` calls issued back-to-back in
    // the same effect (see the extract-completion effect below) would
    // otherwise have the second call re-read a still-stale (or, if a prior
    // write failed -- e.g. quota exceeded -- permanently empty) disk copy as
    // its merge base, silently dropping whatever the first call just set.
    setState((prev) => {
      const next = { ...prev, ...p }
      persistMethodSpecWorkflowState(sessionId, next)
      onStateChange(next)
      return next
    })
  }

  const reviewLoopMutation = useMutation({
    mutationFn: (vars: { rawSpec: Record<string, unknown>; documentId: string; targetName: string; paperText: string }) =>
      sessionApi.runReviewLoop(vars.rawSpec, vars.documentId, vars.targetName, vars.paperText, provider, model, sessionId),
    // Clear the currently-displayed paper/review/resolve/diff right away --
    // a restart from Step 1's output should look like a fresh run, not keep
    // showing this step's previous (possibly hand-patched) result while the
    // new loop is still running.
    onMutate: () => {
      setReviewJobId(null)
      patch({
        paper: undefined,
        review: undefined,
        reviewSource: undefined,
        resolved: undefined,
        totalDiff: undefined,
        history: undefined,
        reviewRunning: true,
        reviewJobId: undefined,
      })
      // A full restart makes every staged-but-uncommitted edit from the
      // previous spec meaningless (wrong shape, wrong indices) -- clear
      // them all rather than let them silently resurface against the new
      // spec once it loads (`effectivePaper` would otherwise keep
      // overriding it with stale `stagedPaperOverride` content).
      setStagedPaperOverride(undefined)
      setFilterFieldDrafts({})
      setFilterReasonDrafts({})
      setFilterStatusDrafts({})
      setUnappliedReasonDrafts({})
      setAppliedReasonDrafts({})
      setDerivationDrafts({})
      setValuePatchDrafts({})
      setUnsupportedValueDrafts({})
      setSortDefaultError(null)
    },
    onSuccess: (res) => {
      setReviewJobId(res.job_id)
      patch({ reviewJobId: res.job_id })
    },
    onError: (err) => {
      patch({ reviewRunning: false })
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
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
          extractToolResults: extractJob.result.tool_results,
        })
        setError(null)
        patch({ extractJobId: undefined })
        if (state.documentId && state.targetName && paperText) {
          reviewLoopMutation.mutate({ rawSpec, documentId: state.documentId, targetName: state.targetName, paperText })
        }
      } else {
        setError(extractJob.result?.error ?? "Extraction returned no output")
        patch({ extractJobId: undefined })
      }
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
    } else if (extractJob.status === "failed") {
      setError(extractJob.error)
      patch({ extractJobId: undefined })
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
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
          reviewRunning: false,
          reviewJobId: undefined,
          reviewToolResults: reviewJob.result.tool_results,
        })
        setError(null)
      } else {
        patch({ reviewRunning: false, reviewJobId: undefined })
        setError(reviewJob.result?.error ?? "Step2 review loop did not converge on a valid MethodSpec")
      }
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
    } else if (reviewJob.status === "failed") {
      patch({ reviewRunning: false, reviewJobId: undefined })
      setError(reviewJob.error)
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
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
      patch({ extractJobId: res.job_id })
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  // Rules-only re-review (`review_method_spec`'s D2/missing-mapping findings,
  // no LLM call) -- used after a human value patch, since a patch clears the
  // stored review and there's no separate LLM-review endpoint to fall back
  // to (that ran once already, via `runReviewLoop` above).
  const reviewMutation = useMutation({
    mutationFn: () => sessionApi.reviewPaperSpec(state.paper!, sessionId),
    // Clear the currently-displayed findings/resolve result right away --
    // otherwise the old review stays on screen until this request resolves.
    // `reviewRunning: true` is what makes the stepper show "running" for
    // Step 2 during that window instead of falling back to "not_started".
    onMutate: () => patch({ review: undefined, reviewSource: undefined, resolved: undefined, reviewRunning: true }),
    onSuccess: (review) => {
      patch({ review, reviewSource: "rules", resolved: undefined, reviewRunning: false })
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
    },
    onError: (err) => {
      patch({ reviewRunning: false })
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
  })

  // Corrects the extracted VALUE itself. Produces a NEW paper, so the
  // stored review/resolved state is cleared -- there's no automatic
  // staleness detection forcing a re-review anymore (docs/decision-log.md
  // 2026-08-09), so we clear it here as the deliberate "you must redo this"
  // signal instead.
  // Takes `paper` as an argument (rather than closing over `state.paper`)
  // so `applyPendingCorrections` below can hand it the filter-edited paper
  // when both kinds of correction are pending together -- see that
  // function's comment for why.
  const patchValueMutation = useMutation({
    mutationFn: (paper: Record<string, unknown>) =>
      sessionApi.patchPaperValue(paper, valuePatchDrafts, "", sessionId, unsupportedValueDrafts),
    onSuccess: (paperSpec) => {
      patch({ paper: paperSpec, review: undefined, reviewSource: undefined, resolved: undefined })
      setValuePatchDrafts({})
      setUnsupportedValueDrafts({})
      setFilterFieldDrafts({})
      setFilterReasonDrafts({})
      setFilterStatusDrafts({})
      setUnappliedReasonDrafts({})
      setAppliedReasonDrafts({})
      setDerivationDrafts({})
      setStagedPaperOverride(undefined)
      setSortDefaultError(null)
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  // `universe.filters[i].derivation` (a `FormulaSpec`) isn't a
  // `SourcedValue` -- `apply_value_patches`/`/patch-value` only patch
  // scalar high-impact fields, so this can't go through that endpoint.
  // Purely a client-side edit of `state.paper` instead: every /review and
  // /resolve call already resends `state.paper` wholesale, so there's
  // nothing to persist server-side until the human re-runs review anyway.
  // `universe.filters[i].derivation` (a `FormulaSpec`) isn't a
  // `SourcedValue` -- `apply_value_patches`/`/patch-value` only patch
  // scalar high-impact fields, so this can't go through that endpoint.
  // No longer its own immediate-commit/own-button pair: parsing happens
  // inline in `computeFilterEditsPaper` below, folded into the SAME single
  // "Apply N correction(s)" button as every other pending edit on this
  // page -- `derivationDrafts` (the raw textarea text) is the only draft
  // state kept here.

  // `accepted_unapplied`/`unapplied_reason` (docs/todo.md item 2): staged
  // into `filterStatusDrafts`, not committed immediately -- see that
  // state's comment. Actually applied by `applyPendingCorrections` below,
  // alongside every other pending correction on this page.
  const applyAcceptedUnapplied = (index: number) => {
    setUnappliedError(null)
    const reason = (unappliedReasonDrafts[index] ?? "").trim()
    if (!reason) {
      setUnappliedError("Provide a reason before marking accepted_unapplied.")
      return
    }
    setFilterStatusDrafts((prev) => ({ ...prev, [index]: { action: "mark_unapplied", reason } }))
  }

  const undoAcceptedUnapplied = (index: number) => {
    setFilterStatusDrafts((prev) => ({ ...prev, [index]: { action: "undo_unapplied" } }))
  }

  // `human_confirmed_applied`/`applied_reason`: symmetric staged escape
  // hatch to `accepted_unapplied`/`unapplied_reason` above.
  const applyHumanConfirmedApplied = (index: number) => {
    setAppliedError(null)
    const reason = (appliedReasonDrafts[index] ?? "").trim()
    if (!reason) {
      setAppliedError("Provide a reason before marking human_confirmed_applied.")
      return
    }
    setFilterStatusDrafts((prev) => ({ ...prev, [index]: { action: "mark_applied", reason } }))
  }

  const undoHumanConfirmedApplied = (index: number) => {
    setFilterStatusDrafts((prev) => ({ ...prev, [index]: { action: "undo_applied" } }))
  }

  //: Same `EvidenceCitation` shape as every citation elsewhere in the spec
  //: -- `interpretation` records who made this correction and why, mirroring
  //: `apply_value_patches`'s "<source> correction: <reason>" convention for
  //: scalar `SourcedValue` fields, so a filter edit leaves the same kind of
  //: audit trail those do.
  const humanCorrectionCitation = (reason: string) => ({
    location: "", quote: "", table_ref: null,
    interpretation: reason.trim() ? `human correction: ${reason.trim()}` : "human correction",
  })

  // concept_id/op/value editing for existing `universe.filters[]` entries --
  // same client-side-edit pattern as the `derivation` drafts above (these
  // scalar `FilterSpec` fields aren't `SourcedValue`s either, so there's no
  // `/patch-value` path for them; `state.paper` is resent wholesale on the
  // next /review or /resolve call). Pure computation only -- no `patch()`
  // call and no draft reset here, since `applyPendingCorrections` below
  // decides where the result goes (straight to local state, or into the
  // `/patch-value` request body when value corrections are pending too).
  const computeFilterEditsPaper = (): Record<string, unknown> | undefined => {
    const paper = effectivePaper as { universe?: { filters?: Array<Record<string, unknown>> } } | undefined
    const filters = paper?.universe?.filters
    const hasFieldDrafts = Object.keys(filterFieldDrafts).length > 0
    const hasStatusDrafts = Object.keys(filterStatusDrafts).length > 0
    const hasDerivationDrafts = Object.keys(derivationDrafts).length > 0
    if (!filters || (!hasFieldDrafts && !hasStatusDrafts && !hasDerivationDrafts)) {
      return paper as Record<string, unknown> | undefined
    }
    const nextFilters = [...filters]
    setDerivationError(null)
    try {
      for (const [indexStr, text] of Object.entries(derivationDrafts)) {
        const i = Number(indexStr)
        nextFilters[i] = { ...nextFilters[i], derivation: text.trim() === "" ? null : JSON.parse(text) }
      }
    } catch (e) {
      setDerivationError(e instanceof Error ? `Invalid derivation JSON: ${e.message}` : String(e))
      return undefined
    }
    try {
      for (const [indexStr, draft] of Object.entries(filterFieldDrafts)) {
        const i = Number(indexStr)
        const next = { ...nextFilters[i] }
        if (draft.concept_id !== undefined) next.concept_id = draft.concept_id
        if (draft.op !== undefined) next.op = draft.op
        if (draft.value !== undefined) {
          const text = draft.value.trim()
          next.value = text === "" ? null : JSON.parse(text)
        }
        const existingEvidence = Array.isArray(next.evidence) ? next.evidence : []
        next.evidence = [...existingEvidence, humanCorrectionCitation(filterReasonDrafts[i] ?? "")]
        nextFilters[i] = next
      }
      // `accepted_unapplied`/`human_confirmed_applied` are mutually exclusive
      // server-side (see `FilterSpec`'s validator) -- marking one always
      // clears the other here too, so a stray leftover `true` from a prior
      // decision can't trip that validator on submit.
      for (const [indexStr, draft] of Object.entries(filterStatusDrafts)) {
        const i = Number(indexStr)
        const next = { ...nextFilters[i] }
        if (draft.action === "mark_unapplied") {
          next.accepted_unapplied = true
          next.unapplied_reason = draft.reason
          next.human_confirmed_applied = false
          next.applied_reason = ""
        } else if (draft.action === "undo_unapplied") {
          next.accepted_unapplied = false
          next.unapplied_reason = ""
        } else if (draft.action === "mark_applied") {
          next.human_confirmed_applied = true
          next.applied_reason = draft.reason
          next.accepted_unapplied = false
          next.unapplied_reason = ""
        } else if (draft.action === "undo_applied") {
          next.human_confirmed_applied = false
          next.applied_reason = ""
        }
        nextFilters[i] = next
      }
    } catch (e) {
      setFilterFieldError(e instanceof Error ? `Invalid filter value JSON: ${e.message}` : String(e))
      return undefined
    }
    return { ...paper, universe: { ...paper!.universe, filters: nextFilters } }
  }

  // The ONE "Apply" action for every pending correction kind on this page:
  // scalar `valuePatchDrafts` (goes through `/patch-value`), local
  // `universe.filters[]` field/derivation/status edits (`filterFieldDrafts`/
  // `derivationDrafts`/`filterStatusDrafts`, no backend endpoint), and any
  // staged structural edit (`stagedPaperOverride` -- add/remove a filter,
  // convert a range union, add/edit a sort). Deliberately a single button
  // rather than several: `patchValueMutation`'s `onSuccess` replaces
  // `state.paper` wholesale with the server's response, so if these were
  // applied separately, whichever ran second would silently drop the
  // other's edit. Folding everything into the paper sent to `/patch-value`
  // (when a scalar value correction is ALSO pending) keeps it all in the
  // one round trip; otherwise it commits straight to local state.
  const applyPendingCorrections = () => {
    setFilterFieldError(null)
    const nextPaper = computeFilterEditsPaper()
    if (nextPaper === undefined) return
    const hasStatusDrafts = Object.keys(filterStatusDrafts).length > 0
    const hasDerivationDrafts = Object.keys(derivationDrafts).length > 0
    const hasStructuralEdits = stagedPaperOverride !== undefined
    if (Object.keys(valuePatchDrafts).length > 0) {
      // Cleared in `patchValueMutation.onSuccess`, not here -- the mutation
      // is async and can fail; clearing eagerly on `mutate()` would discard
      // a human's pending edits if the request errors out.
      patchValueMutation.mutate(nextPaper)
    } else if (Object.keys(filterFieldDrafts).length > 0 || hasStatusDrafts || hasDerivationDrafts || hasStructuralEdits) {
      patch({ paper: nextPaper, review: undefined, reviewSource: undefined, resolved: undefined })
      setFilterFieldDrafts({})
      setFilterReasonDrafts({})
      setFilterStatusDrafts({})
      setUnappliedReasonDrafts({})
      setAppliedReasonDrafts({})
      setDerivationDrafts({})
      setStagedPaperOverride(undefined)
      setSortDefaultError(null)
    }
  }

  const addUniverseFilter = () => {
    const paper = effectivePaper as { universe?: { filters?: Array<Record<string, unknown>> } } | undefined
    if (!paper?.universe) return
    const nextFilters = [
      ...(paper.universe.filters ?? []),
      {
        concept_id: "", op: "nonmissing", value: null,
        evidence: [humanCorrectionCitation(addFilterReason)],
        derivation: null, accepted_unapplied: false, unapplied_reason: "",
        human_confirmed_applied: false, applied_reason: "",
      },
    ]
    setStagedPaperOverride({ ...paper, universe: { ...paper.universe, filters: nextFilters } })
    setAddFilterReason("")
  }

  //: The engine currently only executes single-sort portfolios (see
  //: `registry.py`'s `_clamp_sort_dims`/target-sort resolution) -- for a
  //: paper whose extracted spec has NO `portfolio.sorts` entry at all (e.g.
  //: a Fama-MacBeth/regression-based paper being manually approximated with
  //: an equivalent quantile-sort portfolio, or an extraction gap), this
  //: builds one deterministic default sort + a long/short leg pair instead
  //: of requiring the human to hand-author every `SortDimension` field.
  //: The sort's `concept_id` is `signal.formula.output_concept` -- the
  //: paper's OWN computed signal, same convention as every other resolved
  //: spec in this repo (verified against `asset_growth`'s resolved spec:
  //: the sort's concept_id matches the signal's `output_concept`, not a raw
  //: `data.fields` input) -- never a raw input field, since target-sort
  //: concepts are deliberately excluded from `unmapped_concepts()`'s
  //: required-mapping set (they reference the computed signal, not a
  //: physical column). Long/short legs are picked from `signal.direction`
  //: (negative => long the low quantile, positive => long the high
  //: quantile); anything else (non_monotonic/unspecified) is genuinely
  //: ambiguous and left for a human to author manually.
  const addDefaultTargetSort = () => {
    setSortDefaultError(null)
    const paper = effectivePaper as
      | {
          portfolio?: { sorts?: Array<Record<string, unknown>>; legs?: Array<Record<string, unknown>> }
          signal?: { formula?: { output_concept?: string }; direction?: { value?: string } }
        }
      | undefined
    if (!paper?.portfolio) return
    if ((paper.portfolio.sorts ?? []).length > 0) return
    const conceptId = paper.signal?.formula?.output_concept?.trim()
    if (!conceptId) {
      setSortDefaultError("signal.formula.output_concept is empty -- can't auto-pick a sort concept, add the sort manually.")
      return
    }
    const direction = paper.signal?.direction?.value
    if (direction !== "positive" && direction !== "negative") {
      setSortDefaultError(
        `signal.direction is ${direction ?? "unset"} -- long/short legs are ambiguous, add the sort manually.`,
      )
      return
    }
    const sortId = `${conceptId}_quintile`
    const groupCount = 5
    const citation = humanCorrectionCitation(
      `auto-filled default single sort (quintile, full-sample breakpoints) for signal concept '${conceptId}' -- `
      + "paper's own portfolio.sorts was empty (e.g. a regression-based method being approximated with an "
      + "equivalent quantile-sort portfolio)",
    )
    const sourced = (value: string) => ({ value, evidence: [], status: "unspecified", unsupported_value: null })
    const sort = {
      sort_id: sortId,
      concept_id: conceptId,
      role: "target",
      order: 0,
      mode: sourced("independent"),
      group_type: sourced("quantile"),
      group_count: groupCount,
      breakpoints: { basis: sourced("full_sample"), values: [] },
      condition_on_sort_id: null,
      evidence: [citation],
    }
    const legs = [
      {
        leg_id: `low_${conceptId}`,
        side: direction === "negative" ? "long" : "short",
        selector: { [sortId]: 0 },
        evidence: [citation],
      },
      {
        leg_id: `high_${conceptId}`,
        side: direction === "negative" ? "short" : "long",
        selector: { [sortId]: groupCount - 1 },
        evidence: [citation],
      },
    ]
    setStagedPaperOverride({
      ...paper,
      portfolio: {
        ...paper.portfolio,
        sorts: [sort],
        legs: [...(paper.portfolio.legs ?? []), ...legs],
      },
    })
  }

  //: `group_count` is a plain int on `SortDimension`, not a `SourcedValue`
  //: -- `high_impact_sourced_values` (review.py) never lists it, so it has
  //: no `/patch-value` path at all, unlike `breakpoints.basis`/`group_type`/
  //: `mode`. Edits both fields locally, client-side, same as
  //: `computeFilterEditsPaper` does for `universe.filters`' non-SourcedValue
  //: fields -- and keeps the two legs' `selector` indices in sync with
  //: `group_count` (the "high" leg must always point at `group_count - 1`,
  //: the new top bucket, or a leg silently references a bucket that no
  //: longer exists once the count shrinks).
  const updateSingleSort = (index: number, changes: { group_count?: number; breakpoints_basis?: string }) => {
    const paper = effectivePaper as
      | { portfolio?: { sorts?: Array<Record<string, unknown>>; legs?: Array<Record<string, unknown>> } }
      | undefined
    const sorts = paper?.portfolio?.sorts
    const sort = sorts?.[index]
    if (!paper?.portfolio || !sorts || !sort) return
    const sortId = String(sort.sort_id)
    const prevGroupCount = Number(sort.group_count ?? 0)
    const nextGroupCount = changes.group_count ?? prevGroupCount
    const nextSort = { ...sort }
    if (changes.group_count !== undefined) nextSort.group_count = changes.group_count
    if (changes.breakpoints_basis !== undefined) {
      const bp = sort.breakpoints as { basis?: Record<string, unknown>; values?: unknown[] } | undefined
      nextSort.breakpoints = {
        ...bp,
        basis: { ...(bp?.basis ?? {}), value: changes.breakpoints_basis, unsupported_value: null },
      }
    }
    const nextSorts = sorts.map((s, i) => (i === index ? nextSort : s))
    const legs = paper.portfolio.legs ?? []
    const nextLegs =
      changes.group_count === undefined || nextGroupCount === prevGroupCount
        ? legs
        : legs.map((leg) => {
            const selector = leg.selector as Record<string, number> | undefined
            if (!selector || !(sortId in selector)) return leg
            const isHighBucket = selector[sortId] === prevGroupCount - 1
            if (!isHighBucket) return leg
            return { ...leg, selector: { ...selector, [sortId]: nextGroupCount - 1 } }
          })
    setStagedPaperOverride({ ...paper, portfolio: { ...paper.portfolio, sorts: nextSorts, legs: nextLegs } })
  }

  const removeUniverseFilter = (index: number) => {
    const paper = effectivePaper as
      | { notes?: string; universe?: { filters?: Array<Record<string, unknown>> } }
      | undefined
    const filters = paper?.universe?.filters
    if (!filters) return
    const removed = filters[index]
    const reason = (filterReasonDrafts[index] ?? "").trim()
    const noteLine = `Removed universe filter (human correction${reason ? `: ${reason}` : ""}): ${JSON.stringify({
      concept_id: removed?.concept_id, op: removed?.op, value: removed?.value,
    })}`
    const nextFilters = filters.filter((_, i) => i !== index)
    const nextNotes = paper!.notes ? `${paper!.notes}\n${noteLine}` : noteLine
    setStagedPaperOverride({ ...paper, notes: nextNotes, universe: { ...paper!.universe, filters: nextFilters } })
    // Every OTHER index-keyed draft for this same filters array must shift
    // down too, or a later `computeFilterEditsPaper` reads a draft meant
    // for a now-different filter (or one that no longer exists).
    const remapIndexed = <T,>(prev: Record<number, T>): Record<number, T> => {
      const next: Record<number, T> = {}
      for (const [k, v] of Object.entries(prev)) {
        const idx = Number(k)
        if (idx === index) continue
        next[idx > index ? idx - 1 : idx] = v
      }
      return next
    }
    setFilterFieldDrafts(remapIndexed)
    setFilterReasonDrafts(remapIndexed)
    setFilterStatusDrafts(remapIndexed)
    setUnappliedReasonDrafts(remapIndexed)
    setAppliedReasonDrafts(remapIndexed)
    setDerivationDrafts(remapIndexed)
  }

  const convertToRangeUnion = (suggestion: RangeUnionSuggestion) => {
    const paper = effectivePaper as { universe?: { filters?: Array<Record<string, unknown>> } } | undefined
    const filters = paper?.universe?.filters
    if (!filters) return
    const firstIndex = Math.min(...suggestion.indexes)
    const first = filters[firstIndex]
    const evidence = suggestion.indexes.flatMap((index) => {
      const itemEvidence = filters[index].evidence
      return Array.isArray(itemEvidence) ? itemEvidence : []
    })
    const nextFilters = filters.filter((_, index) => !suggestion.indexes.includes(index))
    nextFilters.splice(firstIndex, 0, {
      ...first,
      op: "intervals",
      value: suggestion.ranges,
      evidence,
    })
    setStagedPaperOverride({ ...paper, universe: { ...paper.universe, filters: nextFilters } })
  }

  const resolveMutation = useMutation({
    mutationFn: async () => {
      // Deterministic concept-mapping is tried first either way (see
      // `build_implementation_resolution`) -- passing provider/model only
      // adds an LLM fallback attempt for concepts that are STILL unresolved
      // after that, so this never changes behavior for a spec that already
      // resolves cleanly.
      const { is_ready, unmapped_concepts, llm_matched_concepts, resolution_findings } = await sessionApi.resolvePaperSpec(
        state.paper!,
        state.review!,
        "us_equity_crsp",
        sessionId,
        provider,
        model,
      )
      if (!is_ready) return { is_ready, unmapped_concepts, llm_matched_concepts, resolution_findings, resolved: null }
      const resolved = await sessionApi.getResolvedMethodSpec((state.paper as { factor_id: string }).factor_id)
      return { is_ready, unmapped_concepts, llm_matched_concepts, resolution_findings, resolved }
    },
    onSuccess: ({ is_ready, resolved }) => {
      queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
      if (resolved) {
        patch({ resolved })
      } else if (!is_ready) {
        setError("Resolved spec is not codegen-ready yet -- see the blocking fields below.")
      }
    },
    onError: (err) => setError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  const findings = (state.review?.findings as Array<Record<string, unknown>> | undefined) ?? []
  const isBlocked = findings.some((f) => f.disposition === "blocked")
  // Every high-impact field, unconditionally (including AUTO_APPROVE ones
  // `findings` omits) -- merged with any OTHER finding not already covered
  // by a high-impact path (missing_mapping, non-high-impact capability
  // checks), so nothing that used to show up disappears.
  const allHighImpactFields = (state.review?.all_high_impact_fields as Array<Record<string, unknown>> | undefined) ?? []
  const highImpactPaths = new Set(allHighImpactFields.map((f) => String(f.field_path)))
  const displayFindings = [...allHighImpactFields, ...findings.filter((f) => !highImpactPaths.has(String(f.field_path)))]
  // Schema reference is keyed by the STATIC dotted path (no `[i]` sort
  // index) -- strip it before lookup; falls back to no info for the one
  // field this can't match (`portfolio.sorts[i].breakpoints.basis`, nested
  // two levels inside a list item the schema walker doesn't recurse into).
  const schemaFieldInfo = (fieldPath: string) => schemaQuery.data?.fields[fieldPath.replace(/\[\d+\]/g, "")]

  //: `data.fields[i].source_column`'s options depend on that SAME index's
  //: `source_table` value (a column only makes sense once a table is
  //: picked) -- `schemaFieldInfo`'s static per-path `allowed_values` can't
  //: express that cross-field dependency, so this reads the live draft/
  //: current `source_table` value straight off `state.paper` and looks up
  //: that table's `physical_columns` in the data-catalog response instead.
  //: Returns `null` (falls back to free-text input) until a real table is
  //: chosen.
  const sourceColumnOptions = (fieldPath: string): string[] | null => {
    const match = fieldPath.match(/^data\.fields\[(\d+)\]\.source_column$/)
    if (!match) return null
    const idx = Number(match[1])
    const fields = (effectivePaper as { data?: { fields?: Array<Record<string, unknown>> } } | undefined)?.data?.fields
    const tableDraft = valuePatchDrafts[`data.fields[${idx}].source_table`]
    const tableValue =
      tableDraft ?? (fields?.[idx]?.source_table as { value?: string } | undefined)?.value ?? null
    if (!tableValue || tableValue === "other") return null
    return dataCatalogQuery.data?.signal_sources[tableValue]?.physical_columns ?? null
  }

  // Step 1 is extract-only; step 2 is review+resolve over whatever step 1
  // already produced -- two distinct pages now, not the same combined panel
  // rendered twice under different labels.
  if (step === 1) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <p className="text-sm font-medium">
            Extract MethodSpec from paper
            {targetName.trim() && (
              <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">
                target_name: {targetName.trim()}
              </span>
            )}
          </p>
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
          <label htmlFor="session-target-name-input" className="text-xs text-muted-foreground">
            target_name (factor label for the extractor)
          </label>
          <input
            id="session-target-name-input"
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
          <ToolResultsPanel results={state.extractToolResults ?? []} title="Step1 tool results" />
        </div>

        {state.rawSpec && (
          <div className="flex flex-col gap-2 rounded-md border border-border p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Step1 succeeded -- raw, unreviewed LLM extraction</p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!file || extractMutation.isPending}
                  onClick={() => extractMutation.mutate()}
                >
                  {extractMutation.isPending ? "Re-extracting…" : "Re-extract"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => navigate(`/runs/${sessionId}/step/2`)}>
                  Go to Step 2 — Review
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Not validated yet, and menu-vocabulary fields (weighting/breakpoints/etc.) are still written as
              the paper's own wording, not engine tokens -- shown below as-is. The Step2 review loop{" "}
              {reviewJob.status === "running" ? "is now running in the background" : reviewJob.status === "completed" ? "has already finished" : "starts automatically"}
              ; see its result (corrected spec, findings, and a before/after diff) on the Step2 page.
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
        <Button size="sm" onClick={() => navigate(`/runs/${sessionId}/step/1`)}>
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
        {canRetry && reviewJob.status !== "running" && (
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
            {reviewLoopMutation.isPending ? "Starting…" : reviewJobId ? "Re-run Step2 review loop" : "Run Step2 review loop"}
          </Button>
        )}
        {!canRetry && (
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
        <ToolResultsPanel results={state.reviewToolResults ?? []} title="Step2 tool results" />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate()}>
            {reviewMutation.isPending ? "Reviewing…" : "Re-run rules-only review"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={reviewLoopMutation.isPending || !(state.documentId && state.targetName && state.paperText)}
            title="Discards any in-step2 edits (patches/status overrides) and restarts the LLM review loop from Step 1's raw extraction."
            onClick={() =>
              reviewLoopMutation.mutate({
                rawSpec: state.rawSpec!,
                documentId: state.documentId!,
                targetName: state.targetName!,
                paperText: state.paperText!,
              })
            }
          >
            {reviewLoopMutation.isPending ? "Re-running…" : "Re-run from Step 1 output"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          The LLM-backed review (full-spec check + menu-vocabulary classification) already ran once as part of
          extraction (`spec_build.build_reviewed_method_spec`). "Re-run rules-only review" only re-runs the
          deterministic rules pass (`MethodReview`'s D2/missing-mapping findings, no LLM call) over THIS
          step's current spec -- use it after applying a value correction below, since a patch clears the
          stored review. "Re-run from Step 1 output" instead throws away any edits made in this step and
          restarts the full LLM review loop from Step 1's raw extraction.
        </p>
        {(() => {
          const sorts = ((effectivePaper as { portfolio?: { sorts?: Array<Record<string, unknown>> } } | undefined)
            ?.portfolio?.sorts ?? [])
          if (sorts.length === 0) {
            return (
              <div className="flex flex-col gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-xs">
                <p>
                  <strong>Portfolio has no sort dimensions.</strong> Step3 codegen needs at least one
                  target-role sort to build portfolios from -- this is expected for a regression-based
                  method (e.g. Fama-MacBeth) where the paper never sorts stocks into groups at all, or a
                  sign that Step1 extraction missed the paper's portfolio construction. The button below
                  auto-fills a default single quintile sort (long the low group, short the high group, or
                  vice versa per <span className="font-mono">signal.direction</span>) -- you can adjust the
                  group count and breakpoint basis right here once it's added, no JSON editing needed.
                </p>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={addDefaultTargetSort}>
                    Add default target sort (quintile)
                  </Button>
                  {sortDefaultError && <p className="text-destructive">{sortDefaultError}</p>}
                </div>
              </div>
            )
          }
          // The engine only ever executes a single sort dimension
          // (`registry.py`'s `_clamp_sort_dims` keeps just the target when
          // there are more) -- only the first entry is editable here.
          const sort = sorts[0]
          const breakpoints = sort.breakpoints as { basis?: { value?: string } } | undefined
          return (
            <div className="flex flex-col gap-2 rounded-md border border-border p-2 text-xs">
              <p className="font-medium">
                Sort dimension: <span className="font-mono">{String(sort.sort_id)}</span> on concept{" "}
                <span className="font-mono">{String(sort.concept_id)}</span>
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-1">
                  <span className="text-muted-foreground">Groups (quintile=5, decile=10):</span>
                  <Input
                    type="number"
                    min={2}
                    max={20}
                    className="h-7 w-16 text-xs"
                    value={String(sort.group_count ?? "")}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (Number.isInteger(n) && n >= 2) updateSingleSort(0, { group_count: n })
                    }}
                  />
                </label>
                <label className="flex items-center gap-1">
                  <span className="text-muted-foreground">Breakpoint basis:</span>
                  <Select
                    value={breakpoints?.basis?.value ?? "full_sample"}
                    onValueChange={(v) => updateSingleSort(0, { breakpoints_basis: v })}
                  >
                    <SelectTrigger className="h-7 w-32 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="full_sample">Full sample</SelectItem>
                      <SelectItem value="nyse">NYSE</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
              </div>
            </div>
          )
        })()}
        {state.review && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Badge variant={isBlocked ? "destructive" : "default"}>
                {findings.length === 0 ? "no findings -- every field looks fine" : `${findings.length} field(s) flagged`}
              </Badge>
              <Badge variant="secondary">{displayFindings.length} high-impact field(s) shown</Badge>
              <Badge variant="outline">
                {state.reviewSource === "llm"
                  ? "LLM-backed review"
                  : state.reviewSource === "human"
                    ? "human override applied"
                    : "Rules-based review"}
              </Badge>
            </div>
            {displayFindings.map((f, i) => {
              const fieldPath = String(f.field_path)
              // Every high-impact field is human-editable regardless of its
              // evidence-driven disposition -- `auto_approve`/`auto_approve_
              // with_flag` fields (clear paper evidence) previously showed
              // only a read-only value, with no way to override a field the
              // paper stated clearly but the human still wants to change
              // (e.g. picking ew over the paper's own vw for a robustness
              // run). `missing_mapping` findings still can't be patched this
              // way -- they need a `data.fields`/`universe.filters` fix and
              // a re-extract, not a value correction.
              // A universe filter and an incomplete-evidence finding are
              // structured objects, not scalar SourcedValues. They remain
              // visible for human review, but must be corrected in the
              // MethodSpec/filter workflow rather than sent to /patch-value.
              // Every finding whose field_path IS a `universe.filters[i]`
              // entry (or a sub-path under it, e.g. `_universe_filter_panel_
              // mismatch_findings`'s "inconsistent" kind) is excluded the
              // same way regardless of `kind` -- `apply_value_patches`
              // raises on any field_path outside its fixed scalar set.
              // These get their OWN inline concept_id/op/value editor below
              // (right where every other field's correction UI lives, not a
              // separate card) instead of the generic value-patch input.
              // `sample.reported_returns` (bare, no .start_year/.end_year
              // suffix) is `_reported_returns_holding_period_mismatch_
              // finding`'s own diagnostic pointer -- not itself a single
              // patchable field (the actual patchable years are the two
              // ALWAYS-shown rows at `.start_year`/`.end_year` right
              // alongside it); patching this bare path would 422 server-side.
              const canPatch =
                !["missing_mapping", "universe_filter", "incomplete"].includes(String(f.kind))
                && !/^universe\.filters\[\d+\]/.test(fieldPath)
                && fieldPath !== "sample.reported_returns"
              const filterIndexMatch = /^universe\.filters\[(\d+)\]/.exec(fieldPath)
              const filterIndex = filterIndexMatch ? Number(filterIndexMatch[1]) : null
              const info = schemaFieldInfo(fieldPath)
              const allowedValues = fieldPath.endsWith(".source_column") ? sourceColumnOptions(fieldPath) : info?.allowed_values ?? null
              const usingOther = useOtherValueFor[fieldPath] ?? false
              const evidence = (f.evidence as Array<Record<string, unknown>> | undefined) ?? []
              return (
                <div key={i} className="flex flex-col gap-1 rounded-md border border-border/60 p-2 text-xs">
                  <div className="flex items-start gap-2">
                    <Badge
                      variant={
                        f.disposition === "auto_approve" ? "secondary" : f.disposition === "blocked" ? "destructive" : "outline"
                      }
                      className="shrink-0"
                    >
                      {String(f.disposition)}
                    </Badge>
                    <div>
                      <span className="font-mono font-medium">{fieldPath}</span>{" "}
                      <span className="text-muted-foreground">({String(f.kind)})</span>
                      <p className="text-muted-foreground">{String(f.reason)}</p>
                      {!canPatch && filterIndex === null && f.paper_value !== undefined && f.paper_value !== null && (
                        <p className="text-muted-foreground">value: {JSON.stringify(f.paper_value)}</p>
                      )}
                    </div>
                  </div>
                  {/* §5.1 four-item human-review contract: 字段解释 */}
                  {canPatch && info?.description && (
                    <p className="pl-1 text-muted-foreground">ℹ {info.description}</p>
                  )}
                  {/* §5.1: source -- the field's own evidence citations */}
                  {evidence.length > 0 && (
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
                  {!canPatch && f.kind === "incomplete" && (
                    <div className="flex items-center gap-2 pl-1">
                      <p className="text-muted-foreground">
                        Add the cited restriction as a universe filter, then re-run review. Do not treat the
                        description alone as an executable screen.
                      </p>
                      <Input
                        className="h-7 w-56 text-[11px]"
                        placeholder="reason for the new filter (recorded as evidence)"
                        value={addFilterReason}
                        onChange={(e) => setAddFilterReason(e.target.value)}
                      />
                      <Button size="sm" variant="outline" onClick={addUniverseFilter}>
                        Add filter
                      </Button>
                    </div>
                  )}
                  {!canPatch && filterIndex !== null && (() => {
                    const draft = filterFieldDrafts[filterIndex] ?? {}
                    const paperValue = (f.paper_value ?? {}) as { concept_id?: string; op?: string; value?: unknown }
                    const opOptions = schemaFieldInfo("universe.filters.op")?.allowed_values ?? []
                    const conceptOptions = Array.from(
                      new Set(
                        (
                          ((effectivePaper as { data?: { fields?: Array<Record<string, unknown>> } } | undefined)
                            ?.data?.fields ?? []) as Array<Record<string, unknown>>
                        ).map((field) => String(field.concept_id)),
                      ),
                    )
                    return (
                      <div className="flex flex-wrap items-center gap-2 pl-1">
                        <span className="text-muted-foreground">Confirm or correct this filter:</span>
                        <Select
                          value={draft.concept_id ?? String(paperValue.concept_id ?? "")}
                          onValueChange={(v) =>
                            setFilterFieldDrafts((prev) => ({ ...prev, [filterIndex]: { ...prev[filterIndex], concept_id: v } }))
                          }
                        >
                          <SelectTrigger className="h-7 w-44 text-xs">
                            <SelectValue placeholder="concept_id" />
                          </SelectTrigger>
                          <SelectContent>
                            {conceptOptions.map((c) => (
                              <SelectItem key={c} value={c}>
                                {c}
                              </SelectItem>
                            ))}
                            {!conceptOptions.includes(String(paperValue.concept_id ?? "")) && paperValue.concept_id ? (
                              <SelectItem value={String(paperValue.concept_id)}>{String(paperValue.concept_id)}</SelectItem>
                            ) : null}
                          </SelectContent>
                        </Select>
                        <Select
                          value={draft.op ?? String(paperValue.op ?? "")}
                          onValueChange={(v) =>
                            setFilterFieldDrafts((prev) => ({ ...prev, [filterIndex]: { ...prev[filterIndex], op: v } }))
                          }
                        >
                          <SelectTrigger className="h-7 w-36 text-xs">
                            <SelectValue placeholder="op" />
                          </SelectTrigger>
                          <SelectContent>
                            {opOptions.map((op) => (
                              <SelectItem key={op} value={op}>
                                {op}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Input
                          className="h-7 w-56 font-mono text-[11px]"
                          placeholder={`current: ${JSON.stringify(paperValue.value)} (JSON, e.g. [1,2] or [[1,3999],[5000,5999]])`}
                          value={draft.value ?? ""}
                          onChange={(e) =>
                            setFilterFieldDrafts((prev) => ({ ...prev, [filterIndex]: { ...prev[filterIndex], value: e.target.value } }))
                          }
                        />
                        <Input
                          className="h-7 w-56 text-[11px]"
                          placeholder="reason for this edit/removal (recorded as evidence)"
                          value={filterReasonDrafts[filterIndex] ?? ""}
                          onChange={(e) => setFilterReasonDrafts((prev) => ({ ...prev, [filterIndex]: e.target.value }))}
                        />
                        <Button size="sm" variant="ghost" onClick={() => removeUniverseFilter(filterIndex)}>
                          Remove
                        </Button>
                      </div>
                    )
                  })()}
                  {!canPatch && filterIndex !== null && (() => {
                    const currentFilter = (
                      (
                        ((effectivePaper as { universe?: { filters?: Array<Record<string, unknown>> } } | undefined)
                          ?.universe?.filters ?? []) as Array<Record<string, unknown>>
                      )[filterIndex] ?? {}
                    ) as Record<string, unknown>
                    // Staged decision (if any) overrides the last-committed value for
                    // display -- clicking a button here only stages a draft (see
                    // `filterStatusDrafts`' comment); nothing commits until the single
                    // "Apply N correction(s)" button below runs.
                    const draft = filterStatusDrafts[filterIndex]
                    const isPending = draft !== undefined
                    const effectiveUnapplied =
                      draft?.action === "mark_unapplied" ? true
                      : draft?.action === "undo_unapplied" ? false
                      : Boolean(currentFilter.accepted_unapplied)
                    const effectiveUnappliedReason =
                      draft?.action === "mark_unapplied" ? draft.reason : String(currentFilter.unapplied_reason ?? "")
                    const effectiveApplied =
                      draft?.action === "mark_applied" ? true
                      : draft?.action === "undo_applied" ? false
                      : Boolean(currentFilter.human_confirmed_applied)
                    const effectiveAppliedReason =
                      draft?.action === "mark_applied" ? draft.reason : String(currentFilter.applied_reason ?? "")
                    return (
                      <div className="flex flex-col gap-1 pl-1">
                        {effectiveUnapplied ? (
                          <div className="flex items-center gap-2 border-t border-border/40 pt-1">
                            <Badge variant={isPending ? "secondary" : "outline"}>
                              {isPending ? "accepted_unapplied (pending)" : "accepted_unapplied"}
                            </Badge>
                            <span className="text-muted-foreground">{effectiveUnappliedReason}</span>
                            <Button size="sm" variant="ghost" onClick={() => undoAcceptedUnapplied(filterIndex)}>
                              Undo
                            </Button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 border-t border-border/40 pt-1">
                            <Input
                              className="h-7 text-[11px]"
                              placeholder="Reason this filter is accepted as unapplied (e.g. engine can't join non-CRSP columns yet)"
                              value={unappliedReasonDrafts[filterIndex] ?? ""}
                              onChange={(e) => setUnappliedReasonDrafts((prev) => ({ ...prev, [filterIndex]: e.target.value }))}
                            />
                            <Button size="sm" variant="outline" onClick={() => applyAcceptedUnapplied(filterIndex)}>
                              Mark accepted_unapplied
                            </Button>
                          </div>
                        )}
                        {effectiveApplied ? (
                          <div className="flex items-center gap-2 border-t border-border/40 pt-1">
                            <Badge variant={isPending ? "secondary" : "outline"}>
                              {isPending ? "human_confirmed_applied (pending)" : "human_confirmed_applied"}
                            </Badge>
                            <span className="text-muted-foreground">{effectiveAppliedReason}</span>
                            <Button size="sm" variant="ghost" onClick={() => undoHumanConfirmedApplied(filterIndex)}>
                              Undo
                            </Button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 border-t border-border/40 pt-1">
                            <Input
                              className="h-7 text-[11px]"
                              placeholder="Reason this filter is confirmed to apply (e.g. reviewed the inferred evidence, it's correct)"
                              value={appliedReasonDrafts[filterIndex] ?? ""}
                              onChange={(e) => setAppliedReasonDrafts((prev) => ({ ...prev, [filterIndex]: e.target.value }))}
                            />
                            <Button size="sm" variant="outline" onClick={() => applyHumanConfirmedApplied(filterIndex)}>
                              Approve & Apply
                            </Button>
                          </div>
                        )}
                        {isPending && (
                          <p className="text-muted-foreground">
                            Staged -- click "Apply N correction(s)" below to commit (this and every other pending
                            decision on this page apply together, in one step).
                          </p>
                        )}
                        {unappliedError && <p className="text-destructive">{unappliedError}</p>}
                        {appliedError && <p className="text-destructive">{appliedError}</p>}
                      </div>
                    )
                  })()}
                  {filterFieldError && filterIndex !== null && (
                    <p className="pl-1 text-destructive">{filterFieldError}</p>
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
                            {/* Enum fields (e.g. weighting) already list their own "other"
                                member above -- only add this free-text escape hatch for
                                fields whose `allowedValues` is a non-exhaustive suggestion
                                list (e.g. source_column), to avoid two overlapping "other"
                                entries in the same dropdown. */}
                            {!allowedValues.includes("other") && (
                              <SelectItem value="__other__">Other (type my own)</SelectItem>
                            )}
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
                  {canPatch && valuePatchDrafts[fieldPath] === "other" && (
                    <div className="flex items-center gap-2 pl-1">
                      <span className="text-muted-foreground">Paper's original wording (unsupported_value):</span>
                      <Input
                        className="h-7 w-56 text-xs"
                        placeholder="e.g. the paper's literal phrase for this choice"
                        value={unsupportedValueDrafts[fieldPath] ?? ""}
                        onChange={(e) =>
                          setUnsupportedValueDrafts((prev) => ({ ...prev, [fieldPath]: e.target.value }))
                        }
                      />
                    </div>
                  )}
                </div>
              )
            })}
            {(() => {
              const pendingCount =
                Object.keys(valuePatchDrafts).length +
                Object.keys(filterFieldDrafts).length +
                Object.keys(filterStatusDrafts).length +
                Object.keys(derivationDrafts).length +
                (stagedPaperOverride !== undefined ? 1 : 0)
              return (
                pendingCount > 0 && (
                  <Button size="sm" variant="outline" disabled={patchValueMutation.isPending} onClick={applyPendingCorrections}>
                    {patchValueMutation.isPending ? "Patching…" : `Apply ${pendingCount} correction(s) -- re-run review after`}
                  </Button>
                )
              )
            })()}
            <p className="text-xs text-muted-foreground">
              Every high-impact field above can be corrected this way, regardless of its disposition --
              "missing_mapping" findings are the only exception (fix `data.fields`/`universe.filters` and
              re-extract instead). Every decision above (value corrections, filter add/remove/edit,
              accepted_unapplied/human_confirmed_applied, sort edits, derivations) is staged, not applied
              immediately -- nothing changes `state.paper` or clears the current review until you click
              "Apply N correction(s)"; that one click commits everything pending at once, then clears the
              review (re-run review afterward). Corrections are recorded as an evidence citation (or a
              `notes` line for a removal).
            </p>
          </div>
        )}
      </div>

      {rangeUnionSuggestions.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md border border-amber-500/50 bg-amber-500/5 p-3 text-sm">
          <p className="font-medium">Universe range union needs correction</p>
          <p className="text-xs text-muted-foreground">
            <code>in</code> accepts a flat list of values, not nested intervals; separate filters are also combined
            with AND. Converting replaces the interval set with one <code>intervals</code> predicate; re-run review
            afterward.
          </p>
          {rangeUnionSuggestions.map((suggestion) => (
            <div key={suggestion.conceptId} className="flex flex-wrap items-center gap-2 text-xs">
              <code>{suggestion.conceptId}</code>
              <span>{suggestion.ranges.map(([low, high]) => `${low}–${high}`).join(" OR ")}</span>
              <Button size="sm" variant="outline" onClick={() => convertToRangeUnion(suggestion)}>
                Convert to intervals
              </Button>
            </div>
          ))}
        </div>
      )}

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
              {(resolveMutation.data.resolution_findings ?? []).map((f, i) => (
                <div key={`resolution-${i}`} className="flex items-start gap-2">
                  <Badge variant="destructive" className="shrink-0">
                    {String(f.kind)}
                  </Badge>
                  <div>
                    <span className="font-mono font-medium">{String(f.field_path)}</span>
                    <p className="text-muted-foreground">{String(f.reason)}</p>
                  </div>
                </div>
              ))}
              <p className="text-muted-foreground">
                Note: D4 (engine-capability blocking) was removed 2026-08-10 -- an out-of-menu choice
                (weighting/construction_type/breakpoints.basis/missing_policies) is now recorded as
                `SourcedValue.unsupported_value` and clamped to an engine default, not blocked here. What
                remains blocking at this point is a `missing_mapping` finding you haven't resolved yet, an
                unmapped concept, or an unsupported universe filter above -- fix the paper's `data.fields`/
                `universe.filters` and re-extract, or pick a value correction in the review panel above.
              </p>
            </div>
          )}
          {/* Filter editor (derivation / accepted_unapplied / human_confirmed_applied) is
              deliberately NOT gated on `!is_ready`: an `accepted_unapplied` filter is designed
              to not block readiness, so gating this under the "not ready" block above made the
              accepted_unapplied/human_confirmed_applied controls unreachable for exactly the
              filters they exist to handle. Only requires that a resolve attempt has happened. */}
          {resolveMutation.data && (
              <div className="flex flex-col gap-2 rounded-md border border-border/60 bg-background p-2">
                <p className="font-medium">
                  Or: register a `derivation` (a `FormulaSpec`) on the filter instead of a direct column
                  mapping -- for a concept that's really computed from other columns (e.g. "listed at least
                  2 years") rather than a raw physical column. Paste/edit the raw JSON below, then re-run
                  resolve.
                </p>
                {(
                  ((effectivePaper as { universe?: { filters?: Array<Record<string, unknown>> } } | undefined)
                    ?.universe?.filters ?? []) as Array<Record<string, unknown>>
                ).map((filt, i) => (
                  <div key={i} className="flex flex-col gap-1 rounded border border-border/60 p-2">
                    <span className="font-mono font-medium">{String(filt.concept_id)}</span>
                    {filt.derivation ? (
                      <JsonTree name="current derivation" data={filt.derivation} />
                    ) : (
                      <span className="text-muted-foreground">no derivation set</span>
                    )}
                    <Textarea
                      className="h-24 font-mono text-[11px]"
                      placeholder='FormulaSpec JSON, e.g. {"paper_expression": "listed >= 2 years", "inputs": ["compustat_listing_history"], "steps": [], "output_concept": "..."} -- leave blank to clear'
                      value={derivationDrafts[i] ?? ""}
                      onChange={(e) => setDerivationDrafts((prev) => ({ ...prev, [i]: e.target.value }))}
                    />
                    {/* accepted_unapplied/human_confirmed_applied now live in the review
                        panel above, right next to each filter's own finding -- available
                        as soon as review runs, not gated behind a resolve attempt. */}
                  </div>
                ))}
                {derivationError && <p className="text-destructive">{derivationError}</p>}
                {Object.keys(derivationDrafts).length > 0 && (
                  <p className="text-muted-foreground">
                    Staged -- click "Apply N correction(s)" in the review panel above to commit this
                    alongside every other pending decision on this page, in one step.
                  </p>
                )}
              </div>
          )}
          {state.resolved && (
            <>
              <p className="text-xs font-medium">
                Resolved MethodSpec — check the highlighted Portfolio (config) and Reported results sections
                before moving on.
              </p>
              {/* `state.resolved` is a `ResolvedMethodSpec` (`{paper, review, resolution}`,
                  see backend/routers/methodspecs.py's `resolve()`) -- `MethodSpecBoard`
                  renders a flat `MethodSpec`, which is the `.paper` field here, not the
                  wrapper itself (passing the wrapper renders every section blank since
                  `spec.signal`/`spec.portfolio`/etc. don't exist at that level). */}
              <MethodSpecBoard spec={(state.resolved as { paper?: Record<string, unknown> }).paper ?? state.resolved} highlightConfigAndResults />
              <Button size="sm" onClick={() => navigate(`/runs/${sessionId}/step/3`)}>
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

/** Steps 3/4/5's request bodies are just refs/hashes into upstream
 * artifacts (a resolved spec + generated plugin, or a script hash) --
 * showing that as a raw JSON textarea always led to the whole MethodSpec
 * getting dumped on screen (step3's `spec` field). Renders the same
 * fields as plain label/value pairs instead; bulky object fields (`spec`,
 * `plugin`) collapse to a "loaded" indicator since their own dedicated
 * views (MethodSpecPicker's plugin code, the Step output card) already
 * show the real content. */
function RequestFieldsSummary({ requestText }: { requestText: string }) {
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(requestText)
  } catch {
    return <p className="text-xs text-destructive">Request body is not valid JSON.</p>
  }
  const entries = Object.entries(parsed).filter(([key]) => key !== "expected_revision")
  if (entries.length === 0) return null
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-2 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2">
          <span className="font-mono text-muted-foreground">{key}:</span>
          <span className="font-mono">
            {value && typeof value === "object"
              ? Object.keys(value as object).length > 0
                ? "loaded"
                : "—"
              : typeof value === "string" && value.length > 16
                ? `${value.slice(0, 12)}…`
                : String(value ?? "—")}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Step3 helper: pick an already-REVIEWED MethodSpec (the existing
 * `/api/methodspecs/resolved` list -- unrelated to session state) and
 * generate a plugin for it on the spot via the existing `/api/codegen`
 * job, instead of hand-pasting both JSON blobs. */
function MethodSpecPicker({
  defaultFactorId,
  onSpecPluginReady,
}: {
  defaultFactorId?: string
  onSpecPluginReady: (spec: Record<string, unknown>, plugin: Record<string, unknown>) => void
}) {
  const [factorId, setFactorId] = useState<string | null>(() => defaultFactorId ?? null)
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
      {defaultFactorId && (
        <p className="text-xs text-muted-foreground">
          Pre-filled with this session's own Step2-resolved spec ({defaultFactorId}) -- change it below to load
          a different one instead.
        </p>
      )}
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

interface CzConfigPreview {
  acronym: string
  raw: Record<string, unknown>
  config_override: Record<string, unknown>
  cz_reported: { mean_return: number | null; t_stat: number | null; sign: number | null }
}

interface ResolvedConfigsPreview {
  original_method: Record<string, unknown>
  standardized_hxz: Record<string, unknown>
}

function formatCzValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** One track's resolved-config diff in the step6 pre-run preview -- the
 * SAME `resolved_diff` shape the Result/comparison panel otherwise only
 * shows once the batch has actually finished, surfaced here BEFORE running
 * anything (per-track `preview_tracks`, no execution). The baseline track
 * (`original_method`) has an empty diff by construction (it IS the
 * baseline), shown as a plain label instead of an empty table. */
function Step6PreviewTrackCard({ track }: { track: Step6PreviewTrack }) {
  const diffKeys = Object.keys(track.resolved_diff).sort()
  return (
    <div className="rounded-md border border-border p-2 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-mono font-medium">{track.name}</span>
        {track.family !== "baseline" && (
          <>
            <Badge variant="outline">{track.family}</Badge>
            <Badge variant="outline">{track.identification_level}</Badge>
          </>
        )}
      </div>
      {diffKeys.length === 0 ? (
        <p className="mt-1 text-muted-foreground">
          {track.family === "baseline" ? "Baseline -- nothing to diff." : "No config difference from baseline."}
        </p>
      ) : (
        <table className="mt-1 w-full border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-1 pr-3 text-left font-medium">Config key</th>
              <th className="py-1 pr-3 text-left font-medium">Baseline value</th>
              <th className="py-1 text-left font-medium">This track's value</th>
            </tr>
          </thead>
          <tbody>
            {diffKeys.map((key) => (
              <tr key={key} className="border-b border-border/50">
                <td className="py-1 pr-3 font-mono">{key}</td>
                <td className="py-1 pr-3 text-muted-foreground">{formatCzValue(track.resolved_diff[key].baseline_value)}</td>
                <td className="py-1">{formatCzValue(track.resolved_diff[key].track_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

/** The ①②③ resolved-config comparison itself, extracted so it can be
 * rendered in BOTH the request card (right after querying ②, unchanged)
 * AND the Result panel -- the latter shows it the INSTANT "Run" is
 * clicked, since every value here is already known client-side and
 * doesn't need the batch to actually finish executing. */
function Step6ConfigDiffTable({
  original,
  cz,
  std,
}: {
  original: Record<string, unknown> | undefined
  cz: Record<string, unknown> | undefined
  std: Record<string, unknown> | undefined
}) {
  const configKeys = Array.from(
    new Set([...Object.keys(original ?? {}), ...Object.keys(cz ?? {}), ...Object.keys(std ?? {})]),
  ).sort()
  if (configKeys.length === 0) return null
  return (
    <div>
      <p className="font-medium">①②③ resolved config, side by side (before running anything)</p>
      <div className="max-h-72 overflow-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-1 pr-3 text-left font-medium">Config key</th>
              <th className="py-1 pr-3 text-left font-medium">① Paper's setup</th>
              <th className="py-1 pr-3 text-left font-medium">② C&amp;Z's config</th>
              <th className="py-1 text-left font-medium">③ Standardized</th>
            </tr>
          </thead>
          <tbody>
            {configKeys.map((key) => {
              const originalValue = original?.[key]
              const czValue = cz?.[key]
              const stdValue = std?.[key]
              return (
                <tr key={key} className="border-b border-border/50 last:border-0">
                  <td className="py-1 pr-3 font-mono text-muted-foreground">{key}</td>
                  <td className="py-1 pr-3 font-mono">{formatCzValue(originalValue)}</td>
                  <td
                    className={cn(
                      "py-1 pr-3 font-mono",
                      cz &&
                        key in cz &&
                        formatCzValue(czValue) !== formatCzValue(originalValue) &&
                        "bg-amber-50 dark:bg-amber-950/20",
                    )}
                  >
                    {cz && key in cz ? formatCzValue(czValue) : "—"}
                  </td>
                  <td
                    className={cn(
                      "py-1 font-mono",
                      formatCzValue(stdValue) !== formatCzValue(originalValue) && "bg-amber-50 dark:bg-amber-950/20",
                    )}
                  >
                    {formatCzValue(stdValue)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Step6 request editor helper (docs/step6.md gap #1): look up C&Z's own
 * reported implementation choices for a factor (`GET /steps/6/cz-config`,
 * a live `openassetpricing` call -- never triggers a backtest) and preview
 * the resulting config for human review BEFORE it's confirmed as the
 * `cz_config_override` field on the step6 request, which becomes its own
 * "cz_actual_config" track (\u2461) alongside \u2460/\u2462. The dropdown lists every
 * factor in the manifest regardless of which paper this session is
 * replicating -- deliberately not auto-restricted, but mismatches are
 * flagged since running an unrelated factor's C&Z config against this
 * session's plugin isn't meaningful.
 *
 * Once \u2461 is queried, ALSO fetches \u2460/\u2462's resolved config straight from
 * `spec` (`POST /steps/6/resolved-configs`, no run needed) so all three
 * configs are visible side by side before anything is actually run --
 * a resolved-configs fetch failure (e.g. `spec` not filled in yet) only
 * drops that one table, it never blocks showing \u2461's own preview above. */
function Step6CzConfigPreview({
  sessionId,
  sessionFactorId,
  spec,
  confirmedOverride,
  onConfirm,
  onDataChange,
}: {
  sessionId: string
  sessionFactorId: string | undefined
  spec: Record<string, unknown> | undefined
  confirmedOverride: Record<string, unknown> | undefined
  onConfirm: (override: Record<string, unknown> | undefined) => void
  onDataChange: (
    data: {
      original: Record<string, unknown>
      cz: Record<string, unknown>
      std: Record<string, unknown>
      raw: Record<string, unknown>
      czReported: { mean_return: number | null; t_stat: number | null }
    } | null,
  ) => void
}) {
  const factorsQuery = useQuery({
    queryKey: ["cz-factors"],
    queryFn: () => api.get<{ factors: { factor_id: string; acronym: string }[] }>("/api/reference/cz-factors"),
  })
  // Initialized from `step6PreviewStore` (localStorage) so a page reload
  // shows the last query's dropdown selection and result instead of
  // resetting to "never queried" -- this endpoint is a live network call
  // (`openassetpricing`), not something worth re-fetching just because the
  // tab was reloaded.
  const cached = getStep6PreviewState(sessionId)
  const [selected, setSelected] = useState(cached.czSelected ?? "")
  const [preview, setPreview] = useState<CzConfigPreview | null>(cached.czPreview ?? null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const factors = factorsQuery.data?.factors ?? []
  const selectedFactor = factors.find((f) => f.acronym === selected)
  const mismatch = selectedFactor !== undefined && selectedFactor.factor_id !== sessionFactorId

  async function handleQuery() {
    setLoading(true)
    setError(null)
    setPreview(null)
    onDataChange(null)
    try {
      const specFactorId = (spec as { paper?: { factor_id?: string } } | undefined)?.paper?.factor_id
      const czConfigParams = new URLSearchParams({ acronym: selected })
      if (specFactorId) czConfigParams.set("factor_id", specFactorId)
      const result = await api.get<CzConfigPreview>(
        `/api/sessions/${sessionId}/steps/6/cz-config?${czConfigParams.toString()}`,
      )
      setPreview(result)
      setStep6PreviewState(sessionId, { czSelected: selected, czPreview: result })
      let resolved: ResolvedConfigsPreview | null = null
      if (spec && Object.keys(spec).length > 0) {
        try {
          resolved = await api.post<ResolvedConfigsPreview>(
            `/api/sessions/${sessionId}/steps/6/resolved-configs`,
            { spec },
          )
        } catch {
          // \u2461's own preview above still shows -- the \u2460\u2461\u2462 side-by-side table
          // just won't, e.g. if `spec` isn't filled in on this request yet.
        }
      }
      if (resolved) {
        onDataChange({
          original: resolved.original_method,
          cz: result.config_override,
          std: resolved.standardized_hxz,
          raw: result.raw,
          czReported: result.cz_reported,
        })
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-xs">
      <div>
        <p className="font-medium">Run against C&amp;Z's actual configuration</p>
        <p className="text-muted-foreground">
          Looks up C&amp;Z's own reported implementation choices for a factor and previews the resulting config --
          confirm below to add it as its own run, alongside the paper's setup and the standardized setup.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Select
          value={selected}
          onValueChange={(v) => {
            setSelected(v)
            setPreview(null)
            setError(null)
            onDataChange(null)
            setStep6PreviewState(sessionId, { czSelected: v, czPreview: undefined, configDiff: undefined })
          }}
        >
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Choose a factor" />
          </SelectTrigger>
          <SelectContent>
            {factors.map((f) => (
              <SelectItem key={f.acronym} value={f.acronym}>
                {f.acronym}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="sm" disabled={!selected || loading} onClick={handleQuery}>
          {loading ? "Querying…" : "Query C&Z config"}
        </Button>
      </div>
      {mismatch && (
        <p className="text-amber-600">
          Note: "{selectedFactor?.factor_id}" is not the factor this session is replicating ("{sessionFactorId}") --
          running its C&amp;Z config against this session's plugin won't be a meaningful comparison.
        </p>
      )}
      {error && <p className="text-destructive">Query failed: {error}</p>}
      {preview && (
        <div className="flex flex-col gap-2 rounded border border-border p-2">
          <p className="text-muted-foreground">
            Queried "{preview.acronym}" -- see the config diff and C&amp;Z's reported performance in the Result
            panel.
          </p>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={confirmedOverride !== undefined}
              onChange={(e) => onConfirm(e.target.checked ? preview.config_override : undefined)}
            />
            Confirmed -- include this as its own run when I run the experiment
          </label>
        </div>
      )}
    </div>
  )
}

interface HxzReportedPreview {
  mean_return: number | null
  t_stat: number | null
  n_months: number | null
  start_year: number | null
  end_year: number | null
  label: string
}

/** HXZ's reported/reference number for the ③ (`standardized_hxz`) row's
 * "Reported (reference)" column (docs/step6.md's `N_hxz` gap). It is usually
 * recomputed from a downloaded HXZ testing-portfolio CSV, but a deliberately
 * labelled manual reference can be shown when no such CSV exists. This is not
 * a live network call like C&Z's. The C&Z manifest supplies the shared
 * factor-id/acronym dropdown. */
function Step6HxzConfigPreview({
  sessionId,
  sessionFactorId,
  specFactorId,
  sampleWindow,
  onDataChange,
}: {
  sessionId: string
  sessionFactorId: string | undefined
  specFactorId: string | undefined
  sampleWindow: { startYear: number; endYear: number } | null
  onDataChange: (data: { originalInsample: HxzReportedPreview | null; hxzPaperSample: HxzReportedPreview | null } | null) => void
}) {
  const factorsQuery = useQuery({
    queryKey: ["cz-factors"],
    queryFn: () => api.get<{ factors: { factor_id: string; acronym: string }[] }>("/api/reference/cz-factors"),
  })
  // Same reload-survival reasoning as Step6CzConfigPreview above.
  const cached = getStep6PreviewState(sessionId)
  const [selected, setSelected] = useState(cached.hxzSelected ?? "")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [queriedAcronym, setQueriedAcronym] = useState<string | null>(cached.hxzPreview?.acronym ?? null)

  const factors = factorsQuery.data?.factors ?? []
  const selectedFactor = factors.find((f) => f.acronym === selected)
  const mismatch = selectedFactor !== undefined && selectedFactor.factor_id !== sessionFactorId

  async function handleQuery() {
    setLoading(true)
    setError(null)
    onDataChange(null)
    setQueriedAcronym(null)
    try {
      const params = new URLSearchParams({ acronym: selected })
      if (sampleWindow) {
        params.set("sample_start_year", String(sampleWindow.startYear))
        params.set("sample_end_year", String(sampleWindow.endYear))
      }
      if (specFactorId) params.set("factor_id", specFactorId)
      const result = await api.get<{
        acronym: string
        original_insample: HxzReportedPreview | null
        hxz_paper_sample: HxzReportedPreview | null
      }>(`/api/sessions/${sessionId}/steps/6/hxz-config?${params.toString()}`)
      onDataChange({ originalInsample: result.original_insample, hxzPaperSample: result.hxz_paper_sample })
      setQueriedAcronym(result.acronym)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-xs">
      <div>
        <p className="font-medium">Look up HXZ's own reported result</p>
        <p className="text-muted-foreground">
          Uses a downloaded HXZ testing-portfolio decile file when available, otherwise a clearly labelled manual
          reference (not a live call) -- reference only for the ③ row, never run as its own track. Uses this
          factor's OWN paper sample window (
          {sampleWindow ? `${sampleWindow.startYear}–${sampleWindow.endYear}` : "full range -- spec has no sample window yet"}
          ), the same basis ①'s reference number is on.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Select
          value={selected}
          onValueChange={(v) => {
            setSelected(v)
            setError(null)
            onDataChange(null)
            setQueriedAcronym(null)
            setStep6PreviewState(sessionId, { hxzSelected: v, hxzPreview: undefined })
          }}
        >
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Choose a factor" />
          </SelectTrigger>
          <SelectContent>
            {factors.map((f) => (
              <SelectItem key={f.acronym} value={f.acronym}>
                {f.acronym}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="sm" disabled={!selected || loading} onClick={handleQuery}>
          {loading ? "Querying…" : "Query HXZ reference"}
        </Button>
      </div>
      {mismatch && (
        <p className="text-amber-600">
          Note: "{selectedFactor?.factor_id}" is not the factor this session is replicating ("{sessionFactorId}").
        </p>
      )}
      {error && <p className="text-destructive">Query failed: {error}</p>}
      {queriedAcronym && <p className="text-muted-foreground">Queried "{queriedAcronym}" -- see the Result panel.</p>}
    </div>
  )
}

/** Step6 request editor helper: picks which of the three ①②③ setups to run,
 * each labeled with where its config actually comes from. ② has no
 * `run_*` field of its own -- checking it only enables the C&Z config
 * section below (`Step6CzConfigPreview`); ② only actually runs once a
 * config has ALSO been queried and confirmed there. Per-field ablation/
 * factorial switches were removed from this UI (2026-08-16) -- this
 * three-track comparison is now the whole "which versions to run" model. */
function Step6VersionsPicker({
  runOriginal,
  runStandardized,
  czEnabled,
  autoAttribution,
  onChange,
  onToggleCz,
}: {
  runOriginal: boolean
  runStandardized: boolean
  czEnabled: boolean
  autoAttribution: boolean
  onChange: (patch: Record<string, unknown>) => void
  onToggleCz: (enabled: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-3 text-xs">
      <p className="font-medium">Which versions to run</p>
      <label className="mt-1 flex items-center gap-1.5">
        <input type="checkbox" checked={runOriginal} onChange={(e) => onChange({ run_original: e.target.checked })} />
        ① Paper's original setup{" "}
        <span className="text-muted-foreground">(agent-extracted from the paper)</span>
      </label>
      <label className="flex items-center gap-1.5">
        <input type="checkbox" checked={czEnabled} onChange={(e) => onToggleCz(e.target.checked)} />
        ② C&amp;Z's actual configuration{" "}
        <span className="text-muted-foreground">
          (pulled from the openassetpricing library -- query &amp; confirm below)
        </span>
      </label>
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={runStandardized}
          onChange={(e) => onChange({ run_standardized: e.target.checked })}
        />
        ③ A fully standardized setup{" "}
        <span className="text-muted-foreground">
          (Hou, Xue &amp; Zhang (2020, RFS) "Replicating Anomalies" standard rules, same for every paper -- not
          from the paper)
        </span>
      </label>
      <label className="mt-1 flex items-center gap-1.5 border-t border-border pt-1.5">
        <input
          type="checkbox"
          checked={autoAttribution}
          onChange={(e) => onChange({ auto_attribution: e.target.checked })}
        />
        Auto attribution for ①→②/①→③{" "}
        <span className="text-muted-foreground">
          (finds which config fields actually differ and runs each combination -- full factorial when 5 or
          fewer fields differ (exact), one-at-a-time otherwise; adds extra{" "}
          <code className="font-mono">factorial_*</code>/<code className="font-mono">ablation_*</code>/
          <code className="font-mono">cz_factorial_*</code>/<code className="font-mono">cz_ablation_*</code>{" "}
          tracks)
        </span>
      </label>
    </div>
  )
}
