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
