import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

type RejectedClaim = { reason: string; claim: Record<string, unknown> }

type Section = "reproduction" | "robustness" | "vs_cz" | "spec_quality" | "gap_split" | null

// docs/step7-8.md readability redesign: one line-item in a card's compact
// table -- most items in a homogeneous set (config divergences, per-switch
// effects, weak spec fields) need only a value comparison, not a full
// templated sentence. `note` is the only per-row prose, reserved for rows
// that genuinely need explanation (an `unresolved` classification, or an
// individually significant effect); a routine/explained row leaves it
// empty.
type SummaryRow = {
  label: string
  ours?: string
  theirs?: string
  effect?: string
  tag?: string
  note?: string
}

type DiagnosisSummary = {
  comparison_line?: string | null
  // docs/step7-8.md Part XVI: which of the 4 reader-facing sections this
  // entry belongs to. `null`/missing on a pre-2026-08-18 persisted
  // diagnosis.json -- falls back to a generic, unbadged rendering rather
  // than crashing.
  section?: Section
  overall_tag: string
  per_switch_summary: Record<string, string>
  joint_supported: boolean | null
  dominant_switches: string[]
  // docs/step7-8.md readability redesign: inverted-pyramid layout --
  // `headline` (bottom line, always shown first) names its own comparison
  // target in plain language, so no separate "vs. X" title is needed;
  // `intro` states a shared caveat/classification note ONCE for the whole
  // card instead of repeating it on every row; `rows` is the compact table
  // of same-shape items; `narrative` holds standalone sentences that are
  // not about any one row; `footnote` is a de-emphasized technical caveat.
  headline: string
  intro: string
  rows: SummaryRow[]
  narrative: string[]
  footnote: string
  // docs/step7-8.md Part XVI: {short label: long explanation} for every
  // setting mentioned by short name -- rendered as hover-tooltip terms, not
  // inlined into every sentence.
  glossary?: Record<string, string>
}

type VsPaperSummary = {
  section?: Section
  headline: string
  intro: string
  rows: SummaryRow[]
  narrative: string[]
  footnote: string
  glossary?: Record<string, string>
}

// docs/step7-8.md "Step B": whether C&Z's and HXZ's own self-reported
// numbers for this factor agree or conflict with EACH OTHER -- independent
// of anything this engine ran. Rendered as its own banner ahead of every
// other card, since it is context a reader needs before asking whether OUR
// replication agrees with the paper.
type PaperVerdictAgreement = {
  available: boolean
  verdict: "agree_significant" | "agree_insignificant" | "conflict" | "unavailable"
  headline: string
}

function paperVerdictBannerClass(verdict: PaperVerdictAgreement["verdict"]): string {
  if (verdict === "conflict") {
    return "border-amber-600/30 bg-amber-500/10 text-amber-900 dark:text-amber-300"
  }
  if (verdict === "agree_significant" || verdict === "agree_insignificant") {
    return "border-sky-600/30 bg-sky-500/10 text-sky-900 dark:text-sky-300"
  }
  return ""
}

function PaperVerdictBanner({ agreement }: { agreement?: PaperVerdictAgreement }) {
  if (!agreement || !agreement.available || !agreement.headline) return null
  return (
    <div className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", paperVerdictBannerClass(agreement.verdict))}>
      {agreement.verdict === "conflict" && <span aria-hidden="true">⚠</span>}
      <span>{agreement.headline}</span>
    </div>
  )
}

// docs/step7-8.md Part XVI: reading order is by READER QUESTION, not by
// comparison target -- reproduction (did it replicate?) first, robustness
// (is it stable?) second, vs C&Z (why do we disagree?) third, then the
// gap split (where does another implementer's distance from the paper sit?);
// the legacy claim-only overflow entry (pre-2026-08-18 batches, no section of
// its own) goes last.
function sectionPriority(section?: Section): number {
  if (section === "robustness") return 0
  if (section === "vs_cz") return 1
  if (section === "gap_split") return 2
  if (section == null) return 3
  return 4
}

// Eyebrow label + left-border accent per section, so the reader can tell the
// project's core research question (vs_cz) apart from supporting robustness
// evidence at a glance, without repeating a raw line id anywhere.
function sectionEyebrow(section?: Section, comparisonLine?: string | null): string {
  if (section === "vs_cz") return "Disagreement with C&Z"
  if (section === "robustness") return "Robustness"
  if (section === "spec_quality") return "How clearly did the paper specify the method"
  if (section === "gap_split") return "Where the distance from the paper's own number sits"
  if (comparisonLine) return `Comparison: ${comparisonLine.replaceAll("_", " ")}`
  return "Other findings"
}

