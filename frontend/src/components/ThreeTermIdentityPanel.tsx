/** step7's `three_term_identity` section: how far an EXTERNAL implementer's
 * own published number (C&Z / HXZ) sits from the PAPER's own reported
 * number, split into the signal, the portfolio settings, and our own
 * replication error (docs/paper-outline.md C1).
 *
 * Layout: a general "how to read this" paragraph (fixed copy, not derived
 * per-factor -- the three terms mean the same thing on every factor), a
 * cross-line verdict sentence computed purely from `largest_term` (works
 * for any factor: 1 line, 2 lines, or 2 lines that disagree), a grouped
 * diverging bar chart putting cz/hxz side by side per term so the reader
 * compares lines at a glance instead of re-reading two separate tables, and
 * the per-line detail table below for the exact numbers. The chart and the
 * "largest term" emphasis are read off the data (`largest_term`,
 * `Math.abs(value)`), never hardcoded to a specific factor's story. */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

type ThreeTermSection = {
  available?: boolean
  reason?: string
  hybrid_track?: string
  total_gap?: number
  terms?: Record<string, number>
  largest_term?: string
  residual?: number
  endpoints?: Record<string, unknown>
  window_basis?: {
    paper_sample_start_year?: number | null
    paper_sample_end_year?: number | null
    external_sample_start_year?: number | null
    external_sample_end_year?: number | null
    external_window_adjustable?: boolean | null
    window_sensitivity_spread?: number | null
    external_source?: string | null
    caveat?: string
  }
}

const REFERENCE_LABELS: Record<string, string> = {
  cz: "C&Z's own published result",
  hxz: "HXZ's own published result",
}

// Fixed order/keys -- `build_three_term_identity` always emits exactly
// these three, so the chart's category axis and the cross-line comparison
// below can both assume this shape rather than deriving it from whichever
// line happens to be available.
const TERM_ORDER = ["signal_and_environment", "config", "agent_replication_residual"] as const

const TERM_LABELS: Record<string, string> = {
  signal_and_environment: "Signal computation (+ data vintage / engine)",
  config: "Portfolio-construction settings alone",
  agent_replication_residual: "Our own run vs the paper's number",
}

const TERM_SHORT_LABELS: Record<string, string> = {
  signal_and_environment: "Signal + env",
  config: "Config",
  agent_replication_residual: "Agent vs paper",
}

const REFERENCE_COLORS: Record<string, string> = {
  cz: "var(--color-primary)",
  hxz: "var(--color-muted-foreground)",
}

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "n/a"
  return value.toFixed(4)
}

function window_(start?: number | null, end?: number | null): string {
  if (start == null && end == null) return "unstated"
  return `${start ?? "?"}-${end ?? "?"}`
}

/** One sentence synthesizing however many lines are available, purely from
 * `largest_term` -- generic across factors: 1 available line just names its
 * largest term, 2 agreeing lines say so, 2 disagreeing lines say that too.
 * Never asserts anything the data itself doesn't already carry. */
function crossLineVerdict(available: [string, ThreeTermSection][]): string | null {
  if (available.length === 0) return null
  if (available.length === 1) {
    const [ref, section] = available[0]
    const term = section.largest_term
    if (!term) return null
    return `${REFERENCE_LABELS[ref] ?? ref}'s distance from the paper is dominated by "${TERM_LABELS[term] ?? term}".`
  }
  const terms = available.map(([, s]) => s.largest_term)
  const allSame = terms.every((t) => t != null && t === terms[0])
  if (allSame && terms[0]) {
    const label = TERM_LABELS[terms[0]] ?? terms[0]
    return `Both lines agree: the largest term in each is "${label}" -- ${
      terms[0] === "agent_replication_residual"
        ? "most of the distance from the paper traces back to our own baseline, not to which config/signal the external implementer used."
        : "the config/signal choice each implementer made is what drives the distance, not our own replication error."
    }`
  }
  const parts = available
    .filter(([, s]) => s.largest_term)
    .map(([ref, s]) => `${ref} → "${TERM_LABELS[s.largest_term!] ?? s.largest_term}"`)
  return `Lines disagree on which term dominates: ${parts.join(", ")} -- read each line's own table below rather than generalizing across them.`
}

