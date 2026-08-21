import { useMemo, useState } from "react"
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
 * purely to group rows -- mirrors ALL 8 top-level sections nested under
 * src/infra/models/method_spec.py's MethodSpec (paper / signal / data /
 * sample / timing / universe / portfolio / reported_results), falling back
 * to "other" only for genuinely flat top-level fields (factor_id,
 * target_name, notes, schema_version). */
function sectionOf(fieldPath: string): string {
  const prefix = fieldPath.split(".")[0]
  return SECTION_ORDER.includes(prefix) ? prefix : "other"
}

const SECTION_ORDER = [
  "paper",
  "signal",
  "data",
  "sample",
  "timing",
  "universe",
  "portfolio",
  "reported_results",
  "other",
]
const SECTION_LABEL: Record<string, string> = {
  paper: "paper",
  signal: "signal",
  data: "data",
  sample: "sample",
  timing: "timing",
  universe: "universe",
  portfolio: "portfolio",
  reported_results: "reported_results",
  other: "Top-level",
}

const ORIGIN_LABEL: Record<string, string> = { llm: "LLM extracted", human: "human review", pipeline: "pipeline" }
const ORIGIN_CLASS: Record<string, string> = {
  llm: "border-blue-400 text-blue-600",
  human: "border-amber-400 text-amber-600",
  pipeline: "border-slate-400 text-slate-500",
}

/** A composite/list entry's children, as full dotted paths resolvable in
 * `data.fields` -- `sub_fields` on a composite is already full-path (mirrors
 * how `_walk_model` builds it), but `list_item_fields` on a list is just bare
 * names, so they need the parent path prefixed back on. Some of the
 * resulting paths won't actually exist as their own schema entry (e.g. a
 * `list[SourcedValue[...]]`'s `value`/`evidence`/`status`, or `EvidenceCitation`'s
 * own `location`/`quote`/`table_ref` -- deliberately not expanded, see
 * schema_reference.py) -- callers must filter those out before recursing. */
function childPaths(entry: SchemaFieldEntry, path: string): string[] {
  if (entry.sub_fields) return entry.sub_fields
  if (entry.list_item_fields) return entry.list_item_fields.map((f) => `${path}.${f}`)
  return []
}

/** One field, collapsed by default below the root, expand to see its own
 * description/usage/allowed-values/example plus (recursively) its children.
 * This is what keeps the page from dumping all ~170 fields flat on screen at
 * once -- only the section roots start open, everything below stays closed
 * until you click into it. */
