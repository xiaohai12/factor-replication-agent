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
