---
type: template
status: draft
project: factor-replication-agent
created: 2026-05-30
updated: 2026-06-03
tags:
  - template
  - methodspec
  - json
  - agent-test
---

> **2026-07 schema simplification — read this first.** The authoritative schema
> is `src/infra/models/method_spec.py`. Portfolio-return construction is now
> **flat on `portfolio`**: `portfolio.construction_type`, `portfolio.sorts[]`,
> `portfolio.return_combination` (there is no
> `reported_results.return_calculation` / `portfolio_return` nesting, and no
> `comparison_policy` / `input_return`). `portfolio.sort` and
> `portfolio.breakpoints` are merged into one `portfolio.sort` block. The
> engine is standardized to a fixed menu, so these fields/enum values were
> **removed**: `weighting_scheme` (use `portfolio.weighting` = `vw`/`ew`),
> `signal.field_sources`, `portfolio.filter`, `breakpoint_source`
> `conditional`/`paper_specific`, `missing_action` `winsorize`/`fill_*`,
> `construction_type` `factor_model_alpha`/`event_window_return`,
> `return_combination` `alpha_estimate`. Older sections below that still show
> the nested shape / removed vocabulary are retained only as historical
> reference; any such value in existing JSON is coerced/clamped on load.

# MethodSpec JSON Template

> 用途：作为 **Extractor Output**：把 paper-first 信息转换成后续 extractor evaluation / Review Gate 可消费的机器可读 MethodSpec。  
> 示例实例：[[annotations/AssetGrowth.methodspec.json]]。

---

## 1. 使用原则

### 1.1 Paper-first / Paper-only extraction

**MethodSpec extractor 主要、且原则上只以 original paper 为依据。**

C&Z / OSAP / factor zoo metadata **不作为 extractor 的参考来源**，也不能作为任何字段的 `source` evidence。它们不能用来：

- 决定是否生成一个 MethodSpec；
- 改写 paper 的 factor definition / formula / sign / timing / sample；
- 补 paper 没有说的 implementation detail；
- 把 downstream variant 当成 paper-original signal；
- 覆盖 paper 的命名、return construction 或 portfolio construction。

允许的例外只有一个：`cz_acronym` 可以作为 **optional downstream mapping metadata**，用于后续 normalizer / evaluation 对齐；但它不是 extraction target，也不是证据来源。如果 `cz_acronym` 和 paper 原始定义不完全一致，优先保留 paper 原始定义，并在 `ambiguous_fields` 或 `annotator_notes` 说明 mapping 风险。

Extractor 不做 CRSP/Compustat implementation mapping。例如 paper 写 “NYSE, Amex, and NASDAQ”，extractor 只填 `universe.exchange_names`；不填 `exchcd in [1,2,3]`。

### 1.2 Source 必须结构化

所有 high-impact field 的 `source` 统一使用：

```json
{
  "location": "Section / page / table / equation",
  "quote": "short original quote from the paper",
  "interpretation": "why this quote supports the field value"
}
```

`quote` 尽量放 paper 原文短句；`interpretation` 放你的解释，不要把两者混在一起。

### 1.3 固定字段 vs 自由字段

固定结构供 extractor / Review Gate 消费：

- `paper`
- `signal`
- `data`
- `sample`
- `timing`
- `universe`
- `portfolio`
- `reported_results`

不确定、推断、冲突、非主规格内容放入：

- `ambiguous_fields`
- `robustness_or_secondary_specs`
- `extensions`
- `annotator_notes`

不要随意新增顶层字段；需要扩展时优先放进 `extensions`。

---

## 2. 关键字段解释

### 2.1 Status fields

| Field | Meaning |
|---|---|
| `annotation_status` | 人工标注生命周期，如 `draft_human_annotation`, `reviewed`, `approved`, `needs_revision` |
| `review_status` | Review Gate 处置状态，如 `pending`, `approved`, `revision_required`, `blocked` |

`ambiguous_fields[].status` 可用：

```text
explicit, inferred, unspecified, ambiguous, conflicting, weak_or_conflicting,
not_main_spec, inferred_for_backtest_not_paper_stated
```

Use `weak_or_conflicting` when the paper contains some evidence but not enough for a clean executable direction, e.g. a sign is insignificant or mechanism evidence and return-table evidence point in different directions.

### 2.2 `paper.paper_sections` vs `paper.evidence_sections`

| Field | Meaning |
|---|---|
| `paper_sections` | 论文整体章节结构，尽量完整列出 |
| `evidence_sections` | 本次 MethodSpec 实际引用过的章节 / 表格 / appendix |

### 2.3 `signal.paper_variable_name` vs `signal.factor_name`

| Field | Example | Meaning |
|---|---|---|
| `paper_variable_name` | `ASSETG` | paper 中的变量名 / signal column name |
| `factor_name` | `Asset Growth` | 人类可读的 factor 名称 |

### 2.4 `signal.formula.inputs` vs `data.required_fields`

Final rule: **`signal.formula.inputs` is a lightweight list of canonical formula variable names, not a second data dictionary.**

| Field | Include | Do not include |
|---|---|---|
| `signal.formula.inputs` | only variables directly used by `signal.formula.expression`; array of strings | `dataset`, `table`, Compustat item explanations, return fields, merge keys |
| `data.required_fields` | paper-stated data concepts needed for the full backtest lifecycle, including signal inputs, universe filters, and return calculation | CRSP-Compustat merge keys or implementation-only mapping choices unless explicitly paper-stated |

Required matching contract:

```text
base variables in signal.formula.expression
        ↓ must match
signal.formula.inputs[]
        ↓ must be present in
data.required_fields[].field
```

Expression variables may carry timing suffixes. Strip timing suffixes to get the base variable name:

