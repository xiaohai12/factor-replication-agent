# Factor Replication Agent Roadmap

## 0. Current Baseline

The project foundation is in place:

- The core positioning is clear: let the LLM write factor signal logic, not control empirical conclusions.
- `docs/architecture.md` defines the Controlled Meta-Coder + Adversarial Sandbox architecture.
- The repository structure has been organized around `docs/`, `prompts/`, `schemas/`, and `runs/method_specs/unreviewed/`.
- `MethodSpec` has been upgraded toward the `methodspec.v1` paper-first schema.
- Module skeletons exist for all pipeline components; most backtest and data-layer methods are stubs (`raise NotImplementedError`).

---

## 1. MVP: End-to-End Minimal Workflow

**Status: done (2026-07-17).** `Pipeline.run_from_method_spec()` runs the curated-MethodSpec
chain (MetaCoder/repair loop → Sandbox → `assemble_signal_master_table()` → plugin
`compute_signal()` → `BacktestEngine.run()` → `EvidenceStore`) against the synthetic data in
`data/synthetic_data/`, and `tests/test_mvp_e2e.py` verifies the `cooper_gulen_schill_2008_asset_growth`
result against independently-derived golden numbers
(`tests/synthetic_data/asset_growth_synthetic_data.py`). `ReviewGate` still requires a live LLM
client and is exercised manually / via `scripts/`, not in the deterministic synthetic-data test.
`DualTrackController` remains a stub — it is explicitly scoped to Phase 5, not the Phase 1 MVP
chain. The extraction-driven `Pipeline.run_factor()` (SemanticExtractor → ReviewGate → MetaCoder
→ Sandbox → DualTrackController → AttributionLayer) was removed 2026-07-22 — it had no callers
anywhere in the repo and its backtrack loops (beyond Sandbox→Meta-Coder repair) were never more
than TODO stubs; see `docs/decision-log.md`. The same day it was reinstated as
`Pipeline.run_full_pipeline()`, this time fail-fast with no fake backtrack claims (only the real
Sandbox→Meta-Coder repair loop, shared with `run_from_method_spec()`), plus every step reachable
standalone via `pipeline.extractor`/`.review_gate`/`.meta_coder`/`.sandbox`/`.runner`/
`.controller`/`.replication_diff` for step-by-step testing.

**2026-07-22 loop redesign.** `run_full_pipeline()` now has two implemented, bounded automatic
feedback loops (see `docs/architecture.md` §3.1): (1) the shared technical `RepairLoop`
(`src/infra/repair.py`) used by all three call sites, with a persisted `RepairAttempt` audit
trail; and (2) a Review→Extractor targeted re-extraction loop (`MAX_REEXTRACT=2`) — when the LLM
reviewer flags a high-impact field as mis-extracted with a paper citation, the extractor re-reads
just those passages. There is deliberately no automatic *empirical* backtrack from later stages;
step 7 (`ReplicationDiff`, renamed from `attribution`) reports the replication gap for a human to
interpret rather than auto-correcting it.

**Future improvements (deferred, not yet built):**
- Degenerate/empty backtest result (e.g. universe filter drops all rows) → auto-flag
  `needs_review` and stop for a human, never auto-fix the empirical params.
- Per-field `EvidenceSource` differentiation in the extractor (currently hardcoded `INFERRED`),
  which would let the Review→Extractor trigger be partly deterministic instead of LLM-only.

**Goal:** run one complete factor replication workflow with every component genuinely implemented — no stubs, no mock returns, no `raise NotImplementedError` shortcuts.

The MVP deliberately starts from a **curated MethodSpec** (human-written) rather than an LLM-extracted one. This isolates the pipeline from extraction quality issues so that module boundaries and empirical logic can be validated cleanly first. Extraction is added in Phase 2.

MVP chain:

```text
curated MethodSpec
-> Review Gate          (real LLM review, Evidence × Impact matrix)
-> MetaCoder            (real LLM plugin generation, repair loop)
-> Adversarial Sandbox  (syntax, schema, future-leak, reproducibility)
-> DataLayer            (synthetic parquet → SignalMasterTable)
-> BacktestEngine       (all 10 steps on synthetic data)
-> EvidenceStore        (RunRecord with hashes persisted)
```

This phase uses synthetic data (small deterministic parquet snapshots), not WRDS production data.

### What "genuinely implemented" means per module

