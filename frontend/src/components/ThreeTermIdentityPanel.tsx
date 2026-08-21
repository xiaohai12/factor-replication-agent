/** step7's `three_term_identity` section: how far an EXTERNAL implementer's
 * own published number (C&Z / HXZ) sits from the PAPER's own reported
 * number, split into the signal, the portfolio settings, and our own
 * replication error (docs/paper-outline.md C1).
 *
 * Rendered as a plain table rather than a waterfall/stacked bar even though
 * the three terms DO sum exactly here: a stacked visual would invite reading
 * the components as comparably-clean effects, and they aren't -- only the
 * settings term holds the signal fixed on both sides. The purity note and
 * the window caveat therefore render alongside the numbers, never behind a
 * disclosure the reader can skip. */

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

const TERM_LABELS: Record<string, string> = {
  signal_and_environment: "Signal computation (+ data vintage / engine)",
  config: "Portfolio-construction settings alone",
  agent_replication_residual: "Our own run vs the paper's number",
}

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "n/a"
  return value.toFixed(4)
}

function window_(start?: number | null, end?: number | null): string {
  if (start == null && end == null) return "unstated"
  return `${start ?? "?"}-${end ?? "?"}`
}

function ReferenceCard({ reference, section }: { reference: string; section: ThreeTermSection }) {
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
  const ordered = Object.entries(terms).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <p className="text-xs font-medium">
        {label} &minus; the paper's own reported spread ={" "}
        <span className="font-mono">{fmt(section.total_gap)}</span> per month
      </p>
      <table className="w-full text-xs">
        <thead className="text-muted-foreground">
          <tr>
            <th className="text-left font-normal">Where the distance sits</th>
            <th className="text-right font-normal">Monthly</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map(([name, value]) => (
            <tr key={name} className={name === section.largest_term ? "font-medium" : undefined}>
              <td className="py-0.5">{TERM_LABELS[name] ?? name}</td>
              <td className="py-0.5 text-right font-mono">{fmt(value)}</td>
            </tr>
          ))}
          <tr className="text-muted-foreground">
            <td className="py-0.5">Residual (zero by construction -- arithmetic check)</td>
            <td className="py-0.5 text-right font-mono">{fmt(section.residual)}</td>
          </tr>
        </tbody>
      </table>
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
  const entries = Object.entries(threeTerm ?? {})
  if (entries.length === 0) return null

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <div>
        <p className="text-xs font-medium">
          Distance from the paper's own reported number, split three ways
        </p>
        <p className="text-xs text-muted-foreground">
          An exact arithmetic split, not a controlled experiment. The three parts are not equally clean:
          only the settings row holds the signal fixed on both sides -- the first row also absorbs
          data-vintage and engine differences, and the last is our own replication error rather than
          anything the paper left ambiguous. The numbers being compared do not share a sample window or
          estimator.
        </p>
      </div>
      {entries.sort(([a], [b]) => a.localeCompare(b)).map(([reference, section]) => (
        <ReferenceCard key={reference} reference={reference} section={section} />
      ))}
    </div>
  )
}
