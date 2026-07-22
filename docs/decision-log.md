# Decision Log

Record of challenging or major decisions and the reasoning behind them.
The goal is to preserve enough context (problem, alternatives considered, why we
chose what we chose, empirical impact) to later cite and justify these choices
when writing the paper.

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