function sectionAccentClass(section?: Section): string {
  if (section === "vs_cz") return "border-l-primary"
  if (section === "robustness") return "border-l-amber-500"
  if (section === "spec_quality") return "border-l-muted-foreground/40"
  if (section === "gap_split") return "border-l-sky-500"
  return "border-l-border"
}

// Maps step7's `classify_overall` verdict tags to a color that reads as
// good/neutral/bad at a glance, without a legend. Falls back to a neutral
// style for older persisted `close_replication`/`sign_agrees_magnitude_differs`/
// `sign_mismatch` tags (pre-2026-08-18 diagnosis.json) and any unknown tag.
function overallTagClass(tag: string): string {
  if (tag === "reproduced" || tag === "close_replication") {
    return "border-emerald-600/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
  }
  if (tag === "contradicted" || tag === "sign_mismatch") {
    return "border-destructive/30 bg-destructive/10 text-destructive"
  }
  if (tag === "not_reproduced" || tag === "sign_agrees_magnitude_differs") {
    return "border-amber-600/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"
  }
  return ""
}

// Short inline mentions (e.g. "portfolio weighting") get their long,
// zero-background explanation as a native hover tooltip here instead of
// repeating it inline every time the setting is mentioned (docs/step7-8.md
// Part XVI).
function GlossaryTerms({ glossary }: { glossary?: Record<string, string> }) {
  const entries = Object.entries(glossary ?? {})
  if (entries.length === 0) return null
  return (
    <p className="text-xs text-muted-foreground">
      <span className="mr-1">Terms:</span>
      {entries.map(([term, definition], i) => (
        <span key={term}>
          <span title={definition} className="cursor-help underline decoration-dotted">
            {term}
          </span>
          {i < entries.length - 1 ? ", " : ""}
        </span>
      ))}
    </p>
  )
}

// docs/step7-8.md readability redesign: the compact table -- one row per
// item in a homogeneous set. Each row shows its own label/tag/values/effect
// and, only when it needs one, a `note` -- the shared reasoning behind a
// whole group of rows lives once in the card's `intro` instead (rendered by
// `SummaryCardBody`), not repeated here per row.
function SummaryRows({ rows }: { rows: SummaryRow[] }) {
  if (rows.length === 0) return null
  return (
    <ul className="flex flex-col gap-1.5 text-sm text-foreground/90">
      {rows.map((row, i) => (
        <li key={i} className="rounded-md border border-border/60 px-2 py-1.5">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-medium">{row.label}</span>
            {row.tag && (
              <span className="rounded-full border border-border/60 px-1.5 py-0 text-[11px] text-muted-foreground">
                {row.tag}
              </span>
            )}
          </div>
          {(row.ours || row.theirs) && (
            <p className="text-xs text-muted-foreground">
              {row.ours && <>ours: {row.ours}</>}
              {row.ours && row.theirs && " · "}
              {row.theirs && <>theirs: {row.theirs}</>}
            </p>
          )}
          {row.effect && <p className="text-xs text-muted-foreground">Effect: {row.effect}</p>}
          {row.note && <p className="text-xs text-foreground/90">{row.note}</p>}
        </li>
      ))}
    </ul>
  )
}

// Standalone sentences not tied to any one row above -- an aggregate fact
// or a cross-cutting verdict.
function NarrativeList({ narrative }: { narrative: string[] }) {
  if (narrative.length === 0) return null
  return (
    <ul className="flex flex-col gap-1 text-sm text-foreground/90">
      {narrative.map((n, i) => (
        <li key={i} className="flex gap-2">
          <span className="text-muted-foreground">·</span>
          <span>{n}</span>
        </li>
      ))}
    </ul>
  )
}

// Shared card body -- `SummaryCard` and `ReproductionCard` differ only in
// their header (eyebrow vs. verdict badge), not in how `intro`/`rows`/
// `narrative`/`footnote`/`glossary` render.
function SummaryCardBody({
  intro,
  rows,
  narrative,
  footnote,
  glossary,
}: {
  intro: string
  rows: SummaryRow[]
  narrative: string[]
  footnote: string
  glossary?: Record<string, string>
}) {
  if (!intro && rows.length === 0 && narrative.length === 0 && !footnote && !glossary) return null
  return (
    <CardContent className="flex flex-col gap-2">
      {intro && <p className="text-xs text-muted-foreground italic">{intro}</p>}
      <SummaryRows rows={rows} />
      <NarrativeList narrative={narrative} />
      <GlossaryTerms glossary={glossary} />
      {footnote && (
        <>
          {(rows.length > 0 || narrative.length > 0) && <Separator />}
          <p className="text-xs text-muted-foreground italic">{footnote}</p>
        </>
      )}
    </CardContent>
  )
}

