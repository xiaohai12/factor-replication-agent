# Known gaps: paper-first (v2) MethodSpec pipeline

Found via a live, real-paper, real-WRDS-data session E2E run (2026-08-07):
"Asset Growth and the Cross Section of Stock Returns.pdf" (Cooper, Gulen,
Schill 2008) through `POST /api/methodspecs/{extract,review,resolve}`
+ session steps 3-8. The run ultimately succeeded end to end, but only after
manually working around the 3 gaps below (see `/memories/repo/
build_commands.md` 2026-08-07 entry for the full reproduction trace,
including the exact request/response bodies and a step-by-step column-trace
debug session). None of these are fixed yet -- each needs real design work,
not a quick patch.

## 1. Extractor doesn't reliably emit canonical engine enum tokens

**Partially fixed 2026-08-08**: `build_method_spec`
(`src/steps/step1_extractor/extractor.py`) now calls
`normalize_engine_vocabulary()` on the raw LLM JSON before validation, which
canonicalizes known `weighting` synonyms (e.g. `"value-weighted"` -> `"vw"`)
and long/short-spread phrasing in `return_combination` (-> `extreme_group_
spread`/`average_leg_spread`) via exact/keyword rules -- never a guess: text
it doesn't recognize is left untouched so review's D4 check still blocks it.
This covers the two fields actually observed drifting in the 2026-08-07
session. Still NOT covered: `construction_type`, `sort.group_type`, and any
other free-text-vs-enum field that might drift the same way -- if a new one
surfaces, extend `normalize_engine_vocabulary` rather than re-diagnosing this
same root cause. The underlying "no resolution-time UI/endpoint to fix a
genuinely unmapped value" gap described below is still open.

`prompts/extractor/methodspec_extractor.md` documents the exact required
tokens (e.g. `portfolio.weighting` must be `vw`/`ew`/`other`/`unspecified`;
`portfolio.return_combination.type` must be one of `extreme_group_spread`/
`average_leg_spread`/`single_signal_portfolio_return`/`full_portfolio_return`/
`other`/`unspecified`), but the LLM extractor (`step1`) doesn't always follow
it. For this paper it produced:

- `portfolio.weighting.value = "value-weighted"` (should be `"vw"`)
- `portfolio.return_combination.value` = a free-text sentence describing the
  long/short legs (should be `"extreme_group_spread"`)

`review_method_spec`'s D4 engine-capability check
(`src/steps/step2_reviewer/review.py`) correctly flags both as
`kind="unsupported"`, `disposition=blocked` -- that part is working exactly
as designed ("paper vocabulary is separate from the engine menu"). The gap
is that there's no resolution-time correction step in the new paper-first
flow: a human (or an LLM-assisted resolver) needs some way to map the
paper's free-text value to the correct menu token before `resolve` can
produce an `is_ready=True` spec. Right now the only way to unblock this is
to hand-edit the persisted draft JSON on disk.

**Needed fix (not started):** a resolution-time step (endpoint + UI, or an
LLM-assisted normalization pass) that lets a reviewer pick/confirm the
correct engine-menu token for any `kind="unsupported"` finding whose root
cause is "free text needs mapping to a menu value" (as opposed to a genuine
engine-capability gap that really can't be run at all).

## 2. Universe filter *values* aren't normalized to physical encodings

Even after concept-name resolution works (see the `implementation_resolution.py`
fix in the same session -- `universe.filters[].concept_id` now gets a
`concept_mapping` entry same as `data.fields`), the filter *value* itself is
still whatever free-form label the extractor wrote, not the physical
column's actual encoding.

For this paper: `{"concept_id": "exchange", "op": "in", "value": ["NYSE",
"Amex", "NASDAQ"]}` -- human-readable exchange names -- while the physical
`exchcd` column (`src/infra/data_layer/sources.py`'s `CIZ_EXCHCD_MAP`) holds
numeric codes `{"N": 1, "A": 2, "Q": 3}`.

`BacktestExecutor.apply_universe_filters` does no label -> code translation,
so `series.isin(["NYSE", "Amex", "NASDAQ"])` against an integer column is
just always `False` -- the filter silently excludes every row instead of
raising. That doesn't fail immediately either: the resulting empty panel
cascades several engine steps downstream (`filter_universe` -> 0 rows ->
`apply_signal_holding_period`'s `self.formation` falls back to a bare
`[permno, cohort, signal]` frame with no CRSP columns carried over at all)
before finally surfacing as a confusing, seemingly-unrelated error in
`compute_breakpoints`: *"config['breakpoint_source']=='nyse' requires an
'exchcd' column ... but the loaded returns panel has none"* -- even though
`exchcd` genuinely exists with real values immediately after `load_data()`.

**Needed fix (not started):** a per-concept value-encoding normalizer (a
label -> physical-code table keyed by concept, analogous to the existing
`CIZ_EXCHCD_MAP`) wired into resolution/`build_config`, plus ideally a
fail-loud check at build/validate time (not several steps downstream) when a
filter's `value` doesn't overlap the column's actual value domain at all.

## 3. Some universe filter concepts aren't physical columns at all

The paper's "a firm must be listed on Compustat for 2 years before inclusion"
backfill-bias exclusion extracted as `{"concept_id":
"compustat_listing_years", "op": "gte", "value": 2}`. This isn't a plain
column lookup -- it's a derived/computed eligibility condition (needs each
firm's own listing-history length as of the formation date), so it can never
be resolved via the flat data-catalog alias mechanism `normalize_fields()`
uses.

Nothing at review time flags this as unsupported (unlike the D4 checks for
weighting/return_combination/construction_type/sort dimensions) -- it just
silently gets a "no evidence findings" pass through review, then blows up as
a 400 at step3's `build_config` with "concept_id 'compustat_listing_years'
has no physical column mapping". Worked around in the test session by
dropping this filter entirely (the paper's other two filters -- exchange
listing + ex-financials SIC range -- still ran for real against real data).

**Needed fix (not started):** either (a) add a D4-style engine-capability
check at review time that flags any `universe.filters[].concept_id` with no
possible physical-column resolution as `unsupported`/`blocked` (consistent
UX with gap #1), and/or (b) implement point-in-time Compustat-listing-
duration eligibility as a real, computable universe filter (would need
firm-level listing-history data plumbed into the engine, not just a single
row's column value).