function ThreeTermChart({ available }: { available: [string, ThreeTermSection][] }) {
  const chartRows = TERM_ORDER.map((term) => {
    const row: Record<string, number | string> = { term: TERM_SHORT_LABELS[term] }
    for (const [ref, section] of available) {
      const value = section.terms?.[term]
      if (typeof value === "number") row[ref] = value
    }
    return row
  })
  // This comparison has only three categories. Give each one enough vertical
  // room to read, while capping width so the diverging bars are not stretched
  // across the full Step 7 panel on a wide monitor.
  const height = Math.max(260, TERM_ORDER.length * 68 + 48)
  return (
    <div className="w-full max-w-2xl self-center rounded-lg border border-border p-3" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartRows} layout="vertical" margin={{ top: 8, right: 16, bottom: 38, left: 8 }} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            label={{ value: "monthly return", position: "insideBottom", offset: -14, fontSize: 11 }}
          />
          <YAxis type="category" dataKey="term" tick={{ fontSize: 11 }} width={110} />
          <ReferenceLine x={0} className="stroke-border" />
          <Tooltip formatter={(value, name) => [Number(value).toFixed(4), REFERENCE_LABELS[name as string] ?? name]} />
          <Legend
            formatter={(value) => REFERENCE_LABELS[value] ?? value}
            verticalAlign="bottom"
            wrapperStyle={{ fontSize: 11, bottom: -2 }}
          />
          {available.map(([ref]) => (
            <Bar key={ref} dataKey={ref} fill={REFERENCE_COLORS[ref] ?? "var(--color-primary)"} barSize={16} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ReferenceDetail({ reference, section }: { reference: string; section: ThreeTermSection }) {
  const label = REFERENCE_LABELS[reference] ?? reference
  if (!section.available) {
    return (
      <div className="rounded-md border border-border p-2">
        <p className="text-xs font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{section.reason ?? "not available for this batch"}</p>
      </div>
    )
  }

  const terms = section.terms ?? {}
  const wb = section.window_basis ?? {}
  const ordered = TERM_ORDER.filter((t) => t in terms)

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium">{label}</p>
        <span className="font-mono text-xs text-muted-foreground">
          &minus; paper = {fmt(section.total_gap)}/mo
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {ordered.map((name) => (
          <div
            key={name}
            className={cn(
              "flex items-center justify-between gap-2 text-xs",
              name === section.largest_term && "font-medium",
            )}
          >
            <span className="flex items-center gap-1">
              {TERM_LABELS[name] ?? name}
              {name === section.largest_term && (
                <Badge variant={name === "agent_replication_residual" ? "secondary" : "outline"} className="h-4 px-1 text-[10px]">
                  largest
                </Badge>
              )}
            </span>
            <span className="font-mono">{fmt(terms[name])}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>Residual (zero by construction -- arithmetic check)</span>
          <span className="font-mono">{fmt(section.residual)}</span>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Windows -- paper: {window_(wb.paper_sample_start_year, wb.paper_sample_end_year)}; {label}:{" "}
        {window_(wb.external_sample_start_year, wb.external_sample_end_year)}
        {wb.external_window_adjustable === false && " (fixed, cannot be recomputed on another window)"}
        {wb.window_sensitivity_spread != null && (
          <>
            {" "}
            &middot; recomputing it on its own paper's window instead moves it by{" "}
            <span className="font-mono">{fmt(wb.window_sensitivity_spread)}</span>
          </>
        )}
      </p>
    </div>
  )
}

export function ThreeTermIdentityPanel({ threeTerm }: { threeTerm: Record<string, ThreeTermSection> | undefined }) {
  const entries = Object.entries(threeTerm ?? {}).sort(([a], [b]) => a.localeCompare(b))
  if (entries.length === 0) return null

  const available = entries.filter((e): e is [string, ThreeTermSection] => e[1].available === true)
  const verdict = crossLineVerdict(available)

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div>
        <p className="text-xs font-medium">Distance from the paper's own reported number, split three ways</p>
        <p className="text-xs text-muted-foreground">
          Exact arithmetic, not a controlled experiment: <span className="font-medium">signal + env</span> and{" "}
          <span className="font-medium">config</span> are the external implementer's choices, held apart by fixing
          the signal on one side; <span className="font-medium">agent vs paper</span> is our own paper-faithful
          baseline's distance from the paper and is <em>not</em> about the external implementer at all — it caps how
          much of the other two terms can be read as saying something about the paper, because if this term is
          already large, the config/signal terms are being measured relative to a baseline that itself doesn't
          match the paper. When this term is the largest of the three, prefer investigating the baseline replication
          itself over any config- or signal-level story.
        </p>
      </div>
      {verdict && (
        <div className="rounded-md border border-border bg-muted/40 p-2 text-xs">{verdict}</div>
      )}
      {available.length > 0 && <ThreeTermChart available={available} />}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {entries.map(([reference, section]) => (
          <ReferenceDetail key={reference} reference={reference} section={section} />
        ))}
      </div>
    </div>
  )
}
