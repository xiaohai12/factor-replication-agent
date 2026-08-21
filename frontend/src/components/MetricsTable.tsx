import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4)
  }
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

export function MetricsTable({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics).filter(([key]) => key !== "by_sample_period")
  return (
    <Table>
      <TableBody>
        {entries.map(([key, value]) => (
          <TableRow key={key}>
            <TableCell className="font-medium text-muted-foreground">{key}</TableCell>
            <TableCell>{formatValue(value)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
