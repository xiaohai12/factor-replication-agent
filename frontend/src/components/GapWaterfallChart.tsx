import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

/** Per-switch contribution to the total replication gap, from whichever
 * decomposition this batch actually produced:
 *
 * - `gap_decomposition.contributions` (OAT, needs `ablation_*` tracks), plus
 *   its residual. NOT additive -- see `src/steps/step7_replication_diff/
 *   bundle.py` -- which is why this is a plain grouped bar chart, never a
 *   cumulative-offset waterfall that would visually imply additivity.
 * - `shapley_attribution.<line>.shapley_effects` (full factorial). A
 *   full-factorial batch runs no `ablation_*` tracks at all, so
 *   `gap_decomposition` is unavailable and this component used to render
 *   nothing -- yet Shapley effects sum EXACTLY to the total gap
 *   (`shapley_sum_check`), making them the stronger source rather than a
 *   fallback. When C&Z and HXZ lines both exist, they share one grouped chart
 *   with distinct colors; there is no residual bar because each line's effects
 *   sum exactly to its own total gap.
 */

type ShapleyLine = {
  available?: boolean
  shapley_effects?: Record<string, number>
  total_gap?: number
}

const LINE_TITLES: Record<string, string> = {
  to_hxz: "Gap to the HXZ standardized config",
  to_cz: "Gap to C&Z's actual config",
}

const LINE_COLORS: Record<string, string> = {
  to_cz: "#2563eb",
  to_hxz: "#dc2626",
}

function BarPanel({
  title,
  rows,
  note,
}: {
  title?: string
  rows: { switchName: string; value: number }[]
  note: string
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border p-3">
      {title && <p className="text-xs font-medium">{title}</p>}
      <div className="h-56 w-full">
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
      <p className="text-xs text-muted-foreground">{note}</p>
    </div>
  )
}

function GroupedShapleyPanel({ panels }: { panels: [string, ShapleyLine][] }) {
  const switches = [...new Set(panels.flatMap(([, result]) => Object.keys(result.shapley_effects ?? {})))]
  const rows = switches.map((switchName) => {
    const row: Record<string, string | number> = { switchName }
    for (const [line, result] of panels) {
      const value = result.shapley_effects?.[switchName]
      if (typeof value === "number") row[line] = value
    }
    return row
  })
  return (
    <div className="w-full max-w-2xl self-center rounded-lg border border-border p-3">
      <p className="text-xs font-medium">Gap to the controlled C&Z and HXZ configurations</p>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 8 }} barGap={4}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="switchName" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis tick={{ fontSize: 11 }} />
            <ReferenceLine y={0} className="stroke-border" />
            <Tooltip formatter={(value, name) => [Number(value).toFixed(4), LINE_TITLES[name as string] ?? name]} />
            <Legend formatter={(value) => LINE_TITLES[value] ?? value} wrapperStyle={{ fontSize: 11 }} />
            {panels.map(([line]) => (
              <Bar key={line} dataKey={line} fill={LINE_COLORS[line] ?? "var(--color-primary)"} barSize={28} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted-foreground">
        Shapley effects from separate full-factorial grids. Within each color they sum exactly to that line's total gap; compare colors descriptively because the two lines use different controlled configurations.
      </p>
    </div>
  )
}

export function GapWaterfallChart({
  gapDecomposition,
  shapleyAttribution,
}: {
  gapDecomposition: Record<string, unknown>
  shapleyAttribution?: Record<string, ShapleyLine>
}) {
  const contributions = (gapDecomposition?.contributions as Record<string, number> | undefined) ?? {}
  const oatRows = Object.entries(contributions).map(([switchName, value]) => ({ switchName, value }))
  if (typeof gapDecomposition?.residual === "number") {
    oatRows.push({ switchName: "residual", value: gapDecomposition.residual })
  }
  if (oatRows.length > 0) {
    return (
      <BarPanel
        rows={oatRows}
        note="One-at-a-time contributions: not guaranteed to be additive, so these bars need not sum to the total gap -- the residual bar is what is left unexplained."
      />
    )
  }

  const shapleyPanels = Object.entries(shapleyAttribution ?? {}).filter(
    ([, line]) => line?.available && Object.keys(line.shapley_effects ?? {}).length > 0,
  )

  if (shapleyPanels.length === 0) {
    return <p className="text-xs text-muted-foreground">No gap decomposition available for this batch.</p>
  }

  return <GroupedShapleyPanel panels={shapleyPanels.sort(([a], [b]) => a.localeCompare(b))} />
}
