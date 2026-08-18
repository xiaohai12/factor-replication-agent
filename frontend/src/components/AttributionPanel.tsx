import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"

type ShapleyAttribution = {
  available?: boolean
  reason?: string
  identification_level?: string
  switches?: string[]
  total_gap?: number
  shapley_effects?: Record<string, number>
}

type PairedTests = {
  available?: boolean
  reason?: string
  per_switch?: Record<
    string,
    { available?: boolean; reason?: string; mean_diff?: number; t_stat?: number; n_overlap_months?: number }
  >
}

type JointTest = {
  available?: boolean
  reason?: string
  switches?: string[]
  wald_stat?: number
  df?: number
  p_value?: number
}

/** Bar chart comparing one metric (`mean_return`/`t_stat`/`sharpe_ratio`/...)
 * across an arbitrary set of tracks -- unlike `ShapleyBarChart` (switch
 * contributions to the GAP) or `GapWaterfallChart` (OAT contributions),
 * this plots each track's own reported metric value side by side, e.g. to
 * see at a glance how far every factorial corner's `mean_return` sits from
 * the baseline, not just the isolated switch effects. `track` is always
 * included even with a missing/zero value so the x-axis stays stable
 * while the caller toggles which metric to show. */
export function TrackMetricsChart({
  tracks,
  trackNames,
  metricKey,
  baselineTrack,
}: {
  tracks: Record<string, { metrics?: Record<string, unknown> }>
  trackNames: string[]
  metricKey: string
  baselineTrack?: string
}) {
  const rows = trackNames.map((track) => {
    const value = tracks[track]?.metrics?.[metricKey]
    return { track, value: typeof value === "number" ? value : null }
  })
  if (rows.every((r) => r.value === null)) {
    return <p className="text-xs text-muted-foreground">No {metricKey} available for these tracks.</p>
  }
  return (
    <div className="h-80 w-full rounded-lg border border-border p-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="track" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
          <YAxis
            tick={{ fontSize: 11 }}
            label={{ value: metricKey, angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <Tooltip formatter={(value) => (typeof value === "number" ? value.toFixed(4) : "—")} />
          <Bar dataKey="value">
            {rows.map((r) => (
              <Cell key={r.track} fill={r.track === baselineTrack ? "var(--color-muted-foreground)" : "var(--color-primary)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const JOINT_SIGNIFICANCE_ALPHA = 0.05
const T_STAT_SIGNIFICANCE_THRESHOLD = 1.96

/** Scatter of `mean_return` (x, economic size) vs `t_stat` (y, statistical
 * confidence) -- one point per track -- so "is this track's difference
 * from baseline real, or just noise" is answered in a single glance
 * instead of toggling `TrackMetricsChart` between two separate bar charts.
 * Dashed reference lines at +/-1.96 mark the conventional significance
 * threshold (same one `PairedTestsTable` highlights). A track missing
 * either value is skipped (can't be plotted), never shown as zero. */
export function TrackScatterChart({
  tracks,
  trackNames,
  baselineTrack,
}: {
  tracks: Record<string, { metrics?: Record<string, unknown> }>
  trackNames: string[]
  baselineTrack?: string
}) {
  const points = trackNames
    .map((track) => {
      const metrics = tracks[track]?.metrics ?? {}
      const meanReturn = metrics.mean_return
      const tStat = metrics.t_stat
      if (typeof meanReturn !== "number" || typeof tStat !== "number") return null
      return { track, meanReturn, tStat }
    })
    .filter((p): p is { track: string; meanReturn: number; tStat: number } => p !== null)

  if (points.length === 0) {
    return <p className="text-xs text-muted-foreground">No mean_return/t_stat pairs available for these tracks.</p>
  }

  return (
    <div className="h-80 w-full rounded-lg border border-border p-3">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            type="number"
            dataKey="meanReturn"
            name="mean return"
            tick={{ fontSize: 11 }}
            label={{ value: "mean_return (monthly)", position: "insideBottom", offset: -12, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="tStat"
            name="t-stat"
            tick={{ fontSize: 11 }}
            label={{ value: "t_stat", angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <ReferenceLine y={T_STAT_SIGNIFICANCE_THRESHOLD} strokeDasharray="4 4" className="stroke-amber-500" />
          <ReferenceLine y={-T_STAT_SIGNIFICANCE_THRESHOLD} strokeDasharray="4 4" className="stroke-amber-500" />
          <Tooltip
            formatter={(value) => (typeof value === "number" ? value.toFixed(4) : "—")}
            labelFormatter={() => ""}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { track: string; meanReturn: number; tStat: number }
              return (
                <div className="rounded-md border border-border bg-background p-2 text-xs shadow">
                  <p className="font-medium">{p.track}</p>
                  <p>mean_return: {p.meanReturn.toFixed(4)}</p>
                  <p>t_stat: {p.tStat.toFixed(2)}</p>
                </div>
              )
            }}
          />
          <Scatter data={points}>
            {points.map((p) => (
              <Cell
                key={p.track}
                fill={p.track === baselineTrack ? "var(--color-muted-foreground)" : "var(--color-primary)"}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function fmtNum(v: number | undefined, digits = 4): string {
  return v === undefined || v === null || Number.isNaN(v) ? "—" : v.toFixed(digits)
}

// docs/step7-8.md Q8: HXZ's tiered thresholds (Q7), reused here so the forest
// plot's reference lines match the same tiers `track_significance_tier`
// already reports -- not a new/independent threshold set.
const HXZ_TIERS = [1.96, 2.78, 3.39]

/** docs/step7-8.md Q8's "forest plot" candidate: one row per track, its own
 * t-stat as a point, HXZ's three tiered significance thresholds (Q7) as
 * dashed reference lines -- lets you see at a glance which tier each track
 * clears without reading the significance table row by row. Tracks with a
 * `null` t-stat are omitted (never plotted as zero). */
export function ForestPlot({
  tracks,
  baselineTrack,
}: {
  tracks: Record<string, { vs_paper?: { track_raw_t_stat?: number | null; track_significance_tier?: number | null } }>
  baselineTrack?: string
}) {
  const rows = Object.entries(tracks)
    .map(([track, d]) => ({
      track,
      tStat: d.vs_paper?.track_raw_t_stat,
      tier: d.vs_paper?.track_significance_tier ?? null,
    }))
    .filter((r): r is { track: string; tStat: number; tier: number | null } => typeof r.tStat === "number")
    .sort((a, b) => Math.abs(b.tStat) - Math.abs(a.tStat))

  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No track t-stats available to plot.</p>
  }

  const height = Math.max(120, rows.length * 32 + 40)
  return (
    <div className="w-full rounded-lg border border-border p-3" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 8, right: 24, bottom: 24, left: 8 }}
          barCategoryGap={10}
        >
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            label={{ value: "t-stat", position: "insideBottom", offset: -12, fontSize: 11 }}
          />
          <YAxis type="category" dataKey="track" tick={{ fontSize: 11 }} width={140} />
          {HXZ_TIERS.flatMap((tier) => [
            <ReferenceLine key={`+${tier}`} x={tier} strokeDasharray="4 4" className="stroke-amber-500" />,
            <ReferenceLine key={`-${tier}`} x={-tier} strokeDasharray="4 4" className="stroke-amber-500" />,
          ])}
          <ReferenceLine x={0} className="stroke-border" />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { track: string; tStat: number; tier: number | null }
              return (
                <div className="rounded-md border border-border bg-background p-2 text-xs shadow">
                  <p className="font-medium">{p.track}</p>
                  <p>t_stat: {p.tStat.toFixed(2)}</p>
                  <p>HXZ tier: {p.tier ?? "n/a"}</p>
                </div>
              )
            }}
          />
          <Bar dataKey="tStat" barSize={14}>
            {rows.map((r) => (
              <Cell
                key={r.track}
                fill={r.track === baselineTrack ? "var(--color-muted-foreground)" : "var(--color-primary)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

type ConfigDiffPairDetail = { stage?: string; baseline_value?: unknown; track_value?: unknown }
type ConfigDiffPair = { changed_keys?: string[]; details?: Record<string, ConfigDiffPairDetail> }

const STAGE_COLORS: Record<string, string> = {
  signal_input: "bg-blue-500/70",
  portfolio: "bg-purple-500/70",
  universe: "bg-emerald-500/70",
  sample: "bg-amber-500/70",
  estimator: "bg-rose-500/70",
  unclassified: "bg-muted-foreground/50",
}

/** docs/step7-8.md Q8's "config diff heatmap" candidate: track x config-key
 * matrix, colored by the changed key's own pipeline `stage` (same taxonomy
 * `config_diff` already tags each key with) -- lowest-effort of the Q8
 * candidates since it's a direct re-render of `config_diff.pairs`, no new
 * computation. A cell is only colored when that key actually changed for
 * that track; hovering shows baseline_value -> track_value. */
export function ConfigDiffHeatmap({
  pairs,
}: {
  pairs: Record<string, ConfigDiffPair> | undefined
}) {
  const trackNames = Object.keys(pairs ?? {})
  const allKeys = Array.from(
    new Set(trackNames.flatMap((t) => pairs?.[t]?.changed_keys ?? [])),
  ).sort()

  if (trackNames.length === 0 || allKeys.length === 0) {
    return <p className="text-xs text-muted-foreground">No config differences to show.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border p-2">
      <table className="border-collapse text-xs">
        <thead>
          <tr>
            <th className="p-1 text-left font-medium">track \\ key</th>
            {allKeys.map((key) => (
              <th key={key} className="p-1 text-left font-mono font-normal text-muted-foreground">
                {key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trackNames.map((track) => (
            <tr key={track}>
              <td className="p-1 font-mono">{track}</td>
              {allKeys.map((key) => {
                const detail = pairs?.[track]?.details?.[key]
                if (!detail) {
                  return <td key={key} className="p-1" />
                }
                const color = STAGE_COLORS[detail.stage ?? "unclassified"] ?? STAGE_COLORS.unclassified
                return (
                  <td
                    key={key}
                    className="p-1"
                    title={`${String(detail.baseline_value)} → ${String(detail.track_value)} (${detail.stage ?? "unclassified"})`}
                  >
                    <div className={cn("h-4 w-8 rounded", color)} />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** step7's `joint_test` result, as one banner line -- the gate described in
 * docs/step7-8.md Part V: whether the switches this batch varied
 * collectively explain more than noise, BEFORE reading any single switch's
 * Shapley value or paired-test result as "this one matters". */
export function JointTestBanner({ jointTest }: { jointTest: JointTest | undefined }) {
  if (!jointTest || jointTest.available !== true) {
    return (
      <p className="text-xs text-muted-foreground">
        Joint test unavailable{jointTest?.reason ? `: ${jointTest.reason}` : "."}
      </p>
    )
  }
  const significant = (jointTest.p_value ?? 1) < JOINT_SIGNIFICANCE_ALPHA
  return (
    <div
      className={cn(
        "rounded-md border p-2 text-xs",
        significant ? "border-border" : "border-amber-500/60 bg-amber-500/10",
      )}
    >
      <span className="font-medium">Joint Wald test</span> across {jointTest.switches?.join(", ") ?? "switches"}:{" "}
      wald={fmtNum(jointTest.wald_stat, 2)}, df={jointTest.df}, p={fmtNum(jointTest.p_value, 6)}
      {" — "}
      {significant ? (
        <span>switches collectively significant.</span>
      ) : (
        <span className="font-medium text-amber-700 dark:text-amber-400">
          not jointly significant — individual switch numbers below lack joint support.
        </span>
      )}
    </div>
  )
}

/** Bar chart of a full-factorial batch's `shapley_effects` (switch name ->
 * contribution to the total gap) -- the full-factorial counterpart of
 * `GapWaterfallChart` (which only covers OAT `gap_decomposition` batches).
 * A real bar chart, not a cumulative waterfall: Shapley values already sum
 * exactly to `total_gap` by construction, so no residual bar is needed. */
function ShapleyBarChart({ effects }: { effects: [string, number][] }) {
  if (effects.length === 0) return null
  const rows = effects.map(([switchName, value]) => ({ switchName, value }))
  return (
    <div className="h-56 w-full rounded-lg border border-border p-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="switchName" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip formatter={(value) => Number(value).toFixed(4)} />
          <Bar dataKey="value" fill="var(--color-primary)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** step7's `shapley_attribution` result -- a bar chart plus one table row
 * per switch. Visually dims itself when the joint test (passed in, not
 * re-derived) doesn't reject "all switches are zero", per docs/step7-8.md
 * Part V: the numbers are still shown (never hidden), just flagged as
 * lacking joint support. */
export function ShapleyAttributionTable({
  shapley,
  jointTest,
}: {
  shapley: ShapleyAttribution | undefined
  jointTest: JointTest | undefined
}) {
  if (!shapley || shapley.available !== true) {
    return (
      <p className="text-xs text-muted-foreground">
        No Shapley attribution available{shapley?.reason ? `: ${shapley.reason}` : "."}
      </p>
    )
  }
  const jointSupported = jointTest?.available === true && (jointTest.p_value ?? 1) < JOINT_SIGNIFICANCE_ALPHA
  const jointChecked = jointTest?.available === true
  const effects = Object.entries(shapley.shapley_effects ?? {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))

  return (
    <div className={cn("flex flex-col gap-1", jointChecked && !jointSupported && "opacity-60")}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">Shapley attribution (mean_return)</span>
        <Badge variant="outline">{shapley.identification_level ?? "controlled"}</Badge>
        {jointChecked && !jointSupported && (
          <Badge variant="secondary">lacks joint support</Badge>
        )}
      </div>
      <ShapleyBarChart effects={effects} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>switch</TableHead>
            <TableHead>contribution</TableHead>
            <TableHead>% of total gap</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {effects.map(([switchName, value]) => (
            <TableRow key={switchName}>
              <TableCell className="font-mono text-xs">{switchName}</TableCell>
              <TableCell className="font-mono text-xs">{fmtNum(value)}</TableCell>
              <TableCell className="font-mono text-xs">
                {shapley.total_gap ? `${((value / shapley.total_gap) * 100).toFixed(1)}%` : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** step7's `paired_tests` result -- one row per switch, |t| >= 1.96
 * highlighted. Each switch's own `available=false` (e.g. missing CSV) is
 * shown per-row rather than failing the whole table. */
export function PairedTestsTable({ pairedTests }: { pairedTests: PairedTests | undefined }) {
  if (!pairedTests || pairedTests.available !== true) {
    return (
      <p className="text-xs text-muted-foreground">
        No paired significance tests available{pairedTests?.reason ? `: ${pairedTests.reason}` : "."}
      </p>
    )
  }
  const rows = Object.entries(pairedTests.per_switch ?? {})
  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No single-switch tracks found.</p>
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>switch</TableHead>
          <TableHead>mean diff (monthly)</TableHead>
          <TableHead>t-stat</TableHead>
          <TableHead>n months</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(([switchName, entry]) => {
          if (entry.available !== true) {
            return (
              <TableRow key={switchName}>
                <TableCell className="font-mono text-xs">{switchName}</TableCell>
                <TableCell colSpan={3} className="text-xs text-muted-foreground">
                  unavailable{entry.reason ? `: ${entry.reason}` : ""}
                </TableCell>
              </TableRow>
            )
          }
          const significant = Math.abs(entry.t_stat ?? 0) >= 1.96
          return (
            <TableRow key={switchName}>
              <TableCell className="font-mono text-xs">{switchName}</TableCell>
              <TableCell className="font-mono text-xs">{fmtNum(entry.mean_diff)}</TableCell>
              <TableCell className={cn("font-mono text-xs", significant && "font-semibold text-primary")}>
                {fmtNum(entry.t_stat, 2)}
              </TableCell>
              <TableCell className="font-mono text-xs">{entry.n_overlap_months ?? "—"}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

const MEASURES = [
  {
    name: "Shapley attribution",
    paper: "Shapley (1953), \"A Value for n-Person Games\"",
    formula: "φ_i = Σ_{S⊆N\\{i}} [ |S|!·(n−|S|−1)! / n! ] · ( v(S∪{i}) − v(S) )",
    purpose:
      "Order-independent split of the total replication gap across the config switches a full-factorial batch " +
      "varied -- unlike a one-at-a-time (OAT) decomposition, the answer doesn't depend on which switch you " +
      "pretend to flip first.",
    detail:
      "v(S) = mean_return of the track with switches in S set to their target value, all others at baseline. " +
      "Property: Σᵢ φ_i = v(N) − v(∅) EXACTLY (Shapley's efficiency property) -- the contributions always add up " +
      "to the total gap, with no residual.",
    example:
      "AssetGrowth (①→③, 3 switches): weighting = −0.00565 (96% of the −0.00590 total gap), " +
      "breakpoint = −0.00183 (31%), universe = +0.00158 (−27%, partially offsetting) -- sums exactly to the total.",
  },
  {
    name: "Paired significance test",
    paper: "Newey & West (1987), Econometrica, \"A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix\"",
    formula: "t = mean(dₜ) / √(NW_var / n),  dₜ = r_baseline,t − r_track,t",
    purpose:
      "Whether ONE switch's effect is statistically distinguishable from zero -- not just numerically different -- " +
      "using the same HAC-robust t-stat this engine already uses for a track's own headline t-stat.",
    detail:
      "dₜ is the monthly return difference over the months BOTH tracks report in-sample. NW_var is the Newey-West " +
      "HAC variance estimate (6 lags by default) of dₜ, correcting for the autocorrelation in monthly returns.",
    example:
      "AssetGrowth, weighting switch: mean_diff = 0.00702/month over 432 overlapping in-sample months, t = 2.74 " +
      "-- clears the 1.96 cutoff, so this switch's effect is significant, not just numerically nonzero.",
  },
  {
    name: "Joint Wald test",
    paper: "Wald (1943)'s general test; the HAC-covariance form here mirrors Ledoit & Wolf (2008), Journal of Empirical Finance, \"Robust performance hypothesis testing with the Sharpe ratio\"",
    formula: "W = δᵀ Σ⁻¹ δ  ~  χ²(df = k)   under H₀: δ = 0",
    purpose:
      "Whether SEVERAL switches collectively explain more than noise -- the gate against picking whichever single " +
      "switch's Shapley/paired-test number happens to look biggest without checking they're jointly significant " +
      "(the classic multiple-comparisons trap).",
    detail:
      "δ is the vector of ALL k single-switch mean-diffs at once; Σ is their HAC covariance matrix, including the " +
      "cross-covariances BETWEEN switches (they share the same baseline and heavily-overlapping months, so they " +
      "are NOT independent).",
    example:
      "AssetGrowth, 3 switches jointly: W = 21.62, df = 3, p ≈ 0.00008 -- strongly rejects \"all three switches " +
      "have zero effect\", so the individual Shapley/paired-test numbers above are backed by joint significance.",
  },
  {
    name: "HXZ tiered significance",
    paper: "Harvey, Liu & Zhu (2016), Review of Financial Studies, \"...and the Cross-Section of Expected Returns\"; thresholds as used in Hou, Xue & Zhang (2020), RFS, \"Replicating Anomalies\"",
    formula: "tier = #{ threshold ∈ (1.96, 2.78, 3.39) : |t| ≥ threshold }",
    purpose:
      "Judge significance on the SAME multiple-testing-adjusted scale the paper being replicated (HXZ) uses, " +
      "instead of only the single 1.96 cutoff -- distinguishes \"barely significant\" from \"overwhelming\".",
    detail:
      "tier 0 = not significant even at 1.96, tier 3 = clears all three (the strictest common bar in the " +
      "anomaly-replication literature).",
    example:
      "AssetGrowth: original_method's t = 6.01 clears all three (tier 3); standardized_hxz's t = 2.05 clears " +
      "only 1.96 (tier 1) -- same \"significant\" label under the old binary cutoff, very different tiers.",
  },
]

/** Static reference card explaining the formula, source paper, purpose, and
 * a worked example (from the real AssetGrowth batch) for each measure above
 * -- collapsed by default (it's documentation, not data) but visually
 * distinct so it stands out from the data tables rather than blending in. */
export function MeasuresExplainer() {
  return (
    <details className="rounded-md border border-primary/30 bg-primary/5 p-2 text-xs">
      <summary className="cursor-pointer font-medium">What these measures are (formulas, papers, examples)</summary>
      <div className="mt-2 flex flex-col gap-4">
        {MEASURES.map((m) => (
          <div key={m.name} className="flex flex-col gap-0.5">
            <span className="font-medium">{m.name}</span>
            <span className="text-muted-foreground">{m.paper}</span>
            <span className="font-mono text-[0.7rem]">{m.formula}</span>
            <span className="mt-1">
              <span className="font-medium">Used for: </span>
              <span className="text-muted-foreground">{m.purpose}</span>
            </span>
            <span className="text-muted-foreground">{m.detail}</span>
            <span className="mt-1 rounded bg-background/60 p-1 font-mono text-[0.7rem]">{m.example}</span>
          </div>
        ))}
      </div>
    </details>
  )
}
