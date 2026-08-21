# factor-replication-agent

This is the canonical instruction file for Codex, Claude, Copilot, and other coding agents.
Compatibility files may point here, but project rules should be maintained here first.

## Project Summary

Controlled Meta-Coder pipeline for auditable factor replication:
1. Extract factor definitions from academic papers into `MethodSpec`.
2. Review and resolve ambiguous empirical choices.
3. Generate signal plugin code only after MethodSpec approval.
4. Validate plugin safety in sandbox.
5. Run controlled backtests and attribute replication gaps.

Research core (see `docs/replication-diagnosis-design.md`): can a controlled,
leakage-proof LLM agent reconstruct a factor's method from the paper, and what
does inter-implementer agreement (agent vs C&Z) plus implementation sensitivity
reveal about reproducibility? C&Z is an **independent human replication**
reference — not ground truth and not the original author's code. HXZ is the
standardized-config source (a config we run on our own signal), not an external
result. The LLM appears only at extraction (Step 1) and `compute_signal`
generation (Step 3), with optional review and an optional final-analysis
explanation layer; every empirical number stays deterministic.

Key constraint: LLMs do not control empirical conclusions. Signal plugins only compute formulas.
Universe, breakpoints, lags, weighting, and portfolio construction come from approved MethodSpec
and controlled pipeline components.

## Required Workflow

- Update `CHANGELOG.md` for every code or repo-instruction change.
- Prefer targeted reads: use `rg`, `rg --files`, and narrow `sed` windows.
- Cap large command outputs. Summarize important lines instead of dumping logs.
- Do not read large PDFs, converted paper text, or many MethodSpec JSONs
  unless the task directly depends on them.
- Use the narrowest relevant tests first (target the specific test file(s)
  covering the changed module). Do NOT run the full `pytest tests/` suite by
  default -- it is slow and usually unnecessary. Only run the full suite when
  explicitly asked, or the change touches shared schema/model behavior
  (`src/infra/models/`, `registry.build_config`) or otherwise crosses many
  modules in a way targeted tests can't cover.
