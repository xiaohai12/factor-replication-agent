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

export interface ReturnRow {
  yyyymm: number
  ls_return: number
}

/** Extended (Phase E) to also plot `monthly_return` -- previously computed
 * client-side for the tooltip but never actually rendered as its own line;
 * shown on a secondary y-axis since monthly and cumulative returns live on
 * very different scales.
 *
 * X axis is a real NUMERIC time value (decimal year), not a string
 * category -- a category axis with hundreds of points only differs
 * visually by how many tick LABELS happen to fit, which read as truncated
 * data. A numeric axis lets recharts place ticks evenly across the true
 * date range regardless of point count. */
export function ReturnChart({ data }: { data: ReturnRow[] }) {
  let cumulative = 1
  const rows = data.map((row) => {
    cumulative *= 1 + row.ls_return
    const year = Math.floor(row.yyyymm / 100)
    const month = row.yyyymm % 100
    return {
      period: String(row.yyyymm),
      t: year + (month - 1) / 12,
      monthly_return: row.ls_return,
      cumulative_return: cumulative - 1,
    }
  })

  return (
    <div className="flex flex-col gap-1">
      {rows.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {rows.length} months ({rows[0].period}–{rows[rows.length - 1].period})
        </p>
      )}
      <div className="h-72 w-full rounded-lg border border-border p-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => String(Math.round(v))}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              yAxisId="cumulative"
              tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              yAxisId="monthly"
              orientation="right"
              tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              formatter={(value, name) => [
                `${(Number(value) * 100).toFixed(2)}%`,
                name === "cumulative_return" ? "Cumulative return" : "Monthly return",
              ]}
              labelFormatter={(_, payload) => `Period: ${payload[0]?.payload?.period ?? ""}`}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line
              yAxisId="cumulative"
              type="monotone"
              dataKey="cumulative_return"
              stroke="var(--color-primary)"
              dot={false}
            />
            <Line
              yAxisId="monthly"
              type="monotone"
              dataKey="monthly_return"
              stroke="#94a3b8"
              strokeWidth={1}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
