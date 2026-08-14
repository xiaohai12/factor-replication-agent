import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { sessionApi } from "@/lib/sessionApi"
import { STEP_REGISTRY } from "@/lib/steps"
import type { SessionManifest, StepStatus } from "@/lib/types"

const DOT_CLASS: Record<StepStatus, string> = {
  not_started: "bg-muted-foreground/20",
  running: "bg-blue-500 animate-pulse",
  success: "bg-emerald-500",
  failed: "bg-destructive",
  blocked: "bg-destructive",
}

/** 8-dot progress summary for one run -- a compressed read of the same
 * per-step attempt status `StepStepper` renders, sized for a list row. */
function ProgressDots({ manifest }: { manifest: SessionManifest }) {
  return (
    <div className="flex items-center gap-1">
      {STEP_REGISTRY.map((def) => {
        const record = manifest.steps[String(def.step)]
        const latest = record?.attempts[record.attempts.length - 1]
        const status: StepStatus = latest?.status ?? "not_started"
        return (
          <span
            key={def.step}
            title={`${def.label}: ${status}${record?.stale ? " (stale)" : ""}`}
            className={cn("h-2.5 w-2.5 rounded-full", DOT_CLASS[status], record?.stale && "ring-2 ring-amber-400")}
          />
        )
      })}
    </div>
  )
}

/** Run list + create -- the entry point into the session-centric workflow
 * control plane. Run id lives in the URL from here on, so a page reload
 * never loses context. No archive action here (see docs/ui-redesign-plan.md
 * §2.1): only delete, always with confirmation. */
export function RunsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [factorId, setFactorId] = useState("")
  const [search, setSearch] = useState("")

  const runsQuery = useQuery({ queryKey: ["sessions"], queryFn: sessionApi.list })

  const createMutation = useMutation({
    mutationFn: () => sessionApi.create(factorId),
    onSuccess: (manifest) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      navigate(`/runs/${manifest.session_id}/step/1`)
    },
  })

  const filtered = useMemo(() => {
    const runs = runsQuery.data ?? []
    const q = search.trim().toLowerCase()
    if (!q) return runs
    return runs.filter(
      (r) => r.factor_id.toLowerCase().includes(q) || (r.paper_id ?? "").toLowerCase().includes(q),
    )
  }, [runsQuery.data, search])

  return (
    <div className="flex flex-col gap-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>New run</CardTitle>
        </CardHeader>
        <CardContent className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="factor-id">Factor id</Label>
            <Input
              id="factor-id"
              value={factorId}
              onChange={(e) => setFactorId(e.target.value)}
              placeholder="cooper_gulen_schill_2008_asset_growth"
            />
          </div>
          <Button disabled={!factorId || createMutation.isPending} onClick={() => createMutation.mutate()}>
            Create run
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Runs</CardTitle>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by factor or paper…"
            className="max-w-xs"
          />
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Factor</TableHead>
                <TableHead>Paper</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((run) => (
                <RunRow key={run.session_id} run={run} onNavigate={navigate} />
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function RunRow({
  run,
  onNavigate,
}: {
  run: SessionManifest
  onNavigate: (path: string) => void
}) {
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: () => sessionApi.hardDelete(run.session_id, run.revision),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  })

  return (
    <TableRow className="cursor-pointer" onClick={() => onNavigate(`/runs/${run.session_id}/step/1`)}>
      <TableCell>{run.factor_id}</TableCell>
      <TableCell className="text-muted-foreground">{run.paper_id ?? "—"}</TableCell>
      <TableCell>
        <ProgressDots manifest={run} />
      </TableCell>
      <TableCell>
        <Badge variant="outline">{run.state}</Badge>
      </TableCell>
      <TableCell>{new Date(run.updated_at).toLocaleString()}</TableCell>
      <TableCell onClick={(e) => e.stopPropagation()}>
        <Button
          size="sm"
          variant="destructive"
          disabled={deleteMutation.isPending}
          onClick={() => {
            if (window.confirm(`Permanently delete run for '${run.factor_id}'? This cannot be undone.`)) {
              deleteMutation.mutate()
            }
          }}
        >
          Delete
        </Button>
      </TableCell>
    </TableRow>
  )
}
