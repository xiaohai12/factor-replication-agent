export function MethodSpecViewer({ spec, title }: { spec: unknown; title?: string }) {
  return (
    <details className="rounded-lg border border-border" open={false}>
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        {title ?? "MethodSpec JSON"}
      </summary>
      <pre className="max-h-96 overflow-auto rounded-b-lg bg-muted p-3 text-xs">
        {JSON.stringify(spec, null, 2)}
      </pre>
    </details>
  )
}
