import {
  CartesianGrid,
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

export function ReturnChart({ data }: { data: ReturnRow[] }) {
  let cumulative = 1
  const rows = data.map((row) => {
    cumulative *= 1 + row.ls_return
    return {
      period: String(row.yyyymm),
      monthly_return: row.ls_return,
      cumulative_return: cumulative - 1,
    }
  })

  return (
    <div className="h-72 w-full rounded-lg border border-border p-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value, name) => [
              `${(Number(value) * 100).toFixed(2)}%`,
              name === "cumulative_return" ? "Cumulative return" : "Monthly return",
            ]}
            labelFormatter={(label) => `Period: ${label}`}
          />
          <Line type="monotone" dataKey="cumulative_return" stroke="var(--color-primary)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
