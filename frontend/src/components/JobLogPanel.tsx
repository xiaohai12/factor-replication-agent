import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { JobState } from "@/lib/useJobStream"

const STATUS_VARIANT: Record<JobState["status"], "default" | "secondary" | "destructive" | "outline"> = {
  idle: "outline",
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
}

export function JobLogPanel({ job, title }: { job: JobState; title?: string }) {
  if (job.status === "idle") return null
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{title ?? "Job progress"}</span>
        <Badge variant={STATUS_VARIANT[job.status]}>{job.status}</Badge>
      </div>
      <ScrollArea className="h-32 rounded-md bg-muted p-2 font-mono text-xs">
        {job.logs.length === 0 ? (
          <span className="text-muted-foreground">Waiting for the job to start…</span>
        ) : (
          job.logs.map((line, i) => <div key={i}>{line}</div>)
        )}
      </ScrollArea>
      {job.status === "failed" && job.error && (
        <pre className="max-h-40 overflow-auto rounded-md bg-destructive/10 p-2 text-xs text-destructive">
          {job.error}
        </pre>
      )}
    </div>
  )
}