function SummaryCard({ summary }: { summary: DiagnosisSummary }) {
  // Old persisted diagnosis.json (pre-readability-redesign) has no
  // rows/narrative/headline -- never assume these exist, or a stale session
  // crashes the whole page.
  const rows = summary.rows ?? []
  const narrative = summary.narrative ?? []
  if (!summary.headline && rows.length === 0 && narrative.length === 0) return null
  return (
    <Card size="sm" className={cn("gap-2 border-l-4 shadow-none", sectionAccentClass(summary.section))}>
      <CardHeader className="gap-1.5">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {sectionEyebrow(summary.section, summary.comparison_line)}
        </p>
        {summary.headline && <CardTitle className="text-sm leading-snug font-semibold">{summary.headline}</CardTitle>}
      </CardHeader>
      <SummaryCardBody
        intro={summary.intro ?? ""}
        rows={rows}
        narrative={narrative}
        footnote={summary.footnote}
        glossary={summary.glossary}
      />
    </Card>
  )
}

// The "reproduction" section: baseline vs the paper's own reported result.
// The ONLY place `overall_tag` is rendered as a badge -- it describes
// exactly this comparison (docs/step7-8.md Part XVI), and showing it again
// on the robustness/vs_cz cards previously made readers misread it as
// "we disagree with C&Z" or "we disagree with HXZ", which it never meant.
function ReproductionCard({ summary, overallTag }: { summary: VsPaperSummary; overallTag: string }) {
  if (!summary.headline) return null
  return (
    <Card size="sm" className="gap-2 border-l-4 border-l-primary shadow-none">
      <CardHeader className="gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Reproduction verdict</p>
          <Badge variant="outline" className={overallTagClass(overallTag)}>
            {overallTag.replaceAll("_", " ")}
          </Badge>
        </div>
        <CardTitle className="text-sm leading-snug font-semibold">{summary.headline}</CardTitle>
      </CardHeader>
      <SummaryCardBody
        intro={summary.intro ?? ""}
        rows={summary.rows ?? []}
        narrative={summary.narrative ?? []}
        footnote={summary.footnote}
        glossary={summary.glossary}
      />
    </Card>
  )
}

/** step8's diagnosis report (docs/step7-8.md Part XVI): a `PaperVerdictBanner`
 * ("Step B" -- do C&Z's and HXZ's own numbers even agree with each other,
 * independent of anything we ran) shown first, ahead of the 4 reader-facing
 * section cards -- reproduction, robustness, vs C&Z, spec quality -- each its
 * own card, badge shown ONLY on the reproduction card. The vs_cz/robustness
 * cards' own bullets also fold in "Step A" (whether reimplementing that
 * implementer's config reproduces the number THEY got) via `summary.py`, so
 * no separate card is needed for that half. The old per-analysis_stage
 * "Findings" claim listing stays dropped (Part XV §15.4): every card here is
 * built directly from the bundle, never from claims. `claims`/`rendered_
 * sentence` are still returned by the API for citation/audit, just not
 * rendered here; the rejected-claims audit trail is kept since it serves a
 * different purpose (validation transparency). */
export function Step8Output({ diagnosis }: { diagnosis: Record<string, unknown> }) {
  const rejected = (diagnosis.rejected_claims as RejectedClaim[] | undefined) ?? []
  const summary = [...((diagnosis.summary as DiagnosisSummary[] | undefined) ?? [])].sort(
    (a, b) => sectionPriority(a.section) - sectionPriority(b.section),
  )
  const vsPaperSummary = diagnosis.vs_paper_summary as VsPaperSummary | undefined
  const specQualitySummary = diagnosis.spec_quality_summary as DiagnosisSummary | undefined
  const paperVerdictAgreement = diagnosis.paper_verdict_agreement as PaperVerdictAgreement | undefined
  const overallTag = String(diagnosis.overall_tag ?? "inconclusive")

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{String(diagnosis.status ?? "").replaceAll("_", " ")}</Badge>
      </div>

      <PaperVerdictBanner agreement={paperVerdictAgreement} />

      <div className="flex flex-col gap-2">
        {vsPaperSummary && <ReproductionCard summary={vsPaperSummary} overallTag={overallTag} />}
        {summary.map((s, i) => (
          <SummaryCard key={i} summary={s} />
        ))}
        {specQualitySummary && <SummaryCard summary={specQualitySummary} />}
        {!vsPaperSummary?.headline && summary.length === 0 && !specQualitySummary?.headline && (
          <p className="text-xs text-muted-foreground">No deterministic summary available.</p>
        )}
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
