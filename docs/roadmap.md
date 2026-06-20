# Factor Replication Agent Roadmap

## 0. Current Baseline

The project foundation is in place:

- The core positioning is clear: let the LLM write factor signal logic, not control empirical conclusions.
- `docs/architecture.md` defines the Controlled Meta-Coder + Adversarial Sandbox architecture.
- The repository structure has been organized around `docs/`, `prompts/`, `schemas/`, and `data/method_specs/curated/`.
- `MethodSpec` has been upgraded toward the `methodspec.v1` paper-first schema.
- Initial skeletons exist for the Semantic Extractor, Review Gate, Sandbox, Pipeline, Evidence Store, Registry, and Attribution Layer.

## 1. MVP: End-to-End Minimal Workflow

Goal: run one complete factor replication workflow with the smallest practical implementation.

MVP chain:

```text
curated MethodSpec
-> Review Gate
-> simple signal plugin
-> Sandbox validation
-> fixture backtest data
-> Controlled Engine
-> RunRecord / Evidence output
```

This phase should use fixture data, not WRDS production data. The goal is to validate module boundaries, artifact flow, and reproducibility before adding real data complexity.

Deliverables:

- Validate curated MethodSpecs against the current schema.
- Review one MethodSpec through Review Gate.
- Run a fixed hand-written plugin for one factor, such as `AssetGrowth`.
- Execute a small long-short backtest on fixture data.
- Save run metadata, config, metrics, and evidence artifacts.

Completion criteria:

- One command can run one factor through the MVP workflow.
- The result is deterministic and reproducible.
- Evidence can trace the MethodSpec, plugin, config, and metrics.

## 2. MethodSpec Quality

Goal: make paper-to-MethodSpec extraction measurable and iteratable.

Core work:

- Load extractor prompts from `prompts/extractor/`.
- Extract draft MethodSpecs from PDF or paper text.
- Compare extracted MethodSpecs against curated MethodSpecs field by field.
- Produce extraction evaluation reports.
- Identify common LLM failure modes, including formula misreads, missing timing assumptions, ambiguous weighting or breakpoints, incorrect reported results, and hallucinated defaults.

Deliverables:

- `data/method_specs/extracted/`
- `data/method_specs/reviewed/`
- Extraction accuracy reports.
- A benchmark over the curated pilot papers.

Completion criteria:

- The system can generate MethodSpecs for the pilot papers.
- Field-level differences are classified as correct, wrong, missing, or paper ambiguous.
- Review Gate blocks high-impact ambiguity from entering code generation.

## 3. Signal Plugin Generation

Goal: implement the Controlled Meta-Coder while keeping LLM output restricted to signal construction.

Core work:

- Define and enforce the signal plugin contract.
- Generate plugins from approved MethodSpecs.
- Validate plugins in the Sandbox for syntax, entrypoint, output schema, future leakage, unauthorized portfolio logic, and deterministic output.
- Allow bounded repair only for technical errors.

Deliverables:

- Generated plugin artifacts.
- Plugin registry records.
- Validation reports.
- A small set of generated plugin examples.

Completion criteria:

- At least one LLM-generated plugin passes Sandbox validation.
- Plugins output only `[permno, yyyymm, signal]`.
- Plugins cannot decide universe, breakpoints, weighting, returns, or t-stats.

## 4. Controlled Backtesting Engine

Goal: move from fixture data to a controlled empirical lifecycle.

Core work:

- Implement Data Layer components: data dictionary, snapshot manager, CCM linking, and `time_avail_m`.
- Implement the controlled engine lifecycle: universe filtering, missing policy, breakpoint computation, portfolio assignment, EW/VW returns, long-short returns, and metrics.
- Introduce frozen data snapshots for reproducibility.

Deliverables:

- Real-data backtest engine.
- Data snapshot convention and metadata.
- Snapshot hash in run records.
- Data quality checks.

Completion criteria:

- At least one factor can run on a real data snapshot.
- The run records the data snapshot hash.
- Engine parameters come from approved MethodSpec or implementation config, not from free-form LLM choices.

## 5. Dual-Track and Attribution

Goal: explain replication gaps across implementation choices.

Core work:

- Support `original_method` and `standardized_hxz` tracks.
- Add ablations for weighting, breakpoints, lag, rebalance frequency, universe, and missing policy.
- Produce gap attribution reports.
- Route anomalies back to Review Gate when results suggest MethodSpec or timing issues.

Deliverables:

- Original vs standardized comparison report.
- Attribution report.
- Implementation-choice deviation matrix.

Completion criteria:

- A factor can run original, standardized, and selected ablation tracks.
- The system can explain which implementation choices drive the main result gap.
- Anomalous results trigger MethodSpec re-review instead of silent tuning.

## 6. Evaluation Against C&Z / OSAP

Goal: compare system outputs against external benchmarks without leaking them into extraction.

Core work:

- Evaluate MethodSpec extraction against curated specs and SignalDoc.
- Compare generated signal output with C&Z firm-level characteristics.
- Compare long-short returns with C&Z return series.
- Classify mismatches as LLM extraction error, paper ambiguity, C&Z supplemented assumption, implementation difference, or data coverage issue.

Deliverables:

- Extraction evaluation report.
- Signal correlation report.
- Portfolio replication report.
- Cross-factor summary.

Completion criteria:

- Pilot factors have systematic evaluation reports.
- C&Z / OSAP remain post-hoc evaluation sources, not extractor inputs.

## 7. Research UI

Goal: make the system usable as a research workflow, not only a collection of scripts.

Core work:

- Build a lightweight Streamlit dashboard after CLI workflows are stable.
- Display MethodSpecs, review reports, plugin validation reports, run metrics, return charts, and attribution reports.
- Keep UI as an artifact viewer and workflow launcher, not the source of core business logic.

Deliverables:

- Factor-level evidence page.
- Run comparison page.
- Attribution report viewer.

Completion criteria:

- A researcher can inspect one factor from paper evidence to final run output.
- Blocked or ambiguous fields are visible and not hidden by the UI.

## Recommended Execution Order

```text
1. End-to-end MVP on fixture data
2. MethodSpec extraction and review quality
3. LLM signal plugin generation
4. Real data layer and real backtest
5. Dual-track and attribution
6. C&Z / OSAP evaluation
7. Research UI
```

The immediate next step is to build the MVP vertical slice:

```text
curated MethodSpec
-> Review Gate
-> fixed plugin
-> fixture backtest
-> evidence output
```

This turns the project from an architecture skeleton into a runnable research harness.
