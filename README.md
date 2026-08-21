# Factor Replication Agent

> **Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution**

让 LLM 写因子 signal，不让 LLM 控制实证结论。

## Research Core

Can a **controlled, leakage-proof LLM agent** faithfully reconstruct a published
factor's method from the paper alone, and what does **inter-implementer
agreement** (our agent vs an independent human replication) reveal about the
reproducibility of the cross-sectional asset-pricing literature?

The study has three separable layers:

1. **Extraction fidelity** — does the agent's reviewed MethodSpec match the
   factor definition? (agent vs C&Z `SignalDoc`)
2. **Signal-implementation agreement** — does the agent's firm-level signal
   agree with an independent implementation? (agent signal vs C&Z signal, rank
   correlation)
3. **Conclusion robustness** — with the signal fixed, how sensitive is the
   factor to controlled implementation choices (EW/VW, NYSE breakpoints,
   microcaps, …)?

Reference roles (see [docs/replication-diagnosis-design.md](docs/replication-diagnosis-design.md)):

- **C&Z (Chen–Zimmermann Open Source Asset Pricing)** is an *independent human
  replication* used to measure inter-implementer agreement — **not** ground
  truth and **not** the original author's code.
- **HXZ (Hou–Xue–Zhang)** is the *standardized-config* source and a robustness
  benchmark — a configuration we run on our own signal, not an external result.

**LLM usage boundary:** the LLM appears only at extraction (Step 1) and
`compute_signal` generation (Step 3), with optional review (Step 2) and an
optional final-analysis explanation layer. Every empirical number — returns,
t-stats, correlations, attribution, thresholds — is produced by deterministic
code, so all core conclusions are reproducible with the LLM switched off.

## Overview

An auditable, AI-assisted factor backtesting pipeline system. Given an academic paper describing a factor, the agent:

1. Extracts the factor definition and methodology from the paper
2. Generates signal construction code (constrained to formula only)
3. Validates the generated code in an adversarial sandbox
4. Executes controlled backtests under fixed portfolio construction rules
5. Runs basic original/standardized/ablation tracks with one frozen signal
6. Builds toward a persisted multi-config diagnosis matrix and C&Z signal bridge

## How Experiments Run

The agent signal is **frozen once**, then executed under multiple controlled
backtest-engine configs on the same data snapshot — so any difference is
attributable to a known change (see design doc §5.3):

| What | Status | Purpose |
|---|---|---|
| Agent signal × `original_method` config (from reviewed MethodSpec) | implemented | paper-method baseline within the engine menu |
| Agent signal × `standardized_hxz` config | basic controller implemented | standardized robustness run; config contract still needs validation cleanup |
| Agent signal × one-at-a-time `ablation_*` | basic controller implemented | screen sensitivity to one requested override |
| Declarative multi-config/factorial matrix | designed, not implemented | controlled pairwise/config-interaction analysis |
| **C&Z signal × our engine (bridge, E2)** | designed, not implemented | isolate signal-implementation difference |
| C&Z published portfolio returns | downloadable | observational reference only |

The target experiment runs the agent signal under validated configs, runs one
C&Z-signal bridge under a matched config, and treats C&Z published returns as an
observational reference. HXZ is a config source, not a separate downloadable
per-factor implementation.

**Design status:** the frozen-signal MethodSpec → code → backtest path and a
basic named-track controller are implemented. Unique multi-config evidence,
strict config validation, a declarative matrix, bridge execution, and diagnosis
report persistence are not yet built. See the canonical Chinese plan,
[docs/multi-config-evidence-plan.md](docs/multi-config-evidence-plan.md), for a
per-key `ConfigKeySpec` stage taxonomy (pre-signal vs post-signal) drives
identification level instead of a hand-written experiment family; run identity
is allocated *before* a script is built so parallel configs never overwrite
each other's output; each run's config, signal, and return series are
separately hashed and persisted; and a declarative
`experiments/<factor_id>.experiments.yaml` will replace today's hardcoded
`ExperimentPlan`. The bridge track (C&Z signal × our engine) and a
`ReplicationDiagnosisReport` comparison bundle are part of that same plan,
not yet implemented.

## Architecture

```text
Paper / C&Z metadata / OSAP code / Data dictionaries
        │
        ▼
┌─────────────────────────────────────────────────┐
│  1. Semantic Extractor          (step1_extractor)│
│  2. Review Gate + Resolution     (step2_reviewer)│
│  3. Controlled Meta-Coder         (step3_codegen)│
│  4. Future-Leak Scan + Sandbox  (step4_validator)│
│  5. Backtest Runner       (step5_backtest_runner)│
│     └─ Controlled Backtest Engine (infra, shared)│
│  6. Basic Multi-Track Controller                 │
│                (step6_dual_track_controller)     │
│  7. Terminal Replication Diagnosis (basic)       │
│                (step7_replication_diff)          │
└─────────────────────────────────────────────────┘
        │
        ▼
  Evaluation (vs C&Z, an independent human replication —
  inter-implementer agreement, not ground truth)
```

