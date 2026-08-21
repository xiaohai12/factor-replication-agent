import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

interface TableRefItem {
  table?: string
  row?: string
  column?: string
}

interface EvidenceItem {
  location?: string
  quote?: string
  interpretation?: string
  table_ref?: TableRefItem | null
}

/** A `SourcedValue[T]` field: `{value, evidence, status}` -- the atomic
 * evidence-carrying unit of a MethodSpec (src/infra/models/method_spec.py).
 * Every leaf field in the schema below is shaped like this. */
interface SourcedValueLike {
  value?: unknown
  evidence?: EvidenceItem[] | null
  status?: string
}

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "boolean") return value ? "yes" : "no"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function formatFilterValue(op: unknown, value: unknown): string {
  if (
    op === "intervals"
    && Array.isArray(value)
    && value.every((interval) => Array.isArray(interval) && interval.length === 2)
  ) {
    return value.map(([low, high]) => `${String(low)}–${String(high)}`).join(" OR ")
  }
  if (op === "in" && Array.isArray(value) && value.some((item) => Array.isArray(item))) {
    return `${fmt(value)} (invalid: use intervals)`
  }
  return fmt(value)
}

function isSourced(v: unknown): v is SourcedValueLike {
  return typeof v === "object" && v !== null && !Array.isArray(v) && "value" in (v as object)
}

/** Renders one paper citation as a small blockquote -- location + the exact
 * quote (or table cell reference) + the extractor's interpretation of it.
 * This is the "cite the paper" evidence every field-level value in a
 * MethodSpec can carry. */
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
              {e.table_ref?.table && (
                <div>
                  table {e.table_ref.table}
                  {e.table_ref.row && `, row ${e.table_ref.row}`}
                  {e.table_ref.column && `, column ${e.table_ref.column}`}
                </div>
              )}
              {e.interpretation && <div>{e.interpretation}</div>}
            </blockquote>
          ))}
        </div>
      )}
    </div>
  )
}

/** One field row: label on the left, value (+ optional status badge +
 * citation) on the right -- the atomic unit of the "board" view. Accepts
 * either a raw value or a `SourcedValue`-shaped object directly, so callers
 * don't have to unwrap `.value`/`.evidence`/`.status` themselves. */
function Field({
  label,
  value,
  evidence,
  status,
  secondary,
}: {
  label: string
  value: unknown
  evidence?: EvidenceItem[] | null
  status?: string
  secondary?: string | null
}) {
  const sourced = isSourced(value)
  const displayValue = sourced ? (value as SourcedValueLike).value : value
  const displayEvidence = evidence ?? (sourced ? (value as SourcedValueLike).evidence : null)
  const displayStatus = status ?? (sourced ? (value as SourcedValueLike).status : undefined)
  return (
    <div className="grid grid-cols-[minmax(0,220px)_1fr] gap-3 border-b border-border/60 py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <div>
        <div className="flex items-center gap-2">
          <span className="font-medium">{fmt(displayValue)}</span>
          {displayStatus && displayStatus !== "unspecified" && (
            <Badge variant="outline" className="text-[10px]">
              {displayStatus}
            </Badge>
          )}
        </div>
        {secondary && <div className="text-xs text-muted-foreground">{secondary}</div>}
        <Citation evidence={displayEvidence} />
      </div>
    </div>
  )
}

function Section({
  title,
  highlighted,
  children,
}: {
  title: string
  highlighted?: boolean
  children: React.ReactNode
}) {
  return (
    <div
      className={
        highlighted
          ? "flex flex-col gap-1 rounded-lg border-2 border-amber-400 bg-amber-50 p-3 dark:border-amber-600 dark:bg-amber-950/20"
          : "flex flex-col gap-1 rounded-lg border border-border p-3"
      }
    >
      <h4 className="text-sm font-semibold">{title}</h4>
      <div className="flex flex-col">{children}</div>
    </div>
  )
}

function period(p: Record<string, any> | undefined): string {
  if (!p) return "—"
  return `${fmt(p.start_year)}–${fmt(p.end_year)}`
}

/** Structured, human-readable "board" view of a `MethodSpec` (the paper-first
 * schema, src/infra/models/method_spec.py) -- every field shown as
 * label/value/citation instead of raw JSON. Reads defensively (every access
 * is optional) since a MethodSpec fresh out of extraction may be missing
 * whole sections; falls back to just omitting a Field/Section when its data
 * isn't present rather than crashing. */
