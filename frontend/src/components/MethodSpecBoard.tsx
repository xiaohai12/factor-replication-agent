import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"

interface EvidenceItem {
  location?: string
  quote?: string
  interpretation?: string
  source_type?: string
}

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "boolean") return value ? "yes" : "no"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** Renders one paper citation as a small blockquote -- location + the exact
 * quote + the extractor's interpretation of it. This is the "cite the
 * paper" evidence every field-level value in a MethodSpec can carry. */
function Citation({ evidence }: { evidence?: EvidenceItem[] | null }) {
  const [open, setOpen] = useState(false)
  if (!evidence || evidence.length === 0) return null
  return (
    <div className="mt-1">
      <button
        type="button"
        className="text-[11px] text-muted-foreground underline"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "hide citation" : `cite paper (${evidence.length})`}
      </button>
      {open && (
        <div className="mt-1 flex flex-col gap-2">
          {evidence.map((e, i) => (
            <blockquote key={i} className="border-l-2 border-border pl-2 text-xs text-muted-foreground">
              {e.location && <div className="font-medium">{e.location}</div>}
              {e.quote && <div className="italic">"{e.quote}"</div>}
              {e.interpretation && <div>{e.interpretation}</div>}
            </blockquote>
          ))}
        </div>
      )}
    </div>
  )
}

/** One field row: label on the left, value (+ optional citation) on the
 * right -- the atomic unit of the "board" view. */
function Field({
  label,
  value,
  evidence,
  secondary,
}: {
  label: string
  value: unknown
  evidence?: EvidenceItem[] | null
  secondary?: string | null
}) {
  return (
    <div className="grid grid-cols-[minmax(0,220px)_1fr] gap-3 border-b border-border/60 py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <div>
        <div className="font-medium">{fmt(value)}</div>
        {secondary && <div className="text-xs text-muted-foreground">{secondary}</div>}
        <Citation evidence={evidence} />
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border p-3">
      <h4 className="text-sm font-semibold">{title}</h4>
      <div className="flex flex-col">{children}</div>
    </div>
  )
}

/** Structured, human-readable "board" view of a MethodSpec -- every field
 * shown as label/value/citation instead of raw JSON. Reads defensively
 * (every access is optional) since a MethodSpec fresh out of extraction may
 * be missing whole sections; falls back to just omitting a Field/Section
 * when its data isn't present rather than crashing. */
