import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { JobLogPanel } from "@/components/JobLogPanel"
import { MetricsTable } from "@/components/MetricsTable"
import { ReturnChart, type ReturnRow } from "@/components/ReturnChart"
import { api } from "@/lib/api"
import { useJobStream } from "@/lib/useJobStream"

interface Snapshot {
  snapshot_id: string
  storage_path: string
}

interface BacktestJobResult {
  metrics: Record<string, unknown>
  return_series: ReturnRow[]
  config: Record<string, unknown>
  script_path: string
  run_record: { run_id: string; status: string }
}

export function BacktestExperimentsPage() {
  const { data: snapshots } = useQuery({
    queryKey: ["snapshots"],
    queryFn: () => api.get<Snapshot[]>("/api/backtest/snapshots"),
  })
  const { data: resolvedFactors } = useQuery({
    queryKey: ["methodspecs", "resolved"],
    queryFn: () => api.get<string[]>("/api/methodspecs/resolved"),
  })

  const [factorId, setFactorId] = useState<string>("")
  const [snapshotId, setSnapshotId] = useState<string>("")
  const [pluginCode, setPluginCode] = useState("")
  const [pluginId, setPluginId] = useState("")
  const [configOverridesText, setConfigOverridesText] = useState("{}")
  const [jobId, setJobId] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    if (snapshots && snapshots.length > 0 && !snapshotId) {
      setSnapshotId(snapshots[0].snapshot_id)
    }
  }, [snapshots, snapshotId])

  const job = useJobStream<BacktestJobResult>(jobId)

  async function handleRun() {
    setRunError(null)
    if (!factorId || !snapshotId || !pluginCode.trim()) {
      setRunError("Select a factor, a snapshot, and paste plugin code before running.")
      return
    }
    try {
      const spec = await api.get<Record<string, unknown>>(
        `/api/methodspecs/resolved/${factorId}`,
      )
      let configOverrides: Record<string, unknown> | null = null
      if (configOverridesText.trim()) {
        configOverrides = JSON.parse(configOverridesText)
      }
      const { job_id } = await api.post<{ job_id: string }>("/api/backtest/run", {
        spec,
        plugin: {
          plugin_id: pluginId || `${factorId}_v1`,
          factor_id: factorId,
          code: pluginCode,
          code_hash: "manual",
        },
        snapshot_id: snapshotId,
        config_overrides: configOverrides,
      })
      setJobId(job_id)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Backtest &amp; Experiments</h2>
        <p className="text-sm text-muted-foreground">
          Run a single backtest for a resolved MethodSpec + signal plugin against a registered data
          snapshot.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configuration</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Resolved factor</Label>
            <Select value={factorId} onValueChange={setFactorId}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a resolved MethodSpec" />
              </SelectTrigger>
              <SelectContent>
                {(resolvedFactors ?? []).map((id) => (
                  <SelectItem key={id} value={id}>
                    {id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Data snapshot</Label>
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

          <div className="flex flex-col gap-1.5">
            <Label>Plugin id (optional)</Label>
            <Textarea
              className="min-h-8"
              value={pluginId}
              onChange={(e) => setPluginId(e.target.value)}
              placeholder={factorId ? `${factorId}_v1` : "plugin id"}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Plugin code (compute_signal source)</Label>
            <Textarea
              className="min-h-40 font-mono text-xs"
              value={pluginCode}
              onChange={(e) => setPluginCode(e.target.value)}
              placeholder="def compute_signal(df): ..."
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Config overrides (JSON, optional)</Label>
            <Textarea
              className="min-h-20 font-mono text-xs"
              value={configOverridesText}
              onChange={(e) => setConfigOverridesText(e.target.value)}
            />
          </div>

          {runError && <p className="text-sm text-destructive">{runError}</p>}

          <Button onClick={handleRun} disabled={job.status === "running"}>
            {job.status === "running" ? "Running…" : "Run backtest"}
          </Button>
        </CardContent>
      </Card>

      <JobLogPanel job={job} title="Backtest job" />

      {job.status === "completed" && job.result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Results</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <MetricsTable metrics={job.result.metrics} />
            <ReturnChart data={job.result.return_series} />
            <p className="text-xs text-muted-foreground">
              Script: {job.result.script_path} · Run id: {job.result.run_record.run_id}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
