import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { JsonTree } from "@/components/JsonTree"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError } from "@/lib/api"
import { sessionApi } from "@/lib/sessionApi"

interface Finding {
  field_path?: string
  kind?: string
  reason?: string
  empirical_impact?: string
  disposition?: string
  paper_value?: unknown
}

interface ResolveState {
  resolution: Record<string, unknown>
  is_ready: boolean
  resolved: Record<string, unknown> | null
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `${error.status}: ${error.message}` : String(error)
}

/** Standalone review/resolve page over backend-persisted MethodSpec drafts.
 * It deliberately reloads artifacts from runs/method_specs rather than
 * relying on sessionStorage or a particular session id. */
export function ReviewResolvePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const factorId = searchParams.get("factor_id") ?? ""
  const [review, setReview] = useState<Record<string, unknown> | null>(null)
  const [resolveState, setResolveState] = useState<ResolveState | null>(null)
  const [error, setError] = useState<string | null>(null)

  const draftsQuery = useQuery({
    queryKey: ["methodspecs", "drafts"],
    queryFn: () => sessionApi.listMethodSpecs("drafts"),
  })
  const reviewsQuery = useQuery({
    queryKey: ["methodspecs", "reviews"],
    queryFn: () => sessionApi.listMethodSpecs("reviews"),
  })
  const specQuery = useQuery({
    queryKey: ["methodspec", "drafts", factorId],
    queryFn: () => sessionApi.getMethodSpec("drafts", factorId),
    enabled: Boolean(factorId),
  })
  const savedReviewQuery = useQuery({
    queryKey: ["methodspec", "reviews", factorId],
    queryFn: () => sessionApi.getMethodSpec("reviews", factorId),
    enabled: Boolean(factorId) && (reviewsQuery.data?.includes(factorId) ?? false),
  })

  useEffect(() => {
    setReview(null)
    setResolveState(null)
    setError(null)
  }, [factorId])

  useEffect(() => {
    if (savedReviewQuery.data) setReview(savedReviewQuery.data)
  }, [savedReviewQuery.data])

  const reviewMutation = useMutation({
    mutationFn: () => sessionApi.reviewPaperSpec(specQuery.data!),
    onSuccess: (result) => {
      setReview(result)
      setResolveState(null)
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["methodspecs", "reviews"] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const resolveMutation = useMutation({
    mutationFn: async (): Promise<ResolveState> => {
      const result = await sessionApi.resolvePaperSpec(specQuery.data!, review!)
      const resolved = result.is_ready ? await sessionApi.getResolvedMethodSpec(factorId) : null
      return { ...result, resolved }
    },
    onSuccess: (result) => {
      setResolveState(result)
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["methodspecs", "resolutions"] })
      queryClient.invalidateQueries({ queryKey: ["methodspecs", "resolved"] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const findings = ((review?.findings as Finding[] | undefined) ?? [])
  const blocked = findings.filter((finding) => finding.disposition === "blocked")
  const drafts = draftsQuery.data ?? []

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <div>
        <h2 className="text-2xl font-semibold">Review & Resolve</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Review a persisted MethodSpec draft, surface unsupported or ambiguous choices, then resolve physical
          data mappings before code generation.
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>1. Select a draft</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Select
            value={factorId || undefined}
            onValueChange={(value) => setSearchParams({ factor_id: value })}
          >
            <SelectTrigger><SelectValue placeholder="Choose an extracted MethodSpec" /></SelectTrigger>
            <SelectContent>
              {drafts.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
            </SelectContent>
          </Select>
          {draftsQuery.isSuccess && drafts.length === 0 && (
            <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
              No extracted drafts exist yet. <Button variant="link" onClick={() => navigate("/extract")}>Open Extractor</Button>
            </div>
          )}
          {specQuery.isError && <p className="text-sm text-destructive">Could not load draft: {errorMessage(specQuery.error)}</p>}
        </CardContent>
      </Card>

      {specQuery.data && (
        <Card>
          <CardHeader><CardTitle>2. Inspect and review</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-4">
            <MethodSpecBoard spec={specQuery.data} />
            <Button disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate()}>
              {reviewMutation.isPending ? "Reviewing…" : review ? "Re-run deterministic review" : "Run deterministic review"}
            </Button>

            {review && (
              <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={blocked.length > 0 ? "destructive" : "default"}>
                    {blocked.length > 0 ? `${blocked.length} blocked` : "not blocked"}
                  </Badge>
                  <Badge variant="outline">{findings.length} finding(s)</Badge>
                  <span className="font-mono text-xs text-muted-foreground">
                    capability {String(review.capability_version ?? "—")}
                  </span>
                </div>
                {findings.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No review findings.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {findings.map((finding, index) => (
                      <div key={`${finding.field_path}-${index}`} className="rounded-md bg-muted/50 p-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-medium">{finding.field_path || "unknown field"}</span>
                          <Badge variant={finding.disposition === "blocked" ? "destructive" : "outline"}>
                            {finding.disposition || "finding"}
                          </Badge>
                          <Badge variant="outline">{finding.kind || "unknown"}</Badge>
                          <span className="text-xs text-muted-foreground">impact: {finding.empirical_impact || "—"}</span>
                        </div>
                        {finding.reason && <p className="mt-2 text-xs text-muted-foreground">{finding.reason}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {review && specQuery.data && (
        <Card>
          <CardHeader><CardTitle>3. Resolve implementation mappings</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-4">
            {blocked.length > 0 && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                The review has blocked findings. Resolve still writes a diagnostic resolution artifact, but the MethodSpec
                will not become codegen-ready until those findings are corrected or explicitly supported.
              </p>
            )}
            <Button disabled={resolveMutation.isPending} onClick={() => resolveMutation.mutate()}>
              {resolveMutation.isPending ? "Resolving…" : "Build implementation resolution"}
            </Button>
            {resolveState && (
              <>
                <Badge variant={resolveState.is_ready ? "default" : "destructive"} className="w-fit">
                  codegen ready: {resolveState.is_ready ? "yes" : "no"}
                </Badge>
                <JsonTree name="implementation_resolution" data={resolveState.resolution} />
                {resolveState.resolved && <JsonTree name="resolved_methodspec" data={resolveState.resolved} />}
                {resolveState.is_ready && (
                  <Button onClick={() => navigate("/sessions")}>
                    Continue in a session from Step 3
                  </Button>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}
