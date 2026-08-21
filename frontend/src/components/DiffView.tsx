import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function fmt(v: unknown): string {
  if (v === undefined) return "—"
  if (v === null) return "null"
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}

/** Generic dict-vs-dict diff table -- only rows whose value differs are
 * shown by default. Used for config-vs-config (step7 `config_diff`) and can
 * also diff two flat MethodSpec-derived dicts. */
export function DiffView({
  left,
  right,
  leftLabel = "before",
  rightLabel = "after",
}: {
  left: Record<string, unknown> | undefined | null
  right: Record<string, unknown> | undefined | null
  leftLabel?: string
  rightLabel?: string
}) {
  const safeLeft = left ?? {}
  const safeRight = right ?? {}
  const keys = Array.from(new Set([...Object.keys(safeLeft), ...Object.keys(safeRight)])).sort()
  const changed = keys.filter((k) => JSON.stringify(safeLeft[k]) !== JSON.stringify(safeRight[k]))

  if (changed.length === 0) {
    return <p className="text-xs text-muted-foreground">No differences.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>field</TableHead>
          <TableHead>{leftLabel}</TableHead>
          <TableHead>{rightLabel}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {changed.map((key) => (
          <TableRow key={key}>
            <TableCell className="font-mono text-xs">{key}</TableCell>
            <TableCell className="font-mono text-xs">{fmt(safeLeft[key])}</TableCell>
            <TableCell className="font-mono text-xs text-primary">{fmt(safeRight[key])}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
