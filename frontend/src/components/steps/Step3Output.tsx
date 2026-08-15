import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { CodeView } from "@/components/CodeView"
import { JsonTree } from "@/components/JsonTree"
import { sessionApi } from "@/lib/sessionApi"
import { cn } from "@/lib/utils"
import type { StepAttempt } from "@/lib/types"

/** Mirrors `src/steps/step3_codegen/registry.py`'s `CONFIG_KEY_STAGE` --
 * single source of truth lives there; kept manually in sync here since the
 * config dict crosses the API boundary as untyped JSON. `sort_dims`/
 * `long_portfolios`/`short_portfolios` aren't in the backend map either
 * (written straight into the dict, never routed through `stage_of`) --
 * placed under "Portfolio" here since that's their only sensible home. */
const CONFIG_KEY_GROUPS: { label: string; keys: string[] }[] = [
  { label: "Signal input", keys: ["accounting_lag_months", "signal_max_staleness_months", "missing_action"] },
  {
    label: "Universe",
    keys: [
      "universe",
      "universe_filters",
      "universe_filter_join_sources",
      "apply_delisting_returns",
      "returns_table",
      "returns_layout",
    ],
  },
  {
    label: "Portfolio",
    keys: [
      "breakpoint_source",
      "breakpoint_quantiles",
      "weighting_rule",
      "rebalance_frequency",
      "holding_period_months",
      "formation_month",
      "formation_month_explicit",
      "long_leg",
      "short_leg",
      "long_portfolios",
      "short_portfolios",
      "sort_dims",
      "return_combination_type",
    ],
  },
  { label: "Sample", keys: ["sample_start_year", "sample_end_year", "publication_year"] },
  { label: "Estimator", keys: ["return_basis", "estimator"] },
]

// Rendered separately (menu-deviation audit trails), never as an ordinary config row.
const NON_ROW_KEYS = new Set(["substitutions", "defaults_applied", "unapplied_universe_filters"])

interface DefaultApplied {
  config_key: string
  value: unknown
  reason: string
  paper_value?: unknown
}

interface Substitution {
  field: string
  paper_value: unknown
  engine_value: unknown
  reason: string
  config_key: string | null
}

interface UnappliedFilter {
  concept_id: string
  op: string
  value: unknown
  reason: string
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4)
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** Small uppercase section header with a colored accent dot -- used both for
 * the five config-stage groups and the audit sections below them, so every
 * section in this card reads the same way at a glance. */
function SectionTitle({
  label,
  dotClassName = "bg-muted-foreground/50",
  count,
}: {
  label: string
  dotClassName?: string
  count?: number
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotClassName)} />
      <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</p>
      {typeof count === "number" && count > 0 && (
        <Badge variant="outline" className="h-4 px-1 text-[10px]">
          {count}
        </Badge>
      )}
    </div>
  )
}

function ConfigRow({
  configKey,
  value,
  substitutions,
  defaultApplied,
}: {
  configKey: string
  value: unknown
  substitutions: Substitution[]
  defaultApplied: DefaultApplied | undefined
}) {
  const rowTone =
    substitutions.length > 0
      ? "bg-amber-50 dark:bg-amber-950/20"
      : defaultApplied
        ? "bg-sky-50 dark:bg-sky-950/20"
        : ""
  const accentBar =
    substitutions.length > 0 ? "bg-amber-400" : defaultApplied ? "bg-sky-400" : "bg-transparent"
  return (
    <tr className={cn("align-top", rowTone)}>
      <td className={cn("w-1 rounded-l-sm", accentBar)} />
      <td className="w-56 py-1.5 pr-3 pl-2 font-mono text-xs text-muted-foreground">{configKey}</td>
      <td className="w-64 py-1.5 pr-3 font-mono text-xs font-medium">{formatValue(value)}</td>
      <td className="rounded-r-sm py-1.5 pr-2 text-xs">
        {substitutions.length === 0 && !defaultApplied && (
          <span className="text-muted-foreground/70">paper-specified</span>
        )}
        {substitutions.map((sub, i) => (
          <div key={i} className="flex flex-col gap-0.5 text-amber-900 dark:text-amber-300">
            <span className="flex items-center gap-1 font-medium">
              <span className="text-[10px] tracking-wide uppercase">Approved substitution</span>
            </span>
            <span>
              paper <span className="font-mono">{formatValue(sub.paper_value)}</span> → engine{" "}
              <span className="font-mono">{formatValue(sub.engine_value)}</span>
            </span>
            <span className="text-amber-800/70 dark:text-amber-400/70">{sub.reason}</span>
          </div>
        ))}
        {defaultApplied && (
          <div className="flex flex-col gap-0.5 text-sky-900 dark:text-sky-300">
            <span className="text-[10px] font-medium tracking-wide uppercase">Engine default</span>
            <span>
              paper <span className="font-mono">{formatValue(defaultApplied.paper_value)}</span>
            </span>
            <span className="text-sky-800/70 dark:text-sky-400/70">{defaultApplied.reason}</span>
          </div>
        )}
      </td>
    </tr>
  )
}