export function MethodSpecBoard({ spec }: { spec: Record<string, any> }) {
  const signal = spec.signal ?? {}
  const portfolio = spec.portfolio ?? {}
  const reported = spec.reported_results ?? {}
  const data = spec.data ?? {}
  const ambiguous = (spec.ambiguous_fields ?? []) as Array<Record<string, any>>
  const resolutions = (spec.resolution_log ?? []) as Array<Record<string, any>>

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-lg border border-border p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">{spec.factor_name || spec.factor_id}</h3>
          <div className="flex gap-1">
            {spec.review_status && <Badge variant="outline">{spec.review_status}</Badge>}
            {spec.codegen_ready && <Badge variant="default">codegen ready</Badge>}
            {ambiguous.length > 0 && <Badge variant="destructive">{ambiguous.length} ambiguous</Badge>}
          </div>
        </div>
        {spec.paper_ref && <p className="mt-1 text-xs italic text-muted-foreground">{spec.paper_ref}</p>}
        {spec.economic_intuition && <p className="mt-2 text-sm">{spec.economic_intuition}</p>}
        <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
          <span>factor_id: {fmt(spec.factor_id)}</span>
          <span>sign: {fmt(spec.sign)}</span>
          <span>
            sample: {fmt(spec.sample_start_year)}–{fmt(spec.sample_end_year)}
          </span>
        </div>
      </div>

      <Section title="Signal">
        <Field
          label="Formula"
          value={signal.formula?.expression}
          secondary={signal.formula?.paper_expression ? `Paper: ${signal.formula.paper_expression}` : null}
          evidence={signal.formula?.evidence}
        />
        <Field label="Sign" value={signal.sign} />
        <Field
          label="Formation month / rebalance / holding period"
          value={`${fmt(signal.timing?.formation_month)} / ${fmt(signal.timing?.rebalance_frequency)} / ${fmt(signal.timing?.holding_period)}mo`}
          evidence={signal.timing?.evidence}
        />
        <Field label="Accounting lag (months)" value={signal.timing?.accounting_lag} />
        <Field
          label="Missing-value policy"
          value={signal.missing_policy?.action}
          evidence={signal.missing_policy?.evidence}
        />
      </Section>

      <Section title="Portfolio">
        <Field label="Universe" value={portfolio.universe} evidence={portfolio.evidence} />
        <Field
          label="Breakpoint source / groups"
          value={`${fmt(portfolio.sort?.breakpoint_source)} / ${fmt(portfolio.sort?.ls_quantile)}`}
          evidence={portfolio.sort?.evidence}
        />
        <Field label="Weighting" value={portfolio.weighting} />
        <Field
          label="Long leg / short leg"
          value={`${fmt(portfolio.long_leg)} / ${fmt(portfolio.short_leg)}`}
          secondary={portfolio.implied_factor_direction?.note}
        />
      </Section>

      <Section title="Reported results">
        <Field label="Return horizon" value={reported.return_horizon} />
        <Field
          label="Input return"
          value={reported.return_calculation?.input_return?.expression}
          secondary={reported.return_calculation?.input_return?.data_frequency}
          evidence={
            reported.return_calculation?.input_return?.source
              ? [reported.return_calculation.input_return.source]
              : null
          }
        />
        <Field
          label="Portfolio return construction"
          value={reported.return_calculation?.portfolio_return?.construction_type}
          secondary={reported.return_calculation?.portfolio_return?.return_combination?.note}
          evidence={
            reported.return_calculation?.portfolio_return?.source
              ? [reported.return_calculation.portfolio_return.source]
              : null
          }
        />
        {reported.spreads && Object.keys(reported.spreads).length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Reported spread</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>t-stat</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(reported.spreads as Record<string, any>).map(([key, s]) => (
                  <TableRow key={key}>
                    <TableCell className="text-xs">{key}</TableCell>
                    <TableCell className="text-xs">{fmt(s.value)}</TableCell>
                    <TableCell className="text-xs">{fmt(s.t_stat)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {data.required_fields?.length > 0 && (
        <Section title="Data sources">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Concept</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data.required_fields as Array<Record<string, any>>).map((f) => (
                <TableRow key={f.field}>
                  <TableCell className="text-xs">{f.field}</TableCell>
                  <TableCell className="text-xs">{f.concept}</TableCell>
                  <TableCell className="text-xs">{f.source_detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {ambiguous.length > 0 && (
        <Section title="Ambiguous fields (need human review)">
          {ambiguous.map((a, i) => (
            <div key={i} className={cn("py-2", i > 0 && "border-t border-border/60")}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{a.field}</span>
                <Badge variant="outline">{fmt(a.confidence)} confidence</Badge>
                <Badge variant="outline">{fmt(a.empirical_impact)} impact</Badge>
              </div>
              {a.candidate_value != null && (
                <p className="text-xs text-muted-foreground">candidate: {fmt(a.candidate_value)}</p>
              )}
              <Citation evidence={a.evidence} />
            </div>
          ))}
        </Section>
      )}

      {resolutions.length > 0 && (
        <Section title="Resolution log (human decisions)">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Old → new</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>By</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {resolutions.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="text-xs">{r.field_path}</TableCell>
                  <TableCell className="text-xs">
                    {fmt(r.old_value)} → {fmt(r.new_value)}
                  </TableCell>
                  <TableCell className="text-xs">{r.reason}</TableCell>
                  <TableCell className="text-xs">{r.reviewer}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
    </div>
  )
}