export function MethodSpecBoard({
  spec,
  highlightConfigAndResults,
}: {
  spec: Record<string, any>
  /** Highlights the "Portfolio" (config) and "Reported results" (result)
   * sections -- used right after a resolve, when those are the two
   * sections most worth double-checking before moving on to codegen. */
  highlightConfigAndResults?: boolean
}) {
  const paper = spec.paper ?? {}
  const signal = spec.signal ?? {}
  const data = spec.data ?? {}
  const sample = spec.sample ?? {}
  const timing = spec.timing ?? {}
  const universe = spec.universe ?? {}
  const portfolio = spec.portfolio ?? {}
  const reported = spec.reported_results ?? {}
  const fields = (data.fields ?? []) as Array<Record<string, any>>
  const filters = (universe.filters ?? []) as Array<Record<string, any>>
  const sorts = (portfolio.sorts ?? []) as Array<Record<string, any>>
  const legs = (portfolio.legs ?? []) as Array<Record<string, any>>
  const missingPolicies = (portfolio.missing_policies ?? []) as Array<Record<string, any>>
  const transforms = (portfolio.transforms ?? []) as Array<Record<string, any>>
  const metrics = (reported.metrics ?? []) as Array<Record<string, any>>

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-lg border border-border p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">{spec.target_name || spec.factor_id}</h3>
          <Badge variant="outline">{fmt(spec.schema_version)}</Badge>
        </div>
        {paper.citation && <p className="mt-1 text-xs italic text-muted-foreground">{paper.citation}</p>}
        <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
          <span>factor_id: {fmt(spec.factor_id)}</span>
          <span>publication_year: {fmt(paper.publication_year)}</span>
          <span>data_coverage: {period(sample.data_coverage)}</span>
        </div>
      </div>

      <Section title="Signal">
        <Field label="Definition" value={signal.definition} />
        <Field label="Economic intuition" value={signal.economic_intuition} />
        <Field label="Direction" value={signal.direction} />
        <Field label="Category" value={signal.category} />
        <Field
          label="Formula"
          value={signal.formula?.output_concept}
          secondary={signal.formula?.paper_expression ? `Paper: ${signal.formula.paper_expression}` : null}
          evidence={signal.formula?.evidence}
        />
        {(signal.formula?.steps ?? []).map((s: Record<string, any>, i: number) => (
          <Field
            key={s.step_id ?? i}
            label={`Step: ${s.step_id ?? i + 1}`}
            value={s.description}
            secondary={s.expression || null}
            evidence={s.evidence}
            status={s.status}
          />
        ))}
        {signal.estimation && (
          <>
            <Field label="Estimation method" value={signal.estimation.method} />
            <Field
              label="Estimation model"
              value={signal.estimation.model_expression}
              secondary={signal.estimation.residual_definition || null}
              evidence={signal.estimation.evidence}
            />
          </>
        )}
      </Section>

      <Section title="Timing">
        <Field label="Formation rule" value={timing.formation_rule} />
        {timing.formation_month && <Field label="Formation month" value={timing.formation_month} />}
        <Field label="Rebalance frequency" value={timing.rebalance_frequency} />
        <Field label="Holding period" value={timing.holding_period} />
        <Field
          label="Data availability (lag)"
          value={`${fmt(timing.data_availability?.lag_value)} ${fmt(timing.data_availability?.lag_unit)} after ${fmt(timing.data_availability?.anchor)}`}
          secondary={timing.data_availability?.basis ? `basis: ${timing.data_availability.basis}` : null}
          evidence={timing.data_availability?.evidence}
        />
      </Section>

      <Section title="Sample">
        <Field label="Data coverage" value={period(sample.data_coverage)} />
        <Field label="Formation sample" value={period(sample.formation)} />
        <Field label="Reported-returns sample" value={period(sample.reported_returns)} />
      </Section>

      <Section title="Universe">
        <Field label="Description" value={universe.description} />
        {filters.length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Concept</TableHead>
                  <TableHead>Op</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filters.map((f, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs">{f.concept_id}</TableCell>
                    <TableCell className="text-xs">{f.op}</TableCell>
                    <TableCell className="text-xs">{formatFilterValue(f.op, f.value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <Section title="Portfolio" highlighted={highlightConfigAndResults}>
        <Field label="Construction type" value={portfolio.construction_type} />
        <Field label="Weighting" value={portfolio.weighting} />
        <Field label="Return combination" value={portfolio.return_combination} />
        {sorts.length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sort</TableHead>
                  <TableHead>Concept</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Group type / count</TableHead>
                  <TableHead>Breakpoint basis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorts.map((s) => (
                  <TableRow key={s.sort_id}>
                    <TableCell className="text-xs">{s.sort_id}</TableCell>
                    <TableCell className="text-xs">{s.concept_id}</TableCell>
                    <TableCell className="text-xs">{s.role}</TableCell>
                    <TableCell className="text-xs">{fmt(s.mode?.value)}</TableCell>
                    <TableCell className="text-xs">
                      {fmt(s.group_type?.value)} / {fmt(s.group_count)}
                    </TableCell>
                    <TableCell className="text-xs">{fmt(s.breakpoints?.basis?.value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {legs.length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Leg</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Selector (0-based)</TableHead>
                  <TableHead>Engine bucket</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {legs.map((l) => {
                  const selector = (l.selector ?? {}) as Record<string, unknown>
                  const entries = Object.entries(selector)
                  return (
                    <TableRow key={l.leg_id}>
                      <TableCell className="text-xs">{l.leg_id}</TableCell>
                      <TableCell className="text-xs">{l.side}</TableCell>
                      <TableCell className="text-xs">{fmt(l.selector)}</TableCell>
                      <TableCell className="text-xs">
                        {entries.length === 0 && "—"}
                        {entries.map(([sortId, rawIndex]) => {
                          const sort = sorts.find((s) => s.sort_id === sortId)
                          const groupCount = sort?.group_count as number | undefined
                          const index = Number(rawIndex)
                          const inRange =
                            groupCount == null || Number.isNaN(index)
                              ? null
                              : index >= 0 && index < groupCount
                          return (
                            <div key={sortId} className="flex items-center gap-1.5">
                              <span>
                                {sortId}: bucket {Number.isNaN(index) ? fmt(rawIndex) : index + 1}
                                {groupCount != null ? ` of ${groupCount}` : ""}
                              </span>
                              {inRange === false && (
                                <Badge variant="destructive" className="text-[10px]">
                                  out of range — this leg will always be empty
                                </Badge>
                              )}
                            </div>
                          )
                        })}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
        {missingPolicies.length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Missing-policy stage</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Threshold</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {missingPolicies.map((m, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs">{m.stage}</TableCell>
                    <TableCell className="text-xs">{fmt(m.action?.value)}</TableCell>
                    <TableCell className="text-xs">{fmt(m.threshold)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {transforms.length > 0 && (
          <div className="pt-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Transform</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Bounds</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transforms.map((t, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs">{t.kind}</TableCell>
                    <TableCell className="text-xs">{t.stage}</TableCell>
                    <TableCell className="text-xs">{fmt(t.bounds)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {fields.length > 0 && (
        <Section title="Data fields">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Concept</TableHead>
                <TableHead>Paper name</TableHead>
                <TableHead>Source hint</TableHead>
                <TableHead>Roles</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fields.map((f) => (
                <TableRow key={f.concept_id}>
                  <TableCell className="text-xs">{f.concept_id}</TableCell>
                  <TableCell className="text-xs">{f.name_in_paper}</TableCell>
                  <TableCell className="text-xs">{f.paper_source_hint}</TableCell>
                  <TableCell className="text-xs">{(f.roles ?? []).join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {metrics.length > 0 && (
        <Section title="Reported results" highlighted={highlightConfigAndResults}>
          <p className="text-xs text-muted-foreground">
            primary metric: <span className="font-mono">{fmt(reported.primary_metric_id)}</span>
          </p>
          {reported.comparison_derivation && (
            <p className="mt-1 text-xs text-muted-foreground">
              derivation: <span className="font-mono">{fmt(reported.comparison_derivation.metric_id)}</span>{" "}
              = {fmt(reported.comparison_derivation.high_metric_id)} − {fmt(reported.comparison_derivation.low_metric_id)}
              {reported.comparison_derivation.use_as_primary_comparison
                ? " (used as primary comparison)"
                : " (recorded, not used as primary comparison)"}
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Weighting</TableHead>
                <TableHead>Estimand</TableHead>
                <TableHead>Adjustment</TableHead>
                <TableHead>Estimate</TableHead>
                <TableHead>Stat</TableHead>
                <TableHead>Sample</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {metrics.map((m) => (
                <TableRow key={m.metric_id}>
                  <TableCell className="text-xs">{m.metric_id}</TableCell>
                  <TableCell className="text-xs">{m.label}</TableCell>
                  <TableCell className="text-xs">{fmt(m.weighting)}</TableCell>
                  <TableCell className="text-xs">{m.estimand}</TableCell>
                  <TableCell className="text-xs">{m.adjustment_model}</TableCell>
                  <TableCell className="text-xs">
                    {fmt(m.estimate)} {m.unit}
                  </TableCell>
                  <TableCell className="text-xs">
                    {m.statistic ? `${m.statistic.kind}=${fmt(m.statistic.value)}` : "—"}
                  </TableCell>
                  <TableCell className="text-xs">{period(m.sample_period)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {spec.notes && (
        <Section title="Notes">
          <p className="text-sm">{spec.notes}</p>
        </Section>
      )}
    </div>
  )
}
