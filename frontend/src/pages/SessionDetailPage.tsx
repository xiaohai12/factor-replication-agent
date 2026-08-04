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

  useEffect(() => {
    const revision = sessionQuery.data?.revision ?? 0
    setRequestText(JSON.stringify({ ...def.requestTemplate, expected_revision: revision }, null, 2))
    setJobId(null)
    setSyncResult(null)
    setRequestError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, sessionId])

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
  const [provider, setProvider] = useState("codex")

  const mutation = useMutation({
    mutationFn: () => sessionApi.extractFromPdf(sessionId, file!, expectedRevision, provider),
    onSuccess: (res) => {
      onError(null)
      onJobStarted(res.job_id)
    },
    onError: (err) => onError(err instanceof ApiError ? `${err.status}: ${err.message}` : String(err)),
  })

  return (
    <div className="flex flex-col gap-3">
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="text-xs"
      />
      <Select value={provider} onValueChange={setProvider}>
        <SelectTrigger className="w-48">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="codex">codex</SelectItem>
          <SelectItem value="copilot">copilot</SelectItem>
          <SelectItem value="claude">claude</SelectItem>
          <SelectItem value="openrouter">openrouter</SelectItem>
        </SelectContent>
      </Select>
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
