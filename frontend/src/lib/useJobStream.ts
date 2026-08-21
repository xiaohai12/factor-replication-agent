import { useEffect, useRef, useState } from "react"
import { api, type JobSnapshot } from "@/lib/api"

export interface JobState<T = unknown> {
  status: "idle" | "pending" | "running" | "completed" | "failed"
  logs: string[]
  result: T | null
  error: string | null
}

/**
 * Tracks a backend job's live progress over SSE (falls back to nothing
 * fancy -- if the EventSource errors out, the caller can still fetch
 * GET /api/jobs/{id} once via `refresh()`; the backend keeps a durable
 * snapshot so a page reload never loses the final result).
 */
export function useJobStream<T = unknown>(jobId: string | null) {
  const [state, setState] = useState<JobState<T>>({
    status: "idle",
    logs: [],
    result: null,
    error: null,
  })
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    sourceRef.current?.close()
    if (!jobId) {
      setState({ status: "idle", logs: [], result: null, error: null })
      return
    }
    setState({ status: "running", logs: [], result: null, error: null })

    const source = new EventSource(`/api/jobs/${jobId}/stream`)
    sourceRef.current = source

    source.addEventListener("log", (event) => {
      const message = JSON.parse((event as MessageEvent).data)
      setState((prev) => ({ ...prev, logs: [...prev.logs, message] }))
    })
    source.addEventListener("completed", (event) => {
      const result = JSON.parse((event as MessageEvent).data)
      setState((prev) => ({ ...prev, status: "completed", result }))
      source.close()
    })
    source.addEventListener("failed", (event) => {
      const error = JSON.parse((event as MessageEvent).data)
      setState((prev) => ({ ...prev, status: "failed", error }))
      source.close()
    })
    source.onerror = () => {
      // Connection dropped without a terminal event -- fall back to a
      // one-shot poll of the durable job snapshot rather than spinning.
      api
        .get<JobSnapshot<T>>(`/api/jobs/${jobId}`)
        .then((snapshot) => {
          setState({
            status: snapshot.status,
            logs: snapshot.log_history,
            result: snapshot.result,
            error: snapshot.error,
          })
        })
        .catch(() => undefined)
      source.close()
    }

    return () => source.close()
  }, [jobId])

  return state
}
