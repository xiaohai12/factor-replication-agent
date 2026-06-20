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
- Prefer targeted reads: use `rg`, `rg --files`, and narrow `sed` windows.
- Cap large command outputs. Summarize important lines instead of dumping logs.
- Do not read large PDFs, converted paper text, OSAP predictor files, or many MethodSpec JSONs
  unless the task directly depends on them.
- Use the narrowest relevant tests first. Run full tests only for shared schema/model behavior
  or broad cross-module changes.
- Never use `git add .` or `git add -A`; data and evidence directories may be large.

## Module Map

| Path | Role |
|---|---|
| `src/extractor/` | Paper text to MethodSpec via LLM. Never receives SignalDoc.csv. |
| `src/review_gate/` | MethodSpec completeness and empirical-impact review. |
| `src/meta_coder/` | Approved MethodSpec to signal plugin code. |
| `src/sandbox/` | Plugin syntax/schema/safety validation. |
| `src/data_layer/` | Data dictionary, snapshots, CCM link, and point-in-time availability. |
| `src/engine/` | Controlled empirical pipeline; most steps are still stubs. |
| `src/controller/` | Dual-track and ablation orchestration. |
| `src/attribution/` | Replication-gap attribution and anomaly flags. |
| `src/models/` | Pydantic models, especially MethodSpec and PluginRecord. |
| `src/llm.py` | LLM client wrappers for Codex, Copilot, and OpenRouter. |
| `app.py` | Streamlit dashboard for extraction and evaluation. |

## Common Commands

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
- Never modify `BacktestEngine` during active experiments; use config overrides for ablations.
