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
│  1. Semantic Extractor                          │
│  2. Review Gate (Picky LLM Reviewer)            │
│  3. Controlled Meta-Coder (few-shot from OSAP)  │
│  4. Adversarial Sandbox                         │
│  5. Plugin Registry                             │
│  6. Controlled Backtesting Engine               │
│  7. Dual-Track + Factorial Controller           │
│  8. Evidence Store + Run Registry               │
│  9. Factorial Attribution Layer                  │
└─────────────────────────────────────────────────┘
        │
        ▼
  Evaluation (vs C&Z ground truth)
```

Key design principle: **LLM generates signal code; everything else is controlled by the framework.** Universe filtering, breakpoints, weighting, portfolio construction, return computation, and metrics are all fixed by the engine configuration — never by LLM output.

## Project Structure

```
src/
├── models/          # Data models: MethodSpec, FactorSpec, PluginRecord, RunRecord
├── extractor/       # Semantic Extractor (paper → MethodSpec)
├── review_gate/     # Picky LLM reviewer with decision matrix
├── meta_coder/      # Signal plugin code generation (few-shot from OSAP)
├── sandbox/         # Adversarial validation of generated plugins
├── registry/        # Plugin storage with code hashing
├── engine/          # Controlled backtesting lifecycle
├── controller/      # Dual-track + factorial ablation controller
├── evidence/        # Evidence store + run registry
├── attribution/     # Factorial attribution of replication gap
├── evaluation/      # Post-hoc evaluation vs C&Z ground truth
├── data_layer/      # Unified data access (dictionary, CCM, time_avail_m)
└── pipeline.py      # Main orchestrator with feedback loops
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

`MethodSpec` is the central artifact flowing through the pipeline. Here's a concrete example for the **Book-to-Market (BM)** factor:

```yaml
factor_id: "BM"
factor_name: "Book-to-Market"
paper_ref: "Fama and French (1992)"
version: 1
economic_intuition: "High book-to-market firms are undervalued relative to fundamentals"
detailed_definition: "Book equity (ceq) divided by market equity (csho * prcc_f)"
cat_form: "continuous"
sign: 1                      # high BM → high expected returns
sample_start_year: 1963
sample_end_year: 2024

signal:
  formula: "ceq / (csho * prcc_f)"
  required_fields: ["ceq", "csho", "prcc_f"]
  field_sources:
    ceq:  { dataset: compustat, table: funda, description: "Common Equity" }
    csho: { dataset: compustat, table: funda, description: "Shares Outstanding" }
    prcc_f: { dataset: compustat, table: funda, description: "Price - Fiscal Year Close" }
  timing:
    formation_month: 6         # June
    rebalance_frequency: annual
    holding_period: 12         # hold July t → June t+1
    accounting_lag: 6          # use fiscal year-end from Dec t-1
    skip_month: null
  missing_policy:
    action: drop
    threshold: null

portfolio:
  universe: "NYSE + AMEX + NASDAQ, common shares only"
  breakpoints:
    source: nyse               # NYSE-only breakpoints (avoid micro-cap influence)
    ls_quantile: 0.1           # decile sort → top 10% vs bottom 10%
    quantiles: [10, 90]        # derived from ls_quantile
  weighting: vw                # value-weighted within each leg
  long_leg: high               # long high-BM (value) stocks
  short_leg: low               # short low-BM (growth) stocks
  filter: ""                   # no additional stock-level filter

ambiguous_fields: []           # all fields clearly stated in paper
review_status: approved
```

### What Makes It Good

| Criterion | Why It Matters |
|-----------|---------------|
| **Formula is explicit** | `ceq / (csho * prcc_f)` — Meta-Coder can translate directly to code |
| **Timing is complete** | formation_month + holding_period + accounting_lag fully determine when to trade |
| **Breakpoints specified** | NYSE source + ls_quantile tells the engine exactly how to sort |
| **Sign is declared** | Engine knows high signal = long leg without guessing |
| **No ambiguous fields** | Review Gate can auto-approve; no human intervention needed |
| **Field sources mapped** | Data Layer knows exactly which Compustat tables to query |

### Common Pitfalls (What a Bad MethodSpec Looks Like)

- `formula: "book to market ratio"` — natural language instead of computable expression
- `accounting_lag: 0` — no lag means look-ahead bias
- `ls_quantile` missing — engine doesn't know decile vs quintile sort
- `sign` wrong — flips long/short legs, inverts the factor return
- `ambiguous_fields` not empty but `review_status: approved` — inconsistent state

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

**Framework stage** — high-level module interfaces are defined; implementation details are in progress.

## Citation

If you use this framework, please cite:

```
@misc{factor-replication-agent,
  title={Controlled Meta-Coder Agents for Auditable Factor Backtesting Pipeline Generation and Implementation-Gap Attribution},
  author={Shengzhao Lei},
  year={2026}
}
```
