import { createContext, useContext, useMemo, useState, type ReactNode } from "react"

export const PROVIDER_MODELS: Record<string, string[]> = {
  codex: ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"],
  copilot: ["claude-opus-5", "claude-sonnet-5", "gpt-5.6-terra", "gpt-5.6-sol"],
  claude: ["claude-sonnet-5", "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
  openrouter: ["openai/gpt-4o", "anthropic/claude-sonnet-4", "openai/gpt-5.4"],
}

interface LlmContextValue {
  provider: string
  model: string
  setProvider: (p: string) => void
  setModel: (m: string) => void
}

const LlmContext = createContext<LlmContextValue | null>(null)

export function LlmProvider({ children }: { children: ReactNode }) {
  const [provider, setProvider] = useState("codex")
  const [model, setModel] = useState(PROVIDER_MODELS.codex[0])

  const value = useMemo<LlmContextValue>(
    () => ({
      provider,
      model,
      setProvider: (p: string) => {
        setProvider(p)
        setModel(PROVIDER_MODELS[p]?.[0] ?? "")
      },
      setModel,
    }),
    [provider, model],
  )

  return <LlmContext.Provider value={value}>{children}</LlmContext.Provider>
}

export function useLlm() {
  const ctx = useContext(LlmContext)
  if (!ctx) throw new Error("useLlm must be used within LlmProvider")
  return ctx
}
