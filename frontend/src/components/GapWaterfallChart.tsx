import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

/** Bar chart of step7's `gap_decomposition.contributions` (switch name ->
 * OAT contribution to the total replication gap), plus the residual --
 * NOT a real waterfall (contributions aren't guaranteed additive, see
 * `src/steps/step7_replication_diff/bundle.py`), so this is deliberately a
 * plain grouped bar chart rather than a cumulative-offset waterfall that
 * would visually imply additivity that isn't guaranteed. */
export function GapWaterfallChart({ gapDecomposition }: { gapDecomposition: Record<string, unknown> }) {
  const contributions = (gapDecomposition.contributions as Record<string, number> | undefined) ?? {}
  const rows = Object.entries(contributions).map(([switchName, value]) => ({ switchName, value }))
  if (typeof gapDecomposition.residual === "number") {
    rows.push({ switchName: "residual", value: gapDecomposition.residual })
  }

  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No gap decomposition available for this batch.</p>
  }

  return (
    <div className="h-64 w-full rounded-lg border border-border p-3">
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
