# Paper vs. Generated-Code Deviation Log

Running log of places where a paper's stated methodology and the pipeline's generated backtest code
(MethodSpec → `compute_signal` plugin → assembled backtest script → `BacktestExecutor` config)
diverge, for use as replication-methodology notes. One `##` section per paper/target; append new
sections below rather than starting new files.

---

## Paper: Lakonishok, Shleifer, Vishny (1993) — *Contrarian Investment, Extrapolation, and Risk*, NBER WP 4360

**Target**: GS strategy (growth-in-sales weighted-rank decile sort), Table 4.

**Artifacts compared**:
- Paper text: `data/paper_text_cache/Contrarian investment, extrapolation, and risk.pdf.txt`
- MethodSpec (resolved): `runs/method_specs/resolved/4a483a60aae1c941.resolved.json`
- MethodSpec (raw LLM extraction): `runs/method_specs/raw/Contrarian investment, extrapolation, and risk.pdf__MeanRankRevGrowth.raw.json`
- MethodSpec (manual re-derivation, for cross-check): `runs/method_specs/Eval/Contrarian investment, extrapolation, and risk.pdf__MeanRankRevGrowth.manual.raw.json`
- Generated backtest script: `runs/sessions/11c2aab1e8e74ceb93dcfb776d76b4a9/steps/step3/af4163ca09961026c87863ed289d8aa1f6beaad89bb9ad4345701de28e7a5c00.py`
- Executed results: `runs/backtest_scripts/results/4a483a60aae1c941/original_method.{csv,metrics.json}`

### 1. Signal formula (`compute_signal`) — faithful, no material deviation

The paper's rule (Section III, p.12–13): for each of years −1…−5 relative to formation, compute
sales growth, rank cross-sectionally within each year, then take the weighted average of the five
ranks with weights 5, 4, 3, 2, 1 (most recent year weighted heaviest).

The generated code:

```python
weights = [5, 4, 3, 2, 1]
df["signal"] = sum(weight * df[col] for weight, col in zip(weights, rank_columns)) / 15
```

- Weight-to-lag mapping is correct: `lag=0` (most recent release) → weight 5; `lag=4` (oldest) → weight 1.
- Divisor 15 = 5+4+3+2+1, matches `formula.constants` in the MethodSpec.
- Ranking is cross-sectional (`groupby(time_avail_m).rank(pct=True)`), matching "rank all companies
  [...] for that year."
- `df[np.isfinite(df["signal"])]` implicitly enforces the paper's "5 years of past data required"
  rule — firms with an incomplete 5-year sales history get `NaN` in at least one rank column, so
  their weighted signal is `NaN` and gets dropped. This is not encoded as an explicit
  `universe.filters` entry in the MethodSpec (see §3), but the executable behavior is correct.

**One implementation nuance worth noting for methodology writeups**: the paper's "for each year, we
rank all companies" implicitly assumes one shared annual ranking cohort. The code instead groups by
`time_avail_m` — the exact calendar month a firm's accounting data becomes available (fiscal-year-end
+ a lag). Firms with different fiscal year-ends land in different `time_avail_m` buckets, so the
cross-sectional rank is computed within narrower monthly cohorts rather than one pooled annual cohort
per relative year. This is a structural property of the engine's point-in-time data model, not a
paper-specific bug, but it is a genuine (likely second-order) difference from the paper's simpler
"one rank per calendar year" description.

### 2. Delisting-return handling — **real methodological deviation**

**Paper** (Section II, Methodology):
> "If a stock disappears from CRSP during a year, its return is replaced until the end of the year
> with the return on a corresponding size decile portfolio."

**Code**: `CONFIG["apply_delisting_returns"] = True` → `BacktestExecutor.apply_delisting_returns()`
(`src/infra/backtest_engine/__init__.py:376-399`) only folds CRSP's own `dlret` column into `ret` for
the delisting month itself. It does **not** implement "replace the remainder of the year with the
matched size-decile portfolio's return."