Evidence Store/Run Registry and Plugin Registry are shared infra used across
steps 3–7, not separate pipeline stages. Plugin Registry currently provides
in-memory traceability; persistent cross-process storage is deferred.

Key design principle: **LLM generates signal code; everything else is controlled by the framework.** Universe filtering, breakpoints, weighting, portfolio construction, return computation, and metrics are all fixed by the engine configuration — never by LLM output.

## Project Structure

```
src/
├── pipeline.py            # Main orchestrator with feedback loops
├── steps/
│   ├── step1_extractor/          # Semantic Extractor (paper → MethodSpec)
│   ├── step2_reviewer/           # Picky LLM reviewer + Resolution Applier
│   ├── step3_codegen/            # MetaCoder (compute_signal only) + registry.build_config
│   │                              #   + script_generator (assembles standalone backtest script)
│   ├── step4_validator/          # Future-Leak Scan + plugin syntax/schema/sandbox smoke test
│   ├── step5_backtest_runner/    # BacktestRunner.build_script() / .execute()
│   ├── step6_dual_track_controller/  # Basic original/standardized/OAT orchestration
│   └── step7_replication_diff/   # Basic terminal gap report (full diagnosis pending)
├── infra/
│   ├── models/            # Pydantic models: MethodSpec, PluginRecord, RunRecord
│   ├── backtest_engine/   # Controlled backtesting lifecycle (single-file BacktestExecutor)
│   ├── data_layer/        # Unified data access (dictionary, CCM, time_avail_m)
│   ├── evidence/          # Evidence store + run registry
│   ├── registry/          # In-memory plugin registry with code hashing
│   ├── pdf_mapper.py      # PDF → factor filename mapping
│   ├── llm.py             # LLM client (OpenRouter / Claude CLI / Codex)
│   ├── repair.py          # Shared bounded repair loop (technical failures only)
│   └── trace.py           # Pipeline execution event logger
└── evaluation/             # Post-hoc evaluation vs C&Z (independent replication reference)
```

## Data Sources

| Source | Usage | Notes |
|--------|-------|-------|
| OSAP `Predictors/*.py` | Few-shot examples for Meta-Coder | ~200 signal construction scripts |
| OSAP `SignalDoc.csv` | Post-hoc extraction reference ONLY | Never used as Extractor input (leakage); compares MethodSpec fidelity |
| C&Z Firm-Level Characteristics | Signal-level inter-implementer agreement | Independent replication signal; rank-correlate vs our signal, and run through our engine as the bridge track |
| C&Z Long-Short Returns | Portfolio-level reference | Downloaded published returns; observational comparison (not ground truth) |
| WRDS (Compustat/CRSP) | Raw data for signal computation | Accessed via Data Layer |

## Key Design Decisions

- **`time_avail_m`**: Point-in-time available date with accounting lag baked into the Data Layer. Plugins never handle lag themselves.
- **SignalDoc exclusion**: SignalDoc.csv is NOT fed to the Extractor (would be information leakage). Used only as a post-hoc reference to score extraction fidelity, never as ground truth for empirical conclusions.
- **Bounded repair**: Sandbox→Meta-Coder repair loop limited to 3 retries. Empirical issues route back to Review Gate.
- **Bounded feedback**: Review→Extractor targeted re-extraction and technical code repair each have explicit retry budgets; ReplicationDiff is terminal and never auto-tunes empirical choices.
- **Plugin output schema**: `[permno, yyyymm, signal]` — standardized across all factors.
- **`unspecified` vs `other`**: a MethodSpec field the paper never addresses stays `unspecified` (a plain default fills the gap silently); a field the paper states explicitly but that isn't an engine menu member (e.g. `weighting="capped_vw"`) normalizes to `other` and is recorded verbatim in `MethodSpec.unsupported_fields` — the engine still only ever runs `vw`/`ew` (no menu growth), but the substitution is recorded (`registry.build_config`'s `substitutions`) and surfaced to review, never silently discarded like the paper-silent case.

## What a Good MethodSpec Looks Like

`MethodSpec` is the central audit artifact flowing through the pipeline. It records
paper-stated facts first; executable table mappings are added later by the Data
Catalog / Normalizer. Here's a compact **Book-to-Market (BM)** example:

```yaml
schema_version: methodspec.v1
factor_id: "BM"
factor_name: "Book-to-Market"
paper_ref: "Fama and French (1992)"
version: 1
economic_intuition: "High book-to-market firms are undervalued relative to fundamentals"
detailed_definition: "Book equity (ceq) divided by market equity (csho * prcc_f)"
cat_form: "continuous"
sign: 1
sample_start_year: 1963
sample_end_year: 2024

data:
  sources:
    - name: "Compustat"
      source_details: ["annual industrial files"]
    - name: "CRSP"
      source_details: ["monthly stock return files"]
  required_fields:
    - field: "ceq"
      concept: "book equity"
      source_detail: "annual industrial files"
    - field: "csho"
      concept: "shares outstanding"
      source_detail: "annual industrial files"
    - field: "prcc_f"
      concept: "fiscal-year-end price"
      source_detail: "annual industrial files"
  normalized_mapping: {}

signal:
  formula:
    expression: "ceq / (csho * prcc_f)"
    paper_expression: "book equity divided by market equity"
    evidence:
      - location: "Section 3"
        quote: "Book-to-market equity is book equity divided by market equity."
        interpretation: "Defines the BM signal."
  required_fields: ["ceq", "csho", "prcc_f"]
  timing:
    formation_month: 6
    rebalance_frequency: annual
    holding_period: 12
    accounting_lag: 6
    skip_month: null
  missing_policy:
    action: drop
    threshold: null

portfolio:
  universe: "NYSE + AMEX + NASDAQ, common shares only"
  sort:
    breakpoint_source: nyse
    ls_quantile: 0.1
  weighting: vw
  long_leg: high
  short_leg: low
  filter: ""

reported_results:
  return_horizon: monthly
  return_calculation:
    input_return: crsp_monthly_return
    portfolio_return:
      weighting: vw
  main_spread: 0.43
  main_t_stat: 2.1

ambiguous_fields: []           # all fields clearly stated in paper
review_status: approved
codegen_ready: true
paper_faithful: true
```

### What Makes It Good

| Criterion | Why It Matters |
|-----------|---------------|
| **Formula is explicit** | `ceq / (csho * prcc_f)` — Meta-Coder can translate directly to code |
| **Timing is complete** | formation_month + holding_period + accounting_lag fully determine when to trade |
| **Breakpoints specified** | NYSE source + ls_quantile tells the engine exactly how to sort |
| **Sign is declared** | Engine knows high signal = long leg without guessing |
| **No ambiguous fields** | Review Gate can auto-approve; no human intervention needed |
| **Source hints preserved** | Extractor keeps paper wording; Normalizer maps it to CRSP/Compustat tables |
| **Evidence is field-level** | Review Gate can audit formula, timing, and reported results against paper quotes |

### Common Pitfalls (What a Bad MethodSpec Looks Like)

- `signal.formula.expression: "book to market ratio"` — natural language instead of computable expression
- `accounting_lag: 0` without paper evidence — likely look-ahead bias
- `ls_quantile` missing — engine doesn't know decile vs quintile sort
- `sign` wrong — flips long/short legs, inverts the factor return
- high-impact unspecified fields silently defaulted in `original_method` — defaults belong only in `standardized_hxz`

### Key Enums Explained

#### `WeightingRule` — How stocks are weighted within each portfolio leg

| Value | Meaning | When to use |
|-------|---------|-------------|
| `ew` | Equal-weighted (1/N) | Most common (210/242 in SignalDoc). Simple, gives small stocks equal influence |
| `vw` | Value-weighted (by market cap) | Reduces micro-cap noise, closer to investable strategy |
| `other` | Paper states a non-menu scheme | Not executed as a bespoke method; literal value is preserved in `unsupported_fields`, then the engine uses and records its default substitution |
| `unspecified` | Paper does not state a scheme | Review/default policy applies |

#### `EvidenceSource` — Confidence tag on each extracted field

Used in `AmbiguousField.source` to record how certain the Extractor is about a field value:

| Value | Meaning | Pipeline Impact |
|-------|---------|-----------------|
| `clear` | Explicitly stated in the paper | Review Gate auto-approves |
| `single` | Mentioned once, reasonable confidence | Likely auto-approved |
| `inferred` | Not stated — guessed from context/conventions | Flagged for review; may trigger ablation |
| `conflicting` | Multiple sources disagree | Review Gate blocks → requires human resolution |

#### `EmpiricalImpact` — Does this ambiguity matter for replication?

Used by review and future diagnosis reporting to prioritize ambiguous fields:

| Value | Meaning | Example |
|-------|---------|---------|
| `high` | Different choices → meaningfully different returns/t-stats | `weighting: ew` vs `vw` for micro-cap-heavy factors |
| `low` | Result is robust to this choice | `formation_month: 6` vs `7` for most annual factors |

Multi-config diagnosis will quantify sensitivity with versioned deterministic
criteria. No fixed effect threshold is currently implemented.

## Setup

```bash
# Install dependencies
pip install -e .

# Download OSAP reference data (SignalDoc.csv + Predictors/*.py)
python scripts/download_osap.py
```

## Requirements

- Python 3.11 recommended for the validated development environment
  (`.python-version`); source compatibility remains Python 3.10+
- pydantic >= 2.0
- pandas, numpy
- openai (for LLM calls)
- PyYAML

## Status

**Implemented, single-factor pilot stage.** Extraction, review/resolution,
formula-only code generation, validation, generated-script execution, the
standardized engine, and basic named-track orchestration are implemented.
Complete multi-config evidence persistence, bridge execution, and automated
diagnosis are not. Real WRDS files must be supplied locally; there is no live
WRDS service. See
[docs/architecture.md](docs/architecture.md) §10 for the full per-module
implementation-status table.

## Citation

If you use this framework, please cite:

```
@misc{factor-replication-agent,
  title={Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution},
  author={Shengzhao Lei},
  year={2026}
}
```
