# Benchmark Result Extraction and Comparability Plan

## Purpose

Improve the agent's ability to extract paper-reported empirical results without
assuming that every paper's headline result is a mean return or risk-adjusted
alpha. The goal is a small, auditable set of paper benchmarks that can be
compared to the controlled implementation only when their estimand and design
actually match.

This plan changes agent capability and applies to newly run workflows. It does
not mutate a completed session or its evidence artifacts. A paper must be
re-extracted and re-run from Step 1 after implementation.

## Problem illustrated by Asset Growth

The initial Asset Growth extraction retained only two Table II FF3-alpha
spreads. It omitted the corresponding raw-return spreads and did not retain the
``10 - 1`` endpoints in `portfolio_selector`. The latter prevents deterministic
alignment of the paper's high-minus-low convention with the engine's
long-minus-short convention.

For this paper, a suitable directly comparable benchmark set is:

| Weighting | Estimand | Paper table convention (high - low) | Engine-aligned convention (low - high) |
| --- | --- | ---: | ---: |
| VW | Monthly raw mean-return spread | -1.05%, t = -5.04 | +1.05%, t = +5.04 |
| VW | Monthly FF3 alpha spread | -0.70%, t = -3.84 | +0.70%, t = +3.84 |
| EW | Monthly raw mean-return spread | -1.73%, t = -8.45 | +1.73%, t = +8.45 |
| EW | Monthly FF3 alpha spread | -1.63%, t = -8.33 | +1.63%, t = +8.33 |

The stored MethodSpec must preserve the paper's original numeric sign. A
display/comparison layer may flip the sign only after it proves the paper and
engine have opposite endpoint orientation.

## Result-selection policy

`reported_results` is an auditable set of the paper results relevant to the
chosen controlled replication. It is not a complete transcription of every
table in the paper.

For every candidate reported metric, the extractor and reviewer must identify:

1. Its estimand: e.g. mean return, alpha, regression coefficient, Sharpe
   ratio, information ratio, event-study CAR, beta/loading, or another
   paper-defined quantity.
2. Its empirical design: universe, sample period, frequency, construction,
   weighting, sort/leg endpoints, and adjustment model where applicable.
3. Its relationship to the selected controlled implementation: directly
   comparable, contextual only, or not comparable.

The agent should select the paper's headline conclusion metric and up to three
same-design supporting metrics. For a portfolio-sort paper that reports both
raw returns and alpha under the same design, both are normally appropriate. For
a regression or event-study paper, the suitable metrics may instead be a slope
and t-statistic, or CAR and its event window. The system must never manufacture
a mean return or alpha simply because those fields are familiar to the current
backtest engine.

## Metric comparability states

Add a per-metric comparison classification (the exact enum name can be chosen
during implementation):

| State | Meaning | Treatment |
| --- | --- | --- |
| `direct` | The engine computes the same estimand under a sufficiently matched design. | Eligible for numerical replication-gap analysis. |
| `context_only` | The paper result supports interpretation but the engine does not compute that estimand. | Display with evidence; exclude from numerical verdicts. |
| `not_comparable` | Material mismatch in estimand, construction, sample, frequency, or statistic. | Display mismatch reason; exclude from numerical verdicts. |

`direct` is a claim that requires deterministic evidence from the reviewed
MethodSpec and the engine configuration. It must not be inferred solely from a
metric label.

## Spread orientation contract

For a portfolio spread, the extractor must record the endpoints whenever they
are stated or unambiguously encoded by the cited table header. A single table
cell such as `10 - 1` is represented as:

```json
{
  "portfolio_selector": {
    "asset_growth_high": 9,
    "asset_growth_low": 0
  }
}
```

The stored estimate remains the paper's literal high-minus-low value. Step 5
and later comparison code determine whether to flip it by comparing these
endpoints with the reviewed engine long and short legs. If endpoints cannot be
determined, the result may still be retained as paper context but cannot be
treated as a direction-aligned direct comparison.

## Agent and review changes

### Step 1 extraction guidance

The extraction prompt and schema reference should require the agent to:

- identify the empirical panel that matches the chosen implementation;
- extract the headline metric plus same-design supporting metrics, subject to
  the configured metric limit;
- preserve exact table value, unit, statistic, and source citation;
- encode spread endpoints for labels such as `10-1`, `H-L`, and `Low-High`;
- distinguish baseline portfolio results from size groups, event-time results,
  subperiods, robustness checks, and unrelated regressions.

For a portfolio-sort result matrix, the agent should seek matching dimensions
across weighting and estimand before choosing a subset. It should not require
that the matrix contain raw returns or alpha.

### Step 2 review checks

Add deterministic structural checks for:

- a candidate direct spread result without endpoint orientation metadata;
- a primary result whose weighting, sample period, or portfolio construction
  conflicts with the reviewed implementation;
- a metric labeled `direct` whose estimand is not produced by the current
  engine/configuration.

Add an evidence-grounded review rubric that asks whether the selected table
contains a same-design companion metric that was omitted. This is a prompt to
re-extract or seek human confirmation, not authorization for the system to
invent a value. For example, alpha and raw-return spreads should be paired when
both are actually reported for the same portfolio design; they are not a
universal requirement.

## Step 5 presentation

Replace the single generic `Paper reported (alpha/ff3)` row with two sections:

1. **Direct paper benchmarks**: a matrix or compact list grouped by weighting,
   estimand, and adjustment model. Values are rendered in engine-aligned
   direction only when the orientation contract proves the transformation.
2. **Paper-reported context**: `context_only` and `not_comparable` metrics,
   displaying the paper's literal value, citation, and non-comparability reason
   without putting them beside engine values.

The provenance/debug view must retain the literal reported value, original
table column, endpoint metadata, and whether a direction correction was
applied.

## Implementation order

1. Extend the MethodSpec model and schema reference with comparison state and
   any required comparability reason.
2. Update Step 1 extraction instructions and Step 2 review/rubric.
3. Implement deterministic review validators for orientation and direct
   comparability.
4. Update Step 5 display and downstream Step 7 evidence selection so only
   `direct` metrics feed a numerical replication verdict.
5. Add fixtures and targeted tests.
6. Create a new session and run the paper again from Step 1 through Step 5.
   Preserve prior sessions unchanged as regression evidence.

## Acceptance criteria

- Asset Growth re-extraction yields the four directly comparable VW/EW raw and
  FF3 spread benchmarks above, each carrying high/low endpoint metadata.
- The displayed paper values align to the engine's low-minus-high orientation
  only through a recorded, deterministic sign correction.
- A regression-only or event-study paper can retain its natural headline
  metric without being forced into a mean-return/alpha representation.
- Metrics not computable by the engine are explicitly labeled contextual or
  not comparable and do not enter a replication-gap verdict.
- No completed session's artifacts are edited during the capability upgrade.
