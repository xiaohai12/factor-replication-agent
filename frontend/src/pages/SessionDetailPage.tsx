import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { StepStepper } from "@/components/StepStepper"
import { JobLogPanel } from "@/components/JobLogPanel"
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
        <Button variant="outline" onClick={() => navigate("/sessions")}>
          All sessions
        </Button>
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

        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {def.isJob ? (
              <JobLogPanel job={job} />
            ) : (
              syncResult != null && (
                <pre className="h-64 overflow-auto rounded-md bg-muted p-2 text-xs">
                  {JSON.stringify(syncResult, null, 2)}
                </pre>
              )
            )}
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
