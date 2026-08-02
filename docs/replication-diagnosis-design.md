# Factor Replication Diagnosis Design

## 1. Purpose

This document defines how the project uses original papers, Chen and Zimmermann
(C&Z) artifacts, agent-generated code, and our backtest results to answer the
research question:

> When a published factor can or cannot be replicated, which observable cause
> best explains the outcome?

The objective is not merely to compare our output with C&Z or to maximize
agreement with a benchmark. The objective is to turn a replication gap into an
auditable diagnosis. C&Z is an independent, explicit implementation that helps
identify where two reasonable attempts diverge. It is not assumed to be the
unique ground truth.

The central constraint remains unchanged:

> The agent reads the paper and produces a MethodSpec and signal code without
> access to C&Z evaluation artifacts. C&Z enters only after those agent artifacts
> have been frozen.

This separation lets the project evaluate both independent paper understanding
and replication quality without leaking the reference implementation into the
answer.

### 1.1 LLM usage boundary

The research claim depends on a strict separation between what the LLM may
produce and what must be deterministic. The LLM appears at exactly three
auditable points, and never controls an empirical conclusion:

1. **Step 1 — extraction:** paper → MethodSpec.
2. **Step 3 — code generation:** approved MethodSpec → `compute_signal()` only.
3. **Final analysis — explanation layer (optional):** turning already-computed
   numbers into a human-readable diagnosis or a difference classification,
   always tagged `LLM-assisted` and human-reviewable.

Everything empirical is fixed, deterministic code: data loading, point-in-time
linking, lags, universe, breakpoints, weighting, return construction, t-stats,
correlations, attribution, accuracy metrics, and every pass/fail threshold.

> Hard line: every core numerical conclusion in the paper must be reproducible
> with the LLM switched off. The LLM may read the paper, write the signal
> formula, and *explain* results — it may never *produce* a number or a
> threshold that enters a conclusion.

This keeps a clean split between **LLM ability** (extraction fidelity in RQ1 and
signal implementation in RQ2) and **implementation sensitivity** (RQ3–RQ5,
LLM-free): the agent's language ability is measured where language belongs,
while every empirical result is produced by deterministic code.

---

## 2. The Four Evidence Families

A replication study for one factor has four distinct evidence families. They
must not be collapsed into one notion of a "track."

### 2.1 Original-paper evidence

The paper provides:

- the economic claim and expected sign;
- the signal definition and required variables;
- sample dates and security universe;
- timing, formation, holding, and rebalance rules;
- portfolio construction choices, when stated;
- reported spreads, alphas, t-statistics, tables, and variants;
- quotations supporting each extracted field.

These facts are represented in the paper-first `MethodSpec`. A paper-reported
number is an external observation, not executable code.

A paper may report several valid targets, such as EW and VW portfolios or raw
returns and factor-model alphas. Every target must therefore be identified by a
variant key rather than compressed into a single unqualified result.

Example:

```yaml
paper_target_id: value_weighted_year1_raw_monthly_low_minus_high
value: 0.0105
t_stat: 5.04
sample_start_year: 1968
sample_end_year: 2002
units: monthly_return
source: Table II, Panel B.2, Year 1
```

### 2.2 C&Z evidence

The local C&Z repository contains three different kinds of evidence:

1. `SignalDoc.csv`: C&Z metadata and their selected baseline implementation.
2. `Signals/pyCode/Predictors/*.py`: per-factor Python signal implementations.
3. `Portfolios/Code/*.R`: a shared R portfolio engine driven by SignalDoc.

Legacy Stata predictor code is also present and can be used as an internal C&Z
cross-check. It is not a separate economic specification.

C&Z therefore represents an executable interpretation:

```text
C&Z predictor code
+ C&Z point-in-time data preparation
+ SignalDoc portfolio settings
+ shared C&Z R portfolio engine
= C&Z replication result
```

C&Z may make choices not stated in the paper. Such choices must be labeled
`cz_supplemented`, not silently promoted to paper truth.

### 2.3 Agent evidence

The agent independently produces:

- an extracted MethodSpec;
- review notes and human resolutions;
- a formula-only `compute_signal()` plugin;
- a standalone controlled backtest script;
- validation and technical-repair history.

