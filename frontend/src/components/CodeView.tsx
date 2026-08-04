/** Plain code viewer with line numbers -- no syntax-highlighting dependency
 * added (none of the pre-existing pages pull one in either; `PluginRecord`
 * code is currently shown in a bare `<pre>`/`<Textarea>`). Scoped
 * deliberately: adding a highlighter is a legitimate follow-up, not blocked
 * on anything here. */
export function CodeView({ code, language }: { code: string; language?: string }) {
  const lines = code.split("\n")
  return (
    <div className="max-h-96 overflow-auto rounded-md border border-border bg-muted">
      {language && (
        <div className="border-b border-border px-2 py-1 text-xs text-muted-foreground">{language}</div>
      )}
      <pre className="p-2 text-xs">
        <code>
          {lines.map((line, i) => (
            <div key={i} className="flex gap-3">
              <span className="w-8 shrink-0 select-none text-right text-muted-foreground">{i + 1}</span>
              <span className="whitespace-pre-wrap">{line}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  )
}