| Module | What must be real |
|---|---|
| `ReviewGate` | LLM review runs, Evidence × Impact matrix fires, disposition (`auto_approve` / `needs_human_confirmation` / `blocked`) is returned |
| `MetaCoder` | LLM prompt is sent, plugin code is generated, repair loop runs up to 3 retries for syntax/schema errors only |
| `AdversarialSandbox` | Syntax check, schema check, future-leak scan (`shift(-`, `.future`, `lead(`), reproducibility check all execute |
| `DataLayer` | `SnapshotManager` loads synthetic parquet; the declarative `assemble_signal_master_table()` links gvkey→permno point-in-time and stamps `time_avail_m` on synthetic data (via the `sources.py` DataSource registry) |
| `BacktestEngine` | All 10 steps run on synthetic data: load → lag → missing policy → universe filter → breakpoints → portfolio assignment → EW returns → long-short → metrics → evidence log |
| `EvidenceStore` | `RunRecord` with MethodSpec hash, plugin code hash, synthetic-data snapshot hash, and metrics is persisted to `runs/evidence/` |

Synthetic data requirements:
- Synthetic CRSP monthly returns parquet (~50 stocks × 60 months)
- Synthetic Compustat annual parquet (same permno universe)
- CCM link table (synthetic)
- Pre-computed expected output (golden numbers) for at least one factor so correctness can be verified, not just reproducibility

### Deliverables

- Synthetic parquet files in `data/synthetic_data/`.
- All `raise NotImplementedError` stubs removed from the MVP path.
- `BacktestEngine` 10-step lifecycle fully implemented on synthetic data.
- `MetaCoder.generate_plugin()` and `repair_plugin()` fully implemented.
- `DataLayer` CCMLinker, TimeAvailComputer, SnapshotManager implemented on synthetic data.
- One curated MethodSpec (e.g., `AssetGrowth`) runs end-to-end.
- Evidence artifacts saved and traceable.
- A test that checks synthetic-data output matches the pre-computed golden numbers.

### Completion criteria

- One command runs one factor through the full MVP chain with no stub bypasses.
- The result matches the pre-computed golden numbers on synthetic data (correctness, not just reproducibility).
- Every module executes real logic: no mock returns, no hardcoded outputs.
- Evidence traces MethodSpec hash, plugin code hash, synthetic-data snapshot hash, and metrics.
- When ReviewGate blocks or MetaCoder exhausts repair retries, the run fails with a clear, traceable error — no silent fallbacks.

---

## 2. Semantic Extraction

**Goal:** add the paper-to-MethodSpec step so the pipeline no longer requires human-curated input.

The Extractor was intentionally excluded from Phase 1 to isolate pipeline correctness from extraction quality. Phase 2 adds extraction and makes its quality measurable.

Core work:

- Load extractor prompts from `prompts/extractor/`.
- Extract draft MethodSpecs from PDF or paper text for the pilot factor set.
- Compare extracted MethodSpecs against curated MethodSpecs field by field.
- Produce extraction evaluation reports.
- Identify common LLM failure modes: formula misreads, missing timing assumptions, ambiguous weighting or breakpoints, incorrect reported results, hallucinated defaults.

### Deliverables

- `runs/method_specs/unreviewed/` — raw LLM-extracted specs.
- `runs/method_specs/reviewed/` — after ReviewGate pass.
- Field-level extraction accuracy report per paper.
- A benchmark over the curated pilot papers.

### Completion criteria

- The system generates MethodSpecs for the pilot papers from PDF without human input.
- Field-level differences are classified as: correct / wrong / missing / paper ambiguous.
- ReviewGate blocks high-impact ambiguity from entering code generation.
- Extraction accuracy is measured and logged, not just eyeballed.

---

## 3. Plugin Quality Iteration

**Goal:** improve MetaCoder output quality through prompt engineering and evaluation, not by bypassing sandbox constraints.

MetaCoder is already implemented in Phase 1. Phase 3 is about measuring and improving the quality and pass rate of generated plugins — how often does the LLM get it right on the first try? What failure modes does it have?

Core work:

- Run MetaCoder on the pilot factor set and log first-pass sandbox pass rates.
- Analyze failure modes: wrong output schema, unauthorized portfolio logic, future leakage, formula errors.
- Iterate on prompts and few-shot examples to improve pass rate.
- Document which types of factors are reliably generated vs. still require repair or fail.

### Deliverables