- Checked: `MethodSpec` (`src/infra/models/method_spec.py`) has no field capable of expressing this
  rule at all — this is a standardized-engine limitation (the portfolio-construction menu doesn't
  offer a "size-decile replacement" delisting policy), not something lost during extraction/review of
  *this* paper specifically. It would affect any paper in this pipeline that uses the same convention.
- Practical impact is likely small for a NYSE/AMEX, 1968–1989 sample (large/liquid names, low
  delisting frequency vs. e.g. small-cap universes), but it is a genuine, disclosable gap between the
  standardized engine and the paper's stated methodology.

### 3. `missing_action` config field — not actually read from the MethodSpec (currently benign)

**MethodSpec** (`portfolio.missing_policies`, both raw and resolved):
```json
{"stage": "input", "action": "drop"}
```

**Registry mapping** (`src/steps/step3_codegen/registry.py:719-725`):
```python
"missing_action": _track_clamp(
    "missing_action",
    next((mp.action.value for mp in paper.portfolio.missing_policies
          if mp.stage == MissingStage.SIGNAL), None),
    STANDARD["missing_action"], "drop",
)
```

This only looks for a `missing_policies` entry tagged `stage == "signal"`. This MethodSpec's entry
(and the raw LLM extraction's, and the manually re-derived one) is tagged `stage == "input"` instead —
a different enum value (`MissingStage` has `INPUT` / `SIGNAL` / `PORTFOLIO`). The lookup therefore
finds nothing and falls back to the engine default (`"drop"`).

- **This run**: the fallback default (`drop`) happens to coincide with what the paper actually
  requires, so `CONFIG["missing_action"] = "drop"` is correct — but only by coincidence, not because
  the MethodSpec was actually consulted (`defaults_applied` in the generated script confirms this:
  `"MethodSpec field unspecified or off-menu; engine default applied"`).
- **Risk for future papers**: any paper whose signal-input missing-data policy is *not* "drop" (e.g.
  winsorize, carry-forward) and gets tagged `stage="input"` by extraction/review — a natural and
  currently-unflagged labeling choice — would silently get the wrong default with no error raised.

### 4. Accounting-data availability lag — engine default, not paper-stated

**Paper**: only states "we require 5 years of past data before including a company," never a specific
lag (in months) between fiscal-year-end and the April portfolio-formation date.

**MethodSpec**: `timing.data_availability.lag_value = null` (left unspecified, correctly — no value
was invented).

**Code**: `CONFIG["accounting_lag_months"] = 6` — the engine's standard default, applied because the
field was unset (`defaults_applied: [{"config_key": "accounting_lag_months", "value": 6, "reason":
"MethodSpec field unspecified; engine default applied"}]`). 6 months is a conventional
COMPUSTAT-availability assumption (consistent with common practice, e.g. Fama-French), but it is not
a number the paper itself supplies — worth flagging explicitly if reporting exact replication
parameters.

### 5. Reported-results metric construction differs from the paper's own tables

**Paper (Table 4)**: reports, per decile, the *average size-adjusted annual return over the 5
post-formation years* (AAB) for 22 overlapping annual formation cohorts (1968–1989), i.e. an
average-of-cohort-averages statistic on **annual, size-adjusted** returns.

**Generated script's metrics** (`original_method.metrics.json`): a single **monthly** long-short
return series (decile 1 − decile 10) run through `BacktestExecutor`, summarized as mean monthly
return, Newey-West t-stat, and Sharpe ratio — a different return frequency and a different
statistical construction (no explicit size-adjustment step comparable to the paper's size-decile
benchmarking; excess/raw return basis, not benchmark-relative).

- Direction is consistent with the paper (value strategy outperforms glamour), but **the two numbers
  are not on the same scale and should not be directly compared as a "replication check" without
  going through Step7's `ReplicationDiff`/gap-decomposition machinery**, which exists precisely to
  reconcile this kind of construction mismatch.

### 6. Comparison to Chen & Zimmermann (C&Z / "Open Source Asset Pricing") reference implementation

C&Z ship this exact factor under the same acronym, `MeanRankRevGrowth` — found via
`data/CZ code/SignalDoc.csv` (row `Acronym=MeanRankRevGrowth`) and its implementation at
`data/CZ code/Signals/pyCode/Predictors/MeanRankRevGrowth.py`. Comparing our generated
`compute_signal` and pipeline config against C&Z's actual code (not just their SignalDoc summary
row) surfaces several real construction differences:

**a. Input variable: `sale` (ours) vs. `revt` (C&Z's)**

Our MethodSpec followed the paper's literal wording ("growth in sales") and mapped to Compustat
`SALE` (net sales). C&Z's code reads `revt` (Total Revenue) instead — a broader item that "includes
non-operating revenue" (per our own catalog's registered description,
`src/infra/data_layer/sources.py:1343`). `sale` and `revt` are usually close but not identical, and
can diverge meaningfully for firms with material non-operating revenue. This is a real, checkable
input-variable difference, not a rounding nuance.

**b. Growth formula: arithmetic (ours) vs. log-difference (C&Z's)**

- Ours: `growth = current_sale / prior_sale - 1` (simple percentage growth), `NaN` only when
  `prior_sale == 0`.
- C&Z: `temp = log(revt) - log(revt_lag12)`, valid only when **both** `revt` and `revt_lag12` are
  **strictly positive** (`> 0`) — replicating Stata's convention that `log()` of a non-positive number
  is missing.

These are different functional forms (log-growth vs. arithmetic growth) with different missing-data
thresholds (C&Z drops any non-positive revenue observation entirely; we only drop exact-zero
denominators, so a firm with negative sales in the prior year — unusual but possible — would still get
a signal value under our formula but not under C&Z's).

**c. Rank direction/scale: percentile rank ascending (ours) vs. ordinal rank descending (C&Z's)**

- Ours: `rank(pct=True)` — a `(0, 1]` percentile rank, ascending with growth (higher growth → value
  closer to 1).
- C&Z: `gsort time_avail_m -temp` then `cumcount()+1` — an integer ordinal rank where **rank 1 = the
  single highest-growth firm that month**, counting up as growth falls.

Both are monotonic in growth, but on opposite numeric scales (ours: high growth → high number; C&Z's:
high growth → low number). This doesn't necessarily flip the final long/short direction — C&Z's
generic portfolio pipeline applies a separate `Sign` field (`Sign=1.0` for this row in SignalDoc) to
resolve which side is "long" — but it does mean the two `compute_signal` outputs are on different
scales and are not directly comparable number-for-number without accounting for both the rank
direction and C&Z's `Sign` convention.

**d. Lag mechanism: calendar-exact (C&Z's) vs. positional-on-available-releases (ours)**

- Ours: `.shift(lag)` on a **sparse per-release** panel (one row per actual annual filing) — takes
  the *n*-th most recently available release, regardless of exact calendar spacing.
- C&Z: merges on `time_avail_m - DateOffset(months=12*k)` for `k=1..5` — requires a filing to exist
  at *exactly* 12, 24, 36, 48, 60 months before the current one, or that lag term is `NaN`.

For a firm with a perfectly regular annual filing calendar these are equivalent. For a firm with an
irregular fiscal calendar (fiscal-year-end change, a skipped/late filing), C&Z's version drops that
lag term as missing (and, since the weighted sum needs all 5, likely drops the firm from that
formation entirely), while ours would still find "the previous available release" positionally. This
is a real, if likely second-order, difference in how missing/irregular accounting histories are
handled.

**e. Portfolio-level parameters (from `SignalDoc.csv`, applied by C&Z's generic portfolio-formation
pipeline) vs. ours**

| Parameter | Paper (as we read it) | Our code | C&Z (`SignalDoc.csv`) |
|---|---|---|---|
| Formation/start month | April | April (4) | **June (6)** |
| Sort granularity | Deciles | Deciles (10) | **Quintile-like extremes (`LS Quantile=0.2`)** |
| Universe filter | NYSE+AMEX | `exchcd in (1,2)` | `exchcd%in%c(1,2)` — matches |
| Weighting | EW | `ew` — matches | `EW` — matches |
| Rebalance | Annual | 12 months — matches | `Portfolio Period=12` — matches |

The formation-month difference (April vs. June) is the most consequential one: C&Z uses their
standard June-formation convention (common Fama-French-style practice, effectively baking in a
~6-month accounting-availability lag from a December fiscal year-end) rather than the paper's stated
April date. Interestingly, C&Z's implicit ~6-month lag lines up with the *number* our own engine
defaulted to for `accounting_lag_months` (see §4 above) — but we combined that 6-month lag with an
**April** formation month (per the paper), while C&Z combines their own 6-month-equivalent lag with a
**June** formation month. The two pipelines are not applying the same combination, and neither
combination is verified against the other end-to-end here.

**f. Which table C&Z is actually calibrating against**

`SignalDoc.csv`'s `Key Table in OP` for `MeanRankRevGrowth` is **"6 panel 2"**, not Table 4 (the
table our MethodSpec/code targets), with the note *"Lots of supporting results, but not exactly what
we do. Tab 6 panel 2 finds t=4.5 using 3x3 sort with CF and LS corners."* Two things worth noting for
writeups:
- C&Z's citation is the **1994 *Journal of Finance*** published version, while we extracted from the
  **1993 NBER working paper** — table numbering can (and, based on the "CF corners" reference, likely
  does) shift between the WP and the published version. Our WP's Table 5 is the GS×CP (cash-flow)
  bivariate sort and Table 6 is GS×EP — the "CF corners" language in C&Z's note lines up much better
  with our WP's **Table 5**, suggesting the JF-published Table 6 corresponds to our WP's Table 5 (i.e.
  a table got inserted/renumbered by one somewhere in review).
- Regardless of numbering, C&Z's own note admits their code target (the univariate weighted-rank
  signal) isn't a clean match to the bivariate table they cite as evidence — so C&Z's own internal
  documentation has the same "which table is this really validated against" ambiguity we've been
  tracking in our own MethodSpec.

### Summary table

| # | Item | Paper says | Our code does | Severity |
|---|---|---|---|---|
| 1 | Signal formula | Weighted avg. rank, weights 5,4,3,2,1 | Matches exactly | None — faithful |
| 1b | Ranking cohort | One rank per relative year | Ranked within exact availability-month buckets | Minor, structural |
| 2 | Delisting return | Replaced with size-decile portfolio return for rest of year | CRSP `dlret` folded in for delisting month only | Real deviation, engine-wide limitation |
| 3 | `missing_action` plumbing | `stage="input"`, action=`drop` | Not read (stage mismatch); falls back to default `drop` | Benign this run; latent risk for other papers |
| 4 | Accounting lag | Not stated | Engine default, 6 months | Disclosed assumption, not paper-derived |
| 5 | Metric construction | Annual, size-adjusted, per-cohort average | Monthly long-short series, NW t-stat/Sharpe | Different measurement, use Step7 for reconciliation |
| 6a | Input variable (vs. C&Z) | "sales" | `sale` | C&Z uses `revt` (broader revenue measure) instead |
| 6b | Growth formula (vs. C&Z) | not algebraic in paper | arithmetic `%change`, drop only if prior=0 | C&Z uses log-difference, drop if either value ≤0 |
| 6c | Rank scale (vs. C&Z) | "rank" (unspecified scale) | ascending percentile rank | C&Z uses descending ordinal rank |
| 6d | Lag mechanism (vs. C&Z) | not specified | positional (nth available release) | C&Z requires exact 12/24/36/48/60-month calendar spacing |
| 6e | Formation month (vs. C&Z) | April | April | C&Z uses June |
| 6f | Sort granularity (vs. C&Z) | Deciles | Deciles | C&Z uses quintile-like extremes (`LS Quantile=0.2`) |

---

## Paper: Datar, Naik, Radcliffe (1998) — *Liquidity and stock returns: An alternative test*, Journal of Financial Markets 1

**Target**: `ShareVol` — turnover rate (3-month average shares traded / shares outstanding), Table 2.

**Artifacts compared**:
- Paper text: `data/paper_text_cache/Liquidity and stock returns- An alternative test.pdf.txt`
- MethodSpec (resolved, human-corrected): `runs/method_specs/resolved/cc376f708c404f89.resolved.json`
- MethodSpec (raw LLM extraction): `runs/method_specs/raw/Liquidity and stock returns- An alternative test.pdf__ShareVol.raw.json`
- MethodSpec (manual re-derivation from the paper alone, independent of the raw extraction): `runs/method_specs/Eval/Liquidity and stock returns- An alternative test.pdf__ShareVol.manual.raw.json`
- No generated backtest script/executed results found yet for this factor_id under `runs/backtest_scripts/` — this comparison stops at the MethodSpec layer.

### 1. Construction type — **real, disclosed methodological substitution**

**Paper** (Sections 3 and 5): the reported result is not a portfolio at all. It is the GLS-pooled slope
coefficient from 342 monthly Litzenberger–Ramaswamy/Fama–MacBeth-style cross-sectional regressions of
returns on turnover (plus controls). Table 2 reports regression coefficients and t-statistics, never a
sorted long/short portfolio return.

**Resolved MethodSpec**: `portfolio.construction_type` = `"characteristic_sort"`, with a decile sort
(`turnover_rate_quintile`, `group_count=10`) and two legs (long the bottom decile, short the top decile)
that do not appear anywhere in the paper. The review record is explicit about this being a substitution,
not an extraction of paper content:

> "human correction: auto-filled default single sort (quintile, full-sample breakpoints) for signal
> concept 'turnover_rate' -- paper's own portfolio.sorts was empty (e.g. a regression-based method being
> approximated with an equivalent quantile-sort portfolio)"

`return_combination` was correspondingly changed from `"other"` (appropriate for a regression coefficient)
to `"extreme_group_spread"` to match the synthetic decile-sort framing.

- This is the same class of gap as `MissingStage`/menu-limitation issues logged for the Contrarian paper
  (§3 there): the engine's portfolio-construction menu has no first-class representation for "pooled
  cross-sectional regression coefficient," so a decile long-short spread is substituted as the nearest
  backtestable proxy. It is a defensible engineering choice, but the resulting backtest will answer a
  different empirical question (an EW/VW decile-spread return) than the one the paper actually reports
  (a GLS-weighted average monthly regression slope, in %-per-unit-turnover units, not a portfolio return).
- The manual ground-truth file deliberately keeps `sorts`/`legs` empty and `construction_type` =
  `"fama_macbeth"`, `return_combination` = `"other"`, because that is what the paper itself describes —
  it is **not** meant to match the resolved file's engine-capability workaround.

### 2. Missing-data and outlier-trim rules — **dropped between the paper and the resolved spec**

**Paper** (Section 4) states two explicit data-handling rules:
1. "If the number of shares outstanding in a stock changes due to stock splits etc. then we exclude that
   stock for a period of three months."
2. "We therefore discard the lowest 1% and highest 1% observations of turnover from the (complete)
   dataset and re-examine the predicted relationship in the trimmed dataset" (Table 2, Panel B).

**Resolved MethodSpec**: `portfolio.missing_policies = []` and `portfolio.transforms = []` — both rules
are absent. Neither was carried into the resolved/reviewed spec (the review's `findings`/
`all_high_impact_fields` also don't flag either as needing confirmation, i.e. they weren't just deferred,
they were dropped from consideration).

**Manual ground truth**: keeps both — a `drop`-action `missing_policies` entry (`stage="signal"`) for the
split-driven 3-month exclusion, and a `truncate` `transforms` entry (`bounds=[0.01, 0.99]`, `stage=
"after_signal"`) for the 1%/99% trim, explicitly flagged in its own evidence as the Panel B robustness
variant rather than the primary Panel A result.

### 3. `timing.data_availability` — ambiguous, not necessarily wrong either way

**Paper**: turnover for month t uses only shares-traded/shares-outstanding data through month t−1
("the average number of shares traded during the previous three months, i.e., during months t−3, t−2
and t−1").

**Resolved MethodSpec**: `lag_value=0`, `basis="point_in_time"` — reads this as: relative to the
formation date (end of month t−1), the t−3..t−1 inputs are already fully available with zero *further*
lag.

**Manual ground truth**: `lag_value=1`, `basis="fixed_calendar_lag"` — reads this as: turnover used to
explain month-t returns is built from data ending one full month before month t begins, i.e., a 1-month
lag relative to the return-month anchor.

Both are internally consistent depending on which instant is treated as the anchor (end of month t−1 vs.
start of month t); the paper's own text doesn't disambiguate a numeric `lag_value`, so this is flagged as
a genuine interpretive ambiguity rather than a clear extraction error on either side.

### 4. `portfolio.weighting.unsupported_value` — likely misattributed evidence in the resolved spec

**Resolved MethodSpec**: `unsupported_value = "paper mentioned both ew and vw"`.

**Paper**: the only ew/vw mention in the text (footnote 8, Section 4) is about how the **market return**
used to estimate portfolio *betas* was computed ("measured it with respect to value weighted as well as
equally weighted market return") — it is not a statement about any turnover-sorted portfolio's own share
weighting (the paper has no such portfolio; see §1). The `weighting` field's *value* (`"other"`) is still
defensible either way, since no true portfolio-weighting scheme exists in the paper, but the specific
justification text in `unsupported_value` appears to reference the wrong sentence.

### 5. Reported-results coverage — resolved spec keeps a subset, no contradiction

**Resolved MethodSpec**: 2 metrics, both matching the manual ground truth exactly on `estimate`/`statistic`
— `turnover_slope_complete_univariate` (−0.04, t=−8.86) and `turnover_slope_complete_full_controls`
(−0.04, t=−8.58), both Table 2 Panel A.

**Manual ground truth**: same two metrics plus two more (the Panel B trimmed-dataset univariate row,
t=−8.73, and the prose-stated ~27-bps/month implied illiquidity premium from Section 5) — additional
coverage, not a disagreement, and within the `reported_results.metrics` schema cap of 4.

### Summary table

| # | Item | Paper says | Resolved MethodSpec | Manual ground truth (this file) | Severity |
|---|---|---|---|---|---|
| 1 | Construction type | GLS-pooled Fama-MacBeth-style regression coefficient, no portfolio | `characteristic_sort`, synthetic decile long/short (human-labeled approximation) | `fama_macbeth`, empty sorts/legs | Real, disclosed engine-capability substitution |
| 1b | `return_combination` | N/A (regression, not a spread) | `extreme_group_spread` | `other` | Follows from #1 |
| 2 | Split-driven exclusion | Exclude stock 3 months after a shares-outstanding change | Absent (`missing_policies=[]`) | Present (`drop`, `stage=signal`) | Dropped between paper and resolved spec |
| 2b | 1%/99% trim (Panel B) | Explicit robustness variant | Absent (`transforms=[]`) | Present (`truncate`, `bounds=[0.01,0.99]`) | Dropped between paper and resolved spec |
| 3 | Availability lag | t-3..t-1 only, no numeric lag stated | `lag_value=0`, `point_in_time` | `lag_value=1`, `fixed_calendar_lag` | Ambiguous — anchor-dependent, not a clear error |
| 4 | Weighting justification | ew/vw language refers to beta's market-return construction, not portfolio weighting | `unsupported_value` cites "paper mentioned both ew and vw" | `unsupported_value` cites GLS regression weighting instead | Likely misattributed evidence in resolved spec |
| 5 | Reported metrics | Table 2, Panels A & B; Section 5 prose premium | 2 of these (Panel A rows only) | Same 2 + Panel B row + prose premium | Superset, no contradiction |

---

## Paper: *(next paper goes here)*