| Expression variable | Base variable | Must appear in `inputs` |
|---|---|---|
| `sale_t` | `sale` | `"sale"` |
| `inventory_t` | `inventory` | `"inventory"` |
| `at_t_minus_1` | `at` | `"at"` |
| `emp_t_minus_1` | `emp` | `"emp"` |

Examples:

```json
{
  "expression": "pct_change(sale_t) - pct_change(inventory_t)",
  "inputs": ["sale", "inventory"]
}
```

```json
{
  "expression": "(at_t_minus_1 - at_t_minus_2) / at_t_minus_2",
  "inputs": ["at"]
}
```

`data.required_fields` should then contain matching `field` names, with richer descriptions:

```json
"required_fields": [
  {"field": "sale", "dataset": "compustat", "table": "...", "description": "Sales; Compustat item 12"},
  {"field": "inventory", "dataset": "compustat", "table": "...", "description": "Inventory; Compustat item 78 or 3"}
]
```

Important simplification: if a paper expression has item numbers such as `(12)`, `(78 or 3)`, or ranked names such as `RINV`, explain them in `source.interpretation` or `data.required_fields[].description`; **do not create a new mapping field unless code will consume it.**

Extractor output does not include CRSP–Compustat merge keys; those implementation requirements are added later by the normalizer / lifecycle engine.

### 2.4.1 `timing.skip_months` vs `timing.return_window`

Use `skip_months` only for momentum-style or explicit portfolio-formation skips: a gap between the signal measurement / ranking period and the holding-period start.

Do **not** use `skip_months` for a paper's return-measurement window if `timing.return_window` already states when returns begin.

Example:

- Momentum: rank on past 12-month returns ending at month `t-2`, skip month `t-1`, hold from `t` → `skip_months = 1`.
- Abarbanell & Bushee: fiscal year ends in December, earnings are required by March 31, abnormal returns are cumulated from the fourth month after fiscal year-end → put this in `return_window.start`; do **not** set `skip_months = 3`.

This avoids confusing a disclosure/accounting-lag return window with a momentum skip-month convention.

### 2.4.2 `data.sample_coverage_notes`

Purpose: record paper-stated **data coverage requirements or warnings** that matter for replication quality, but are **not row-level filters, not formula inputs, and not executable portfolio rules**.

Think of this field as:

```text
"Does the data source / data loader cover the same population the paper intended?"
```

Do **not** read it as:

```text
"Which observations should I keep or drop?"
```

Use `universe.filters` for row-level sample restrictions that can become code filters. Use `data.sample_coverage_notes` for coverage/bias warnings that the normalizer or reviewer should check.

| Field | Question answered | Becomes code filter? | Example |
|---|---|---|---|
| `universe.filters` | Should this observation be kept/dropped? | Usually yes | keep only December fiscal-year-end firms |
| `data.sample_coverage_notes` | Does the data source include the intended coverage? | Usually no; warning / data-loader requirement | include delisted/inactive firms to avoid survivorship bias |

Examples for `sample_coverage_notes`:

- paper includes delisted firms / inactive firms;
- paper warns about survivorship bias;
- paper uses Compustat Research file for delisted firms;
- paper mentions historical identifiers only to recover delisted returns;
- paper requires a non-survivor-only data source.

Abarbanell & Bushee example:

```json
"sample_coverage_notes": [
  {
    "topic": "delisted_firms",
    "paper_action": "included",
    "details": "The paper includes Compustat Research file data to calculate signals for delisted firms and identifies delisted return observations through historical CUSIPs on CRSP.",
    "implementation_relevance": "important_for_avoiding_survivorship_bias; extractor note only",
    "normalizer_hint": "Use a survivor-bias-free data loader. Do not treat historical_cusip as a signal input or row filter.",
    "source": {"location": "", "quote": "", "interpretation": ""}
  }
]
```

Why this is not a filter: "include delisted firms" does **not** mean `keep only delisted firms`; it means the source data must not silently exclude delisted firms. Codegen may ignore this field in P0 and emit a warning; normalized implementation config should handle it later.

### 2.4.3 `universe.winsorize_bounds.status`

Use `status` in plain language to explain what `null` bounds mean. This avoids confusing "not mentioned" with "mentioned but not fully specified."

Examples:

```json
"winsorize_bounds": {
  "status": "paper mentions truncation, but exact bounds are not given here",
  "lower_pct": null,
  "upper_pct": null,
  "applies_to": "main_portfolio_spec",
  "source": {"location": "", "quote": "", "interpretation": ""}
}
```

```json
"winsorize_bounds": {
  "status": "bounds are stated in the paper",
  "lower_pct": 1,
  "upper_pct": 99,
  "applies_to": "main_portfolio_spec",
  "source": {"location": "", "quote": "", "interpretation": ""}
}
```

Plain-language status values are preferred. Do not create complicated enums unless code needs them.


### 2.5 `sample.formation_years` vs `sample.return_sample`

| Field | Meaning |
|---|---|
| `formation_years` | portfolio formation years, e.g. June 1968 through June 2002 |
| `return_sample` | actual return observation window, structured as `{year, month}` start/end |

For annual June-formed portfolios held for 12 months, the last formation year is usually one year before the return sample end year. Use structured dates to avoid inconsistencies like `"July 1968"` plus `start_year: 1968`.

Important: compute `return_sample.end` from the **last return observation window**, not from the last formation/sample year label. If the paper's main formation/sample years are 1974-1988 but the last fiscal-year-1988 portfolio earns a 12-month return from April 1989 through March 1990, then:

```json
"formation_years": {"start": 1974, "end": 1988},
"return_sample": {
  "start": {"year": 1974, "month": 4},
  "end": {"year": 1990, "month": 3}
}
```

Avoid this common off-by-one error by deriving return end date as:

```text
last_return_start_month + holding_period_or_cumulation_window - 1 month
```

rather than copying the paper's sample end year.


### 2.6 `timing.formation`

