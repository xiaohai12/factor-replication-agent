import {
  CartesianGrid,
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
}

/** Overlays cumulative return for every step6 track on one chart -- the
 * step6 multi-track visualization the plan called for (each track's own
 * `return_series.csv`, fetched via the existing evidence download
 * endpoint and parsed client-side, see lib/csv.ts). */
export function MultiTrackChart({ series }: { series: TrackSeries[] }) {
  if (series.length === 0) {
    return <p className="text-xs text-muted-foreground">No track return series available.</p>
  }

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
          <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 11 }} />
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
