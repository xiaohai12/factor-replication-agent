import { useEffect, useState } from "react"
import { useQuery, useQueries } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { JsonTree } from "@/components/JsonTree"
import { MultiTrackChart, type TrackSeries } from "@/components/MultiTrackChart"
import { api } from "@/lib/api"
import { fetchReturnSeries, fetchRuns, type RunRecord } from "@/lib/evidence"
import { cn } from "@/lib/utils"
import type { StepAttempt } from "@/lib/types"

function executionIds(attempt: StepAttempt | undefined): string[] {
  const raw = attempt?.output_refs.execution_ids
  return raw ? (JSON.parse(raw) as string[]) : []
}

function useStep6Runs(attempt: StepAttempt | undefined) {
  const ids = executionIds(attempt)
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => fetchRuns(),
    enabled: ids.length > 0,
  })
  const runs = (runsQuery.data ?? []).filter((r) => ids.includes(r.run_id))
  return { runs, isLoading: runsQuery.isLoading }
}

// original_method pinned first when present, matching step7's own default
// baseline (`BASELINE_TRACK` in bundle.py) -- step6 has no baseline concept
// of its own yet (that's only computed once step7 runs), so this is a
// best-effort stand-in, not the same field.
function orderWithBaseline(runs: RunRecord[]): RunRecord[] {
  const baseline = runs.find((r) => r.track === "original_method")
  if (!baseline) return runs
  return [baseline, ...runs.filter((r) => r !== baseline)]
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

function formatConfigValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

// Metadata keys rendered separately elsewhere (or not at all here), never as
// an ordinary config-per-track row -- mirrors Step3Output.tsx's own NON_ROW_KEYS.
const NON_ROW_KEYS = new Set(["substitutions", "defaults_applied", "unapplied_universe_filters"])

interface DefaultApplied {
  config_key: string
  reason: string
}

/** `config_key`s this track's `defaults_applied` list marks as engine-filled
 * (the paper didn't specify a value, so a convention default was used) --
 * everything else in the table is what the paper/reviewed spec actually
 * resolved to. */
function defaultedKeys(config: Record<string, unknown> | undefined): Map<string, string> {
  const entries = (config?.defaults_applied as DefaultApplied[] | undefined) ?? []
  return new Map(entries.map((d) => [d.config_key, d.reason]))
}

/** Each track's RESOLVED config (`registry.build_config()`'s output) --
 * read from `comparison.json` via a step6-scoped preview endpoint, since
 * that file is already written as a side effect of step6's own run (see
 * `GET /steps/6/track-configs` in backend/routers/replication.py) and
 * doesn't require step7 to have ever been triggered for this session. */
function useTrackConfigs(sessionId: string, experimentBatchId: string | undefined) {
  const query = useQuery({
    queryKey: ["step6-track-configs", sessionId, experimentBatchId],
    queryFn: () =>
      api.get<Record<string, Record<string, unknown>>>(
        `/api/sessions/${sessionId}/steps/6/track-configs?experiment_batch_id=${encodeURIComponent(experimentBatchId!)}`,
      ),
    enabled: !!experimentBatchId,
  })
  return { configs: query.data, isLoading: query.isLoading }
}

/** Renders in the request/result grid's "Result" slot for step6 -- live job
 * log (step6 IS a job) plus a brief batch summary; the full cross-track
 * table lives in `Step6Output` below. */
export function Step6BatchSummaryCard({ attempt }: { attempt: StepAttempt | undefined }) {
  const { runs, isLoading } = useStep6Runs(attempt)
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (runs.length === 0) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
  const invalidated = runs.some((r) => r.batch_invalidated)
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge variant="outline">{runs.length} tracks</Badge>
      <Badge variant={invalidated ? "destructive" : "default"}>
        batch: {invalidated ? "invalidated" : "consistent"}
      </Badge>
    </div>
  )
}

/** Renders in the "Step output" card below the request/result grid --
 * cross-track comparison table (baseline pinned first) + the overlay
 * chart, entirely from PERSISTED `RunRecord`s (global `/api/runs`, same
 * factor_id caveat as step5 -- see lib/evidence.ts). */