`timing.formation` combines machine-readable month and human-readable timing rule:

```json
{
  "month": 6,
  "date_rule": "end_of_month",
  "description": "End of June in year t"
}
```

`month` is a normalized paper timing value; `description` is for audit/review.

### 2.7 Formula expression convention

`formula.expression` 必须使用 `formula_convention` 定义的时间下标。

默认：

- `t` = portfolio formation year
- annual accounting field 的 `_t_minus_1` = fiscal year ending in calendar year `t-1`
- `_t_minus_2` = fiscal year ending in calendar year `t-2`
- monthly signal 可用 `_m` 或 `lag(x,n)`，但需要在 `formula_convention.notes` 说明

### 2.8 Filter op enum

`universe.filters[].op` 只能使用下面这些字符串，避免代码端无法 parse：

```text
eq, neq, in, not_in, between, not_between,
gt, gte, lt, lte,
nonmissing, nonzero, is_true, is_false
```

不要写 `>=`, `!=`, `excludes` 这类自由文本。


### 2.9 Breakpoint source enum

`portfolio.sort.breakpoint_source` 只能使用：

```text
nyse_only, full_sample, unspecified
```

- `nyse_only`: NYSE stocks define breakpoints.
- `full_sample`: all eligible stocks define breakpoints.
- `unspecified`: paper does not say.

> Note: the standardized engine implements only `nyse`/`full_sample`. A paper's
> conditional/paper-specific breakpoint rule is recorded in prose/`ambiguous_fields`
> but is clamped to the menu default at backtest time (no bespoke code is generated).

### 2.10 `portfolio.sort`: simple portfolio sort vs signal-rank transformation

`portfolio.sort` is a high-level description of how the paper uses the signal for grouping/ranking. It is **not always** a simple long-short portfolio sort.

`group_type` is an **open string**, not a closed enum. Use paper-faithful, machine-readable names. The template gives recommended examples, but new papers may require new values.

Recommended examples:

```text
decile, quintile, tercile, median,
scaled_decile_rank, rank_score, continuous_regressor,
industry_neutral_rank, paper_specific_custom
```

Use `group_type = "decile"` when decile groups directly define portfolio legs, e.g. high-minus-low or low-minus-high decile portfolios.

Use `group_type = "scaled_decile_rank"` when the paper ranks firms into deciles only to create a regression input / score variable, and the final factor return is produced by a regression-weighted or mimicking-portfolio construction.

If none of the recommended values fit, write a clear paper-specific string and explain it in `sort.role` and `sort.source.interpretation`. Do **not** modify the schema just to add a new grouping type.

Abarbanell & Bushee example:

```json
"sort": {
  "variable": "INV",
  "role": "signal rank transformation for regression, not simple portfolio sorting",
  "n_groups": 10,
  "group_type": "scaled_decile_rank",
  "ls_quantile": null,
  "breakpoint_source": "unspecified",
  "source": {"location": "", "quote": "", "interpretation": ""}
}
```

Why `ls_quantile = null` here: the paper uses annual scaled decile ranks as regressors and OLS-derived zero-investment weights. The main specification is **not** a simple top-decile-minus-bottom-decile spread, even though decile ranks are used internally.

Parser rule:

- If `portfolio.construction_type = "characteristic_sort"`, codegen may use `portfolio.sort` / `portfolio.sorts` to build sorted portfolio legs.
- If `construction_type = "regression_weighted"`, codegen must not infer a simple high-minus-low portfolio from `portfolio.sort`; the engine runs a Fama-MacBeth estimator instead.

`registry.build_config` reads the flat `portfolio.sorts` / `portfolio.construction_type` / `portfolio.return_combination.type` and `portfolio.universe_filters` to *select* which standardized step implementation runs (no plugin hooks are generated). When the paper prose (`long_leg`/`short_leg`/`universe`) describes a non-standard construction but these structured fields are unpopulated, ReviewGate emits a warning; the engine then runs the menu default (a single-variable sort), and any residual gap is decomposed by step7's replication-gap analysis.

### 2.11 Portfolio weighting

The standardized engine implements exactly two weighting schemes: **value-weight
(`vw`)** and **equal-weight (`ew`)**. Record the paper's choice in
`portfolio.weighting` (`vw` / `ew` / `unspecified`). Any custom scheme a paper
states (capped-VW, signal/rank-weighted, regression-derived, inverse-vol, …) is
**not** code-generated; it is clamped to the menu default at backtest time.
Capture the paper's exact custom rule in prose / evidence / `ambiguous_fields`
so the replication-gap analysis (step7) can flag the divergence — there is no
separate `weighting_scheme` block anymore.

### 2.12 Simple long-short direction

Use this field narrowly:

```json
"paper_reports_explicit_simple_long_short_strategy": true
```

means the paper explicitly defines a **tradable simple sorted-leg long-short strategy**, such as "buy low-growth stocks and short high-growth stocks."

Do **not** set it to `true` merely because the paper reports a high-minus-low / low-minus-high spread as a comparison statistic.

Example: Asset Growth reports high-minus-low spreads in Table II, but does not explicitly define a tradable simple long-short strategy. Therefore:

```json
"paper_reports_explicit_simple_long_short_strategy": false,
"paper_spread_direction": "high_minus_low"
```

If the paper only compares high/low portfolios but does not state a tradable long-short strategy, use:

```json
"paper_reports_explicit_simple_long_short_strategy": false
```

and record any backtest-needed direction in `portfolio.implied_factor_direction`, marked as inferred when appropriate.

For regression-weighted zero-investment papers like Abarbanell & Bushee, also use:

```json
"paper_reports_explicit_simple_long_short_strategy": false,
"paper_spread_direction": "not_applicable"
```

