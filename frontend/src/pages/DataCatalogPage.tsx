import { useMemo, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

interface SignalSourceEntry {
  join: { key: string; link: string | null; date: string | null; lag: number | string }
  physical_columns: string[]
  columns: Record<string, string>
  description: string
  column_descriptions: Record<string, string>
}

interface LinkTableEntry {
  key: string
  permno: string
  start: string
  end: string
  valid_filters?: Record<string, unknown>
  primary_filter?: Record<string, unknown>
}

interface ReturnsUniverseEntry {
  returns_table: string
  returns_layout: string
}

interface DataCatalogResponse {
  signal_sources: Record<string, SignalSourceEntry>
  link_tables: Record<string, LinkTableEntry>
  returns_universes: Record<string, ReturnsUniverseEntry>
  default_returns_universe: string
}

/** Mirrors SchemaReferencePage's `AttributeRow`: a fixed-width, small-caps
 * muted label to the left of its value, so attributes never blend
 * together even when several are stacked directly on top of each other. */
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

function SignalSourceCard({ name, entry }: { name: string; entry: SignalSourceEntry }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
        <code className="text-xs font-semibold">{name}</code>
        <Badge variant={entry.join.link ? "outline" : "secondary"}>
          {entry.join.link ? `links via ${entry.join.link}` : "already permno-keyed"}
        </Badge>
      </div>

      {entry.description && (
        <AttributeRow label="Description">
          <p className="text-xs text-muted-foreground">{entry.description}</p>
        </AttributeRow>
      )}

      <AttributeRow label="Join">
        <p className="text-xs text-muted-foreground">
          key=<code>{entry.join.key}</code>, link=<code>{entry.join.link ?? "none"}</code>, date=
          <code>{entry.join.date ?? "none"}</code>, lag=<code>{String(entry.join.lag)}</code>
        </p>
      </AttributeRow>

      <AttributeRow label="Physical columns">
        <div className="flex flex-col gap-1">
          {entry.physical_columns.map((col) => (
            <div key={col} className="flex flex-wrap items-baseline gap-2">
              <Badge variant="outline" className="shrink-0 font-mono text-[0.7rem]">
                {col}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {entry.column_descriptions[col] || "no description registered"}
              </span>
            </div>
          ))}
        </div>
      </AttributeRow>

      {Object.keys(entry.columns).length > 0 && (
        <AttributeRow label="Concept aliases">
          <div className="flex flex-col gap-0.5">
            {Object.entries(entry.columns).map(([concept, column]) => (
              <p key={concept} className="text-xs text-muted-foreground">
                <code>{concept}</code> → <code>{column}</code>
              </p>
            ))}
          </div>
        </AttributeRow>
      )}
    </div>
  )
}

/** Read-only Data Catalog reference page: every registered signal source,
 * link table, and returns universe, sourced from `GET /api/data-catalog`
 * (backed directly by `src/infra/data_layer/catalog.py`/`sources.py`, the
 * single source of truth the data loader itself resolves against) -- so a
 * paper's required field either resolves to one of these sources, or it
 * genuinely needs a new one registered before review can approve it. */
export function DataCatalogPage() {
  const [filter, setFilter] = useState("")
  const { data, isLoading, error } = useQuery({
    queryKey: ["data-catalog"],
    queryFn: () => api.get<DataCatalogResponse>("/api/data-catalog"),
  })

  const sourceEntries = useMemo(() => {
    if (!data) return []
    const needle = filter.trim().toLowerCase()
    return Object.entries(data.signal_sources)
      .filter(([name, entry]) => {
        if (!needle) return true
        return (
          name.toLowerCase().includes(needle) ||
          entry.physical_columns.some((c) => c.toLowerCase().includes(needle)) ||
          Object.keys(entry.columns).some((c) => c.toLowerCase().includes(needle))
        )
      })
      .sort(([a], [b]) => a.localeCompare(b))
  }, [data, filter])

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Data Catalog</h2>
        <p className="text-sm text-muted-foreground">
          Every registered signal source, its join into the CRSP permno backbone, and every
          registered returns universe -- sourced directly from the data loader's own registry, so
          this page can't drift from what the pipeline actually resolves at runtime. A required
          field that isn't covered here must have a new source registered before review can
          approve it (`ReviewGate._check_source_mapping_resolved`).
        </p>
      </div>

      <Input
        placeholder="Filter by source name or column/concept (e.g. total_assets)…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error instanceof Error ? error.message : String(error)}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Signal Sources</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {sourceEntries.map(([name, entry]) => (
            <SignalSourceCard key={name} name={name} entry={entry} />
          ))}
          {data && sourceEntries.length === 0 && (
            <p className="text-xs text-muted-foreground">No source matches "{filter}".</p>
          )}
        </CardContent>
      </Card>

      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Link Tables</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {Object.entries(data.link_tables).map(([name, link]) => (
              <div key={name} className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
                <code className="text-xs font-semibold">{name}</code>
                <AttributeRow label="Resolves">
                  <p className="text-xs text-muted-foreground">
                    <code>{link.key}</code> → <code>{link.permno}</code>, valid <code>{link.start}</code>–
                    <code>{link.end}</code>
                  </p>
                </AttributeRow>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Returns Universes</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {Object.entries(data.returns_universes).map(([alias, universe]) => (
              <div key={alias} className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <code className="text-xs font-semibold">{alias}</code>
                  {alias === data.default_returns_universe && <Badge>default</Badge>}
                </div>
                <AttributeRow label="Table / layout">
                  <p className="text-xs text-muted-foreground">
                    <code>{universe.returns_table}</code> / <code>{universe.returns_layout}</code>
                  </p>
                </AttributeRow>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
