// Minimal CSV parser for the generated backtest script's `return_series.csv`
// / `signal_series` exports -- these are plain numeric columns with no
// quoted/escaped commas, so a full CSV library isn't warranted here.

export function parseSimpleCsv(text: string): Record<string, string>[] {
  const lines = text.trim().split(/\r?\n/)
  if (lines.length === 0) return []
  const headers = lines[0].split(",")
  return lines.slice(1).map((line) => {
    const cells = line.split(",")
    const row: Record<string, string> = {}
    headers.forEach((h, i) => {
      row[h] = cells[i] ?? ""
    })
    return row
  })
}
