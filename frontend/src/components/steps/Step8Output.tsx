import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

type RejectedClaim = { reason: string; claim: Record<string, unknown> }

type DiagnosisSummary = {
  comparison_line?: string | null
  overall_tag: string
  per_switch_summary: Record<string, string>
  joint_supported: boolean | null
  dominant_switches: string[]
  // docs/step7-8.md Part XII: inverted-pyramid layout -- `headline` (bottom
  // line, always shown first) names its own comparison target in plain
  // language, so no separate "vs. X" title is needed; `details` are
  // supporting bullets in decreasing importance; `footnote` is a
  // de-emphasized technical caveat.
  headline: string
  details: string[]
  footnote: string
}

type VsPaperSummary = {
  headline: string
  details: string[]
  footnote: string
}

// docs/step7-8.md Part XI: `to_cz` is the project's core research question
// (AGENTS.md -- inter-implementer agreement), always shown first; `to_hxz`
// is supporting sensitivity context; the line-less ("Overall") card goes last.
function summaryLinePriority(comparisonLine?: string | null): number {
  if (comparisonLine === "to_cz") return 0
  if (comparisonLine === "to_hxz") return 1
  if (comparisonLine == null) return 3
  return 2
}

// Eyebrow label + left-border accent per comparison line, so the reader can
// tell the core research question (to_cz) apart from supporting sensitivity
// context (to_hxz) at a glance, without repeating the raw line id anywhere.
function lineEyebrow(comparisonLine?: string | null): string {
  if (comparisonLine === "to_cz") return "Core comparison · vs. C&Z"
  if (comparisonLine === "to_hxz") return "Supporting context · vs. HXZ standardized"
  return "Overall"
}

function lineAccentClass(comparisonLine?: string | null): string {
  if (comparisonLine === "to_cz") return "border-l-primary"
  if (comparisonLine === "to_hxz") return "border-l-amber-500"
  return "border-l-border"
}

// Maps step7's `classify_overall` verdict tags to a color that reads as
// good/neutral/bad at a glance, without a legend.
function overallTagClass(tag: string): string {
  if (tag === "close_replication") {
    return "border-emerald-600/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
  }
  if (tag === "sign_mismatch") {
    return "border-destructive/30 bg-destructive/10 text-destructive"
  }
  if (tag === "sign_agrees_magnitude_differs") {
    return "border-amber-600/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"
  }
  return ""
}

function SummaryCard({ summary }: { summary: DiagnosisSummary }) {
  // Old persisted diagnosis.json (pre-Part-XII) has no details/headline --
  // never assume these exist, or a stale session crashes the whole page.
  const details = summary.details ?? []
  if (!summary.headline && details.length === 0) return null
  return (
    <Card size="sm" className={cn("gap-2 border-l-4 shadow-none", lineAccentClass(summary.comparison_line))}>
      <CardHeader className="gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {lineEyebrow(summary.comparison_line)}
          </p>
          <Badge variant="outline" className={overallTagClass(summary.overall_tag)}>
            {summary.overall_tag.replaceAll("_", " ")}
          </Badge>
        </div>
        {summary.headline && <CardTitle className="text-sm leading-snug font-semibold">{summary.headline}</CardTitle>}
      </CardHeader>
      {(details.length > 0 || summary.footnote) && (
        <CardContent className="flex flex-col gap-2">
          {details.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm text-foreground/90">
              {details.map((d, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-muted-foreground">·</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
          {summary.footnote && (
            <>
              {details.length > 0 && <Separator />}
              <p className="text-xs text-muted-foreground italic">{summary.footnote}</p>
            </>
          )}
        </CardContent>
      )}
    </Card>
  )
}

function VsPaperCard({ summary }: { summary: VsPaperSummary }) {
  if (!summary.headline) return null
  const details = summary.details ?? []
  return (
    <Card size="sm" className="gap-2 border-l-4 border-l-muted-foreground/40 shadow-none">
      <CardHeader className="gap-1.5">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Vs. the paper's own reported result
        </p>
        <CardTitle className="text-sm leading-snug font-semibold">{summary.headline}</CardTitle>
      </CardHeader>
      {(details.length > 0 || summary.footnote) && (
        <CardContent className="flex flex-col gap-2">
          {details.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm text-foreground/90">
              {details.map((d, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-muted-foreground">·</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
          {summary.footnote && (
            <>
              {details.length > 0 && <Separator />}
              <p className="text-xs text-muted-foreground italic">{summary.footnote}</p>
            </>
          )}
        </CardContent>
      )}
    </Card>
  )
}

/** step8's diagnosis report (docs/step7-8.md Part XV §15.4): only the
 * deterministic Summary section (one card per comparison line, plus the
 * vs-paper card) is shown -- the old per-analysis_stage "Findings" claim
 * listing was dropped entirely, since `SummaryCard`/`VsPaperCard` are built
 * directly from the bundle (not from claims) and never depended on it for
 * content. `claims`/`rendered_sentence` are still returned by the API for
 * citation/audit, just not rendered here anymore; the rejected-claims audit
 * trail is kept since it serves a different purpose (validation
 * transparency, not a findings duplicate). */
export function Step8Output({ diagnosis }: { diagnosis: Record<string, unknown> }) {
  const rejected = (diagnosis.rejected_claims as RejectedClaim[] | undefined) ?? []
  const summary = [...((diagnosis.summary as DiagnosisSummary[] | undefined) ?? [])].sort(
    (a, b) => summaryLinePriority(a.comparison_line) - summaryLinePriority(b.comparison_line),
  )
  const vsPaperSummary = diagnosis.vs_paper_summary as VsPaperSummary | undefined
  const overallTag = String(diagnosis.overall_tag ?? "inconclusive")

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{String(diagnosis.status ?? "").replaceAll("_", " ")}</Badge>
        <Badge variant="outline" className={overallTagClass(overallTag)}>
          overall: {overallTag.replaceAll("_", " ")}
        </Badge>
      </div>

      <div className="flex flex-col gap-2">
        {summary.length === 0 ? (
          <p className="text-xs text-muted-foreground">No deterministic summary available.</p>
        ) : (
          summary.map((s, i) => <SummaryCard key={i} summary={s} />)
        )}
        {vsPaperSummary && <VsPaperCard summary={vsPaperSummary} />}
      </div>

      {rejected.length > 0 && (
        <details className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
          <summary className="cursor-pointer font-medium text-destructive">
            Rejected claims (audit) · {rejected.length}
          </summary>
          <div className="mt-2 flex flex-col gap-1">
            {rejected.map((r, i) => (
              <p key={i} className="text-muted-foreground">
                ⚑ {r.reason}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