The agent is allowed to generate only signal-formula code. The controlled
pipeline owns source loading, point-in-time linking, lags, universe filters,
breakpoints, weighting, return construction, and metrics.

### 2.4 Our executed evidence

A run should produce:

- the exact MethodSpec, plugin, config, and data hashes;
- the firm-month signal series;
- portfolio membership and breakpoint diagnostics;
- monthly leg and long-short return series;
- aggregate metrics and sample-segment metrics;
- logs and repair history.

The current implementation persists run metadata and aggregate metrics, while
return CSVs live under the script results directory. Signal-series persistence,
track-specific artifact paths, and first-class diagnostic reports remain to be
implemented. Until then, the repository does not yet contain the complete
evidence needed for automated causal diagnosis.

---

## 3. Research Questions

The system should answer five ordered questions for every factor.

### RQ1: Did the agent understand the paper correctly?

Compare the frozen MethodSpec with paper quotations and, only afterward, with
C&Z metadata. Classify each disagreement as:

- `llm_misread`;
- `paper_ambiguous`;
- `paper_silent`;
- `paper_internally_conflicting`;
- `cz_supplemented`;
- `reasonable_divergence`;
- `target_variant_mismatch`.

### RQ2: Did the agent implement the signal correctly?

Run the agent and C&Z signal formulas on a harmonized input panel where
possible. Compare firm-month outputs, not source-code text alone.

### RQ3: Did the controlled portfolio engine implement the intended method?

Hold the signal fixed and vary only portfolio-construction logic. Compare our
engine with the C&Z portfolio implementation and with the reviewed MethodSpec.

### RQ4: Are remaining differences caused by data?

Hold code and configuration as fixed as possible, then vary data vintage,
coverage, linking, and CRSP layout. Data differences must not be mislabeled as
formula or portfolio differences.

### RQ5: Is the factor statistically robust after implementation differences are removed?

Compare in-sample, post-sample, and post-publication behavior. Diagnose whether
the result is concentrated in microcaps, extreme months, or a small number of
firms.

The order matters. A statistical explanation is not credible until upstream
paper, implementation, and data mismatches have been evaluated.

---

## 4. Blindness and Information Boundaries

### 4.1 Before artifact freeze

The following may be used:

- paper PDF or converted paper text;
- registered data dictionary and source catalog;
- generic code-generation examples that do not reveal the target answer;
- deterministic engine menus and validation rules.

The following must not be supplied to the target-factor extractor, reviewer, or
MetaCoder as answers:

- the target row from C&Z `SignalDoc.csv`;
- the target C&Z predictor file;
- target C&Z firm-level signals;
- target C&Z portfolio returns;
- a target-specific C&Z result summary.

Using target C&Z code as a MetaCoder few-shot example would invalidate the
independence claim. Generic examples must exclude the evaluated target factor
and should be recorded in the run provenance.

### 4.2 Freeze point

The following artifacts are frozen before C&Z evaluation begins:

- extracted and reviewed MethodSpec;
- all human resolution entries;
- generated plugin code and hash;
- chosen paper target variant;
- data snapshot identifier;
- original-method run configuration.

### 4.3 After artifact freeze

C&Z artifacts may be loaded for:

- field-level MethodSpec comparison;
- signal-output comparison;
- portfolio-setting comparison;
- return-series comparison;
- diagnostic ablations.

C&Z findings never automatically rewrite MethodSpec or regenerate code. A human
may start a new, explicitly versioned MethodSpec after reviewing the diagnosis.
The original frozen attempt remains preserved.

---

## 5. The Diagnostic Experiment Matrix

A simple `original_method` versus `standardized_hxz` comparison cannot identify
the source of a replication gap. The main diagnosis requires controlled bridge
experiments.

Let:

- $S_A$: agent-generated signal;
- $S_C$: C&Z signal;
- $P_A$: our controlled portfolio engine configured to the reviewed paper method;
- $P_C$: C&Z portfolio engine/configuration;
- $D_A$: our frozen data snapshot;
- $D_C$: C&Z data or published C&Z output;
- $R_P$: paper-reported result.

The ideal experiment matrix is:

| Experiment | Signal | Portfolio | Data | Main purpose |
|---|---|---|---|---|
| E1 | Agent | Ours | Ours | Actual agent replication |
| E2 | C&Z | Ours | Harmonized/Ours | Isolate signal implementation |
| E3 | Agent | C&Z | Harmonized/C&Z | Cross-check portfolio behavior; optional |
| E4 | C&Z | C&Z | C&Z | C&Z reference replication |
| E5 | Fixed signal | Ours | Alternative snapshot | Isolate data sensitivity |
| E6 | Agent | Ours canonical profile | Ours | Robustness, not primary replication |

The minimum viable diagnostic set is E1, E2, and a published or downloaded E4
return series. E3 is useful but expensive because the C&Z R engine expects its
own data layout. E6 belongs to robustness analysis and must not be presented as
the main replication track.

### 5.1 Gap decomposition

If experiments are harmonized, define:

$$
\Delta_{signal} = R(S_A, P_A, D_A) - R(S_C, P_A, D_A)
$$

$$
\Delta_{portfolio} = R(S_C, P_A, D_H) - R(S_C, P_C, D_H)
$$

where $D_H$ is a harmonized data panel.

A data component can be estimated by holding signal and portfolio logic fixed:

$$
\Delta_{data} = R(S_C, P_C, D_A) - R(S_C, P_C, D_C)
$$

The remaining paper gap is:

$$
\Delta_{paper,residual} = R(S_C, P_C, D_C) - R_P
$$

These expressions are conceptual until both implementations can consume
harmonized inputs. When only published C&Z outputs are available, the report
must mark components as observational rather than experimentally identified.

### 5.2 Do not overclaim causality

A difference between two end-to-end results is not automatically attributable
to code. Attribution is credible only when one component changes while the
other relevant components remain fixed.

Every reported component must carry an identification level:

- `controlled`: one intended component changed on the same input;
- `harmonized`: inputs were transformed to a common contract but not byte-identical;
- `observational`: external published outputs were compared;
- `unidentified`: multiple components changed together.

### 5.3 What is executed versus downloaded

A recurring practical question is which comparison targets we actually *run*
through our engine and which we merely *load*. The answer differs by reference,
and it determines the identification level each comparison can claim.

**Agent side — always executed (our engine, our snapshot).** The agent signal
$S_A$ is frozen once, then run under several engine configs on the same data:

- `original_method` — config from the reviewed MethodSpec (paper-faithful);
- `standardized_hxz` — the uniform house-standard config;
- `ablation_*` / `factorial_*` — one (or a controlled subset of) parameters
  changed at a time.

Because only the config changes across these, they compare at `controlled`
level. This is experiment E1 plus its controlled variants (E6 for robustness).

**Comparison targets — run vs download:**

