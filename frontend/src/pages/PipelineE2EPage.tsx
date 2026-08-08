import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { JobLogPanel } from "@/components/JobLogPanel"
import { MethodSpecViewer } from "@/components/MethodSpecViewer"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { MetricsTable } from "@/components/MetricsTable"
import { ReturnChart, type ReturnRow } from "@/components/ReturnChart"
import { api } from "@/lib/api"
import { useJobStream } from "@/lib/useJobStream"
import { useLlm } from "@/lib/llmContext"
import { parseResolutionValue, splitIssuesBySeverity } from "@/lib/utils"

interface ExtractionResult {
  spec: Record<string, unknown> | null
  error: string | null
}

interface FieldReviewNote {
  field: string
  status: string
  reason: string
  current_value: unknown
  candidate_value: unknown
}

interface ReviewResult {
  disposition: string
  issues: string[]
  warnings: string[]
  blocked_fields: string[]
  field_notes: FieldReviewNote[]
}

interface PluginRecord {
  plugin_id: string
  factor_id: string
  code: string
  code_hash: string
}

interface ValidationReport {
  passed: boolean
  syntax_ok: boolean
  schema_ok: boolean
  no_future_leak: boolean
  reproducible: boolean
  executes_ok: boolean
  errors: string[]
  warnings: string[]
}

interface Snapshot {
  snapshot_id: string
}

interface BacktestJobResult {
  metrics: Record<string, unknown>
  return_series: ReturnRow[]
  script_path: string
  run_record: { run_id: string; status: string }
}