- Generated plugin artifacts for pilot factors.
- Plugin registry records with validation reports.
- First-pass and post-repair pass rate metrics.
- Documentation of failure patterns and prompt improvements.

### Completion criteria

- At least one LLM-generated plugin passes Sandbox validation first-pass.
- Pass rate across pilot factors is measured and tracked.
- Plugins consistently output only `[permno, yyyymm, signal]`.
- Plugins cannot decide universe, breakpoints, weighting, returns, or t-stats.

---

## 4. Real Data Layer

**Goal:** move from synthetic data to frozen real-data snapshots (WRDS CRSP + Compustat).

The backtest engine and data layer are already implemented in Phase 1 on synthetic data. Phase 4 is a data swap: same logic, real data. The main new work is data pipeline correctness and snapshot management.

Core work:

- Build a data pipeline that reads from WRDS CRSP and Compustat, applies CCM linking, computes `time_avail_m`, and writes a frozen parquet snapshot.
- Add snapshot hash to run records.
- Add data quality checks: coverage stats, missing-rate flags, CCM link anomalies.
- Validate that real-data backtest outputs are plausible for at least one known factor.

### Deliverables

- Data snapshot builder script.
- At least one frozen snapshot in `data/snapshots/`.
- Snapshot hash in all run records.
- Data quality check output.

### Completion criteria

- At least one factor runs on a real data snapshot.
- Run records the snapshot hash for reproducibility.
- Engine parameters come from approved MethodSpec or implementation config only — no LLM-chosen parameters.
- Data quality checks pass or surface known issues explicitly.

---

## 5. Dual-Track and Attribution

**Goal:** explain replication gaps across implementation choices.

Core work:

- Support `original_method` and `standardized_hxz` tracks via `DualTrackController`.
- Add ablations: weighting, breakpoints, lag, rebalance frequency, universe, missing policy.
- Produce gap attribution reports.
- Route anomalies back to Review Gate when results suggest MethodSpec or timing issues rather than silently tuning.

### Deliverables

- Original vs. standardized comparison report.
- Attribution report per implementation-choice switch.
- Implementation-choice deviation matrix.

### Completion criteria

- A factor runs original, standardized, and selected ablation tracks.
- The system attributes which implementation choice drives the main result gap.
- Anomalous results (sign flip, >50% t-stat gap) trigger MethodSpec re-review, not silent tuning.

---

## 6. Evaluation Against C&Z / OSAP

**Goal:** compare system outputs against external benchmarks without leaking them into extraction.

Core work:

- Evaluate MethodSpec extraction accuracy against curated specs and SignalDoc.
- Compare generated signal output with C&Z firm-level characteristics.
- Compare long-short returns with C&Z return series.
- Classify mismatches: LLM extraction error / paper ambiguity / C&Z supplemented assumption / implementation difference / data coverage issue.

### Deliverables

- Extraction evaluation report.
- Signal correlation report.
- Portfolio replication report.
- Cross-factor summary.

### Completion criteria

- Pilot factors have systematic evaluation reports.
- C&Z / OSAP are used only as post-hoc evaluation sources, never as extractor inputs.

---

## 7. Research UI

**Goal:** make the system usable as a research workflow, not only a collection of scripts.

Core work:

- Build a lightweight Streamlit dashboard after CLI workflows are stable.
- Display MethodSpecs, review reports, plugin validation reports, run metrics, return charts, and attribution reports.
- Keep UI as an artifact viewer and workflow launcher — no core business logic in the UI.

### Deliverables

- Factor-level evidence page.
- Run comparison page.
- Attribution report viewer.

### Completion criteria

- A researcher can inspect one factor from paper evidence to final run output.
- Blocked or ambiguous fields are visible and not hidden by the UI.

---

## Phase Execution Order

```text
1. MVP              — synthetic data, all modules real, curated MethodSpec as input
2. Extraction       — add paper→MethodSpec step, measure extraction quality
3. Plugin quality   — measure and improve MetaCoder pass rates
4. Real data        — swap synthetic data for frozen WRDS snapshots
5. Dual-track       — original vs. standardized, gap attribution
6. C&Z evaluation   — benchmark against external reference
7. Research UI      — dashboard for artifact inspection
```

The boundary between phases is intentional:

- Phases 1–3 can be done without WRDS access (synthetic data + LLM API).
- Phase 4 requires WRDS access; it only changes the data source, not the engine logic.
- Phases 5–7 build on a working real-data pipeline.
