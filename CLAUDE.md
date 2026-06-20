# factor-replication-agent

## Project Summary

Controlled Meta-Coder pipeline: extracts trading factor definitions from academic papers (PDF), generates signal code via LLM, validates in Adversarial Sandbox, runs controlled dual-track backtests, attributes replication gaps.

Key constraint: **LLM does not control empirical conclusions.** Signal plugins only do formula computation. All empirical parameters (universe, breakpoints, lag, portfolio construction) come from approved MethodSpec, controlled by BacktestEngine.

**CHANGELOG.md must be updated on every code change** (see .github/copilot-instructions.md).

---

## Module Map

| Path | Role |
|---|---|
| `src/extractor/` | SemanticExtractor: paper text → MethodSpec via LLM. Never receives SignalDoc.csv (leakage). |
| `src/review_gate/` | ReviewGate: validates MethodSpec completeness. Evidence × Impact Decision Matrix → auto_approve / needs_human_confirmation / blocked. |
| `src/meta_coder/` | MetaCoder: approved MethodSpec → signal plugin code. Uses C&Z Predictors as few-shot examples. Max 3 repair retries. |
| `src/sandbox/` | AdversarialSandbox: syntax check, schema check, no future leakage (`shift(-`, `.future`, `lead(`), reproducibility. |
| `src/registry/` | PluginRegistry: in-memory store of validated PluginRecords keyed by plugin_id. |
| `src/engine/` | BacktestEngine: fixed 10-step empirical pipeline. Parameters from MethodSpec only. Most steps are stubs. |
| `src/controller/` | DualTrackController: runs original_method, standardized_hxz, ablation_* tracks via ExperimentPlan. |
| `src/evidence/` | EvidenceStore + RunRegistry: persists run metadata to `evidence/<factor_id>/<run_id>/metadata.json`. |
| `src/attribution/` | AttributionLayer: decomposes replication gap per switch. Flags sign flips or >50% t-stat gap. |
| `src/data_layer/` | DataLayer: DataDictionary, SnapshotManager, CCMLinker, TimeAvailComputer. Builds SignalMasterTable keyed [permno, time_avail_m]. Lag is handled HERE, not in plugins. |
| `src/pipeline.py` | End-to-end orchestrator. MAX_REPAIR_RETRIES=3, MAX_BACKTRACK_DEPTH=3. |
| `src/models/` | All Pydantic data models. |
| `src/llm.py` | Thin LLM client wrapper. |
| `src/pdf_mapper.py` | PDF → text extraction. |
| `app.py` | Streamlit dashboard (interactive extraction + evaluation). |

---

## Key Data Models (`src/models/`)

| Model | Key fields |
|---|---|
| `MethodSpec` | `factor_id`, `signal` (SignalSpec), `portfolio` (PortfolioSpec), `review_status`, `codegen_ready`, `ambiguous_fields`. Has `stable_hash()`. schema_version="methodspec.v1" |
| `SignalSpec` | `formula`, `required_fields`, `timing` (SignalTiming), `missing_policy` |
| `PortfolioSpec` | `universe`, `breakpoints` (BreakpointSpec), `weighting`, `long_leg`, `short_leg` |
| `PluginRecord` | `plugin_id`, `factor_id`, `code`, `validation_status`, `validation_report`, `repair_trace` |
| `RunRecord` | `run_id`, `factor_id`, `plugin_id`, `track`, `metrics` (RunMetrics), `status` |

**Enums:** ReviewStatus: pending/approved/revision_required/blocked/rejected · WeightingRule: ew/vw/capped_vw · BreakpointSource: nyse/full_sample · RebalanceFrequency: monthly/quarterly/annual · MissingAction: drop/fill_zero/fill_median/fill_forward/winsorize

---

## Common Commands

```bash
streamlit run app.py                           # Streamlit dashboard
pytest tests/                                  # Run tests
ruff check src/                                # Lint
python scripts/validate_methodspecs.py         # Validate MethodSpec JSONs (Pydantic)
python scripts/review_methodspecs.py           # Run ReviewGate, output to reviewed/
python scripts/resolve_review_blocks.py        # Apply human resolutions
python scripts/convert_papers_to_md.py         # PDF → markdown
python scripts/download_papers.py              # Download paper list
python scripts/download_osap.py                # Download OSAP data
python scripts/csv_to_gold_standard.py         # Build gold standard from CSV
```

---

## Data Directory Layout

```
data/
  papers/               # PDF papers
  osap/
    SignalDoc.csv         # EVALUATION ONLY — never pass to SemanticExtractor
    Predictors/           # C&Z reference plugins (few-shot for MetaCoder)
  method_specs/
    curated/              # Draft / LLM-extracted JSONs
    reviewed/             # After ReviewGate pass
    resolutions/          # Human-supplied field resolutions
    resolved/             # Final resolved specs
  snapshots/              # Frozen CRSP/Compustat parquet snapshots
evidence/                 # Run artifacts: factor_id/run_id/metadata.json
```

---

## Model Selection (cost optimization)

Use `/task <description>` to auto-select model. Manual guidance:

| Model | Run with | Use for |
|---|---|---|
| Haiku | `/model haiku` | Single-file edits, renames, formatting, adding one field, docstring fixes |
| Sonnet | `/model sonnet` (default) | Bug fixes, feature additions, writing tests, extraction/review/pipeline work |
| Opus | `/model opus` | Cross-module refactors, architecture decisions, subtle logic bugs, designing new pipeline stages |

---

## Anti-Patterns — Do Not Do These

- **Never pass SignalDoc.csv to SemanticExtractor** — information leakage, invalidates accuracy eval
- **Never add lag logic inside signal plugins** — lag belongs in DataLayer.TimeAvailComputer
- **Never let LLM decide breakpoints, weighting, or universe** — BacktestEngine controls these from MethodSpec
- **Never call MetaCoder.generate_plugin() when codegen_ready=False** — raises ValueError
- **Never use `git add .` or `git add -A`** — data/osap/ and evidence/ may contain large files
- **Never repair empirical issues in sandbox repair loop** — empirical issues must backtrack to ReviewGate; only syntax/schema errors are repairable in the loop
- **Never modify BacktestEngine during active experiments** — use config_overrides for ablations
