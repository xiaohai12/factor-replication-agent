import { Component, type ErrorInfo, type ReactNode } from "react"

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

// No error boundary existed anywhere in the app -- any uncaught render/effect
// exception (e.g. a `localStorage` quota error) unmounts the whole React tree
// to a blank page with nothing in the UI explaining why. This is the last
// line of defense, not a substitute for fixing the underlying throw.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error:", error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col gap-2 p-6 text-sm">
          <p className="font-medium text-destructive">Something went wrong rendering this page.</p>
          <pre className="max-h-64 overflow-auto rounded-md border border-border bg-muted/30 p-2 text-xs">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            className="self-start rounded-md border border-border px-3 py-1 text-xs"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