// One accent color per config-stage group, purely for quick visual scanning
// of the header dots -- has no semantic meaning beyond "same group".
const GROUP_DOT_CLASS: Record<string, string> = {
  "Signal input": "bg-violet-400",
  Universe: "bg-blue-400",
  Portfolio: "bg-emerald-400",
  Sample: "bg-orange-400",
  Estimator: "bg-pink-400",
  Other: "bg-muted-foreground/50",
}

function ConfigGroup({
  label,
  keys,
  config,
  substitutions,
  defaultsApplied,
}: {
  label: string
  keys: string[]
  config: Record<string, unknown>
  substitutions: Substitution[]
  defaultsApplied: DefaultApplied[]
}) {
  const present = keys.filter((k) => k in config)
  if (present.length === 0) return null
  return (
    <div className="flex flex-col gap-1.5">
      <SectionTitle label={label} dotClassName={GROUP_DOT_CLASS[label] ?? "bg-muted-foreground/50"} />
      <table className="w-full border-collapse">
        <tbody>
          {present.map((key) => (
            <ConfigRow
              key={key}
              configKey={key}
              value={config[key]}
              substitutions={substitutions.filter((s) => s.config_key === key)}
              defaultApplied={defaultsApplied.find((d) => d.config_key === key)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function shortHash(hash: string | undefined): string {
  if (!hash) return "—"
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash
}

function CopyButton({ text }: { text: string | undefined }) {
  const [copied, setCopied] = useState(false)
  if (!text) return null
  return (
    <button
      type="button"
      className="text-muted-foreground hover:text-foreground"
      title="Copy full hash"
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? "copied" : "📋"}
    </button>
  )
}

function usePlugin(sessionId: string, attempt: StepAttempt | undefined) {
  const refs = attempt?.output_refs ?? {}
  const pluginQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 3, refs.plugin_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, refs.plugin_ref),
    enabled: !!refs.plugin_ref,
  })
  return {
    plugin: pluginQuery.data ? (JSON.parse(pluginQuery.data.content) as Record<string, unknown>) : undefined,
    isLoading: pluginQuery.isLoading,
  }
}

/** Renders in the request/result grid's "Result" slot for step3 (in place
 * of the generic Result card, per the 2026-08-14 layout change) -- the rest
 * of step3's output (config table, script, debug) lives below in
 * `Step3Output`, which shares the same react-query cache key so this
 * doesn't cause a second fetch. */
export function Step3ComputeSignalCard({
  sessionId,
  attempt,
}: {
  sessionId: string
  attempt: StepAttempt | undefined
}) {
  const { plugin, isLoading } = usePlugin(sessionId, attempt)
  if (isLoading) return <p className="text-xs text-muted-foreground">Loading…</p>
  if (!plugin) return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
  return <CodeView code={(plugin.code as string) ?? ""} language="python" />
}

export function Step3Output({ sessionId, attempt }: { sessionId: string; attempt: StepAttempt | undefined }) {
  const refs = attempt?.output_refs ?? {}

  const { plugin } = usePlugin(sessionId, attempt)
  const scriptQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 3, refs.script_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, refs.script_ref),
    enabled: !!refs.script_ref,
  })
  const configQuery = useQuery({
    queryKey: ["step-artifact", sessionId, 3, refs.config_ref],
    queryFn: () => sessionApi.getStepArtifact(sessionId, 3, refs.config_ref),
    enabled: !!refs.config_ref,
  })

  if (!plugin && !scriptQuery.data && !configQuery.data) {
    return <p className="text-xs text-muted-foreground">No output recorded yet for this step.</p>
  }

  const config = configQuery.data ? (JSON.parse(configQuery.data.content) as Record<string, unknown>) : undefined
  const substitutions = (config?.substitutions as Substitution[] | undefined) ?? []
  const defaultsApplied = (config?.defaults_applied as DefaultApplied[] | undefined) ?? []
  const unappliedFilters = (config?.unapplied_universe_filters as UnappliedFilter[] | undefined) ?? []
  const unmatchedSubstitutions = substitutions.filter((s) => s.config_key === null)
  const repairTrace = (plugin?.repair_trace as string[] | undefined) ?? []
  const diagnostics = attempt?.diagnostics && "readiness" in attempt.diagnostics ? attempt.diagnostics : undefined

  // Any config key the grouping table above doesn't know about yet -- shown
  // in a fallback group rather than silently dropped (e.g. a future engine
  // config field this component hasn't been updated for).
  const knownKeys = new Set(CONFIG_KEY_GROUPS.flatMap((g) => g.keys))
  const unclassifiedKeys = config
    ? Object.keys(config).filter((k) => !knownKeys.has(k) && !NON_ROW_KEYS.has(k))
    : []

  return (
    <div className="flex flex-col gap-4">
      {plugin && (
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center gap-1 font-mono text-muted-foreground">
            script: {shortHash(refs.script_sha256)} <CopyButton text={refs.script_sha256} />
          </span>
          <span className="flex items-center gap-1 font-mono text-muted-foreground">
            code: {shortHash(plugin.code_hash as string | undefined)}
          </span>
          <Badge variant={plugin.validation_status === "passed" ? "default" : "outline"}>
            validation: {String(plugin.validation_status)}
          </Badge>
          {diagnostics && (
            <>
              <Badge variant={diagnostics.readiness === "ready" ? "default" : "destructive"}>
                readiness: {diagnostics.readiness}
              </Badge>
              {typeof diagnostics.counters?.repair_attempt_count === "number" &&
                diagnostics.counters.repair_attempt_count > 0 && (
                  <Badge variant="outline">repair attempts: {diagnostics.counters.repair_attempt_count}</Badge>
                )}
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {config && (
          <div className="flex flex-col gap-3 rounded-md border border-border p-3">
            {CONFIG_KEY_GROUPS.map((group) => (
              <ConfigGroup
                key={group.label}
                label={group.label}
                keys={group.keys}
                config={config}
                substitutions={substitutions}
                defaultsApplied={defaultsApplied}
              />
            ))}
            {unclassifiedKeys.length > 0 && (
              <ConfigGroup
                label="Other"
                keys={unclassifiedKeys}
                config={config}
                substitutions={substitutions}
                defaultsApplied={defaultsApplied}
              />
            )}
            {unappliedFilters.length > 0 && (
              <div className="flex flex-col gap-1.5 rounded-md border border-rose-400/40 bg-rose-50 p-2 dark:bg-rose-950/20">
                <SectionTitle
                  label="Unapplied universe filters"
                  dotClassName="bg-rose-400"
                  count={unappliedFilters.length}
                />
                <p className="text-[11px] text-rose-800/70 dark:text-rose-400/70">
                  Stated in the paper, not enforced by the engine.
                </p>
                <table className="w-full border-collapse text-xs">
                  <tbody>
                    {unappliedFilters.map((f, i) => (
                      <tr key={i} className="border-t border-rose-400/20 first:border-0">
                        <td className="py-1 pr-3 font-mono text-rose-900 dark:text-rose-300">{f.concept_id}</td>
                        <td className="py-1 pr-3 font-mono text-rose-900 dark:text-rose-300">
                          {f.op} {formatValue(f.value)}
                        </td>
                        <td className="py-1 text-rose-800/70 dark:text-rose-400/70">{f.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {unmatchedSubstitutions.length > 0 && (
              <div className="flex flex-col gap-1.5 rounded-md border border-amber-400/40 bg-amber-50 p-2 dark:bg-amber-950/20">
                <SectionTitle
                  label="Unmatched substitutions"
                  dotClassName="bg-amber-400"
                  count={unmatchedSubstitutions.length}
                />
                <p className="text-[11px] text-amber-800/70 dark:text-amber-400/70">
                  Approved during review, but not automatically linked to a config key above.
                </p>
                <table className="w-full border-collapse text-xs">
                  <tbody>
                    {unmatchedSubstitutions.map((s, i) => (
                      <tr key={i} className="border-t border-amber-400/20 first:border-0">
                        <td className="py-1 pr-3 font-mono text-amber-900 dark:text-amber-300">{s.field}</td>
                        <td className="py-1 pr-3 font-mono text-amber-900 dark:text-amber-300">
                          {formatValue(s.paper_value)} → {formatValue(s.engine_value)}
                        </td>
                        <td className="py-1 text-amber-800/70 dark:text-amber-400/70">{s.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {scriptQuery.data && (
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium">Assembled backtest script</p>
            <CodeView code={scriptQuery.data.content} language="python" maxHeightClassName="max-h-[80vh]" />
          </div>
        )}
      </div>

      <details>
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">Debug / provenance</summary>
        <div className={cn("mt-2 flex flex-col gap-2")}>
          {repairTrace.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium">Repair trace</p>
              {repairTrace.map((entry, i) => (
                <p key={i} className="text-xs text-muted-foreground">
                  {entry}
                </p>
              ))}
            </div>
          )}
          {diagnostics && diagnostics.flags.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium">Diagnostics flags</p>
              {diagnostics.flags.map((f, i) => (
                <p key={i} className="text-xs text-muted-foreground">
                  ⚑ {f}
                </p>
              ))}
            </div>
          )}
          {config && <JsonTree name="config" data={config} />}
        </div>
      </details>
    </div>
  )
}
