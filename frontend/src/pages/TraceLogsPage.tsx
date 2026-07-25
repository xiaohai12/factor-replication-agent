import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"

interface RunRecord {
  run_id: string
  factor_id: string
  status: string
  track: string
  created_at: string
}

interface RunsResponse {
  summary: Record<string, number>
  runs: RunRecord[]
}

interface EvidenceListing {
  factor_id: string
  run_id: string
  files: string[]
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  success: "default",
  failed: "destructive",
  pending: "secondary",
  running: "secondary",
  needs_review: "outline",
}

export function TraceLogsPage() {
  const { data } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<RunsResponse>("/api/runs"),
  })
  const [selected, setSelected] = useState<RunRecord | null>(null)

  const { data: evidence } = useQuery({
    queryKey: ["evidence", selected?.factor_id, selected?.run_id],
    queryFn: () =>
      api.get<EvidenceListing>(`/api/evidence/${selected!.factor_id}/${selected!.run_id}`),
    enabled: !!selected,
  })

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Trace &amp; Logs</h2>
        <p className="text-sm text-muted-foreground">
          Run registry (rebuilt from the persistent evidence store on backend startup) and evidence
          file browser.
        </p>
      </div>

      {data?.summary && (
        <div className="flex gap-2">
          {Object.entries(data.summary).map(([status, count]) => (
            <Badge key={status} variant={STATUS_VARIANT[status] ?? "outline"}>
              {status}: {count}
            </Badge>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run registry</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Factor</TableHead>
                <TableHead>Run id</TableHead>
                <TableHead>Track</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.runs ?? []).map((run) => (
                <TableRow
                  key={run.run_id}
                  className="cursor-pointer hover:bg-muted"
                  onClick={() => setSelected(run)}
                >
                  <TableCell>{run.factor_id}</TableCell>
                  <TableCell className="font-mono text-xs">{run.run_id}</TableCell>
                  <TableCell>{run.track}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[run.status] ?? "outline"}>{run.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Evidence: {selected.factor_id} / {selected.run_id}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 text-sm">
              {(evidence?.files ?? []).map((file) => (
                <li key={file}>
                  <a
                    className="text-primary hover:underline"
                    href={`/api/evidence/${selected.factor_id}/${selected.run_id}/download/${file}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {file}
                  </a>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