function FieldNode({ path, data, depth }: { path: string; data: MethodSpecSchemaResponse; depth: number }) {
  const entry = data.fields[path]
  const [open, setOpen] = useState(depth === 0)
  if (!entry) return null

  const candidateChildren = childPaths(entry, path)
  const realChildren = candidateChildren.filter((c) => data.fields[c])
  // list_item_fields whose names don't resolve to their own entry (plain
  // sub-values, or the intentionally-not-re-expanded EvidenceCitation shape)
  // -- shown as plain badges instead of further expandable nodes.
  const terminalNames = entry.list_item_fields && realChildren.length === 0 ? entry.list_item_fields : null
  const hasChildren = realChildren.length > 0
  const hasDetail = Boolean(entry.description || entry.usage || entry.allowed_values || entry.example || terminalNames)
  const label = path.split(".").pop()!

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => (hasChildren || hasDetail) && setOpen((o) => !o)}
        className="flex w-full flex-wrap items-center gap-2 rounded border border-border/60 bg-card px-2 py-1 text-left hover:bg-muted/50 disabled:cursor-default"
        disabled={!hasChildren && !hasDetail}
      >
        <span className="w-3 shrink-0 text-center text-xs text-muted-foreground">
          {hasChildren || hasDetail ? (open ? "\u25be" : "\u25b8") : ""}
        </span>
        <code className="text-xs font-semibold">{label}</code>
        {entry.list_item_fields && (
          <Badge variant="secondary" className="text-[0.65rem]">list</Badge>
        )}
        {entry.allowed_values && (
          <Badge variant="outline" className="font-mono text-[0.65rem]">enum</Badge>
        )}
        {entry.origin && (
          <Badge variant="outline" className={`text-[0.65rem] ${ORIGIN_CLASS[entry.origin]}`}>
            {ORIGIN_LABEL[entry.origin]}
          </Badge>
        )}
        <Badge variant={entry.engine_consumed ? "default" : "secondary"} className="text-[0.65rem]">
          {entry.engine_consumed ? "engine-consumed" : "docs-only"}
        </Badge>
      </button>

      {open && (
        <div className="ml-4 flex flex-col gap-1.5 border-l border-border/50 pl-3">
          {entry.description && <p className="text-xs text-muted-foreground">{entry.description}</p>}
          {entry.usage && (
            <p className="text-xs text-muted-foreground">
              <span className="font-semibold">Usage: </span>
              {entry.usage}
            </p>
          )}
          {entry.allowed_values && (
            <div className="flex flex-wrap gap-1">
              {entry.allowed_values.map((v) => (
                <Badge key={v} variant="outline" className="font-mono text-[0.7rem]">
                  {v}
                </Badge>
              ))}
            </div>
          )}
          {entry.example && (
            <code className="block w-fit whitespace-pre-wrap break-all rounded bg-muted px-1.5 py-0.5 text-xs">
              {entry.example}
            </code>
          )}
          {terminalNames && (
            <div className="flex flex-wrap gap-1">
              {terminalNames.map((f) => (
                <Badge key={f} variant="outline" className="font-mono text-[0.7rem]">
                  {f}
                </Badge>
              ))}
            </div>
          )}
          {realChildren.map((c) => (
            <FieldNode key={c} path={c} data={data} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Flat search-result row -- used only while a filter is active, since a
 * collapsible tree makes searching harder (matches could be buried several
 * levels deep). Same attribute layout as the old always-flat page. */
function SearchResultRow({ path, entry }: { path: string; entry: SchemaFieldEntry }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-xs font-semibold">{path}</code>
        {entry.allowed_values && <Badge variant="outline" className="font-mono text-[0.65rem]">enum</Badge>}
        <Badge variant={entry.engine_consumed ? "default" : "secondary"} className="text-[0.65rem]">
          {entry.engine_consumed ? "engine-consumed" : "docs-only"}
        </Badge>
      </div>
      {entry.description && <p className="text-xs text-muted-foreground">{entry.description}</p>}
      {entry.allowed_values && (
        <div className="flex flex-wrap gap-1">
          {entry.allowed_values.map((v) => (
            <Badge key={v} variant="outline" className="font-mono text-[0.7rem]">
              {v}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

/** Read-only MethodSpec field reference (plan.md Phase A.5) -- every field
 * this project has description/example/enum/engine-consumption metadata
 * for, sourced from the same single-source-of-truth backend endpoint
 * (`GET /api/methodspecs/schema`) the extractor/review prompts and resolve
 * UI dropdowns already use, so this page can never drift from the real
 * schema either. Rendered as a collapsible tree (only section roots start
 * expanded) rather than one flat list of ~170 rows. */
export function SchemaReferencePage() {
  const [filter, setFilter] = useState("")
  const { data, isLoading, error } = useQuery({
    queryKey: ["methodspec-schema"],
    queryFn: () => api.get<MethodSpecSchemaResponse>("/api/methodspecs/schema"),
  })

  const needle = filter.trim().toLowerCase()

  const searchRows = useMemo(() => {
    if (!data || !needle) return []
    return Object.entries(data.fields)
      .filter(([path]) => path.toLowerCase().includes(needle))
      .sort(([a], [b]) => a.localeCompare(b))
  }, [data, needle])

  const rootsBySection = useMemo(() => {
    if (!data) return {}
    const grouped: Record<string, string[]> = {}
    for (const path of Object.keys(data.fields)) {
      if (path.includes(".")) continue
      const section = sectionOf(path)
      grouped[section] = grouped[section] ?? []
      grouped[section].push(path)
    }
    for (const roots of Object.values(grouped)) roots.sort((a, b) => a.localeCompare(b))
    return grouped
  }, [data])

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">MethodSpec Schema Reference</h2>
        <p className="text-sm text-muted-foreground">
          Every field's legal values, example, and whether it actually affects the backtest
          ("engine-consumed") or is documentation/audit metadata only -- generated directly from
          the real MethodSpec schema, never hand-duplicated. Click a row to expand it.
        </p>
      </div>

      <Input
        placeholder="Filter by field path (e.g. breakpoint_basis)…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error instanceof Error ? error.message : String(error)}</p>}

      {data && needle && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{searchRows.length} match(es)</p>
          {searchRows.map(([path, entry]) => (
            <SearchResultRow key={path} path={path} entry={entry} />
          ))}
        </div>
      )}

      {data &&
        !needle &&
        SECTION_ORDER.filter((section) => rootsBySection[section]?.length).map((section) => (
          <Card key={section}>
            <CardHeader>
              <CardTitle className="text-base">{SECTION_LABEL[section]}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {rootsBySection[section].map((path) => (
                <FieldNode key={path} path={path} data={data} depth={0} />
              ))}
            </CardContent>
          </Card>
        ))}
    </div>
  )
}