because positive regression weights being bought and negative weights being shorted is **not** the same as a simple high-minus-low sorted spread. The executable construction should come from `portfolio.weighting_scheme.type = "regression_derived_zero_investment"` and `reported_results.return_calculation.portfolio_return.construction_type = "regression_weighted"`.

### 2.12.1 Main field vs inferred candidate

If a high-impact field is not explicit in the paper, do **not** silently write an inferred value into the main field for original-method codegen.

Use the main field value:

```json
"breakpoint_source": "unspecified"
```

and put the candidate inference in `ambiguous_fields`:

```json
{
  "field": "portfolio.sort.breakpoint_source",
  "status": "unspecified",
  "candidate_value": "full_sample",
  "reason": "Paper states decile cutoffs but does not explicitly state NYSE-only vs all-stock cutoffs.",
  "needs_human_confirmation": true
}
```

This prevents codegen from treating a reviewer-level inference as a paper-stated fact. After Review Gate approves a candidate, the approved implementation config may use that value.

### 2.13 Return calculation for paper results

If the paper reports abnormal returns, alphas, BHAR, CAR, event-window returns, or factor returns, record the return construction in `reported_results.return_calculation`. Use a **two-layer structure**:

| Field | Meaning |
|---|---|
| `input_return` | firm/security-level return used as input, e.g. monthly stock return or size-adjusted BHAR |
| `portfolio_return` | how input returns are combined into the final factor portfolio return |

If the paper states return-construction special handling, record it under the general `input_return.adjustments[]` array, not as a one-off field and not only in `data.sample_coverage_notes`.

Example:

```json
"adjustments": [
  {
    "type": "delisting_return_handling",
    "action": "include_delisting_return_then_reinvest_in_size_portfolio_benchmark",
    "description": "Include the delisting return, then reinvest remaining-period returns in the size benchmark.",
    "source": {"location": "", "quote": "", "interpretation": ""}
  }
]
```

Use this general array for paper-stated return adjustments such as delisting-return handling, dividend/total-return treatment, benchmark reinvestment, risk-free-rate subtraction, currency conversion, or event-window compounding rules.

Use the same `portfolio_return` shape across papers:

```json
"portfolio_return": {
  "construction_type": "characteristic_sort | regression_weighted | other",
  "sorts": [],
  "weighting": {"type": "", "variants": []},
  "return_combination": {"type": "", "expression": "", "long_leg": null, "short_leg": null},
  "regression": null,
  "reported_frequency": "",
  "holding_period": "",
  "source": {"location": "", "quote": "", "interpretation": ""}
}
```

Examples:

- AssetGrowth: `construction_type = characteristic_sort`, one ASSETG decile sort, `return_combination.type = extreme_group_spread`.
- Ball 2016: `construction_type = characteristic_sort`, size/profitability 2x3 sorts, `return_combination.type = average_leg_spread`.
- Abarbanell & Bushee: `construction_type = regression_weighted`, no explicit portfolio sort, `return_combination.type = single_signal_portfolio_return`, with regression details in `regression`.

Do not use the generic name `aggregation`; use `return_combination` to clarify that this is the rule for combining portfolio legs/returns into the final factor return.

### 2.14 Reported results direction

`reported_results.spreads` 应保留 paper 原始方向，例如 paper 报 `high_minus_low = -1.73` 就照填。后续 evaluator 负责和 backtest 方向对齐。

---

## 3. Final Field Decisions / Parser Contract

This section records the final design decisions from the pilot annotations. Future extractor runs should follow these rules to avoid schema drift.

### 3.1 MethodSpec is an individual factor spec, not a strategy spec

A `.methodspec.json` represents **one individual factor / signal**. It should not mix in paper-level aggregate strategy logic as the main spec.

- Good: `GrSaleToGrInv.methodspec.json` represents the paper's `INV` signal / C&Z target factor.
- Bad: putting Abarbanell & Bushee's full nine-signal aggregate strategy inside every individual signal JSON.

If a paper defines an aggregate strategy, record it only as secondary context for now and create a future `.strategy.json` if needed.

```text
factor MethodSpec: one signal -> one factor portfolio return
strategy spec: multiple factor portfolio returns -> aggregate strategy return
```

Current decision: **do not add** `spec_type`, `paper_strategy_context`, or `target_signal` to factor JSONs yet. Keep the individual factor files simple. Document future strategy-level support in [[readme]].

### 3.2 Do not add `target_signal`; use existing signal fields

Do not add a separate `target_signal` field. It duplicates:

```json
"signal": {
  "paper_variable_name": "INV"
}
```

If the paper uses transformed/ranked versions such as `RINV`, explain that in `interpretation`, not as a new hard field.

Example interpretation:

```text
For paper variable INV, the regression uses the scaled decile-rank version of the signal, e.g. RINV. The associated coefficient is interpreted as the return to this signal-specific factor portfolio.
```

### 3.3 Return construction must use `input_return` + `portfolio_return`

Always express reported return construction in two layers:

```json
"reported_results": {
  "return_calculation": {
    "name": "factor_portfolio_return",
    "input_return": {},
    "portfolio_return": {}
  }
}
```

| Field | Meaning | Codegen role |
|---|---|---|
| `input_return` | security/firm-level return before portfolio construction | build or load the per-stock return series |
| `portfolio_return` | how securities/legs/regression outputs become the factor return | build factor portfolio return |

Source rule: `return_calculation` is only a container. Do **not** add `return_calculation.source`. Put evidence in:

- `input_return.source`: how the security/firm-level return is computed, e.g. monthly return, BHAR, CAR, size-adjusted return.
- `portfolio_return.source`: how the factor portfolio return is constructed, e.g. sorted-leg spread, regression-weighted coefficient, alpha.

Do **not** use `data.return_measure`; it duplicates `reported_results.return_calculation.name`. Use only:

```json
"data": {
  "return_data_frequency": "monthly"
}
```

and:

```json
"reported_results": {
  "return_calculation": {"name": "factor_portfolio_return"}
}
```

### 3.4 Standard `portfolio_return` shape

Use the same keys for all papers, even if some values are empty or `null`:

```json
"portfolio_return": {
  "construction_type": "characteristic_sort | regression_weighted | other",
  "sorts": [],
  "weighting": {"type": "", "variants": []},
  "return_combination": {"type": "", "expression": "", "long_leg": null, "short_leg": null},
  "regression": null,
  "reported_frequency": "",
  "holding_period": "",
  "source": {"location": "", "quote": "", "interpretation": ""},
  "interpretation": ""
}
```

#### `construction_type`

Recommended values:

| Value | Meaning | Example |
|---|---|---|
| `characteristic_sort` | portfolios are formed by sorting on one or more characteristics | AssetGrowth, Ball 2016 |
| `regression_weighted` | portfolio return is implied by regression/mimicking-portfolio weights | Abarbanell & Bushee |
| `factor_model_alpha` | reported return is an alpha from a factor model | FF3/Carhart alpha tables |
| `event_window_return` | event-window CAR/BHAR around announcements | earnings announcement tests |
| `other` | paper-specific construction not covered above | must cite exact source |

#### `sorts`

`sorts` is always an array.

One-way sort example:

```json
"sorts": [
  {"variable": "ASSETG", "group_type": "decile", "n_groups": 10, "breakpoint_source": "unspecified"}
]
```

2x3 sort example:

```json
"sorts": [
  {"variable": "size", "group_type": "median", "n_groups": 2, "breakpoint_source": "nyse_only"},
  {"variable": "CbOP", "group_type": "tercile", "n_groups": 3, "breakpoint_source": "nyse_only", "breakpoints": [0.3, 0.7]}
]
```

Regression-weighted papers can use:

```json
"sorts": []
```

because the final factor return is not a simple sorted-leg spread. If the paper still rank-transforms signals before regression, record that under `portfolio.sort` with `group_type = "scaled_decile_rank"` and `ls_quantile = null`; do not duplicate it as sorted portfolio legs here.

#### `weighting`

This is local to the reported return construction. It should be consistent with `portfolio.weights` / `portfolio.weighting_scheme`.

Examples:

```json
"weighting": {"type": "reported_variants", "variants": ["equal_weight", "value_weight"]}
```

```json
"weighting": {"type": "value_weight", "variants": ["value_weight"]}
```

```json
"weighting": {"type": "regression_derived_zero_investment", "variants": []}
```

#### `return_combination`, not `aggregation`

Do **not** use the generic field name `aggregation`. It is ambiguous. Use `return_combination`, meaning:

```text
how portfolio legs / regression-implied returns are combined into final factor return
```

Recommended `return_combination.type` values:

| Value | Meaning | Example |
|---|---|---|
| `extreme_group_spread` | top-minus-bottom or high-minus-low spread | AssetGrowth Table II Panel B |
| `average_leg_spread` | average high legs minus average low legs | Ball 2016 RMWOP / RMWCbOP |
| `single_signal_portfolio_return` | one signal's regression-weighted portfolio return | Abarbanell individual signals |
| `full_portfolio_return` | one long-only or full portfolio return, no spread | some long-only tests |
| `alpha_estimate` | reported result is model alpha | FF3/Carhart alpha panels |
| `other` | paper-specific rule | cite exact source |

### 3.5 Three canonical examples

#### AssetGrowth style: characteristic-sort decile return

```json
"return_calculation": {
  "name": "factor_portfolio_return",
  "input_return": {
    "name": "monthly_stock_return",
    "data_frequency": "monthly",
    "expression": "ret_i,m",
    "benchmark": null
  },
  "portfolio_return": {
    "construction_type": "characteristic_sort",
    "sorts": [
      {"variable": "ASSETG", "group_type": "decile", "n_groups": 10, "breakpoint_source": "unspecified"}
    ],
    "weighting": {"type": "reported_variants", "variants": ["equal_weight", "value_weight"]},
    "return_combination": {
      "type": "extreme_group_spread",
      "expression": "high_minus_low",
      "long_leg": "high_asset_growth_decile",
      "short_leg": "low_asset_growth_decile",
      "note": "Paper-reported direction; implied backtest factor may use low-minus-high."
    },
    "regression": null,
    "reported_frequency": "monthly",
    "holding_period": "July_t_to_June_t_plus_1"
  }
}
```

#### Ball 2016 style: Fama-French 2x3 RMW factor

```json
"return_calculation": {
  "name": "factor_portfolio_return",
  "input_return": {
    "name": "monthly_stock_return",
    "data_frequency": "monthly",
    "expression": "ret_i,m",
    "benchmark": null
  },
  "portfolio_return": {
    "construction_type": "characteristic_sort",
    "sorts": [
      {"variable": "size", "group_type": "median", "n_groups": 2, "breakpoint_source": "nyse_only"},
      {"variable": "CbOP", "group_type": "tercile", "n_groups": 3, "breakpoint_source": "nyse_only", "breakpoints": [0.3, 0.7]}
    ],
    "weighting": {"type": "value_weight", "variants": ["value_weight"]},
    "return_combination": {
      "type": "average_leg_spread",
      "expression": "0.5 * (small_robust + big_robust) - 0.5 * (small_weak + big_weak)",
      "long_leg": "robust/high profitability portfolios",
      "short_leg": "weak/low profitability portfolios"
    },
    "regression": null,
    "reported_frequency": "monthly_factor_series_with_annualized_statistics",
    "holding_period": "annual_rebalance_end_of_June"
  }
}
```

#### Abarbanell & Bushee style: regression-weighted signal portfolio

