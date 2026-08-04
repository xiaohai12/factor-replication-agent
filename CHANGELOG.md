# Changelog

## [Unreleased]

### Added

- Session-centric UI redesign, Phase 0 + Phase 1 (implements the plan from
  docs/decision-log.md's 2026-08-04 "Session-centric web UI redesign" entry):
  a new workflow-control-plane `Session` concept, separate from
  `EvidenceStore`/`RunRecord`/`comparison.json` (which remain the sole
  authority for empirical artifacts).
  - `src/infra/models/session.py`: `SessionState` state machine +
    `validate_transition` (illegal transitions raise
    `IllegalTransitionError`), `StepStatus`/`StepAttempt`/`StepRecord`
    (append-only attempts -- rerun never overwrites), `SessionManifest`
    (`schema_version` + `revision`, refs/hashes only), and the Phase 0.4
    `STEP_IO_CONTRACT` + `missing_input_refs()` per-step input/output ref
    table.
  - `src/infra/session_store.py`: `SessionStore` -- `fcntl.flock` per-session
    lock + compare-and-set `revision` write + atomic tempfile+`os.replace`
    manifest persistence (deliberately NOT `EvidenceStore.save_run`'s
    rmtree+rename pattern, which is single-writer-only).
    `SESSION_OWNED_STEPS = {1,2,3,4}`; step5+ is reference-only, enforced at
    the API (`step_dir()` raises for step >= 5). `reconcile_orphaned_running()`
    turns any attempt left `running` into `interrupted` on backend restart.
  - `backend/sessions.py` + `backend/routers/sessions.py`: session
    CRUD/archive/events endpoints, a session-scoped append-only structured
    event journal (`events.jsonl`, `since_seq` incremental reads), and the
    step3->4->5 **artifact-identity chain**: `POST .../steps/3/script`
    returns only `{artifact_id, sha256}` (never raw script text);
    `POST .../steps/4/validate` validates that exact artifact and records its
    sha256 only if validation passed; `POST .../steps/5/execute` accepts
    *only* a `script_sha256` matching a step4 SUCCESS record's
    `validated_script_sha256`, re-reads and re-hashes the stored artifact
    before running it, and rejects raw text/path input, hash mismatches, and
    tampered on-disk artifacts outright (closes the "execute becomes an
    arbitrary-code-execution endpoint" risk flagged in review).
  - `backend/jobs.py` / `backend/routers/jobs.py`: jobs may now be tagged
    with `session_id`/`step`/`stage` (existing untagged call sites
    unaffected); a tagged job's `log()` also appends a structured event into
    the session journal; SSE stream gained a 15s heartbeat comment frame so
    idle long-LLM-call connections don't time out; `JobManager` gained a
    TTL-based eviction sweep (`JOB_TTL_SECONDS`) so the in-process job dict
    doesn't grow unbounded; `backend/main.py`'s startup now calls
    `session_store.reconcile_orphaned_running()`.
  - New tests: `tests/test_session_store.py` (27), `tests/test_session_api.py`
    (11, including the artifact-identity-chain end-to-end run against the
    real synthetic golden numbers and 3 dedicated attack-scenario tests),
    `tests/test_jobs_manager.py` (4). Full suite now 430 passed, 26 skipped
    (was 388/26 before this session's work started -- zero regressions).
  - Deliberately NOT done yet (Phase 2+ of the plan): step6/7/8 endpoints
    (experiments/replication/diagnosis), `StepDiagnostics`/evaluation
    endpoints, and all frontend work -- see `/memories/session/plan.md` (agent
    session memory) for the full phased plan.

- Session-centric UI redesign, Phase 2 (step6/7/8 session endpoints): still
  no empirical logic changes, only new HTTP surface + one small
  `RunRegistry.get_by_id()` addition.
  - `backend/routers/experiments.py`: `POST /api/sessions/{sid}/steps/6/
    experiment` wraps `DualTrackController.run_experiment` as a job (an
    `ExperimentPlan` built from the request), persists every resulting
    `RunRecord` via `EvidenceStore`/`RunRegistry` (same as the existing
    `/api/backtest/run` route), and records `experiment_batch_id` +
    `execution_ids` on the session -- surfacing `batch_invalidated` honestly
    rather than hiding it.
  - `backend/routers/replication.py`: `POST /api/sessions/{sid}/steps/7/
    comparison` accepts *only* `experiment_batch_id` or a list of
    `execution_id`s (never client-supplied runs/config/metrics) -- looks the
    records up itself via the new `RunRegistry.get_by_id()`, rejects a batch
    spanning more than one factor/batch, rejects an invalidated batch, and
    -- since `comparison.json` is overwritten per-factor rather than
    versioned per-batch -- rejects the request outright (409) if the
    on-disk bundle's own recorded `batch.experiment_batch_id` no longer
    matches what was asked for, instead of silently serving a newer batch's
    numbers under an old batch's name. Never rebuilds the evidence bundle;
    only reads what `write_comparison_summary`/`build_evidence_bundle`
    already wrote. `GET .../steps/7/comparison` reads back the session's own
    recorded reference.
  - `backend/routers/diagnosis.py`: `POST /api/sessions/{sid}/steps/8/
    diagnosis` is opt-in (a separate job, never invoked by step6/7), requires
    step7's `comparison_ref` to already be recorded on the session, and a
    diagnosis failure is confirmed (by test) to never touch step7's recorded
    success status.
  - New tests: `tests/test_experiment_replication_diagnosis_api.py` (8),
    including a caught real architectural fact worth knowing: `RunRecord.
    run_id`/`execution_id` is deterministic from `(factor_id, track,
    code_hash, config_hash)` alone (`BacktestRunner.build_script`), so two
    experiment batches for the SAME factor/track/plugin/config collide on
    the same `run_id` and the second run's `RunRecord` silently overwrites
    the first in `RunRegistry` -- not a regression introduced here, just an
    existing property the new step7 endpoint's tests had to account for
    (see the test file's `_run_baseline_only_experiment(factor_id_suffix=...)`
    helper and the `test_stale_comparison_on_disk_is_rejected...` test's use
    of a differently-configured second batch to actually exercise the
    intended "comparison.json overwritten, RunRegistry entry NOT overwritten"
    case). Full suite now 438 passed, 26 skipped (zero regressions).
  - Still not done: `StepDiagnostics`/evaluation endpoints (Phase 3) and all
    frontend work (Phase 4) -- see `/memories/session/plan.md`.

### Changed

- Fixed a stale doc: `AGENTS.md`'s module map still described
  `src/steps/step6_dual_track_controller/` as having "basic" orchestration
  with repair-detection-only freeze/invalidation. The real auto-freeze
  (`_run_tracks_with_freeze`, bounded re-run under repair-disabled plugin),
  the merged `run_experiment`/`run_from_matrix` entry points, and bridge-track
  support (`is_bridge_track`) had already landed in prior sessions but were
  never reflected in the module map. Updated the row to match the current
  implementation. No code change; this is a pre-work checkpoint ahead of the
  session-centric web UI redesign (see `docs/decision-log.md`).

- Ran the real `scripts/run_real_asset_growth_experiment.py` matrix (7 tracks:
  original, standardized_hxz, 4 single-switch ablations, 1 factorial) against
  actual `data/local` WRDS CSVs end-to-end, then ran Step 8 (`analyze_comparison.py`,
  real `codex` LLM call, not `--dry-run`) against the resulting `comparison.json`.
  Found that `standardized_hxz`/`ablation_rebalance` (both `rebalance_frequency:
  monthly`) collapse to `n_months=74` (June-only) vs. 882 for the annual-rebalance
  tracks, because `_resample_annual_signal_asof`
  (`src/infra/backtest_engine/__init__.py`) only forward-fills an annual signal
  when `rebalance_frequency == "annual"`; this is existing, deliberately-tested
  behavior (`tests/test_calendar_rebalance.py`), not fixed in this pass.
  Confirmed by real, unmocked LLM output that this sample-size collapse silently
  contaminates `gap_decomposition.contributions.rebalance` (the largest OAT
  contribution, 1.43) -- the claim passed the existing validator uncaught,
  because nothing checked that the two t-stats being differenced came from
  comparable samples.
- Added a validator-only safeguard for this failure mode rather than fixing the
  engine gating: `src/steps/step8_diagnosis/__init__.py`'s `gap_attribution`
  entailment check now rejects any claim whose `ablation_<switch>` track's
  `n_months` differs from the baseline track's by more than 2x
  (`GAP_ATTRIBUTION_N_MONTHS_RATIO_THRESHOLD`), citing both n_months values and
  the mismatch ratio in the rejection reason so it shows up in the "Rejected
  claims (audit)" section of `diagnosis.md`. Re-ran the real experiment's Step 8
  diagnosis afterward and confirmed the `rebalance` attribution claim is now
  rejected while the (sample-comparable) `breakpoint` attribution claim still
  passes. New tests: `test_gap_attribution_is_rejected_when_ablation_track_
  sample_size_collapses`, `test_gap_attribution_is_accepted_when_sample_sizes_
  are_comparable` in `tests/test_replication_diagnosis.py`.

- Assessed C&Z bridge feasibility across the project's 10 test papers
  (`data/test_papers/`, 12 human-labeled MethodSpecs in
  `data/test_method_specs_human_labeled/`): read each factor's actual C&Z
  predictor script (where one exists) and classified it SIMPLE
  (single-source, clean lag) / COMPLEX (multi-source merge, rolling
  regressions, external patent/citation/options data) / NO_MATCH. Of the 11
  non-AssetGrowth factors, only ONE (`Valta_StrategicDefault_
  ConvertibleDebt`, Valta's convertible-debt indicator) qualified as SIMPLE;
  the rest need daily-return rolling correlations (Betting Against Beta),
  36-month rolling FF3 regressions (Residual Momentum), recursive SG&A
  depreciation with industry adjustment (Organization Capital), external
  patent/citation panels (Innovative Efficiency), or OptionMetrics implied
  volatility (the options-based factors) -- none of which are safely
  portable without substantially more infrastructure and individual
  verification. Registered the one that qualified:
  `src/infra/reference/cz_bridge.py`'s `convdebt_from_panel` is a direct
  port of `data/CZ code/Signals/pyCode/Predictors/ConvDebt.py`'s formula
  (`ConvDebt = 1 if dc != 0 or cshrc != 0 else 0`) -- the simplest of the
  three ported factors so far: single Compustat source, no lag/shift at
  all (contemporaneous), missing values treated as 0 (never dropped, since
  0 is itself a meaningful signal value here). New tests: 7 in
  `tests/test_cz_bridge.py`. Full suite: 386 passed, 26 skipped.

- Registered a SECOND real C&Z bridge factor, demonstrating
  `CZ_BRIDGE_SIGNALS` genuinely generalizes (registry pattern, not a single
  one-off): `src/infra/reference/cz_bridge.py`'s `accruals_from_panel` is a
  direct port of `data/CZ code/Signals/pyCode/Predictors/Accruals.py`'s
  Sloan (1996) working-capital-accruals formula, with the same documented
  12-months->1-row shift adaptation as `asset_growth_from_panel`. Verified
  against the exact `ACCRUAL_VALUES` golden fixture
  `tests/test_accruals_e2e.py` already depends on, through the real
  (unmocked) `assemble_signal_master_table_from_sources` call -- not just a
  hand-built panel. Module docstring rewritten to state plainly WHY full
  coverage of all ~200 C&Z predictors isn't attempted automatically: many
  (e.g. `BM.py`) need multi-source merges/PIT logic beyond a clean
  single-source lag formula, and porting those without individually
  verifying each script would risk silently WRONG bridge signals -- worse
  than no bridge. New tests: 7 more in `tests/test_cz_bridge.py` (unit tests
  for `accruals_from_panel` + a real synthetic-data integration test).
  Full suite: 379 passed, 26 skipped.

- Merged the legacy `ExperimentPlan` entry point and the new declarative
  `ExperimentMatrix` (yaml) entry point into ONE execution implementation:
  `DualTrackController.run_experiment` is now a thin adapter
  (`_plan_to_matrix`) over `run_from_matrix`, instead of two divergent
  code paths. `run_from_matrix` gained a `run_baseline: bool = True` param
  (`run_experiment` passes `plan.run_original`) so both entry points can
  still independently control whether the `original_method` baseline runs.
  New `experiment_spec.build_experiment_spec` is the single shared
  `family`/`identification_level` derivation both `load_experiment_matrix`
  (yaml) and `_plan_to_matrix` (Python plan) now call -- previously only
  the yaml path derived these; plan-based `ablation_*`/`standardized_hxz`
  tracks now get the same classification (and the same
  `experiment_spec_hash` auditability) for free.
  - Also implemented `ExperimentPlan.factorial_switches` -- declared since
    early in the project but never executed (see docs/multi-config-
    evidence-plan.md's explicit "don't leave two half-finished interfaces"
    note). `DualTrackController._factorial_track_specs` expands the full
    factorial (cartesian product of {baseline value, HXZ-standardized
    value} for each given switch, excluding the redundant all-baseline
    corner) -- de-duplicated by resulting track name, since a switch whose
    baseline coincidentally already equals its own HXZ value degenerates
    to fewer than 2^n distinct combinations (a real case caught while
    writing tests, not by accident later).
  - New tests: `tests/test_experiment_plan_matrix_merge.py` (10, covering
    the delegation, `run_baseline=False`, ablation/factorial classification,
    and the degenerate-switch dedup case). Full suite: 372 passed, 26
    skipped.

- Wired the C&Z bridge signal into an ACTUAL executable track, closing the
  gap the previous entry explicitly left open -- the core "bridge
  experiment" (Phase C/D's E2: same engine, same resolved config, only the
  signal source differs) now really runs, not just computes a standalone
  series:
  - `generate_backtest_script`/`script_generator`'s template gained a
    `precomputed_signal_path` mode: when set, the generated script SKIPS
    `compute_signal()` entirely and loads that parquet directly as the
    signal fed into `BacktestExecutor.run_with_config()` -- everything
    downstream (universe filter, breakpoints, portfolios, metrics, the
    `signal.parquet`/return-series artifacts) is byte-identical to a normal
    track. `BacktestRunner.build_script` threads this straight through.
  - New `DualTrackController._run_bridge_track`: computes the C&Z bridge
    signal, persists it to a real parquet file, builds+executes the script
    in that mode, and returns a `RunRecord` with the new
    `is_bridge_track=True` field and a descriptive (non-agent)
    `code_hash=f"cz_bridge:{factor_id}"`. Does NOT go through the shared
    bounded `RepairLoop` (a bridge track's content is an externally-supplied
    signal, not agent code -- nothing for `MetaCoder.repair_plugin` to fix).
  - `DualTrackController.run_from_matrix` now actually RUNS an experiment
    declaring `signal_input_ref: cz_bridge` (or `cz_bridge:<factor_id>` to
    reference a different registered factor) as a real bridge track instead
    of unconditionally skipping it; any other `signal_input_ref` value, or a
    `snapshot_ref`, is still recorded-but-skipped (no adapter exists for
    those).
  - `RunRecord.is_bridge_track` excludes bridge tracks from
    `_finalize_batch`'s "every track ran identical code" consistency check
    (Phase 0.6) -- a bridge track's entire point is a DIFFERENT signal
    source under the same config, a different comparison axis from
    config-only ablations.
  - **Verified with a real end-to-end run, not just fakes**:
    `tests/test_bridge_track_e2e.py` runs the AssetGrowth bridge track
    through the REAL `Pipeline`/`BacktestRunner`/subprocess chain against
    the same synthetic snapshot the MVP golden-number test uses, and gets a
    real `status="success"` `RunRecord` with populated metrics and a
    persisted signal series. New tests: `tests/
    test_script_generator_bridge_mode.py` (3), `tests/
    test_bridge_track_wiring.py` (5, fakes), `tests/test_bridge_track_e2e.py`
    (1, real subprocess). Full suite: 363 passed, 26 skipped.

- Added a REAL (not placeholder) C&Z signal bridge for one factor:
  `src/infra/reference/cz_bridge.py`'s `asset_growth_from_panel` is a direct
  port of C&Z's own `data/CZ code/Signals/pyCode/Predictors/AssetGrowth.py`
  formula (`(at - l.at) / l.at`, division-by-zero -> missing), computed
  against a REAL panel built by our own
  `assemble_signal_master_table_from_sources`. Their script isn't
  subprocess-executed (it imports `polars`, not a project dependency);
  instead their published formula is ported and verified line-by-line
  against their source. Documented, deliberate adaptation: their
  `m_aCompustat.parquet` is monthly/forward-filled (hence their literal
  `.shift(12)`), while our own panel is one row per firm-fiscal-year
  (`_load_generic_signal_frame`), so this ports it as a 1-row shift -- the
  same economic quantity ("prior fiscal year's assets") on the two
  different panel shapes. Verified against the SAME synthetic Compustat
  fixture the MVP e2e golden-number test uses
  (`tests/test_cz_bridge.py::TestRealSyntheticDataIntegration`, real
  `assemble_signal_master_table_from_sources` call, not mocked) --
  recovers the fixture's exact per-firm growth rates. `CZ_BRIDGE_SIGNALS`
  is a registry (`factor_id -> (sources, lag_months, compute_fn)`) so more
  factors can be added the same way when their C&Z formula is similarly a
  short, single-source transformation; `compute_cz_bridge_signal(factor_id,
  data_dir)` is the one public entry point. NOT yet wired into
  `DualTrackController` as an actual executable "bridge track" (running
  this signal through `BacktestExecutor` with the SAME config as the agent
  run, per Phase C/D's stated E2 experiment) -- that requires either a new
  script-generation mode (precomputed-signal input instead of
  `compute_signal()`) or an in-process engine entry point, which is the
  next concrete step. New tests: `tests/test_cz_bridge.py` (10). Full
  suite: 354 passed, 26 skipped.

- Completed Phase 0.6 (docs/multi-config-evidence-plan.md) as a FULL
  plugin freeze, not just detection: `DualTrackController.
  _run_tracks_with_freeze` runs a batch once with repair allowed, and if any
  track's repair changed its code away from the batch's frozen plugin, the
  WHOLE batch is now automatically RE-RUN from that newly-repaired plugin
  with repair disabled (`_NoRepairMetaCoder`, bounded to one re-freeze
  attempt by default) -- previously this only detected and flagged the
  violation, never corrected it. `_run_track` now returns `(record,
  plugin_used)` so callers can act on per-track code drift directly.
  A single-track "batch" never triggers a refreeze pass (consistency is a
  cross-track property). Because the frozen re-run pass never itself
  repairs, a track that still can't run under the shared re-frozen plugin
  simply becomes `status="failed"` rather than "successful but still
  divergent" -- so with the default of 1 re-freeze attempt,
  `batch_invalidated` now only fires in practice via the explicit
  `max_refreeze_attempts=0` escape hatch (exercised directly in
  `tests/test_batch_invalidation.py::TestZeroRefreezeAttemptsIsDetectionOnly`),
  not through `run_experiment`/`run_from_matrix`'s normal path. `comparison.json`'s
  `"batch"` key gained `refreeze_attempts` (0 when no repair ever fired) for
  auditability even when the batch converged. Full suite: 344 passed, 26
  skipped.

- Implemented `docs/multi-config-evidence-plan.md` Phase A1 (evidence
  bundle, bounded scope), Phase A2 (declarative experiment matrix), and a
  bounded slice of Phase B/C&D (external-reference contract layer +
  deterministic matched-sample comparison math). Full suite: 343 passed, 26
  skipped (was 283/26 after Phase 0).
  - **A1.1:** the generated backtest script now writes the REALIZED signal
    series to `<track>.signal.parquet` (`[permno, yyyymm, signal]`),
    captured right after `compute_signal()`, before any universe filter/
    breakpoint/portfolio step (`script_generator.py`'s `main()`).
  - **A1.2:** new `src/infra/hashing.py`: `artifact_sha256` (raw file-byte
    integrity) vs `series_semantic_hash` (canonicalized panel-content
    equality -- column selection, sort order, float rounding, and a
    canonical missing-value sentinel all normalized first) are kept as two
    deliberately different hash kinds, matching the plan's warning against
    conflating them.
  - **A1.4 (partial/approximated):** new `snapshot_manifest_hash()` in the
    same module populates `RunRecord.data_snapshot_hash` (declared on the
    model since Phase 0, never populated before) from `(relative_path,
    size_bytes)` pairs for files directly under a snapshot's `storage_path`
    and `storage_path/local`. Documented limitation: this is coarser than
    the full design (an exact manifest of files a run actually consumed,
    each individually content-hashed) -- an in-place edit that doesn't
    change file size won't change this hash, and it includes every file
    present, not only the ones a given run read.
  - **A1.6:** `EvidenceStore.save_run` now accepts optional `artifacts`
    (`{filename: source_path}`, copied) and `inline_content`
    (`{filename: text}`, written directly) params, copies the run's own
    `return_series_path`/`signal_series_path` in and rewrites those fields
    to the evidence-root-local copies, records each artifact's
    `artifact_sha256` in `run.logs`, and writes everything atomically (a
    `.staging` directory swapped into place with one `rename()` -- a
    mid-copy crash never leaves a `metadata.json` claiming artifacts exist
    that don't). `Pipeline.run_from_method_spec` now passes the script text
    + plugin code + MethodSpec JSON through on every save (success and
    failed runs alike).
  - `RunRecord.return_series_path`/`signal_series_path`/`data_snapshot_hash`
    (declared since Phase 0.5, never populated before) are now actually
    filled in by `BacktestRunner.make_run_record`.
  - **NOT implemented** (explicitly deferred, matching the plan's own
    phasing): persisting `breakpoints.parquet`/`assignments.parquet`/
    `portfolio_returns.parquet`/`diagnostics.json` intermediate artifacts --
    would require extending `BacktestExecutor.run_with_config`'s return
    contract, a deeper engine change with wide blast radius across every
    consumer (including golden-number tests), left for a dedicated pass.
  - **A2:** new `src/steps/step6_dual_track_controller/experiment_spec.py`:
    `load_experiment_matrix(path, spec)` loads/validates one
    `experiments/<factor_id>.experiments.yaml`, expands declarative `sweep`
    grids via cartesian product, and derives (never accepts as authored
    input) each experiment's `family`
    (`portfolio_ablation`/`signal_input`/`reference_bridge`/`data_vintage`)
    and `identification_level` (`controlled` iff exactly one resolved-config
    key differs from baseline, else `unidentified`) from the actual resolved
    config diff. The whole file is validated at load time via
    `registry.build_config`'s existing override validation (one bad entry
    fails the whole file); a no-op NAMED experiment is rejected outright,
    while a sweep-grid corner that happens to coincide with the baseline is
    silently skipped (the baseline is, by construction, always one point in
    a full grid -- not a caller mistake the way a hand-authored no-op is).
    `expected_diff`, when given, is cross-checked against the actual diff.
  - `DualTrackController.run_experiment`'s post-track-loop logic (batch
    invalidation bookkeeping + `write_comparison_summary`/diagnosis call) was
    factored into a shared `_finalize_batch` helper, now also used by the
    new `DualTrackController.run_from_matrix(plugin, spec, matrix,
    snapshot_id)`, which runs every experiment in a loaded `ExperimentMatrix`
    as its own track (plus the implicit `original_method` baseline),
    embeds `experiment_spec_hash` + each experiment's derived
    `family`/`identification_level` into the run logs / `comparison.json`'s
    `"batch"` key, and SKIPS (records, doesn't execute) any
    `signal_input_ref`/`snapshot_ref` experiment -- no C&Z bridge/data-vintage
    adapter exists yet to resolve those references (see Phase B below).
  - **Phase B (bounded -- metadata only, explicitly NOT a real signal
    bridge):** new `src/infra/reference/__init__.py`:
    `load_cz_reference_profile(acronym, signaldoc_path=None)` parses one
    factor's C&Z-reported summary numbers (mean return, t-stat, sign,
    weighting, breakpoint filter, sample window) from `SignalDoc.csv`,
    reusing the existing `evaluation.helpers.load_signaldoc` reader. This is
    METADATA ONLY -- it does not load or compute any real C&Z firm-level
    signal value. Doing that would require actually running C&Z's own
    `Predictors/*.py`/`Portfolios/Code/*.R` source (`data/CZ code/`) against
    real WRDS data, a separate, substantial data-integration task not
    attempted here.
  - **Phase C/D (bounded -- comparison math only, no live bridge
    execution):** new
    `src/steps/step7_replication_diff/matched_comparison.py`:
    `matched_sample_stats(signal_a, signal_b)` computes matched-sample
    coverage ratios, Pearson/Spearman correlation, sign-agreement rate, and
    cross-sectional (per-yyyymm) top/bottom-decile overlap between two
    `[permno, yyyymm, signal]` panels -- pure deterministic arithmetic, no
    LLM involvement, fully testable today with synthetic data. It consumes
    whatever two signal series it's given; no adapter yet supplies a REAL
    C&Z firm-level series as one of them (that's the actual "bridge" this
    utility is a prerequisite for, not a substitute for).
  - `Pipeline.run_full_pipeline`'s `PipelineStatus` gained `comparison_path`
    and `diagnosis` fields: after `run_experiment` finishes, the pipeline now
    reads back `results/<factor_id>/comparison.json`/`diagnosis.json` (both
    already written to disk by step 5/6/8) and surfaces them on the returned
    status object, instead of leaving the caller to know the on-disk path
    convention itself. Addresses the roadmap's "persisted and
    pipeline-returned diagnosis report" item for the ALREADY-COMPUTED
    deterministic bundle + optional LLM narrative; it reads existing files,
    it computes nothing new.
  - New test files: `tests/test_hashing.py` (15), `tests/
    test_evidence_store.py` (7), `tests/test_experiment_matrix.py` (16),
    `tests/test_run_from_matrix.py` (4), `tests/test_cz_reference_profile.py`
    (5), `tests/test_matched_comparison.py` (10), `tests/
    test_pipeline_status_artifacts.py` (2); plus one new test each in
    `tests/test_mvp_e2e.py` (real subprocess execution now asserts
    `signal.parquet`/`data_snapshot_hash` are actually produced).
  - **Explicitly NOT done, stated plainly (Phase B/C&D's real core, and
    Phase 0.6/A2's remaining pieces):** no adapter loads a REAL C&Z
    firm-level signal series (the actual "bridge" experiment -- Phase C/D's
    E2 -- cannot run without one); no batch-level plugin FREEZE that
    prevents a track-local repair (only post-hoc detection exists, Phase
    0.6); `run_from_matrix` does not yet drive the Streamlit UI's override
    controls; Phase A2's declarative matrix is not yet wired to the
    ablation/`ExperimentPlan` path used by existing callers (both entry
    points coexist). A genuine end-to-end validation run against a real
    factor satisfying all of docs/multi-config-evidence-plan.md's
    "Completion Criteria" has NOT been executed this session.


### Changed

- `src/steps/step3_codegen/registry.py`'s `build_config` no longer does a
  blind `config.update(overrides)`. Added `_validate_overrides` (Phase 0.2 of
  `docs/multi-config-evidence-plan.md`): an override for an unknown config
  key, or an off-menu value for a menu-governed key (`breakpoint_source`,
  `weighting_rule`, `missing_action`, `return_combination_type`), now raises
  `ConfigOverrideError` instead of being silently merged in or clamped away.
  An override whose value already equals the MethodSpec's own resolved
  default emits a `UserWarning` (not raised — a named track like
  `standardized_hxz` legitimately bundles several settings as one package,
  and one of them coinciding with the paper's own choice is a reportable
  fact, not a caller mistake). Verified live: `HXZ_STANDARD_CONFIG`'s
  overrides trigger this warning for several AssetGrowth-fixture keys with
  zero behavior change. Also moved the per-key stage taxonomy
  (`CONFIG_KEY_STAGE`/`stage_of`) from `src/steps/step7_replication_diff/
  bundle.py` into `registry.py` (single source of truth); `bundle.py` now
  re-imports the same objects so existing call sites are unaffected. New
  tests: `tests/test_config_override_validation.py` (11 tests). Full suite:
  264 passed, 26 skipped (was 253/26).

- Completed the rest of `docs/multi-config-evidence-plan.md` Phase 0
  (config/run identity), on top of Phase 0.1/0.2 above:
  - **0.3 (D4 fix):** `generate_backtest_script`'s `ACCOUNTING_LAG_MONTHS`
    used to be an independently-templated constant baked from
    `spec.accounting_lag_months or 6`, completely ignoring any
    `config_overrides={"accounting_lag_months": ...}` -- an
    "ablation_lag_12" experiment silently ran on the paper's own lag. Now
    `ACCOUNTING_LAG_MONTHS = CONFIG["accounting_lag_months"]` is read from
    the resolved config at script run time. New tests:
    `tests/test_script_generator_lag_override.py`.
  - **0.4 (D2 fix):** `RunRecord.run_id` used to be
    `f"{factor_id}_{track}_{code_hash[:8]}"` -- no `config_hash` component,
    so two different config overrides on the same track/plugin were
    indistinguishable by run_id. `BacktestRunner.build_script` now resolves
    the config ONCE (also fixing a redundant duplicate `build_config` call
    that silently double-emitted the new no-op-override warning) and
    computes `config_hash`/`execution_id` from it BEFORE the script is
    written/executed; `execute()` threads them through; `make_run_record`/
    `make_failed_run_record` use them as the run's real identity, falling
    back to the old format only for minimal test fakes that don't supply
    them. `generate_backtest_script` gained an optional `resolved_config`
    param so the config is resolved exactly once per script. New tests:
    `tests/test_run_identity.py`.
  - **0.5:** Added `src/infra/provenance.py`
    (`collect_runtime_provenance()`): every successful/failed RunRecord now
    carries `runtime_provenance` (git commit + dirty-worktree flag, a sha256
    of the single-file `BacktestExecutor` engine module's current on-disk
    content, interpreter version, pinned pandas/numpy/statsmodels/
    linearmodels versions, and the external FF-factor file's hash when one
    was supplied) and `lifecycle_commit` (previously declared on the model
    but never populated) is now filled in. Best-effort by design -- never
    raises, falls back to documented sentinels. New tests:
    `tests/test_runtime_provenance.py`.
  - **0.6 (partial):** `DualTrackController.run_experiment` now allocates an
    `experiment_batch_id` and records the `frozen_plugin_hash` (the plugin's
    `code_hash` before any track ran) on every `RunRecord` it produces. If a
    per-track technical repair (`RepairLoop`, on an execution failure) hands
    back a plugin with a DIFFERENT `code_hash` for one track, the entire
    batch -- not just that track -- is now marked
    `batch_invalidated=True` with a `batch_invalidation_reason` explaining
    which track(s) diverged, both on every `RunRecord` and embedded in
    `comparison.json`'s new `"batch"` key. This detects and surfaces the
    violation; it does not yet prevent the repair or re-run the batch from a
    re-frozen plugin (full matrix-freeze remains future work). New tests:
    `tests/test_batch_invalidation.py`.
  - Added new `RunRecord` fields: `runtime_provenance`,
    `experiment_batch_id`, `frozen_plugin_hash`, `batch_invalidated`,
    `batch_invalidation_reason`.
  - `BacktestRunner.write_comparison_summary` gained an optional
    `batch_info` param, embedded verbatim under `comparison.json`'s new
    `"batch"` key.
  - Full suite: 283 passed, 26 skipped (was 264/26).

- Step 8 replication-diagnosis contract (`src/infra/models/diagnosis.py`,
  `src/steps/step8_diagnosis/`, `prompts/analysis/replication_diagnosis.md`)
  moved from citation-shape validation to claim-entailment validation. A real,
  whitelisted evidence key no longer makes a claim automatically true: each
  `DiagnosisClaim` now carries a structured `relation` (e.g. `agrees` /
  `disagrees`, `larger` / `smaller` / `similar`) that the validator checks
  against the actual value of the cited key — a claim asserting `disagrees`
  while citing a `sign_agrees` key whose value is `true` is now rejected, and
  likewise for `significance`/`magnitude_gap` (checked against
  `track_significant`/`abs_spread_ratio`), `config_divergence` (now requires
  citing both `.baseline_value` and `.track_value` of the same key,
  symmetrically), and `gap_attribution`. `subject_track` must match the track
  named in the claim's own cited evidence. `stage`, `identification_level`,
  and `evidence_strength` are no longer LLM-authored fields: `stage` is
  derived from the cited `config_diff`/`gap_decomposition` key's own stage;
  `identification_level` (`controlled`/`harmonized`/`observational`/
  `unidentified`) is derived from claim type and the bundle's own tagging
  (`config_diff`/`gap_decomposition` now carry an explicit
  `identification_level`, since a config diff is merely observational while an
  OAT decomposition is one-at-a-time/harmonized and not a controlled design);
  `evidence_strength` is a deterministic mapping from `identification_level`,
  replacing the old unconstrained `confidence` self-rating. Added a causal-
  language ban (`drives`/`explains`/`caused by`/`due to`/...) enforced in the
  validator rather than only requested in the prompt, since this pipeline
  never produces a controlled/factorial design and one-at-a-time evidence
  cannot support causal wording. Renamed the `original_method` track's prompt
  description from "paper-faithful" to "the approved (reviewed) interpretation
  of the paper", since it may embed human resolutions of paper ambiguities and
  is not guaranteed to be the unique faithful implementation. Removed the
  "six to ten claims" prompt language that implied a minimum count. Schema
  bumped to v2.

### Fixed


- `BacktestRunner.build_script()` named its output script/CSV/metrics files by
  `spec.factor_id` alone, so `DualTrackController.run_experiment()`'s multiple
  tracks (`original_method`/`standardized_hxz`/`ablation_*`) for the same
  factor silently overwrote each other's on-disk artifact — only the
  in-memory `RunRecord` per track was ever reliable. Added an optional
  `track_name` parameter (threaded through `RepairLoop.build_validate_repair`/
  `execute_with_repair` and `DualTrackController._run_track`) so each track now
  persists to its own `{factor_id}__{track_name}` script/output path. Verified
  with a real `run_experiment()` call (original_method + standardized_hxz,
  one frozen plugin) against real WRDS data: both tracks completed and wrote
  distinct files.
- `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` was an invalid percentile list
  (`[10, 20, ..., 90]`) instead of the integer group count the engine actually
  reads (`int(config.get("breakpoint_quantiles", 10))`), so the
  `standardized_hxz` track has never been runnable (a known, previously
  documented but unfixed bug — see `docs/decision-log.md` 2026-08-02 entry).
  Fixed to `10` (decile sort). Verified with the same real
  `standardized_hxz` run above.

- `prompts/review_gate/methodspec_audit.md` (the live system prompt driving
  `ReviewGate.review_with_llm`, fed `spec.model_dump()` of the current FLAT
  `MethodSpec`) described a stale/nonexistent curated-schema shape in several
  sections — top-level `paper.*`/`sample.*`/`universe.*`/`formula_convention.*`/
  `input_return.*` objects, `calculation_steps`/`formula.inputs`,
  `robustness_or_secondary_specs`/`extensions`/`annotator_notes`,
  `portfolio.sorts` (plural) — none of which exist on the real model. This
  caused the LLM reviewer to emit confusing "schema-incompatible" P0 findings
  and invented `blocked_fields` dotted paths (e.g. `sample.return_sample`,
  `universe.winsorize_bounds` without the existing `resolution.py`
  `PATH_ALIASES` mapping) that don't resolve against the actual spec, so a
  human resolving them via `scripts/resolve_review_blocks.py` would silently
  write into a dead location. Rewrote the affected sections (4.1/4.2/4.4/4.6/
  5.1/5.3 + a few stray mentions) to reference the real flat paths
  (`paper_ref`, `sample_start_year`/`sample_end_year`, `portfolio.universe`,
  `portfolio.universe_filters[]`, `signal.missing_policy.*`,
  `signal.required_fields[]`, `portfolio.sort`, `ambiguous_fields`/
  `unsupported_fields`). Verified end-to-end by re-running `review_with_llm`
  on a real extracted spec (AB1998_ETR, Abarbanell & Bushee 1998): before the
  fix `blocked_fields` was `['signal.formula.expression', 'sample.return_sample',
  'universe.winsorize_bounds']`; after, it correctly resolves to
  `['factor_id', 'signal.formula.expression']`. Found via a full manual
  `run_full_pipeline` dry run against real `data/local` WRDS data — see
  `docs/decision-log.md`.
- Review Gate never consulted `MethodSpec.resolution_log`, so a field a human
  already resolved via `scripts/resolve_review_blocks.py` (genuinely
  paper-silent + high-impact) got re-blocked on the exact same "paper doesn't
  state this" reasoning every time the resolved spec was re-reviewed — an
  infinite loop, since that reasoning never stops being true. Added
  `_resolved_by_human()` (checks `resolution_log` for a matching
  field_path+value) to `src/steps/step2_reviewer/__init__.py`, wired into the
  3 deterministic blocking checks and as a code-level backstop in
  `_raw_to_review_result` for the LLM path (doesn't rely on prompt
  compliance) — with one override preserved: a field_note carrying new,
  non-empty paper evidence can still legitimately re-block (a real
  contradiction), but an evidence-less re-block is always downgraded to a
  warning. Updated `prompts/review_gate/methodspec_audit.md` (§1.2.1) and
  `_LLM_REVIEW_CONTRACT` to match. Verified live on AssetGrowth (Cooper,
  Gulen & Schill 2008): 3 previously-reblocked fields
  (`portfolio.weighting`/`long_leg`/`return_combination`) downgraded to
  warnings on the next review pass; a genuinely new, not-yet-resolved field
  (`portfolio.sort.breakpoint_source`) still correctly blocked. Full suite:
  209 passed, 26 skipped. See `docs/decision-log.md`.
- Continuing the same real end-to-end run (AssetGrowth / Cooper, Gulen &
  Schill 2008, full real `data/local` WRDS CSVs) past review, 4 more codegen/
  data-layer bugs surfaced and were fixed:
  - `SemanticExtractor` never called `DataDictionary.normalize_fields()`, so
    `data.normalized_mapping` stayed permanently empty for every freshly
    extracted spec, passing review silently (an empty mapping isn't
    distinguished from "nothing to resolve") but crashing codegen's
    `pick_signal_input_mode()`. Now auto-populated in
    `SemanticExtractor._build_method_spec_from_llm()`; also added a new
    ReviewGate hard block (`data.normalized_mapping[empty]`) as a backstop.
  - `MetaCoder._build_prompt()` leaked `normalized_mapping`'s raw dict repr
    as a literal column name when it used the richer `{"source","column"}`
    form, and included universe/sample fields (not just the formula's own
    inputs) in the prompt — together causing the LLM to bake broken
    universe/exchange/SIC filtering INSIDE `compute_signal()` (a hard rule
    violation) using a nonsense column name. Fixed to restrict the prompt to
    `spec.required_fields` only, extract the real `.column`, and explicitly
    forbid universe/sample filtering inside the plugin.
  - `signal_input_sources()` didn't dedupe physical columns per source, so
    two paper concepts sharing one physical column at different lags (e.g.
    asset growth's `total_assets_t_minus_1`/`total_assets_t_minus_2`, both
    Compustat `at`) produced a duplicate-column select, crashing
    `df.groupby(...)[col] = ...` in the generated plugin. Now deduplicated.
  - The generated script's `main()` multi_source branch called
    `build_crsp_monthly_panel_ciz(SIGNAL_DATA_DIR)` directly, but
    `SIGNAL_DATA_DIR` is the PARENT of the raw-CSV `local/` folder (the same
    convention `assemble_signal_master_table_from_sources()` uses internally)
    while that function wants the actual CSV directory — fixed to append
    `/ "local"`, matching the equivalent fix already made to `load_msf()`'s
    CIZ fallback.
  All 4 verified against the real `data/local` WRDS CSVs (not samples) —
  reached `BacktestExecutor.run_with_config()` computing a real signal
  (285k observations, 24.7k firms, 1951–2026). Full suite stayed 209
  passed/26 skipped throughout. A genuine, NOT-fixed methodological gap was
  also found at this point (flat `accounting_lag` doesn't produce a uniform
  annual formation month for firms with non-December fiscal year-ends —
  `BacktestExecutor._validate_annual_formation_month` correctly rejects it;
  fixing this needs a per-firm variable-lag concept the schema doesn't have
  yet) — documented, not fixed, see `docs/decision-log.md`.
- Generalized annual accounting-factor timing with an engine-level
  calendar-lag/as-of alignment step. For explicit annual formation-month
  specs, `BacktestExecutor` now samples each stock's latest already-available
  signal as of the reviewed formation month, bounded by
  `signal_max_staleness_months` (default 11 months, matching C&Z's 12-month
  forward-fill window). Monthly/quarterly strategies and already-aligned
  annual signals remain on the old path. This unblocked the real full-WRDS
  AssetGrowth execution through metrics while preserving all existing tests.
- `compute_factor_alphas` now drops NaN/inf rows separately for each CAPM/FF3/
  FF5 regression before calling statsmodels, instead of crashing when the
  external factor file has missing/non-finite observations in an overlapping
  month.

### Added

- Per-factor results layout: `BacktestRunner.build_script(track_name=...)` now
  writes each track's CSV/metrics under `results/<factor_id>/<track_name>.csv`
  (was a flat `results/` directory), and
  `BacktestRunner.write_comparison_summary()` aggregates every executed
  track's resolved config + metrics alongside the paper's own reported
  results (`spec.reported_results`) into one `results/<factor_id>/
  comparison.json` — self-contained enough to hand directly to an LLM/human
  without opening each track's separate script/metrics file.
- **Replication-diagnosis layer (step 8), LLM-assisted but not
  LLM-controlled** — implements Phase E of
  `docs/multi-config-evidence-plan.md`:
  - `comparison.json` schema bumped to v2: alongside `paper_reported`/
    `tracks`, it now embeds a fully deterministic evidence bundle
    (`src/steps/step7_replication_diff/bundle.py`) — per-track vs-paper
    deltas (`sign_agrees`, `abs_spread_ratio`, `*_significant` at a fixed
    |t|≥1.96 threshold), a baseline-vs-track `config_diff` tagged by pipeline
    stage (`signal_input`/`portfolio`/`universe`/`sample`/`estimator`), the
    OAT `gap_decomposition` (explicit "unmeasured, not zero" when no
    `ablation_*` tracks ran), and a flat `evidence_keys` whitelist. All of it
    is pure arithmetic over numbers already on disk; the deterministic
    `overall_tag` verdict (`close_replication`/`sign_agrees_magnitude_differs`/
    `sign_mismatch`/`inconclusive`) is computed here, never by an LLM.
  - Fixed defect D9 (`docs/multi-config-evidence-plan.md`): `Pipeline.
    run_full_pipeline`'s `ReplicationDiff.diff_ablation(runs)` result was
    computed and discarded; now captured on `PipelineStatus.replication_diff`
    and threaded into the comparison bundle. Added
    `safe_diff_ablation()` (returns `None` instead of raising when the
    required tracks are absent) so a single-track experiment doesn't crash
    this step.
  - New `src/steps/step8_diagnosis/`: `ReplicationDiagnoser` prompts an LLM
    (`prompts/analysis/replication_diagnosis.md`) for structured
    `DiagnosisClaim`s (`src/infra/models/diagnosis.py`), each required to cite
    `evidence_keys` from the bundle. A validator rejects any claim containing
    a digit (numbers must come from the bundle, never be authored by the
    LLM), any claim citing a key outside the whitelist, and any claim whose
    `claim_type` isn't backed by the evidence shape it requires (e.g. a
    `significance` claim must cite a `*_significant` key, a `gap_attribution`
    claim must cite a measured OAT contribution) — rejected claims are kept
    in `rejected_claims` for audit rather than silently dropped. A
    deterministic renderer (`step8_diagnosis/render.py`) then writes
    `diagnosis.md`/`diagnosis.json`, re-inserting every cited value straight
    from the bundle so the report stays reproducible with the LLM switched
    off. The whole artifact is tagged `status: "llm_assisted_proposal"`.
  - Wired as strictly opt-in (`run_diagnosis=False` default on `Pipeline`, no
    `diagnoser` by default on `DualTrackController`) so tests and batch runs
    never spend an unwanted LLM call. New
    `scripts/analyze_comparison.py --factor-id <id> [--dry-run]` runs the
    layer standalone (`--dry-run` inspects the deterministic bundle only, no
    LLM call).
  - Verified against the real AssetGrowth (Cooper, Gulen & Schill 2008)
    comparison bundle via codex: correctly flagged the standardized track's
    spread-sign mismatch vs. the paper and both tracks' loss of statistical
    significance, attributed the standardized-vs-original divergence to the
    `breakpoint_source`/`rebalance_frequency`/`holding_period_months`/
    `universe` config keys, and correctly reported the OAT gap decomposition
    as unavailable (no `ablation_*` tracks were run) rather than inventing an
    attribution — 9/9 claims passed validation on this run.
  - New `tests/test_replication_diagnosis.py` (33 tests, all against a fake
    LLM client — no real LLM call in the suite): bundle arithmetic, the
    "missing evidence ≠ zero" gap-decomposition handling, whitelist
    validation, all rejection paths, and renderer figures coming from the
    bundle rather than claim text.

### Changed


- Consolidated active documentation around the current research target:
  paper-first MethodSpec extraction, formula-only plugin generation,
  deterministic backtesting, independent C&Z comparison, and planned
  multi-config evidence/bridge diagnosis.
- Replaced the historical phase-by-phase roadmap with a concise current roadmap.
- Consolidated the multi-config implementation plan into one canonical Chinese
  document: `docs/multi-config-evidence-plan.md`.
- Renamed active “Ground Truth” terminology:
  human-labeled MethodSpecs are “Curated Reference Specs”; C&Z artifacts are
  post-hoc/independent replication references, never empirical ground truth.
- Configured pytest to collect only `tests/`, preventing accidental collection
  of third-party C&Z scripts under `data/CZ code/`.
- Clarified the parallel UI migration: Streamlit remains the complete research
  UI while React/FastAPI reaches feature parity; both reuse `src/` logic.

### Added

- MethodSpec distinction between `unspecified` (paper silent) and `other`
  (paper explicit but engine-unsupported), with the literal paper value stored
  in `unsupported_fields`.
- Deterministic `build_config` substitution provenance and dedicated ReviewGate
  handling for unsupported paper values.
- Regression coverage for unsupported fields, including the Novy-Marx
  `capped_vw` MethodSpec fixture.
- Python 3.11 project pin and optional `openassetpricing==0.0.2` evaluation
  dependency for C&Z reference downloads.

### Removed

- Dead hook-era dashboard code and comments.
- `scripts/test_codegen.py`, which called removed hook APIs.
- The stale MethodSpec markdown template; the Pydantic model and extractor
  prompt are the authoritative contracts.
- Unreferenced hook-era HXZ/Novy-Marx plugin fixtures and dead hook code from
  the active Sloan fixture.
- Unused `Evaluator` stubs, the orphan `FactorSpec` model, and the obsolete
  `csv_to_gold_standard.py` workflow.
- Tracked macOS `.DS_Store` metadata (already covered by `.gitignore`).
- Redundant BacktestExecutor config-resolution compatibility delegates; engine,
  script generation, and dashboard now use the single codegen registry source.
- The duplicate English multi-config plan and obsolete CHANGELOG release
  history. Historical methodology decisions remain in `docs/decision-log.md`.

### Fixed

- Dashboard plugin generation no longer calls removed hook APIs.
- Dashboard backtest execution now passes the supported `signal_data_dir`
  argument instead of removed `compustat_data_path`/`ccm_link_path` arguments.
- Removed the non-functional Attribution dashboard path and replaced it with an
  honest Replication Diagnosis status view.
- Plugin Registry documentation now reflects its active in-memory use.

### Known Gaps

- Unique multi-config run identity, complete evidence persistence, strict config
  validation, declarative experiment matrices, C&Z signal bridge execution,
  and persisted diagnosis reports are designed but not implemented.
- `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` still needs to be aligned with
  the engine’s supported quantile-count contract and covered by a real-runner
  smoke test.
