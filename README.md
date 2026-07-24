# Factor Replication Agent

> **Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution**

让 LLM 写因子 signal，不让 LLM 控制实证结论。

## Overview

An auditable, AI-assisted factor backtesting pipeline system. Given an academic paper describing a factor, the agent:

1. Extracts the factor definition and methodology from the paper
2. Generates signal construction code (constrained to formula only)
3. Validates the generated code in an adversarial sandbox
4. Executes controlled backtests under fixed portfolio construction rules
5. Runs dual-track (original vs standardized) and ablation experiments
6. Attributes the replication gap to specific implementation choices

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
│  6. Dual-Track + Ablation Controller             │
│                (step6_dual_track_controller)     │
│  7. Replication-Gap Diff   (step7_replication_diff)│
└─────────────────────────────────────────────────┘
        │
        ▼
  Evaluation (vs C&Z ground truth)
```

Evidence Store/Run Registry and Plugin Registry are shared infra used across
steps 3–7, not separate pipeline stages (Plugin Registry is currently deferred
— pilot-stage file-path tracing is sufficient).

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
│   ├── step6_dual_track_controller/  # Dual-track + factorial ablation controller
│   └── step7_replication_diff/   # Replication-gap decomposition vs C&Z/paper
├── infra/
│   ├── models/            # Pydantic models: MethodSpec, FactorSpec, PluginRecord, RunRecord
│   ├── backtest_engine/   # Controlled backtesting lifecycle (BacktestExecutor + steps.py)
│   ├── data_layer/        # Unified data access (dictionary, CCM, time_avail_m)
│   ├── evidence/          # Evidence store + run registry
│   ├── registry/          # Plugin storage with code hashing (deferred, not yet used)
│   ├── pdf_mapper.py      # PDF → factor filename mapping
│   ├── llm.py             # LLM client (OpenRouter / Claude CLI / Codex)
│   ├── repair.py          # Shared bounded repair loop (technical failures only)
│   └── trace.py           # Pipeline execution event logger
└── evaluation/             # Post-hoc evaluation vs C&Z ground truth
```

## Data Sources

| Source | Usage | Notes |
|--------|-------|-------|
| OSAP `Predictors/*.py` | Few-shot examples for Meta-Coder | ~200 signal construction scripts |
| OSAP `SignalDoc.csv` | Evaluation ground truth ONLY | Never used as Extractor input |
| C&Z Firm-Level Characteristics | Signal-level evaluation | Compare plugin output vs reference signals |
| C&Z Long-Short Returns | Portfolio-level evaluation | Compare LS returns vs reference |
| WRDS (Compustat/CRSP) | Raw data for signal computation | Accessed via Data Layer |

## Key Design Decisions

- **`time_avail_m`**: Point-in-time available date with accounting lag baked into the Data Layer. Plugins never handle lag themselves.
- **SignalDoc exclusion**: SignalDoc.csv is NOT fed to the Extractor (would be information leakage). Used only for post-hoc evaluation.
- **Bounded repair**: Sandbox→Meta-Coder repair loop limited to 3 retries. Empirical issues route back to Review Gate.
- **Max backtrack depth**: 3 levels (e.g., Attribution→Review→Extractor).
- **Plugin output schema**: `[permno, yyyymm, signal]` — standardized across all factors.

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
    quantiles: [10, 90]
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
| `capped_vw` | Value-weighted with max cap | Prevents single mega-cap from dominating |

#### `EvidenceSource` — Confidence tag on each extracted field

Used in `AmbiguousField.source` to record how certain the Extractor is about a field value:

| Value | Meaning | Pipeline Impact |
|-------|---------|-----------------|
| `clear` | Explicitly stated in the paper | Review Gate auto-approves |
| `single` | Mentioned once, reasonable confidence | Likely auto-approved |
| `inferred` | Not stated — guessed from context/conventions | Flagged for review; may trigger ablation |
| `conflicting` | Multiple sources disagree | Review Gate blocks → requires human resolution |

#### `EmpiricalImpact` — Does this ambiguity matter for replication?

Used in the **Factorial Attribution Layer** to tag whether an ambiguous field choice materially changes results:

| Value | Meaning | Example |
|-------|---------|---------|
| `high` | Different choices → meaningfully different returns/t-stats | `weighting: ew` vs `vw` for micro-cap-heavy factors |
| `low` | Result is robust to this choice | `formation_month: 6` vs `7` for most annual factors |

The Attribution Layer runs ablation experiments on ambiguous fields. If flipping a choice changes the long-short return by >20% or flips t-stat significance, it's tagged `HIGH`. This tells the researcher which implementation details actually explain the replication gap.

## Setup

```bash
# Install dependencies
pip install -e .

# Download OSAP reference data (SignalDoc.csv + Predictors/*.py)
python scripts/download_osap.py
```

## Requirements

- Python 3.10+
- pydantic >= 2.0
- pandas, numpy
- openai (for LLM calls)
- PyYAML

## Status

**Implemented, single-factor pilot stage.** All seven pipeline steps (Extractor,
Review Gate, Meta-Coder, Validator, Backtest Runner, Dual-Track Controller,
Replication-Diff) and the shared BacktestExecutor standard-step library run
end-to-end (Streamlit dashboard in `app.py`, CLI scripts in `scripts/`).
Honest remaining gaps: the replication-diff decomposition algorithm is
structural only (no automated gap attribution yet), `data/local/*.parquet`
(Compustat/CRSP) must be supplied manually, there is no live WRDS connection,
and the Plugin Registry is in-memory/deferred. See
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