```json
"return_calculation": {
  "name": "factor_portfolio_return",
  "input_return": {
    "name": "size_adjusted_buy_and_hold_abnormal_return",
    "paper_variable": "BHAR(+m)_it",
    "data_frequency": "daily",
    "expression": "prod(1 + R_i,j) - prod(1 + SAR_k,j)",
    "benchmark": "value_weighted_size_decile_return",
    "adjustments": [
      {
        "type": "delisting_return_handling",
        "action": "include_delisting_return_then_reinvest_in_size_portfolio_benchmark",
        "description": "If a firm delists, include the delisting return and then reinvest in the size portfolio benchmark for the remaining window."
      }
    ]
  },
  "portfolio_return": {
    "construction_type": "regression_weighted",
    "sorts": [],
    "weighting": {"type": "regression_derived_zero_investment", "variants": []},
    "return_combination": {
      "type": "single_signal_portfolio_return",
      "expression": "return is the regression-weighted zero-investment portfolio return associated with this signal-specific scaled decile-rank regressor",
      "long_leg": null,
      "short_leg": null,
      "note": "Aggregate paper strategy sums coefficients across signals; individual factor JSON records only the signal-specific return."
    },
    "regression": {
      "equation": "BHAR(+m)_it = a0 + Σ_k a_k RSIGNAL_k,it + a10 RBETA_it + a11 RCEPS_it + e_it",
      "dependent_variable": "input_return",
      "controls": ["RBETA", "RCEPS"]
    },
    "reported_frequency": "event_cumulation",
    "holding_period": "fourth_month_after_fiscal_year_end_t_through_m_subsequent_months"
  }
}
```

### 3.6 `portfolio.weights` vs `reported_results.return_calculation.portfolio_return.weighting`

These are related but not identical.

| Field | Role |
|---|---|
| `portfolio.weights` | coarse summary of paper portfolio weighting, useful for quick review |
| `portfolio.weighting_scheme` | detailed custom weighting rule when `weights = ["other"]` |
| `reported_results.return_calculation.portfolio_return.weighting` | weighting used specifically in the reported return construction |

Do not duplicate source evidence:

- Simple EW/VW: use `portfolio.weights_source`; `portfolio.weighting_scheme = null`.
- Custom weighting: use `portfolio.weighting_scheme.source`; omit `portfolio.weights_source`.
- In `return_calculation`, cite evidence at the calculation layer: use `input_return.source` for firm/security-level returns and `portfolio_return.source` for factor portfolio construction. Do not use top-level `return_calculation.source`; it duplicates the child sources.

### 3.7 `sample_coverage_notes` is a warning / normalizer hint, not executable config

Parser contract:

- Do not turn `sample_coverage_notes` into row-level filters.
- Do not treat fields mentioned only inside `sample_coverage_notes` as formula inputs.
- Do surface them in Review Gate and implementation warnings.
- The normalizer may translate them into data-loader requirements, e.g. "use survivor-bias-free Compustat/CRSP coverage".

Typical use: a paper says it includes delisted firms to avoid survivorship bias. This is a coverage requirement, not a filter. The code should not do `df = df[df.delisted == true]`; it should ensure the data source is not survivor-only.

Do not add `historical_cusip` to `data.required_fields` unless it is directly required as an executable field by the current backtest implementation. In extractor output, it is usually a normalizer/data-loader hint.

### 3.8 `robustness_or_secondary_specs` is optional and not P0 codegen

Use this for paper-stated but non-main specifications:

- holdout sample / out-of-sample period;
- alternative sign strategy;
- earnings-based decomposition;
- secondary alpha panels;
- footnote simple hedge portfolios;
- robustness screens or trimming variants.

These should not overwrite the main fields. Codegen P0 may ignore them or emit warnings. Normalizer/backtester can support them later as optional runs.

### 3.9 Parser guidance for codegen

A downstream parser should mainly consume:

```text
signal.formula
sample
timing
universe
portfolio
reported_results.return_calculation.input_return
reported_results.return_calculation.portfolio_return
```

It should not execute:

```text
source.quote
source.interpretation
annotator_notes
paper_sections
robustness_or_secondary_specs unless explicitly requested
sample_coverage_notes except as warnings / normalizer hints
```

Suggested dispatch:

```python
p = spec["reported_results"]["return_calculation"]["portfolio_return"]

if p["construction_type"] == "characteristic_sort":
    build_sorted_portfolios(p["sorts"], p["weighting"], p["return_combination"])
elif p["construction_type"] == "regression_weighted":
    build_regression_weighted_portfolio(input_return, p["regression"], p["weighting"], p["return_combination"])
else:
    stop_or_request_human_review()
```

If any high-impact field is `ambiguous`, `conflicting`, or `unspecified`, codegen should stop or ask for review rather than silently assuming.

---

## 4. Blank JSON Template

