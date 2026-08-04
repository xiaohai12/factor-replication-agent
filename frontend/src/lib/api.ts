const API_BASE = "" // same-origin; Vite dev server proxies /api -> :8000

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new ApiError(res.status, text)
  }
  const contentType = res.headers.get("content-type") ?? ""
  if (contentType.includes("application/json")) {
    return res.json() as Promise<T>
  }
  return res.text() as unknown as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "DELETE", body: body === undefined ? undefined : JSON.stringify(body) }),
  /** Plain-text GET (e.g. an evidence file download) -- bypasses the JSON
   * content-type branch in `request()` since these responses are CSV/text. */
  getText: async (path: string): Promise<string> => {
    const res = await fetch(`${API_BASE}${path}`)
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new ApiError(res.status, text)
    }
    return res.text()
  },
  upload: async <T>(path: string, file: File): Promise<T> => {
    const form = new FormData()
    form.append("file", file)
    const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new ApiError(res.status, text)
    }
    return res.json() as Promise<T>
  },
  /** Multipart POST with extra form fields alongside the file (e.g. the
   * session step1 PDF-upload endpoint, which also needs expected_revision/
   * llm_provider as form fields). */
  postForm: async <T>(path: string, file: File, fields: Record<string, string>): Promise<T> => {
    const form = new FormData()
    form.append("file", file)
    Object.entries(fields).forEach(([k, v]) => form.append(k, v))
    const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new ApiError(res.status, text)
    }
    return res.json() as Promise<T>
  },
}

export interface JobSnapshot<T = unknown> {
  job_id: string
  status: "pending" | "running" | "completed" | "failed"
  result: T | null
  error: string | null
  log_history: string[]
}