- Never use `git add .` or `git add -A`; data and evidence directories may be large.
- `pytest tests/` never writes to the real `runs/` directory. `tests/conftest.py`
  redirects `backend.state.RUNS_DIR` to the gitignored `.runs_scratch/` dir
  (set at collection time, before any test module's own `from backend.main
  import app`). Manual/live agent verification (starting a real uvicorn/
  streamlit process) is NOT covered by that conftest and must set
  `export FACTOR_AGENT_RUNS_DIR=.runs_scratch` itself first, then
  `rm -rf .runs_scratch` to clean up afterward — never delete/hand-pick files
  under the real `runs/` dir for test/verification cleanup.

## Module Map

| Path | Step | Role |
|---|---|---|
| `src/steps/step1_extractor/` | 1 | Paper text to MethodSpec via LLM. Never receives SignalDoc.csv. |
| `src/steps/step2_reviewer/` | 2 | MethodSpec completeness and empirical-impact review + resolution. |
| `src/steps/step3_codegen/` | 3 | Approved MethodSpec to signal plugin code (the `compute_signal` formula only — no hook code), then assembles it into the one complete standalone backtest script (`script_generator.generate_backtest_script`) that step4/step5 operate on unchanged. The script-assembly call is exposed as `BacktestRunner.build_script()` (physically in the step5 module, since it also needs `DataLayer` snapshot-path resolution that step3_codegen doesn't have) but is conceptually step3's output. Empirical parameters (weighting, breakpoints, missing policy, return combination, sort form, estimator) are *selected* from a fixed menu by `registry.build_config`, which clamps any out-of-menu value to the menu default. |
| `src/steps/step4_validator/` | 4 | Plugin syntax/schema/safety validation (future-leak scan) + a compute_signal execution smoke test on the script step3 built (now also reporting a whitelisted `technical_metrics` dict — nan_ratio/n_permno/n_months/missing_columns/dtype — and a hard dtype-mismatch failure). Also read as a Tool Prelude source (`sandbox_validate`) by step3's tool catalog (docs/tools-plus-llm-plan.md) — registered as a step3 tool, not physically moved. |
| `src/steps/step5_backtest_runner/` | 5 | Execute the standalone backtest script (already built by step3) via subprocess (`BacktestRunner.execute()`) — literally "run the generated file". Used by both `Pipeline.run_from_method_spec` (single track) and `MultiTrackController` (multi-track), so there's one implementation of "execute" either way. |
| `src/steps/step6_dual_track_controller/` | 6 | Original/standardized/OAT/declarative-matrix orchestration (`run_experiment` is now a thin adapter over `run_from_matrix`, sharing one `_finalize_batch`). Auto-freeze is real, not detection-only: if a track's technical repair changes its code, `_run_tracks_with_freeze` re-runs the WHOLE batch under the repaired code with repair disabled, bounded to `max_refreeze_attempts` (default 1); `batch_invalidated=True` only fires via the explicit `max_refreeze_attempts=0` escape hatch. (A C&Z signal bridge-track mechanism existed here previously but was removed 2026-08-18 -- it was never run outside tests; a future C&Z bridge track is tracked as future work, not implemented.) |
| `src/steps/step7_replication_diff/` | 7 | Replication-gap analysis vs reference (C&Z/paper): decompose where the gap comes from (`ReplicationDiff`). Terminal reporting step, not a feedback-loop trigger. `bundle.py` turns that decomposition plus each track's config/metrics into the deterministic evidence bundle (`derived`/`config_diff`/`gap_decomposition`/`evidence_keys`, plus the newer `spec_quality`/`menu_deviations`/`publication_decay`/`robustness_summary` sections) embedded in `comparison.json`, which is all step8 is allowed to read. Also read as a Tool Prelude source by step8's tool catalog (docs/tools-plus-llm-plan.md) — registered as step8 tools, not physically moved. |
| `src/steps/step8_diagnosis/` | 8 (optional) | LLM-assisted, NOT LLM-controlled explanation layer over an already-written `comparison.json`. The LLM only drafts wording/attribution as `DiagnosisClaim`s citing `evidence_keys` from the deterministic bundle; a validator rejects any claim containing a digit, citing an unlisted key, or of a `claim_type` unbacked by its required evidence; a deterministic renderer (`render.py`) reinserts every figure from the bundle. Output is always tagged `status: "llm_assisted_proposal"`. Opt-in only (`Pipeline(run_diagnosis=True)` or `scripts/analyze_comparison.py`) — never runs in tests or default batch runs. |
| `src/infra/backtest_engine/` | — | The controlled backtest lifecycle engine (`BacktestExecutor`, standard step computations). Fully standardized — no LLM hook loading; steps are selected from config. Shared infrastructure used by pipeline.py/step6/app.py and the generated script's runtime import — not itself "step 5" (see step5 row above), which is just the build+execute action around it. |
| `src/infra/models/` | — | Pydantic models (MethodSpec, PluginRecord, RunRecord). |
| `src/infra/data_layer/` | — | `sources.py` DataSource registry (single source of truth: CRSP returns universe + Compustat/IBES signal sources + CCM/IBES link tables + declarative signal-master loader); `catalog.py` derived query views; `__init__.py` `DataLayer` facade + `DataDictionary` + `SnapshotManager`. |
| `src/infra/evidence/` | — | Evidence store + RunRegistry for run artifacts. |
| `src/infra/llm.py` | — | LLM client wrappers for Codex, Copilot, and OpenRouter. |
| `src/infra/trace.py` | — | Pipeline execution event logger. |
| `src/evaluation/` | — | Post-hoc reference matching + extraction accuracy metrics. |
| `src/pipeline.py` | — | End-to-end orchestrator with feedback loops. |
| `app.py` | — | 7-page Streamlit dashboard. |

## Generated Artifacts vs. Fixtures

- `runs/` — gitignored. Every pipeline-run-generated artifact (MethodSpecs at each
  stage, plugins, `generate_backtest_script()` output, EvidenceStore RunRecords)
  lives here. Safe to delete/regenerate at any time.
- `tests/fixtures/` — committed. Resolved MethodSpecs + plugins that golden-number
  tests (`tests/test_*_e2e.py`) and manual dashboard testing depend on. Promote a
  `runs/` artifact here manually when it should become a durable reference.

## Common Commands

### Starting the Streamlit dashboard

The dashboard lives in `app.py`. Run it with whichever Python environment
has the project dependencies installed (streamlit, pymupdf, pydantic, …):

```bash
# If installed in a virtualenv / uv environment:
source .venv/bin/activate   # or: uv run streamlit run app.py
streamlit run app.py

# If installed with pip into the system / user Python:
python3 -m streamlit run app.py
```

The app opens at http://localhost:8501 by default.
Use `--server.port 8502` to pick a different port.

```bash
streamlit run app.py
pytest tests/
ruff check src/
python scripts/validate_methodspecs.py
python scripts/review_methodspecs.py
python scripts/resolve_review_blocks.py
python scripts/convert_papers_to_md.py
```

## Model Selection

Do not default to the strongest model for routine work.

| Task type | Recommended model tier |
|---|---|
| Single-file edits, docs, formatting, small tests | Cheap/fast model |
| Normal bug fixes, focused features, test writing | Mid-tier default |
| Architecture, cross-module refactors, subtle extraction/review logic, financial correctness | Strongest model |

Repo files can guide model choice, but they cannot forcibly switch the active model in Codex,
Claude, or Copilot. If the current model is excessive for the task, recommend switching down.

## Hard Constraints

- Never pass `data/osap/SignalDoc.csv` to `SemanticExtractor`; it is evaluation-only.
- Never add lag logic inside signal plugins; lag belongs in the DataLayer signal-source loader (`src/infra/data_layer/sources.py`: `_load_generic_signal_frame` / `assemble_signal_master_table`).
- Never let LLM output decide empirical parameters without MethodSpec review.
- Never call `MetaCoder.generate_plugin()` when `codegen_ready=False`.
- Never repair empirical issues in the sandbox repair loop; only syntax/schema errors are repairable.
- Never generate hook code. The engine is fully standardized: portfolio
  construction is selected from a fixed menu by `registry.build_config`, and an
  out-of-menu MethodSpec value is clamped to the menu default (never
  code-generated). The LLM writes only `compute_signal`.
- Never modify `BacktestExecutor` during active experiments; use config overrides for ablations.
- Never default the *signal-input* source/columns. They come from the reviewed
  MethodSpec via the DataSource registry (`src/infra/data_layer/sources.py`, the
  single source of truth), surfaced through the derived catalog query functions
  (`src/infra/data_layer/catalog.py`): signal columns resolve through
  `catalog.source_of_column`/`resolve_concept`; an unknown/unset signal source is
  hard-blocked at review (a human registers one `SourceSpec` in `sources.py`),
  never silently guessed (e.g. to Compustat). The
  *returns* panel, by contrast, defaults to CRSP monthly
  (`catalog.DEFAULT_RETURNS_UNIVERSE` = `us_equity_crsp`) when
  `MethodSpec.returns_source` is unset; an explicitly-set but unregistered
  returns universe is still blocked at review.