```json
{
  "schema_version": "methodspec.v1",
  "factor_id": "",
  "cz_acronym": "",
  "annotation_status": "draft_human_annotation",
  "review_status": "pending",
  "formula_convention": {
    "time_index_base": "formation_year_t",
    "default_accounting_period": "fiscal_year_ending_in_calendar_year",
    "suffix_rules": {
      "_t": "value associated with formation year t, unless field-specific timing overrides it",
      "_t_minus_1": "accounting value for fiscal year ending in calendar year t-1",
      "_t_minus_2": "accounting value for fiscal year ending in calendar year t-2",
      "_m": "monthly value at portfolio formation month m, when a monthly signal is specified",
      "lag(x,n)": "n-period lag of x at the data frequency specified by the signal"
    },
    "notes": ""
  },
  "paper": {
    "pdf_file": "",
    "title": "",
    "citation": "",
    "paper_sections": [],
    "evidence_sections": []
  },
  "signal": {
    "paper_variable_name": "",
    "factor_name": "",
    "economic_intuition": {
      "value": "",
      "source": {"location": "", "quote": "", "interpretation": ""}
    },
    "definition": {
      "value": "",
      "source": {"location": "", "quote": "", "interpretation": ""}
    },
    "formula": {
      "expression": "",
      "paper_expression": "",
      "source": {"location": "", "quote": "", "interpretation": ""},
      "inputs": []
    },
    "category": "continuous",
    "sign": {
      "value": null,
      "meaning": "1 = high signal -> high returns; -1 = high signal -> low returns",
      "source": {"location": "", "quote": "", "interpretation": ""}
    }
  },
  "data": {
    "frequency": "annual",
    "return_data_frequency": "monthly",
    "sources": [
      {"dataset": "", "tables": [], "use": ""}
    ],
    "required_fields": [
      {"field": "", "dataset": "", "table": "", "description": ""}
    ],
    "sample_coverage_notes": [
      {
        "topic": "",
        "paper_action": "",
        "details": "",
        "implementation_relevance": "",
        "normalizer_hint": "",
        "source": {"location": "", "quote": "", "interpretation": ""}
      }
    ],
    "source_note": ""
  },
  "sample": {
    "formation_years": {"start": null, "end": null},
    "return_sample": {"start": {"year": null, "month": null}, "end": {"year": null, "month": null}},
    "source": {"location": "", "quote": "", "interpretation": ""}
  },
  "timing": {
    "formation": {"month": null, "date_rule": "end_of_month", "description": ""},
    "rebalance_frequency": "annual",
    "holding_period_months": null,
    "return_window": {"start": "", "end": ""},
    "accounting_lag_months": null,
    "accounting_data_used": {
      "current_period": {"label": "", "description": "", "used_for": ""},
      "lag_period": {"label": "", "description": "", "used_for": ""},
      "base_time_index": "formation_year_t"
    },
    "skip_months": null,
    "source": {"location": "", "quote": "", "interpretation": ""}
  },
  "universe": {
    "description": "",
    "source": {"location": "", "quote": "", "interpretation": ""},
    "exchange_names": {
      "value": [],
      "source": {"location": "", "quote": "", "interpretation": ""}
    },
    "filters": [
      {"field": "", "op": "", "value": null, "source": {"location": "", "quote": "", "interpretation": ""}}
    ],
    "missing_policy": {
      "action": "unspecified",
      "source": {"location": "", "quote": "", "interpretation": ""},
      "confidence": "low"
    },
    "winsorize_bounds": {
      "status": "not mentioned or not specified in the paper",
      "lower_pct": null,
      "upper_pct": null,
      "applies_to": "main_portfolio_spec",
      "source": {"location": "", "quote": "", "interpretation": ""}
    }
  },
  "portfolio": {
    "sort": {
      "variable": "",
      "role": "simple portfolio sorting OR signal rank transformation for regression",
      "n_groups": null,
      "group_type": "decile",
      "ls_quantile": null,
      "breakpoint_source": "unspecified",
      "source": {"location": "", "quote": "", "interpretation": ""}
    },
    "weights": [],
    "weights_source": {"location": "", "quote": "", "interpretation": ""},
    "weighting_scheme": null,
    "paper_reports_explicit_simple_long_short_strategy": null,
    "paper_spread_direction": "unspecified",
    "implied_factor_direction": {
      "long_leg": "",
      "short_leg": "",
      "use_for_backtest_if_needed": null,
      "note": ""
    },
    "overlapping_portfolios": null
  },
  "reported_results": {
    "return_horizon": "monthly",
    "return_type": "raw",
    "return_type_explanation": "raw = realized portfolio return before risk adjustment; alpha = risk-adjusted intercept; size_adjusted_bhar = compounded security return minus compounded benchmark return",
    "return_calculation": {
      "name": "factor_portfolio_return",
      "input_return": {
        "name": "",
        "paper_variable": "",
        "data_frequency": "",
        "expression": "",
        "benchmark": null,
        "adjustments": [],
        "source": {"location": "", "quote": "", "interpretation": ""}
      },
      "portfolio_return": {
        "construction_type": "",
        "sorts": [],
        "weighting": {"type": "", "variants": []},
        "return_combination": {"type": "", "expression": "", "long_leg": null, "short_leg": null},
        "regression": null,
        "reported_frequency": "",
        "holding_period": "",
        "source": {"location": "", "quote": "", "interpretation": ""}
      }
    },
    "main_table": "",
    "spreads": {},
    "comparison_policy": {
      "preserve_paper_direction": true,
      "align_backtest_to_paper_direction_before_comparison": true,
      "note": ""
    }
  },
  "robustness_or_secondary_specs": [],
  "ambiguous_fields": [],
  "extensions": {},
  "annotator_notes": ""
}
```

---

## 5. Required vs Optional for Pilot

### Required before Review Gate

- `factor_id`
- `paper`
- `signal.definition`
- `signal.formula`
- `signal.sign`
- `data.frequency`
- `data.required_fields`
- `sample`
- `timing`
- `universe`
- `portfolio.sort`
- `portfolio.weights`
- `reported_results` if paper reports comparable spread / alpha
- `ambiguous_fields` for all inferred or conflicting high-impact decisions

### Can be empty in early draft

- `cz_acronym` if same as `factor_id`
- `robustness_or_secondary_specs`
- `extensions`
- `annotator_notes`

---

## 6. Common Annotation Mistakes

