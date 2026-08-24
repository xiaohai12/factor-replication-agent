import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { JsonTree } from "@/components/JsonTree"
import { ReturnChart } from "@/components/ReturnChart"
import { fetchEvidenceFiles, fetchReturnSeries, fetchRuns } from "@/lib/evidence"
import { latestSuccessRef } from "@/lib/manifestArtifacts"
import { sessionApi } from "@/lib/sessionApi"
import type { SessionManifest, StepAttempt } from "@/lib/types"
import { cn } from "@/lib/utils"

interface ReportedMetric {
  metric_id: string
  label: string
  estimand: string
  adjustment_model: string
  estimate: number
  statistic?: { kind: string; value: number } | null
  sample_period?: { start_year?: number | null; end_year?: number | null } | null
  portfolio_selector?: Record<string, number> | null
}

interface ComparisonDerivation {
  metric_id: string
  label: string
  operation: "high_minus_low"
  high_metric_id: string
  low_metric_id: string
  use_as_primary_comparison?: boolean
}

function executionId(attempt: StepAttempt | undefined): string | undefined {
  const raw = attempt?.output_refs.execution_ids
  if (!raw) return undefined
  const ids = JSON.parse(raw) as string[]
  return ids[0]
}

function useStep5Run(attempt: StepAttempt | undefined) {
  const runId = executionId(attempt)
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => fetchRuns(),
    enabled: !!runId,
  })
  const run = runsQuery.data?.find((r) => r.run_id === runId)
  return { run, isLoading: runsQuery.isLoading, runId }
}

/** step3's resolved config (`sample_start_year`/`sample_end_year`/
 * `publication_year`, needed to date-range the sample-period breakdown) and
 * resolved spec (`paper.reported_results`, the paper's own number) --
 * neither lives on the step5 `RunRecord` itself, only on step3's own
 * artifacts, so this walks the manifest the same way `Step4RepairCard`
 * does for step3's plugin code. */
function useStep3Facts(sessionId: string, manifest: SessionManifest | undefined) {
  const configRef = latestSuccessRef(manifest, 3, "config_ref")
  const specRef = latestSuccessRef(manifest, 3, "spec_ref")
  const configQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 3, configRef],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, configRef!),
    enabled: !!configRef,
  })
  const specQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 3, specRef],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, specRef!),
    enabled: !!specRef,
  })
  const config = configQuery.data ? (JSON.parse(configQuery.data.content) as Record<string, unknown>) : undefined
  const spec = specQuery.data ? (JSON.parse(specQuery.data.content) as Record<string, unknown>) : undefined
  return { config, spec }
}

function reportedPrimaryMetric(spec: Record<string, unknown> | undefined): ReportedMetric | undefined {
  const paper = spec?.paper as Record<string, unknown> | undefined
  const rr = paper?.reported_results as {
    primary_metric_id?: string
    metrics?: ReportedMetric[]
    comparison_derivation?: ComparisonDerivation | null
  } | undefined
  if (!rr?.metrics) return undefined
  const derivation = rr.comparison_derivation
  let metric: ReportedMetric | undefined
  if (derivation?.use_as_primary_comparison && derivation.operation === "high_minus_low") {
    const high = rr.metrics.find((m) => m.metric_id === derivation.high_metric_id)
    const low = rr.metrics.find((m) => m.metric_id === derivation.low_metric_id)
    if (high && low) {
      metric = { ...high, metric_id: derivation.metric_id, label: `${derivation.label} (derived)`, estimand: "spread", estimate: high.estimate - low.estimate, statistic: null }
    }
  }
  metric ??= rr.metrics.find((m) => m.metric_id === rr.primary_metric_id)
  if (!metric) return undefined

  // Paper tables often label the spread high-minus-low even when the
  // executable strategy's economic direction is low-minus-high. Align the
  // displayed paper estimate to the engine's long/short legs using only the
  // reviewed MethodSpec; preserve the stored source metric unchanged.
  const portfolio = paper?.portfolio as {
    sorts?: { sort_id?: string; role?: string }[]
    legs?: { side?: string; selector?: Record<string, number> }[]
  } | undefined
  const targetSort = portfolio?.sorts?.find((s) => s.role === "target") ?? portfolio?.sorts?.[0]
  const sortId = targetSort?.sort_id
  const selector = metric.portfolio_selector
  if (!sortId || !selector) return metric

  const paperHigh = selector[`${sortId}_high`]
  const paperLow = selector[`${sortId}_low`]
  const engineLong = portfolio?.legs?.find((leg) => leg.side === "long")?.selector?.[sortId]
  const engineShort = portfolio?.legs?.find((leg) => leg.side === "short")?.selector?.[sortId]
  if (paperHigh !== engineShort || paperLow !== engineLong) return metric

  return {
    ...metric,
    label: `${metric.label} (direction-aligned to engine long-minus-short)`,
    estimate: -metric.estimate,
    statistic: metric.statistic
      ? { ...metric.statistic, value: -metric.statistic.value }
      : metric.statistic,
  }
}

