# TODO — deferred work

Status: tracking list, not yet scheduled. Add new items with date + context;
don't delete resolved items, mark them done instead.

## Compustat-derived universe-eligibility filters (e.g. "listed on Compustat >= 2 years")

**Real fix DONE (2026-08-13) for the common case: any universe filter
resolved to a REAL, already-registered physical column** (e.g.
`total_assets` -> `comp_funda.at`) is now genuinely supported, not just
`accepted_unapplied`-workaround-able. The generated script
(`script_generator.join_universe_filter_sources`, called from `main()`
before the engine runs) point-in-time joins any such column onto the
returns panel via `assemble_signal_master_table_from_sources` -- the SAME
mechanism `compute_signal`'s own input already used -- so `filter_universe`
(step 4) sees it as an ordinary panel column, with zero `BacktestExecutor`
changes. `registry._universe_filter_join_sources` builds the
`{source: [columns]}` config; `ResolvedMethodSpec.unsupported_universe_
filters()` now only flags a filter when its resolved column ISN'T even
registered in `catalog.DATA_CATALOG` for its source (genuinely un-loadable).
See `docs/decision-log.md` 2026-08-13 entry.

**Still deferred: the DERIVED-column case** -- e.g. the classic
Fama-French backfill-bias screen ("firm must have >= 2 years of Compustat
coverage before inclusion", `compustat_first_datadate`/
`compustat_listing_duration`). Unlike `total_assets`, this isn't a raw
physical column at all -- it's a groupby-min over `datadate` per `gvkey` --
so the join mechanism above doesn't help; a human must still mark it
`accepted_unapplied=True` + `unapplied_reason` (write path DONE, see below)
until the derived-column engineering below is built.

**Real fix, deferred (derived-column case only):**

1. `sources.py`: register a derived column on `comp_funda` -- for each
   `gvkey`, the earliest `datadate` across all its annual records
   (`first_datadate`, a groupby-min, not a raw per-row column) -- and expose
   it as a normal physical column/concept alias (e.g.
   `compustat_first_datadate`) so `build_implementation_resolution` can
   resolve it like any other concept. This IS the standard academic
   definition of "years on Compustat" (not an approximation of true IPO
   date) -- no new raw data file needed, `COMPUSTAT_FUNDAMENTALS_ANNUAL.csv`
   is sufficient. Once registered as a real physical column, the
   `total_assets`-style join mechanism above picks it up automatically --
   no further engine/script-generator work needed.
2. This still needs `docs/decision-log.md` recording once implemented,
   since it changes what "supported" means for this filter class (affects
   comparability with prior experiment runs that used `accepted_unapplied`).

Full discussion: this session's chat history (2026-08-13), also see
`docs/known-gaps-paper-first-v2.md` problem 3 and
`docs/resolve-diagnostics-gaps.md` (§ on `unsupported_universe_filters`/
`accepted_unapplied`).

## `FilterSpec.accepted_unapplied`/`unapplied_reason` has no write path

**DONE (2026-08-13).** `SessionDetailPage.tsx`'s resolve panel now has a
client-side control per `universe.filters[i]` (reason `Input` + "Mark
accepted_unapplied" button, next to the existing `derivation` editor) that
sets `accepted_unapplied=true`/`unapplied_reason=<text>` on `state.paper`
(same pattern as the derivation editor -- no new backend endpoint, `state.
paper` is resent wholesale on the next `/resolve` call) + an "Undo" button
to revert. This is also the concrete unblock for the Compustat-eligibility-
filter item above's interim plan (mark it `accepted_unapplied` today, real
engine support stays deferred).

~~Confirmed still true as of 2026-08-13 (`docs/resolve-diagnostics-gaps.md`
问题1 already flagged this): zero references in `backend/`/`frontend/` --
only the Pydantic fields exist. To actually use the plan-A workaround above
from the session UI, `SessionDetailPage.tsx`'s resolve panel needs a small
client-side control (mirroring the existing `derivation` JSON-textarea
pattern -- no new backend endpoint needed, since `state.paper` is resent
wholesale on every `/review`/`/resolve` call) to set
`universe.filters[i].accepted_unapplied = true` +
`unapplied_reason = <text>`. Not yet implemented.~~

