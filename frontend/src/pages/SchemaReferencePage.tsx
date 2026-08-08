import { useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

interface SchemaFieldEntry {
  description: string
  example: string
  allowed_values: string[] | null
  engine_consumed: boolean
  usage: string
  origin: "llm" | "human" | "pipeline" | null
  sub_fields: string[] | null
  list_item_fields: string[] | null
}

interface MethodSpecSchemaResponse {
  fields: Record<string, SchemaFieldEntry>
  json_schema: Record<string, unknown>
}

/** The top-level MethodSpec section a dotted field path belongs to, used
 * purely to group rows -- mirrors the nesting in
 * src/infra/models/method_spec.py (data / signal / portfolio /
 * reported_results), falling back to "other" for flat top-level fields. */
function sectionOf(fieldPath: string): string {
  const prefix = fieldPath.split(".")[0]
  return ["data", "signal", "portfolio", "reported_results"].includes(prefix) ? prefix : "other"
}

const SECTION_ORDER = ["other", "data", "signal", "portfolio", "reported_results"]
const SECTION_LABEL: Record<string, string> = {
  other: "Top-level",
  data: "data",
  signal: "signal",
  portfolio: "portfolio",
  reported_results: "reported_results",
}

/** One row inside a `FieldCard`: a small-caps, muted label (with a fixed
 * min-width so labels line up) to the left of its value, separated by a
 * left accent bar -- gives each attribute its own clearly labeled slot so
 * "description" vs. "allowed values" vs. "example" can't be confused, even
 * when several rows are stacked directly on top of each other. */
function AttributeRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 border-l-2 border-border/70 pl-2.5">
      <span className="w-28 shrink-0 pt-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-muted-foreground/80">
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/** One field's full metadata stacked vertically (label above value) instead
 * of a wide table row, so every field is fully readable without horizontal
 * scrolling regardless of viewport width. */
function FieldCard({ path, entry }: { path: string; entry: SchemaFieldEntry }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
        <code className="text-xs font-semibold">{path}</code>
        <div className="flex gap-1.5">
          {entry.origin && (
            <Badge variant="outline" className={
              entry.origin === "llm" ? "border-blue-400 text-blue-600" :
              entry.origin === "human" ? "border-amber-400 text-amber-600" :
              "border-slate-400 text-slate-500"
            }>
              {entry.origin === "llm" ? "LLM extracted" :
               entry.origin === "human" ? "human review" :
               "pipeline"}
            </Badge>
          )}
          <Badge variant={entry.engine_consumed ? "default" : "secondary"}>
            {entry.engine_consumed ? "engine-consumed" : "documentation-only"}
          </Badge>
        </div>
      </div>

      {entry.description && (
        <AttributeRow label="Description">
          <p className="text-xs text-muted-foreground">{entry.description}</p>
        </AttributeRow>
      )}

      {entry.usage && (
        <AttributeRow label="Usage">
          <p className="text-xs text-muted-foreground">{entry.usage}</p>
        </AttributeRow>
      )}

      <AttributeRow label="Allowed values">
        {entry.allowed_values ? (
          <div className="flex flex-wrap gap-1">
            {entry.allowed_values.map((v) => (
              <Badge key={v} variant="outline" className="font-mono text-[0.7rem]">
                {v}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-xs italic text-muted-foreground">free-form (no fixed enum)</span>
        )}
      </AttributeRow>

      {entry.example && (
        <AttributeRow label="Example">
          <code className="block w-fit whitespace-pre-wrap break-all rounded bg-muted px-1.5 py-0.5 text-xs">
            {entry.example}
          </code>
        </AttributeRow>
      )}

      {entry.sub_fields && (
        <AttributeRow label="Has fields">
          <div className="flex flex-wrap gap-1">
            {entry.sub_fields.map((f) => (
              <Badge key={f} variant="outline" className="font-mono text-[0.7rem]">
                {f.split(".").pop()}
              </Badge>
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            This is a composite object, not a single value -- see each field's own entry above/below.
          </p>
        </AttributeRow>
      )}

      {entry.list_item_fields && (
        <AttributeRow label="Each item has">
          <div className="flex flex-wrap gap-1">
            {entry.list_item_fields.map((f) => (
              <Badge key={f} variant="outline" className="font-mono text-[0.7rem]">
                {f}
              </Badge>
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            This field is a LIST -- each entry in the list has these properties.
          </p>
        </AttributeRow>
      )}
    </div>
  )
}

/** Read-only MethodSpec field reference (plan.md Phase A.5) -- every field
 * this project has description/example/enum/engine-consumption metadata
 * for, sourced from the same single-source-of-truth backend endpoint
 * (`GET /api/methodspecs/schema`) the extractor/review prompts and resolve
 * UI dropdowns already use, so this page can never drift from the real
 * schema either. */
export function SchemaReferencePage() {
  const [filter, setFilter] = useState("")
  const { data, isLoading, error } = useQuery({
    queryKey: ["methodspec-schema"],
    queryFn: () => api.get<MethodSpecSchemaResponse>("/api/methodspecs/schema"),
  })

  const rows = useMemo(() => {
    if (!data) return []
    const needle = filter.trim().toLowerCase()
    return Object.entries(data.fields)
      .filter(([path]) => !needle || path.toLowerCase().includes(needle))
      .sort(([a], [b]) => a.localeCompare(b))
  }, [data, filter])

  const bySection = useMemo(() => {
    const grouped: Record<string, [string, SchemaFieldEntry][]> = {}
    for (const [path, entry] of rows) {
      const section = sectionOf(path)
      grouped[section] = grouped[section] ?? []
      grouped[section].push([path, entry])
    }
    return grouped
  }, [rows])

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">MethodSpec Schema Reference</h2>
        <p className="text-sm text-muted-foreground">
          Every field's legal values, example, and whether it actually affects the backtest
          ("engine-consumed") or is documentation/audit metadata only -- generated directly from
          the real MethodSpec schema, never hand-duplicated.
        </p>
      </div>

      <Input
        placeholder="Filter by field path (e.g. breakpoint_basis)…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error instanceof Error ? error.message : String(error)}</p>}

      {SECTION_ORDER.filter((section) => bySection[section]?.length).map((section) => (
        <Card key={section}>
          <CardHeader>
            <CardTitle className="text-base">{SECTION_LABEL[section]}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {bySection[section].map(([path, entry]) => (
              <FieldCard key={path} path={path} entry={entry} />
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