export function PipelineE2EPage() {
  const { provider, model } = useLlm()

  // Stage 1: paper + extraction
  const [factorId, setFactorId] = useState("")
  const [paperText, setPaperText] = useState("")
  const [extractJobId, setExtractJobId] = useState<string | null>(null)
  const extractJob = useJobStream<ExtractionResult>(extractJobId)
  const [spec, setSpec] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    if (extractJob.status === "completed" && extractJob.result?.spec) {
      setSpec(extractJob.result.spec)
    }
  }, [extractJob.status, extractJob.result])

  // Stage 2: review
  const [reviewResult, setReviewResult] = useState<ReviewResult | null>(null)
  const [reviewSource, setReviewSource] = useState<"rules" | "llm" | null>(null)
  const [resolutionValues, setResolutionValues] = useState<Record<string, string>>({})
  const [resolutionReasons, setResolutionReasons] = useState<Record<string, string>>({})
  const [useOtherFor, setUseOtherFor] = useState<Record<string, boolean>>({})
  const [reviewLlmJobId, setReviewLlmJobId] = useState<string | null>(null)
  const reviewLlmJob = useJobStream<{ review_result: ReviewResult; raw_llm_output: unknown }>(reviewLlmJobId)

  useEffect(() => {
    if (reviewLlmJob.status === "completed" && reviewLlmJob.result?.review_result) {
      setReviewResult(reviewLlmJob.result.review_result)
      setReviewSource("llm")
    }
  }, [reviewLlmJob.status, reviewLlmJob.result])

  const { data: fieldHelp } = useQuery({
    queryKey: ["field-help"],
    queryFn: () =>
      api.get<Record<string, { description: string; options: string[]; example: string }>>(
        "/api/methodspecs/field-help",
      ),
  })

  // Stage 3: codegen
  const [codegenJobId, setCodegenJobId] = useState<string | null>(null)
  const codegenJob = useJobStream<PluginRecord>(codegenJobId)
  const [plugin, setPlugin] = useState<PluginRecord | null>(null)

  useEffect(() => {
    if (codegenJob.status === "completed" && codegenJob.result) {
      setPlugin(codegenJob.result)
    }
  }, [codegenJob.status, codegenJob.result])

  // Stage 4: validate
  const [validation, setValidation] = useState<ValidationReport | null>(null)
  const { data: snapshots } = useQuery({
    queryKey: ["snapshots"],
    queryFn: () => api.get<Snapshot[]>("/api/backtest/snapshots"),
  })
  const [snapshotId, setSnapshotId] = useState("")
  useEffect(() => {
    if (snapshots && snapshots.length > 0 && !snapshotId) setSnapshotId(snapshots[0].snapshot_id)
  }, [snapshots, snapshotId])

  // Stage 5: backtest
  const [backtestJobId, setBacktestJobId] = useState<string | null>(null)
  const backtestJob = useJobStream<BacktestJobResult>(backtestJobId)

  const [error, setError] = useState<string | null>(null)

  async function handleExtract() {
    setError(null)
    if (!factorId.trim() || !paperText.trim()) {
      setError("Enter a factor id and paste the paper text.")
      return
    }
    try {
      const { job_id } = await api.post<{ job_id: string }>("/api/methodspecs/extract", {
        factor_id: factorId,
        paper_text: paperText,
        llm_provider: provider,
        llm_model: model,
      })
      setExtractJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const [pdfFile, setPdfFile] = useState<File | null>(null)

  async function handleExtractFromPdf() {
    setError(null)
    if (!factorId.trim() || !pdfFile) {
      setError("Enter a factor id and choose a PDF file.")
      return
    }
    try {
      const form = new FormData()
      form.append("factor_id", factorId)
      form.append("llm_provider", provider)
      if (model) form.append("llm_model", model)
      form.append("file", pdfFile)
      const res = await fetch("/api/methodspecs/extract-pdf", { method: "POST", body: form })
      if (!res.ok) throw new Error(await res.text())
      const { job_id } = (await res.json()) as { job_id: string }
      setExtractJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleReview() {
    if (!spec) return
    setError(null)
    try {
      const result = await api.post<ReviewResult>("/api/methodspecs/review", { spec })
      setReviewResult(result)
      setReviewSource("rules")
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleReviewLlm() {
    if (!spec) return
    setError(null)
    if (!paperText.trim()) {
      setError("LLM-backed review needs the source paper text (paste it in stage 1, even if you extracted from a PDF).")
      return
    }
    try {
      const { job_id } = await api.post<{ job_id: string }>("/api/methodspecs/review/llm", {
        spec,
        paper_text: paperText,
        llm_provider: provider,
        llm_model: model,
      })
      setReviewLlmJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleResolve() {
    if (!spec || !reviewResult) return
    setError(null)
    const decisions = reviewResult.blocked_fields
      .map((field) => {
        const note = reviewResult.field_notes.find((n) => n.field === field)
        const hasTyped = field in resolutionValues
        const value = hasTyped ? parseResolutionValue(resolutionValues[field]) : note?.candidate_value
        return { field, note, value }
      })
      // Leave a field blank (untouched, no candidate default, or explicitly
      // cleared) to skip it -- it stays blocked instead of being forced to a
      // fabricated "unspecified" string, which used to crash MethodSpec
      // validation for dict/list-typed fields (confirmed live: a real 422
      // dict_type error on data.normalized_mapping).
      .filter(({ value }) => value !== undefined && value !== null && value !== "")
      .map(({ field, note, value }) => ({
        field_path: field,
        canonical_field_path: field,
        old_value: note?.current_value ?? null,
        new_value: value,
        decision_type: "human_empirical_assumption",
        reason: resolutionReasons[field] || "Resolved via Pipeline E2E wizard.",
        reviewer: "human",
        paper_evidence: [],
      }))
    try {
      const resolved = await api.post<Record<string, unknown>>("/api/methodspecs/resolve", {
        spec,
        decisions,
        reviewer: "human",
      })
      setSpec(resolved)
      setReviewResult(null)
      setReviewSource(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleCodegen() {
    if (!spec) return
    setError(null)
    try {
      const { job_id } = await api.post<{ job_id: string }>("/api/codegen", {
        spec,
        llm_provider: provider,
        llm_model: model,
      })
      setCodegenJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleValidate() {
    if (!spec || !plugin) return
    setError(null)
    try {
      const report = await api.post<ValidationReport>("/api/validate", {
        spec,
        plugin,
        snapshot_id: snapshotId || null,
      })
      setValidation(report)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleBacktest() {
    if (!spec || !plugin || !snapshotId) return
    setError(null)
    try {
      const { job_id } = await api.post<{ job_id: string }>("/api/backtest/run", {
        spec,
        plugin,
        snapshot_id: snapshotId,
      })
      setBacktestJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const canReview = !!spec
  const isApproved = reviewResult?.disposition === "approved"
  const isBlocked = reviewResult?.disposition === "blocked"
  const canCodegen = !!spec && (isApproved || (!!reviewResult && !isBlocked))

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Pipeline — End to End</h2>
        <p className="text-sm text-muted-foreground">
          Extract → Review → Resolve → Codegen → Validate → Backtest, stage by stage.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Stage 1: Extract */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">1. Extract MethodSpec</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>Factor id</Label>
            <Input value={factorId} onChange={(e) => setFactorId(e.target.value)} placeholder="e.g. BM" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Upload paper PDF</Label>
            <label
              htmlFor="pdf-upload-input"
              className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-border p-4 text-center transition-colors hover:border-primary hover:bg-muted/50"
            >
              <span className="text-sm font-medium">
                {pdfFile ? pdfFile.name : "Click to choose a PDF, or drag one here"}
              </span>
              <span className="text-xs text-muted-foreground">
                {pdfFile ? `${(pdfFile.size / 1024).toFixed(0)} KB -- click to change` : "PDF files only"}
              </span>
            </label>
            <input
              id="pdf-upload-input"
              type="file"
              accept="application/pdf"
              onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
              className="hidden"
            />
            <Button
              onClick={handleExtractFromPdf}
              disabled={extractJob.status === "running" || !pdfFile}
              variant="default"
            >
              {extractJob.status === "running" ? "Extracting…" : "Extract from PDF"}
            </Button>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Or paste paper text instead</Label>
            <Textarea
              className="min-h-32 text-xs"
              value={paperText}
              onChange={(e) => setPaperText(e.target.value)}
              placeholder="Paste the paper's relevant text here…"
            />
            <Button onClick={handleExtract} disabled={extractJob.status === "running"} variant="outline">
              {extractJob.status === "running" ? "Extracting…" : "Extract from pasted text"}
            </Button>
          </div>
          <JobLogPanel job={extractJob} title="Extraction job" />
          {spec && <MethodSpecBoard spec={spec} />}
          {spec && <MethodSpecViewer spec={spec} title="View raw MethodSpec JSON" />}
        </CardContent>
      </Card>

      {/* Stage 2: Review */}
      {spec && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">2. Review</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex gap-2">
              <Button onClick={handleReview} disabled={!canReview} variant="outline">
                Run rules-based review
              </Button>
              <Button onClick={handleReviewLlm} disabled={!canReview || reviewLlmJob.status === "running"}>
                {reviewLlmJob.status === "running" ? "Reviewing…" : "Run LLM-backed review"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Rules-based review only checks deterministic gaps (missing/ambiguous fields, evidence
              presence). LLM-backed review additionally re-reads the source paper text to catch
              subtler mismatches -- both write the same `ReviewResult` shape and can resolve blocked
              fields the same way below.
            </p>
            <JobLogPanel job={reviewLlmJob} title="LLM review job" />
            {reviewResult && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <Badge variant={isApproved ? "default" : isBlocked ? "destructive" : "secondary"}>
                    {reviewResult.disposition}
                  </Badge>
                  <Badge variant="outline">
                    {reviewSource === "llm" ? "LLM-backed review" : "Rules-based review"}
                  </Badge>
                </div>
                {(() => {
                  const { required, advisory } = splitIssuesBySeverity(reviewResult.issues)
                  return (
                    <>
                      {required.length > 0 && (
                        <div className="flex flex-col gap-1">
                          <p className="text-xs font-medium text-destructive">Must resolve ({required.length})</p>
                          {required.map((issue, i) => (
                            <p key={i} className="text-xs text-destructive">
                              ⚠ {issue}
                            </p>
                          ))}
                        </div>
                      )}
                      {advisory.length > 0 && (
                        <details className="text-xs text-muted-foreground">
                          <summary className="cursor-pointer">Advisory notes ({advisory.length}) -- don't block approval</summary>
                          {advisory.map((issue, i) => (
                            <p key={i} className="pl-4">
                              ℹ {issue}
                            </p>
                          ))}
                        </details>
                      )}
                      {reviewResult.warnings.length > 0 && (
                        <details className="text-xs text-muted-foreground">
                          <summary className="cursor-pointer">Warnings ({reviewResult.warnings.length})</summary>
                          {reviewResult.warnings.map((warning, i) => (
                            <p key={i} className="pl-4">
                              ℹ {warning}
                            </p>
                          ))}
                        </details>
                      )}
                    </>
                  )
                })()}
                {isBlocked && (
                  <div className="flex flex-col gap-3 rounded-md border border-border p-3">
                    <p className="text-sm font-medium">Resolve blocked fields</p>
                    <p className="text-xs text-muted-foreground">
                      Leave a field blank to skip it -- it stays blocked and can be resolved later.
                    </p>
                    {(() => {
                      // More than one `_check_*` rule (or the LLM's own note
                      // plus a merged deterministic precheck note) can
                      // independently flag the SAME field -- dedupe by field
                      // path so React never sees two list items with the same
                      // key, and so a resolution decision isn't submitted
                      // twice for one field.
                      const seenBlockedFields = new Set<string>()
                      return reviewResult.field_notes.filter((n) => {
                        if (!reviewResult.blocked_fields.includes(n.field) || seenBlockedFields.has(n.field)) {
                          return false
                        }
                        seenBlockedFields.add(n.field)
                        return true
                      })
                    })()
                      .map((note) => {
                        const help = fieldHelp?.[note.field]
                        const hasOptions = !!help?.options?.length
                        const usingOther = useOtherFor[note.field] ?? false
                        return (
                          <div key={note.field} className="flex flex-col gap-1">
                            <Label>{note.field}</Label>
                            {help?.description && (
                              <p className="text-xs text-muted-foreground">ℹ {help.description}</p>
                            )}
                            {help?.example && (
                              <p className="text-xs text-muted-foreground">
                                📝 Example: <code>{help.example}</code>
                              </p>
                            )}
                            <p className="text-xs text-muted-foreground">Why it's blocked: {note.reason}</p>
                            {note.candidate_value != null && (
                              <div className="flex items-center gap-2">
                                <p className="text-xs text-emerald-600">
                                  💡 Suggested value: <code>{String(note.candidate_value)}</code> (pre-filled below --
                                  review it, don't just accept it blindly)
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
                                  onChange={(e) =>
                                    setResolutionValues((prev) => ({ ...prev, [note.field]: e.target.value }))
                                  }
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
                              onChange={(e) =>
                                setResolutionReasons((prev) => ({ ...prev, [note.field]: e.target.value }))
                              }
                            />
                          </div>
                        )
                      })}
                    <Button onClick={handleResolve}>Submit resolution</Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Stage 3: Codegen */}
      {canCodegen && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">3. Generate signal plugin</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Button onClick={handleCodegen} disabled={codegenJob.status === "running"}>
              {codegenJob.status === "running" ? "Generating…" : "Generate plugin"}
            </Button>
            <JobLogPanel job={codegenJob} title="Codegen job" />
            {plugin && (
              <pre className="max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">{plugin.code}</pre>
            )}
          </CardContent>
        </Card>
      )}

      {/* Stage 4: Validate */}
      {plugin && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">4. Validate (Adversarial Sandbox)</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Data snapshot (optional, enables execution smoke test)</Label>
              <Select value={snapshotId} onValueChange={setSnapshotId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a snapshot" />
                </SelectTrigger>
                <SelectContent>
                  {(snapshots ?? []).map((s) => (
                    <SelectItem key={s.snapshot_id} value={s.snapshot_id}>
                      {s.snapshot_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleValidate}>Validate</Button>
            {validation && (
              <div className="flex flex-col gap-1 text-sm">
                <Badge variant={validation.passed ? "default" : "destructive"}>
                  {validation.passed ? "passed" : "failed"}
                </Badge>
                {validation.errors.map((e, i) => (
                  <p key={i} className="text-xs text-destructive">
                    {e}
                  </p>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Stage 5: Backtest */}
      {validation?.passed && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">5. Run backtest</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Button onClick={handleBacktest} disabled={backtestJob.status === "running"}>
              {backtestJob.status === "running" ? "Running…" : "Run backtest"}
            </Button>
            <JobLogPanel job={backtestJob} title="Backtest job" />
            {backtestJob.status === "completed" && backtestJob.result && (
              <div className="flex flex-col gap-3">
                <MetricsTable metrics={backtestJob.result.metrics} />
                <ReturnChart data={backtestJob.result.return_series} />
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
