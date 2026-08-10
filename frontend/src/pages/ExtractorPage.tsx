import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { JobLogPanel } from "@/components/JobLogPanel"
import { MethodSpecBoard } from "@/components/MethodSpecBoard"
import { ApiError } from "@/lib/api"
import { PROVIDER_MODELS, useLlm } from "@/lib/llmContext"
import { sessionApi } from "@/lib/sessionApi"
import { useJobStream } from "@/lib/useJobStream"

interface ExtractionResult {
  spec?: Record<string, unknown>
  error?: string
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `${error.status}: ${error.message}` : String(error)
}

/** Standalone paper-first extraction page. Extraction artifacts are global
 * MethodSpec drafts, not session step-1 artifacts; the backend persists every
 * successful result under runs/method_specs/unreviewed. */
export function ExtractorPage() {
  const navigate = useNavigate()
  const { provider, model, setProvider, setModel } = useLlm()
  const [file, setFile] = useState<File | null>(null)
  const [documentId, setDocumentId] = useState("")
  const [targetName, setTargetName] = useState("")
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const job = useJobStream<ExtractionResult>(jobId)

  const mutation = useMutation({
    mutationFn: () =>
      sessionApi.extractPaperPdf(
        documentId.trim() || file!.name,
        targetName.trim(),
        file!,
        provider,
        model,
      ),
    onSuccess: ({ job_id }) => {
      setError(null)
      setJobId(job_id)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const spec = job.result?.spec ?? null
  const factorId = spec?.factor_id ? String(spec.factor_id) : ""
  const extractionError = job.status === "completed" && !spec ? job.result?.error ?? "Extraction returned no spec" : null

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <div>
        <h2 className="text-2xl font-semibold">Extractor</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Extract one paper-first MethodSpec draft from a PDF. The draft is saved globally and can be reviewed
          without creating a session.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Paper and target</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <label
            htmlFor="extractor-pdf"
            className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary hover:bg-muted/50"
          >
            <span className="text-sm font-medium">{file ? file.name : "Choose a paper PDF"}</span>
            <span className="text-xs text-muted-foreground">
              {file ? `${(file.size / 1024).toFixed(0)} KB — click to change` : "PDF files only"}
            </span>
          </label>
          <input
            id="extractor-pdf"
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(event) => {
              const nextFile = event.target.files?.[0] ?? null
              setFile(nextFile)
              if (nextFile && !documentId) setDocumentId(nextFile.name)
            }}
          />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="extract-document-id">Document ID</Label>
              <Input
                id="extract-document-id"
                value={documentId}
                onChange={(event) => setDocumentId(event.target.value)}
                placeholder="Stable paper id; filename is used if blank"
              />
              <p className="text-xs text-muted-foreground">Used with the target name to derive a stable factor id.</p>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="extract-target-name">Target factor name</Label>
              <Input
                id="extract-target-name"
                value={targetName}
                onChange={(event) => setTargetName(event.target.value)}
                placeholder="Asset growth"
              />
              <p className="text-xs text-muted-foreground">The precise factor or signal to extract from the paper.</p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>LLM provider</Label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.keys(PROVIDER_MODELS).map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(PROVIDER_MODELS[provider] ?? []).map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button
            disabled={!file || !targetName.trim() || mutation.isPending || job.status === "running"}
            onClick={() => mutation.mutate()}
          >
            {job.status === "running" ? "Extracting…" : "Extract MethodSpec"}
          </Button>
          <JobLogPanel job={job} title="Extraction job" />
          {(error || extractionError) && <p className="text-sm text-destructive">{error || extractionError}</p>}
        </CardContent>
      </Card>

      {spec && (
        <Card>
          <CardHeader>
            <CardTitle>2. Extracted draft</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <MethodSpecBoard spec={spec} />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => navigate(`/review?factor_id=${encodeURIComponent(factorId)}`)}>
                Continue to Review & Resolve
              </Button>
              <Button variant="outline" onClick={() => navigate("/schema")}>Open schema reference</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
