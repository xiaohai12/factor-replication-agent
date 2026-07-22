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

Key constraint: LLMs do not control empirical conclusions. Signal plugins only compute formulas.
Universe, breakpoints, lags, weighting, and portfolio construction come from approved MethodSpec
and controlled pipeline components.

## Required Workflow

- Update `CHANGELOG.md` for every code or repo-instruction change.
- Record challenging or major decisions (methodology, empirical trade-offs,
  deviations from the C&Z/original reference, architectural constraints) in
  `docs/decision-log.md`, capturing the rationale for later paper write-up.
- Prefer targeted reads: use `rg`, `rg --files`, and narrow `sed` windows.
- Cap large command outputs. Summarize important lines instead of dumping logs.
- Do not read large PDFs, converted paper text, or many MethodSpec JSONs
  unless the task directly depends on them.
- Use the narrowest relevant tests first. Run full tests only for shared schema/model behavior
  or broad cross-module changes.
- Never use `git add .` or `git add -A`; data and evidence directories may be large.

## Module Map

| Path | Step | Role |
|---|---|---|
| `src/steps/step1_extractor/` | 1 | Paper text to MethodSpec via LLM. Never receives SignalDoc.csv. |
| `src/steps/step2_reviewer/` | 2 | MethodSpec completeness and empirical-impact review + resolution. |
| `src/steps/step3_codegen/` | 3 | Approved MethodSpec to signal plugin code + hook functions, then assembles those into the one complete standalone backtest script (`script_generator.generate_backtest_script`) that step4/step5 operate on unchanged. The script-assembly call is exposed as `BacktestRunner.build_script()` (physically in the step5 module, since it also needs `DataLayer` snapshot-path resolution that step3_codegen doesn't have) but is conceptually step3's output. |
| `src/steps/step4_validator/` | 4 | Plugin syntax/schema/safety validation (future-leak scan) + a compute_signal execution smoke test on the script step3 built. |
| `src/steps/step5_backtest_runner/` | 5 | Execute the standalone backtest script (already built by step3) via subprocess (`BacktestRunner.execute()`) — literally "run the generated file". Used by both `Pipeline.run_from_method_spec` (single track) and `DualTrackController` (multi-track), so there's one implementation of "execute" either way. |
| `src/steps/step6_dual_track_controller/` | 6 | Dual-track and ablation orchestration: runs each track via `BacktestRunner` (step5), with its own bounded repair loop back to `MetaCoder` (step3) on an execution failure. |
| `src/steps/step7_replication_diff/` | 7 | Replication-gap analysis vs reference (C&Z/paper): decompose where the gap comes from (`ReplicationDiff`). Terminal reporting step, not a feedback-loop trigger. |
| `src/infra/backtest_engine/` | — | The controlled backtest lifecycle engine (`BacktestExecutor`, standard step computations, hook loading). Shared infrastructure used by pipeline.py/step6/app.py and the generated script's runtime import — not itself "step 5" (see step5 row above), which is just the build+execute action around it. |
| `src/infra/models/` | — | Pydantic models (MethodSpec, PluginRecord, RunRecord). |
| `src/infra/data_layer/` | — | Data loaders, dictionary, snapshots, CCM link, time_avail. |
| `src/infra/evidence/` | — | Evidence store + RunRegistry for run artifacts. |
| `src/infra/llm.py` | — | LLM client wrappers for Codex, Copilot, and OpenRouter. |
| `src/infra/trace.py` | — | Pipeline execution event logger. |
| `src/evaluation/` | — | Ground truth matching + extraction accuracy metrics. |
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
- Never add lag logic inside signal plugins; lag belongs in `DataLayer.TimeAvailComputer`.
- Never let LLM output decide empirical parameters without MethodSpec review.
- Never call `MetaCoder.generate_plugin()` when `codegen_ready=False`.
- Never repair empirical issues in the sandbox repair loop; only syntax/schema errors are repairable.
- Never modify `BacktestExecutor` during active experiments; use config overrides for ablations.
