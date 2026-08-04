import { useState } from "react"
import { cn } from "@/lib/utils"

/** A collapsible tree viewer for arbitrary JSON, replacing the flat
 * `JSON.stringify` `<pre>` dump `MethodSpecViewer` used. Collapsed by
 * default below the top level so a large MethodSpec doesn't dump its
 * entire evidence-citation tree open at once. */
export function JsonTree({ data, name = "root", depth = 0 }: { data: unknown; name?: string; depth?: number }) {
  const [open, setOpen] = useState(depth < 1)

  if (data === null || data === undefined) {
    return (
      <div className="font-mono text-xs">
        <span className="text-muted-foreground">{name}:</span> <span className="text-muted-foreground">null</span>
      </div>
    )
  }

  if (typeof data !== "object") {
    return (
      <div className="font-mono text-xs">
        <span className="text-muted-foreground">{name}:</span>{" "}
        <span>{typeof data === "string" ? `"${data}"` : String(data)}</span>
      </div>
    )
  }

  const entries = Array.isArray(data) ? data.map((v, i) => [String(i), v] as const) : Object.entries(data)
  const isEmpty = entries.length === 0

  return (
    <div className="font-mono text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn("flex items-center gap-1 text-left", !isEmpty && "cursor-pointer hover:text-primary")}
        disabled={isEmpty}
      >
        {!isEmpty && <span>{open ? "▾" : "▸"}</span>}
        <span className="text-muted-foreground">{name}</span>
        <span className="text-muted-foreground">
          {Array.isArray(data) ? `[${entries.length}]` : `{${entries.length}}`}
        </span>
      </button>
      {open && !isEmpty && (
        <div className="ml-4 border-l border-border pl-2">
          {entries.map(([key, value]) => (
            <JsonTree key={key} name={key} data={value} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}
