# Decision Log

Record of challenging or major decisions and the reasoning behind them.
The goal is to preserve enough context (problem, alternatives considered, why we
chose what we chose, empirical impact) to later cite and justify these choices
when writing the paper.

> **Historical audit notice:** entries are intentionally preserved as decisions
> made at the time. Older entries may mention files, hooks, classes, paths, or
> designs that have since been removed. They are not current implementation
> instructions. For current architecture and planned work, use
> [architecture.md](architecture.md), [roadmap.md](roadmap.md), and
> [multi-config-evidence-plan.md](multi-config-evidence-plan.md).

## How to use

- Add a new entry at the **top** of the log (most recent first).
- Copy the template below. Keep it concise but capture the *why*, not just the *what*.
- Link to relevant code, tests, MethodSpecs, or CHANGELOG entries where useful.
- Reserve this file for decisions worth defending in a paper: methodology,
  empirical trade-offs, architectural constraints, deviations from the reference
  (C&Z / original paper). Routine changes belong in `CHANGELOG.md`.

### Entry template

```markdown
## YYYY-MM-DD — <short decision title>

- **Context / problem:** What situation forced a decision? What was at stake?
- **Options considered:** The main alternatives, briefly.
- **Decision:** What we chose.
- **Rationale:** Why this option over the others. The core argument for the paper.
- **Empirical impact:** Effect on replication (numbers, gap, direction) if known.
- **Trade-offs / risks:** What we knowingly gave up or deferred.
- **References:** Files, tests, commits, papers, MethodSpec IDs.
```

---

<!-- Add new entries below this line, newest first. -->

## 2026-08-08 — Extract/Review are standalone pages; sessions visibly begin at Step 3

- **Context / problem:** The paper-first MethodSpec backend lifecycle is global and persists drafts/reviews/resolutions under `runs/method_specs`; session-owned endpoints for Step 1/2 were deleted. The React UI nevertheless left `Extractor` and `Review & Resolve` disabled in the sidebar, then rendered one combined extract/review/resolve panel twice inside session Step 1 and Step 2, with progress stored only in sessionStorage under a session id. This contradicted the backend ownership boundary, made refresh/tab close lose UI state, and sent new sessions to two steps they cannot own.
- **Decision:** Add real standalone `/extract` and `/review` routes backed by the persisted MethodSpec APIs. Extraction links to review by `factor_id`; review reloads persisted drafts/reviews and writes resolution artifacts. Session creation/list navigation now enters Step 3, and the session stepper hides Step 1/2. Legacy session Step 1/2 URLs redirect to the standalone pages.
- **Rationale:** UI ownership now matches artifact ownership: MethodSpec lifecycle is reusable across sessions, while a session owns the generated script and later empirical artifacts from Step 3 onward. Backend files remain the durable source of truth; browser state is no longer required to review a saved draft.
- **Empirical impact:** None. This changes routing and workflow presentation only; extractor, reviewer, resolver, and backtest logic are unchanged.
- **References:** `frontend/src/pages/ExtractorPage.tsx`, `frontend/src/pages/ReviewResolvePage.tsx`, `frontend/src/App.tsx`, `frontend/src/layout/AppLayout.tsx`, `frontend/src/pages/SessionsPage.tsx`, `frontend/src/components/StepStepper.tsx`, `CHANGELOG.md`.

## 2026-08-07 — Full deletion of v1 `MethodSpec` after completing the paper-first migration

- **Context / problem:** Over this session, every consumer of the flat v1
  `MethodSpec` (registry/MetaCoder/script_generator/step4/step5/step6/
  RepairLoop/backend routers/app.py/all golden-fixture e2e tests) had been
  migrated to dual-dispatch on the new paper-first schema
  (`PaperMethodSpec`/`MethodReview`/`ImplementationResolution`/
  `ResolvedMethodSpec`). The only remaining question was whether to finally
  delete `src/infra/models/method_spec.py` and the ~20 files whose entire
  purpose was v1-only (`SemanticExtractor`, `ReviewGate`, `apply_decisions`,
  `field_contract.py`, v1 CLI scripts, extraction-accuracy evaluation), or
  keep both schemas indefinitely.
- **Options considered:** (1) Full deletion now. (2) First validate the new
  paper-first workflow against a REAL paper with a real LLM call end-to-end
  (extract -> review -> resolve -> codegen -> backtest), since it had only
  been proven on synthetic/structural tests, then delete. (3) Keep v1
  permanently as a deliberate two-schema design.
- **Decision:** (1) — full deletion now, on explicit user instruction after
  being shown the risk (option 2 was recommended but declined).
- **Rationale:** The user made the call to prioritize a clean, single-schema
  codebase over further validation before deletion. All dual-dispatch call
  sites were already covered by unit/integration tests (structural
  correctness), even though no real paper had been run through the new
  extractor with a live LLM yet.
- **Empirical impact:** None on any existing golden number -- every
  `*_resolved_method_spec` test (asset growth, accruals, real-WRDS-sample
  smoke test) reproduces byte-identical config/metrics to the retired v1
  fixtures it replaced, verified field-by-field via `registry.build_config`
  before conversion.
- **Trade-offs / risks:** (a) The paper-first extractor
  (`PaperExtractor`/`review_paper_method_spec`/
  `build_implementation_resolution`) has never been exercised against a real
  paper with a real LLM call -- if its prompt/schema has a gap, it will only
  surface the first time someone actually uses it, with no v1 fallback left.
  (b) `backend/routers/sessions.py` lost its step1(extract)/step2(review)
  endpoints entirely (no paper-first equivalent was wired into the
  session-based flow this session) -- sessions now start from step3 (script
  build); there is no session-based extract/review UI path anymore, only the
  standalone `paper_methodspecs.py` API + app.py's "Paper-First Workflow"
  page. (c) **The React frontend was not touched or verified** -- it still
  calls the now-deleted `/api/methodspecs/*`, `/api/evaluations/*`, and
  session step1/2 endpoints (`frontend/src/lib/sessionApi.ts`, `steps.ts`,
  `pages/BacktestExperimentsPage.tsx`, `pages/PipelineE2EPage.tsx`,
  `pages/SchemaReferencePage.tsx`, `pages/SessionDetailPage.tsx`) and will
  404 on those calls until updated.
- **References:** `src/infra/models/paper_method_spec.py`,
  `backend/routers/paper_methodspecs.py`, `app.py`'s "Paper-First Workflow"
  page, CHANGELOG.md 2026-08-07 entry, `/memories/repo/
  methodspec_schema_notes.md` (session-long migration log).

## 2026-08-07 — Re-added double sort to the engine (partial reversal of the 2026-07-24 vanilla-path simplification)

