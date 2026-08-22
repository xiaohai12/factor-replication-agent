import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DiffView } from "@/components/DiffView"
import { GapWaterfallChart } from "@/components/GapWaterfallChart"
import { JointTestBanner, MeasuresExplainer, PairedTestsTable, ShapleyAttributionTable, TrackMetricsChart, TrackScatterChart, ForestPlot } from "@/components/AttributionPanel"
import { ThreeTermIdentityPanel } from "@/components/ThreeTermIdentityPanel"
import { cn } from "@/lib/utils"

type ConfigDiffPair = {
  changed_keys?: string[]
  details?: Record<string, { stage?: string; baseline_value?: unknown; track_value?: unknown }>
}

const TRACK_METRIC_OPTIONS = [
  { key: "mean_return", label: "Mean return" },
  { key: "t_stat", label: "t-stat" },
  { key: "sharpe_ratio", label: "Sharpe" },
  { key: "alpha_ff3", label: "Alpha (FF3)" },
] as const

const LINE_LABELS: Record<string, string> = {
  to_hxz: "vs. HXZ standardized config",
  to_cz: "vs. C&Z actual config",
  default: "",
}

/** step7's `shapley_attribution`/`paired_tests`/`joint_test` are each
 * computed PER comparison line (docs/step7-8.md Part V: ①→② and ①→③ are
 * split so a batch running both never has two different tracks fight over
 * the same switch name) -- `{line: {...result...}}`, except when NO line
 * has any switches at all, in which case it's the flat `{available: false,
 * ...}` shape directly. Normalizes both into a uniform list of
 * `[lineName, result]` pairs. */
function linesOf(x: Record<string, unknown> | undefined): [string, Record<string, unknown>][] {
  if (!x) return []
  if ("available" in x) return [["default", x]]
  return Object.entries(x) as [string, Record<string, unknown>][]
}

/** step7's evidence bundle (`comparison.json`'s top-level keys), rendered
 * as one panel: overall_tag, joint test, Shapley attribution, paired
 * tests, the OAT gap-decomposition chart (mutually exclusive with Shapley
 * per batch -- see docs/step7-8.md), and a track-selectable config diff
 * (mirrors Step6Output's own "Compare" checklist so a batch with 10+
 * factorial tracks doesn't dump every one on screen by default). */