export function Step6Output({
  sessionId,
  attempt,
  paperReported,
  czReported,
  hxzReported,
}: {
  sessionId: string
  attempt: StepAttempt | undefined
  paperReported?: { mean_return?: number; t_stat?: number } | null
  czReported?: { mean_return: number | null; t_stat: number | null } | null
  hxzReported?: {
    originalInsample: { mean_return: number | null; t_stat: number | null } | null
    hxzPaperSample: { mean_return: number | null; t_stat: number | null } | null
  } | null
}) {
  const { runs, isLoading } = useStep6Runs(attempt)
  const ordered = orderWithBaseline(runs)
  const baselineTrack = ordered[0]?.track
  const { configs } = useTrackConfigs(sessionId, attempt?.output_refs.experiment_batch_id)
  // Which tracks to show -- shared between "Config per track" and the chart
  // below, since a batch with auto-attribution's factorial_*/ablation_*
  // tracks can easily reach 10+ tracks and the user may only want a
  // handful side by side/plotted at once. Defaults to every track (matches
  // the prior always-show-everything behavior); the baseline is always
  // force-included (its checkbox is disabled) since both sections use it
  // as the pinned reference/delta basis. `null` means "not yet
  // initialized"; new tracks appearing after a re-run default to selected
  // too. Keyed off the track-name list (a stable string), not `ordered`
  // itself (a new array every render), to avoid re-running on every render.
  const orderedTrackNames = ordered.map((r) => r.track).join(",")
  const [selectedTracks, setSelectedTracks] = useState<Set<string> | null>(null)
  useEffect(() => {
    const known = orderedTrackNames ? orderedTrackNames.split(",") : []
    setSelectedTracks((prev) => {
      const next = new Set(prev ?? known)
      for (const track of known) {
        if (!(prev?.has(track) ?? false)) next.add(track)
      }
      if (baselineTrack) next.add(baselineTrack)
      return next
    })
  }, [orderedTrackNames, baselineTrack])
  const isTrackSelected = (track: string) => track === baselineTrack || (selectedTracks?.has(track) ?? true)
  const toggleTrack = (track: string) => {
    if (track === baselineTrack) return // baseline can't be unchecked
    setSelectedTracks((prev) => {
      const next = new Set(prev ?? ordered.map((r) => r.track))
      if (next.has(track)) next.delete(track)
      else next.add(track)
      return next
    })
  }
  const seriesQueries = useQueries({
    queries: ordered.map((run) => ({
      queryKey: ["return-series", run.factor_id, run.run_id],
      queryFn: () => fetchReturnSeries(run.factor_id, run.run_id),
      enabled: true,
    })),
  })

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (runs.length === 0) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>

  const first = runs[0]
  const invalidated = runs.some((r) => r.batch_invalidated)
  const invalidationReason = runs.find((r) => r.batch_invalidated)?.batch_invalidation_reason

  const series: TrackSeries[] = ordered
    .map((run, i) => {
      const config = configs?.[run.track]
      return {
        track: run.track,
        rows: seriesQueries[i]?.data ?? [],
        sampleStartYear: config?.sample_start_year as number | undefined,
        sampleEndYear: config?.sample_end_year as number | undefined,
        publicationYear: config?.publication_year as number | undefined,
      }
    })
    .filter((s) => s.rows.length > 0 && isTrackSelected(s.track))

  // Compare against the paper's/C&Z's OWN reported numbers on the SAME
  // basis they were reported on -- the paper's original sample window
  // ("in-sample"), not this engine's full extended history (which runs
  // well past publication and is not what any reported number covers).
  // `metrics.by_sample_period` only exists when the run's config carried
  // sample_start_year/sample_end_year/publication_year; falls back to the
  // full-period numbers when it's absent rather than showing nothing.
  const inSamplePeriod = (run: RunRecord) =>
    (run.metrics as Record<string, unknown> | undefined)?.by_sample_period as
      | Record<string, Record<string, unknown>>
      | undefined
  const displayMetrics = (run: RunRecord) => {
    const metrics = (run.metrics ?? {}) as Record<string, unknown>
    const insamp = inSamplePeriod(run)?.insamp
    return {
      meanReturn: (insamp?.mean_monthly_return ?? metrics.mean_return) as number | undefined,
      tStat: (insamp?.t_stat ?? metrics.t_stat) as number | undefined,
      sharpe: (insamp?.sharpe_ratio ?? metrics.sharpe_ratio) as number | undefined,
      alphaFf3: (insamp?.alpha_ff3 ?? metrics.alpha_ff3) as number | undefined,
      nMonths: (insamp?.n_months ?? metrics.n_months) as number | undefined,
      coverage: metrics.coverage as number | undefined,
      isInSample: insamp !== undefined,
    }
  }
  const baselineTStat = ordered[0] ? displayMetrics(ordered[0]).tStat : undefined

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-muted-foreground">batch: {shortHash(first.experiment_batch_id)}</span>
        <Badge variant="outline">{runs.length} tracks</Badge>
        <Badge variant={invalidated ? "destructive" : "default"}>
          {invalidated ? "batch invalidated" : "batch consistent"}
        </Badge>
      </div>
      {invalidated && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          {invalidationReason || "A track-local repair changed the plugin code away from this batch's frozen hash."}
        </p>
      )}

      <div>
        <p className="mb-1 text-xs font-medium">Cross-track comparison</p>
        <p className="mb-1 text-xs text-muted-foreground">
          Mean return/t-stat/Sharpe/Alpha use the paper's OWN sample window (in-sample) when the run's config
          carries one -- the same basis "Reported (reference)" is on -- not this engine's full extended history.
        </p>
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-1 pr-3 text-left font-medium">Track</th>
              <th className="py-1 pr-3 text-left font-medium">Status</th>
              <th className="py-1 pr-3 text-left font-medium">Mean return</th>
              <th className="py-1 pr-3 text-left font-medium">t-stat</th>
              <th className="py-1 pr-3 text-left font-medium">Sharpe</th>
              <th className="py-1 pr-3 text-left font-medium">Alpha (FF3)</th>
              <th className="py-1 pr-3 text-left font-medium">n_months</th>
              <th className="py-1 pr-3 text-left font-medium">Coverage</th>
              <th className="py-1 text-left font-medium">Reported (reference)</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((run) => {
              const isBaseline = run.track === baselineTrack
              const isCzTrack = run.track === "cz_actual_config"
              const isHxzTrack = run.track === "standardized_hxz"
              const { meanReturn, tStat, sharpe, alphaFf3, nMonths, coverage, isInSample } = displayMetrics(run)
              const delta =
                !isBaseline && typeof tStat === "number" && typeof baselineTStat === "number"
                  ? tStat - baselineTStat
                  : undefined
              // Paper's own headline number next to ①, C&Z's own reported
              // number (from the step6 UI's live query, reference only --
              // never re-run) next to ②, HXZ's own reported number (from a
              // downloaded testing-portfolio CSV, also reference only) next
              // to ③.
              const reported = isBaseline ? paperReported : isCzTrack ? czReported : isHxzTrack ? hxzReported?.originalInsample : undefined
              return (
                <tr
                  key={run.run_id}
                  className={cn("border-b border-border/50 last:border-0", isBaseline && "bg-sky-50 dark:bg-sky-950/20")}
                >
                  <td className="py-1 pr-3">
                    {run.track}
                    {isBaseline && (
                      <Badge variant="outline" className="ml-1">
                        baseline
                      </Badge>
                    )}
                  </td>
                  <td className="py-1 pr-3">
                    <Badge variant={run.status === "success" ? "default" : "destructive"}>{run.status}</Badge>
                  </td>
                  <td className="py-1 pr-3">
                    {formatMetric(meanReturn)}
                    {isInSample && <span className="ml-1 text-muted-foreground">(in-sample)</span>}
                  </td>
                  <td className="py-1 pr-3">
                    {formatMetric(tStat)}
                    {delta !== undefined && (
                      <span className="ml-1 text-muted-foreground">
                        ({delta >= 0 ? "+" : ""}
                        {delta.toFixed(2)})
                      </span>
                    )}
                  </td>
                  <td className="py-1 pr-3">{formatMetric(sharpe)}</td>
                  <td className="py-1 pr-3">{formatMetric(alphaFf3)}</td>
                  <td className="py-1 pr-3">{formatMetric(nMonths)}</td>
                  <td className="py-1 pr-3">{formatMetric(coverage)}</td>
                  <td className="py-1 text-muted-foreground">
                    {reported
                      ? `${isBaseline ? "paper" : isCzTrack ? "C&Z" : "HXZ"}: ${formatMetric(reported.mean_return)} / t=${formatMetric(reported.t_stat)}`
                      : "—"}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border p-2 text-xs">
        <span className="text-muted-foreground">
          Compare (applies to "Config per track" below and the chart; baseline is always included):
        </span>
        {ordered.map((run) => (
          <label
            key={run.track}
            className={cn("flex items-center gap-1", run.track === baselineTrack && "opacity-70")}
          >
            <input
              type="checkbox"
              checked={isTrackSelected(run.track)}
              disabled={run.track === baselineTrack}
              onChange={() => toggleTrack(run.track)}
            />
            <span className="font-mono">{run.track}</span>
          </label>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-5 px-1.5 text-xs"
          onClick={() => setSelectedTracks(new Set(ordered.map((r) => r.track)))}
        >
          All
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-5 px-1.5 text-xs"
          onClick={() => setSelectedTracks(new Set(baselineTrack ? [baselineTrack] : []))}
        >
          None
        </Button>
      </div>

      {configs && (
        <div>
          <p className="mb-1 text-xs font-medium">Config per track</p>
          <p className="mb-1 text-xs text-muted-foreground">
            Every resolved config key, one column per track -- a cell that differs from the baseline (
            {baselineTrack}) is highlighted amber. A{" "}
            <span className="rounded bg-sky-50 px-1 font-mono text-sky-900 dark:bg-sky-950/20 dark:text-sky-300">
              sky
            </span>{" "}
            value means the paper didn't specify this field and the pipeline filled in a convention default (hover
            for why); an unmarked value is what the paper/reviewed spec actually resolved to.
          </p>
          {(() => {
            const visibleConfigTracks = ordered.filter((run) => configs[run.track] && isTrackSelected(run.track))
            return (
              <>
                <div className="max-h-96 overflow-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="sticky left-0 bg-background py-1 pr-3 text-left font-medium">Config key</th>
                        {visibleConfigTracks.map((run) => (
                          <th key={run.track} className="py-1 pr-3 text-left font-medium">
                            {run.track}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from(new Set(Object.values(configs).flatMap((c) => Object.keys(c))))
                        .filter((key) => !NON_ROW_KEYS.has(key))
                        .sort()
                        .map((key) => {
                          const baselineValue = baselineTrack ? configs[baselineTrack]?.[key] : undefined
                          return (
                            <tr key={key} className="border-b border-border/50 last:border-0">
                              <td className="sticky left-0 bg-background py-1 pr-3 font-mono text-muted-foreground">
                                {key}
                              </td>
                              {visibleConfigTracks.map((run) => {
                                const value = configs[run.track]?.[key]
                                const differs =
                                  run.track !== baselineTrack && JSON.stringify(value) !== JSON.stringify(baselineValue)
                                const defaultReason = defaultedKeys(configs[run.track]).get(key)
                                return (
                                  <td
                                    key={run.track}
                                    title={defaultReason}
                                    className={cn(
                                      "py-1 pr-3 font-mono",
                                      // Amber (differs from baseline) takes priority over sky
                                      // (engine-filled default) when a cell is both, so the
                                      // more actionable signal ("this track's value diverges")
                                      // always wins visually.
                                      differs
                                        ? "bg-amber-50 dark:bg-amber-950/20"
                                        : defaultReason && "bg-sky-50 text-sky-900 dark:bg-sky-950/20 dark:text-sky-300",
                                    )}
                                  >
                                    {formatConfigValue(value)}
                                  </td>
                                )
                              })}
                            </tr>
                          )
                        })}
                    </tbody>
                  </table>
                </div>
              </>
            )
          })()}
        </div>
      )}

      <MultiTrackChart series={series} />

      <details>
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Debug / provenance</summary>
        <div className="mt-2 flex flex-col gap-3 text-xs">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-1 pr-3 text-left font-medium">Track</th>
                <th className="py-1 pr-3 text-left font-medium">code_hash</th>
                <th className="py-1 pr-3 text-left font-medium">frozen_plugin_hash</th>
                <th className="py-1 text-left font-medium">config_hash</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((run) => (
                <tr key={run.run_id} className="border-b border-border/50 last:border-0">
                  <td className="py-1 pr-3">{run.track}</td>
                  <td className="py-1 pr-3 font-mono">{shortHash(run.code_hash)}</td>
                  <td className="py-1 pr-3 font-mono">{shortHash(run.frozen_plugin_hash)}</td>
                  <td className="py-1 font-mono">{shortHash(run.config_hash)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ordered
            .filter((run) => (run.repair_history?.length ?? 0) > 0)
            .map((run) => (
              <div key={run.run_id}>
                <p className="mb-1 font-medium">{run.track} repair trace</p>
                <JsonTree name="repair_history" data={run.repair_history} />
              </div>
            ))}
          <JsonTree name="runs" data={ordered} />
        </div>
      </details>
    </div>
  )
}
