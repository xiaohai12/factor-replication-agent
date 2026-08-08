import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { StepStepper } from "@/components/StepStepper"
import { JobLogPanel } from "@/components/JobLogPanel"
import { StepOutputView } from "@/components/StepOutputView"
import { sessionApi } from "@/lib/sessionApi"
import { stepDefinition } from "@/lib/steps"
import { useJobStream } from "@/lib/useJobStream"
import { ApiError } from "@/lib/api"
import { PROVIDER_MODELS, useLlm } from "@/lib/llmContext"
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
      }
    },
    onError: (err) => {
      setRequestError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
    },
  })

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
        onSelect={(s) => navigate(`/sessions/${sessionId}/steps/${s}`)}
      />

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
            {step === 1 ? (
              <PdfExtractPanel
                sessionId={sessionId}
                expectedRevision={sessionQuery.data.revision}
                onJobStarted={setJobId}
                onError={setRequestError}
              />
            ) : (
              <>
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
              </>
            )}
            {requestError && <p className="text-xs text-destructive">{requestError}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {def.isJob ? (
              <JobLogPanel job={job} />
            ) : null}
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
      </div>

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
            sessionRevision={sessionQuery.data.revision}
            onResolved={async () => {
              queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
              queryClient.invalidateQueries({ queryKey: ["session-step", sessionId, step] })
              queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
              // Resolving step2's blocked fields always resets review_status/
              // codegen_ready to pending (src/steps/step2_reviewer/resolution.py),
              // so the resolved spec must go back through Review Gate before
              // codegen is allowed. Auto-fire that re-review instead of making
              // the user click "Run" again with a manifest revision that's now
              // stale (the resolve call already bumped it).
              if (step === 2) {
                try {
                  const manifest = await sessionApi.get(sessionId)
                  const body = await buildAutoFilledRequest(sessionId, step, manifest, def.requestTemplate)
                  const response = await sessionApi.runStep(def.endpoint(sessionId), withLlmSelection(body))
                  if (typeof response.job_id === "string") {
                    setJobId(response.job_id)
                  } else {
                    setSyncResult(response)
                    queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
                    queryClient.invalidateQueries({ queryKey: ["session-step", sessionId, step] })
                    queryClient.invalidateQueries({ queryKey: ["session-events", sessionId] })
                  }
                } catch (err) {
                  setRequestError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err))
                }
              }
            }}
          />
        </CardContent>
      </Card>

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
    </div>
  )
}

/** Step1's input is fundamentally different from every other step's plain
 * JSON body (a document, not a small object) -- a dedicated PDF-upload
 * widget instead of a JSON textarea. `SemanticExtractor.extract()` accepts
 * `pdf_bytes` directly (used when the built LLM client supports native PDF
 * attachments); the backend endpoint always also extracts plain text via
 * pymupdf as the fallback (`backend/routers/sessions.py`'s
 * `extract_step1_from_pdf`). */
function PdfExtractPanel({
  sessionId,
  expectedRevision,
  onJobStarted,
  onError,
}: {
  sessionId: string
  expectedRevision: number
  onJobStarted: (jobId: string) => void
  onError: (message: string | null) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const { provider, model, setProvider, setModel } = useLlm()

  const mutation = useMutation({
    mutationFn: () => sessionApi.extractFromPdf(sessionId, file!, expectedRevision, provider, model),
    onSuccess: (res) => {
      onError(null)
      onJobStarted(res.job_id)
    },
    onError: (err) => onError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  return (
    <div className="flex flex-col gap-3">
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
      <p className="text-xs text-muted-foreground">
        Same Provider/Model picker as the sidebar (bottom-left) -- shared everywhere, not just here.
      </p>
      <Button disabled={!file || mutation.isPending} onClick={() => mutation.mutate()}>
        Extract MethodSpec from PDF
      </Button>
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