- **Context / problem:** The MethodSpec v2 redesign (see
  `docs/methodspec-v2-plan.md` D4) decided the paper-first schema should be
  able to represent independent/sequential double sorts, since Hirshleifer,
  Hsu & Li (2012)'s innovation-efficiency factors need a size x
  patents/citations independent double sort and are in the project's test
  corpus. This directly reverses part of the 2026-07-24 decision ("Strip
  non-standard engine capabilities to one vanilla single-dim portfolio-sort
  path") that deliberately removed multi-dimensional sorts, along with
  overlapping-cohort holding, the discrete/categorical sort form, the
  Fama-MacBeth estimator, and microcap exclusion.
- **Options considered:** (a) leave the schema able to *describe* double
  sorts but keep them permanently unsupported/blocked at review, treating
  Hirshleifer as a single-sort approximation forever; (b) restore all five
  capabilities removed on 2026-07-24 in one pass, matching the original
  scope of that removal; (c) re-add only double sort, since it is the only
  one of the five with a concrete driving paper right now, per the
  2026-07-24 entry's own stated re-introduction policy ("re-introduce
  capabilities later, incrementally, only as a specific paper's replication
  actually needs them").
- **Decision:** (c). Restored, adapted (not copy-pasted) from the
  2026-07-24-removed implementation: `BacktestExecutor.
  compute_breakpoints_multi`/`assign_portfolios_multi`/
  `compute_portfolio_returns_multi`/`combine_portfolio_returns_multi`
  (`src/infra/backtest_engine/__init__.py`), dispatched from
  `form_portfolios`/`compute_portfolio_returns`/`combine_portfolio_returns`
  only when `config["sort_dims"]` has 2 entries -- the single-dim path's
  code and behavior are completely untouched otherwise. Fama-MacBeth,
  overlapping-cohort holding, the discrete sort form, and microcap exclusion
  remain removed; not part of this decision.
- **Rationale:** The adaptation is not a straight restoration of the deleted
  code: the original multi-dim implementation grouped by `yyyymm` and
  computed breakpoints directly from the post-return-join panel, which is
  exactly the future-return-availability leak the single-dim path's
  2026-07-28 formation-locked-breakpoints fix closed (the 2026-07-24 entry's
  own trade-offs note flagged this gap explicitly: "should double sorts
  return in the future, they would need the same fix applied to their own
  breakpoint/assignment functions"). The re-added implementation instead
  derives per-dimension breakpoints from `self.formation` (the pre-return-
  join formation cross-section) and applies them to `self.merged` by
  `cohort`, matching the single-dim path's convention, and reuses the
  single-dim path's lagged-`me` value-weighting (`_attach_lagged_me`)
  instead of the original's same-month `me`.
- **Empirical impact:** None on any existing replication -- the multi-dim
  path only activates when a MethodSpec resolves `sort_dims` with 2+
  entries, which no currently-approved MethodSpec does yet (Hirshleifer's
  MethodSpecs are still in `data/test_method_specs_human_labeled/`,
  unreviewed against the v2 schema). New `tests/test_double_sort_engine.py`
  (7 tests) verifies the 2x2 independent-sort mechanics by hand (same
  economics as the deleted `test_multi_sort.py` fixture) and that the
  single-dim path is unaffected when `sort_dims` is absent/empty. Full
  suite: 594 passed, 26 skipped (was 587 before this entry -- the 7 more are
  exactly the new double-sort tests, zero regressions).
- **Trade-offs / risks:** Only independent or dimension-0-conditional
  (sequential) double sorts are supported, capped at 2 dimensions (see
  `MAX_SUPPORTED_SORT_DIMENSIONS` in `paper_method_spec.py`, currently 3 in
  the schema's capability constant but only 2 actually executable by the
  engine as of this entry -- a 3-dimension sort will pass
  `ResolvedMethodSpec.is_ready`'s dimension-count check but is NOT yet
  executable; this mismatch should be tightened or the 3rd dimension
  implemented before any real 3-way-sort MethodSpec reaches Step3). Not yet
  wired into `registry.build_config`/`MetaCoder`/`step6_dual_track_controller`
  -- those still only know the single-dim `MethodSpec` v1 shape; deriving
  `config["sort_dims"]` from a `ResolvedMethodSpec`'s `portfolio.sorts[]` is
  separate, not-yet-done work (see `docs/methodspec-v2-plan.md` migration
  Phase D).
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (`compute_breakpoints_multi`, `assign_portfolios_multi`,
  `compute_portfolio_returns_multi`, `combine_portfolio_returns_multi`),
  [tests/test_double_sort_engine.py](../tests/test_double_sort_engine.py),
  [docs/methodspec-v2-plan.md](methodspec-v2-plan.md) (D4), the 2026-07-24
  entry below ("Strip non-standard engine capabilities...").



## 2026-08-04 (fifth) — Systematically assessed C&Z bridge feasibility across the 10 test papers; only 1 of 11 factors qualifies as safely portable

- **Context / problem:** Asked whether the C&Z bridge mechanism could be
  confirmed to generalize across the project's 10 test papers
  (`data/test_papers/`, 12 human-labeled MethodSpecs). Rather than guess
  from paper titles, dispatched a thorough read of each factor's ACTUAL C&Z
  predictor source file (where a plausible match existed) and classified
  each as SIMPLE (single-source, clean formula, lag a clean multiple of 12
  months -- portable the same way `asset_growth_from_panel`/
  `accruals_from_panel` were) / COMPLEX (multi-source merge, rolling
  regressions, external data) / NO_MATCH (no corresponding C&Z file at
  all).
- **Result:** Only 1 of 11 non-AssetGrowth factors qualified as SIMPLE:
  `Valta_StrategicDefault_ConvertibleDebt` (`ConvDebt.py`). Verified this
  myself by reading the source directly (not just trusting the assessment)
  before implementing -- confirmed single `comp_funda` source
  (`dc`/`cshrc`), a binary indicator with NO lag at all (the simplest of
  the three ported factors). The other 10 need substantially more
  infrastructure: daily-return rolling correlations (Betting Against Beta),
  36-month rolling FF3 regressions (Residual Momentum), recursive SG&A
  depreciation with FF17 industry adjustment (Organization Capital),
  external patent/citation panels this repo doesn't have (Innovative
  Efficiency, both variants), or OptionMetrics implied volatility data
  (the three options-based factors) -- plus 2 factors (Valta's Secured
  Debt and Shareholders variants) with no corresponding C&Z predictor file
  in this repo's copy of their source at all.
- **Decision:** Registered `ConvDebt` as the third `CZ_BRIDGE_SIGNALS`
  entry. Explicitly did NOT attempt to port any of the 10
  COMPLEX/NO_MATCH factors -- doing so without the missing infrastructure
  (daily CRSP rolling-window computation, external patent/citation/options
  data ingestion) would mean either an incomplete/wrong port or silently
  reinventing empirical choices the paper's/C&Z's actual implementation
  makes, both of which this project's hard constraints forbid.
- **Empirical impact:** None -- `ConvDebt` has no existing golden-number
  fixture in this repo (unlike AssetGrowth/Accruals) to verify against, so
  its tests are direct unit tests on hand-built panels only (no real
  synthetic-data integration test this time). Full suite: 386 passed, 26
  skipped, zero regressions.
- **Trade-offs / risks:** The bridge registry now covers 3 of ~200 C&Z
  predictors and, within THIS project's specific 10 test papers, exactly 1
  of 12. Genuinely expanding coverage further requires either (a) reading
  more predictor scripts outside the test-paper set looking for more SIMPLE
  candidates, or (b) building real infrastructure for one of the COMPLEX
  categories (e.g. a daily-CRSP rolling-window helper would unlock Betting
  Against Beta and likely several similar momentum/beta factors at once) --
  neither attempted here.
- **References:** `src/infra/reference/cz_bridge.py` (`convdebt_from_panel`,
  `CZ_BRIDGE_SIGNALS`); `tests/test_cz_bridge.py`;
  `data/CZ code/Signals/pyCode/Predictors/ConvDebt.py`;
  `data/test_method_specs_human_labeled/*.methodspec.json`;
  `data/test_papers/paper_spec_mapping.json`.

## 2026-08-04 (fourth) — Merged `ExperimentPlan`/`ExperimentMatrix` into one execution path; implemented the long-dormant `factorial_switches`

- **Context / problem:** `DualTrackController` had two independent ways to
  declare a batch of tracks -- the original hardcoded-in-Python
  `ExperimentPlan` (`run_experiment`) and the newer declarative yaml
  `ExperimentMatrix` (`run_from_matrix`, Phase A2). They duplicated the
  track-building/`_finalize_batch` glue, and only the yaml path derived
  `family`/`identification_level` -- a plan-based `ablation_*` track had no
  such classification at all. Separately, `ExperimentPlan.factorial_switches`
  had been declared since early in the project (see docs/multi-config-
  evidence-plan.md's explicit warning against exactly this: "implement the
  declared-but-never-executed `factorial_switches` in the same pass, don't
  leave two half-finished interfaces") but nothing ever read it.
- **Decision:** Extracted `experiment_spec.build_experiment_spec` as the ONE
  shared per-experiment resolution (resolve config, diff against baseline,
  derive `family`/`identification_level`) that both `load_experiment_matrix`
  (yaml) and a new `DualTrackController._plan_to_matrix` (Python
  `ExperimentPlan`) call. `run_experiment` is now a thin adapter:
  `_plan_to_matrix(plan, spec)` then `run_from_matrix(...)`. Implemented
  `factorial_switches` as `_factorial_track_specs`: a real full-factorial
  cartesian product of {baseline value, HXZ value} per given switch,
  excluding the redundant all-baseline corner.
- **A real bug caught while writing tests, not by luck:** the cartesian
  product degenerates when a switch's baseline value happens to already
  equal its own HXZ-standardized value (e.g. a paper whose own weighting is
  already "vw", same as HXZ's default) -- `itertools.product` then yields
  the SAME resulting override dict from more than one input position,
  which would have produced two `RunRecord`s with an IDENTICAL track name:
  a silent on-disk collision (second overwrites first) and a lost entry in
  `comparison.json`'s `tracks` dict (a plain `{name: ...}` mapping loses
  duplicates with no error). Fixed by de-duplicating by resulting track
  name inside `_factorial_track_specs`. Caught because a test using a
  fixture whose weighting happened to match HXZ's default failed with a
  suspicious "2 == 3" instead of "4 == 3" -- worth remembering: a
  cartesian-product expansion over "baseline vs standard" values is NOT
  safe to assume produces `2^n` distinct entries without checking for
  option-level duplicates first.
- **Empirical impact:** None on real runs. Full suite: 372 passed, 26
  skipped, zero regressions; existing plan-based tests (`tests/
  test_dual_track_controller.py`, `tests/test_batch_invalidation.py`)
  needed no changes -- their outward behavior is identical, since
  `_plan_to_matrix` reproduces the original track set exactly (baseline
  optional via `run_baseline`, `standardized_hxz`, `ablation_*`).
- **Trade-offs / risks:** `_plan_to_matrix` calls `build_config` once for
  the plan's baseline and `build_experiment_spec` calls it again per
  experiment (and `_finalize_batch`'s `tracks_summary` recomputes it once
  more per successful track for `comparison.json`) -- a real, minor,
  accepted redundancy (each call is cheap in-process arithmetic, not I/O);
  not worth a deeper refactor for this pass.
- **References:** `src/steps/step6_dual_track_controller/__init__.py`
  (`run_experiment`, `_plan_to_matrix`, `_factorial_track_specs`,
  `run_from_matrix`'s new `run_baseline` param);
  `src/steps/step6_dual_track_controller/experiment_spec.py`
  (`build_experiment_spec`); `tests/test_experiment_plan_matrix_merge.py`;
  `docs/multi-config-evidence-plan.md` Phase A2.

## 2026-08-04 (second) — A real C&Z bridge is feasible for AssetGrowth without adding `polars`; ported the formula instead of subprocess-executing their script

- **Context / problem:** The 2026-08-03 session flatly stated no C&Z
  firm-level signal bridge existed and that building one would require
  "running/porting their pipeline." Investigated `data/CZ code/Signals/
  pyCode/Predictors/AssetGrowth.py` directly and found its actual input
  requirement is trivial: `[gvkey, permno, time_avail_m, at]` -- exactly the
  shape our own `assemble_signal_master_table_from_sources({"comp_funda":
  ["at"]})` already produces from real WRDS data. So a real bridge for THIS
  factor was much closer than assumed.
- **Options considered:** (a) subprocess-execute their actual `.py` script
  against a `m_aCompustat.parquet` we assemble ourselves; (b) port their
  documented formula as our own function operating on our own panel shape;
  (c) leave it undone as previously stated.
- **Decision:** (b). `save_standardized.py` (which their script imports)
  itself imports `polars`, which the project doesn't depend on (see session
  memory note on why bare `pytest` collecting `data/CZ code/**/test_*.py`
  files fails for exactly this reason) -- adding a new runtime dependency
  just to execute one predictor script wasn't a call to make silently.
  Their formula is short, fully stated, and unambiguous, so porting it is
  both cheaper and doesn't require a new dependency.
- **A correctness catch worth recording:** the FIRST draft of the port
  copied their literal `.shift(12)` unchanged. That would have been WRONG:
  their `m_aCompustat.parquet` is a MONTHLY, forward-filled panel (one row
  per firm-month), so `.shift(12)` means "12 months ago"; our own
  `assemble_signal_master_table_from_sources` produces one row per
  firm-FISCAL-YEAR-OBSERVATION (annual frequency, not forward-filled --
  `_load_generic_signal_frame`). Shifting 12 ROWS on an annual panel would
  look back 12 YEARS, not 1. Fixed to shift by 1 row, which is the correct
  economic equivalent ("prior fiscal year's assets") on our panel's shape.
  Caught by tracing `_load_generic_signal_frame`'s output frequency before
  trusting the port, not by a failing test -- the synthetic-data
  integration test (added after the fix) would NOT have caught the
  original bug on its own without deliberately checking output row counts.
- **Empirical impact:** `tests/test_cz_bridge.py::
  TestRealSyntheticDataIntegration` recovers the exact per-firm growth
  rates from the SAME synthetic Compustat fixture the MVP e2e golden-number
  test uses, through the real (not mocked) `assemble_signal_master_table_
  from_sources` call. This is a real, verified signal series, not a
  placeholder.
- **Trade-offs / risks:** Still bounded to ONE factor (AssetGrowth); most
  C&Z predictors are more complex (multi-source joins, discretionary
  edge-case handling, PIT nuances) and are NOT covered by this pattern
  without individually verifying each one's own script the same careful
  way. NOT yet wired into an actual executable `DualTrackController` bridge
  track -- `BacktestExecutor.run_with_config()` already accepts a
  pre-computed `signal` DataFrame directly (bypassing `compute_signal()`
  entirely), so the remaining work is a NEW script-generation mode (or an
  in-process engine entry point) that swaps in `compute_cz_bridge_signal()`'s
  output instead of the agent's plugin, run under the SAME resolved config
  as the baseline track -- not a data problem anymore, an orchestration one.
- **References:** `src/infra/reference/cz_bridge.py`; `tests/
  test_cz_bridge.py`; `data/CZ code/Signals/pyCode/Predictors/
  AssetGrowth.py`; `src/infra/data_layer/sources.py`
  (`_load_generic_signal_frame`, `assemble_signal_master_table_from_sources`);
  `docs/multi-config-evidence-plan.md` Phase B/C&D.

## 2026-08-04 — Phase 0.6 upgraded from detection-only to a real auto-converging freeze; found the mechanism makes `batch_invalidated=True` nearly unreachable via the public API

- **Context / problem:** The previous Phase 0.6 pass (2026-08-03, ninth
  entry) only DETECTED when a track-local repair broke a batch's "every
  track ran identical code" premise -- it never corrected it, leaving a
  human to notice `batch_invalidated=True` and manually re-run everything.
  Asked to close that gap: auto-freeze-and-rerun instead of detect-only.
- **Decision:** `_run_tracks_with_freeze` now runs the batch once with
  repair allowed; if that pass produced any successful track whose code
  diverged from the original plugin, it picks the FIRST diverging track's
  repaired plugin as the new frozen candidate and re-runs the ENTIRE batch
  (every track, including ones that already succeeded) against that one
  plugin with repair explicitly DISABLED (`_NoRepairMetaCoder`, whose
  `llm_client=None` is exactly the attribute `RepairLoop` checks to decide
  whether it may attempt a repair at all). Bounded to `max_refreeze_attempts`
  re-runs (default 1). A single-track batch skips this entirely (no other
  track to be consistent with).
- **Finding worth recording:** because the frozen re-run pass can never
  itself change a plugin's code (no repair capability), EVERY successful
  track in that pass trivially uses the exact `current_plugin` it was given
  -- there is no code path by which two successful tracks in a frozen pass
  can disagree. A track that can't run under the shared re-frozen plugin
  doesn't "diverge", it FAILS (`status="failed"`) and drops out of the
  comparison set entirely. Consequence: with the default of one re-freeze
  attempt, `batch_invalidated=True` cannot occur from `run_experiment`/
  `run_from_matrix`'s normal call path -- the batch either converges among
  its survivors, or the non-convergible track is marked failed (itself
  visible and honest, just not via the `batch_invalidated` flag). The flag
  now only fires via the explicit `max_refreeze_attempts=0` escape hatch
  (kept as a real, tested code path -- `TestZeroRefreezeAttemptsIsDetectionOnly`
  -- for a caller that wants the OLD detect-only behavior), which
  `run_experiment`/`run_from_matrix` never pass.
- **Rationale:** This is a strictly better outcome than the old detect-and-
  flag behavior, not a regression: a track that structurally cannot run
  under the shared frozen code shouldn't produce a "successful but
  incomparable" result at all -- marking it failed is the economically
  correct signal (this track's config combination isn't achievable with the
  batch's one frozen implementation), and every track that DOES succeed is
  now provably running identical code, satisfying the batch's actual
  purpose (valid cross-track config attribution) rather than merely
  reporting that it was violated.
- **Empirical impact:** None on real runs (no real WRDS run has needed a
  track-local repair yet). Full suite: 344 passed, 26 skipped, zero
  regressions; two existing tests in `tests/test_batch_invalidation.py`
  were rewritten to assert the new (correct) converging behavior instead of
  the old permanently-invalidated one, plus a new direct
  `max_refreeze_attempts=0` test for the still-supported detect-only mode.
- **Trade-offs / risks:** If TWO tracks each need a genuinely different,
  mutually incompatible fix, the current design arbitrarily freezes on
  whichever diverging track appears FIRST in `track_specs` order and lets
  the other fail -- it does not try every diverging candidate looking for
  one that satisfies the most tracks. Considered acceptable for now (a
  single technical repair fixing multiple independent tracks is the common
  case; true "irreconcilable" formula bugs should surface as a real,
  visible per-track failure rather than being silently arbitrated away).
- **References:** `src/steps/step6_dual_track_controller/__init__.py`
  (`_run_tracks_with_freeze`, `_NoRepairMetaCoder`, `_run_track`);
  `tests/test_batch_invalidation.py`; `tests/test_dual_track_controller.py`
  (`TestRepairLoop::test_execute_failure_repairs_then_succeeds`, updated for
  the single-track guard); `docs/multi-config-evidence-plan.md` Phase 0.6.

## 2026-08-03 (seventh) — Diagnosis claims: citation-shape validation was not claim-entailment validation

- **Context / problem:** An external review of `prompts/analysis/
  replication_diagnosis.md` (the sixth entry above) identified that the
  validator added there only checked that a claim cited a real, whitelisted,
  correctly-typed key — never that the claim's *text* was actually consistent
  with that key's *value*. Concretely, a claim `{"claim_type":
  "sign_agreement", "text": "The signs are opposite.", "evidence_keys":
  ["...sign_agrees"]}` passed validation even when `sign_agrees` was `true`,
  because nothing compared the prose to the cited value. The same review also
  flagged: the OAT (`gap_decomposition.contributions`) evidence was treated as
  sufficient for causal wording ("drives", "explains") despite being
  one-at-a-time, not additive, and order/baseline-dependent; `confidence` was
  an unconstrained LLM self-rating with no defined meaning, contradicting the
  project's "conclusions must be deterministic" constraint; `stage` was
  LLM-guessed rather than derived from the config key it actually concerned;
  `original_method` was described in the prompt as "paper-faithful" when it
  may embed human-resolved ambiguities the paper never specified; and
  `config_divergence` claims could cite only one side (`track_value`) of a
  changed key without the `baseline_value` needed to show the actual
  divergence.
- **Options considered:**
  1. Patch only the prompt wording (softer causal language, drop the "six to
     ten claims" phrasing). Cheap, but the review's own point was that prompt
     wording is not enforcement — an LLM can still emit an unfaithful claim
     and nothing in code would catch it.
  2. Structure the claim's assertion as an enum (`relation`, e.g.
     `agrees`/`disagrees`, `larger`/`smaller`/`similar`,
     `significant`/`insignificant`) checked deterministically against the
     value of the cited key, plus a code-level ban on causal vocabulary, plus
     deriving `stage`/`identification_level`/`evidence_strength` from the
     evidence rather than accepting them from the LLM.
- **Decision:** Implemented option 2. `DiagnosisClaim`
  (`src/infra/models/diagnosis.py`) gained `relation` (checked against the
  claim type: `CLAIM_RELATIONS`), `subject_track` (must match the track named
  in the claim's own cited keys), `identification_level`
  (`controlled`/`harmonized`/`observational`/`unidentified`) and
  `evidence_strength` (a fixed mapping from `identification_level`, not an
  LLM opinion); `confidence` was removed entirely. `src/steps/
  step8_diagnosis/__init__.py`'s validator now: (a) compares the asserted
  `relation` against the actual cited value for `sign_agreement`
  (`sign_agrees`), `significance` (`track_significant`), and `magnitude_gap`
  (`abs_spread_ratio` vs. `CLOSE_REPLICATION_RATIO_BAND`); (b) requires
  `config_divergence` to cite both `.baseline_value` and `.track_value` of
  the same key; (c) rejects a `subject_track` that doesn't match the track in
  the claim's own citations; (d) rejects causal vocabulary
  (`CAUSAL_TERM_RE`: drives/explains/caused by/due to/...) in claim text
  outright, since nothing in this pipeline produces a controlled/factorial
  design; (e) derives `stage` from the cited `config_diff`/
  `gap_decomposition` key's own stage rather than trusting the model; (f)
  narrows `evidence_limitation` to citing an availability/reason key or a
  null value, rather than any `derived.tracks.*`/`gap_decomposition.*` key.
  `src/steps/step7_replication_diff/bundle.py`'s `config_diff` and
  `gap_decomposition` sections now carry their own `identification_level`
  (`observational` and `harmonized`/`unidentified` respectively) plus an
  explicit `interaction_caveat` string on the OAT decomposition. The prompt
  was rewritten to describe `original_method` as "the approved (reviewed)
  interpretation of the paper" rather than "paper-faithful," and the "six to
  ten claims" language was replaced with "at most ten, no minimum implied."
  `render.py` now generates the claim's displayed sentence deterministically
  from `(claim_type, relation, subject_track)` — the LLM's own `text` is
  shown only as a secondary, explicitly unauthoritative aside. Schema bumped
  to v2 (was already v1→v2 in the prior entry's `comparison.json`; this is
  `ReplicationDiagnosisReport.schema_version` specifically).
- **Rationale:** The review's core point stands: a citation-whitelist check
  proves a key exists and is well-typed, never that the sentence built around
  it is true. Structuring the assertion as an enum makes the sentence itself
  a deterministic function of validated inputs, so "real key, wrong sentence"
  becomes structurally impossible rather than merely discouraged in a prompt.
  Banning causal vocabulary in code (not just prompt instruction) matches the
  actual epistemic status of the evidence this pipeline can produce: a config
  diff is observational, and even a full OAT decomposition is one-at-a-time
  and non-additive, so no claim type reachable today can honestly claim
  `identification_level == "controlled"` — that value exists in the schema so
  a future factorial/Shapley-decomposition addition has somewhere to report
  itself, but every currently-emittable claim is `harmonized` at best.
- **Empirical impact:** None on any backtest number. `stage`/
  `identification_level`/`evidence_strength` change what a diagnosis *report*
  displays for claims about the same underlying evidence, not any metric.
- **Trade-offs / risks:** The remaining gap the review raised but this pass
  did not close: `original_method`'s MethodSpec may contain human-resolved
  ambiguities that are invisible to `config_diff` (which only diffs
  *resolved* configs, not which fields were paper-stated vs. reviewer-filled).
  Making that visible would require surfacing MethodSpec resolution
  provenance as its own evidence-bundle section — deferred, not yet scoped in
  `docs/multi-config-evidence-plan.md`.
- **References:** `src/infra/models/diagnosis.py`,
  `src/steps/step8_diagnosis/__init__.py`, `src/steps/step8_diagnosis/
  render.py`, `src/steps/step7_replication_diff/bundle.py`, `prompts/
  analysis/replication_diagnosis.md`, `tests/test_replication_diagnosis.py`,
  CHANGELOG.md.

## 2026-08-03 (sixth) — LLM replication-diagnosis layer: evidence-key citation over free-text narrative

- **Context / problem:** After `comparison.json` gained per-track config +
  metrics + the paper's own reported results, the natural next step was to
  let an LLM turn those numbers into a readable diagnosis. The obvious naive
  approach — hand the whole file to an LLM and ask for a markdown summary —
  would let the model restate, round, or silently miscompute any of those
  numbers (a spread delta, a t-stat gap, a significance call), and would let
  it invent a cause for a gap that was never actually measured. That directly
  violates the project's hard constraint (AGENTS.md, `docs/
  replication-diagnosis-design.md` §1.1): "every core numerical conclusion
  must be reproducible with the LLM switched off," and the LLM must never
  produce a number or threshold that enters a conclusion.
- **Options considered:**
  1. Free-text narrative: give the LLM `comparison.json`, ask for prose. Cheap
     to build, but auditable-only by re-reading the whole prose against the
     source numbers by hand, and nothing stops a hallucinated figure or an
     unfounded causal claim from reading as authoritative.
  2. Full Phase E discipline (as scoped in `docs/multi-config-evidence-plan.md`
     since before this entry, just not yet implemented): a deterministic
     evidence bundle with a flat citable-key whitelist; the LLM outputs only
     structured claims (`claim_type` + prose + cited keys), never numbers; a
     validator enforces per-claim-type evidence requirements and rejects any
     digit in the prose or any unlisted key; a deterministic renderer
     re-inserts every number from the bundle.
- **Decision:** Implemented option 2 in full, not a lighter version of it.
  Added `src/steps/step7_replication_diff/bundle.py`
  (`build_evidence_bundle`/`build_track_vs_paper`/`build_config_diff`/
  `build_gap_decomposition`/`flatten` → `evidence_keys`),
  `src/infra/models/diagnosis.py` (`DiagnosisClaim`/
  `ReplicationDiagnosisReport`, `CLAIM_EVIDENCE_REQUIREMENTS`/
  `CLAIM_EVIDENCE_SUBSTRINGS`), `src/steps/step8_diagnosis/`
  (`ReplicationDiagnoser` + `validate_claims` + `render.py`), and
  `prompts/analysis/replication_diagnosis.md`. `comparison.json` bumped to
  schema v2 to carry the bundle. Wired as strictly opt-in
  (`Pipeline(run_diagnosis=False)` default, `DualTrackController(diagnoser=
  None)` default) plus a standalone `scripts/analyze_comparison.py`.
- **Rationale:** The project's whole premise is that empirical conclusions
  must be auditable and reproducible without the LLM. A narrative layer that
  can write its own numbers or invent causation undermines that premise at
  the very last step of the pipeline, right where a reader is most likely to
  just trust the prose. Citation-only claims plus a validator plus a
  deterministic renderer make the failure mode "claim gets rejected and shows
  up in `rejected_claims` for a human to see" instead of "wrong number ships
  silently in a polished-looking report." The one-time cost (an evidence-key
  whitelist, a per-claim-type requirements table, ~150 extra lines) is small
  next to what it buys for the paper's reproducibility argument.
- **Empirical impact:** None on any backtest number — this layer only
  explains numbers that already exist. Verified on the real AssetGrowth
  (Cooper, Gulen & Schill 2008) bundle via codex: correctly reported the
  standardized track's spread-sign mismatch against the paper, both tracks'
  loss of statistical significance (|t| < 1.96), attributed the
  standardized-vs-original divergence to `breakpoint_source`/
  `rebalance_frequency`/`holding_period_months`/`universe`, and — because no
  `ablation_*` tracks had been run — correctly reported the OAT gap
  decomposition as unavailable rather than fabricating an attribution. 9/9
  claims passed validation on that run.
- **Trade-offs / risks:** The evidence-key whitelist is the full bundle
  flattened, which grows with the number of tracks/ablations; if that ever
  gets too large for a single LLM call, the fix is to shard by pipeline stage
  rather than relaxing the whitelist. The significance threshold (|t|≥1.96)
  and the "close replication" ratio band are fixed constants chosen for
  reasonableness, not fit to any dataset — worth re-examining if the project
  starts reporting Bonferroni-corrected or one-sided tests. Sequence-level
  evidence (return-series correlation, drawdown comparison) is deliberately
  out of scope for this bundle; it would need each track's `<track>.csv`, not
  just `comparison.json`, and is left for a later Phase C addition.
- **References:** `src/steps/step7_replication_diff/bundle.py`,
  `src/steps/step8_diagnosis/__init__.py`, `src/steps/step8_diagnosis/
  render.py`, `src/infra/models/diagnosis.py`, `prompts/analysis/
  replication_diagnosis.md`, `scripts/analyze_comparison.py`,
  `tests/test_replication_diagnosis.py`, `docs/multi-config-evidence-plan.md`
  §Phase E, CHANGELOG.md.

## 2026-08-03 (fourth) — Generalize annual accounting factors with calendar-lag/as-of signal alignment, not report-date timing by default

- **Context / problem:** The first real full-WRDS `AssetGrowth` run reached
  `BacktestExecutor.run_with_config()` and failed the annual formation-month
  validation: the MethodSpec declared June formation, but the raw signal's
  `yyyymm` cohorts appeared in all calendar months because real Compustat has
  many fiscal-year-end months. Data availability (`datadate + accounting_lag`)
  and portfolio formation calendar (e.g. every June) were coupled: the engine
  treated each signal row's availability month as the portfolio cohort. The
  user asked whether using actual report/release dates would be more general,
  and how to avoid breaking non-accounting factors.
- **Options considered:**
  1. **Report-date / filing-date timing** (Compustat RDQ, EDGAR filing dates,
     PIT data). This is the most precise for announcement-sensitive papers
     such as PEAD, but it is not the mainstream construction for classic
     annual accounting factors, has weak historical coverage for early
     samples, requires new PIT data sources, and would intentionally deviate
     from papers/C&Z implementations that use calendar lags.
  2. **C&Z-style data-layer monthly forward-fill**. `data/CZ code/Signals/
     pyCode/DataDownloads/CompustatAnnual.py` does `time_avail_m = datadate +
     6 months`, expands each annual record 12 times, and then predictors such
     as `AssetGrowth.py` use `.shift(12)`. This matches C&Z's intermediate
     representation, but changing our shared data loader this way would alter
     the shape of every Compustat-backed signal input, require prompt/plugin
     convention changes (`shift(1)` annual logic would become `shift(12)`),
     and force broad golden-number revalidation.
  3. **Engine-level calendar-lag/as-of alignment**. Keep the data layer as
     "one row when a signal becomes available", but before holding-period
     expansion, sample each stock's latest already-available, non-stale signal
     as of the reviewed rebalance grid (e.g. every June). This is equivalent
     to C&Z's forward-fill for the formation-month sample, but leaves existing
     plugin/data-loader contracts mostly intact.
- **Decision:** Chose (3) for the current engine generalization. Added
  `BacktestExecutor._resample_annual_signal_asof`, invoked only for
  `rebalance_frequency="annual"` when `formation_month` was explicit. It is a
  no-op for monthly/quarterly strategies and for already-aligned annual
  signals (all cohorts already in the reviewed formation month), preserving
  existing code paths/golden tests. It samples the latest signal as of each
  `(permno, formation_month)` row in the returns panel, bounded by
  `signal_max_staleness_months` (default 11, i.e. C&Z's 12-month fill window
  offsets 0..11). Added `signal_max_staleness_months` to resolved config.
  Kept report-date timing as a future explicit `timing_basis="report_date"`
  capability, not a default.
- **Rationale:** This separates two concepts the old lifecycle conflated:
  data availability (`time_avail_m`, owned by the data layer and accounting
  lag policy) and portfolio formation schedule (owned by the backtest config).
  The chosen implementation has small blast radius: monthly price signals
  physically bypass the new code, existing December-FYE synthetic golden paths
  are no-ops, and the fragile point-in-time universe-filter/formation-attribute
  logic in `apply_signal_holding_period` remains untouched after receiving an
  already-aligned signal. At the same time it follows the mainstream
  Fama-French/C&Z calendar-lag convention rather than introducing actual
  report-date timing that most classic annual accounting papers did not use.
- **Empirical impact:** This unblocked the real `AssetGrowth` execution past
  the formation-month error. The full real WRDS run completed through metrics:
  mean monthly return 0.4199%, annualized return 5.04%, Newey-West t-stat 2.59,
  882 months, CAPM alpha 0.573% (t=3.13), FF3 alpha 0.288% (t=1.99), FF5 alpha
  0.170% (t=1.24). These are not yet a final replication claim: the run uses a
  manually resolved spec/config and still needs the planned evidence bundle and
  C&Z bridge before interpreting the gap.
- **Trade-offs / risks:** Engine-level as-of alignment is not identical to
  adopting C&Z's monthly forward-filled intermediate table everywhere. That is
  intentional for compatibility, but it means future bridge diagnostics should
  record this representation choice. `signal_max_staleness_months` is still a
  config default rather than a reviewed MethodSpec field; roadmap now tracks
  promoting `timing_basis` and max-staleness into the paper-first review
  contract. Actual report-date timing remains unsupported until a point-in-time
  announcement/filing-date source is registered.
- **References:** `src/infra/backtest_engine/__init__.py`
  (`_resample_annual_signal_asof`, `compute_factor_alphas` NaN/inf cleanup),
  `src/steps/step3_codegen/registry.py` (`signal_max_staleness_months`),
  `tests/test_calendar_rebalance.py`, `tests/test_round5_faithfulness_fixes.py`,
  `tests/test_factor_alphas.py`, `docs/roadmap.md`, C&Z
  `Signals/pyCode/DataDownloads/CompustatAnnual.py` and
  `Signals/pyCode/Predictors/AssetGrowth.py`.

## 2026-08-03 (third) — First real end-to-end run against full WRDS data (AssetGrowth) surfaced 4 codegen/data-layer bugs + 1 genuine methodology gap

- **Context / problem:** After the review-loop fix (see the entry below),
  continued the same `AssetGrowth` (Cooper, Gulen & Schill 2008) dry run
  through codegen, sandbox validation, and actual script execution against
  the real `data/local` WRDS CSV export — the first time in this project's
  history any run reached real script execution against the FULL real
  dataset (not a small `data/local/samples/` fixture or synthetic data).
  Four distinct crashes surfaced in sequence, each fixed and re-verified
  before the next appeared:
  1. `pick_signal_input_mode()` raised "Cannot determine the signal input
     source": `data.normalized_mapping` was empty. Traced to
     `DataDictionary.normalize_fields()` never being called anywhere in the
     live pipeline (`Pipeline.run_full_pipeline`, the CLI scripts) — only
     ever referenced in comments and 4 old hand-populated fixtures. Worse,
     `ReviewGate._check_source_mapping_resolved` (via
     `MethodSpec.unresolved_source_fields()`) treats an EMPTY mapping as
     "nothing unresolved" (its own docstring says so), so this sailed
     through review with no warning.
  2. After auto-populating the mapping, the generated plugin had
     `at_col = "{'source': 'comp_funda', 'column': 'at'}"` — MetaCoder had
     copied the literal Python repr of the richer mapping-value dict as a
     column name, because `MetaCoder._build_prompt()` interpolated the raw
     dict into an f-string without extracting `.column`.
  3. After that fix, the plugin instead crashed on `KeyError: 'exchcd'`
     inside `compute_signal` — MetaCoder had ALSO baked exchange/SIC
     universe filtering into the plugin (violating its own "no universe
     filters" hard rule), because `_build_prompt()`'s "Data Fields"/"Column
     Mapping" sections listed ALL of `spec.data.required_fields` (including
     universe-membership concepts), not just the formula's own inputs.
  4. After restricting the prompt to formula fields only, hit
     `KeyError: 'at'` in a *different* place — `assemble_signal_master_
     table_from_sources()` returned zero rows/columns entirely. Traced to a
     directory-convention mismatch: the snapshot's `storage_path` was
     registered as `data/local` (the raw-CSV directory itself), but
     `_load_link_tables()`/`_load_generic_signal_frame()` hardcode
     `d / "local" / <raw_file>` (expecting `d` = the PARENT of `local/`).
     Confirmed against `test_real_wrds_samples_e2e.py`'s own fixture (passes
     the parent, not the `local/` dir) as the actually-correct, tested
     convention. Fixed the snapshot registration to use the parent — which
     then exposed a SECOND instance of the same confusion already baked
     into the generated script itself: `main()`'s multi_source branch (and
     my own earlier same-day fix to `load_msf()`'s CIZ fallback) called
     `build_crsp_monthly_panel_ciz(SIGNAL_DATA_DIR)` directly, but that
     function wants the ACTUAL csv directory, not the parent-of-`local`
     `SIGNAL_DATA_DIR` convention every other call site uses.
  5. After fixing the directory convention, hit `ValueError: Cannot set a
     DataFrame with multiple columns to the single column
     total_assets_t_minus_2` — `signal_input_sources()` returned
     `{"comp_funda": ["at", "at"]}` (duplicate), because two paper concepts
     (`total_assets_t_minus_1`/`total_assets_t_minus_2`) legitimately share
     one physical column at different lags, and nothing deduplicated the
     column list before asking the loader to select it.
  6. After deduplicating, the ENGINE (not codegen) raised "Universe filter
     references field 'exchange_listing', which the loaded returns panel
     does not have" — the resolved spec's own `portfolio.universe_filters`
     used paper-concept field names (`exchange_listing`,
     `industry_classification`, and even signal-side concepts like
     `total_assets_t_minus_1`) instead of the physical CRSP columns
     (`exchcd`, `siccd`) `BacktestExecutor.apply_universe_filters` requires.
     This one is confirmed WORKING AS DESIGNED, not a bug: that function's
     own docstring explains column-availability can only be checked at
     runtime (different returns universes have different columns), so it
     fails loud there deliberately. Fixed by correcting the SPEC's field
     names directly (a content fix, not a code fix) and dropping two
     filters that were genuinely misplaced signal-computability
     preconditions already handled correctly inside `compute_signal()`
     itself, plus one (`compustat_listing_history_years`) the engine
     architecturally cannot express via the CRSP-panel filter DSL at all.
  7. After that, the signal computed successfully (285k observations,
     24.7k firms, 1951–2026) and reached `BacktestExecutor.
     run_with_config()`, which then raised (correctly) on
     `_validate_annual_formation_month`: cohort months spanned all of
     1–12, not just the declared `formation_month=6`. Root cause: a flat
     `signal.timing.accounting_lag` (6 months) only produces a uniform
     June formation for December-fiscal-year-end firms; real Compustat has
     firms with every fiscal year-end month, and `_load_generic_signal_
     frame` computes `time_avail_m` per-row from EACH firm's own fiscal
     year-end + the flat lag. This is a genuine, NOT-yet-fixed
     methodological gap (see below) — every prior golden-number test in
     this repo used synthetic/small-sample data that happened to have
     uniform December fiscal year-ends, so this was never exercised until
     this run.
- **Decision:** Fixed bugs 1–5 in code (all generalize to every future
  paper/factor, not just this one): `SemanticExtractor._populate_normalized_
  mapping` (auto-populate + new ReviewGate backstop block), `MetaCoder.
  _build_prompt` (restrict to formula fields, extract `.column`, forbid
  universe filtering in-plugin), `signal_input_sources()` (dedupe columns),
  `script_generator.py` (fix the `SIGNAL_DATA_DIR` directory convention in
  both `load_msf()`'s CIZ fallback and `main()`'s multi_source branch).
  Fixed #6 as spec content (this factor's own `universe_filters`), not code
  — the engine's runtime-only column check is an intentional design choice
  (documented in `apply_universe_filters`'s own docstring) that correctly
  caught a genuine extraction-quality issue; no code change was warranted.
  Left #7 (the fiscal-year-end/formation-month gap) UNFIXED and explicitly
  documented rather than attempting a same-session engine/schema redesign:
  properly supporting non-uniform fiscal year-ends needs either an explicit
  December-FYE universe restriction (a per-paper MethodSpec decision) or a
  genuinely per-firm variable accounting lag (a new engine capability, since
  the schema only has one flat `accounting_lag: int` today) — both are
  real, scoped follow-up work, not a quick fix.
- **Empirical impact:** None yet for AssetGrowth's actual replicated numbers
  (blocked on #7); the value here is entirely in the 5 generalizable pipeline
  fixes (bugs 1–5), each verified by re-running the exact same failing step
  and confirming the NEXT distinct error appeared (i.e. each fix genuinely
  unblocked forward progress, not just papered over the symptom). Full test
  suite re-run after every single fix: 209 passed, 26 skipped throughout,
  zero regressions.
- **Trade-offs / risks:** This was the first time ANY of this project's
  automated steps (extraction, review, codegen, sandbox validation) were
  exercised against the full real dataset end-to-end rather than curated
  fixtures/small samples/synthetic data — expect more gaps of this exact
  shape (works on golden-number fixtures, breaks on real heterogeneous data)
  to surface the next time a NEW paper is run through fully, especially for
  "multi_source" mode (never exercised at all yet) and any signal touching
  fiscal-year-end timing.
- **References:** `src/steps/step1_extractor/__init__.py`
  (`_populate_normalized_mapping`), `src/steps/step2_reviewer/__init__.py`
  (`_check_source_mapping_resolved`'s new empty-mapping block),
  `src/steps/step3_codegen/__init__.py` (`_build_prompt`),
  `src/infra/data_layer/sources.py` (`signal_input_sources`),
  `src/steps/step3_codegen/script_generator.py` (`load_msf`, `main()`),
  `src/infra/backtest_engine/__init__.py`
  (`apply_universe_filters`/`_validate_annual_formation_month`),
  `runs/method_specs/resolved/AssetGrowth.resolved.methodspec.json`,
  CHANGELOG.md [Unreleased].

## 2026-08-02 — MethodSpec must record "paper stated but engine-unsupported" separately from "paper silent"

- **Context / problem:** Investigating whether the pipeline can capture a
  non-standard portfolio choice (e.g. Novy-Marx 2013's weight-capped VW
  scheme, `weighting="capped_vw"`) found that `MethodSpec`'s normalizers
  (`_normalize_weighting`/`_normalize_breakpoint_source`/
  `_normalize_missing_action`) silently mapped ANY off-menu value to the same
  `"unspecified"` sentinel used for "the paper never addressed this choice" —
  discarding the paper's literal value with no trace and making the two cases
  indistinguishable in review. A concrete orphaned fixture
  (`novy_marx_2013_gross_profitability.resolved.methodspec.json`, referenced by
  no test) already encoded this exact scenario.
- **Options considered:** (1) widen the engine's supported menu to include
  non-standard schemes like capped-VW (rejected — the user does not want to
  implement every non-standard config a paper might use); (2) widen MethodSpec
  fields to plain, unconstrained strings (rejected — reintroduces "enumerate
  every possible value" and weakens type safety for no benefit, since the
  engine still only executes menu members); (3) keep the standard menu closed
  and the engine untouched, but stop silently discarding an off-menu paper
  value: normalize it to a single `OTHER` sentinel (distinct from
  `UNSPECIFIED`) and preserve the literal value in a dedicated record.
- **Decision:** Chose (3). Added `OTHER` to `WeightingRule`, `BreakpointSource`,
  `MissingAction` (already the convention for `PortfolioConstructionType`/
  `ReturnCombinationType`). Added `MethodSpec.unsupported_fields` (paper's
  literal value + reason + evidence) as the only place that value survives —
  distinct from `ambiguous_fields` (paper silent/ambiguous), and explicitly
  descriptive-only (may explain what the paper's value *means*, never propose
  what to substitute). `registry.build_config` is the single deterministic
  point that decides the substitute, and now records it in
  `config["substitutions"]`. `ReviewGate` surfaces every unsupported field for
  human confirmation via a dedicated check, distinct from the existing
  paper-silent check.
- **Rationale:** This keeps the engine menu closed (no `capped_vw` branch is
  ever implemented) while making the pipeline's core "LLM-independent,
  auditable" claim hold for this case too: MethodSpec stays a faithful record
  of what the paper said, execution stays standardized, and the gap between
  them is recorded rather than silently erased. It also unlocks a future
  research statistic (substitution rate across factors) called for in
  `docs/replication-diagnosis-design.md` §15, and gives Phase C/D (see
  `docs/multi-config-evidence-plan.md`) a caveat to attach to any "vs paper"
  comparison for a factor with a recorded substitution — no substitution
  enters comparisons among our own multi-config runs, since it is a constant
  shared by every run of that factor's signal.
- **Empirical impact:** None on any existing run's numbers (a substitution
  only changes provenance/reporting, not what gets computed) — verified by a
  full test-suite run (208 passed, 26 skipped, no regressions) and by
  round-tripping the previously-unused `novy_marx_2013_gross_profitability`
  fixture end to end (`weighting` normalizes to `OTHER`;
  `unsupported_fields` records `paper_value="capped_vw"`; `build_config` clamps
  to `vw` and logs the substitution).
- **Trade-offs / risks:** Fixed an unrelated bug found while wiring this up:
  the curated-schema legacy-shape translator (fires whenever `signal` has no
  `timing` key) previously discarded an already-resolved
  `signal.missing_policy` in favor of the (usually absent)
  `universe.missing_policy`; now prefers the already-resolved value, matching
  the file's existing `universe_filters` precedence pattern. The
  `_UNSUPPORTED_FIELD_TO_CONFIG_KEY` map in `registry.py` must be kept in sync
  by hand if a new clamped config key is added.
- **References:** `src/infra/models/method_spec.py` (`WeightingRule`,
  `BreakpointSource`, `MissingAction`, `UnsupportedField`,
  `MethodSpec.unsupported_fields`, `_record_unsupported`),
  `src/steps/step3_codegen/registry.py` (`build_config` substitutions),
  `src/steps/step2_reviewer/__init__.py` (`_check_unsupported_fields`),
  `prompts/extractor/methodspec_extractor.md`,
  `prompts/review_gate/methodspec_audit.md`,
  `tests/test_unsupported_fields.py`,
  `tests/fixtures/method_specs/novy_marx_2013_gross_profitability.resolved.methodspec.json`,
  CHANGELOG `[Unreleased]`.

## 2026-08-02 — Pre/post-signal grouping, family vs identification level, and an experiment-matrix authoring layer

- **Context / problem:** A self-review of the multi-config evidence plan found
  three remaining gaps: (1) Decision 2's diff-set rule only covered 2 of the 5
  declared `ConfigKeySpec` stages (`portfolio`, `signal_input`), leaving
  `universe`/`sample`/`estimator` single-key diffs unaddressed even though they
  behave like `portfolio` (post-signal, signal-invariant); (2) the worked
  example's comparison table conflated the declared experiment *family* with
  the computed *identification level* into one column, inventing non-standard
  level names instead of using the design's own §5.2 vocabulary; (3) there was
  no answer to "where does a researcher actually declare which configs to
  run" — `ExperimentPlan` is only ever hardcoded in Python or clicked once in
  the Streamlit dashboard, never versioned or entered into the evidence chain.
- **Options considered:** (1) leave the two-stage rule as-is and special-case
  `universe`/`sample`/`estimator` later; (2) generalize to a pre-signal/
  post-signal grouping now; for authoring, (a) keep configs as inline Python/UI
  state, (b) add a declarative per-factor experiment-matrix file validated
  against `ConfigKeySpec` at load time.
- **Decision:** Generalized to (2): every `ConfigKeySpec.stage` is pre-signal
  (`signal_input`) or post-signal (`portfolio`/`universe`/`sample`/`estimator`);
  a single-key diff in either group is `controlled`, with the group determining
  whether a semantic-hash-equal (post-signal) or code-hash-equal (pre-signal)
  assertion applies. Split `family` (declared, on `ExperimentSpec`) from
  `identification level` (computed from the resolved diff, using design §5.2's
  four values) as two separate, never-merged report columns. Added Phase A2.1:
  a versioned `experiments/<factor_id>.experiments.yaml` per factor, validated
  whole-file against `ConfigKeySpec` at load time, with a `sweep` grid that
  expands into `ExperimentSpec`s and an `experiment_spec_hash` recorded on every
  run/batch.
- **Rationale:** The two-stage rule was incomplete, not just simplified — it
  silently left 3 of 5 stages without a defined comparability rule. Conflating
  family and identification level would let a `portfolio_ablation`-labeled
  experiment masquerade as `controlled` even when its resolved diff actually
  spans both groups. Without an authoring layer, "which configs were run" is
  never itself a reproducible, hashed input — undermining the audit trail the
  rest of the plan builds.
- **Empirical impact:** None — documentation only.
- **Trade-offs / risks:** The experiment-matrix file format is new surface area
  (schema, `ConfigKeySpec`-based validation, sweep expansion) that must be
  implemented before Phase A2 can proceed; deferred design of a Streamlit editor
  for the file.
- **References:** `docs/multi-config-evidence-plan.md` §3, §4
  Phase A2.1, §9; CHANGELOG `[Unreleased]`.

## 2026-08-02 — Reframe the research core around inter-implementer agreement and codify the LLM usage boundary

- **Context / problem:** The original framing ("which implementation choices
  drive the replication gap") overlaps heavily with the HXZ/C&Z literature and
  is weakened by the absence of original-author code — we only have C&Z's
  independent replication and its download API. The docs also still called C&Z
  "ground truth" and did not state where the LLM may and may not act.
- **Options considered:** (1) keep the implementation-gap-attribution framing as
  the headline; (2) pivot the headline to "can a controlled, leakage-proof LLM
  agent reconstruct a factor's method, and what does inter-implementer agreement
  (agent vs C&Z) plus implementation sensitivity reveal about reproducibility?",
  keeping gap-attribution as a supporting layer.
- **Decision:** Chose (2). C&Z is treated as an independent human replication
  (not ground truth, not original code); HXZ as the standardized-config source
  and robustness benchmark. Three separable layers: extraction fidelity, signal
  implementation agreement, conclusion robustness. Codified the LLM usage
  boundary (extraction + `compute_signal` only, optional review/explanation;
  everything empirical deterministic).
- **Rationale:** Without original-author code, "copying the author" is not a
  defensible claim; "reproducibility of the literature via inter-implementer
  agreement" is. The deterministic empirical layer is what makes the agent's
  contribution auditable and the conclusions LLM-independent.
- **Empirical impact:** None — documentation only; no code or numbers changed.
- **Trade-offs / risks:** The bridge track (C&Z signal × our engine, E2) needed
  to identify signal-vs-portfolio contributions is not yet implemented; docs now
  mark it as the one extra backtest to build.
- **References:** `README.md`, `docs/architecture.md` §1,
  `docs/replication-diagnosis-design.md` §1.1/§5.3, `docs/roadmap.md`,
  `AGENTS.md`, CHANGELOG `[Unreleased]`.

## 2026-08-01 — C&Z is a post-freeze diagnostic reference, not the second endpoint of a simple dual track

- **Context / problem:** The implemented Step 6 compares `original_method`
  with `standardized_hxz`, but the research objective is to explain why a
  published factor does or does not replicate. The repository actually has
  four evidence families: paper claims, C&Z per-factor signal code plus shared
  R portfolio code/SignalDoc settings, independently generated agent code, and
  our executed results. A two-endpoint result comparison changes several
  components at once and cannot identify the cause of a gap.
- **Options considered:** (1) retain original vs standardized as the primary
  replication design; (2) treat C&Z as ground truth and tune our pipeline to
  match it; (3) freeze the paper-only agent attempt, then use C&Z as a layered
  post-hoc reference for MethodSpec, signal, portfolio, data, and return
  comparisons. Chose (3); the standardized profile remains a robustness run.
- **Decision:** The target-factor extractor/reviewer/MetaCoder never receives
  target C&Z answers. After MethodSpec, human resolutions, plugin, target
  variant, snapshot, and paper-method config are frozen, diagnostic bridge
  experiments may compare agent and C&Z signals and portfolio results. Every
  claimed contribution must be labeled controlled, harmonized, observational,
  or unidentified. Replication outcomes use explicit cause labels and Step 7
  remains terminal rather than auto-tuning MethodSpec.
- **Rationale:** C&Z is valuable as an independent, explicit interpretation,
  not an infallible truth. Layered bridge experiments can distinguish paper
  ambiguity, extraction error, signal formula/timing, portfolio construction,
  data vintage/linking, and statistical fragility. End-to-end agreement alone
  cannot make those distinctions and target-code leakage would invalidate the
  evaluation of agent independence.
- **Empirical impact:** No backtest numbers change in this documentation-only
  decision. Future reports will distinguish paper target variants (for example
  AssetGrowth EW versus VW) before calling a result replicated or failed.
- **Trade-offs / risks:** Full diagnosis requires C&Z firm-level signals and
  returns, immutable per-track artifacts, signal-series persistence, adapters,
  and bridge experiments that are not implemented yet. Some historical data
  gaps may remain observational or unresolved.
- **References:** [replication-diagnosis-design.md](replication-diagnosis-design.md),
  [cz-reference.md](cz-reference.md), `src/evaluation/`,
  `src/steps/step6_dual_track_controller/`,
  `src/steps/step7_replication_diff/`, CHANGELOG `[Unreleased]`.

## 2026-07-30 — Real WRDS raw CSV data support: CIZ CRSP mapping approximations, Compustat/IBES dedup filters, and what was deliberately left unwired

- **Context / problem:** `data/local/` gained real bulk WRDS exports for the
  first time (CRSP monthly/daily, Compustat annual/quarterly, CCM link, IBES
  x3, 13F, CRSP index, Pastor-Stambaugh liquidity factors). None of them
  match the file names/column names/shapes the pipeline's catalog
  (`src/infra/data_layer/catalog.py`) and loaders (`data_layer/__init__.py`)
  already assumed (parquet files named `<source>.parquet` with a fixed,
  legacy CRSP-shaped column set). Two design questions: (1) convert to the
  legacy shape first via an offline script, or teach the data layer to read
  the real files directly; (2) how much of the real data to wire up given
  varying levels of schema ambiguity.
- **Options considered:**
  1. Offline conversion script producing `<source>.parquet` in the legacy
     shape, no `data_layer.py` changes.
  2. Extend `data_layer.py`/`catalog.py` to read the real files directly.
  3. For scope: wire up only the sources with a clean 1:1 physical-column
     match (Compustat, CCM/IBES links), vs. attempt every file including the
     structurally ambiguous ones (13F has no permno; CIZ CRSP has no direct
     shrcd equivalent; global Compustat is a different universe entirely).
- **Decision:** Chose option 2 (direct CSV readers, no offline conversion
  step) per explicit user direction. Chose to wire up everything with a
  well-defined mapping (CRSP monthly/daily CIZ, Compustat annual/quarterly,
  CCM link, IBES-CRSP link, IBES summary, CRSP index, liquidity factors), add
  best-effort/lightly-wired loaders for the structurally ambiguous ones (13F,
  IBES recommendation/actual), and explicitly skip
  `COMPUSTAT_GLOBAL_STOCK_MONTH.csv` (a different, international returns
  universe — its own design question, not a quick add).
- **Rationale / key mapping decisions:**
  - **CRSP CIZ `exchcd`:** the new CIZ format's `PrimaryExch` is a letter
    code with no official published mapping back to legacy numeric exchcd.
    Only the three unambiguous codes seen in this vendor's export are mapped
    (N=1 NYSE, A=2 AMEX, Q=3 Nasdaq); every other code (this export also has
    'X'/'R', meaning unclear) maps to 0 ("other/unclassified", a valid
    legacy value) rather than guessing. This means `breakpoint_source="nyse"`
    behaves identically to the legacy path (only real exchcd==1 rows count).
  - **CRSP CIZ `shrcd`:** CIZ has NO direct share-code equivalent at all
    (legacy CRSP's own `shrcd` classification was dropped from this export
    format). Approximated from `SecurityType`/`SecuritySubType`/`ShareType`/
    `USIncFlg` well enough for the common `shrcd in [10, 11]` "ordinary
    common stock only" universe filter to evaluate correctly (US-incorporated
    common, non-ADR -> 11; everything else common -> 12; CEF -> 18; ETF/FUND
    -> 73; else -> 0). This is NOT a faithful reproduction of every legacy
    shrcd value CRSP itself would have assigned — a real limitation if a
    paper's universe filter depends on a shrcd distinction finer than
    "ordinary common vs. everything else".
  - **Compustat annual/quarterly dedup:** the raw bulk export is NOT
    pre-cleaned to one row per (gvkey, datadate) the way a hand-converted
    parquet snapshot was — it also carries an `indfmt=="FS"`
    (financial-services) format variant of the same gvkey+datadate with
    different field meanings for some items. Filtered to `indfmt=="INDL"`
    (the standard non-financial-services format), matching the conventional
    WRDS Compustat filter (`indfmt=INDL, datafmt=STD, popsrc=D, consol=C`
    — datafmt/consol were already constant in this export; popsrc wasn't
    present as a column at all).
  - **IBES summary dedup:** the raw export carries multiple forecast
    horizons (QTR/ANN/LTG) and FPI values per (ticker, statpers). Filtered to
    the single standard series most papers use: FY1 (`fpi==1`) annual
    (`fiscalp=="ANN"`) EPS (`measure=="EPS"`) consensus.
  - **13F institutional ownership:** this export has no `permno` column at
    all (its own key is `cusip`); resolved via a CUSIP match against
    `CRSP_STOCK_MONTH.csv`'s own (permno, CUSIP) pairs using each CUSIP's
    MOST RECENT observed permno — NOT a point-in-time link (no validity
    window, unlike the CCM/IBES-CRSP link tables already in the catalog). A
    CUSIP reassigned across permnos at some point in CRSP's history could
    resolve to the wrong one. Deliberately kept OUTSIDE the declarative
    catalog (not registered as a `DATA_CATALOG`/`tr_13f` join) until this is
    replaced with a real point-in-time CUSIP history — registering a
    catalog entry implies a level of correctness this loader doesn't have.
  - **IBES recommendation detail / unadjusted actual:** no signal plugin in
    the repo consumes either, so no catalog entry or permno-linking logic was
    invented for them — a thin lower-case/date-parse pass-through loader
    only. Wire up a real catalog entry (with its own join key/date/lag) once
    a paper actually needs one.
- **Empirical impact:** None yet measured — this is data-plumbing, not a
  MethodSpec run. The exchcd/shrcd approximations could matter for any
  future MethodSpec whose universe filter relies on a shrcd/exchcd
  distinction finer than what's preserved here (see Trade-offs).
- **Trade-offs / risks:**
  - `shrcd`/`exchcd` on the CIZ path are best-effort approximations, not a
    byte-exact reproduction of what legacy CRSP would have assigned — see
    rationale above. Revisit if a paper's replication gap traces back to a
    universe-filter mismatch on real CIZ data.
  - The 13F CUSIP link is not point-in-time and is explicitly marked
    not-production-quality.
  - `CRSP_STOCK_DAILY.csv` (~60GB, ~10^8 rows) has a loader
    (`load_daily_msf_ciz`) but was never run against the FULL file in this
    session — tests use a small `nrows` sample only. A real production run
    against the full file has not been timed/memory-profiled.
  - `COMPUSTAT_GLOBAL_STOCK_MONTH.csv` remains completely unwired.
- **References:** `src/infra/data_layer/__init__.py` (`build_crsp_monthly_panel_ciz`,
  `load_daily_msf_ciz`, `_read_raw_source_csv`, `_read_raw_link_table_csv`,
  `load_crsp_index_factors`, `load_liquidity_factors`,
  `load_institutional_ownership_13f`, `load_ibes_recommendation_detail`,
  `load_ibes_unadjusted_actual`); `src/infra/data_layer/catalog.py`
  (`RAW_CSV_SOURCE_FILES`, `RAW_CSV_LINK_TABLE_FILES`,
  `RETURNS_UNIVERSES["us_equity_crsp_ciz"]`); `src/infra/backtest_engine/__init__.py`
  (`load_data`'s `returns_layout=="crsp_ciz"` branch);
  `tests/test_real_wrds_csv_loaders.py`; CHANGELOG.md [Unreleased] same date.

## 2026-07-28 — Fix: breakpoint population was leaking future return availability (look-ahead / survivorship)

- **Context / problem:** An external technical review of `BacktestExecutor`
  reproduced a concrete bias: `apply_signal_holding_period` expands each
  signal row to its held months and does `df.merge(expanded, on=["permno",
  "yyyymm"], how="inner")` against the returns panel — so a permno with NO
  valid return in ANY of its held months (e.g. delisted the month right
  after formation) is entirely absent from the resulting `self.merged`.
  `compute_breakpoints` then computed the formation-cohort quantile
  breakpoints FROM `self.merged`, meaning that stock's signal never entered
  its own cohort's breakpoint calculation — a formation-time statistic was
  silently conditioned on information (whether the stock has ANY future
  return) that could not have been known at formation time. The reviewer's
  minimal repro: formation signals `[1,2,3,4]` (true median 2.5) with the
  signal-4 stock delisted before any held month, produced a breakpoint of
  2.0 (computed from the surviving `[1,2,3]`) instead of the correct 2.5.
- **Options considered:** (a) leave as documented limitation (the existing
  formation-locked-breakpoints fix already addressed *when* breakpoints are
  computed, not *which population* enters them); (b) restructure the engine
  to fully decouple portfolio assignment from the returns panel until after
  assignment (assign portfolios on the pure signal cross-section, join
  returns only at `compute_portfolio_returns`) — the "textbook-correct" but
  invasive rewrite touching `apply_signal_holding_period`'s public contract
  and the two existing unit-test files that call
  `compute_breakpoints`/`assign_portfolios` directly with an explicit
  post-join `df`; (c) keep the existing method signatures/contracts (so
  `compute_breakpoints(df, config)` called explicitly with an arbitrary
  `df`, as the existing unit tests do, is unaffected) but change the
  *default* population `compute_breakpoints` reads from `self.*` state when
  called with no `df` — from `self.merged` to a new `self.formation`
  cross-section built by `apply_signal_holding_period` independently of
  return-join survival.
- **Decision:** (c). `apply_signal_holding_period` now also builds
  `self.formation`: one row per (permno, cohort) with `signal` (+ `exchcd`
  read from that permno's OWN formation-month row in the base returns panel,
  not from an arbitrary later held month, so `breakpoint_source="nyse"`
  doesn't reintroduce the same leak) — built directly from `signal` before
  the future-returns inner join, so it is unaffected by which permnos
  survive that join. `form_portfolios` passes `self.formation` (falling back
  to the merged panel only if `self.formation` was never built, e.g. a test
  hand-sets `self.merged` bypassing `apply_signal_holding_period`) into
  `compute_breakpoints` instead of the post-join panel.
  `assign_portfolios`'s target population is unchanged (still the post-join
  `self.merged`) — a permno with zero surviving held-month rows contributes
  nothing to `compute_portfolio_returns` regardless, so there's no bias risk
  in leaving that part alone; only the breakpoint *population* needed to
  change.
- **Rationale:** A formation-time statistic (the breakpoint) must be
  computable from only formation-time-available information. Whether a
  stock happens to have a valid return in a FUTURE held month is not
  formation-time information — using it to decide whether that stock's
  signal counts toward the breakpoint is a look-ahead/survivorship leak, and
  one that gets worse the more delisting/missing-return churn a factor's
  universe has (i.e. it's not a rare edge case for many real cross-sections).
  Keeping the existing method signatures/explicit-`df` contract intact meant
  the fix required zero changes to the two existing
  `test_formation_locked_breakpoints.py`/`test_calendar_rebalance.py` test
  files, which call `compute_breakpoints`/`assign_portfolios` with an
  explicit `df` and therefore exercise the same (unbiased-by-this-issue)
  grouping/quantile/pd.cut mechanics either way.
- **Empirical impact:** No-op for any signal/universe with zero
  delisting/missing-return churn during the holding period (confirmed by the
  full existing test suite passing unchanged, 150 passed / 26 skipped).
  Changes numbers only for cohorts where at least one formation-eligible
  stock has no valid return in any of its held months — exactly the case
  this fix targets. New regression test
  (`tests/test_no_lookahead_breakpoints.py`) reproduces the reviewer's exact
  scenario: breakpoint moves from the biased 2.0 back to the correct 2.5,
  and the resulting portfolio assignment for the surviving stocks changes
  accordingly (permno with signal 2.0 moves from the "high" leg to the "low"
  leg once measured against the true 4-stock median instead of the
  survivor-only 3-stock median).
- **Trade-offs / risks:** `self.formation` only carries `exchcd` (the one
  formation-time attribute `compute_breakpoints` currently needs) alongside
  `signal` — if a future breakpoint variant needs additional formation-time
  columns (e.g. a size-conditional double sort), `apply_signal_holding_period`
  will need to pull those into `self.formation` too. The direct
  `engine.merged = ...; engine.form_portfolios()` isolated-testing pattern
  documented in the class docstring still reproduces the old (biased)
  behavior when used without going through `apply_signal_holding_period`,
  since the true formation population can't be reconstructed from `merged`
  alone — this is called out explicitly in both methods' docstrings.
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (`apply_signal_holding_period`, `form_portfolios`, `compute_breakpoints`),
  [tests/test_no_lookahead_breakpoints.py](../tests/test_no_lookahead_breakpoints.py).

## 2026-07-28 — Fix: ReviewGate approved fully-defaulted specs as `paper_faithful`

- **Context / problem:** The same external review that found the P0-1
  breakpoint issue above also constructed a MethodSpec with only
  `signal.formula`/`signal.required_fields`/`portfolio.long_leg`/`short_leg`
  set (the last two already default to "high"/"low", so setting them isn't
  even required) and every other empirical field left at its schema default
  (`breakpoint_source`/`weighting`/`missing_policy`/`rebalance_frequency`
  all "unspecified", `formation_month`/`holding_period`/`accounting_lag`/
  `sign` all `None`, `universe`/`universe_filters` empty). `ReviewGate.review()`
  returned `approved=True, codegen_ready=True, paper_faithful=True` for it.
  Root cause: `_check_required_fields` only checks those three
  non-empty-string conditions; `_check_ambiguous_fields` (the mechanism that
  actually applies the Evidence×Impact Review Decision Matrix and can block
  approval) only iterates `spec.ambiguous_fields` -- a list the EXTRACTOR
  must proactively populate. A spec where the extractor (or a hand-built
  test spec) never records an `ambiguous_fields` entry for a silent
  high-impact field has *nothing* for that check to act on, so
  `registry.build_config`'s menu-default clamping proceeds completely
  unreviewed, and the resulting run still gets stamped `paper_faithful=True`.
  This directly contradicts the project's core invariant ("empirical
  parameters must be reviewed", `AGENTS.md` "Never let LLM output decide
  empirical parameters without MethodSpec review").
- **Options considered:** (a) leave as-is, since `_check_ambiguous_fields`
  technically implements the full Review Decision Matrix once evidence is
  reported -- but this leaves the matrix inert whenever evidence reporting
  itself is silent, which is exactly the failure mode found; (b) require the
  extractor to always emit an `ambiguous_fields` entry for every
  `HIGH_IMPACT_FIELDS` path regardless of confidence, so `_check_ambiguous_fields`
  always has something to classify -- pushes the fix into prompt-following
  behavior that can't be verified deterministically at review time; (c) add
  a deterministic reviewer-side backstop that inspects a fixed, individually
  verified subset of `HIGH_IMPACT_FIELDS` for an unambiguous "nothing was
  said" sentinel (explicit `UNSPECIFIED` enum member, or `None`/empty for a
  plain Optional/list field), and — only when no matching `ambiguous_fields`
  entry already covers that field — treats it as
  `(EvidenceSource.UNSPECIFIED, EmpiricalImpact.HIGH)` per the existing
  Review Decision Matrix (`needs_human_confirmation`), independent of
  whether the extractor said anything at all.
- **Decision:** (c). Added `ReviewGate._check_silent_high_impact_fields`,
  wired into `review()` after `_check_ambiguous_fields`. Covers
  `portfolio.sort.breakpoint_source`, `portfolio.weighting`,
  `signal.missing_policy`, `signal.timing.rebalance_frequency`,
  `signal.timing.formation_month`, `signal.timing.holding_period`,
  `signal.timing.accounting_lag`, `signal.sign`, `portfolio.universe`,
  `portfolio.universe_filters`, `portfolio.return_combination` — the
  subset of `HIGH_IMPACT_FIELDS` whose silence is unambiguous by value.
  Deliberately does NOT cover `portfolio.long_leg`/`short_leg`
  (default to the affirmative-looking "high"/"low", not a sentinel) or
  `portfolio.construction_type`/`portfolio.implied_factor_direction`/
  `reported_results.*` (no individually-verified sentinel mapping yet) —
  those remain dependent on the extractor's own `ambiguous_fields`
  reporting, same as before.
- **Rationale:** A deterministic, reviewer-owned check that can't be
  bypassed by the extractor simply staying silent is a stronger guarantee
  than relying entirely on the extractor to self-report uncertainty — it
  makes "no evidence recorded" fail closed (block) instead of fail open
  (silently default + stamp paper-faithful). Restricting it to an
  individually-verified subset (rather than a generic loop over all of
  `HIGH_IMPACT_FIELDS`) avoids guessing at fields whose "unspecified" value
  can't be told apart from a legitimate explicit choice, which would risk
  false positives blocking genuinely-complete specs.
- **Empirical impact:** No-op for every existing fixture/test in the repo
  (full suite: 154 passed / 26 skipped, no changes) — all curated
  `tests/fixtures/method_specs/*.resolved.methodspec.json` specs already
  have these fields explicitly set or covered by `ambiguous_fields`.
  New regression suite `tests/test_reviewer_silent_defaults.py` reproduces
  the reviewer's exact minimal-spec repro (now blocked, not
  approved/paper_faithful), confirms an already-flagged field isn't
  double-blocked, and confirms a genuinely complete spec still passes
  cleanly (no false positives).
- **Trade-offs / risks:** Not exhaustive over all 20 `HIGH_IMPACT_FIELDS`
  entries (see the "deliberately does NOT cover" list above) — a spec could
  still slip through with one of those uncovered fields silently defaulted.
  Extending coverage to them requires verifying, field by field, what value
  actually constitutes "the paper said nothing" for each (several of
  `HIGH_IMPACT_FIELDS`' dotted paths are legacy aliases that don't map
  1:1 onto the current Pydantic attribute tree, e.g. `"timing.accounting_lag_months"`
  has no corresponding real attribute and always resolves to `None` via
  `_get_field_value`'s dotted-path walker regardless of the spec's actual
  content) — deferred rather than guessed at in this pass.
- **References:** [src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py)
  (`_check_silent_high_impact_fields`, `HIGH_IMPACT_FIELDS`, `review`),
  [tests/test_reviewer_silent_defaults.py](../tests/test_reviewer_silent_defaults.py).

## 2026-07-26 — MethodSpec field audit: remove dead fields, keep the curated evidence-citation schema

- **Context / problem:** After the engine/pipeline simplification (single
  standard backtest path, `BacktestExecutor` consolidation), user asked
  whether `MethodSpec` itself still carries residual complexity from the
  earlier, more complex agent design that could now be simplified. A full
  field-by-field audit (via a research subagent, cross-checking every
  `MethodSpec` field against actual reads in `registry.py`, the engine,
  `step2_reviewer`, `step1_extractor`, `src/evaluation/`, `app.py`, and
  `scripts/`) found most "unread by Python code" fields are not actually
  dead — `step2_reviewer` dumps the ENTIRE spec as JSON into the LLM
  review-gate prompt (`json.dumps(spec.model_dump(...))`), so any field
  reachable from that dump is consumed by the audit/review step even
  without a dedicated `.field` access in Python. The one deliberately large
  candidate for removal, `MethodSpec.normalize_curated_schema` (~150 lines,
  converts the LLM's actual output shape — top-level `paper`/`timing`/
  `universe`/`portfolio` keys with per-field `{location, quote,
  interpretation}` evidence — into the flat pydantic fields the rest of the
  pipeline consumes), turned out to be the LIVE extractor-prompt contract
  (`prompts/extractor/methodspec_extractor.md` still requires this exact
  curated shape), not legacy back-compat: `data/test_method_specs_human_labeled/`
  (10 files), 5 `tests/fixtures/method_specs/*.resolved.methodspec.json`
  fixtures, and `scripts/run_extraction_eval.py`'s `load_ground_truth()` all
  depend on it today.
- **Options considered:** For the curated schema specifically: (a) keep it
  as-is; (b) rewrite the extractor prompt to have the LLM emit the flat
  `MethodSpec` shape directly and delete `normalize_curated_schema`
  entirely; (c) keep the curated input capability but restructure
  `MethodSpec.economic_intuition`/`detailed_definition`/`sign` into
  evidence-carrying sub-models so no per-field citation granularity is lost
  either way.
- **Decision:** Kept the curated schema/`normalize_curated_schema` as-is
  (option a) — explicitly rejected flattening. The curated shape's entire
  reason for existing is giving `economic_intuition`/`detailed_definition`/
  `sign` (and other fields) their OWN per-field `{location, quote,
  interpretation}` paper citation, independent of the coarser
  sub-model-level `evidence: list[EvidenceCitation]` fields the flat
  `MethodSpec` already has elsewhere (`SignalTiming.evidence`,
  `MissingPolicy.evidence`, etc.). Flattening the extractor prompt would
  either lose that per-field citation granularity or require a
  larger redesign of the flat schema itself — neither was worth it just to
  remove ~150 lines of adapter code, given per-field evidence citation is a
  core "auditable pipeline" selling point of this project (see
  `docs/architecture.md` §2). Instead, removed only what a full field audit
  confirmed was genuinely dead: `PortfolioSortSpec.quantiles` (duplicated
  `ls_quantile`, the field the engine actually reads), `ReturnCombinationSpec.long_leg`/
  `short_leg` (duplicated `PortfolioSpec.long_leg`/`short_leg`, the fields
  `registry.resolve_long_leg`/`resolve_short_leg` actually read),
  `AmbiguousField.confidence` (written by the extractor and
  `step2_reviewer/resolution.py` but never read — `empirical_impact` is the
  field that actually drives review-blocking), and the orphaned
  `src/evaluation/gt_matcher.py` module (`GroundTruthMatcher`, zero
  production callers anywhere in the repo).
- **Rationale:** "Not read by a Python `.field` access" is not the same as
  "unused" for an audit-first schema whose primary consumer for many fields
  is a human/LLM reading the full JSON dump, not runtime logic — conflating
  the two would have deleted real audit-trail content. Narrowing to fields
  confirmed dead by tracing every actual reader kept this a safe, reversible
  cleanup instead of an extraction-prompt redesign with a real fidelity
  trade-off.
- **Empirical impact:** None — pure schema/dead-code cleanup, no behavior
  change to extraction, review, codegen, or backtest numbers. One test
  (`tests/test_resolution.py::test_apply_decisions_writes_value_clears_ambiguous_and_resets_status`)
  updated to stop asserting on the removed `confidence` field. Full suite:
  147 passed, 26 skipped (unchanged from baseline).
- **Trade-offs / risks:** None identified for the fields actually removed
  (confirmed zero readers across the whole repo before deleting each one).
  The curated-schema simplification opportunity remains on the table for a
  future, deliberate redesign if the per-field evidence-citation granularity
  is ever judged not worth its complexity — that would need prompt
  engineering care (`prompts/extractor/methodspec_extractor.md`) and is out
  of scope here.
- **References:** [src/infra/models/method_spec.py](../src/infra/models/method_spec.py)
  (`PortfolioSortSpec`, `ReturnCombinationSpec`, `AmbiguousField`),
  [src/steps/step1_extractor/__init__.py](../src/steps/step1_extractor/__init__.py),
  [src/steps/step2_reviewer/resolution.py](../src/steps/step2_reviewer/resolution.py),
  `tests/test_resolution.py`, `CHANGELOG.md` [Unreleased].

## 2026-07-24 — Replace Streamlit dashboard with a React + FastAPI website

- **Context / problem:** `app.py` (a single ~2,200-line Streamlit script, 7
  pages) is hard to make interactive/responsive: Streamlit reruns the whole
  script on every widget interaction, blocks the browser during long LLM/
  backtest operations (only `st.spinner`/`st.progress` feedback), and has no
  path to real-time step-by-step progress. User asked for a proper website
  with good interactivity.
- **Options considered:** (a) Keep Streamlit, add custom components /
  `st.status` for nicer progress -- limited ceiling, still monolithic reruns.
  (b) Next.js SSR app -- more routing/build machinery than an internal
  single-user research tool needs. (c) FastAPI backend (wrapping existing
  `Pipeline`/step classes unmodified) + React/TypeScript/Vite SPA frontend
  with Tailwind/shadcn/ui, Recharts, and a generic SSE-based job system for
  live progress.
- **Decision:** Option (c). Full replacement of `app.py` (kept in place,
  untouched, until the new site reaches feature parity; removal is a
  separate future step). Local-only deployment (localhost:8000 backend /
  localhost:5173 frontend dev servers), no auth. Scope staged: Phase 1 covers
  Pipeline-E2E-wizard + Backtest&Experiments + Trace&Logs pages (the
  highest-value core loop); the remaining 4 standalone pages
  (Extractor/Review&Resolve/MetaCoder/Attribution) are explicit follow-up,
  since their backend endpoints get built anyway (the E2E wizard calls the
  same per-stage business logic).
- **Rationale:** All business logic (`src/pipeline.py`, `src/steps/*`,
  `src/infra/*`) is already well-factored and reusable as-is -- the backend
  only needs to wrap existing entry points (`SemanticExtractor.extract`,
  `ReviewGate.review`/`review_with_llm`, `MetaCoder.generate_plugin`,
  `AdversarialSandbox.validate`, `BacktestRunner.build_script`/`execute`,
  `EvidenceStore`/`RunRegistry`), never re-implementing empirical logic in
  the web layer (preserves the "LLMs don't control empirical conclusions"
  constraint). `PipelineTracer` (`src/infra/trace.py`) is in-memory,
  read-after-fact only (no subscribe/callback API) -- rather than wiring
  into it, the backend orchestrates each pipeline stage itself (mirroring
  how `app.py` already manually drives stages 1-7 with human-in-the-loop
  pauses) and emits its own SSE events per stage via a generic `JobManager`
  (`asyncio.to_thread` + per-job event queue). This is simpler than making
  `PipelineTracer` thread-safe/subscribable and needs no core pipeline
  changes.
- **Empirical impact:** None -- UI/tooling change only, no effect on
  replication results.
- **Trade-offs / risks:** (1) The resolution-decision logic
  (`_apply_decisions` et al.) previously lived only in
  `scripts/resolve_review_blocks.py`; extracted to
  `src/steps/step2_reviewer/resolution.py` as a prerequisite so the backend
  doesn't duplicate it -- pure refactor, covered by new
  `tests/test_resolution.py`. (2) `BacktestRunner.execute()` has no
  subprocess timeout today; not adding one as part of this migration (matches
  current behavior) -- revisit only if a hung backtest becomes a real
  problem. (3) Dual-track/ablation runs are already disabled/placeholder in
  `app.py` itself, so the new Backtest & Experiments page intentionally only
  covers single-run backtests for now -- not a regression, matches current
  real functionality.
- **References:** `pyproject.toml` (`web` extra), `src/steps/step2_reviewer/resolution.py`,
  `tests/test_resolution.py`, `CHANGELOG.md` [Unreleased] "web UI backend
  scaffolding".

## 2026-07-24 — Consolidate `steps.py`/`estimators.py`/`__init__.py` into one stateful `BacktestExecutor` class

- **Context / problem:** The engine was split across three files (`__init__.py`
  orchestration, `steps.py` pure step functions, `estimators.py` the
  estimator-strategy registry), with state threaded explicitly through a
  `BacktestContext` dataclass and a generic `_dispatch(name, *args, config=...)`
  indirection. User feedback: this was harder to read than necessary for a
  fixed, single-path pipeline (post the same-day capability-strip) — wanted
  one file, one class, each pipeline step as one method, and `run_with_config()`
  readable top-to-bottom as the complete pipeline.
- **Options considered:** (a) leave the three-file/dataclass/dispatch design;
  (b) merge to one class with zero-argument instance methods that only
  read/write `self.*` (matches the user's literal preference, but would make
  each step un-testable in isolation without first hand-populating instance
  state — a real regression against this repo's long-standing "pure function,
  independently testable" principle); (c) merge to one class where every step
  method accepts its inputs as OPTIONAL explicit arguments (falling back to
  the matching `self.*` attribute when omitted) — `run_with_config()` calls
  each with zero arguments (reading/writing `self.*`, satisfying the
  readability ask), while a unit test can still call the same method with
  explicit arguments and read the return value directly, exactly like the
  old pure-function call sites.
- **Decision:** (c). Everything now lives in
  `src/infra/backtest_engine/__init__.py` as one `BacktestExecutor` class;
  `steps.py`/`estimators.py` are deleted. `_dispatch()`/`Step` Protocol/
  `BacktestContext` are gone — `run_with_config()` is a flat sequence of
  `self.<step>()` calls in fixed order. A handful of small pure utilities that
  aren't themselves pipeline steps (`load_msf`, `load_daily_msf`,
  `apply_universe_filters`, `_apply_filter_op`, `_rebalance_step_months`,
  `_series_metrics`, `_sample_period_metrics`, `_newey_west_var`) are
  `@staticmethod`s needing no instance state.
- **Rationale:** Preserves the project's established testability/auditability
  principle (every step still independently callable and unit-testable with
  explicit inputs -> explicit output) while genuinely improving readability of
  the top-level pipeline (`run_with_config()` reads as 10 method calls, one
  per line, vs. the old `ctx.data = self._dispatch("name", ctx.data, config=config); ctx.trace.append("name")`
  boilerplate repeated per step) and satisfying the one-file/one-class ask.
- **Empirical impact:** None (pure refactor, no behavior change). Full suite
  re-verified after: 134 passed, 26 skipped (same as immediately before this
  change). 9 test files updated to call `BacktestExecutor().<method>(...)` /
  `BacktestExecutor.<static_method>(...)` instead of `steps.<function>(...)`;
  no test assertions changed.
- **Trade-offs / risks:** An engine instance is not safe to reuse
  concurrently/re-entrantly for two different `run_with_config()` calls at the
  same time (shared mutable `self.*` state) — every current caller
  (`app.py`, `script_generator.py`'s generated scripts, `pipeline.py`) already
  constructs a fresh `BacktestExecutor()` per run, so this is not a change in
  practice, just documented here as a constraint to keep in mind if a future
  caller wants to reuse/parallelize instances.
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (now the only file in the package besides `__pycache__`).

## 2026-07-24 — Formation-locked (cohort-based) breakpoints/portfolio assignment for the standard sort path

- **Context / problem:** `steps.form_portfolios`'s standard (non-overlapping)
  continuous-sort path recomputed breakpoints and portfolio membership fresh
  every CURRENT month (`compute_breakpoints`/`assign_portfolios` grouped by
  `yyyymm`), rather than locking them at the formation date and holding them
  fixed for the whole holding period. This deviates from the standard
  academic/industry factor-replication convention (Fama-French / Ken French
  Data Library / AQR-style: form once per rebalance, hold membership fixed,
  only recompute returns monthly) and had two concrete consequences: (a) a
  stock's portfolio number could drift within its own nominal holding period
  if the concurrent cross-section composition changed (e.g. another stock's
  transient missing-return month, or a differently-scaled cohort
  concurrently held), and (b) mixing staggered formation cohorts in the same
  current month could corrupt everyone's breakpoints.
- **Options considered:** (a) leave as-is (documented limitation); (b) always
  route the standard path through the existing overlapping-cohort machinery
  (`compute_breakpoints_overlap`/`assign_portfolios_overlap`, which already
  compute breakpoints once per formation `cohort`); (c) write an independent
  formation-locked implementation directly inside the standard
  `compute_breakpoints`/`assign_portfolios` functions, with the overlapping-
  cohort feature family removed entirely in the same pass (see the
  companion entry below) so there is no ambiguity about which mechanism the
  standard path uses.
- **Decision:** (c). `steps.merge_signal` (renamed `apply_signal_holding_period`
  the same day, see below) now tags every expanded row with a
  `cohort` column (the signal's original, pre-shift formation `yyyymm`).
  `compute_breakpoints` groups by `cohort` (de-duplicating to one row per
  `(permno, cohort)` before quantiling — which specific held month's row
  survives the de-dup doesn't matter, since `signal` is constant across a
  cohort's held months by construction). `assign_portfolios` looks up
  breakpoints by `cohort` instead of `yyyymm`, so a stock's portfolio number
  is fixed for its whole holding period. A cohort whose de-duplicated
  cross-section produces duplicate quantile edges (too few distinct signal
  values to cut into `n` groups) is skipped entirely for that cohort, rather
  than silently collapsing to fewer groups whose portfolio numbers would
  mean something different from every other cohort's.
- **Rationale:** Matches the standard convention used by Kenneth French's
  Data Library, AQR's published factor-replication code, and virtually every
  academic "portfolio sort" implementation — the goal of this project is
  fidelity to a paper's stated methodology, not a lower-staleness variant
  the paper never specified. `compute_returns`/`compute_long_short` needed
  no changes: they only `groupby(["yyyymm","portfolio"])` and build a fresh
  frame via `reset_index`, so the extra `cohort` column is inert metadata
  that never survives past `compute_returns`'s output.
- **Empirical impact:** No-op (byte-identical) for a synchronized formation
  calendar with zero missing-data churn during a holding period (breakpoints
  computed from an unchanged constant cross-section give identical numbers
  whether keyed by cohort or current month) — confirmed by the full existing
  `test_*_e2e.py` suite passing unchanged. Numbers change only for papers
  with staggered/rolling formation dates or missing-return churn mid-holding
  period — exactly the cases this fix targets. One pre-existing test
  (`test_signal_master_multisource.py::test_generated_multi_source_script_runs`)
  surfaced a genuine edge case (a monthly-refreshed IBES signal run through
  the non-overlapping default without flagging `overlapping`, producing a
  formation cohort with a degenerate/duplicate-value cross-section); fixed
  by skipping portfolio formation for that one degenerate cohort instead of
  crashing (see `compute_breakpoints`/`assign_portfolios` in `steps.py`).
- **Trade-offs / risks:** Multi-dimensional (double) sorts were removed in
  the same pass (see below) and never got a formation-locked treatment;
  should double sorts return in the future, they would need the same fix
  applied to their own breakpoint/assignment functions.
- **References:** [src/infra/backtest_engine/steps.py](../src/infra/backtest_engine/steps.py)
  (`apply_signal_holding_period`, `compute_breakpoints`, `assign_portfolios`),
  [tests/test_formation_locked_breakpoints.py](../tests/test_formation_locked_breakpoints.py).

## 2026-07-24 — Strip non-standard engine capabilities to one vanilla single-dim portfolio-sort path

- **Context / problem:** An architecture review of every config/MethodSpec
  field driving the backtest engine (schema → extractor → reviewer →
  registry → engine) found five branches whose value, weighed purely
  against "is this part of the single most standard factor-replication
  path" (independent of how many existing fixtures happened to exercise
  them), did not belong in a from-scratch vanilla engine: overlapping-cohort
  holding (momentum/reversal convention), multi-dimensional (double) sorts,
  the discrete/categorical sort form, the Fama-MacBeth cross-sectional-
  regression estimator, and the optional microcap-exclusion filter.
- **Options considered:** (a) keep all five (prior audit's recommendation,
  weighing fixture-coverage loss — 9/26 fixtures used Fama-MacBeth, ~3-5
  used double sorts); (b) remove only the two with near-zero fixture
  coverage (overlapping: 2/26; discrete: 0/26; microcap: 0/26, always
  `False`); (c) remove all five regardless of fixture coverage, per explicit
  direction to standardize the engine to one vanilla path first and
  re-introduce capabilities later, incrementally, only as a specific
  paper's replication actually needs them.
- **Decision:** (c). Removed: `config["overlapping"]` (+
  `merge_signal_overlap`/`compute_breakpoints_overlap`/
  `assign_portfolios_overlap`/`compute_returns_overlap`/
  `compute_long_short_overlap`, `_OVERLAP_STEPS` dispatch routing,
  `SignalTiming.overlapping_portfolios`/`skip_month` fields);
  `cat_form="discrete"` (+ `MethodSpec.cat_form` field, the discrete
  branches in `compute_breakpoints`/`assign_portfolios`/`compute_long_short`);
  `config["microcap_exclude"]` (+ its branch in `filter_universe`);
  `config["sort_dims"]`/multi-dimensional sort (+
  `compute_breakpoints_multi`/`assign_portfolios_multi`, `_MULTI_DIM_STEPS`
  dispatch routing, `registry.resolve_sort_dims`/`_sort_variable_column`,
  `PortfolioSpec.sorts[]`/`SortLegSpec`); `estimator="fama_macbeth"` (+
  `estimators.run_fama_macbeth`, `steps.compute_fama_macbeth`,
  `PortfolioConstructionType.REGRESSION_WEIGHTED`, the optional
  `linearmodels` dependency). Kept as-is (both options in each pair are
  equally "standard" in the literature and removing either wouldn't reduce
  branching complexity): `weighting_rule` (vw/ew), `breakpoint_source`
  (nyse/full_sample), all four `return_combination_type` variants,
  `rebalance_frequency`, the deterministic delisting/missing/excess-return
  handling.
- **Rationale:** A vanilla, easy-to-verify single path is a better
  foundation to layer the formation-locked-breakpoints fix (see companion
  entry above) onto than a codebase with four parallel step-families
  (standard/`_overlap`/`_multi`/fama-macbeth) to keep in sync. Every removed
  capability remains re-addable later, one at a time, against a concrete
  paper that needs it, rather than carried as speculative generality.
- **Empirical impact:** Deleted the fixtures/tests tied to the removed
  capabilities: 9 Asness-Bender 1998 fixtures (`data/test_method_specs_human_labeled/AB1998_*`,
  fama_macbeth), 2 LohWarachka 2011 fixtures (`..._StreakSign`/`..._StreakSURPQuintile`,
  overlapping), 3 Ball 2016 fixtures (`Ball2016_ACC`/`RMWCbOP`/`RMWOP`, 2x3
  double sort), and 3 orphaned `tests/fixtures/` momentum/double-sort
  fixtures+plugins that no active test referenced
  (`jegadeesh_titman_1993_momentum`, `moskowitz_grinblatt_1999_industry_momentum`,
  `fama_french_1993_double_sort_hml`). Deleted `tests/test_overlapping_holding.py`,
  `tests/test_multi_sort.py`, `tests/test_fama_macbeth.py`,
  `tests/test_discrete_sort.py`, and the microcap tests in
  `tests/test_research_design.py`. Full suite: 134 passed, 26 skipped
  (previously 193 passed, 26 skipped — the 59 fewer are exactly the deleted
  tests for removed capabilities, not a regression).
- **Trade-offs / risks:** Replicating an Asness-Bender-style
  (regression-weighted), momentum-overlapping, double-sort, or
  categorical-signal paper is not currently possible until that capability
  is deliberately re-added; the removed code is preserved in git history if
  needed as a reference when re-adding.
- **References:** [src/infra/backtest_engine/steps.py](../src/infra/backtest_engine/steps.py),
  [src/infra/backtest_engine/estimators.py](../src/infra/backtest_engine/estimators.py),
  [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py),
  [src/steps/step3_codegen/registry.py](../src/steps/step3_codegen/registry.py),
  [src/infra/models/method_spec.py](../src/infra/models/method_spec.py),
  [src/steps/step1_extractor/__init__.py](../src/steps/step1_extractor/__init__.py),
  [src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py).



## 2026-07-23 — No silent default data source; a declarative catalog is the single source of truth

- **Context / problem:** Many code paths silently assumed CRSP/Compustat.
  `_normalize_mapping_entry` inferred `comp_funda` for any non-CRSP column (so an
  IBES/OptionMetrics column was silently misattributed to Compustat);
  `pick_signal_input_mode` defaulted an empty mapping to Compustat; and
  `_load_data` hardcoded the returns panel to `crsp_msf`. For a project meant to
  replicate *general* papers, a silently-wrong data source produces a
  plausible-looking but wrong backtest — the worst failure mode for an auditable
  pipeline.
- **Options considered:** (a) keep CRSP/Compustat as an example but add a
  hand-maintained "known Compustat columns" set; (b) unify the four scattered
  source fragments (`_CONCEPT_MAP`, `SIGNAL_SOURCES`, `LINK_TABLES`,
  `DataDictionary`) into one declarative catalog and drive all resolution from
  it; (c) docs-only. Also debated whether the returns universe (always CRSP for
  US-equity cross-section) is in scope.
- **Decision:** (b) — a declarative `catalog.py` is the single source of truth.
  Signal source/columns resolve via `catalog.source_of_column`/`resolve_concept`;
  the returns universe comes from a new `MethodSpec.returns_universe` →
  `catalog.RETURNS_UNIVERSES`. Nothing defaults: an unknown/unset source is
  hard-blocked at review so a human registers it in the catalog once, after
  which every future paper using it works.
- **Rationale:** The controlled-pipeline principle (empirical choices come from
  the reviewed MethodSpec, never guessed) applies to *which data source* just as
  much as to breakpoints/weighting. A registry makes "register once, reuse
  forever" explicit and keeps the human in the loop exactly at the point of
  genuine novelty (a new data source), not per paper.
- **Empirical impact:** None. Golden e2e (accruals/ball2016/mvp) are
  byte-identical; the 9 golden fixtures gained explicit `returns_universe`
  (+ ball2016 an explicit `normalized_mapping`) — explicit values only, no metric
  moved.
- **Trade-offs / risks:** The returns universe is modeled even though it is
  effectively always CRSP in the current US-equity scope — accepted, because the
  goal is generality and the field makes the (previously implicit) scope
  assumption explicit and reviewable. Registering a genuinely new source still
  requires a one-time human catalog edit (the agent cannot invent a loader for
  an unseen database) — this is intended, not a limitation.
- **References:** `src/infra/data_layer/catalog.py`,
  `src/infra/models/method_spec.py` (`_normalize_mapping_entry`,
  `unresolved_source_fields`, `returns_universe`),
  `src/steps/step2_reviewer/__init__.py` (`_check_source_mapping_resolved`,
  `_check_returns_universe`), `src/steps/step3_codegen/script_generator.py`
  (`pick_signal_input_mode`) + `registry.py` (`build_config`),
  `src/infra/backtest_engine/__init__.py` (`_load_data`),
  `tests/test_data_catalog.py`, `tests/test_no_default_source.py`, CHANGELOG
  `[Unreleased]`.

## 2026-07-22 — Loop redesign: two bounded automatic loops, one shared RepairLoop, "feed back the problem not the answer"

- **Context / problem:** The pipeline's feedback loops had accreted three
  near-duplicate copies of the same technical repair logic (in
  `Pipeline._validate_with_repair`, `Pipeline.run_from_method_spec`'s inline
  execute loop, and `DualTrackController._run_track`), while the "empirical"
  cross-stage loops from the original design were unimplemented. We wanted to
  (a) decide, from first principles, which loops this agent *should* have, and
  (b) consolidate the technical loop and add an audit trail.
- **Options considered:** Grounded the design in agent-architecture references
  (Anthropic "Building Effective Agents" — workflow vs agent, evaluator-optimizer;
  Chip Huyen "Agents" — plan/execute decoupling, reflection, human-in-the-loop
  for risky ops; Reflexion — episodic feedback memory; Self-Refine — bounded
  iterate-with-stopping-criterion). Key realization: this system is a *workflow*
  (fixed 7-step controlled path), not an autonomous agent, because its whole
  thesis is "the LLM does not decide empirical conclusions." So loops must be
  bounded, evaluator-optimizer-shaped, and must keep a hard line between
  technical fixes (safe to automate) and empirical judgments (human-gated).
- **Decision:** Exactly TWO automatic feedback loops, both bounded, plus a
  governing principle:
  1. **Technical repair loop** (steps 3↔4↔5): consolidated into one shared
     `RepairLoop` (`src/infra/repair.py`) used by all three call sites;
     `MAX_REPAIR_RETRIES=3`; every attempt recorded as a `RepairAttempt` on the
     RunRecord (audit trail persisted to the evidence store).
  2. **Review→Extractor targeted re-extraction loop** (step 2, `MAX_REEXTRACT=2`):
     when the LLM reviewer judges a high-impact field was mis-extracted
     (`remediation_mode == TARGETED_REEXTRACTION`) AND backs it with a paper
     quote, the extractor re-reads just those passages. FULL_REGENERATION,
     paper-silent fields (no citation), or an exhausted budget escalate to a
     human (`needs_manual`).
  - **Governing principle** ("feed back the problem, not the answer"): each loop
    only tells the upstream step *where* the problem is / *what* to re-check —
    the technical loop feeds MetaCoder the raw errors (its prompt forbids
    touching empirical params); the empirical loop feeds the extractor the
    reviewer's paper citation, never a value. Final values always come from the
    paper (extractor) + human-gated Review.
  - **No automatic empirical backtrack from later stages.** Step 7 (renamed
    `attribution` → `replication_diff`) reports the replication gap for a human
    to interpret; it is terminal, not a loop trigger.
- **Rationale:** The technical/empirical split is the technical embodiment of
  the project's core positioning. Auto-repairing code is safe and cheap;
  auto-adjusting empirical parameters would let the LLM decide conclusions,
  which we forbid. Using "does the reviewer have a paper citation?" as the
  re-extract-vs-human router is more reliable than evidence-tier heuristics and
  reuses the existing `EvidenceCitation` data. Consolidating three loop copies
  removes the drift that had already caused several rounds of doc/comment
  corrections.
- **Empirical impact:** None on replication numbers — the technical loop's
  behavior is preserved (golden-number e2e tests unchanged); the re-extraction
  loop only affects extraction-driven runs, which are not in the deterministic
  test set yet.
- **Trade-offs / risks:** The Review→Extractor loop depends on the LLM reviewer
  path (`review_with_llm`) actually emitting `TARGETED_REEXTRACTION`; the
  deterministic `review()` never does, so the loop is a no-op without an LLM
  client (falls back to fail-fast — acceptable). The `DualTrackController`
  per-track re-validate is now a full (not static-only) re-validate for
  consistency — a negligible per-track cost.
- **References:** `src/infra/repair.py` (`RepairLoop`, `ValidateOutcome`,
  `ExecuteOutcome`), `src/infra/models/run_record.py` (`RepairAttempt`,
  `RunRecord.repair_history`), `src/pipeline.py` (`run_full_pipeline` review
  loop, `_review`, `_build_reextract_feedback`, `MAX_REEXTRACT`),
  `src/steps/step1_extractor` (re-extraction feedback params + prompt hook),
  `src/steps/step7_replication_diff` (renamed), `docs/architecture.md` §3.1,
  `tests/test_repair_loop.py`, `tests/test_reextraction_loop.py`.

## 2026-07-22 — Reinstated the full 7-step orchestrator as `Pipeline.run_full_pipeline()` (fail-fast, no fake backtrack)

- **Context / problem:** Steps 1/2/6/7 (SemanticExtractor, ReviewGate,
  DualTrackController, AttributionLayer) had just been un-wired from
  `Pipeline` in the same-day removal of `run_factor()` (previous entry) —
  correct at the time since that method was dead and dishonest about its
  backtrack loops, but it left `Pipeline` unable to run the whole agent
  end-to-end, which is explicitly part of the intended product ("整个完整
  agent的一环"). The user also wants every step runnable in isolation for
  testing/debugging.
- **Options considered:** (1) Leave `Pipeline` at steps 3-5 only
  (`run_from_method_spec()`) and treat 1/2/6/7 as permanently
  test-callers-instantiate-directly (as `tests/test_extractor.py` and
  `tests/test_dual_track_controller.py` already do). (2) Re-add a full
  orchestrator, but reproduce the old backtrack claims (Review↔Extractor,
  Sandbox↔Review empirical, Attribution↔Review) as real implementations.
  (3) Re-add a full orchestrator that is honest about scope: chain all 7
  steps, fail-fast (no automatic retry) at whichever stage rejects the
  factor, and expose each sub-component as a `Pipeline` attribute so any
  step can be driven standalone.
- **Decision:** (3) — new method `Pipeline.run_full_pipeline()`, plus restored
  constructor wiring (`self.extractor`, `self.review_gate`, `self.controller`,
  `self.attribution`).
- **Rationale:** Option (1) doesn't satisfy "part of the whole agent" — there
  would be no single call that exercises extraction through attribution.
  Option (2) is real, non-trivial feature work (what re-extraction feedback
  looks like, when to give up, how anomaly-triggered re-review interacts with
  an already-approved spec) that deserves its own dedicated design pass, not
  a quick re-add — and doing it hastily is exactly how the previous stubs
  were born. Option (3) restores the capability the user asked for today
  (full pipeline + step-by-step testability) without repeating the previous
  mistake of claiming untested/unimplemented retry behavior. Fail-fast with a
  clear `PipelineStatus.stage`/`.error` is itself a legitimate, honest design
  — callers can inspect what failed and retry manually (e.g., re-run
  `pipeline.extractor.extract()` with edited paper text).
- **Empirical impact:** None yet — `run_full_pipeline()` is new and not yet
  exercised by any golden-number test; `run_from_method_spec()` remains the
  path all e2e tests use.
- **Trade-offs / risks:** No cross-stage backtrack means a rejected factor
  requires a human/agent to intervene and re-invoke a stage manually rather
  than the pipeline self-correcting — acceptable for now since that's exactly
  the previous "auto-retry" behavior that was never actually implemented
  anyway. Real backtrack loops remain Phase 2 scope (`docs/roadmap.md`).
- **References:** `src/pipeline.py` (`run_full_pipeline`, `PipelineStatus`),
  `docs/architecture.md` §3.1/§4, `docs/roadmap.md` Phase 1 status note,
  CHANGELOG.md 2026-07-22 entries, previous decision-log entry immediately
  below (the `run_factor()` removal this reinstates, differently).

## 2026-07-21 — Validator: execution smoke test + Step-5 repair net; C&Z stays out of the loop

- **Context / problem:** `AdversarialSandbox` (step4) was purely static (syntax,
  future-leak scan, and "does `compute_signal` exist"). It never executed the
  LLM-generated code and never checked hook functions at all, so two whole
  classes of defect slipped straight through to run time with no safety net:
  (a) a required hook function missing/misnamed — `registry.load_hooks()` then
  silently finds nothing and `_dispatch()` quietly runs the *standard* step,
  treating a non-standard factor as standard; (b) any runtime error in
  `compute_signal` or a hook (wrong column, bad schema, exception). Worse, when
  the Step-5 backtest subprocess failed, `run_from_method_spec` let the
  `RuntimeError` propagate unhandled — leaving a *registered* plugin and **no**
  RunRecord, with no repair attempt.
- **Options considered:**
  1. Static-only hook check (cheap, but can't catch runtime bugs).
  2. Execute `compute_signal` + all hooks in isolation on synthetic/real data.
  3. Whole-pipeline dry-run on a slice (runs everything, but couples step4→step5
     and hits degenerate-quantile false failures on thin slices).
  4. Compare executed output to C&Z ground-truth numbers and feed mismatches
     back to repair.
- **Decision:** A layered validator plus a run-stage net ("catch-early +
  catch-late"):
  - **Early (step4):** static hook contract check (each `PluginRecord.hooks`
    entry is defined with arity matching `HOOK_SIGNATURES`) **+** an execution
    *smoke test that runs `compute_signal` only*, in a subprocess with a
    timeout, on a small real-data slice sliced **by permno keeping full month
    history** (preserves lookback). It is **lenient**: only a raised exception
    or a hang fails it; an empty/degenerate result on a thin slice is
    *inconclusive* (a warning, not a failure); no slice ⇒ check skipped. Hooks
    are **not** executed here.
  - **Late (step5):** a backtest-subprocess failure now feeds its stderr back
    into the same bounded MetaCoder repair loop and persists a
    `status="failed"` RunRecord.
  - **C&Z ground truth is never used inside the validator or repair loop.**
- **Rationale:**
  - Executing generated code to check functional correctness (not text matching)
    is the established practice — HumanEval/Codex (arXiv:2107.03374, which also
    flags sandboxing untrusted model code), CodeT (arXiv:2207.10397, auto-built
    minimal execution checks), and Self-Debugging (arXiv:2304.05128, feeding
    execution errors back to repair — exactly our step3⇄step4 loop, now extended
    to step5). Domain difference: at generation time we have **no per-factor
    numeric ground truth** for a new signal, so the smoke test can only verify
    "runs + output schema", never values.
  - `compute_signal` is the highest-risk (free-form formula), easiest-to-drive
    (natural data input), and highest-value-to-catch-early piece; hooks have
    fixed signatures, are mostly cross-sectional, need fiddly per-hook inputs to
    execute, and would produce false failures on the low-cross-section slice a
    lookback-preserving permno slice implies. So hooks get a static contract
    check early and their runtime coverage from the guaranteed Step-5 net.
  - Leniency is *safe precisely because* Step-5 is the guaranteed net: the early
    check can never manufacture a false failure (which would waste repair budget
    or, worse, push the LLM to "fix" correct code to match a bad slice).
  - **C&Z-not-in-the-loop** upholds the project's core scientific claim: the
    replication gap must measure an *uncontaminated* pipeline. Feeding C&Z
    numbers into codegen/repair would optimize the LLM toward the answer key —
    the same leakage principle already stated for extraction
    ("post-hoc evaluation against C&Z, **not feedback**"; SignalDoc is
    evaluation-only). C&Z numeric ground truth (via OSAP / running C&Z code)
    remains available for **post-hoc** signal/portfolio evaluation only, never
    fed back.
- **Empirical impact:** None on any factor's numbers — validation gates and
  repair are upstream of the reported backtest; golden e2e numbers unchanged.
- **Trade-offs / risks:** (a) Executing LLM code is an arbitrary-code-execution
  surface (OWASP); mitigated only by subprocess + timeout, **not** a full
  filesystem/network sandbox — accepted, consistent with the existing trust
  model (the generated backtest script is already run via subprocess). A
  container/gVisor sandbox is a future hardening. (b) The smoke test won't catch
  hook runtime bugs or full-data-only failures early — deliberately delegated to
  the Step-5 net. (c) `HOOK_SIGNATURES` is now referenced from three places
  (step3 generator, step5 `load_hooks`, step4 validator); left as an import for
  now, single-source-of-truth consolidation deferred.
- **Addendum (same day):** The first implementation of the execution smoke test
  had `_check_executes` `exec()` the plugin's source directly via a hand-rolled
  runner — a second, separate "how do I run a plugin" implementation alongside
  `script_generator.generate_backtest_script()`'s template and
  `registry.load_hooks()`. Reworked so validation instead **imports the ONE
  complete standalone script Step5 will execute** (`Pipeline._build_script`,
  which calls `generate_backtest_script()` — the same function
  `_run_backtest_via_script` used, now split into `_build_script`
  build-only, no execution + `_execute_script` write-and-subprocess-run
  an already-built script). Importing (not running) the script never triggers
  its `main()` (guarded by `if __name__ == "__main__":`), so validation still
  never touches full data / the real engine — only the module-level
  `exec(compile(PLUGIN_CODE, ...))` line runs. `_validate_with_repair` now
  rebuilds the script fresh on every attempt (including after a repair)
  and validates that exact text; `run_from_method_spec` executes that same
  built dict — so "what was validated" and "what gets executed" are
  byte-identical on every attempt, never independently regenerated. This both
  removes the duplicate runner and directly serves the project's audit
  principle: there is exactly one code path from "plugin generated" to
  "backtest run", and Step4 checks precisely that path.
- **References:** [src/steps/step4_validator/__init__.py](../src/steps/step4_validator/__init__.py)
  (`_check_hooks`, `_check_executes`, `_EXECUTE_DRIVER`),
  [src/pipeline.py](../src/pipeline.py) (`_build_script`, `_execute_script`,
  `_build_validation_slice`, `_make_failed_run_record`,
  `_validate_with_repair`, run-with-repair loop in `run_from_method_spec`),
  [src/infra/models/plugin.py](../src/infra/models/plugin.py)
  (`ValidationReport.hooks_ok`/`executes_ok`),
  [tests/test_sandbox_validation.py](../tests/test_sandbox_validation.py),
  `CHANGELOG.md [Unreleased]`. Lit: arXiv:2107.03374, arXiv:2207.10397,
  arXiv:2304.05128.

## 2026-07-20 — BacktestEngine: fixed step order + standard/hook dispatch, LLM never controls the pipeline

- **Context / problem:** LLMs can plausibly write end-to-end backtest code, but
  a generated pipeline is unauditable and lets the model silently decide
  empirical choices (universe, breakpoints, lag, weighting, holding). For a
  replication study the empirical conclusions must be controlled, not model-
  authored, or the "replication gap" is uninterpretable.
- **Options considered:**
  1. Let the LLM generate the whole backtest per paper.
  2. Fixed engine skeleton; LLM generates only `compute_signal()` plus, where a
     step is non-standard, a typed hook of identical shape.
  3. Fully hard-coded engine with no extensibility.
- **Decision:** Option 2. `BacktestEngine.run_with_config()` runs a **fixed,
  ordered** chain (`load_msf → apply_delisting_returns → apply_missing_policy →
  filter_universe → merge_signal → neutralize_signal → compute_breakpoints →
  assign_portfolios → compute_returns → compute_long_short → compute_metrics`).
  Steps are pure, stateless `(df, ..., config) -> df` functions. Each step
  chooses standard / multi-dim / overlap / hook path from the reviewed
  MethodSpec; the LLM may supply a hook only when a field falls outside the
  standard set, and a hook has the same signature as the standard step it
  replaces.
- **Rationale:** Pure stateless steps make every intermediate fully traceable
  and let a hook be swapped in without special-casing. Fixing the *order*
  (while allowing per-step path selection) confines LLM influence to formula
  computation, keeping empirical structure under controlled code — the core
  claim of the framework ("let the LLM write the signal, not the conclusion").
- **Empirical impact:** Guarantees the same construction path across factors, so
  cross-factor replication-gap comparisons are apples-to-apples.
- **Trade-offs / risks:** Papers whose design genuinely departs from the fixed
  order are not expressible without extending the engine (deliberately: engine
  changes are gated, ablations go through config, per AGENTS.md hard constraints).
- **References:** [src/steps/engine/steps.py](../src/steps/engine/steps.py),
  [src/steps/engine/registry.py](../src/steps/engine/registry.py),
  [docs/architecture.md](architecture.md) §2–§3, `AGENTS.md` Hard Constraints.

## 2026-07-20 — DataLayer: lag lives in the data layer, declarative panel assembly, concept→column dictionary

- **Context / problem:** Point-in-time correctness (accounting lag) and vendor
  data plumbing (a firm's data split across CRSP msf / msenames / msedelist,
  Compustat, CCM link) are the most common sources of look-ahead bugs and of
  ambiguous paper-to-code field mappings. If plugins handled lag or ad-hoc
  merges, every generated signal could reintroduce future-leak.
- **Options considered:**
  1. Let each signal plugin apply its own lag and merge its own tables.
  2. Centralize lag + panel assembly in a shared, deterministic data layer;
     plugins only see already-lagged, pre-merged data.
- **Decision:** Option 2. `TimeAvailComputer` computes `time_avail_m` (fiscal
  period end + `lag_months`, default 6, C&Z convention) and builds a
  `[permno, time_avail_m]` SignalMasterTable that plugins read from. Raw
  WRDS-shaped sources are combined by a single declarative `assemble_panel()`
  driven by `SOURCE_SCHEMA` roles (`base` / `pit_attrs` with namedt≤date≤nameendt
  windows / delistings), and paper field names map to physical columns via
  `DataDictionary.normalize_fields()` over `_CONCEPT_MAP` (exact →
  source-detail substring → concept substring, substring only for keys ≥4 chars
  to avoid `"at"` matching inside `"compustat"`).
- **Rationale:** Placing lag in the data layer means ablating lag is a config
  change, not a plugin regeneration, and makes future-leak scannable in one
  place (AGENTS.md: "never add lag logic inside signal plugins"). Declarative
  assembly + concept map mirror C&Z's single shared SignalMasterTable and keep
  empirical data construction controlled infrastructure, never an LLM hook.
- **Empirical impact:** Default 6-month accounting lag applied uniformly; PIT
  attribute joins prevent using post-period exchange/SIC/share codes.
- **Trade-offs / risks:** The concept→column map and `SOURCE_SCHEMA` are
  hand-maintained; an unmapped field is silently omitted from the mapping (must
  be caught at Review Gate, not at backtest time). Per-paper differences (which
  sources/fields, lag, imputation) belong in the reviewed MethodSpec, not here.
- **References:** [src/infra/data_layer/__init__.py](../src/infra/data_layer/__init__.py)
  (`TimeAvailComputer`, `DataLayer`, `assemble_panel`/`SOURCE_SCHEMA`,
  `DataDictionary.normalize_fields`, `_CONCEPT_MAP`),
  `AGENTS.md` Hard Constraints, [docs/cz-reference.md](cz-reference.md).

## Simplify pipeline: remove LLM hook codegen; standardize the backtest engine

- **Context:** Advisor meeting (2026-07) — simplify the pipeline. Extraction and
  review workflows stay; the MethodSpec schema simplifies; the Meta-Coder LLM
  only writes the signal formula; the backtest engine is standardized.
- **Options considered:**
  1. Keep LLM-generated *hook* code for empirical steps outside the standard
     menu (weighting, breakpoints, missing policy, multi-leg combinations).
  2. Remove hooks entirely; the engine selects a built-in implementation from a
     fixed menu, and clamps any out-of-menu MethodSpec value to the menu
     default.
- **Decision:** Option 2. `MetaCoder.generate_plugin()` now emits only
  `compute_signal()`. `build_config()` deterministically resolves/clamps every
  empirical choice (`_clamp`), and `BacktestExecutor._dispatch()` routes only to
  the standard step functions plus their deterministic `_overlap`/`_multi`
  variants. `detect_hooks`, `load_hooks`, `PluginRecord.hooks`,
  `ValidationReport.hooks_ok`, the step4 hook-contract check, and
  `prompts/meta_coder/hook_system.md` are deleted.
- **Rationale:** The controlled-replication guarantee is stronger when *no* LLM
  output can influence portfolio construction: the LLM is confined to the
  formula, and every empirical parameter is an auditable config value drawn from
  the reviewed MethodSpec. It also removes the run-time sandbox surface for
  arbitrary hook code and shrinks the schema.
- **Empirical impact:** Factors whose paper construction fell outside the
  standard menu (e.g. a revenue-weighted scheme, a bespoke multi-leg
  combination, a >2-dimensional or non-size double sort) now run with the menu
  default rather than a bespoke hook. The ball2016 cash-based operating
  profitability e2e (a 2×3 size×profitability double sort combined as
  0.5·(robust legs) − 0.5·(weak legs)) was a hook demonstration; its golden
  numbers are tied to the removed multi-leg hook, so the test and its exclusive
  fixtures were deleted rather than re-baselined against a construction the
  paper didn't use.
- **Returns table default:** `returns_universe` now defaults to `us_equity_crsp`
  (CRSP monthly) when unset (`catalog.DEFAULT_RETURNS_UNIVERSE`); the reviewer
  warns + defaults instead of hard-blocking. This is a deliberate, scoped
  reversal of the earlier "never default a data source" rule *for the returns
  panel only* — signal-input sources still never default (multi-source catalog
  resolution + reviewer hard-block are unchanged).
- **Trade-offs / risks:** Papers needing a genuinely non-standard construction
  can no longer be replicated exactly; the replication-gap analysis (step7) is
  where that shortfall should surface, and extending the standard menu (not
  re-adding hooks) is the path to supporting a new construction.
- **References:** `src/steps/step3_codegen/` (`__init__.py`, `registry.py`),
  `src/infra/backtest_engine/__init__.py`, `src/steps/step4_validator/__init__.py`,
  `src/steps/step2_reviewer/__init__.py`, `src/infra/data_layer/catalog.py`,
  `CHANGELOG.md`.

## Schema flatten + enum pruning with load-time back-compat coercion

- **Context:** Follow-up to the hook-removal simplification — the advisor asked
  to also simplify the MethodSpec schema itself ("not too complex").
- **Decision:** Flatten portfolio-return construction (`construction_type`,
  `sorts`, `return_combination`) from the deep
  `reported_results.return_calculation.portfolio_return` nesting onto
  `PortfolioSpec`; merge `portfolio.sort`+`portfolio.breakpoints`; delete the
  dead `field_sources`/`weighting_scheme`/`filter` fields; and prune enum
  values that only fed the removed hook path.
- **Key mechanism — no data migration:** Rather than rewrite the ~26 committed
  human-labeled specs + fixtures, `MethodSpec.normalize_curated_schema` lifts
  the legacy nested construction fields onto `portfolio` at load time, and
  before-validators on `PortfolioSortSpec`/`MissingPolicy`/`ReturnCombinationSpec`/
  `PortfolioSpec` coerce pruned/removed enum values (and stray `null` legs) to
  `unspecified`/`""`. `build_config` then clamps to the menu default. So the
  canonical *schema* is simpler while every existing JSON still loads.
- **Rationale:** The loader carries the (hidden) legacy-translation complexity
  once, so the human-facing schema and the extractor's forward output are the
  simple flat shape. Migrating the labeled ground-truth set was rejected as
  high-risk churn for a reference dataset.
- **Trade-offs / risks:** `normalize_curated_schema` grows a back-compat branch;
  if the legacy nested shape is ever fully retired, that branch (and the enum
  coercions) can be deleted and the labeled specs migrated in one pass.
- **References:** `src/infra/models/method_spec.py`
  (`normalize_curated_schema` lift, `PortfolioSpec`, before-validator coercions),
  `src/steps/step3_codegen/registry.py`, `src/steps/step2_reviewer/__init__.py`,
  `CHANGELOG.md`.
