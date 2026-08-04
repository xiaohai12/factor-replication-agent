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

## 2026-08-04 (third) — Bridge signal wired into a real executable track: `BacktestExecutor.run_with_config` already accepted a precomputed signal, so this was an orchestration addition, not a data one

- **Context / problem:** The previous entry (second) built a real C&Z bridge
  SIGNAL for AssetGrowth but explicitly stopped short of running it through
  anything -- `compute_cz_bridge_signal()` returned a DataFrame nobody
  consumed. The actual research question (Phase C/D's E2 "bridge
  experiment") needs that signal run through OUR OWN engine, under the SAME
  config as the agent's own track, so any gap is attributable to the signal
  alone.
- **Decision:** Added a `precomputed_signal_path` mode to
  `generate_backtest_script`: when set, the generated script skips
  `compute_signal()` and loads that parquet directly, then proceeds through
  the IDENTICAL downstream lifecycle (universe filter, breakpoints,
  portfolios, metrics, artifact persistence) as every other track. New
  `DualTrackController._run_bridge_track` computes the bridge signal,
  writes it to a real file, and runs the script in that mode --
  deliberately NOT through the shared `RepairLoop` (there's no agent code
  to repair here). `run_from_matrix` recognizes
  `signal_input_ref: "cz_bridge"` (or `"cz_bridge:<factor_id>"`) as "run
  this as a real bridge track" instead of the previous unconditional skip.
- **A second design decision worth recording:** a bridge track's
  `code_hash` is deliberately set to a descriptive, non-agent string
  (`f"cz_bridge:{factor_id}"`), and a new `RunRecord.is_bridge_track` flag
  excludes it from Phase 0.6's "every track ran identical code"
  consistency check. Without this exclusion, EVERY bridge track would
  spuriously trip `batch_invalidated=True` (its code_hash never matches the
  frozen agent plugin's, by design), even though that's not a violation --
  a bridge track's whole point is a different signal source, which is a
  different comparison axis entirely from the config-only ablations that
  check applies to.
- **Empirical impact:** `tests/test_bridge_track_e2e.py` runs the
  AssetGrowth bridge through the REAL `Pipeline`/`BacktestRunner`/subprocess
  chain (not fakes) against the same synthetic snapshot the MVP
  golden-number test uses, and gets back a real `status="success"`
  `RunRecord` with populated metrics and a persisted signal series -- this
  is now a genuinely executable capability, verified end-to-end, not a
  theoretical one. Full suite: 363 passed, 26 skipped, zero regressions.
- **Trade-offs / risks:** Still bounded to the one registered factor
  (AssetGrowth) from the prior entry. The bridge track is not yet wired
  into `run_experiment`'s (non-matrix) `ExperimentPlan` path -- only
  `run_from_matrix` recognizes it, so a caller still using the older
  hardcoded `ExperimentPlan` entry point has no way to request a bridge
  track. `matched_comparison.matched_sample_stats` (built earlier) is still
  not automatically invoked to compare the bridge track's realized signal
  against the agent's own -- that comparison would need to be added to
  `bundle.py`'s evidence bundle or run manually against the two tracks'
  `signal.parquet` files.
- **References:** `src/steps/step3_codegen/script_generator.py`
  (`precomputed_signal_path`, `PRECOMPUTED_SIGNAL_PATH` template branch);
  `src/steps/step5_backtest_runner/__init__.py` (`build_script`);
  `src/steps/step6_dual_track_controller/__init__.py`
  (`_run_bridge_track`, `run_from_matrix`); `src/infra/models/run_record.py`
  (`is_bridge_track`); `tests/test_script_generator_bridge_mode.py`; `tests/
  test_bridge_track_wiring.py`; `tests/test_bridge_track_e2e.py`;
  `docs/multi-config-evidence-plan.md` Phase C/D.

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

## 2026-08-03 (tenth) — Phase A1/A2/B/C&D implemented at bounded scope; the real C&Z signal bridge is explicitly NOT one of them

- **Context / problem:** Asked to complete the rest of
  `docs/multi-config-evidence-plan.md` (Phases A1 through E) in one session.
  Phase E (LLM diagnosis) was already done (see the seventh entry above and
  roadmap). Phases B/C&D's actual point -- comparing our agent-generated
  signal against C&Z's OWN firm-level signal under a matched engine config
  -- requires either downloading C&Z's already-computed firm-level signal
  output or running their own `Predictors/*.py`/`Portfolios/Code/*.R` source
  (`data/CZ code/`) against real WRDS data. Neither exists as a usable
  artifact in this repo today: `data/CZ code/` is their SOURCE CODE (needs
  their own WRDS download pipeline run against it), not a precomputed
  per-factor signal file.
- **Options considered:** (a) fabricate a "bridge" using synthetic/placeholder
  data and present it as done; (b) skip Phase B/C&D entirely; (c) implement
  every piece that IS honestly buildable without that missing data adapter
  (config/evidence infrastructure, comparison math, metadata parsing) and
  state plainly what still can't be claimed done.
- **Decision:** (c). Implemented, and verified with real tests (343 passed,
  26 skipped, zero regressions):
  - Phase A1 (evidence bundle): realized-signal persistence
    (`<track>.signal.parquet`), `artifact_sha256`/`series_semantic_hash`
    (deliberately different hash kinds -- see `src/infra/hashing.py`
    docstring), an approximated `data_snapshot_hash`, and
    `EvidenceStore.save_run` accepting a real artifact bundle written
    atomically.
  - Phase A2 (declarative matrix): `experiment_spec.load_experiment_matrix`
    + `DualTrackController.run_from_matrix`, with `family`/
    `identification_level` DERIVED from the actual resolved-config diff,
    never authored in the yaml.
  - Phase B (bounded to metadata): `load_cz_reference_profile` parses
    C&Z's reported summary numbers from `SignalDoc.csv` -- explicitly NOT a
    firm-level signal loader.
  - Phase C/D (bounded to math): `matched_comparison.matched_sample_stats`
    implements the actual correlation/sign-agreement/extreme-overlap
    arithmetic the bridge experiment will need, consuming whatever two
    signal series it's given -- but nothing yet supplies a REAL C&Z series
    as one of them.
  - `PipelineStatus.comparison_path`/`.diagnosis` now surface the
    already-written `comparison.json`/`diagnosis.json` back through
    `run_full_pipeline`'s return value (roadmap: "persisted and
    pipeline-returned diagnosis report").
- **Rationale:** Every piece implemented is independently real, tested, and
  useful on its own merits (config/run identity integrity, evidence
  auditability, a validated declarative experiment format) regardless of
  whether the C&Z bridge ever gets built. None of it depends on or assumes
  data that doesn't exist. Fabricating a "bridge" against synthetic
  standins would produce a plausible-looking function call that answers
  nothing about actual replication reproducibility -- worse than admitting
  the gap, since a future reader could mistake it for a real result.
- **Empirical impact:** None -- no real bridge run exists to report a
  number from. Full test suite unaffected in behavior (343/26, all new
  tests use synthetic/fake data).
- **Trade-offs / risks:** The plan's stated "Completion Criteria" (one
  real-data factor running a versioned experiment matrix + C&Z bridge +
  deterministic diagnosis report, reproducible with the LLM off) is NOT met
  by this session's work and should not be represented as met. The
  remaining gap is squarely: (1) a real C&Z firm-level signal adapter
  (requires running/porting their pipeline or sourcing an already-computed
  export), (2) wiring that adapter's output through
  `matched_comparison.py` and a real `DualTrackController` bridge track,
  (3) an actual full run against `data/local`'s real WRDS data producing a
  `comparison.json` that includes a bridge track. Also NOT done: full
  batch-level plugin FREEZE (Phase 0.6 remains detection-only), engine-level
  intermediate-artifact persistence (breakpoints/assignments/portfolio
  returns), and Streamlit UI wiring for the new declarative matrix path.
- **References:** `src/infra/hashing.py`, `src/infra/evidence/__init__.py`,
  `src/steps/step6_dual_track_controller/experiment_spec.py`,
  `src/infra/reference/__init__.py`,
  `src/steps/step7_replication_diff/matched_comparison.py`, `src/pipeline.py`
  (`PipelineStatus`); `tests/test_hashing.py`, `tests/test_evidence_store.py`,
  `tests/test_experiment_matrix.py`, `tests/test_run_from_matrix.py`,
  `tests/test_cz_reference_profile.py`, `tests/test_matched_comparison.py`,
  `tests/test_pipeline_status_artifacts.py`; `docs/multi-config-evidence-
  plan.md` Phases A1/A2/B/C/D.

## 2026-08-03 (ninth) — Phase 0.6 batch-invalidation detects, but does not yet prevent, a track-local repair breaking the frozen-plugin guarantee

- **Context / problem:** `docs/multi-config-evidence-plan.md` D5 flagged
  that each track in `DualTrackController.run_experiment` runs its OWN
  `RepairLoop.execute_with_repair` independently. If a track's execution
  fails for a genuine technical reason and gets repaired, that track's
  plugin `code_hash` silently diverges from every other track's -- so a
  "config X differs, everything else held fixed" comparison across tracks
  is quietly false, with no record of it happening.
- **Options considered:** (a) the full Phase 0.6 design as scoped in the
  plan: freeze the plugin before the matrix starts, forbid ALL track-local
  repair during the matrix, and invalidate + re-run the entire batch from a
  newly-frozen plugin if a technical bug is found; (b) a smaller slice:
  keep per-track repair as-is (still needed -- a paper's own genuinely buggy
  formula can surface on any single track first), but detect after the fact
  when it happened and make the violation explicit and auditable instead of
  silent; (c) do nothing until the full batch-freeze/re-run infrastructure
  (Phase 0's `RunContext`, per-execution unique dirs) is ready.
- **Decision:** (b), as an explicitly partial step. Every `RunRecord` in one
  `run_experiment()` call now carries a shared `experiment_batch_id` and the
  `frozen_plugin_hash` (the plugin's `code_hash` as passed into
  `run_experiment`, before any track ran). After all tracks finish, any
  successful track whose final `code_hash` differs from
  `frozen_plugin_hash` marks `batch_invalidated=True` with a
  `batch_invalidation_reason` naming the diverged track(s) -- on EVERY
  record in the batch, not only the repaired one, since the whole batch's
  cross-track attribution is compromised, not just that track's number.
  The same flag is embedded in `comparison.json`'s new `"batch"` key so a
  human/LLM reading that file sees it too.
- **Rationale:** Full pre-matrix freeze-and-forbid-repair requires the
  matrix orchestration layer (declarative experiment loading, batch-level
  re-run-from-frozen-plugin) that Phase A2 introduces -- building it here,
  ahead of that, would mean either blocking a real technical bug fix
  mid-matrix (bad: a real formula crash on one track is exactly the kind of
  thing repair should still fix) or half-implementing batch re-run without
  the rest of the identity infrastructure it depends on. Detecting and
  flagging the violation is strictly additive, requires no new
  orchestration, and immediately prevents the worse failure mode: silently
  trusting a cross-track config-attribution claim that isn't true.
- **Empirical impact:** None on existing runs (verified: 283/26 suite, zero
  regressions). No real experiment has yet hit this path in production (no
  real WRDS run has needed a track-local repair), so no historical
  `comparison.json` needs reinterpreting.
- **Trade-offs / risks:** This does not stop the repair from happening, nor
  does it re-run the batch from a re-frozen plugin -- a human/LLM reading a
  `batch_invalidated=True` result must currently re-run the whole matrix
  manually once satisfied the repair was correct. The full freeze/forbid/
  re-run design remains Phase A2 (`docs/multi-config-evidence-plan.md`
  §4 Phase A2, "batch semantics").
- **References:** `src/steps/step6_dual_track_controller/__init__.py`
  (`run_experiment`); `src/infra/models/run_record.py`
  (`experiment_batch_id`/`frozen_plugin_hash`/`batch_invalidated`/
  `batch_invalidation_reason`); `src/steps/step5_backtest_runner/__init__.py`
  (`write_comparison_summary`'s `batch_info` param); `tests/
  test_batch_invalidation.py`; `docs/multi-config-evidence-plan.md` D5,
  Phase 0.6.

## 2026-08-03 (eighth) — Config override validation is a soft warning for no-ops, not a hard reject

- **Context / problem:** `docs/multi-config-evidence-plan.md` Phase 0.2
  (D3) flagged that `build_config`'s `config.update(overrides)` silently
  accepted anything — an unknown key, an off-menu value, or a no-op override
  (value already equal to the resolved default) all passed through
  identically. This makes any config-diff-based attribution unverifiable: a
  track named `ablation_weighting_ew` could silently run on the default
  weighting if the override key was misspelled, and the resulting "no
  effect" finding would be a false negative caused by tooling, not economics.
- **Options considered:** (a) reject all three cases identically as hard
  errors; (b) reject unknown-key/off-menu-value hard, but only warn on
  no-op; (c) leave no-op unchecked entirely.
- **Decision:** (b). Unknown override key and off-menu value for a
  menu-governed key both raise `ConfigOverrideError`. A no-op override only
  emits a `UserWarning`.
- **Rationale:** `DualTrackController`'s `HXZ_STANDARD_CONFIG` and its
  per-switch ablation map (`_get_ablation_override`) each ship a *named,
  intentional* config bundle applied uniformly across every factor,
  regardless of what that particular paper's own MethodSpec already
  resolves to. When a paper's own weighting already happens to be `vw`, the
  `standardized_hxz`/`ablation_weighting` track coinciding with it on that
  one key is a real, reportable empirical fact ("this paper's own choice
  already matches the HXZ standard on this dimension") — not a caller
  mistake to reject. Hard-rejecting the whole override dict for one
  coincidental match would have broken every real experiment run whose
  paper happens to agree with the standard on at least one field. Strict
  per-experiment no-op rejection (reject *this one* declared experiment
  because *its* declared override changed nothing) is deferred to Phase A2's
  `ExperimentSpec.expected_diff` cross-check, which operates on a single
  named experiment's intent rather than a shared multi-key config bundle.
- **Empirical impact:** None on existing runs (verified: 264/26 suite,
  zero regressions; `test_dual_track_controller.py`'s existing test now
  visibly emits the expected no-op warnings for `HXZ_STANDARD_CONFIG` keys
  that coincide with its synthetic fixture's own resolved defaults).
- **Trade-offs / risks:** A no-op override is still possible to miss if
  warnings aren't surfaced/read; Phase A2 must still add the stricter
  per-experiment check before declarative experiment matrices can rely on
  "no silent no-ops" as a guarantee rather than a warning.
- **References:** `src/steps/step3_codegen/registry.py`
  (`_validate_overrides`, `ConfigOverrideError`); `tests/
  test_config_override_validation.py`; `docs/multi-config-evidence-plan.md`
  Phase 0.2, Decision 2.

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

## 2026-08-03 (fifth) — Fixed two long-known multi-track bugs while running a real original-vs-HXZ comparison

- **Context / problem:** After manually running a 3-config smoke test for
  AssetGrowth (VW/full_sample, EW/full_sample, VW/NYSE) by giving each track a
  different `factor_id` as a workaround, the user asked why the actual
  `standardized_hxz`/C&Z tracks hadn't been run through the real
  `DualTrackController`. Attempting that surfaced two real, previously-known
  bugs that had never been exercised end-to-end before:
  1. `BacktestRunner.build_script()` names its output script/CSV/metrics files
     using `spec.factor_id` ALONE. `DualTrackController.run_experiment()`
     calls `build_script()` once per track (`original_method`,
     `standardized_hxz`, `ablation_*`) for the SAME factor, so every track
     after the first silently overwrote the previous track's on-disk file.
     Only the in-memory `RunRecord.metrics` per track was ever correct; no
     test caught this because `test_dual_track_controller.py` uses a
     `FakeRunner` that never touches the filesystem.
  2. `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` was `[10, 20, ..., 90]` (a
     percentile-cutpoint list) while `BacktestExecutor.compute_breakpoints`
     does `int(config.get("breakpoint_quantiles", 10))` — `int()` on a list
     raises `TypeError`. This was already documented (2026-08-02 entry,
     `docs/roadmap.md` Immediate Correctness Work #1) but never actually
     fixed, so the `standardized_hxz` track has never been runnable against
     real data until now.
- **Decision:** Fixed both, since they directly blocked the real ask (run the
  actual HXZ track, not a hand-rolled `factor_id` workaround):
  1. Added an optional `track_name: str | None = None` parameter to
     `BacktestRunner.build_script()`. When supplied, the script/output file
     stem becomes `{factor_id}__{track_name}` instead of just `{factor_id}`;
     omitted (`None`), it's the original single-track filename (backward
     compatible with every other caller — `Pipeline.run_from_method_spec`,
     `backend/routers/*`, `RepairLoop`'s own single-track use). Threaded
     `track_name` through `RepairLoop.build_validate_repair`/
     `execute_with_repair` (both call `build_script()` on every rebuild
     attempt, including mid-repair) and `DualTrackController._run_track`
     (which already has `track_name` available, just wasn't passing it
     anywhere).
  2. Changed `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` to the integer `10`
     (a decile sort — the percentile list's 9 cutpoints implied 10 groups
     anyway), matching the engine's real contract.
- **Empirical impact:** Ran the real `DualTrackController.run_experiment()`
  (not manual overrides) for AssetGrowth against real `data/local` WRDS data,
  `ExperimentPlan(run_original=True, run_standardized=True)`, one frozen/
  validated plugin shared by both tracks:
  - `original_method`: mean_return=0.4199%, t_stat=2.594 (VW, full_sample
    breakpoints, annual June formation, as-of-aligned per the fourth entry
    above).
  - `standardized_hxz`: mean_return=0.3141%, t_stat=1.023 (VW, NYSE
    breakpoints, monthly rebalance).
  Both tracks completed successfully and wrote to distinct files
  (`asset_growth_us_equity_vw__original_method.*` /
  `asset_growth_us_equity_vw__standardized_hxz.*`), confirming the file
  collision is fixed. Full suite: 213 passed, 26 skipped (unchanged; added a
  targeted assertion in `test_dual_track_controller.py`'s existing multi-track
  test that each `build_script` call carries the matching `track_name`).
- **Trade-offs / risks:** This does not yet implement the fuller Phase 0
  run-identity design (unique `execution_id`/content hashes/full evidence
  persistence) from the 2026-08-02 entry — it's the minimal fix that makes
  today's `DualTrackController` usable without artifact collisions, not the
  final run-identity system. `{factor_id}__{track_name}` filenames are
  human-readable but not guaranteed unique across concurrent/overlapping
  ablation runs with the same track name; that's still Phase 0 scope.
- **References:** `src/steps/step5_backtest_runner/__init__.py`
  (`build_script`), `src/infra/repair.py` (`build_validate_repair`,
  `execute_with_repair`), `src/steps/step6_dual_track_controller/__init__.py`
  (`_run_track`, `HXZ_STANDARD_CONFIG`), `tests/test_dual_track_controller.py`,
  `tests/test_repair_loop.py`, `docs/roadmap.md`, CHANGELOG.md [Unreleased].

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

## 2026-08-03 (second) — Review Gate must treat `resolution_log` as authoritative, or paper-silent fields can never leave `blocked_fields`

- **Context / problem:** Continuing the same end-to-end dry run (this time
  against `AssetGrowth` / Cooper, Gulen & Schill 2008, a paper whose main
  strategy IS a supported `characteristic_sort`), Review Gate blocked 3
  genuinely paper-silent, high-impact fields (`portfolio.weighting` — paper
  reports both EW and VW without designating a main target;
  `portfolio.long_leg`/`portfolio.return_combination` — paper's tables show
  a 10-minus-1 spread while the executable direction requires an explicit
  low-minus-high convention). Resolved all 3 via
  `resolution.apply_decisions`/`build_decision` (the exact mechanism
  `scripts/resolve_review_blocks.py` uses), grounded in the project's own
  `SENSIBLE_DEFAULTS` convention and the paper's own curated reference spec
  (`tests/fixtures/method_specs/cooper_gulen_schill_2008_asset_growth.
  resolved.methodspec.json`, which made the identical choices). Per
  `resolve_review_blocks.py`'s own printed next-step instructions, re-ran
  Review Gate on the resolved spec — and all 3 fields were immediately
  re-blocked, with the SAME "paper doesn't state this" reasoning. Traced the
  cause: `MethodSpec.resolution_log` (the only place a human's decision +
  reasoning is recorded) was never read by either review path (`review()`
  rule-based, or `review_with_llm()`/`_raw_to_review_result`). Since "the
  paper is silent on this" is permanently true once established, a reviewer
  that only asks that question loops on the field forever — no number of
  human resolutions can ever produce an `approved` spec for a paper with any
  genuinely silent high-impact field (which is common; EW vs VW ties are a
  frequent example across many papers, not particular to this one).
- **Options considered:** (1) leave review as-is and have a human bypass
  Review Gate entirely for resolved specs (rejected — throws away the
  review gate's other checks, e.g. schema/format/source-mapping validation,
  for the whole spec just to unblock 3 fields); (2) make `apply_decisions`
  set `codegen_ready=true` directly, skipping re-review altogether (rejected
  — same problem, loses the safety net for any NEW issue introduced by the
  resolution itself, e.g. a typo'd value); (3) teach both review paths to
  recognize `resolution_log` as authoritative for a field whose current
  value still matches the recorded decision, and stop re-flagging it for
  the identical paper-silent reasoning — with one narrow override so this
  can't become a rubber stamp: a NEW, cited paper quote that actually
  contradicts the resolution can still re-block it.
- **Decision:** Chose (3). Added `_resolved_by_human(spec, field_path,
  current_value)` (`src/steps/step2_reviewer/__init__.py`): true when
  `spec.resolution_log` has an entry for that exact field_path whose
  `new_value` still equals the field's current value (i.e. nobody silently
  changed it again since). Wired into all 3 deterministic blocking checks
  (`_check_ambiguous_fields`, `_check_silent_high_impact_fields`,
  `_check_unsupported_fields`) — a match downgrades `needs_human_
  confirmation` to `auto_approve_with_flag` and adds a `warnings` entry
  instead of `blocked_fields`. For the LLM path, added the same rule to
  `_LLM_REVIEW_CONTRACT` and `prompts/review_gate/methodspec_audit.md`
  (§1.2.1), PLUS a code-level backstop in `_raw_to_review_result` that
  doesn't rely on the LLM obeying the prompt: any `blocked_fields` entry
  matching `_resolved_by_human` gets downgraded UNLESS its `field_notes`
  entry carries at least one new evidence citation (a real quote) — an
  evidence-less re-block can only mean "still just paper-silent," which is
  exactly the loop this closes; a re-block WITH a genuine new citation is
  still respected (the narrow override).
- **Empirical impact:** Re-ran `review_with_llm` on the exact same resolved
  `AssetGrowth` spec (same paper text, same LLM) after the fix: the 3
  previously-reblocked fields now show as `warnings`
  ("already human-resolved in resolution_log... should not be re-blocked on
  that basis alone") instead of `blocked_fields`; one genuinely new,
  not-yet-resolved field (`portfolio.sort.breakpoint_source`, never
  touched by any resolution) still correctly blocks. Full suite: 209
  passed, 26 skipped (unchanged from baseline — pure additive logic, no
  existing test exercised this path since no prior test constructed a
  resolution_log-backed re-review scenario).
- **Trade-offs / risks:** The LLM-path override (new evidence can still
  re-block) trusts the LLM to only attach evidence for a genuine new
  citation, not to game the override by attaching an empty-ish/irrelevant
  evidence object — acceptable given the LLM is already trusted for every
  other paper-evidence judgment in this pipeline, and `_resolved_by_human`
  is a hard backstop for the (more common) empty-evidence case regardless.
  Did not extend `resolution.ResolutionLogEntry` to carry the original
  paper evidence that led to the human's decision (would let a future
  reviewer judge the human's reasoning quality, not just whether the value
  changed) — deferred as a possible future enhancement, not needed to close
  this specific loop.
- **References:** `src/steps/step2_reviewer/__init__.py`
  (`_resolved_by_human`, `_check_ambiguous_fields`,
  `_check_silent_high_impact_fields`, `_check_unsupported_fields`,
  `_raw_to_review_result`, `_LLM_REVIEW_CONTRACT`),
  `prompts/review_gate/methodspec_audit.md` §1.2.1,
  `src/steps/step2_reviewer/resolution.py` (`apply_decisions`,
  `resolution_log`), `scripts/resolve_review_blocks.py`, CHANGELOG.md
  [Unreleased].

## 2026-08-03 — Review Gate's LLM audit prompt had drifted from the real (flat) MethodSpec schema

- **Context / problem:** Ran a manual, full `Pipeline.run_full_pipeline()` dry
  run against real WRDS data (`data/local`, registered as an ad hoc
  `local_data_v1` snapshot) for a brand-new paper/factor
  (`AB1998_ETR`, Abarbanell & Bushee 1998's effective-tax-rate signal) to
  exercise every step end-to-end. Extraction correctly produced a spec with an
  empty `signal.formula.expression` (the paper's exact Table 1 formulas are
  literally absent from the extractable PDF text — "*Insert Table 1 here*" is
  the only trace — a genuine paper-silent case, not a bug). But
  `ReviewGate.review_with_llm`'s blocked-field output was confusing:
  `blocked_fields = ['signal.formula.expression', 'sample.return_sample',
  'universe.winsorize_bounds']` and the `issues` text complained about
  missing `paper.*`/`formula_convention.*`/`input_return.*` sections. None of
  `sample.return_sample`, `universe.winsorize_bounds` (unaliased),
  `formula_convention`, or `input_return` exist on the current flat
  `MethodSpec` model (`src/infra/models/method_spec.py`) — the reviewer is
  handed `spec.model_dump()` of that exact flat model, but its system prompt
  (`prompts/review_gate/methodspec_audit.md`) still described the older
  richer *curated* nested schema (`paper.*`/`sample.*`/`universe.*`/
  `formula_convention.*`/`input_return.*`, `calculation_steps`/
  `formula.inputs`, `robustness_or_secondary_specs`/`extensions`/
  `annotator_notes`, `portfolio.sorts` plural) that only the *extractor*
  prompt (`prompts/extractor/methodspec_extractor.md`) still legitimately
  emits (and `MethodSpec.normalize_curated_schema` flattens on the way in —
  see the 2026-07 MethodSpec schema notes). `resolve_review_blocks.py`
  already has a `PATH_ALIASES` mechanism for exactly two known cases
  (`universe.missing_policy.action`, `universe.winsorize_bounds`), but a
  freshly-invented path like `sample.return_sample` has no alias and would
  silently write into a dead nested dict a human "resolving" it would never
  notice was discarded.
- **Options considered:** (1) leave the prompt as-is and rely on
  `PATH_ALIASES` to patch every future invented path reactively (rejected —
  purely reactive, guaranteed to keep recurring per-paper since the prompt
  itself keeps re-inventing new unaliased paths); (2) make the reviewer
  ignore/re-derive schema shape from the JSON it's given instead of a written
  contract (rejected — the whole point of a written parser-contract section
  is to give the LLM a stable, auditable vocabulary; removing it weakens the
  audit); (3) fix the prompt itself to describe the real flat schema.
- **Decision:** Chose (3). Rewrote `prompts/review_gate/methodspec_audit.md`
  §4.1 (paper/target scope), §4.2 (signal — no `calculation_steps`/
  `formula.inputs`/`extensions.formula_constants`, only `signal.formula.
  {expression,paper_expression}` + top-level `signal.required_fields[]`),
  §4.4 (sample — flat `sample_start_year`/`sample_end_year`, no month-level
  `return_sample`), §4.6 (universe — `portfolio.universe`/
  `portfolio.universe_filters[]`/`signal.missing_policy.*`, not a `universe.*`
  object), §5.1 (Required stable fields — replaced the entire invented list
  with the real flat locations), §5.3 (formula executability — checked against
  `signal.required_fields[]`, not phantom `calculation_steps`), plus stray
  `portfolio.sorts` (plural, doesn't exist — it's `portfolio.sort`) and
  `robustness_or_secondary_specs`/`extensions`/`annotator_notes`/
  `sample_coverage_notes` mentions (none exist; the only real escape hatches
  are `ambiguous_fields`/`unsupported_fields`).
- **Empirical impact:** Re-ran `review_with_llm` on the exact same
  already-extracted `AB1998_ETR` spec after the fix (no re-extraction) —
  `blocked_fields` changed from the invented
  `['signal.formula.expression', 'sample.return_sample',
  'universe.winsorize_bounds']` to the correct
  `['factor_id', 'signal.formula.expression']`, both real dotted paths on the
  actual model. `requires_human=True` in both cases (correctly — the paper's
  Table 1 truly isn't extractable), so this fix doesn't change the pipeline's
  terminal disposition for THIS spec, but does change what a human resolving
  future blocked specs would be told to look at.
- **Trade-offs / risks:** Did not touch the extractor prompt (intentionally —
  its curated schema is the documented, live, tested contract that
  `normalize_curated_schema` flattens; see the MethodSpec schema notes) or add
  new `PATH_ALIASES` entries speculatively (avoided over-engineering for
  paths the corrected prompt should no longer produce). AB1998's 9 fundamental
  signals (AQ/AR/CAPX/EQ/ETR/GM/INV/LF/SA) remain unbacktestable from this PDF
  specifically because Table 1 (all 9 formulas) was never included in the
  extractable text — a paper-data-availability gap, not something further
  pipeline changes can fix.
- **References:** `prompts/review_gate/methodspec_audit.md`,
  `src/steps/step2_reviewer/__init__.py` (`review_with_llm`, `_LLM_REVIEW_CONTRACT`,
  `HIGH_IMPACT_FIELDS`), `src/steps/step2_reviewer/resolution.py`
  (`PATH_ALIASES`), `src/infra/models/method_spec.py`
  (`MethodSpec.normalize_curated_schema`), CHANGELOG.md [Unreleased].

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

## 2026-08-02 — Run-identity, per-key config validation, provenance, and the LLM-classification boundary for multi-config experiments

- **Context / problem:** Before running one frozen signal under many configs, a
  review found that the naive first cut (`run_id` built in `make_run_record`)
  would harden a run-identity API that later phases must overturn, and that
  several defects make multi-config attribution untrustworthy: config overrides
  bypass menu validation, a `lag` override is a no-op on the signal, per-track
  repair can change `code_hash`, the generated script is non-hermetic, and the
  evidence store persists only metadata. A concrete existing bug:
  `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` is a percentile list while the
  engine calls `int(...)`; no test catches it because the dual-track test uses a
  fake runner. (All verified against code.)
- **Options considered:** (1) implement multi-config persistence directly
  (unique paths in `make_run_record`); (2) a binary portfolio-only/signal-input
  config taxonomy; (3) a per-key `ConfigKeySpec` stage taxonomy with
  resolved-diff-driven comparability, run identity allocated before build, full
  runtime provenance, semantic vs artifact hashing, and an explanation-only LLM
  layer.
- **Decision:** Chose (3). Run identity = per-execution unique `execution_id`
  with content hashes stored as fields (audit-friendly), plus matrix/batch
  identity so a frozen-input group can be invalidated atomically. Config
  validity = per-key stage taxonomy; comparability and identification level come
  from the resolved diff-set, not from a whole-config label. Reproducibility =
  runtime provenance (commit/dirty, engine source hash, versions, FF file hash)
  because the script imports engine code at run time. Signal equality = a
  canonicalized `series_semantic_hash`, not a Parquet byte hash, captured at a
  defined stage (post-canonicalization, pre-portfolio). LLM = explanation-only,
  each claim bound to a claim-type→evidence-schema, classifications are
  `llm_assisted_proposal` and never written back.
- **Rationale:** These are the minimal invariants that make config-vs-signal
  attribution and cross-factor conclusions auditable and LLM-independent. The
  binary taxonomy could not express factorial or cross-stage diffs and would have
  masked the `breakpoint_quantiles` bug.
- **Empirical impact:** None yet — plan/docs only; no run numbers changed.
- **Trade-offs / risks:** Heavier evidence model (intermediate artifacts,
  provenance); mitigated by a configurable evidence level (full for pilot/bridge,
  lean for bulk). The `breakpoint_quantiles` fix + real-runner smoke test are
  called out as immediate, plan-independent work.
- **References:** `docs/multi-config-evidence-plan.md`,
  `docs/replication-diagnosis-design.md` Phases A–E, `src/steps/step6_dual_track_controller/__init__.py`,
  `src/steps/step3_codegen/registry.py`, `src/steps/step3_codegen/script_generator.py`,
  `src/infra/repair.py`, `src/infra/evidence/__init__.py`, `src/pipeline.py`,
  CHANGELOG `[Unreleased]`.

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

## 2026-08-02 — Keep reviewer field-defaults and the standardized-track config separate; cite the standard's provenance

- **Context / problem:** `HXZ_STANDARD_CONFIG` (step6 standardized track) was an
  uncited hardcoded constant, and step2's `SENSIBLE_DEFAULTS` held an
  overlapping-looking copy of the same conventions. Their `rebalance` values
  disagree (`monthly` vs `annual`), which looked like drift and raised the
  question "where do these numbers come from?".
- **Options considered:** (1) merge the two into one shared constant and force a
  single rebalance value; (2) keep them separate but add per-field provenance
  and document why they differ.
- **Decision:** Chose (2). The two are different concepts with different key
  namespaces: `SENSIBLE_DEFAULTS` (dotted MethodSpec paths) fills a
  paper-SILENT field with its field-level convention to keep `original_method`
  faithful to the paper; `HXZ_STANDARD_CONFIG` (engine-config keys) deliberately
  OVERRIDES the paper to force a uniform house standard for cross-factor
  comparison. Merging would conflate "faithful default" with "standardized
  override" and break the diagnosis design.
- **Rationale:** The `annual` vs `monthly` difference is the correct answer to
  two different questions (unspecified-accounting-factor default vs HXZ
  standardized protocol), not a bug. Auditable replication requires the
  standardized "house standard" to have a citable provenance.
- **Empirical impact:** None — documentation and comments only; no config value
  changed.
- **Trade-offs / risks:** Verified that `accounting_lag_months=6` is a
  Fama-French (1992) convention, not HXZ (which matches most-recent quarterly
  earnings monthly). The "HXZ_STANDARD" name is therefore approximate for that
  field; logged a TODO to either realign to HXZ or rename the track to a neutral
  `standardized`.
- **References:** `src/steps/step6_dual_track_controller/__init__.py`,
  `src/steps/step2_reviewer/__init__.py`, `docs/cz-reference.md` §7,
  CHANGELOG `[Unreleased]`.

## 2026-08-01 — Standardize the validated project environment on Python 3.11

- **Context / problem:** The existing `.venv` was created with Python 3.14.
  The official `openassetpricing==0.0.2` client imported and loaded SignalDoc
  there, but `dl_port('op', ..., ['AssetGrowth'])` caused a native segmentation
  fault. The identical portfolio and firm-signal requests succeeded in an
  isolated Python 3.11 environment. The package documents testing on Python
  3.10, while the project's scientific dependencies are mature on 3.11.
- **Options considered:** (1) keep Python 3.14 and bypass the client; (2) run
  only C&Z downloads in a separate environment; (3) standardize the whole
  project development/test environment on Python 3.11 while keeping the C&Z
  client evaluation-only. Chose (3), gated on golden and full-suite tests.
- **Decision:** Add `.python-version` = 3.11 and an `evaluation` optional extra
  for `openassetpricing==0.0.2`. Recreate the virtual environment rather than
  attempting to replace an interpreter inside an existing venv. Preserve the
  Python 3.14 environment as a backup until Python 3.11 validation passes.
- **Rationale:** One validated interpreter reduces cross-environment drift and
  avoids a demonstrated native crash. Python 3.11 has stable wheels for the
  project's pandas/pyarrow/scientific stack and requires no source syntax
  changes. Keeping the client optional avoids imposing WRDS/Polars dependencies
  on core pipeline users.
- **Empirical impact:** None observed. Both golden E2E tests passed unchanged;
  the focused migration gate passed 19 tests, and the full Python 3.11 suite
  passed 200 tests with 26 expected skips. The AssetGrowth OP portfolio API
  also completed successfully (9,570 rows), while the Python 3.14 call had
  crashed natively.
- **Trade-offs / risks:** Dependency resolution selects pandas 2.2.x when the
  evaluation extra is installed, rather than the unpinned pandas 3.x version
  previously present. Tests must establish compatibility. Python 3.14 is no
  longer the validated development interpreter even though the source metadata
  still permits future versions.
- **References:** `.python-version`, `pyproject.toml`, CHANGELOG `[Unreleased]`,
  `docs/replication-diagnosis-design.md`.

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

## 2026-08-01 — DataLayer refactor Round 1 P4: one signal-master path (B-group deleted)

- **Context / problem:** Two parallel mechanisms built the signal-master table:
  the snapshot-based B-group (`CCMLinker` + `TimeAvailComputer` +
  `get_signal_master_table`) — which the mvp/accruals GOLDEN NUMBERS ran through
  — and the declarative D-group (`assemble_signal_master_table`, migrated to
  `sources.py` in P3). Plan §5 (gated) merges them into one.
- **Options considered:** (a) keep both; (b) merge, gated on a byte-identical
  golden-number check with a fallback to split P4 into its own round.
  Chose (b) — but FIRST ran a read-only equivalence check to quantify the risk.
- **Read-only check (before any code change):** B-group vs D-group produced
  BYTE-IDENTICAL `[permno, time_avail_m, *cols]` on both golden fixtures
  (mvp/asset_growth, accruals). The only behavioral divergence: `CCMLinker`
  drops a Compustat row whose linked `permno` is absent from the CRSP panel;
  `link_to_permno` keeps it (irrelevant to the fixtures — every permno is in CRSP).
- **Decision:** Deleted the B-group; the declarative loader is the single path.
  The generated script's "compustat" mode now calls the same
  `assemble_signal_master_table_from_sources` as "multi_source" (the modes
  differ only in returns-panel loading). **Ghost-permno rule: KEEP** (user-
  approved) — a permno with accounting data but no CRSP presence is retained
  (CRSP-centric identity; the returns inner-join drops it downstream), rather
  than replicating CCMLinker's pre-emptive drop.
- **Rationale:** One implementation of "resolve gvkey→permno + stamp
  time_avail_m", no drift risk between the in-process and generated paths, and
  the registry/declarative loader is the single source of truth end to end.
- **Empirical impact:** None — golden numbers byte-identical, verified by both
  the read-only check and the subprocess-run mvp/accruals e2e.
- **Trade-offs / risks:** Snapshot signal tables renamed to the real WRDS
  layout (`comp_funda.parquet` + `ccm_lnkhist.parquet`, CCM keyed on `lpermno`);
  every snapshot writer (e2e fixtures, `backend/state.py`, `app.py`,
  `scripts/build_synthetic_data.py`) + `generate_backtest_script`'s signature
  updated in lockstep. `SnapshotManager`/`DataLayer.snapshots` kept (orthogonal:
  reproducible-run registry + UI picker + path resolution).
- **References:** `src/infra/data_layer/__init__.py`,
  `src/steps/step3_codegen/script_generator.py`,
  `src/steps/step5_backtest_runner/__init__.py`, `src/pipeline.py`, `app.py`,
  `tests/test_mvp_e2e.py`, `tests/test_accruals_e2e.py`, `plan.md` §5/P4,
  CHANGELOG (Round 1 P4 entry).

## 2026-08-01 — DataLayer refactor Round 1 P3: registry is the single source of truth; catalog derived

- **Context / problem:** The signal-input metadata lived as hand-written dicts
  in `catalog.py` (`DATA_CATALOG` / `LINK_TABLES`) while the loading behavior
  lived as free functions in `data_layer/__init__.py` (the "D-group") — two
  places to keep in sync, and a second signal-assembly path parallel to the
  older snapshot one (plan.md §3).
- **Options considered:** (a) keep catalog as the source of truth and have
  `sources.py` read from it; (b) make the DataSource registry the source of
  truth and DERIVE the catalog views from it. Chose (b) per plan §2② — one
  place declares "what data exists / how it links", everything else is a view.
- **Decision:** Registered `comp_funda`/`comp_fundq`/`ibes_statsumu` as
  declarative `SourceSpec`s + `crsp_msf` as a `CrspSignalSource` (CRSP's dual
  signal role, §2④), plus `ccm`/`ibes_crsp_link` as `LinkTableSpec`s; moved the
  link/load/assemble logic into `sources.py`. `catalog.DATA_CATALOG` /
  `LINK_TABLES` / `RETURNS_UNIVERSES` are now derived from the registry,
  byte-identical to the old literals, so `source_of_column`/`resolve_concept`/
  `signal_sources`/`concept_map` (and therefore MethodSpec + the reviewer) are
  untouched (plan §6b). Raw dedup filters became declarative
  `SourceSpec.raw_filters` instead of bespoke filter functions.
- **Rationale:** Adding a Compustat-like source is now one `SourceSpec` entry
  (the §0 litmus test) with no scattered dict edits; the "no silent default
  source" rule is enforced by the same fail-loud registry lookups.
- **Empirical impact:** None — the migrated loading logic is exercised
  unchanged by `test_signal_master_multisource` on synthetic WRDS-shaped data,
  and mvp/accruals golden numbers are byte-identical.
- **Trade-offs / risks:** CRSP is now two registered objects (`crsp` returns
  universe + `crsp_msf` signal source) sharing the CIZ assembler — intentional,
  makes the dual role explicit. The old snapshot-based signal-master path
  (B-group: CCMLinker/TimeAvailComputer/get_signal_master_table) still coexists;
  merging it is the gated P4.
- **References:** `src/infra/data_layer/sources.py`,
  `src/infra/data_layer/catalog.py`, `src/infra/data_layer/__init__.py`,
  `tests/test_data_sources.py`, `tests/test_signal_master_multisource.py`,
  `plan.md` §2/§3/§4/P3, CHANGELOG (Round 1 P3 entry).

## 2026-08-01 — DataLayer refactor Round 1 P2: CRSP returns via a DataSource registry

- **Context / problem:** `BacktestExecutor.load_data` called the free assembler
  `build_crsp_monthly_panel_ciz` directly, and returns/signal data entered the
  pipeline through separate ad-hoc paths (see `plan.md` §1). Round 1 introduces a
  CRSP-centric `DataSource` registry + `DataLayer` facade as the single source of
  truth for "what data exists / how it links to permno".
- **Options considered:** (a) config-driven `SourceSpec` for CRSP too;
  (b) a bespoke `DataSource` subclass for CRSP. Chose (b) — CRSP needs multi-file
  assembly (`CRSP_STOCK_MONTH.csv` + `CRSP_DELISTING.csv`), derived exchcd/shrcd
  approximations, and a delisting merge, which `plan.md` §2③ explicitly carves out
  as the "CRSP-shaped special" case for a custom class.
- **Decision:** Migrated the CIZ returns backbone into `sources.py` as
  `CrspReturnsUniverse` (+ the moved assembler/daily-loader/`_ciz_shrcd`/CIZ
  constants). Added a returns sub-registry and a `DataLayer.load_returns*` facade;
  `load_data` now resolves the panel through the registry. Kept the two public
  assemblers re-exported from `sources.py` so the generated multi_source script,
  `_load_source_frame`, and tests are unchanged.
- **Rationale:** Establishes the one-directional `sources <- catalog <- __init__`
  layering and the "no silent default panel" fail-loud contract without touching
  the signal-assembly paths (deferred to P3/P4) — keeping golden numbers stable.
- **Empirical impact:** None — mvp/accruals golden-number e2e byte-identical; the
  panel-building code is a pure relocation, not a behavior change.
- **Trade-offs / risks:** CRSP's signal role is still served by the re-exported
  `build_crsp_monthly_panel_ciz` (D-group `_load_source_frame`); it becomes a
  formally-registered CRSP `SignalSource` in P3. Transient duplication of the
  `us_equity_crsp` alias between `catalog.RETURNS_UNIVERSES` and
  `CrspReturnsUniverse.universe_aliases` until catalog is made registry-derived in P3.
- **References:** `src/infra/data_layer/sources.py`,
  `src/infra/data_layer/__init__.py`, `src/infra/backtest_engine/__init__.py`,
  `tests/test_data_sources.py`, `plan.md` §2/§4/P2, CHANGELOG (Round 1 P2 entry).

## 2026-07-31 — Deleted `load_msf`/`load_daily_msf` and the "panel" returns_layout

- **Context / problem:** After removing the legacy 3-table CRSP assembler
  (previous entry, same date), the user asked to also delete `load_msf`/
  `load_daily_msf` ("还是删了msf或者daily msf吧"). These are format-agnostic
  utilities (read an already-pre-flattened parquet, regardless of whether it
  originated from legacy CRSP or CIZ) backing the `"panel"` returns_layout —
  NOT specific to the legacy vs. CIZ distinction, so I flagged before
  deleting that this would break the `"panel"` layout and
  `tests/test_daily_frequency.py`'s `TestLoadDailyMsf` (3 tests). User
  confirmed to proceed anyway.
- **Approach:** Rather than fully hand-tracing every consumer up front
  (as done for the previous, much larger legacy-assembler removal), deleted
  the two methods + the `"panel"` layout, then ran the full test suite to
  empirically discover the exact breakage — cheaper and more reliable than
  guessing for a change of this size, and the test suite is comprehensive
  enough to trust for this.
- **What broke (only 6 tests, not the large cascade the "panel" layout's
  other consumers implied):**
  - `tests/test_daily_frequency.py::TestLoadDailyMsf` (all 3 tests) — deleted,
    directly exercised the removed `load_daily_msf`.
  - `tests/test_no_default_source.py::test_load_data_does_not_fall_back_to_crsp_for_a_different_returns_table`
    — deleted, tested the removed `<data_path>/local/msf.parquet` legacy
    file-location shim.
  - `tests/test_no_default_source.py::test_build_config_sets_returns_table_from_universe`
    / `test_build_config_defaults_returns_table_to_crsp_when_universe_unset` —
    updated to assert `returns_layout == "crsp_ciz"` instead of `"panel"`
    (since `catalog.RETURNS_UNIVERSES["us_equity_crsp"]` was repointed at
    `crsp_ciz`, consolidating away the now-redundant separate
    `"us_equity_crsp_ciz"` entry).
- **What did NOT break (verified, not assumed):** `tests/test_mvp_e2e.py`,
  `tests/test_accruals_e2e.py`, `tests/test_backend_api.py`, `app.py`,
  `backend/state.py` — all pass. Root cause: the ACTUAL backtest execution for
  these paths runs through `BacktestRunner.execute()`, which executes a
  GENERATED STANDALONE SCRIPT via subprocess (see
  `src/steps/step3_codegen/script_generator.py`). That generated script has
  its OWN independent `load_msf()` function baked into its template — it
  never calls `BacktestExecutor.load_data()`'s file-dispatch logic at all.
  The `<data_path>/local/msf.parquet` file these e2e tests write was
  apparently only ever consumed by `BacktestExecutor.load_data()`'s in-process
  legacy shim (now removed), which nothing in the actual golden-number
  execution path was relying on — the shim (and its supporting comment in
  `tests/test_mvp_e2e.py`) had become stale/vestigial.
- **Rationale:** Confirms `load_msf`/`load_daily_msf`/the `"panel"` layout
  were narrower-scoped than they first appeared — removing them completes
  the standardization on the real WRDS CIZ format for anything that goes
  through `BacktestExecutor.load_data()` directly, while the
  generated-script execution path (which most e2e tests and the demo
  actually exercise) was never touched by any of this.
- **Empirical impact:** None on any MethodSpec/backtest numbers. Full suite:
  186 passed (down from 190 — 4 tests removed, 2 updated), 26 skipped.
- **Trade-offs / risks:** Any FUTURE code that wants to hand
  `BacktestExecutor.load_data()` a pre-flattened parquet by file path (rather
  than an in-memory `data=` DataFrame or the real CIZ export) has no
  supported mechanism anymore — would need a new, explicitly-scoped addition
  if that need arises.
- **References:** `src/infra/backtest_engine/__init__.py`,
  `src/infra/data_layer/catalog.py`, `src/infra/data_layer/__init__.py`,
  `src/steps/step3_codegen/registry.py`, `tests/test_daily_frequency.py`,
  `tests/test_no_default_source.py`; CHANGELOG.md [Unreleased] same date.

## 2026-07-31 — Deleted the legacy 3-table CRSP assembler; standardized on real WRDS CIZ format

- **Context / problem:** After building real-WRDS-CIZ support (2026-07-30)
  alongside the pre-existing legacy 3-table CRSP assembler
  (`crsp_msf`/`crsp_msenames`/`crsp_msedelist`, joined via `SOURCE_SCHEMA`/
  `assemble_panel()`), the user asked to drop the old format entirely and
  standardize everything on the real sample-file-derived (CIZ) format
  ("旧格式就不要了吧，全都按照sample文件为准").
- **Options considered:**
  1. Keep both formats side by side indefinitely (status quo from
     2026-07-30).
  2. Delete the legacy assembler and its `"crsp_raw"` returns_layout, and
     delete/rework every test that depends on it.
  3. Delete the legacy assembler but ALSO migrate its downstream synthetic
     test fixtures (`data/synthetic_data/test_papers_v1/`) to a CIZ-shaped
     equivalent, preserving full test coverage.
- **Decision:** Option 2, per explicit user confirmation after being shown
  the blast radius (a full audit was run first — see below — since this is
  the kind of destructive, hard-to-reverse, cross-cutting change that
  warrants explicit confirmation before touching anything). User also
  explicitly confirmed deleting the dependent tests rather than pursuing
  option 3's larger rework.
- **Audit performed before touching anything** (to avoid guessing at blast
  radius): confirmed that `scripts/build_synthetic_data.py`,
  `tests/synthetic_data/asset_growth_synthetic_data.py`/
  `accruals_synthetic_data.py`, `tests/test_mvp_e2e.py`,
  `tests/test_accruals_e2e.py`, `tests/test_backend_api.py`, `app.py`,
  `backend/state.py`, and `Pipeline.run_from_method_spec()` are all
  INDEPENDENT of the legacy 3-table assembler — they all pass a single
  pre-flattened DataFrame directly (via the `"panel"` returns_layout, or
  `data=`/`DataLayer` snapshot passthrough), which reads a pre-flattened
  parquet regardless of its internal provenance and was NOT touched. Only
  `tests/test_crsp_raw_panel.py` (entirely), one test in
  `tests/test_signal_master_multisource.py` (`test_apply_pit_attrs_
  fallback_for_coverage_gap`, calling `assemble_panel()` directly), and one
  more in the same file (`test_generated_multi_source_script_runs`, which
  executes a generated multi-source script that transitively called the
  legacy assembler through `script_generator.py`'s template) actually
  depended on it.
- **What was removed:**
  - `src/infra/data_layer/__init__.py`: `SOURCE_SCHEMA`, `_DERIVE_OPS`,
    `_load_base`, `_apply_pit_attrs`, `_apply_fold_last`, `assemble_panel`,
    `build_crsp_monthly_panel` (the legacy one — `build_crsp_monthly_panel_ciz`
    is now the only CRSP raw-tables assembler and was NOT renamed, to avoid
    an unnecessary rename churn across already-working CIZ code).
  - `BacktestExecutor.load_data()`'s `"crsp_raw"` returns_layout branch +
    its `build_crsp_monthly_panel` import (kept `"panel"` and `"crsp_ciz"`).
  - `catalog.RETURNS_UNIVERSES["us_equity_crsp_raw"]`.
  - `_load_source_frame`'s special-cased `crsp_msf` branch: now calls
    `build_crsp_monthly_panel_ciz(d / "local")` instead (matching where the
    real CIZ export actually lives, same convention as the other raw-CSV
    fallbacks).
  - `script_generator.py`'s generated multi-source backtest script template:
    now calls `build_crsp_monthly_panel_ciz(SIGNAL_DATA_DIR)` instead — a
    generated script's `SIGNAL_DATA_DIR` is now expected to contain a real
    WRDS CIZ export (`CRSP_STOCK_MONTH.csv`/`CRSP_DELISTING.csv`), not the
    legacy 3-table split.
  - `tests/test_crsp_raw_panel.py` (deleted entirely, all 5 tests) and two
    tests in `tests/test_signal_master_multisource.py` (see above).
- **Deliberately NOT removed / left as-is:**
  - `scripts/build_test_papers_synthetic_data.py` — still generates
    comp_funda/comp_fundq/ccm_lnkhist/ibes_crsp_link/ibes_statsumu fixtures
    under `data/synthetic_data/test_papers_v1/` that
    `test_signal_master_multisource.py`'s remaining tests use (those tests
    never touched the legacy CRSP assembler — they exercise the generic
    `_load_source_frame`/`link_to_permno` signal-input path against
    Compustat/IBES parquet fixtures, independent of how the returns panel is
    built). The same script's `crsp_msf`/`crsp_msenames`/`crsp_msedelist`/
    `crsp_dsf`/`crsp_msedist` outputs are now simply unused, harmless
    leftover files — not worth a separate script rewrite for this pass.
  - The `"panel"` returns_layout / `DEFAULT_RETURNS_UNIVERSE="us_equity_crsp"`
    — this is a GENERIC "read one pre-flattened parquet" mechanism, unrelated
    to whether the underlying data was ever in the legacy 3-table shape; it's
    what the MVP/accruals e2e tests and the Streamlit demo actually use, and
    was never part of "the old format" being removed.
- **Empirical impact:** None on any MethodSpec/backtest numbers (deletion +
  test removal only). Full suite: 190 passed (down from 197 — 7 tests
  removed), 26 skipped, unchanged otherwise.
- **Trade-offs / risks:** Any future MethodSpec/generated script that needs a
  multi-source signal + CRSP returns panel now REQUIRES the real WRDS CIZ
  export to be present (no more legacy-format fallback for that combination).
  `data/synthetic_data/test_papers_v1/`'s CRSP-shaped parquet files
  (crsp_msf/crsp_msenames/crsp_msedelist/crsp_dsf/crsp_msedist) are now dead
  weight on disk (gitignored, harmless) unless `build_test_papers_synthetic_data.py`
  is revisited later to stop generating them.
- **References:** `src/infra/data_layer/__init__.py`,
  `src/infra/backtest_engine/__init__.py`,
  `src/infra/data_layer/catalog.py`,
  `src/steps/step3_codegen/script_generator.py`,
  `tests/test_signal_master_multisource.py`; CHANGELOG.md [Unreleased] same
  date; 2026-07-30 entries above (original CIZ-format introduction).

## 2026-07-31 — Explicit WRDS date format after finding CCM's `LINKENDDT="E"` sentinel

- **Context / problem:** Asked to validate the data layer against the
  curated `data/local/samples/` (see the 2026-07-30 alignment work below).
  Running the real Compustat/CCM/IBES loaders surfaced a `UserWarning:
  Could not infer format... falling back to dateutil` on `CRSP_COMPUSTAT_LINK.csv`.
  Root cause: `LINKENDDT` is not always a date string — an open (still
  active) link is coded as the literal string `"E"`. Mixed real-dates +
  `"E"` defeats pandas' fast columnar date-format inference, forcing a slow
  per-row `dateutil` parse. The same unformatted `pd.to_datetime(...,
  errors="coerce")` pattern was used everywhere else a date column from a
  real WRDS file gets parsed (comp_funda/comp_fundq's `datadate`, IBES
  summary's `statpers`, CRSP CIZ's `DlyCalDt`/`DelistingDt`, 13F's `rdate`,
  IBES detail/actual's date columns, CRSP index's `mthcaldt`/`dlycaldt`,
  liquidity factors' `date`) — same latent perf/warning issue at production
  scale (comp_fundq alone is ~1.9M rows over a 4GB file).
- **Options considered:**
  1. Leave as-is — `errors="coerce"` already makes `"E"` become `NaT`, which
     `link_to_permno`'s `.fillna(pd.Timestamp.max)` correctly treats as
     "open-ended" anyway, so behavior is already correct.
  2. Add an explicit `format="%Y-%m-%d"` everywhere a KNOWN real WRDS file's
     date column is parsed.
  3. Add the explicit format to the GENERIC, source-agnostic `link_to_permno`/
     `_load_source_frame` date-parsing calls too (which run for every
     source, including hypothetical future non-WRDS ones).
- **Decision:** Option 2. Did NOT do option 3: `link_to_permno`/
  `_load_source_frame`'s date parsing must stay format-agnostic since they're
  shared infrastructure for ANY future registered source, not just
  WRDS-shaped ones — hardcoding `"%Y-%m-%d"` there would silently turn every
  row of a differently-formatted future source's dates into `NaT` (and then
  zero rows downstream), exactly the "silent zero rows" class of bug this
  project already fixed once for `patents_nber` (2026-07-25 entry). Instead,
  `_read_raw_source_csv` (which IS scoped to a known real file) now
  pre-parses the source's own `date` column with the explicit format before
  handing off to the generic pipeline, so the later generic call becomes a
  cheap no-op (already-datetime input) rather than needing its own format
  hardcoded.
- **Rationale:** This is a correctness-preserving performance/robustness fix,
  not a behavior change — confirmed `"E"` still resolves to `NaT` ->
  `Timestamp.max` (open-ended) exactly as before. Measured ~18% faster on the
  real `comp_fundq` load (68.1s -> 56.3s) as a side benefit.
- **Also found (documented, not fixed — not a bug):** a delisted stock's CIZ
  monthly row for its OWN delisting month often has `PrimaryExch`/
  `SecurityType`/`SecuritySubType`/`SICCD` blanked out entirely (confirmed on
  permno 10000's 1987-06 delisting row: `PrimaryExch="X"`,
  `SecurityType=NaN`, `SecuritySubType="UNK"`, `SICCD=0`, `MthRet=0.0` — the
  real delisting return comes from `CRSP_DELISTING.csv`'s `DelRet`
  separately). This means `exchcd=0`/`shrcd=0` for that one month even
  though the stock was ordinary common stock every prior month — it won't
  pass a `shrcd in [10, 11]` or `breakpoint_source="nyse"` filter for its
  final month. This is genuinely how the CIZ export reports it (not an
  adapter bug), and differs from the legacy 3-table path where
  `_apply_pit_attrs`'s window-based join would carry forward the last known
  attrs. Documented in `build_crsp_monthly_panel_ciz`'s module comment;
  revisit only if this is ever shown to matter for a specific replication
  (e.g. a paper whose universe filter would wrongly exclude a stock's exact
  delisting month).
- **Empirical impact:** None on any MethodSpec/backtest numbers — pure
  parsing-performance fix, values unchanged.
- **Trade-offs / risks:** None identified; `errors="coerce"` remains the
  safety net for any date value that still doesn't match `"%Y-%m-%d"`.
- **References:** `src/infra/data_layer/__init__.py`
  (`_read_raw_link_table_csv`, `_read_raw_source_csv`,
  `build_crsp_monthly_panel_ciz`, `load_daily_msf_ciz`,
  `load_crsp_index_factors`, `load_liquidity_factors`,
  `load_institutional_ownership_13f`, `load_ibes_recommendation_detail`,
  `load_ibes_unadjusted_actual`); CHANGELOG.md [Unreleased] same date.

## 2026-07-31 — Removed catalog.py entries with no real data behind them (optionm_vsurf, optionm_crsp_link, tr_13f, patents_nber)

- **Context / problem:** After the 2026-07-30 real-data work, the user asked
  for `catalog.py` to only reflect data sources actually backed by real data
  in this project, not speculative/test-only registrations. Auditing every
  `DATA_CATALOG`/`LINK_TABLES` entry against `data/local/`'s real files found
  four with no real backing: `optionm_vsurf`/`optionm_crsp_link` (no
  OptionMetrics data file exists anywhere in the project) and `patents_nber`
  (no NBER patents data exists). `tr_13f` was a subtler case: it's registered
  `{"key": "permno", "link": None, ...}` — i.e. assumed to be ALREADY
  permno-keyed — but the real 13F export we now have (`data/local/13F.csv`)
  has no permno column at all; its own key is `cusip`. So `tr_13f`'s
  registered shape doesn't match how the one real 13F file we have actually
  joins.
- **Options considered:**
  1. Leave all four registered (they exercise genuinely useful *generic*
     catalog/join-framework behavior in tests, independent of whether real
     data backs them).
  2. Remove all four from `catalog.py`, and either drop or rework the tests
     that depended on them reading from the real module-level `DATA_CATALOG`.
  3. Fix `tr_13f`'s shape to match the real cusip-keyed 13F file (register a
     new `crsp_cusip` link table) instead of removing it.
- **Decision:** Option 2 — removed all four. For `tr_13f` specifically,
  did NOT pursue option 3 in this pass: the real 13F loader
  (`data_layer.load_institutional_ownership_13f()`, added 2026-07-30) already
  documents that its CUSIP match is NOT point-in-time (uses each CUSIP's most
  recent observed permno, no validity window) — registering it in the
  declarative catalog would imply a level of correctness (point-in-time
  join, like CCM/IBES-CRSP link) it doesn't actually have yet. Revisit once a
  real point-in-time CUSIP history replaces that best-effort match.
- **Rationale:** A catalog entry is effectively a claim "this is how this
  real data source joins" — `optionm_vsurf`/`optionm_crsp_link`/
  `patents_nber` made that claim about data that doesn't exist at all, and
  `tr_13f` made a claim about join shape that's simply wrong for the one real
  13F file this project has. Keeping them registered contradicts the
  project's own "never silently guess/misrepresent a data source" principle
  (the same principle behind `catalog.source_of_column`/`resolve_concept`
  returning `(None, None)` rather than a guess, and the reviewer's hard-block
  on unregistered sources). The tests that exercised these entries
  (`test_link_to_permno_no_row_explosion[optionm_vsurf]`,
  `test_link_to_permno_noop_for_permno_keyed_source`,
  `test_load_source_frame_raises_for_source_without_date_column`) were
  reworked to preserve their actual behavioral coverage — the generic
  "link=None -> no-op" case now uses `crsp_msf` (a real, still-registered
  permno-keyed source) instead of the removed `tr_13f`; the "join.date=None
  must fail loud" regression test (originally added for the real
  `patents_nber` bug, see the 2026-07-25 entry above) now monkeypatches a
  temporary fake source into `SIGNAL_SOURCES` for the duration of that one
  test, so the regression guard isn't lost even though `patents_nber` itself
  is gone.
- **Empirical impact:** None — pure data-plumbing/registry cleanup, no
  MethodSpec/backtest numbers affected.
- **Trade-offs / risks:** Re-adding any of these four requires a fresh
  catalog entry once real data exists for it (OptionMetrics, NBER patents)
  or once `tr_13f`'s join is redesigned around a real point-in-time CUSIP
  history. `scripts/build_test_papers_synthetic_data.py` still builds
  synthetic `optionm_vsurf.parquet`/`optionm_crsp_link.parquet`/
  `tr_13f.parquet`/`patents_nber.parquet` fixtures — left in place
  (harmless, unused parquet files) since touching that script was out of
  scope for this catalog-only cleanup.
- **References:** `src/infra/data_layer/catalog.py` (removed entries, with
  a comment pointing back here); `tests/test_data_catalog.py`;
  `tests/test_signal_master_multisource.py`; CHANGELOG.md [Unreleased] same
  date; 2026-07-30 entry below (original `tr_13f` best-effort loader
  decision) and 2026-07-25 entry (original `patents_nber` fail-loud fix).

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

## 2026-07-28 — Fix (fifth pass): fail-loud on missing filter field; annual formation-month consistency; VW excludes (not fabricates) missing prior-month ME

- **Context / problem:** A fifth-pass review surfaced three remaining
  faithfulness gaps in `apply_signal_holding_period` / `compute_portfolio_returns`:
  1. **Silent skip of a stated universe filter.** Both filter sites
     (`apply_universe_filters` on the returns panel, and the formation
     cross-section loop) did `if field not in columns: continue`. A MethodSpec
     that explicitly requires e.g. `shrcd in [10,11]` would then keep every row
     when the panel lacked `shrcd` — running a DIFFERENT universe than the paper
     stated while still reporting success.
  2. **No check that an annual signal forms in its declared month.** Nothing
     verified that an annual-rebalanced signal's formation cohorts matched the
     reviewed `formation_month`, so the engine and the spec could silently
     disagree on the formation calendar.
  3. **VW fabricated missing prior-month ME.** When `me_{t-1}` was unavailable,
     `_attach_lagged_me` fell back to same-month ME — reintroducing the exact
     same-month look-ahead the fourth pass removed, silently and only for the
     rows where the lag was missing.
- **Options considered:**
  - Fix 1: (a) keep skipping, (b) warn, (c) **raise**. Chose raise — column
    availability can't be validated at spec-review time (different returns
    universes have different columns), so run time is the only place it's known,
    and a stated restriction must never be silently dropped.
  - Fix 2: (a) enforce a full formation calendar for all frequencies, (b)
    **annual-only, explicit-formation_month-only validation**, (c) do nothing.
    Chose (b). Rejected (a) because quarterly/monthly cohort-month sets are
    convention-dependent (which 4 months? fiscal vs calendar quarters?) and the
    engine must not invent a calendar the spec didn't state; and a DEFAULTED
    `formation_month` (=6) is not authoritative over the signal's own cohorts,
    so only an EXPLICIT `formation_month` triggers the check (new
    `formation_month_explicit` config flag from `registry.build_config`).
  - Fix 3: (a) error out, (b) **exclude the row (weight 0) + report missing
    fraction**, (c) keep same-month fallback. Chose (b). Rejected (a) because a
    sample's first held month legitimately can lack a prior-month row for some
    stocks; a hard error would be too brittle. Rejected (c) as the actual bug.
- **Decision:** Both filter sites raise `ValueError` naming the field and the
  available columns. `apply_signal_holding_period` calls a new
  `_validate_annual_formation_month` that raises when an annual + explicit-
  `formation_month` signal has any cohort in a different month. VW now drops
  rows with NaN/non-positive `me_lag` from the weighted average and surfaces
  `vw_lagged_me_missing_frac` (None under EW) in `compute_metrics`;
  `_attach_lagged_me` no longer fills NaN with same-month ME.
- **Empirical impact:** No change to the golden e2e numbers. The single-stock-
  per-decile MVP/accruals/backend fixtures needed a June-1998 formation-month
  row added to the synthetic CRSP panel (`asset_growth_synthetic_data.build_crsp_msf`)
  so that `me_{t-1}` resolves for the first held month under the new exclude
  rule — real CRSP panels always have that row; the fixture simply omitted it.
  With the row present, `me_lag` is defined for every held month and the 24-month
  long-short series is byte-identical. The stale cached snapshot under
  `data/synthetic_data/mvp_v1/` (gitignored) was regenerated.
- **Trade-offs / risks:** Fix 2 does not police quarterly/monthly calendars
  (deliberately — see above); a future paper needing quarterly formation-month
  discipline would require a spec-declared calendar, not an engine-invented one.
  Fix 1 will now hard-fail a spec that references an unregistered column, which
  is the intended behavior but shifts the burden to catalog/spec correctness.
- **References:** `src/infra/backtest_engine/__init__.py`
  (`apply_universe_filters`, `apply_signal_holding_period`,
  `_validate_annual_formation_month`, `compute_portfolio_returns`,
  `_attach_lagged_me`, `compute_metrics`), `src/steps/step3_codegen/registry.py`
  (`formation_month_explicit`), `tests/test_round5_faithfulness_fixes.py`,
  `tests/test_research_design.py::TestApplyUniverseFilters::test_unknown_field_raises_not_skipped`,
  `tests/synthetic_data/asset_growth_synthetic_data.py`. This is the FIFTH
  same-day fix pass on `apply_signal_holding_period`.

## 2026-07-28 — Fix (fourth pass): eligibility propagated to assignment; VW switched to prior-month ME; `formation_month` range-validated

- **Context / problem:** A fourth-pass review found three more issues, one of
  them a direct self-inconsistency introduced by the third-pass point-in-time
  fix:
  1. **Eligibility didn't reach the actual portfolio.** The third pass filtered
     `self.formation` (the breakpoint population) by point-in-time
     universe-filter eligibility, but `self.merged` (the population
     `assign_portfolios`/`compute_portfolio_returns` actually use) was built
     BEFORE that filtering and never got the same exclusion. Result: a stock
     ineligible at its own formation month was correctly excluded from
     DEFINING the breakpoints, yet still sorted BY those breakpoints and
     contributing returns. Reproduced: a stock with `shrcd=99` at formation
     (excluded) but `shrcd=10` (and valid returns) in its held months
     appeared in `formation=[1,2,3]` but `assigned=[1,2,3,4]`.
  2. **VW used same-month ME.** `compute_portfolio_returns` weighted month-`t`
     returns by month-`t` end-of-month market equity (`|prc_t|*shrout_t`),
     which already reflects the very return being weighted -- a subtle
     look-ahead (two stocks +10%/-10% from equal starting caps net to 0%
     under prior-month weights but a spurious +1% under same-month weights).
  3. **`formation_month` had no range check.** An explicit `formation_month=13`
     was approved with `paper_faithful=True` -- the reviewer's silent-field
     check only tested `is None`, and neither the schema nor `build_config`
     range-validates it.
- **Options considered:** For eligibility, filter `merged` by the same
  `(permno, cohort)` exclusion computed for `formation` (chosen) vs.
  recomputing eligibility independently on `merged` (rejected -- duplicates
  the point-in-time logic and risks the two drifting). For VW, three ME-timing
  schemes: (a) prior-month-end ME `me_{t-1}` (chosen -- the standard monthly
  VW convention, removes the look-ahead); (b) formation-date ME held fixed
  across the holding period (a valid "formation weight, no drift" scheme, but
  a bigger behavioral change and less common); (c) leave same-month (rejected
  -- it's the look-ahead). For `formation_month`, add a range check to the
  reviewer (chosen) vs. also ENGINE-enforcing `signal.yyyymm % 100 ==
  formation_month` (REJECTED -- that would wrongly reject every
  monthly/quarterly-rebalanced signal, whose cohorts legitimately appear in
  many calendar months; formation_month=6 is an annual-June default, not a
  universal constraint).
- **Decision:** (1) In `apply_signal_holding_period`, compute the excluded
  `(permno, cohort)` pairs (positive evidence: a formation-month row exists
  AND fails the filter) once and remove them from BOTH `self.formation` and
  `self.merged` (via an anti-join), so the exclusion reaches assignment and
  returns. (2) Added `BacktestExecutor._attach_lagged_me`: looks up each held
  row's `me_{t-1}` from `self._pre_missing_policy_data` (the fullest available
  `[permno, yyyymm, me]` series, so the prior month is found even when it's
  the formation month rather than a held row); VW now weights by `me_lag`.
  Where a prior-month `me` genuinely can't be found (panel never recorded that
  stock-month -- common in synthetic/test panels), `me_lag` falls back to the
  row's own current-month `me` (a documented data-completeness fallback that
  reintroduces the same-month dependency for ONLY those unresolved rows rather
  than dropping the stock). (3) Added `_is_invalid_formation_month` to
  `step2_reviewer` (mirroring `_is_invalid_ls_quantile`) and used it in
  `_check_silent_high_impact_fields` so an unset OR out-of-1..12
  `formation_month` blocks approval.
- **Rationale:** A stock's eligibility to be sorted/returned must be the SAME
  as its eligibility to define the sort -- decoupling them (as the third-pass
  fix accidentally did) is a logical contradiction, not a methodology choice.
  Prior-month VW is the standard convention precisely because same-month
  weighting double-counts the current return. The reviewer-only
  `formation_month` range check catches the genuinely-invalid case (13)
  without the false-rejection risk of a rigid engine calendar constraint.
- **Empirical impact:** VW change is a NO-OP for both golden-number e2e tests
  (`test_mvp_e2e`, `test_accruals_e2e`) because they use single-stock-per-
  decile designs, where a single-stock portfolio's VW return equals the
  stock's own return regardless of ME timing (verified: full suite 182 passed,
  up from 175, no golden-number changes). VW numbers change only for
  multi-stock portfolios, exactly where the look-ahead lived. Eligibility
  propagation changes numbers only when `universe_filters` excludes a stock
  that has a formation-month row failing the filter AND survives into the
  held-month panel. New `tests/test_eligibility_and_vw_weighting.py` covers
  both (excluded stock absent from formation/merged/assignment; the
  +10%/-10% two-stock VW example netting to 0% under prior-month weights;
  single-stock VW = own return). New `formation_month` reviewer tests (13/0
  blocked, 6 not) added to `tests/test_reviewer_silent_defaults.py`.
- **Trade-offs / risks:** The VW prior-month-ME fallback to current-month ME
  (when no prior-month row exists) still carries the same-month look-ahead for
  those specific unresolved rows -- an honestly-documented data-completeness
  limitation for panels that omit a stock's prior-month record (real CRSP
  rarely does). `formation_month` is validated only at review time, not
  enforced against actual signal cohorts in the engine (deliberately -- see
  the rejected option). This is the FOURTH fix pass on `apply_signal_holding_period`
  in one day; the recurring theme has been that "which population does X" was
  under-specified across `formation`/`merged`/assignment -- future edits
  should keep those three populations' relationship explicit.
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (`apply_signal_holding_period`, `compute_portfolio_returns`, `_attach_lagged_me`),
  [src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py)
  (`_is_invalid_formation_month`, `_check_silent_high_impact_fields`),
  [tests/test_eligibility_and_vw_weighting.py](../tests/test_eligibility_and_vw_weighting.py),
  [tests/test_reviewer_silent_defaults.py](../tests/test_reviewer_silent_defaults.py).

## 2026-07-28 — Fix (third pass): formation eligibility/exchcd made point-in-time and cohort-specific; explicit invalid `ls_quantile` now blocked

- **Context / problem:** A third-pass external review of the same-day fixes
  above (universe-filter eligibility + `ls_quantile` clamping) found the
  second-pass fix was itself still wrong in two ways, plus a residual gap
  in the `ls_quantile` reviewer check:
  1. **Eligibility was permno-wide, not cohort-specific.** The second-pass
     fix computed `excluded_permnos = seen_permnos - eligible_permnos`
     across a permno's ENTIRE history in `self._pre_missing_policy_data` --
     so a stock that passed `universe_filters` at ANY point in its history
     (even an unrelated month, e.g. before or after the cohort in question)
     was never excluded, even from a DIFFERENT cohort where it actually
     fails the filter at formation. Reproduced: a stock with `shrcd=10` at
     an unrelated month but `shrcd=99` at its own formation/held months for
     a specific cohort still entered that cohort's `full_sample`
     breakpoint (median 2.5 instead of the correct 2.0).
  2. **`exchcd` for `breakpoint_source="nyse"` was still read from `df`**
     (the post-`filter_universe` panel used for the returns join), not the
     pre-missing-policy snapshot -- and, independently, `df` NEVER contains
     a row at a cohort's own formation month at all under this engine's
     held-months-only convention (held months start at `h=1`, strictly
     after formation). Reproducing this end-to-end (nothing in the existing
     test suite exercised `breakpoint_source="nyse"` through the full
     pipeline) showed `exchcd` came back `NaN` for EVERY stock, not just
     ones with a missing formation-return -- `compute_breakpoints` crashed
     with an opaque pandas `ValueError` (0-column quantile frame) rather
     than computing a wrong number. This was a more severe defect than
     described: `breakpoint_source="nyse"` was effectively non-functional
     after the same-day fix, not merely biased for an edge case.
  3. **`ls_quantile` reviewer check only caught `None`,** not an explicit
     invalid value (e.g. `-1`, `1`, `0.9`) -- `registry._resolve_ls_quantile`
     (previous entry) silently clamps those to the standard 10-group
     default at `build_config` time, but `ReviewGate` still approved the
     spec (with `paper_faithful=True`) despite the explicit value being
     numerically nonsensical for a long-short sort.
- **Options considered (eligibility/exchcd):** (a) patch the permno-wide set
  to be per-(permno, cohort) by intersecting with each cohort's own
  held-month window -- rejected: still not truly point-in-time, and
  doesn't fix the `exchcd`-from-`df` half of the bug; (b) require an exact
  formation-month row in `df` (post-`filter_universe`) -- rejected: `df`
  never has one, so this would evaluate to "no data" for every cohort in
  every existing test fixture; (c) look up BOTH `universe_filters` fields
  and `exchcd` from `self._pre_missing_policy_data` (already captured for
  the eligibility fix), joined POINT-IN-TIME on `(permno, cohort)` where
  `cohort` is that signal row's own formation `yyyymm` -- a permno/cohort
  pair with a matching formation-month row gets real attributes and is
  excluded only if it fails the filter there; a pair with NO matching row
  (the panel never recorded that exact stock-month -- common in this
  repo's synthetic/test panels, though real WRDS CRSP panels normally do
  have one) is left unclassified (`exchcd` `NaN`, not excluded by
  `universe_filters` -- no positive evidence either way).
- **Decision:** (c). Rewrote the `self.formation` construction in
  `apply_signal_holding_period`: build `attrs_at_formation` from
  `self._pre_missing_policy_data` (falling back to `df`) with `yyyymm`
  renamed to `cohort` and deduplicated to one row per `(permno, cohort)`;
  left-merge it onto `formation` with a `_has_formation_row` indicator.
  `universe_filters` are evaluated with `_apply_filter_op` directly (not
  `apply_universe_filters`, to keep the per-row `passes` mask alongside the
  indicator) and a row is dropped only when `has_formation_row AND NOT
  passes` -- i.e. exclude only with positive, point-in-time evidence.
  `exchcd` rides along in the same merge, so it's now the formation-month's
  own point-in-time value (or `NaN` if genuinely unavailable) instead of an
  arbitrary later held-month's value. Added a `bp_df.empty` guard in
  `compute_breakpoints` that raises a clear `ValueError` (distinguishing
  "no stock resolved to NYSE at formation" from "no signal at all") instead
  of letting an empty quantile frame crash with a confusing pandas
  `ValueError` on the column rename. For `ls_quantile`, added module-level
  `_is_invalid_ls_quantile` to `step2_reviewer` (deliberately NOT imported
  from `registry._resolve_ls_quantile`, keeping the reviewer independent of
  the codegen module) mirroring the same validity rule, and used it (instead
  of a bare `is None` check) in `_check_silent_high_impact_fields`'s
  `ls_quantile` entry.
- **Rationale:** Formation-time attributes must be evaluated AT formation
  time for the SPECIFIC cohort in question, not aggregated across a stock's
  whole history (a stock's eligibility/exchange listing can genuinely change
  over time, and conflating cohorts would let a later/earlier month's
  attributes leak into a decision that should only depend on what was true
  at THAT formation). The permissive "no data = no exclusion" fallback keeps
  the original 2026-07-28 look-ahead fix intact for panels that don't record
  every formation month explicitly (this repo's synthetic test panels), while
  still being exact for panels that do (real CRSP data). Keeping
  `_is_invalid_ls_quantile` independent of `registry._resolve_ls_quantile`
  (rather than importing it) avoids adding a `step2_reviewer -> step3_codegen`
  dependency in the wrong direction of the pipeline.
- **Empirical impact:** No-op for the full existing suite (175 passed, up
  from 167, no failures) -- no existing fixture exercises `universe_filters`
  with a time-varying attribute or `breakpoint_source="nyse"` end-to-end.
  Rewrote `tests/test_formation_universe_eligibility.py` to include
  formation-month rows in its panels (matching the point-in-time semantics)
  and added two new test classes: cohort-specificity (a stock ineligible
  ONLY at its own formation, still correctly excluded) and "no formation-row
  means no exclusion" (explicit coverage of the permissive fallback). Added
  `TestNyseExchcdIsPointInTimeAndDecoupledFromReturnAvailability` -- the
  first test in this repo to exercise `breakpoint_source="nyse"`
  end-to-end through `apply_signal_holding_period`/`compute_breakpoints`.
  Added 5 new `ReviewGate` tests confirming `ls_quantile=-1`/`1`/`0.9` are
  now blocked and `10`/`0.1` are not.
- **Trade-offs / risks:** The "no formation-month row -> don't exclude,
  exchcd stays NaN" fallback means `breakpoint_source="nyse"` can still
  silently exclude fewer/more stocks than a true point-in-time CRSP
  classification would, for any panel that (like this repo's synthetic test
  data) doesn't record a row at every stock's exact formation month -- this
  is now an honestly-documented data-completeness limitation, not a silent
  wrong number, but it means synthetic/test panels used for `nyse`
  breakpoints should include a formation-month row per signal to get exact
  behavior. This is the third fix pass on this exact ~40 lines of code in
  one day; future changes to `apply_signal_holding_period` should be
  reviewed with particular care given this history.
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (`apply_signal_holding_period`, `compute_breakpoints`),
  [src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py)
  (`_is_invalid_ls_quantile`, `_check_silent_high_impact_fields`),
  [tests/test_formation_universe_eligibility.py](../tests/test_formation_universe_eligibility.py),
  [tests/test_reviewer_silent_defaults.py](../tests/test_reviewer_silent_defaults.py).

## 2026-07-28 — Fix: `self.formation` didn't inherit universe-filter eligibility (second-pass regression from the same-day look-ahead fix), plus `ls_quantile` clamping

- **Context / problem:** A follow-up external review of the same-day
  look-ahead fix (previous entry below) found that fix had itself introduced
  a new leak: `self.formation` was built directly from the raw `signal`
  DataFrame (`signal.rename(columns={"yyyymm": "cohort"})`), which is never
  run through `filter_universe` at all — that step only ever touches the
  returns panel `self.data`, not the separate `signal` object. So a stock
  explicitly excluded by `config["universe_filters"]` (e.g. wrong share
  class) still contributed its signal to its cohort's `full_sample`
  breakpoint. Reproduction: formation signals `[1,2,3,4]`, permno 4 fails a
  `shrcd in [10,11]` filter (present with `shrcd=99` in every month it
  appears) — `filter_universe` correctly drops permno 4 from `self.data`,
  but `self.formation` still contained it, giving a breakpoint of 2.5
  instead of the correct 2.0 (median of the 3 eligible signals). The same
  review also flagged that `registry._resolve_ls_quantile` (then inlined in
  `build_config`) never validated `ls_quantile`: `None` correctly defaults
  to a decile sort, but `-1` resolved to `-1` "groups", and `1.5`/`3.3` were
  silently truncated by a bare `int()` to `1`/`3` — all of which reach
  `compute_breakpoints`/`assign_portfolios` unvalidated (a genuinely
  negative/zero group count crashes deep inside the engine with an opaque
  `IndexError` on `bins[0]` rather than failing at config-build time).
- **Options considered (universe eligibility):** (a) restrict `self.formation`
  to permnos present in `self.merged` (the post-return-join panel) —
  rejected outright, since that's exactly the population the SAME-DAY
  look-ahead fix moved away from (it would reintroduce future-return-
  availability dependence); (b) require a formation-month row to exist in
  the (already `filter_universe`-restricted) returns panel `df` and inner-
  join on it — rejected: this repo's returns-panel convention (all existing
  test fixtures, and `apply_signal_holding_period`'s own held-month
  expansion starting at `h=1`, i.e. strictly AFTER formation) never
  populates a row at the formation month itself, so this would empty out
  `self.formation` for every existing formation-locked test; (c) compute a
  set of permnos with POSITIVE evidence of failing `universe_filters` (seen
  somewhere in the panel, but excluded by `apply_universe_filters`) using
  the panel state BEFORE `apply_missing_policy` drops missing-return rows,
  and only remove those specific permnos from `self.formation` — a permno
  with ZERO rows anywhere (no evidence either way — e.g. delisted before
  any data was ever recorded) is left alone, preserving the same-day
  look-ahead fix.
- **Decision:** (c) for universe eligibility. `apply_missing_policy` now
  snapshots its input into `self._pre_missing_policy_data` before dropping
  missing-return rows. `apply_signal_holding_period` computes
  `excluded_permnos = (permnos seen in that pre-drop snapshot) - (permnos
  that pass config["universe_filters"] there)` and removes only those from
  `self.formation` — decoupling "fails the universe screen" from both "has
  a non-missing return" (uses the pre-`apply_missing_policy` panel) and
  "has a future held-month return" (never checks `self.merged` at all).
  Falls back to `df` when `self._pre_missing_policy_data` is unset (e.g.
  the method exercised directly, bypassing `apply_missing_policy`). For
  `ls_quantile`, extracted `registry._resolve_ls_quantile(ls_quantile)`:
  `> 1` rounds (not truncates) to a whole group count, clamping to 10 if
  that rounds below 2; a fraction in `(0, 0.5]` converts to `1/value`
  groups; anything else (`None`, `<= 0`, a fraction `> 0.5`) clamps to the
  standard 10-group default — same "clamp an out-of-menu value to the
  canonical default" policy `_clamp` already applies to every other menu
  field in `build_config`. Also added `"portfolio.sort.ls_quantile"` to
  `ReviewGate._check_silent_high_impact_fields`'s covered-field list (see
  the entry below this one) so an unset `ls_quantile` requires human
  confirmation rather than silently defaulting to a decile sort on an
  approved, `paper_faithful` spec.
- **Rationale:** The correct formation-eligibility semantics is "include
  unless there is positive evidence of exclusion" (permissive by default,
  matching the look-ahead fix's spirit of not penalizing a stock for
  missing FUTURE data it couldn't have controlled at formation time) rather
  than "exclude unless there is positive evidence of inclusion" (which is
  what an inner-join-based population check does, and which would have
  re-broken the delisted-stock case). Using the pre-`apply_missing_policy`
  snapshot specifically for the universe-filter check (rather than the
  fully-processed `df`) cleanly separates two independent concerns that
  the pipeline's linear ordering had otherwise conflated: "is this stock in
  the reviewed universe" (a static-ish attribute question: shrcd/exchcd/
  siccd) versus "does this stock have a valid return value this month" (an
  outcome question that's irrelevant to universe membership).
- **Empirical impact:** No-op for any run with no `universe_filters`
  configured, or where every formation-eligible stock's universe-defining
  attributes (shrcd/exchcd/siccd) are stable and pass the filter in every
  month it appears (confirmed by the full existing suite passing
  unchanged). Changes numbers only when `universe_filters` excludes a
  stock that has a signal value AND appears somewhere in the panel with a
  disqualifying attribute — exactly the case this fix targets. New
  regression suite `tests/test_formation_universe_eligibility.py` covers:
  the excluded-stock case (breakpoint corrected from 2.5 to 2.0), the
  zero-data delisted-stock case (still NOT excluded, confirming no
  regression on the same-day look-ahead fix), and the no-`universe_filters`
  no-op case. `tests/test_ls_quantile_validation.py` covers all the
  `_resolve_ls_quantile` clamping cases enumerated above.
- **Trade-offs / risks:** The universe-eligibility check is per-permno, not
  per-(permno, month) — a permno is excluded if it EVER fails the filter
  anywhere in the pre-missing-policy panel, not specifically at its own
  formation month (which, per the options-considered discussion, isn't
  reliably available in this repo's panel convention). This is a reasonable
  approximation for the largely time-invariant attributes
  `universe_filters` typically screens on (share class, exchange, industry)
  but is not a strictly point-in-time-exact eligibility check for a
  genuinely time-varying filter field. `ls_quantile` rounding (`1.5` -> `2`)
  changes behavior versus the old silent truncation (`1.5` -> `1`) for any
  spec that happened to have a fractional `> 1` value before this fix —
  no existing fixture hits this path (confirmed by the passing suite).
- **References:** [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py)
  (`apply_missing_policy`, `apply_signal_holding_period`),
  [src/steps/step3_codegen/registry.py](../src/steps/step3_codegen/registry.py)
  (`_resolve_ls_quantile`),
  [src/steps/step2_reviewer/__init__.py](../src/steps/step2_reviewer/__init__.py)
  (`_check_silent_high_impact_fields`),
  [tests/test_formation_universe_eligibility.py](../tests/test_formation_universe_eligibility.py),
  [tests/test_ls_quantile_validation.py](../tests/test_ls_quantile_validation.py).

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

## 2026-07-25 — Data-loader audit: CCM link-quality filter was missing from the multi-source join path

- **Context / problem:** An audit of `src/infra/data_layer/__init__.py` +
  `catalog.py` found the declarative multi-source signal-input loader
  (`link_to_permno()`, used by `assemble_signal_master_table`/`multi_source`
  codegen mode) had NO CCM linktype/linkprim data-quality filter at all,
  unlike the legacy `CCMLinker` class (used by
  `DataLayer.get_signal_master_table()`), which correctly restricts to
  `linktype IN ('LC','LU')` / `linkprim IN ('P','C')` per
  `docs/architecture.md` Section 3.2. `link_to_permno`'s own docstring
  additionally claimed "primary link wins on ties" while the tie-break was
  actually just "smallest permno wins" — misleading, and not the CRSP-
  standard rule. Not caught by tests because
  `scripts/build_test_papers_synthetic_data.py` only ever generates clean
  `linktype∈{LC,LU}` / `linkprim∈{P,C}` rows, so the missing filter never
  had a bad row to reject in test fixtures.
- **Options considered:** (a) leave `link_to_permno` filter-free and document
  it as a known gap; (b) hardcode the CCM-specific `linktype`/`linkprim`
  column names into `link_to_permno`; (c) make the filter/tie-break rule
  fully declarative in `catalog.LINK_TABLES` so it generalizes to any future
  link table with its own quality-flag columns, not just CCM.
- **Decision:** (c). Added optional `valid_filters: {column: [allowed
  values]}` and `primary_filter: {column: value}` keys to a `LINK_TABLES`
  entry (only `"ccm"` uses them today). `link_to_permno()` now drops rows
  outside `valid_filters` before joining and prefers the `primary_filter`
  row on ties (remaining ties still fall back to smallest permno for
  determinism).
- **Rationale:** Keeps the "register once" declarative philosophy (adding a
  new link table with its own quality flags is a catalog entry, not new
  join code) and makes the two CCM-linking code paths agree, matching the
  documented CRSP/CCM convention instead of leaving a silent
  correctness gap that would only bite once real (non-synthetic) WRDS data
  with mixed linktypes is loaded.
- **Empirical impact:** None on existing golden-number tests (all synthetic
  fixtures already only contain "good" link rows) — this only changes
  behavior once a raw `ccm_lnkhist` extract containing non-`LC`/`LU` or
  non-primary rows is used.
- **Trade-offs / risks:** None identified; purely additive/declarative.
- **References:** `src/infra/data_layer/__init__.py` (`link_to_permno`),
  `src/infra/data_layer/catalog.py` (`LINK_TABLES["ccm"]`),
  `tests/test_signal_master_multisource.py::test_link_to_permno_drops_bad_linktype_and_prefers_primary`,
  `tests/test_data_catalog.py::test_link_tables_unchanged`. Two related,
  lower-severity findings from the same audit fixed alongside this one (see
  `CHANGELOG.md` [Unreleased]): `_apply_pit_attrs` silently dropping
  panel rows with no covering `msenames` window (now falls back to the
  earliest attrs record, matching its own long-standing comment), and
  `patents_nber` (a catalog source registered with `date: None`) silently
  returning zero rows forever instead of failing loud.


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

## 2026-07-24 — Rename `merge_signal` to `apply_signal_holding_period`

- **Context / problem:** `merge_signal`'s name only described the least
  important part of what it does (a one-line `.merge()` at the end); the
  actual non-trivial logic is expanding a low-frequency signal into one row
  per held month, capped at the rebalance step (`apply_*` is the existing
  naming convention for "apply a rule to the data", used by
  `apply_delisting_returns`/`apply_missing_policy`/`apply_excess_returns").
- **Decision:** Renamed to `apply_signal_holding_period` (via IDE rename
  across `steps.py`, its call sites, and tests; the dynamic
  `_dispatch("merge_signal", ...)` string literal and `ctx.trace.append(...)`
  in `__init__.py` needed a manual follow-up fix since a language-server
  rename can't see through `getattr(steps, step_name_string)`).
- **Rationale:** Consistent naming makes the step list in
  `BacktestExecutor`'s docstring read accurately; no behavior change.
- **Empirical impact:** None (pure rename). Full suite re-verified: 134
  passed, 26 skipped.
- **References:** [src/infra/backtest_engine/steps.py](../src/infra/backtest_engine/steps.py),
  [src/infra/backtest_engine/__init__.py](../src/infra/backtest_engine/__init__.py).

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



## 2026-07-23 — Full-repo audit: remove remaining silent CRSP defaults (universe screen + legacy path fallback)

- **Context / problem:** After the `catalog.py`/`RETURNS_UNIVERSES` refactor
  established "no silent default data source" for the returns panel, a
  design review surfaced two places where a CRSP-specific assumption still
  applied unconditionally, contradicting that principle: (1)
  `steps.filter_universe()` hardcoded a `shrcd`/`exchcd`/`siccd` baseline
  screen applied to every returns panel regardless of `returns_universe`,
  and (2) `BacktestExecutor._load_data()`'s legacy-path fallback
  (`<data_path>/local/msf.parquet`) applied whenever ANY named returns
  table's raw/ file was missing, not just CRSP's -- so a future non-CRSP
  returns universe with a misplaced/missing file would silently load CRSP
  data instead of failing loud. A full-repo audit (grep across `src/` and
  `scripts/` for hardcoded source/table-name defaults) was run to check for
  further instances of this same class of bug.
- **Options considered:** (a) leave the baseline screen hardcoded but make it
  configurable via new MethodSpec fields (`include_financials`/`share_codes`/
  `exchange_codes`) with CRSP-matching defaults; (b) move the baseline
  screen's definition into `catalog.py` as a per-returns-universe
  `baseline_filters` property; (c) remove the hardcoded baseline entirely and
  rely on the extractor to capture it (like any other paper-specific universe
  restriction) via the existing `universe_filters` DSL.
- **Decision:** (c) for the universe screen — simplest, and consistent with
  the principle that ALL universe restrictions (paper-specific or
  "boilerplate") should be explicit, reviewable MethodSpec fields, not
  code-level defaults tied to one specific data source's column vocabulary.
  For the legacy-path fallback, scoped it to `returns_table == "crsp_msf"`
  only (kept, since it's a genuine file-location compatibility shim for
  pre-catalog snapshots/tests -- not a data-source choice -- but must not
  silently substitute CRSP data for a different requested universe).
- **Rationale:** `shrcd`/`exchcd`/`siccd` are CRSP-specific column names;
  hardcoding them into a step that runs for every returns panel assumes every
  registered returns universe is CRSP-shaped, which the catalog design
  explicitly rejects (a returns universe is meant to be one-catalog-entry
  extensible, e.g. to a non-US or non-CRSP panel). The extractor already has
  a working DSL (`UniverseFilterSpec`/`FilterOp`) for exactly this kind of
  row-level restriction; asking it to also capture the common boilerplate
  screen (which nearly every US-equity paper states, even if just by
  citation) is more consistent than maintaining a parallel, hardcoded
  version of the same rule in Python.
- **Empirical impact:** None for existing papers. Full suite green at
  192 passed / 26 skipped (was 191/26 before the new regression test for the
  legacy-path fix); all 9 golden e2e tests byte-identical -- the synthetic
  test panels don't contain rows the old hardcoded screen would have
  excluded, so removing it was a numeric no-op for every existing fixture.
- **Trade-offs / risks:** A paper whose universe restriction extraction
  misses the common boilerplate (and where the reviewer's evidence check
  doesn't catch it) would now run against a broader universe than intended,
  silently -- this risk is accepted because the alternative (a hardcoded,
  unconditional CRSP-shaped screen) was strictly worse: it silently imposed
  a restriction that's WRONG for any paper that doesn't want it, with no way
  to turn it off short of a full `filter_universe_hook` rewrite.
  `portfolio.universe`/`portfolio.universe_filters` are already
  `HIGH_IMPACT_FIELDS` in the reviewer, so this is covered by the existing
  evidence-check machinery, not a new gap.
- **References:** `src/infra/backtest_engine/steps.py` (`filter_universe`),
  `src/infra/backtest_engine/__init__.py` (`_load_data`),
  `prompts/extractor/methodspec_extractor.md` §4.5.2,
  `tests/test_research_design.py`, `tests/test_no_default_source.py`,
  `docs/architecture.md` §4.6, CHANGELOG `[Unreleased]`.

## 2026-07-23 — Estimator-strategy layer + single `form_portfolios` hook; delete dead `neutralize_signal` scaffold

- **Context / problem:** An architecture review (assessing over-design vs.
  generality for replicating arbitrary papers) found the engine had accreted
  narrow deterministic branches that added complexity without expanding real
  coverage: (1) Fama-MacBeth was an inline `if` branch inside
  `run_with_config()` rather than a swappable strategy, making it awkward to
  ever add a third estimator (factor-model alpha, event-window return,
  custom); (2) `compute_breakpoints`/`assign_portfolios` were dispatched as
  two separate Step-contract functions, but `compute_breakpoints_multi` (the
  multi-dim counterpart) did no real work — it just returned
  `config["sort_dims"]` unchanged so `assign_portfolios_multi` could do
  everything, a "fake step" that only existed to satisfy the two-call
  contract; (3) `neutralize_signal` was a full step (dispatch call, trace
  entry, hook contract) that was *always* a no-op in practice — no
  `MethodSpec` field has ever driven `config["neutralization"]` away from
  `"none"` — pure speculative scaffolding (YAGNI) for a feature nothing uses.
- **Options considered:** (a) leave as-is; (b) fix only the two most
  clearly broken cases (neutralize_signal deletion, breakpoints/assign
  merge) without a real estimator abstraction; (c) formalize an
  `Estimator` strategy layer now (`estimators.py`) *and* merge
  breakpoints+assign into one hookable `form_portfolios` unit, while leaving
  the overlapping-cohort step family and `compute_long_short`'s
  `average_leg_spread` special case for a later pass.
- **Decision:** (c). The estimator abstraction is small (two functions +
  a registry dict) and immediately removes the inline Fama-MacBeth branch
  from `run_with_config()`, which now only knows about "prep chain, then
  ask the estimator." `form_portfolios`/`form_portfolios_hook` replace
  the `compute_breakpoints`/`assign_portfolios` pair (and their
  `_hook` counterparts) as the single unit for "how portfolios get formed" —
  the underlying `compute_breakpoints`/`assign_portfolios`/`_multi` pure
  functions are unchanged and still directly unit-tested, only the
  dispatch/hook *contract* collapsed from two names to one.
- **Rationale:** Per the reviewed direction (fewer deterministic engine
  branches, more delegation to reviewed hooks, empirics still gated by
  MethodSpec review), a new engine branch is only justified if it (a)
  covers a broad class of papers and (b) composes with existing branches.
  A two-function contract where one function never does real work fails
  (b); an always-no-op step fails both. Collapsing them to one hook name
  each reduces the number of things a future `detect_hooks()`/hook author
  has to reason about without losing any expressiveness (nothing was
  standard-implemented that isn't standard-implemented after this change).
- **Empirical impact:** None. Golden e2e (`test_*_e2e.py`, incl.
  `test_ball2016_e2e.py`'s hand-written hooks) byte-identical; full suite
  191 passed / 26 skipped after this change (was 193/26 — the 2 fewer
  passing tests are the deleted `TestNeutralizeSignalScaffold` cases, not a
  regression).
- **Trade-offs / risks:** `form_portfolios_hook` is a breaking rename of the
  hook contract (`compute_breakpoints_hook`/`assign_portfolios_hook` no
  longer load) — any *external* plugin authored against the old contract
  would need updating; migrated the two fixtures that used it in this repo.
  Overlapping-cohort's parallel `_overlap` step family and
  `compute_long_short`'s `average_leg_spread` (numerically identical to
  `extreme_group_spread` unless `long_portfolios`/`short_portfolios` are
  hand-fed via config) were flagged in the same review as further
  candidates for consolidation but are deliberately deferred to a later,
  separately-verified pass rather than bundled into this change.
- **References:** `src/infra/backtest_engine/estimators.py`,
  `src/infra/backtest_engine/__init__.py` (`run_with_config`,
  `_MULTI_DIM_STEPS`/`_OVERLAP_STEPS`), `src/infra/backtest_engine/steps.py`
  (`form_portfolios`/`form_portfolios_overlap`, deleted `neutralize_signal`),
  `src/infra/backtest_engine/registry.py` (`load_hooks`),
  `src/steps/step3_codegen/__init__.py` (`HOOK_SIGNATURES`/`HOOK_RETURN_DOCS`),
  `src/steps/step3_codegen/registry.py` (`detect_hooks`/`build_config`),
  `tests/fixtures/plugins/ball2016_cash_based_operating_profitability_factor.py`,
  `tests/fixtures/plugins/fama_french_1993_double_sort_hml.py`,
  `tests/test_engine_hooks.py`, `tests/test_ball2016_e2e.py`,
  `tests/test_sandbox_validation.py`, `tests/test_research_design.py`,
  `docs/architecture.md` §4.6, CHANGELOG `[Unreleased]`.

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

## 2026-07-22 — Removed `Pipeline.run_factor()` (dead extraction-driven orchestrator)

- **Context / problem:** `Pipeline.run_factor()` was the designed full pipeline
  entry point wiring SemanticExtractor → ReviewGate → MetaCoder → Sandbox →
  DualTrackController → AttributionLayer, with backtrack loops between them
  (docs/architecture.md §3.1). A repo-wide grep (`app.py`, `scripts/`, `tests/`)
  found zero callers of `run_factor()` anywhere — the only working, tested path
  was the separate `run_from_method_spec()` MVP bypass (used by
  `tests/test_mvp_e2e.py`, `test_accruals_e2e.py`, `test_ball2016_e2e.py`).
  Worse, of `run_factor()`'s four "feedback loop" branches, three
  (Review→Extractor, Sandbox→Review empirical, Attribution→Review anomaly)
  were never more than TODO stubs: each incremented `backtrack_count` and then
  immediately returned `status="failed"` instead of actually re-invoking the
  upstream stage. Only Sandbox→Meta-Coder technical repair genuinely retried.
- **Options considered:** (1) Keep `run_factor()` as documented-but-unfinished
  scaffolding for future Phase 2 extraction work. (2) Implement the three
  missing backtrack loops for real. (3) Delete `run_factor()` and its
  dedicated helpers (`_has_empirical_issues`, `_is_anomalous`, `PipelineStatus`,
  `MAX_BACKTRACK_DEPTH`) plus the now-orphaned constructor wiring
  (`self.extractor`, `self.review_gate`, `self.controller`, `self.attribution`
  and their imports).
- **Decision:** (3) — delete it entirely.
- **Rationale:** Unused, partially-fake code (backtrack loops that silently
  fail on first trigger while claiming to retry) is worse than no code: it
  misrepresents the pipeline's actual capabilities to future readers/agents
  (as already surfaced by several rounds of doc/comment corrections this same
  day — see the two preceding CHANGELOG entries). Implementing the missing
  loops properly (option 2) is real feature work requiring product decisions
  (what re-extraction feedback looks like, when to give up) that belongs in
  its own dedicated effort, not a cleanup pass. `run_from_method_spec()` is
  unaffected and remains the sole, fully-real `Pipeline` entry point.
- **Empirical impact:** None — `run_factor()` was never exercised by any test
  or script, so no replication results depended on it.
- **Trade-offs / risks:** Re-introducing extraction-driven, multi-track,
  attribution-gated orchestration (roadmap Phase 2) now means writing a new
  orchestrator from scratch rather than finishing this one. That's judged
  preferable to building on stub backtrack logic that was never validated
  end-to-end. `SemanticExtractor`, `ReviewGate`, `DualTrackController`, and
  `AttributionLayer` themselves are untouched and fully usable standalone.
- **References:** `src/pipeline.py`, `docs/architecture.md` §3.1 and §4,
  `docs/roadmap.md` Phase 1 status note, CHANGELOG.md 2026-07-22 entries.

## 2026-07-22 — `src/steps/step5_backtest_runner/` created; `DualTrackController._run_track()` stub fixed

- **Context / problem:** After the previous two entries, "Step 5" had no
  corresponding module at all — it was private methods on `Pipeline`
  (`_build_script`/`_execute_script`/`_make_failed_run_record`), unlike every
  other numbered step, which is a dedicated class `Pipeline` orchestrates.
  Separately, `DualTrackController._run_track()` (step 6) was
  `raise NotImplementedError` — meaning `Pipeline.run_factor()`, the
  documented 8-stage pipeline entry point, could reach "run" and then crash;
  only the separate `run_from_method_spec()` bypass actually executed a
  backtest. These two gaps were connected: fixing `_run_track()` requires
  exactly the "build script, execute it" action `run_from_method_spec` already
  had inlined — extracting that into a real Step 5 module made both fixable
  in one pass instead of writing `_run_track()`'s own separate build+execute
  logic (a third copy, the exact drift risk this project's Phase 0 decision
  was designed to prevent).
- **Options considered:**
  1. Leave Step 5 as private `Pipeline` methods; write `_run_track()`'s
     build+execute logic as its own separate implementation.
  2. Extract Step 5 into `src/steps/step5_backtest_runner/BacktestRunner`
     (build_script/execute/make_run_record/make_failed_run_record); have
     both `Pipeline` and `DualTrackController` depend on it; give
     `DualTrackController` its own bounded repair loop (step6→step3) using
     injected `MetaCoder`/`AdversarialSandbox` collaborators.
  3. Same extraction, but put the repair loop in `BacktestRunner` itself
     (so step5 owns retries, not just the build+execute action).
- **Decision:** Option 2. `BacktestRunner` is a pure action + result-shaping
  class (`build_script`, `execute`, `make_run_record`, `make_failed_run_record`)
  with **no retry logic of its own** — `Pipeline.run_from_method_spec` and
  `DualTrackController._run_track` each own their own bounded repair loop
  around it. `DualTrackController.__init__` now takes
  `runner: BacktestRunner, meta_coder: MetaCoder, sandbox: AdversarialSandbox`
  instead of `engine: BacktestExecutor`; `run_experiment`/`_run_track` gained a
  required `snapshot_id`; `Pipeline.run_factor()` gained the same required
  `snapshot_id` (a real, independent gap this closes — `run_factor()`
  previously had no way to reference a data snapshot at all).
- **Rationale:** Option 1 would have meant three drifting implementations of
  "build the script, run it, handle failure" once `_run_track()` was filled in
  (Pipeline's, `_run_track()`'s, and whatever the next caller needed) — the
  same class of problem Phase 0 fixed for the engine itself
  (`docs/decision-log.md` 2026-07-20 entry: "unify the duplicated engine logic
  into one importable module"). Option 3 (repair loop inside `BacktestRunner`)
  was rejected because retrying is a decision that needs `MetaCoder`
  (Step 3) and `AdversarialSandbox` (Step 4) as collaborators — giving Step 5
  those dependencies just to retry itself would make it the same kind of
  cross-cutting orchestrator `Pipeline`/`DualTrackController` already are,
  instead of a clean action step; every other step (`AdversarialSandbox.validate()`,
  `BacktestRunner.execute()`) stays retry-free by design, with retries owned by
  whichever orchestrator has the repair collaborators. `DualTrackController`
  needing its own copy of the repair loop (rather than reusing
  `Pipeline._validate_with_repair`) is accepted asymmetry: per-track repair
  only re-validates statically (no compute_signal execution-smoke slice)
  because that smoke test already ran once against the shared plugin before
  `run_experiment` is called — repeating it per track per repair attempt would
  be redundant (same signal formula, only `config_overrides` differ per track).
- **Empirical impact:** None on any already-passing factor's numbers. Positive
  functional impact: `Pipeline.run_factor()`'s "run" stage is no longer
  guaranteed to crash — dual-track/ablation experiments can now actually
  execute end-to-end through the numbered 8-stage pipeline, not just through
  `run_from_method_spec()`.
- **Trade-offs / risks:** `run_factor()`'s public signature changed (added a
  required `snapshot_id` parameter) — an intentional breaking change, since
  the method could not have worked without one; no released callers depended
  on the old signature (grep-verified, and this project has no external
  version yet). `DualTrackController`'s per-track repair validates
  statically only (no data slice) — acceptable given the shared plugin's
  formula was already smoke-tested once; documented above as the reason, not
  silently different behavior.
- **References:** [src/steps/step5_backtest_runner/__init__.py](../src/steps/step5_backtest_runner/__init__.py)
  (new), [src/steps/step6_dual_track_controller/__init__.py](../src/steps/step6_dual_track_controller/__init__.py)
  (`_run_track` fixed), [src/pipeline.py](../src/pipeline.py) (`run_factor`
  `snapshot_id` param, `run_from_method_spec`/`_validate_with_repair` now call
  `self.runner.*`), [tests/test_dual_track_controller.py](../tests/test_dual_track_controller.py),
  `AGENTS.md` Module Map, `CHANGELOG.md [Unreleased]`.

## 2026-07-22 — Engine library (`BacktestExecutor`/`steps.py`) moved from `src/steps/step5_executor/` to `src/infra/backtest_engine/`

- **Context / problem:** "Step 5" as a *pipeline action* is genuinely just
  "build the standalone script, validate it, execute it via subprocess" —
  literally `subprocess.run([sys.executable, script_path])`, implemented
  entirely in `src/pipeline.py` (`_build_script`/`_execute_script`). But the
  directory `src/steps/step5_executor/` held something different: the
  `BacktestExecutor` class and `steps.py`'s 12-step computation functions —
  the *engine library* the generated script imports and calls once it's
  running, not the act of running it. The folder name conflated "the action
  of step 5" with "a library step 5's output happens to depend on", which is
  what motivated the previous entry's move (registry.py's generation-time
  functions) and this one.
- **Options considered:**
  1. Leave the engine library under `src/steps/step5_executor/` (status quo).
  2. Move it under `src/steps/step3_codegen/` (reasoning: "step3 generates the
     script that uses it").
  3. Move it under `src/infra/` (reasoning: it's shared computation
     infrastructure with no single owning step).
- **Decision:** Option 3. Moved (via `git mv`, contents unchanged) to
  `src/infra/backtest_engine/`. `src/steps/` now contains only genuine
  pipeline actions; "Step 5" has no corresponding numbered folder — it's the
  build+execute action in `pipeline.py`.
- **Rationale:** Option 2 was checked against actual callers (grep) before
  rejecting it: `step3_codegen` (after the previous entry's move) has **zero**
  real imports of the engine library — the only remaining mention is the
  generated script's own runtime import, which is the *artifact* step3
  produces, not step3's own code. Meanwhile the real callers are
  `pipeline.py` (orchestration), `step6_dual_track_controller` (ablation
  experiments), `app.py` (dashboard), `scripts/test_codegen.py`, and 13 unit
  test files that import `steps.py` directly to test individual step
  functions' math — none of which have anything to do with code generation.
  Filing it under `step3_codegen` would repeat the exact mistake being fixed
  (one consumer's name imposed on a library everyone uses), just with a
  different consumer. `src/infra/` already holds exactly this kind of
  cross-cutting library with no single owning step (`DataLayer`, `CCMLinker`,
  `TimeAvailComputer`, the Pydantic `models/`) — the engine library fits that
  same shape.
- **Empirical impact:** None — pure code motion (`git mv`, no logic/config
  changes). `python3 -m pytest tests/`: 124 passed / 28 skipped / 14 failed
  (same 14 pre-existing pyarrow-environment failures), identical before/after.
- **Trade-offs / risks:** `src/steps/` numbering now has a "gap" at 5 (no
  `step5_*` folder) — documented in `AGENTS.md`'s Module Map (Step 5's row now
  points at `pipeline.py`'s `_build_script`/`_execute_script` instead of a
  folder) so this doesn't read as a missing/forgotten step.
- **References:** [src/infra/backtest_engine/](../src/infra/backtest_engine/)
  (moved package), [src/pipeline.py](../src/pipeline.py) (`_build_script`/
  `_execute_script` — the actual Step-5 action), `AGENTS.md` Module Map,
  `docs/architecture.md` §4.6, `CHANGELOG.md [Unreleased]`.

## 2026-07-22 — Codegen decision layer physically moved from step5_executor to step3_codegen

- **Context / problem:** `step5_executor/registry.py` bundled two unrelated
  responsibilities: generation-time decisions (`STANDARD`/`detect_hooks`/
  `build_config`/`resolve_long_leg`/`resolve_short_leg`/`normalize_leg`/
  `resolve_sort_dims` — "what does the LLM need to generate for this
  MethodSpec") and run-time hook loading (`load_hooks` — "how does
  `BacktestExecutor.run_with_config()` load a plugin's hook at run time").
  Grep-verified: `run_with_config()`/`_dispatch()` never call `detect_hooks`;
  `build_config` is called by generation-time code (`script_generator`) and by
  `BacktestExecutor`'s own (now-vestigial — no current caller passes a raw
  signal in-process; the real path is generate-script → validate → execute)
  `run()` convenience method; `load_hooks` is called only by
  `run_with_config()`. Because step3 could only reach the generation-time
  functions through `BacktestExecutor`'s wrapper methods
  (`BacktestExecutor._detect_hooks(spec)`, `engine._build_config(...)`),
  `step3_codegen` imported the execution-engine class just to reach two pure
  functions of a `MethodSpec` — the opposite of the intended shape ("step5
  only executes the already-generated code; it decides nothing").
- **Options considered:**
  1. Leave as-is; have step3 call `registry.detect_hooks`/`registry.build_config`
     directly instead of through the `BacktestExecutor` wrapper (removes the
     *class* dependency, keeps the *file* in step5_executor/).
  2. Physically move the generation-time functions into `step3_codegen/registry.py`;
     keep only `load_hooks` in `step5_executor/registry.py`; keep
     `BacktestExecutor._detect_hooks()`/etc. as delegates to the new location
     for backward compatibility.
  3. Move everything (including `load_hooks`) into step3_codegen.
- **Decision:** Option 2. `src/steps/step3_codegen/registry.py` is the new,
  sole owner of `STANDARD`/`FILTER_UNIVERSE_ALWAYS_HOOK_REASON`/`ev`/
  `detect_hooks`/`build_config`/`resolve_sort_dims`/`resolve_long_leg`/
  `resolve_short_leg`/`normalize_leg`. `MetaCoder.generate_plugin` and
  `script_generator.generate_backtest_script` call these directly (no more
  `from src.steps.step5_executor import BacktestExecutor` at either call
  site — the generated script's own runtime import of `BacktestExecutor`,
  which it genuinely needs to execute, is untouched). `step5_executor/registry.py`
  now holds only `load_hooks`. `BacktestExecutor._detect_hooks()`/
  `_build_config()`/`_resolve_long_leg()`/`_resolve_short_leg()`/
  `_normalize_leg()` stay on the class as thin delegates to
  `step3_codegen.registry`, so existing callers (notably
  `tests/test_engine_hooks.py`'s direct use of `BacktestExecutor._detect_hooks(spec)`)
  keep working unchanged.
- **Rationale:** Option 1 (just change the import) would have removed the
  *appearance* of step3 depending on the execution engine without changing
  where the code physically lives — the file's own docstring already said
  "this module answers what the LLM needs to generate ... not what a backtest
  computes", i.e. it was already conceptually step3's file, just filed under
  step5_executor/. Option 3 was rejected because `load_hooks` is genuinely
  run-time-only (BacktestExecutor's own dispatch calls it); moving it too
  would make step5_executor depend on step3_codegen for something step5 uses
  internally on every run, which is backwards for the opposite reason. Option
  2 makes the dependency strictly one-directional and matches each function's
  actual caller: step3_codegen (decides) has zero imports of step5_executor
  now (verified); step5_executor (executes) imports step3_codegen.registry
  only for five backward-compatible delegate methods, never for anything its
  own `run_with_config()`/`_dispatch()` executes.
- **Empirical impact:** None — pure code motion, no config/logic changes.
  `python3 -m pytest tests/`: 124 passed / 28 skipped / 14 failed (same 14
  pre-existing pyarrow-environment failures as before this change) —
  identical before and after.
- **Trade-offs / risks:** `BacktestExecutor`'s five delegate methods are now a
  standing backward-compatibility shim with no other purpose; if/when
  `tests/test_engine_hooks.py` and any other direct callers are updated to
  import `step3_codegen.registry` directly, those methods could be deleted
  entirely for full decoupling. Left as delegates for now to avoid touching an
  unrelated test file's public call pattern in this change.
- **References:** [src/steps/step3_codegen/registry.py](../src/steps/step3_codegen/registry.py)
  (new), [src/steps/step5_executor/registry.py](../src/steps/step5_executor/registry.py)
  (trimmed to `load_hooks`), [src/steps/step5_executor/__init__.py](../src/steps/step5_executor/__init__.py)
  (delegate methods), [src/steps/step3_codegen/__init__.py](../src/steps/step3_codegen/__init__.py) /
  [src/steps/step3_codegen/script_generator.py](../src/steps/step3_codegen/script_generator.py)
  (direct calls), [tests/test_multi_sort.py](../tests/test_multi_sort.py),
  `docs/architecture.md` §4.6, `CHANGELOG.md [Unreleased]`.

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

## 2026-07-21 — Multi-source data loader: per-source join registry, not per-paper join code

- **Context / problem:** The loader could only reach two worlds — CRSP-only or
  CRSP+Compustat — chosen by a binary heuristic (`_signal_needs_compustat`:
  "any mapped column outside a CRSP whitelist ⇒ Compustat"). It had no path to
  IBES / OptionMetrics / 13F / patents, and `normalized_mapping` recorded only
  `concept → column`, never *which source* a column came from. Papers that use
  those sources could not be assembled at all, and when a genuinely new data
  source appears there was no principled place to teach the loader how to join
  it. The open question: should join logic be re-decided per paper (dialog /
  LLM at runtime), or declared once?
- **Options considered:**
  1. Pop up a resolve-stage dialog per paper to declare how to join each source.
  2. Let the LLM decide/generate the join at runtime, per paper.
  3. Maintain a per-source join **registry**, updated once when a new source
     first appears; field→source mapping stays per-paper (reviewed), join
     mechanism is per-source.
- **Decision:** Option 3. Split the problem along its real seam: the
  **field→source→column mapping is per-paper** (human-confirmed in resolve,
  lives in `MethodSpec.data.normalized_mapping`, now allowing the richer
  `{concept: {source, column}}` form); the **join mechanism is per-source**,
  declared once in `data_layer.SIGNAL_SOURCES` (`key/link/date/lag`) with one
  generic point-in-time `link_to_permno` over `LINK_TABLES` (CCM / IBES-CRSP /
  OptionMetrics-CRSP). `assemble_signal_master_table` groups a spec's formula
  fields by source, reads only the needed columns, links each to permno,
  computes an availability month, and merges on `[permno, time_avail_m]`. When
  a spec references a source absent from the registry, `ReviewGate` **blocks**
  and a human registers it once (LLM may *draft* the entry for review) — after
  which every future paper using that source is handled automatically.
- **Rationale:** "How IBES links to permno" is a property of IBES, identical for
  every paper that uses it — so re-deciding it per paper (Options 1/2) is both
  wasteful and a reproducibility hazard (the same source could join differently
  across papers/runs). Point-in-time linking (CCM `linkdt`/`linkenddt`, IBES/OM
  `sdate`/`edate`) is safety-critical for look-ahead/survivorship, so it must be
  written and tested **once**, not regenerated. This mirrors the engine's
  STANDARD-set-vs-hook philosophy and AGENTS.md's hard constraint that the LLM
  never controls empirical data construction. The registry *is* the general
  mechanism (add a source = one declaration), so it is more general than
  per-paper join code, not less.
- **Empirical impact:** None on existing replications — golden e2e
  (accruals/ball2016/mvp) stay on the untouched binary `compustat`/`crsp_only`
  path and remain byte-identical; the source-driven `multi_source` path is
  additive. Enables (not yet exercised for a published factor) IBES/OptionMetrics
  signals end-to-end on the synthetic WRDS-shaped data.
- **Trade-offs / risks:** v1 cross-source alignment is an exact
  `[permno, time_avail_m]` merge, not an as-of join — correct for single-source
  and same-frequency multi-source signals, but mixing annual+monthly sources in
  one formula needs an as-of join (deferred). Patents' year-based availability
  is registered but not yet computed (`date=None` rows drop). LLM-drafted
  registry entries are a documented future step, not yet built.
- **References:** `src/infra/data_layer/__init__.py`
  (`SIGNAL_SOURCES`/`LINK_TABLES`/`link_to_permno`/`assemble_signal_master_table`),
  `src/infra/models/method_spec.py` (`resolved_sources`), `src/steps/reviewer/__init__.py`
  (`_check_source_mapping_resolved`), `src/steps/codegen/script_generator.py`
  (`pick_signal_input_mode` + `multi_source` mode), `tests/test_signal_master_multisource.py`,
  `tests/test_crsp_raw_panel.py`, CHANGELOG `[0.15.0]`.


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

## 2026-07-20 — BacktestEngine: ResearchDesign steps are deterministic config, daily data is source-only

- **Context / problem:** Sample-construction choices (delisting-return
  adjustment, universe filters, neutralization) materially move results but are
  not "signal formula". Also, some signals need daily prices while the engine is
  monthly-rebalanced. Both risked leaking into LLM-generated hooks or forcing a
  parallel daily engine.
- **Decision:** (a) Treat delisting returns, the `filter_universe` DSL, and
  `neutralize_signal` as a deterministic **ResearchDesign** layer expressed as
  pure config — never defaulting to an LLM hook. (b) Support daily CRSP as
  *source data compounded to a monthly-keyed panel* (`ret = ∏(1+daily)-1`, `me`
  from the last trading day) so daily-input signals flow through the existing
  monthly engine unchanged — explicitly NOT genuine daily-frequency rebalancing.
- **Rationale:** Keeps empirical sample choices auditable and ablatable via
  config (per AGENTS.md, lag/empirical params are never LLM-decided), and avoids
  duplicating the whole pipeline just to admit daily price inputs.
- **Empirical impact:** Delisting adjustment uses `(1+ret)*(1+dlret)-1`; rows
  with missing `dlret` stay as plain `ret` (documented simplification vs. the
  Shumway/Johnson exchange-based imputation) — a known, bounded source of gap.
- **Trade-offs / risks:** No true daily-rebalanced estimator (deferred to the
  "ext" tier); delisting imputation is simplified. Both are documented scope
  limits, not silent approximations.
- **References:** [src/steps/engine/steps.py](../src/steps/engine/steps.py)
  (`load_daily_msf`, `apply_excess_returns`, `apply_delisting_returns`),
  plan.md Phases 2.5 / 6.

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

## 2026-08-04 — Session-centric web UI redesign: contract-first plan, checkpoint before starting

- **Context / problem:** The React/FastAPI site (2026-07-24 decision) only covers
  step1-5 and holds all workflow state in per-page `useState` (lost on reload).
  User wants full step1-8 coverage, every step independently runnable from a
  stored upstream artifact, a persisted structured trace, and a per-step
  "readiness to move on" signal to identify pipeline bottlenecks. A first draft
  plan bundled persisted-workflow-state, missing-endpoint, evaluation, and
  frontend work into one change; user review (external, thorough) scored it
  7/10 and flagged the Session data model and step3-7 artifact boundary as the
  most likely rework sources.
- **Decision:** Split the redesign into a **workflow control plane** (a new
  `Session` = state machine + artifact *references*, owned by the new backend
  session store) and the existing **research evidence plane** (`EvidenceStore`,
  `RunRecord`, `comparison.json` stay the sole authority for empirical
  artifacts). Concretely:
  - `SessionManifest` stores references + hashes only
    (`methodspec_ref, plugin_ref, script_ref(+sha256), execution_ids[],
    experiment_batch_id, comparison_ref, diagnosis_ref`); only step1-4's small
    artifacts (spec/review report/resolution/plugin/script/validation) live
    physically under the session directory; step5 onward is reference-only.
  - Formal session state machine (`created -> ... -> diagnosis_complete`, plus
    `blocked/failed/interrupted/cancelled/archived`) with rerun = new
    append-only `attempts[]`, never in-place overwrite; staleness propagates
    from upstream hash changes.
  - `run-all` replaced by `advance`/`resume` (run-until-blocked): a backend job
    cannot reliably pause across a process restart, so the "waits for human
    review" step is a return value + resumable call, not a long-lived thread.
    On backend startup, any `running` job/session is reconciled to
    `interrupted`; the UI always reads final state from the session, never
    from a stale job id; SSE is a notification channel only.
  - step3->4->5 chained by **artifact identity**, not by passing script text or
    paths over HTTP: step3 returns `{artifact_id, sha256}`, step4 validates
    that id, step5's execute endpoint accepts only an artifact_id whose sha256
    matches a passed validation record. Prevents the execute endpoint from
    becoming an arbitrary-code-execution surface.
  - step7's new endpoint accepts only `experiment_batch_id` /
    `execution_id`s (never client-supplied runs/config/metrics); the backend
    loads `RunRecord`s itself and checks same-batch, not-invalidated, hash
    completeness before building the comparison (reusing
    `write_comparison_summary`'s existing bundle build, not a second one).
  - Renamed "Scorecard" (a unified 0-100 per-step quality score) to
    `StepDiagnostics` + a separate `readiness` gate: several of the originally
    proposed "quality" signals do not actually indicate quality (fewer
    blocked fields != a more accurate MethodSpec; fewer repairs != a correct
    formula; `ValidationReport.executes_ok` defaults `True` and stays `True`
    when the check is skipped, so it must render tri-state, not a green
    check). A true `evaluation score` is computed only where an independent
    reference exists (today: step1 only, against SignalDoc/human labels).
  - Extraction evaluation is exposed as its own opt-in
    `POST /api/evaluations/extraction` action, isolated from normal sessions,
    so a normal session's extractor call can never be handed `SignalDoc.csv`
    or the human-labeled fixtures (existing hard constraint).
- **Rationale:** Confirmed before committing to the plan that
  `EvidenceStore.save_run` is a whole-directory `rmtree`+`rename` swap by a
  single writer (`src/infra/evidence/__init__.py`), not a general transactional
  store — a session manifest needs its own lock + revision/CAS write, not a
  copy of that method. Also confirmed the in-flight step6 auto-freeze/
  invalidation work (see CHANGELOG "Fixed a stale doc" entry same date) had
  already landed, meaning the original plan's "current state" section was
  stale against the actual worktree — reinforcing the need to freeze a
  checkpoint before defining the Session API contract against it.
- **Process:** Before any Session/UI code is written: (1) confirm the in-flight
  multi-config/evidence/step6-8 work is stable (`pytest tests/` green: 388
  passed/26 skipped, matching the last recorded baseline — no regression); (2)
  fix the stale `AGENTS.md` step6 description (done, this changelog entry);
  (3) this decision-log entry serves as the checkpoint marker; Session API
  schemas and state-transition tests are written next, before any endpoint
  handler body (Phase 0 of the revised plan).
- **Trade-offs / risks:** More upfront design work before any visible UI
  change; deliberately deferred a unified quality score the user might have
  wanted for an at-a-glance "which step is bad" answer — mitigated by still
  shipping per-step diagnostics and an explicit `readiness` gate, just not a
  single misleading number.
- **References:** `docs/multi-config-evidence-plan.md`, `AGENTS.md` (module
  map), `backend/jobs.py`, `backend/routers/*`, `src/infra/evidence/__init__.py`,
  `src/infra/models/plugin.py` (`ValidationReport.executes_ok`),
  `src/steps/step6_dual_track_controller/__init__.py`, `CHANGELOG.md`.
