import { NavLink, Outlet } from "react-router-dom"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { PROVIDER_MODELS, useLlm } from "@/lib/llmContext"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { to: "/runs", label: "Runs" },
  { to: "/extract", label: "Extractor" },
  { to: "/review", label: "Review & Resolve" },
  { to: "/backtest", label: "Backtest & Experiments" },
  { to: "/trace", label: "Trace & Logs" },
  { to: "/schema", label: "Schema Reference" },
  { to: "/data-catalog", label: "Data Catalog" },
]

const COMING_SOON = ["MetaCoder", "Replication Diagnosis"]

export function AppLayout() {
  const { provider, model, setProvider, setModel } = useLlm()

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-64 shrink-0 flex-col gap-6 border-r border-border p-4">
        <div>
          <h1 className="text-lg font-semibold">Factor Replication Agent</h1>
          <p className="text-xs text-muted-foreground">Pipeline dashboard</p>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-foreground hover:bg-muted",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
          <div className="mt-2 border-t border-border pt-2">
            {COMING_SOON.map((label) => (
              <div
                key={label}
                className="cursor-not-allowed rounded-md px-3 py-2 text-sm text-muted-foreground"
                title="Coming soon"
              >
                {label}
              </div>
            ))}
          </div>
        </nav>

        <div className="mt-auto flex flex-col gap-2 border-t border-border pt-4">
          <label className="text-xs font-medium text-muted-foreground">LLM Provider</label>
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(PROVIDER_MODELS).map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <label className="text-xs font-medium text-muted-foreground">Model</label>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(PROVIDER_MODELS[provider] ?? []).map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
