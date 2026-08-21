import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import { cn } from "@/lib/utils"

/** IDE-like code viewer (Prism via `react-syntax-highlighter`, VS Code Dark+
 * theme) with line numbers -- follow-up to the plain `<pre>` version this
 * replaced. `maxHeightClassName` defaults to a short snippet-sized box;
 * pass a taller one (e.g. `max-h-[80vh]`) for a full-file view like the
 * assembled backtest script. */
export function CodeView({
  code,
  language,
  maxHeightClassName = "max-h-96",
}: {
  code: string
  language?: string
  maxHeightClassName?: string
}) {
  return (
    <div className={cn("overflow-auto rounded-md border border-border", maxHeightClassName)}>
      {language && (
        <div className="border-b border-border bg-muted px-2 py-1 text-xs text-muted-foreground">{language}</div>
      )}
      <SyntaxHighlighter
        language={language ?? "text"}
        style={vscDarkPlus}
        showLineNumbers
        customStyle={{ margin: 0, fontSize: "0.75rem", borderRadius: 0 }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}
