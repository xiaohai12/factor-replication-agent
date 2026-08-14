import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import type { ToolResult } from "@/lib/types"

const STATUS_VARIANT: Record<ToolResult["status"], "default" | "secondary" | "destructive" | "outline"> = {
  ok: "default",
  skipped: "outline",
  error: "destructive",
}

/** Renders the Tool Prelude results (docs/tools-plus-llm-plan.md) that
 * `src/infra/tooling/`'s `ToolRunner` already computes before every Step1
 * extraction / Step2 review round -- `ExtractionResult.tool_results` /
 * `SpecBuildOutcome.tool_results`. Each tool's `payload` is opaque JSON
 * (no fixed shape across tools), so it's just pretty-printed. */
export function ToolResultsPanel({ results, title }: { results: ToolResult[]; title?: string }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  if (results.length === 0) return null
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <span className="text-sm font-medium">{title ?? "Tool results"}</span>
      <div className="flex flex-col gap-2">
        {results.map((r) => {
          const hasPayload = Object.keys(r.payload).length > 0
          const isOpen = expanded[r.name] ?? false
          return (
            <div key={r.name} className="rounded-md border border-border/60 p-2 text-xs">
              <div
                className={`flex items-center justify-between ${hasPayload ? "cursor-pointer" : ""}`}
                onClick={() => hasPayload && setExpanded((prev) => ({ ...prev, [r.name]: !isOpen }))}
              >
                <span className="font-mono font-medium">{r.name}</span>
                <Badge variant={STATUS_VARIANT[r.status]}>{r.status}</Badge>
              </div>
              {r.error && <p className="mt-1 text-destructive">{r.error}</p>}
              {hasPayload && isOpen && (
                <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-2">
                  {JSON.stringify(r.payload, null, 2)}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