- 把 C&Z / OSAP / factor zoo metadata 当成 extractor 参考来源；extractor evidence 必须来自 original paper。
- 把 C&Z / OSAP 的 implementation choice 当成 paper-stated fact。
- 以 C&Z acronym 作为 extractor target；正确做法是以 paper-original signal/factor 为 target，C&Z acronym 只是 optional downstream mapping metadata。
- 用 C&Z definition 去改写 paper formula；如果二者不同，active MethodSpec 保留 paper formula，差异只放 `ambiguous_fields` / `annotator_notes`。
- 为 downstream variant 生成 paper MethodSpec，即使 paper 没有原样定义这个因子；例如 `pchgm_pchsale` 若只是 A&B `GM` 的后续变体，不应作为 A&B paper-original factor 生成。
- `source.quote` 写成自己的 paraphrase，而不是 paper 原文短句。
- `formula.expression` 用了 `t-1`，但没有说明相对于 formation year 还是 fiscal year。
- `signal.formula.inputs` 写成 full objects（含 dataset/table/description）；现在应写成字符串数组，例如 `["sale", "inventory"]`。
- `signal.formula.expression`、`signal.formula.inputs`、`data.required_fields[].field` 三者变量名不一致，例如 expression 用 `inventory_t`，inputs 却写 `invt_or_finished_goods_inventory`。
- 把 accounting disclosure delay / return window start 写成 `skip_months`；如果 paper 已在 `timing.return_window.start` 说明从第 4 个月/4 月开始，通常不要再填 `skip_months`。
- paper 没有 explicit long-short strategy，却直接填 long/short 为 paper-stated。
- paper 只报告 high-minus-low / low-minus-high spread 作为比较统计，却把 `paper_reports_explicit_simple_long_short_strategy` 设为 `true`；该字段只表示 paper 明确提出 tradable simple long-short strategy。
- 把 regression-weighted zero-investment strategy 当成 `paper_reports_explicit_simple_long_short_strategy = true`；这个字段只表示 paper 明确提出的 tradable simple sorted-leg long-short strategy。
- paper 同时报 EW/VW，却只记录其中一个且没有说明。
- 把 robustness sample filter 写进 main `universe.filters`。
- 把 winsorization robustness 当成 main specification。
- 在 extractor output 里提前写入 CRSP `exchcd` / CCM merge keys 等 implementation mapping。
- paper 未明确 breakpoint universe 时，把 `breakpoint_source` 直接填成 `full_sample` 或 `nyse_only`；原始 MethodSpec 应先填 `unspecified`，把候选推断放到 `ambiguous_fields.candidate_value`。
- 在 `sample.return_sample` 同时混用 string date 和 year/month，造成不一致。
- 把 `sample.return_sample.end` 直接设成 paper main sample 的最后一年，而不是实际最后一个 return window 的结束月份；例如 Abarbanell & Bushee main fiscal years 1974-1988，但 1988 signal 的 12-month return window ends in 1990-03。
- copy-paste ranked signal explanation 后忘记改变量名，例如每个 Abarbanell signal 都写成 `INV -> RINV`；应逐个确认 `AR -> RAR`, `GM -> RGM`, `S&A -> RS&A`, `ETR -> RETR`, `LF -> RLF`。
- 两个 downstream acronyms 映射到同一个 paper signal 时不标注 duplicate/mapping ambiguity；例如 `ChInvIA` / `GrSaleToGrInv` both map to paper `INV`，`GrGMToGrSales` / `pchgm_pchsale` both map to paper `GM`。
- 在 `data.required_fields` 同时写语义重复 alias，例如 `returns` 和 `daily_ret`、`firm_size_decile_return` 和 `size_decile_benchmark_daily_return`；保留更具体、更接近 return_calculation 的字段名。
- `signal.sign.value` 只根据 mechanism/结论段填方向，而忽略 main reported return table 的相反或不显著证据；有冲突时填 `null` 并在 `ambiguous_fields` 解释。
- 在 `reported_results.return_calculation` 里直接写自由文本，而不是使用统一的 `input_return` + `portfolio_return` 结构。
- 在 `reported_results.return_calculation.source` 放重复 evidence；`return_calculation` 是 container，source 应放在 `input_return.source` 和 `portfolio_return.source`。
- 使用 `aggregation` 作为字段名；应使用 `return_combination`。
- 新增 `target_signal` / `coefficient` 等字段；应使用已有 `signal.paper_variable_name`，并在 `interpretation` 里解释 ranked signal（如 RINV）。
- 把 aggregate paper strategy（例如 sum of signal coefficients）混入 individual factor MethodSpec 的 main return calculation。
- 使用 `data.return_measure`；应使用 `data.return_data_frequency` + `reported_results.return_calculation.name`。
- 把 `historical_cusip` / delisted-firm treatment 写进 `data.required_fields`；应放进 `data.sample_coverage_notes` 作为 normalizer hint。
- paper 明确给出 delisting-return/reinvestment 等 return-construction 规则时，只放到 `sample_coverage_notes` 而不放到 `reported_results.return_calculation.input_return.adjustments[]`；返回计算规则应进入 return-calculation layer，但用 general array，不新增 one-off field。
- 把 `data.sample_coverage_notes` 当成 `universe.filters` 使用；coverage note 是数据覆盖/偏差提醒，不是“筛掉谁”的规则。
- `winsorize_bounds.lower_pct/upper_pct` 是 null 时不写原因；应加大白话 `status` 说明是 paper 没提，还是提了 truncation 但 bounds 不明确。
- 把 `portfolio.sort.group_type` 当成 schema enum 维护；它应该是开放字符串。遇到 paper-specific grouping 时，写清楚字符串并在 `role` / `source.interpretation` 解释，不要为了每种新类型改 schema。
- paper 只是把 signal 做 decile-rank regression input，却把 `portfolio.sort.group_type` 写成普通 `decile` 且 `ls_quantile = 0.1`；这会让 codegen 误生成 high-minus-low。应使用类似 `scaled_decile_rank` 的开放字符串 + `ls_quantile = null`。

---

## 7. Example Instance

完整 filled example 不再嵌入本模板，避免模板过长。见：

- [[annotations/AssetGrowth.methodspec.json]]

## 8. Validation Schema

Extractor-output JSON Schema: [[schema/methodspec.v1.schema.json]]