| Target | Run it? | How it is obtained | Identification level | Matrix cell |
|---|---|---|---|---|
| C&Z published portfolio returns | No | `dl_port()` download (already run on C&Z's own data + R engine) | `observational` | E4 |
| C&Z firm-level signal $S_C$ | **Yes** | download the signal, then run it through **our** engine under the **same** config as $S_A$ | `controlled` / `harmonized` | E2 (bridge) |
| HXZ **config** (on our agent signal) | **Yes** | run frozen $S_A$ × HXZ standardized config × our engine (`standardized_hxz` track) | `controlled` (internal variant) | E6 |
| HXZ **own factor result** | No (usually N/A) | no per-factor library to download; only a hand-collected published t-stat where it exists | `observational` | — |

Three consequences:

1. **C&Z returns are downloaded, not run.** They were produced on C&Z's own data
   vintage and R engine, so the comparison is `observational`: the gap cannot be
   cleanly attributed (the download omits breakpoints, weights, and security
   assignments — see [cz-reference.md](cz-reference.md) §5).
2. **The only genuinely *extra* backtest is the bridge (E2):** feed the C&Z
   signal into our engine under a config identical to the agent run. E2 is what
   isolates the *signal-implementation* difference at `controlled` level;
   the config ablations isolate the *portfolio-parameter* differences.
3. **"HXZ" means two different things — separate them.** *HXZ as a config* IS
   executed: the `standardized_hxz` track is exactly the frozen agent signal
   $S_A$ × the HXZ standardized config × our engine (same $S_A$ as every other
   track — only the config differs, so `original_method` vs `standardized_hxz`
   isolates the *config* effect at `controlled` level). *HXZ as an external
   factor result* is NOT run: HXZ has no per-factor result/signal library to
   download — it is primarily a methodology, and its own q-factors are a small
   fixed set (ME, I/A, ROE, EG), not a 200+ factor library like C&Z. So for an
   arbitrary factor there is no "HXZ implementation of this factor" to obtain;
   "compare to HXZ" only ever means running $S_A$ under the standardized config.
   The lone exception is a factor HXZ happens to have replicated in *Replicating
   Anomalies*, whose published t-stat can be compared `observational`ly
   (hand-collected, no API, not run).

In short: run the agent signal under every controlled config (including the
HXZ-standardized one); run **one** bridge track (C&Z signal × our engine);
download C&Z's published returns; and treat HXZ as a *config we execute on our
own signal*, never as a separate external result to run or download.

---

## 6. Layer-by-Layer Diagnostics

### 6.1 Paper and MethodSpec layer

Compare these fields before executing ablations:

- formula and sign;
- required concepts and physical columns;
- source table and identifier mapping;
- sample start/end;
- universe and exclusions;
- availability lag and formation month;
- rebalance and holding period;
- breakpoint source and quantiles;
- weighting;
- missing-value treatment;
- return type and factor direction;
- selected reported-result variant.

A field comparison must retain three values:

```text
paper-stated value
agent-reviewed value
C&Z value
```

It must also retain provenance and status. For example:

| Field | Paper | Agent | C&Z | Classification |
|---|---|---|---|---|
| Weighting | EW and VW both reported | VW selected as primary | EW baseline | target_variant_mismatch |
| Breakpoints | not stated | full sample, human resolution | blank/default | paper_silent |
| Sign | low minus high | low minus high | sign=-1 | agreement |

This prevents a legitimate variant difference from being mistaken for a
replication failure.

### 6.2 Signal layer

Required signal-comparison metrics:

- common firm-month count;
- coverage of agent relative to C&Z and vice versa;
- Pearson correlation;
- Spearman rank correlation;
- sign agreement;
- exact equality where appropriate;
- decile or quantile assignment agreement;
- overlap of long and short extreme portfolios;
- disagreement by year and data source;
- missingness disagreement;
- scale relationship, including monotonic transformations.

Rank agreement is often more important than level equality for sorting factors.
A signal can differ by a positive affine transformation and still produce the
same portfolios. Conversely, a high aggregate correlation can hide severe
disagreement in the extreme portfolios.

Suggested diagnostic statuses:

- `signal_exact_match`;
- `signal_rank_equivalent`;
- `signal_scale_only_difference`;
- `signal_timing_mismatch`;
- `signal_coverage_mismatch`;
- `signal_formula_mismatch`;
- `signal_direction_mismatch`;
- `signal_unavailable`.

### 6.3 Portfolio layer

With a fixed signal, compare:

- eligible universe count by month;
- breakpoint values by month;
- portfolio assignment counts;
- extreme-leg membership overlap;
- EW/VW stock weights;
- delisting-return treatment;
- holding and overlapping-portfolio behavior;
- long, short, and long-short monthly returns;
- return direction and units.

Implementation switches should include:

- universe filters;
- CRSP share/exchange-code treatment;
- breakpoint universe;
- number of portfolios;
- weighting;
- formation month;
- rebalance frequency;
- holding period;
- missing policy;
- return combination;
- delisting returns;
- minimum portfolio size.

One-at-a-time ablations are useful for screening, but their effects need not sum
to the total gap because switches interact. Use two-sided OAT from both endpoints
first. Escalate only the interacting subset to a factorial or Shapley analysis.

### 6.4 Data layer

Record and compare:

- CRSP format and vintage, including legacy versus CIZ;
- Compustat vintage and annual/quarterly table choice;
- CCM link-table vintage and filters;
- identifier resolution and one-to-many tie-breaks;
- observation dates and `time_avail_m`;
- delisted security coverage;
- share/exchange classification;
- sample endpoints;
- variable units and currency;
- raw-filter rules;
- missingness and duplicate rates.

Data diagnosis requires snapshot hashes and coverage summaries. "Same WRDS
source" is not enough to establish the same data.

### 6.5 Statistical layer

After upstream mismatches are controlled, evaluate:

- mean return and t-stat over the matched paper sample;
- monthly return correlation with C&Z;
- alpha and t-stat under the same factor model;
- in-sample, between-sample, and post-publication results;
- rolling estimates;
- leave-one-year-out sensitivity;
- influence of extreme months;
- microcap contribution;
- value-weighted versus equal-weighted sensitivity;
- portfolio turnover and effective breadth;
- confidence intervals around the replication gap.

A factor should not be declared replicated solely because one aggregate mean or
t-statistic is close. Sign, time-series agreement, target variant, and sample
alignment must also be considered.

---

## 7. Replication Outcome Taxonomy

Each factor receives a primary outcome and zero or more contributing causes.
The primary outcome must be evidence-based and may remain unresolved.

### 7.1 Replication outcomes

- `replicated_robustly`: paper target is reproduced and remains qualitatively
  stable under reasonable implementation variants.
- `replicated_target_variant`: a clearly identified paper variant is reproduced,
  while another reported variant is not.
- `replicated_only_under_cz_choices`: agreement requires C&Z-supplemented choices
  not supported clearly by the paper.
- `replicated_in_sample_only`: paper sample reproduces but later data does not.
- `direction_only_replication`: sign agrees but magnitude or significance does not.
- `not_replicated`: matched implementation and data still fail the declared
  criterion.
- `underidentified`: the paper omits choices with material empirical impact.
- `unresolved`: evidence or harmonized data is insufficient for diagnosis.

### 7.2 Contributing-cause labels

- `paper_ambiguity`;
- `paper_internal_conflict`;
- `target_variant_mismatch`;
- `extraction_error`;
- `human_resolution_difference`;
- `signal_formula_difference`;
- `signal_timing_difference`;
- `signal_coverage_difference`;
- `portfolio_universe_difference`;
- `breakpoint_difference`;
- `weighting_difference`;
- `holding_rebalance_difference`;
- `delisting_return_difference`;
- `data_vintage_difference`;
- `linking_difference`;
- `sample_period_difference`;
- `post_publication_decay`;
- `microcap_dependence`;
- `outlier_month_dependence`;
- `statistical_fragility`;
- `reference_data_unavailable`.

These labels are diagnostic findings, not automatic instructions to modify the
MethodSpec.

---

## 8. Decision Rules

Thresholds should be calibrated on pilot factors and versioned. The first
implementation should report continuous metrics alongside provisional labels,
not hide evidence behind a binary flag.

A provisional paper-result match may require all of the following:

1. identical target definition, direction, units, and sample window;
2. matching sign;
3. mean spread difference within a predeclared absolute or relative tolerance;
4. no material contradiction in return-series behavior;
5. sufficient common months and portfolio coverage.

A t-stat tolerance alone is inappropriate because t-statistics change with
sample length, missing months, and serial-correlation treatment.

Suggested signal diagnostics for pilot calibration, not universal pass/fail
rules:

- Spearman rank correlation;
- extreme-decile membership overlap;
- common-observation coverage;
- disagreement concentrated around availability dates.

Suggested return diagnostics:

- common-month return correlation;
- mean and volatility differences;
- sign agreement;
- cumulative-return divergence;
- matched-sample t-stat difference.

Every threshold set should have a version, for example
`replication_criteria_v1`, and be stored in the report.

---

## 9. Required Artifacts and Data Model

### 9.1 Reference manifest

Each factor needs an explicit manifest connecting paper and C&Z identities:

```yaml
factor_id: cooper_gulen_schill_2008_asset_growth
paper_ref: Cooper, Gulen, and Schill (2008)
cz_acronym: AssetGrowth
cz_predictor_path: data/CZ code/Signals/pyCode/Predictors/AssetGrowth.py
cz_legacy_path: data/CZ code/Signals/LegacyStataCode/Predictors/AssetGrowth.do
cz_portfolio_profile_source: data/CZ code/SignalDoc.csv
paper_target_id: value_weighted_year1_raw_monthly_low_minus_high
cz_baseline_target_id: equal_weighted_year1_raw_monthly_low_minus_high
```

The manifest must distinguish a paper factor from a reported-result variant.

### 9.2 Run artifact layout

Track-specific paths are required to prevent later runs overwriting earlier
ones:

```text
runs/evidence/<factor_id>/<run_id>/
  metadata.json
  methodspec.json
  plugin.py
  backtest.py
  config.json
  signal.parquet
  breakpoints.parquet
  assignments.parquet
  portfolio_returns.parquet
  long_short_returns.csv
  diagnostics.json
  logs.txt
```

The current factor-level script/result filenames are insufficient for
multi-track diagnosis because later tracks can overwrite earlier artifacts.

### 9.3 Diagnostic report model

A first-class report should include:

```yaml
report_id: ...
factor_id: ...
criteria_version: replication_criteria_v1
paper_target: ...
cz_target: ...
agent_run_id: ...
cz_reference_version: ...
methodspec_comparison: ...
signal_comparison: ...
portfolio_comparison: ...
data_comparison: ...
statistical_comparison: ...
primary_outcome: unresolved
contributing_causes: []
identification_levels: {}
limitations: []
```

The report must be persisted and returned by the pipeline. It must never be a
transient method call whose result is discarded.

---

## 10. Revised Pipeline Roles

The seven existing steps remain useful, but Steps 6 and 7 need revised roles.

### Steps 1-5: independent replication

1. Extract paper-only MethodSpec.
2. Review and resolve ambiguities without target C&Z answers.
3. Generate and freeze formula-only signal code.
4. Validate technical safety and execution.
5. Execute the paper-method run and persist complete artifacts.

### Step 6: diagnostic experiment controller

Step 6 should orchestrate named experiments rather than assume that
`original_method` and `standardized_hxz` are the two scientific endpoints.

Recommended experiment families:

- `agent_paper_method`;
- `cz_signal_our_engine`;
- `agent_signal_cz_profile`;
- `cz_reference` as an imported external run;
- `bridge_<switch>_from_agent`;
- `bridge_<switch>_from_cz`;
- `canonical_v1` robustness run;
- conditional factorial interaction runs.

The same agent plugin remains frozen during portfolio ablations. A C&Z signal
adapter is a separate reference artifact, not an LLM repair of the agent plugin.

### Step 7: replication diagnosis

Step 7 should combine:

- paper-result evidence;
- MethodSpec versus C&Z metadata comparison;
- agent versus C&Z signal comparison;
- portfolio and return comparison;
- data coverage diagnostics;
- bridge-experiment contributions;
- statistical robustness evidence.

It produces a persisted `ReplicationDiagnosisReport`. It remains terminal and
does not automatically tune empirical choices.

---

## 11. C&Z Adapters

Directly executing arbitrary C&Z target code inside the main pipeline would
couple the controlled system to external layouts and weaken audit boundaries.
Use explicit adapters.

### 11.1 C&Z metadata adapter

Responsibilities:

- map `factor_id` to `cz_acronym`;
- parse C&Z portfolio settings and reported C&Z quality labels;
- retain raw values and normalized values;
- identify C&Z defaults versus explicit values;
- never mutate MethodSpec.

### 11.2 C&Z signal adapter

Preferred input is downloaded C&Z firm-level characteristics, because it
captures the complete C&Z preprocessing pipeline. When those outputs are not
available, a controlled adapter may execute or translate a predictor against a
harmonized panel, but the report must note that this is not a full C&Z
reproduction.

Adapter output contract:

```text
[permno, yyyymm, cz_signal]
```

For the verified October 2025 API, request individual characteristics with
`dl_signal("pandas", [acronym], signed=False)`. The default raw form is required
for comparison with the agent's formula-only plugin. `signed=True` multiplies
the characteristic by SignalDoc `Sign`; feeding that into an engine that also
implements the reviewed long/short direction would double-apply direction.

The adapter must enforce unique `[permno, yyyymm]` keys and inner-join to the
common return window. C&Z accounting characteristics may extend beyond the last
available return month because observations are carried through their intended
availability period.

### 11.3 C&Z return adapter

Load C&Z long-short returns and normalize:

```text
[yyyymm, cz_ls_return]
```

The adapter records units, sign convention, sample, portfolio profile, data
release, and source URL/hash.

For `openassetpricing==0.0.2`, `dl_port(profile, "pandas", [acronym])` returns
`[signalname, port, date, ret, signallag, Nlong, Nshort]`. Select `port == "LS"`,
convert `date` to integer `yyyymm`, and divide `ret` by 100 before comparison
with this project's decimal-return contract. The `op` profile is C&Z's
executable original-paper interpretation; SignalDoc `Return`/`T-Stat` are
hand-collected paper benchmarks and must be modeled separately from the return
series downloaded here.

C&Z's R summary computes a simple mean-over-standard-error t-stat, whereas this
project reports a six-lag Newey-West t-stat. The adapter/report must recompute
both estimators on the same aligned monthly series. For AssetGrowth over
1968-2003, the same C&Z series produces 7.656 (simple) and 6.677 (NW(6)); this
estimator effect is not a replication gap.

Published API output does not include firm-level portfolio assignments,
security weights, monthly breakpoints, or the underlying WRDS/CCM vintage.
Those components remain unidentified unless a controlled engine emits them or
the C&Z code is instrumented to persist its intermediate state.

### 11.4 C&Z code is evidence, not trusted runtime

C&Z code should be inspected and hashed. It should not bypass our sandbox or be
allowed to change controlled empirical parameters implicitly. Where the C&Z R
engine is executed for a bridge experiment, run it as an isolated external
reference process with explicit inputs and outputs.

---

## 12. Worked Example: Asset Growth

### 12.1 Paper target

The reviewed fixture identifies the signal as annual total-asset growth and
selects the paper's value-weighted, year-one, raw monthly low-minus-high result:

- mean spread: approximately 1.05% per month;
- t-stat: approximately 5.04;
- sample: 1968-2002;
- annual June formation and 12-month holding period.

The paper reports both EW and VW variants. Therefore "the paper result" is not a
single number.

### 12.2 C&Z target

The local `SignalDoc.csv` row identifies:

- acronym `AssetGrowth`;
- annual total-asset growth;
- sign `-1`;
- baseline EW weighting;
- decile tails;
- 12-month portfolio period;
- June start;
- C&Z t-stat around 8.45;
- a note that VW also works with t-stat around 5.

The baseline C&Z target and the selected MethodSpec target differ in weighting.
That is a target-variant difference, not immediate evidence that either
implementation is wrong.

The October 2025 API makes this distinction observable. AssetGrowth `op`
equals the `deciles_ew` series, while separate `deciles_vw`, quintile, NYSE,
price-screened, and microcap-screened profiles are downloadable. Across the
full 1952-2024 API window, the AssetGrowth LS mean is approximately 0.905% for
`op`/EW deciles and 0.374% for VW deciles. These are C&Z release statistics,
not the paper's 1.73% EW or 1.05% VW table entries.

### 12.3 Signal implementation

C&Z Python computes:

$$
AssetGrowth_{i,t}=\frac{AT_{i,t}-AT_{i,t-12}}{AT_{i,t-12}}.
$$

The agent plugin computes the corresponding annual percentage change using the
reviewed point-in-time inputs. These should first be compared on the same
firm-month panel for rank, coverage, and extreme-decile overlap.

### 12.4 Current result limitation

The current stored run uses a synthetic 24-month fixture. Its mean return is
close to 1% by construction, while its very large t-stat reflects the synthetic
sample and cannot be interpreted as a successful reproduction of the paper's
t-stat. A real-data, matched-period run and persisted firm-month signal are
required before classifying the factor.

### 12.5 Diagnosis sequence

1. Confirm the exact paper target variant.
2. Compare paper, agent, and C&Z field choices.
3. Run agent and C&Z signals on a harmonized panel.
4. Feed both signals separately into our engine using the same configuration.
5. Compare our C&Z-signal return with downloaded C&Z returns.
6. Switch EW/VW and other differing settings through bridge experiments.
7. Match the paper sample before comparing aggregate statistics.
8. Test post-sample and post-publication stability.
9. Assign outcome and contributing-cause labels with identification levels.

---

## 13. Current Repository Gaps

The repository already has paper extraction, MethodSpec review, formula-only
code generation, controlled backtests, run metadata, and basic ablation
orchestration. The following gaps block complete replication diagnosis:

1. No target-specific reference manifest linking MethodSpec, C&Z acronym, code,
   result variant, and downloaded reference data.
2. C&Z firm-level signals and long-short returns are not present locally.
3. `Evaluator.evaluate_signal()` and `evaluate_portfolio()` are unimplemented.
4. Agent signal series are not persisted as run artifacts.
5. Return CSV paths are not attached to RunRecord or copied into EvidenceStore.
6. Multi-track scripts and output CSVs can overwrite each other because paths
   use `factor_id` rather than `run_id`/track/config hash.
7. Snapshot hashes and detailed data coverage diagnostics are incomplete.
8. Step 6 does not run C&Z bridge experiments and ignores
   `factorial_switches`.
9. Step 7 only computes structural t-stat differences and its result is not
   persisted or returned.
10. Replication criteria and cause-classification thresholds are not versioned.

These are not cosmetic gaps. Without firm-level signals, return series, and
track-specific provenance, the system can observe a discrepancy but cannot
reliably identify its cause.

---

## 14. Implementation Plan

### Phase A: preserve complete run evidence

- make script and output paths unique by run/track/config;
- persist return series and attach `return_series_path`;
- persist agent signal series and attach `signal_series_path`;
- persist resolved config, MethodSpec, plugin, script, and snapshot hash;
- add coverage, breakpoint, and assignment diagnostics.

Completion criterion: two tracks cannot overwrite each other, and every metric
can be traced to immutable series and configuration artifacts.

### Phase B: reference manifests and data adapters

- add factor-to-C&Z manifest schema;
- parse SignalDoc into normalized reference profiles;
- download/version C&Z firm-level signals and long-short returns;
- implement signal and return adapters with hashes and unit/sign metadata.

Completion criterion: AssetGrowth reference signal and return series can be
loaded through stable contracts without entering extraction or code generation.

### Phase C: comparison metrics

- implement field-level MethodSpec comparison;
- implement signal-level metrics and disagreement slices;
- implement matched-sample return comparison;
- distinguish target-variant mismatch from implementation mismatch.

Completion criterion: one factor produces a persisted comparison report before
any attribution claim is made.

### Phase D: bridge experiments

- generalize Step 6 from named dual tracks to an experiment matrix;
- run C&Z signal through our engine;
- add two-sided OAT bridge runs for only the settings that differ;
- add conditional factorial analysis for interactions;
- record identification level for every inferred contribution.

Completion criterion: the system can experimentally separate signal and
portfolio effects on at least one real-data factor.

### Phase E: diagnosis and cross-factor study

- implement `ReplicationDiagnosisReport`;
- calibrate and version replication criteria;
- classify pilot factors with human review of unresolved cases;
- aggregate cause frequencies and outcome patterns across factors;
- analyze whether failure causes vary by data family, publication period, or
  C&Z replication-quality label.

Completion criterion: cross-factor conclusions are based on persisted,
versioned evidence rather than manually interpreted console output.

---

## 15. Research Outputs

The final empirical analysis should report more than a replication rate.
Suggested outputs include:

- fraction of papers with material specification ambiguity;
- agent extraction and signal-implementation accuracy;
- agreement between independent agent and C&Z signals;
- distribution of signal, portfolio, data, and statistical gap components;
- share of factors replicated only under supplemented assumptions;
- in-sample versus post-publication decay;
- sensitivity to microcaps, weighting, and breakpoint choices;
- unresolved share caused by unavailable historical data;
- case studies where C&Z and the agent make different defensible choices.

This supports the paper's substantive claim: controlled agents can make factor
replication more auditable, and C&Z can be used as an independent diagnostic
reference to explain why published results do or do not reproduce.

---

## 16. Non-Goals

This design does not:

- treat C&Z as infallible ground truth;
- feed target C&Z answers into the extractor or generator;
- automatically tune parameters until the paper number is matched;
- infer causality from an uncontrolled end-to-end difference;
- declare a factor false merely because one implementation fails;
- modify an approved MethodSpec based on Step 7 results;
- replace human judgment where the paper is genuinely underidentified.

The system's role is to preserve evidence, execute controlled comparisons, and
narrow the set of plausible explanations. Empirical conclusions remain with the
researcher.