// Which column of the breakdown table the paper's own `estimate` belongs in
// -- an `estimand: "alpha"` metric is a risk-adjusted alpha, not the raw
// mean/spread, and which alpha column depends on `adjustment_model`.
function paperMetricColumn(metric: ReportedMetric): "mean" | "alpha_capm" | "alpha_ff3" | "alpha_ff5" {
  if (metric.estimand !== "alpha") return "mean"
  if (metric.adjustment_model === "capm") return "alpha_capm"
  if (metric.adjustment_model === "ff3") return "alpha_ff3"
  if (metric.adjustment_model === "ff5") return "alpha_ff5"
  return "mean"
}

function periodRange(
  kind: "insamp" | "between" | "postpub",
  start: number | undefined,
  end: number | undefined,
  pub: number | undefined,
  lastDataYear: number | undefined,
): string {
  if (kind === "insamp") return start != null && end != null ? `${start}–${end}` : "—"
  if (kind === "between") return end != null && pub != null ? `${end + 1}–${pub}` : "—"
  // The actual last year the return series covers, not "present" -- the
  // data's own end date can trail well behind today (e.g. a snapshot taken
  // months/years ago), so assuming "present" would overstate the window.
  if (pub == null) return "—"
  return lastDataYear != null ? `${pub + 1}–${lastDataYear}` : `${pub + 1}–?`
}

// yyyymm (e.g. 202512) -> its calendar year -- every OTHER date range in
// this table is year-only (the MethodSpec's sample_start_year/end_year/
// publication_year have no month granularity), so the full-sample row must
// match that granularity instead of showing a mismatched year+month range.
function yearOf(yyyymm: number): number {
  return Math.floor(yyyymm / 100)
}

function shortHash(hash: string | undefined): string {
  if (!hash) return "—"
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash
}

function formatMetric(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4)
  return String(value)
}

// A period's `mean_monthly_return` (by_sample_period entries) vs. the
// top-level RunMetrics' `mean_return` -- same quantity, different key name.
function periodMean(period: Record<string, unknown> | undefined): unknown {
  return period?.mean_monthly_return ?? period?.mean_return
}

const SAMPLE_PERIODS = [
  { key: "insamp", label: "In-sample" },
  { key: "between", label: "Between" },
  { key: "postpub", label: "Post-publication" },
] as const

// Full-sample-only stats with no per-period equivalent (unlike
// alpha_capm/ff3/ff5, which `BacktestExecutor.run_with_config` now also
// regresses per sample-period segment -- see `by_sample_period` entries).
const EXTRA_METRIC_KEYS = ["coverage", "microcap_share"] as const

/** Renders in the request/result grid's "Result" slot for step5 -- live job
 * log (step5 IS a job) plus a compact full-sample glance. The per-period
 * breakdown (this would otherwise duplicate) lives ONLY in the "Step
 * output" card below via `Step5Output`. */
export function Step5HeadlineCard({ attempt }: { attempt: StepAttempt | undefined }) {
  const { run, isLoading } = useStep5Run(attempt)
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (!run) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
  const metrics = run.metrics ?? {}
  return (
    <div className="grid grid-cols-3 gap-2">
      {(["mean_return", "t_stat", "sharpe_ratio"] as const).map((key) => (
        <div key={key} className="rounded-md border border-border p-2 text-center">
          <p className="text-[10px] tracking-wide text-muted-foreground uppercase">{key}</p>
          <p className="text-lg font-semibold">{formatMetric(metrics[key])}</p>
        </div>
      ))}
    </div>
  )
}

/** Renders in the "Step output" card below the request/result grid --
 * entirely from PERSISTED evidence (the global `/api/runs` + the run's own
 * `factor_id` for `return_series.csv`), never the job's transient result,
 * so it survives a page reload (unlike step4's repair_history, run
 * metrics/series are fully written to the evidence store by the time this
 * step succeeds). */
