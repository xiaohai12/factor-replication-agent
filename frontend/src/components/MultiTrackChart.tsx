import {
  CartesianGrid,
  Label,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]

export interface TrackSeries {
  track: string
  rows: { yyyymm: number; ls_return: number }[]
  // Same fields that drive `BacktestExecutor._sample_period_segments`
  // (metrics.by_sample_period) -- when at least one is set for a track,
  // its rows get split into in-sample/between/post-publication panels
  // below instead of one combined chart, mirroring how the "Cross-track
  // comparison" table already segments this run's own metrics.
  sampleStartYear?: number
  sampleEndYear?: number
  publicationYear?: number
}

function yearOf(yyyymm: number): number {
  return Math.floor(yyyymm / 100)
}

/** Same boundary logic as `BacktestExecutor._sample_period_segments`: an
 * "insamp" segment exists whenever ANY of the three fields is set (missing
 * bounds fall back to -Infinity/+Infinity); "between" needs BOTH
 * `sampleEndYear` and `publicationYear`; "postpub" needs `publicationYear`.
 * A track with none of the three set is treated as one whole "insamp"
 * segment (its full history, since there's no window info to split on). */
function splitBySamplePeriod(series: TrackSeries[]): {
  insamp: TrackSeries[]
  between: TrackSeries[]
  postpub: TrackSeries[]
} {
  const insamp: TrackSeries[] = []
  const between: TrackSeries[] = []
  const postpub: TrackSeries[] = []
  for (const s of series) {
    const { sampleStartYear: start, sampleEndYear: end, publicationYear: pub } = s
    if (start === undefined && end === undefined && pub === undefined) {
      insamp.push(s)
      continue
    }
    const lo = start ?? -Infinity
    const hi = end ?? Infinity
    const insampRows = s.rows.filter((r) => yearOf(r.yyyymm) >= lo && yearOf(r.yyyymm) <= hi)
    if (insampRows.length > 0) insamp.push({ ...s, rows: insampRows })
    if (end !== undefined && pub !== undefined) {
      const betweenRows = s.rows.filter((r) => yearOf(r.yyyymm) > end && yearOf(r.yyyymm) <= pub)
      if (betweenRows.length > 0) between.push({ ...s, rows: betweenRows })
    }
    if (pub !== undefined) {
      const postpubRows = s.rows.filter((r) => yearOf(r.yyyymm) > pub)
      if (postpubRows.length > 0) postpub.push({ ...s, rows: postpubRows })
    }
  }
  return { insamp, between, postpub }
}

/** One overlaid cumulative-return chart for a set of (already segmented)
 * track series -- the single-panel renderer `MultiTrackChart` below calls
 * once per segment (or once, unsegmented, when no track carries sample-
 * period bounds). */
function SingleChart({ series }: { series: TrackSeries[] }) {
  const periodSet = new Set<string>()
  const byTrack = series.map(({ track, rows }) => {
    let cumulative = 1
    const points = new Map<string, number>()
    rows.forEach((row) => {
      cumulative *= 1 + row.ls_return
      const period = String(row.yyyymm)
      periodSet.add(period)
      points.set(period, cumulative - 1)
    })
    return { track, points }
  })

  const periods = Array.from(periodSet).sort()
  const merged = periods.map((period) => {
    const row: Record<string, string | number> = { period }
    byTrack.forEach(({ track, points }) => {
      const v = points.get(period)
      if (v !== undefined) row[track] = v
    })
    return row
  })

  return (
    <div className="h-72 w-full rounded-lg border border-border p-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 11 }}>
            <Label value="Cumulative return" angle={-90} position="insideLeft" style={{ fontSize: 11 }} />
          </YAxis>
          <Tooltip formatter={(value) => `${(Number(value) * 100).toFixed(2)}%`} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {byTrack.map(({ track }, i) => (
            <Line
              key={track}
              type="monotone"
              dataKey={track}
              stroke={COLORS[i % COLORS.length]}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Overlays cumulative return for every step6 track -- one chart per
 * sample-period segment (in-sample/between/post-publication, same
 * boundaries as `BacktestExecutor._sample_period_segments`/the
 * "Cross-track comparison" table's `by_sample_period`) when at least one
 * track carries `sampleStartYear`/`sampleEndYear`/`publicationYear`;
 * otherwise a single combined chart, unchanged from before. */
export function MultiTrackChart({ series }: { series: TrackSeries[] }) {
  if (series.length === 0) {
    return <p className="text-xs text-muted-foreground">No track return series available.</p>
  }

  const hasAnyBounds = series.some(
    (s) => s.sampleStartYear !== undefined || s.sampleEndYear !== undefined || s.publicationYear !== undefined,
  )
  if (!hasAnyBounds) {
    return <SingleChart series={series} />
  }

  const { insamp, between, postpub } = splitBySamplePeriod(series)
  const panels: { label: string; series: TrackSeries[] }[] = [
    { label: "In-sample", series: insamp },
    { label: "Between (sample end \u2192 publication)", series: between },
    { label: "Post-publication", series: postpub },
  ].filter((p) => p.series.length > 0)

  if (panels.length === 0) {
    return <SingleChart series={series} />
  }

  return (
    <div className="flex flex-col gap-3">
      {panels.map((p) => (
        <div key={p.label} className="flex flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground">{p.label}</p>
          <SingleChart series={p.series} />
        </div>
      ))}
    </div>
  )
}