export function Step7Output({ bundle }: { bundle: Record<string, unknown> }) {
  const derived = (bundle.derived as Record<string, unknown>) ?? {}
  const shapleyLines = linesOf(bundle.shapley_attribution as Record<string, unknown> | undefined)
  const pairedLines = new Map(linesOf(bundle.paired_tests as Record<string, unknown> | undefined))
  const jointLines = new Map(linesOf(bundle.joint_test as Record<string, unknown> | undefined))
  const externalPerformanceComparison = bundle.external_performance_comparison as
    | { cz?: { available?: boolean; mean_return?: number | null; t_stat?: number | null; source?: string | null }; hxz?: { available?: boolean; mean_return?: number | null; t_stat?: number | null; source?: string | null } }
    | undefined
  const configDiff =
    (bundle.config_diff as { baseline_track?: string; pairs?: Record<string, ConfigDiffPair> }) ?? {}
  const tracks =
    (bundle.tracks as Record<string, { config?: Record<string, unknown>; metrics?: Record<string, unknown> }>) ?? {}
  // Same "prefer the paper's own sample window over this engine's full
  // extended history" convention Step6Output.tsx already applies per-run --
  // TrackMetricsChart/TrackScatterChart previously read raw `tracks`
  // (full-history metrics), inconsistent with ForestPlot right above them
  // (which reads `derived.tracks[*].vs_paper`, already in-sample-preferred).
  const inSampleTracks = Object.fromEntries(
    Object.entries(tracks).map(([name, payload]) => {
      const metrics = payload.metrics ?? {}
      const insamp = (metrics.by_sample_period as Record<string, Record<string, unknown>> | undefined)?.insamp
      return [
        name,
        {
          ...payload,
          metrics: insamp
            ? {
                ...metrics,
                mean_return: insamp.mean_monthly_return ?? metrics.mean_return,
                t_stat: insamp.t_stat ?? metrics.t_stat,
                sharpe_ratio: insamp.sharpe_ratio ?? metrics.sharpe_ratio,
                alpha_ff3: insamp.alpha_ff3 ?? metrics.alpha_ff3,
                n_months: insamp.n_months ?? metrics.n_months,
              }
            : metrics,
        },
      ]
    }),
  )
  const baselineTrack = configDiff.baseline_track
  const baselineConfig = (baselineTrack && tracks[baselineTrack]?.config) || {}
  const allPairTrackNames = Object.keys(configDiff.pairs ?? {})

  const [metricKey, setMetricKey] = useState<(typeof TRACK_METRIC_OPTIONS)[number]["key"]>("mean_return")
  const [onlyDiffering, setOnlyDiffering] = useState(true)
  const trackNamesKey = allPairTrackNames.join(",")
  const [selectedTracks, setSelectedTracks] = useState<Set<string> | null>(null)
  useEffect(() => {
    const known = trackNamesKey ? trackNamesKey.split(",") : []
    setSelectedTracks((prev) => {
      const next = new Set(prev ?? known)
      for (const track of known) next.add(track)
      return next
    })
  }, [trackNamesKey])

  const differingTrackNames = allPairTrackNames.filter(
    (track) => (configDiff.pairs?.[track]?.changed_keys?.length ?? 0) > 0,
  )
  const candidateTrackNames = onlyDiffering ? differingTrackNames : allPairTrackNames
  const isTrackSelected = (track: string) => selectedTracks?.has(track) ?? true
  const toggleTrack = (track: string) => {
    setSelectedTracks((prev) => {
      const next = new Set(prev ?? allPairTrackNames)
      if (next.has(track)) next.delete(track)
      else next.add(track)
      return next
    })
  }
  const visibleTrackNames = candidateTrackNames.filter(isTrackSelected)

  return (
    <div className="flex flex-col gap-3">
      <Badge variant="outline">overall_tag: {String(derived.overall_tag ?? "inconclusive")}</Badge>
      <MeasuresExplainer />
      <div className="flex flex-col gap-1">
        <p className="text-xs text-muted-foreground">
          Forest plot -- each track's own t-stat against HXZ's tiered significance thresholds (docs/step7-8.md Q7/Q8)
        </p>
        <ForestPlot
          tracks={derived.tracks as Record<string, { vs_paper?: Record<string, unknown> }>}
          baselineTrack={baselineTrack}
          externalPerformance={
            externalPerformanceComparison
              ? { cz: externalPerformanceComparison.cz, hxz: externalPerformanceComparison.hxz }
              : undefined
          }
        />
      </div>
      <GapWaterfallChart
        gapDecomposition={bundle.gap_decomposition as Record<string, unknown>}
        shapleyAttribution={bundle.shapley_attribution as Parameters<typeof GapWaterfallChart>[0]["shapleyAttribution"]}
      />
      <ThreeTermIdentityPanel
        threeTerm={bundle.three_term_identity as Parameters<typeof ThreeTermIdentityPanel>[0]["threeTerm"]}
      />
      {shapleyLines.map(([line, shapley]) => (
        <div key={line} className="flex flex-col gap-2 rounded-md border border-border p-2">
          {LINE_LABELS[line] && <p className="text-xs font-medium">{LINE_LABELS[line]}</p>}
          <JointTestBanner jointTest={jointLines.get(line)} />
          <ShapleyAttributionTable shapley={shapley} jointTest={jointLines.get(line)} />
          <PairedTestsTable pairedTests={pairedLines.get(line)} />
        </div>
      ))}

      {baselineTrack && allPairTrackNames.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border p-2 text-xs">
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={onlyDiffering}
                onChange={(e) => setOnlyDiffering(e.target.checked)}
              />
              <span>Only show tracks with config differences</span>
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border p-2 text-xs">
            <span className="text-muted-foreground">Compare metric across tracks:</span>
            {TRACK_METRIC_OPTIONS.map((opt) => (
              <Button
                key={opt.key}
                type="button"
                variant={metricKey === opt.key ? "default" : "ghost"}
                size="sm"
                className="h-5 px-1.5 text-xs"
                onClick={() => setMetricKey(opt.key)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <TrackMetricsChart
              tracks={inSampleTracks}
              trackNames={[baselineTrack, ...visibleTrackNames.filter((t) => t !== baselineTrack)]}
              metricKey={metricKey}
              baselineTrack={baselineTrack}
            />
            <div className="flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">mean_return vs t_stat -- is the difference real, or noise?</p>
              <TrackScatterChart
                tracks={inSampleTracks}
                trackNames={[baselineTrack, ...visibleTrackNames.filter((t) => t !== baselineTrack)]}
                baselineTrack={baselineTrack}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border p-2 text-xs">
            <span className="text-muted-foreground">Compare against {baselineTrack}:</span>
            {candidateTrackNames.map((track) => (
              <label key={track} className="flex items-center gap-1">
                <input type="checkbox" checked={isTrackSelected(track)} onChange={() => toggleTrack(track)} />
                <span className="font-mono">{track}</span>
              </label>
            ))}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-xs"
              onClick={() => setSelectedTracks(new Set(allPairTrackNames))}
            >
              All
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-xs"
              onClick={() => setSelectedTracks(new Set())}
            >
              None
            </Button>
          </div>
          {visibleTrackNames.length === 0 && (
            <p className="text-xs text-muted-foreground">No tracks selected (or none differ from the baseline).</p>
          )}
          {visibleTrackNames.map((track) => (
            <div key={track} className={cn("flex flex-col gap-1")}>
              <p className="mb-1 text-xs font-medium">
                {track} vs {baselineTrack} config
              </p>
              <DiffView
                left={baselineConfig}
                right={tracks[track]?.config ?? {}}
                leftLabel={baselineTrack}
                rightLabel={track}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