export function Step5Output({
  sessionId,
  attempt,
  manifest,
}: {
  sessionId: string
  attempt: StepAttempt | undefined
  manifest: SessionManifest | undefined
}) {
  const { run, isLoading, runId } = useStep5Run(attempt)
  const seriesQuery = useQuery({
    queryKey: ["return-series", run?.factor_id, runId],
    queryFn: () => fetchReturnSeries(run!.factor_id, runId!),
    enabled: !!run,
  })
  const filesQuery = useQuery({
    queryKey: ["evidence-files", run?.factor_id, runId],
    queryFn: () => fetchEvidenceFiles(run!.factor_id, runId!),
    enabled: !!run,
  })
  const { config, spec } = useStep3Facts(sessionId, manifest)

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (!run) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>

  const metrics = run.metrics ?? {}
  const bySamplePeriod = (metrics.by_sample_period as Record<string, Record<string, unknown>> | undefined) ?? {}
  const provenance = run.runtime_provenance ?? {}
  const extraMetrics = Object.fromEntries(
    EXTRA_METRIC_KEYS.filter((k) => metrics[k] !== undefined && metrics[k] !== null).map((k) => [k, metrics[k]]),
  )

  const sampleStartYear = config?.sample_start_year as number | undefined
  const sampleEndYear = config?.sample_end_year as number | undefined
  const publicationYear = config?.publication_year as number | undefined
  const paperMetric = reportedPrimaryMetric(spec)
  const fullSampleRange =
    seriesQuery.data && seriesQuery.data.length > 0
      ? `${yearOf(seriesQuery.data[0].yyyymm)}–${yearOf(seriesQuery.data[seriesQuery.data.length - 1].yyyymm)}`
      : "—"
  const lastDataYear =
    seriesQuery.data && seriesQuery.data.length > 0
      ? yearOf(seriesQuery.data[seriesQuery.data.length - 1].yyyymm)
      : undefined

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-muted-foreground">run: {shortHash(run.run_id)}</span>
        <Badge variant="outline">track: {run.track}</Badge>
        <Badge variant={run.status === "success" ? "default" : "destructive"}>status: {run.status}</Badge>
      </div>

      {seriesQuery.data && <ReturnChart data={seriesQuery.data} />}

      <div>
        <p className="mb-1 text-xs font-medium">Sample-period breakdown</p>
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-1 pr-3 text-left font-medium">Period</th>
              <th className="py-1 pr-3 text-left font-medium">Date range</th>
              <th className="py-1 pr-3 text-left font-medium">Mean monthly return</th>
              <th className="py-1 pr-3 text-left font-medium">t-stat</th>
              <th className="py-1 pr-3 text-left font-medium">Sharpe</th>
              <th className="py-1 pr-3 text-left font-medium">n_months</th>
              <th className="py-1 pr-3 text-left font-medium">Alpha (CAPM)</th>
              <th className="py-1 pr-3 text-left font-medium">Alpha (FF3)</th>
              <th className="py-1 text-left font-medium">Alpha (FF5)</th>
            </tr>
          </thead>
          <tbody>
            {paperMetric && (
              <tr className="border-b border-border/50 bg-sky-50 dark:bg-sky-950/20">
                <td className="py-1 pr-3 font-medium" title={paperMetric.label}>
                  Paper reported
                  <span className="ml-1 font-normal text-muted-foreground">
                    ({paperMetric.estimand}
                    {paperMetric.estimand === "alpha" ? `/${paperMetric.adjustment_model}` : ""})
                  </span>
                </td>
                <td className="py-1 pr-3">
                  {paperMetric.sample_period?.start_year != null && paperMetric.sample_period?.end_year != null
                    ? `${paperMetric.sample_period.start_year}–${paperMetric.sample_period.end_year}`
                    : "—"}
                </td>
                <td className="py-1 pr-3">
                  {paperMetricColumn(paperMetric) === "mean" ? formatMetric(paperMetric.estimate) : "—"}
                </td>
                <td className="py-1 pr-3">
                  {paperMetric.statistic?.kind === "t_stat" ? formatMetric(paperMetric.statistic.value) : "—"}
                </td>
                <td className="py-1 pr-3">—</td>
                <td className="py-1 pr-3">—</td>
                <td className="py-1 pr-3">
                  {paperMetricColumn(paperMetric) === "alpha_capm" ? formatMetric(paperMetric.estimate) : "—"}
                </td>
                <td className="py-1 pr-3">
                  {paperMetricColumn(paperMetric) === "alpha_ff3" ? formatMetric(paperMetric.estimate) : "—"}
                </td>
                <td className="py-1">
                  {paperMetricColumn(paperMetric) === "alpha_ff5" ? formatMetric(paperMetric.estimate) : "—"}
                </td>
              </tr>
            )}
            <tr className="border-b border-border/50">
              <td className="py-1 pr-3">All (engine, full sample)</td>
              <td className="py-1 pr-3">{fullSampleRange}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.mean_return)}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.t_stat)}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.sharpe_ratio)}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.n_months)}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.alpha_capm)}</td>
              <td className="py-1 pr-3">{formatMetric(metrics.alpha_ff3)}</td>
              <td className="py-1">{formatMetric(metrics.alpha_ff5)}</td>
            </tr>
            {SAMPLE_PERIODS.every(({ key }) => !bySamplePeriod[key]) ? (
              <tr>
                <td className="py-1 text-muted-foreground" colSpan={9}>
                  Per-period breakdown not available -- publication_year wasn't set for this run.
                </td>
              </tr>
            ) : (
              SAMPLE_PERIODS.map(({ key, label }) => {
                const period = bySamplePeriod[key]
                return (
                  // Same highlight as the "Paper reported" row above -- these
                  // two are the ones meant to be compared directly (the
                  // paper's own sample window IS "in-sample" by definition).
                  <tr
                    key={key}
                    className={cn(
                      "border-b border-border/50 last:border-0",
                      key === "insamp" && "bg-sky-50 dark:bg-sky-950/20",
                    )}
                  >
                    <td className="py-1 pr-3">{label}</td>
                    <td className="py-1 pr-3">
                      {periodRange(key, sampleStartYear, sampleEndYear, publicationYear, lastDataYear)}
                    </td>
                    <td className="py-1 pr-3">{period ? formatMetric(periodMean(period)) : "—"}</td>
                    <td className="py-1 pr-3">{period ? formatMetric(period.t_stat) : "—"}</td>
                    <td className="py-1 pr-3">{period ? formatMetric(period.sharpe_ratio) : "—"}</td>
                    <td className="py-1 pr-3">{period ? formatMetric(period.n_months) : "—"}</td>
                    <td className="py-1 pr-3">{period ? formatMetric(period.alpha_capm) : "—"}</td>
                    <td className="py-1 pr-3">{period ? formatMetric(period.alpha_ff3) : "—"}</td>
                    <td className="py-1">{period ? formatMetric(period.alpha_ff5) : "—"}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
        {Object.keys(extraMetrics).length > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            {Object.entries(extraMetrics)
              .map(([k, v]) => `${k}: ${formatMetric(v)}`)
              .join("   ·   ")}
          </p>
        )}
      </div>

      <details>
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Debug / provenance</summary>
        <div className="mt-2 flex flex-col gap-2 text-xs">
          <div className="flex flex-wrap gap-3 font-mono text-muted-foreground">
            <span>code_hash: {shortHash(run.code_hash)}</span>
            <span>config_hash: {shortHash(run.config_hash)}</span>
            <span>data_snapshot_hash: {shortHash(run.data_snapshot_hash)}</span>
            <span>method_spec_hash: {shortHash(run.method_spec_hash)}</span>
          </div>
          {Object.keys(provenance).length > 0 && (
            <div>
              <p className="mb-1 font-medium">Runtime provenance</p>
              {provenance.git_dirty === true && (
                <p className="text-destructive">⚑ git_dirty: true -- run against an uncommitted worktree</p>
              )}
              <JsonTree name="runtime_provenance" data={provenance} />
            </div>
          )}
          {filesQuery.data && filesQuery.data.length > 0 && (
            <div>
              <p className="mb-1 font-medium">Evidence files</p>
              {filesQuery.data.map((f) => (
                <a
                  key={f}
                  className="block text-primary underline"
                  href={`/api/evidence/${run.factor_id}/${run.run_id}/download/${encodeURIComponent(f)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {f}
                </a>
              ))}
            </div>
          )}
          <JsonTree name="run_record" data={run} />
        </div>
      </details>
    </div>
  )
}
