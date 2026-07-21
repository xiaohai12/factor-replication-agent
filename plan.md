# BacktestEngine Generalization Plan

**Status (2026-07-20): all phases complete** (0, 1, 2, 2.5, 3, 4, 5, 6, 7, 8).
See each phase section below for what was delivered, how it was verified, and
honestly-scoped limitations. Final suite: 115 passed / 26 skipped, `ruff
check` clean on every file this plan touched. See `CHANGELOG.md` entries
`[0.13.6]` through `[0.13.14]` for the detailed, dated history.

## Goal
Convert the fixed 9-step, single-sort / extreme-decile / raw-return engine into a
methodology-aware, config-driven engine with a single source of truth, whose
STANDARD (non-LLM) path implements a principled, canonical empirical
asset-pricing methodology set.

## Scope claim (honest bound)
This framework aims to cover the **dominant class of US equity cross-sectional
factor replication workflows**: characteristic-sorted portfolios, long-short
spreads, factor-model alphas, and Fama-MacBeth regressions. It is **not** "almost
all factor backtesting": other asset classes, event studies, complex data
frequencies, and non-standard portfolio construction are **explicit extensions or
deterministic config modules, not unrestricted LLM hooks**.

## Design philosophy
The standard set is **not** reverse-engineered from any particular collection of
factor papers. Assume no papers in hand. Instead, define the standard path from
first principles / established empirical asset-pricing conventions (the choices a
careful researcher would make by default). Papers then map onto this canonical
set via config.

**Deterministic-first, hook-last.** The most dangerous part of a backtest is not
the signal formula but *sample construction, time availability, universe
filters, return alignment, and neutralization*. These must be expressed in a
deterministic config DSL (see `ResearchDesignConfig`, Phase 2.5), **not** default
to LLM hooks. LLM hooks are the last resort for genuinely idiosyncratic
computation only. This preserves the project's core constraint: the LLM never
controls empirical conclusions. (Note: a partial deterministic filter DSL already
exists — `UniverseFilterSpec` + `FilterOp` — but the engine currently forces
`filter_universe` to a hook unconditionally; Phase 2.5 wires the DSL in instead.)

## Decisions
- **Unify** the duplicated engine logic into one importable module; the
  standalone script becomes a thin wrapper that imports it.
- Standard path is a four-layer design (SignalBuilder / deterministic
  ResearchDesign / Estimator / Evaluator). Sample construction, filters,
  timing, delisting, neutralization live in the **deterministic** layer, not in
  LLM hooks.
- Canonical defaults are tiered v1 (initial standard path) vs ext (explicit
  deterministic extensions); see the canonical table. Each default is
  overridable by config.
- Free to restructure now; keep the default path numerically stable so golden
  e2e tests remain the safety net through the early phases.
- Out of scope: transaction costs/turnover, live trading, non-equity asset
  classes.

## Key architecture facts
- Engine logic is duplicated in **two** places that must stay in sync:
  - `src/steps/step5_engine/__init__.py` — in-process `BacktestEngine`.
  - `src/steps/step3_codegen/script_generator.py` `_TEMPLATE` — full inline
    duplicate; this is the **real** execution path (pipeline generates a
    standalone script -> subprocess -> `results/{factor}.csv` +
    `.metrics.json`).
- `BacktestEngine.run()` today is only used for `_detect_hooks()` /
  `_build_config()`.
- Hook contract is split: `STANDARD` + `_detect_hooks` in the engine;
  `HOOK_SIGNATURES` + `_generate_hooks` in `src/steps/step3_codegen/__init__.py`
  (L36, L257).
- Hook naming: `{step}_hook(df, [bp/signal,] config)`, loaded via `exec` in
  `_load_hooks`.
- `RunMetrics` (`src/infra/models/run_record.py` L11) already declares
  `sharpe_ratio`, `alpha_capm`, `alpha_ff3`, `alpha_ff5`, `coverage`,
  `microcap_share` — only `mean_return`/`t_stat`/`n_months` populated
  (`pipeline.py` L292).
- No FF factor returns / rf / daily data loaded anywhere. CRSP monthly +
  Compustat via CCM only.
- Validator: syntax, schema (entry fn exists), future-leak scan; repair =
  syntax/schema only.

## Canonical standard set (defaults, paper-agnostic)
Chosen from common empirical asset-pricing convention, not from any paper.
Each is a config default and can be overridden per run. **Tier** marks what the
initial standard path must handle (v1) vs. explicit deterministic extensions
added later (ext).

| Axis | Tier | Canonical default | Standard overrides |
|---|---|---|---|
| Universe | v1 | Common shares (shrcd 10/11), NYSE/AMEX/NASDAQ (exchcd 1/2/3), ex-financials | keep/other exchanges; price/size screens |
| Universe filter timing | v1 | Filters applied on the formation-date snapshot (point-in-time) | — |
| Return frequency | v1 | Monthly | Daily (ext) |
| Return basis | v1 | Excess of risk-free | Raw |
| Delisting returns | v1 | Apply CRSP delisting return; missing-DLRET convention documented | — |
| Rebalance | v1 | Annual (June) for accounting signals; monthly for price signals | any month; monthly |
| Accounting lag | v1 | 6 months | any lag |
| Formation/holding calendar | v1 | Single formation, non-overlapping hold | J/skip/K overlapping (Phase 5); event-aligned (ext) |
| Sort dimensions | v1 | Single | 2+ independent or dependent (Phase 3) |
| Breakpoints | v1 | NYSE breakpoints, deciles (10) | full-sample; quintiles/terciles/custom N |
| Breakpoint vs holding universe | v1 | Breakpoints from NYSE only; holding universe separate (all-listed) | — |
| Weighting | v1 | Value-weighted | Equal-weighted; capped VW |
| Neutralization | ext | None | Industry-adjusted / residualized / beta-neutral (deterministic module) |
| Portfolio combination | v1 | Extreme-decile long-short spread | avg-leg spread; full portfolios; single |
| Estimator | v1 | Portfolio sort | Fama-MacBeth (Phase 7); factor-model alpha |
| Microcap treatment | v1 | Report microcap_share diagnostic; exclusion is an explicit override (not default) | microcap exclusion |
| Data sources | v1 | CRSP monthly + annual Compustat via CCM | quarterly Compustat, IBES, event dates (ext) |
| Metrics | v1 | Mean, NW t-stat, CAPM/FF3/FF5 alpha, Sharpe, coverage, microcap share | — |

Anything not expressible through the deterministic config/DSL above routes to an
LLM hook — which should become rare after Phase 2.5.

## Target design
Three layers, so adding an event study or regression factor never pollutes the
portfolio-sort pipeline:

1. **SignalBuilder** — computes the signal at each point-in-time-available date
   only (today's `compute_signal` + hooks). No portfolio logic.
2. **ResearchDesign (deterministic)** — universe filters, sample screens, filter
   timing, delisting-return handling, calendar alignment, neutralization,
   microcap treatment. Pure config/DSL, never an LLM decision (Phase 2.5).
3. **Estimator** — portfolio sort / Fama-MacBeth / factor-model alpha / (ext)
   event study. Selected by the registry from `construction_type`.
4. **Evaluator** — raw/excess returns, CAPM/FF3/FF5 alphas, Sharpe, coverage,
   microcap share, replication gap.

Common prep: `load_data -> apply_missing_policy -> filter_universe (DSL) ->
merge_signal`.

Estimator fork (from `construction_type`):
- **portfolio_sort** (default): `sort` (N-dim) -> `compute_returns` (all
  portfolios) -> `combine_returns` (extreme / avg-leg / full / single) ->
  `metrics` (+ factor alphas)
- **fama_macbeth**: cross-sectional regression per period -> `metrics`
- **factor_alpha**: single portfolio -> `metrics`

Structure: `BacktestContext` (data + config + spec + factor returns + hooks) +
ordered step callables + a resolver/registry owning `STANDARD`,
`_detect_hooks`, `_build_config`, `_load_hooks`.

### Modularity approach (contracts over file count)
Modularity means clear boundaries + a uniform contract, **not** many files. Keep
computation as **stateless pure functions** (`(ctx) -> ctx`); use classes only at
polymorphism points (Estimator selection, Registry, config objects). Standard
step and LLM hook implement the **same** `Step` contract so they are
interchangeable via `_dispatch`.

- `Step` = uniform callable (Protocol, not an ABC base class):
  `def __call__(self, ctx: BacktestContext) -> BacktestContext`.
- `BacktestContext` = a `dataclass` carrying all state (config, spec, data,
  factors, portfolios, returns, metrics, trace) so steps stay stateless and
  every number is traceable.
- Registry maps config/spec -> which step implementation to use; hooks override.

### Progressive file split (don't pre-explode)
Start lean, grow files only when a layer gains a **second implementation** or a
file gets too large (~500-700 lines). The full directory tree is an END state
reached by Phase 7, not built up front.
- **Phase 1:** split the current single file into exactly **3 files** by concern
  (stable boundaries already present as sections today):
  - `engine/__init__.py` — `BacktestContext`, `Step` Protocol, `RunConfig`,
    `BacktestEngine.run()` (orchestration)
  - `engine/steps.py` — the 9 standard step pure functions (computation)
  - `engine/registry.py` — `STANDARD` / `_detect_hooks` / `_build_config` /
    `_load_hooks` (selection)
- **Later, only when triggered:** `evaluate/metrics.py` (Phase 2),
  `design/` (Phase 2.5), `estimator/{portfolio_sort,fama_macbeth}.py`
  (when the 2nd estimator lands, Phase 7).

## Phases

### Phase 0 — Unify execution path (behavior-preserving) — ✅ DONE (2026-07-20)
Rewrote `script_generator._TEMPLATE` to emit a thin script that imports
`BacktestEngine` and calls the new `run_with_config()` method, writing CSV +
`metrics.json`. Deleted the inline duplicate step implementations AND the
separate inline CCM-linking duplication (script now reuses
`src.infra.data_layer.CCMLinker`/`TimeAvailComputer`). Added
`BacktestEngine.run_with_config(signal, config, plugin=None, data=None)` as
the single shared lifecycle implementation; `run()` now just builds `config`
and delegates to it (additive, `data=None` preserves prior behavior).
**Found & fixed a real bug along the way:** this repo's editable install only
puts `src/` (not the repo root) on `sys.path`, so the generated script's `from
src...` imports failed when run via subprocess from a non-repo-root cwd —
fixed by passing `PYTHONPATH=<repo_root>` explicitly to the subprocess in
`src/pipeline.py:_run_backtest_via_script()` and `app.py`'s equivalent helper
(see `/memories/repo/paper_loading_flow.md` for details).
**Verified:** `tests/test_*_e2e.py` golden numbers byte-identical (44 passed /
26 skipped, before and after).

### Phase 1 — Step-based refactor (behavior-preserving, depends on 0) — ✅ DONE (2026-07-20)
Split the engine into `engine/__init__.py` (orchestration: `BacktestEngine`,
new `Step` Protocol, new `BacktestContext` dataclass, `run()`/
`run_with_config()`/`_dispatch()`), `engine/steps.py` (the 9 standard step
pure functions, no class state), and `engine/registry.py` (`STANDARD`,
`detect_hooks`, `build_config`, `load_hooks`, leg-resolution helpers).
`BacktestEngine`'s public API is unchanged (`_detect_hooks` classmethod,
`_build_config`/`_load_hooks` instance methods still exist, now as thin
delegations) so every existing call site keeps working unmodified.
**Verify:** full `pytest` green (44 passed / 26 skipped, unchanged), `ruff
check` clean on all three files.

### Phase 2 — Factor data + rich metrics (depends on 1) — ✅ DONE (2026-07-20)
Added `scripts/fetch_ff_factors.py`: fetches monthly FF3/FF5/UMD/rf via
`pandas-datareader` (Ken French Data Library, no WRDS needed — confirmed
network-reachable from this environment) and writes `ff_factors.parquet`.
Fetched **once, at build time**, never at run time; verified by an actual
run against Ken French's site. Added `steps.compute_factor_alphas(ls,
factors, config)`: regresses the combined return series on CAPM/FF3/FF5
using `statsmodels` OLS with Newey-West (HAC) standard errors, producing
`alpha_{capm,ff3,ff5}` + `alpha_{...}_tstat` + per-factor betas — gracefully
returns `{}` when `statsmodels` isn't installed (it's the optional
`research` extra, not core) or when `ls` has no single series to regress
(`full_portfolio_return` shape). **Kept the existing hand-rolled
`newey_west_var` for the primary long-short t-stat unchanged** (statsmodels'
HAC uses different normalization/df conventions) — golden numbers stay
byte-identical. Added `sharpe_ratio` directly to `compute_metrics` (no new
dependency needed for that one). `BacktestEngine.run()`/`run_with_config()`
gained an optional `factors` parameter (mirroring the Phase 0 `data`
parameter) — when given, `compute_factor_alphas` output is merged into the
metrics dict. Wired end-to-end: `script_generator.py`'s generated script now
optionally loads a FF-factors parquet and passes it through;
`pipeline.py:_run_backtest_via_script` looks for `ff_factors.parquet` per-
snapshot first, then falls back to the shared `data/local/ff_factors.parquet`
— alphas are simply omitted when neither exists. `RunMetrics` mapping in
`pipeline.py` now populates `sharpe_ratio`/`alpha_capm`/`alpha_ff3`/`alpha_ff5`.
**Deferred** (honest scope boundary, not attempted here): `coverage` and
`microcap_share` as populated metrics — both need portfolio-level universe-
size context not yet threaded through to the metrics step (the Phase 2.5
`microcap_exclude` filter exists, but the *diagnostic* share isn't computed);
excess-vs-raw return basis is moot for the long-short spread (rf cancels in
a long/short difference) so wasn't implemented, but genuinely matters for
`single_signal_portfolio_return`/`full_portfolio_return` single-leg modes —
left as a known gap for a future pass, not silently assumed correct.
**Verify:** `tests/test_factor_alphas.py` (new, 10 tests) — synthetic
`ls_return = alpha + beta*mktrf` series (zero noise) so OLS recovers the
exact alpha/beta for CAPM/FF3/FF5, plus edge cases (missing rmw/cma, no
factors, too few overlapping months, full_portfolio_return shape) and
`sharpe_ratio` correctness (including a float-precision guard for
near-constant series). Full suite: 101 passed / 26 skipped (was 91/26 — all
new tests, zero regressions). `ruff check` clean. `pyproject.toml`
`research` extra pins updated to the actually-installed/tested versions
(`statsmodels==0.14.6`, `linearmodels==7.0`, superseding the earlier
placeholder pins).

### Phase 2.5 — Deterministic ResearchDesignConfig (depends on 1) — ✅ DONE (2026-07-20)
Wired the existing `UniverseFilterSpec` + `FilterOp` DSL into `filter_universe`
(`steps.apply_universe_filters` + `steps._apply_filter_op`, covering all 14
FilterOp values) and **removed the unconditional `filter_universe -> hook`
rule** from `registry.detect_hooks()` — filter_universe is now standard by
default; a plugin's `filter_universe_hook` still overrides it when present.
Added `steps.apply_delisting_returns` (folds CRSP `dlret` into `ret` via
`(1+ret)*(1+dlret)-1`; no-op when no `dlret` column, documented simplification
for missing-DLRET rows) as a new dispatchable step between `load_data` and
`apply_missing_policy`. Added microcap **exclusion** as an opt-in
`filter_universe` config flag (`microcap_exclude`, NYSE-20th-percentile ME
threshold; off by default — diagnostic-not-exclusion remains the canonical
default, full `microcap_share` diagnostic metric deferred to Phase 2 since it
belongs with the other metrics). Added `steps.neutralize_signal` as a
dispatchable no-op scaffold (`config["neutralization"]`, default `"none"`;
raises `NotImplementedError` prompting a plugin hook for any other value —
wiring an actual MethodSpec field for this is deferred since no such field
exists in the schema yet, and inventing one wasn't in scope for this pass).
Breakpoint-vs-holding-universe separation required no new code:
`compute_breakpoints` already computes breakpoints from the NYSE-only slice
while `assign_portfolios` already assigns/holds the full passed-in universe —
this was already correct, just undocumented; documented it in the module/
class docstrings. Point-in-time filter timing needed no new code either:
filters apply row-wise on the monthly panel, which is already point-in-time
by construction.
**Verify:** `tests/test_research_design.py` (new, 14 tests) covers the DSL/
delisting/neutralization/microcap functions directly; `tests/test_engine_hooks.py`
updated for the new (intentional) hook-detection contract. Full suite: 60
passed / 26 skipped (was 44/26 — all new tests, zero regressions). `ruff
check` clean.

### Phase 3 — Generalized sorting (depends on 1; parallel with 2) — ✅ DONE (2026-07-20)
Added `steps.compute_breakpoints_multi`/`assign_portfolios_multi`/
`compute_returns_multi`/`compute_long_short_multi`: N-dimension-shaped
independent-or-dependent breakpoints (dimension 0 always independent on its
own configured universe; dimension i>0 either independent or conditional on
dimension 0's bucket), dispatched automatically via
`BacktestEngine._dispatch()`'s `_MULTI_DIM_STEPS` name-mangling whenever
`config["sort_dims"]` has 2+ entries. `registry.resolve_sort_dims()` maps a
MethodSpec's `portfolio_return.sorts[]` onto this — **deliberately narrow
v1**: only resolves an exactly-2-dimensional sort where one dimension is
recognized as size-like (`me`) and the other is the paper's own
characteristic (`signal`); anything else (3+ dims, or 2 dims where neither/
both are size-like) still falls back to a hook, honestly bounding the claim
to "the single most common double-sort pattern in the literature" rather
than all possible multi-way sorts. `detect_hooks()` no longer flags
`compute_breakpoints`/`assign_portfolios` when `resolve_sort_dims()` resolves.
`compute_long_short_multi` implements the standard "average the
characteristic spread across control-dimension groups" double-sort
convention.
**Verify:** `tests/test_multi_sort.py` (new, 11 tests) — hand-checkable 2x2
independent-sort panel verifying exact bucket assignment, cell returns, and
the averaged long-short spread; `resolve_sort_dims` mapping tests. Updated
`tests/test_engine_hooks.py`'s sort tests for the new (intentional)
hook-detection contract. Single-sort/no-sort path is provably untouched
(`_MULTI_DIM_STEPS` routing only triggers when `len(sort_dims) > 1`, and
`sort_dims` is `[]` unless `resolve_sort_dims()` succeeds). Full suite: 73
passed / 26 skipped (was 60/26 — all new tests, zero regressions). `ruff
check` clean.

### Phase 4 — Generalized return combination (depends on 3) — ✅ DONE (2026-07-20)
Generalized `steps.compute_long_short` to cover all four
`ReturnCombinationType` values via `config["return_combination_type"]`
(kept the `compute_long_short`/`compute_long_short_hook` name for hook-
contract backward compatibility rather than renaming to `combine_returns` as
originally sketched — a rename is deferred to Phase 8's hook-contract
cleanup pass so existing plugin hook names keep working):
- `extreme_group_spread` (default): unchanged, single top/bottom portfolio.
- `average_leg_spread`: averages `config["long_portfolios"]`/
  `["short_portfolios"]` (explicit portfolio-number lists) — degrades to
  the same single top/bottom pair as extreme_group_spread when not given,
  since free-text leg descriptions ("average of deciles 8-10") aren't
  auto-parsed.
- `single_signal_portfolio_return`: reports one portfolio's return as-is.
  **Real bug fix, not just generalization**: this type was already marked
  STANDARD before Phase 4, but the old implementation always computed a
  spread regardless of `return_combination.type` — any factor using this
  combination through the standard path silently got a wrong (spread
  instead of single-leg) result. Fixed here.
- `full_portfolio_return`: returns the full per-portfolio grid uncombined;
  `compute_metrics` now detects this shape (no `ls_return` column) and
  reports basic coverage diagnostics instead of a mean/t-stat.
Added `AVERAGE_LEG_SPREAD`/`FULL_PORTFOLIO_RETURN` to
`STANDARD["return_combination"]`, so `detect_hooks()` no longer flags them.
**Verify:** `tests/test_return_combination.py` (new, 8 tests) covering all
four modes + the metrics shape-detection; updated
`tests/test_engine_hooks.py`/`tests/test_ball2016_e2e.py` hook-detection
expectations (ball2016's multi-dim sort remains correctly hooked per Phase
3's unchanged, narrow heuristic — only its `average_leg_spread` combination
is now standard, with no runtime effect since its plugin's hand-written
`compute_long_short_hook` still takes priority). Full suite: 82 passed / 26
skipped (was 73/26 — all new tests, zero regressions). `ruff check` clean.

### Phase 5 — Formation/holding calendar (depends on 1) — ✅ DONE (2026-07-20)
Added the overlapping-cohort holding model as standard:
`steps.merge_signal_overlap` (produces one row per (permno, current yyyymm,
`cohort`) instead of collapsing to one row per (permno, yyyymm), so several
formation cohorts can hold the same stock simultaneously — respects
`skip_month` (K) as well as `holding_period_months` (H); the lookback J is
already baked into `compute_signal()`'s own formula, so no new J config was
needed), `compute_breakpoints_overlap`/`assign_portfolios_overlap` (group by
`cohort` instead of `yyyymm`, since a cohort's signal cross-section is fixed
at formation), and `compute_returns_overlap`/`compute_long_short_overlap`
(each still-open cohort gets its own sub-portfolio return each month; the
reported series is the equal-weighted average of every active cohort's
long-short spread that month — the standard Jegadeesh-Titman convention).
Dispatched via `BacktestEngine._dispatch()`'s `_OVERLAP_STEPS` whenever
`config["overlapping"]` is true; **not combined with the multi-dimensional
sort in this v1** (`_dispatch` only takes one alternate path at a time) — that
specific combination still requests a hook, an honest scope boundary rather
than silently picking one behavior. `detect_hooks()` no longer flags
`merge_signal` for `overlapping_portfolios=true` alone.
Event-aligned calendars (PEAD, seasonality, event continuation) remain an
explicit ext, as originally scoped — not attempted here.
**Verify:** `tests/test_overlapping_holding.py` (new, 8 tests) — a hand-built
2-stock/3-cohort scenario with a deliberately SWAPPED cohort (200002's signal
ranking reversed relative to 200001/200003) so months with 2-3 simultaneously
active cohorts genuinely exercise per-cohort breakpoints/assignment and
averaging across *differing* cohort compositions (not just repeated
identical values) — every month's expected `ls_return` is hand-computed in
the test docstring and all matched on first run. Confirmed safe: no existing
e2e test exercises `jegadeesh_titman_1993_momentum` (its fixture plugin
defines no hooks and isn't wired into any golden-number test), and updated
`tests/test_engine_hooks.py`'s overlapping-portfolio tests for the new
(intentional) hook-detection contract. Full suite: 91 passed / 26 skipped
(was 82/26 — all new tests, zero regressions). `ruff check` clean.

### Phase 6 — Frequency / data calendar (depends on 1, 2) — ✅ DONE (2026-07-20)
Added `steps.load_daily_msf(path)`: loads daily CRSP-shaped data (permno,
date, ret, prc, shrout, exchcd, shrcd, siccd) and compounds it into the same
`yyyymm`-keyed monthly panel every other standard step already expects
(`ret` = compounded monthly return, `me` from the last trading day of the
month). **Deliberately scoped v1 (documented explicitly)**: this is "daily
source data, monthly output", not a genuine daily-frequency REBALANCING
engine (breakpoints/holding computed at daily granularity) — that remains an
explicit ext, as originally scoped, since it would need a trading-day
calendar abstraction threaded through every step (`compute_breakpoints`,
`assign_portfolios`, etc.), a much larger change than justified by current
needs. Still a real capability: signals needing daily prices as input (short-
term reversal, realized volatility, illiquidity) can now flow through the
existing monthly-rebalanced engine unchanged. Added
`steps.apply_excess_returns(df, factors, config)`: subtracts `rf` when
`config["return_basis"] == "excess"` (now the canonical default in
`build_config`) and factor data with an `rf` column is supplied — a partial
completion of Phase 2's deferred excess-vs-raw item (matters for
`single_signal_portfolio_return`/`full_portfolio_return` single-leg modes;
still a no-op for the standard long-short spread itself, since `rf` cancels
in `long - short`). Called directly in `run_with_config()` (not via
`_dispatch()`/hooks, since it needs `ctx.factors`, outside the standard
`(df, config)` Step signature) right after `filter_universe`; a no-op for
every existing test (none currently supply `factors`). `return_frequency`
resolved into config from `spec.reported_results.return_horizon` for
documentation/future use — not yet consumed by the standard steps, which
are already frequency-agnostic given a `yyyymm`-keyed panel (the genuine
gap this closes is data *loading*, not per-step logic).
**Verify:** `tests/test_daily_frequency.py` (new, 8 tests) — hand-computed
compounding across multiple trading days/permnos/months, last-trading-day
`me`, and all `apply_excess_returns` branches (excess/raw/no-factors/no-rf-
column). Full suite: 109 passed / 26 skipped (was 101/26 — all new tests,
zero regressions, confirmed by re-running the existing e2e suite). `ruff
check` clean.

### Phase 7 — Fama-MacBeth / regression estimator (depends on 1, 2) — ✅ DONE (2026-07-20)
Added `steps.compute_fama_macbeth(merged, config)`: a genuinely different
**estimator**, not a variant of the portfolio-sort pipeline — regresses
`ret` on `signal` (+ constant) period-by-period via
`linearmodels.panel.FamaMacBeth`, averaging the slope over time with
Fama-MacBeth standard errors. Routed via `config["estimator"] ==
"fama_macbeth"` (set in `build_config()` from `construction_type ==
"regression_weighted"`); `BacktestEngine.run_with_config()` branches to it
entirely right after `merge_signal`, skipping breakpoints/assign/returns/
combine altogether — returns `{fm_intercept, fm_slope, fm_slope_tstat,
fm_n_periods}` and an empty `return_series` (no portfolio-level series for
this estimator). Deterministic-layer winsorization of `signal` via
`config["winsorize_signal_pct"]` (clip at the given/complementary
percentile) rather than a plugin hook, consistent with Phase 2.5's
philosophy. Added `REGRESSION_WEIGHTED` to
`STANDARD["portfolio_construction"]`, so `detect_hooks()` no longer flags
`compute_returns` for it. Raises `RuntimeError` (not a silent `{}`, unlike
`compute_factor_alphas`) if `linearmodels` isn't installed, since
Fama-MacBeth IS the explicitly requested estimator here, not an optional
enrichment. **v1 scope limit (documented)**: single-characteristic FM only
— no cross-sectional control variables beyond `signal` (a multi-regressor
FM is a plausible future extension, not attempted here); not combined with
overlapping-cohort holding (Phase 5) in this pass.
**Verify:** `tests/test_fama_macbeth.py` (new, 5 tests) — synthetic balanced
panel (`ret = intercept + slope*signal`, deterministic cross-sectional
spread, zero/near-zero noise) recovering the exact intercept/slope for
positive, negative, and near-zero true slopes; winsorization changes the
recovered slope when an outlier is injected; missing-data rows are dropped
correctly. Updated `tests/test_engine_hooks.py`'s construction-type test
(now uses `FACTOR_MODEL_ALPHA` as the "still non-standard" exemplar, since
`REGRESSION_WEIGHTED` is standard now). Full suite: 115 passed / 26 skipped
(was 109/26 — all new tests, zero regressions). `ruff check` clean.

### Phase 8 — Prune hooks + docs (depends on 3-7) — ✅ DONE (2026-07-20)
Reviewed `detect_hooks()` holistically after Phases 2.5-7's incremental
pruning: it's already narrow — the only remaining hook triggers are
genuinely non-standard cases (non-standard `breakpoint_source`/`weighting`;
`missing_action` values other than `drop` kept **deliberately** hooked,
since which columns to winsorize is paper-specific and not something the
engine can safely default — verified against the real
`sloan_1996_accruals` fixture, which winsorizes several named accounting
columns, not just returns; overlapping-cohort holding combined with a
multi-dim sort; multi-dim sorts `resolve_sort_dims()` can't map; non-standard
`construction_type`/`return_combination` values like `factor_model_alpha`/
`event_window_return`/`alpha_estimate`/`other`). No further pruning was
warranted without inventing new standard behavior out of this phase's scope.
Added `HOOK_SIGNATURES`/`HOOK_RETURN_DOCS` entries for
`apply_delisting_returns`/`neutralize_signal` (completing the documented
contract to match `registry.load_hooks()`'s full hookable-step list), each
noting what the standard implementation already covers so MetaCoder doesn't
generate an unnecessary hook. Updated `prompts/meta_coder/hook_system.md`'s
config-keys section (`universe_filters` DSL, `skip_month`, and a note that
most factors need zero hooks now). Rewrote `docs/architecture.md` §4.6
(module split, current `STANDARD` sets, the full current `detect_hooks()`
table, the "no longer unconditional" summary for filter_universe/multi-dim
sort/return_combination/overlapping/Fama-MacBeth, and the updated standard
step list including `apply_delisting_returns`/`apply_excess_returns`/
`neutralize_signal`/the Fama-MacBeth branch) plus smaller fixes elsewhere in
the doc that referenced the old "11 fixed steps"/"filter_universe always
hooked" design.
**Verify:** full suite unaffected (115 passed / 26 skipped, no test changes
needed for this phase); `ruff check src/` shows only pre-existing issues in
files untouched by this whole plan (`src/evaluation/`, `src/infra/llm.py`,
`src/infra/trace.py`, `src/steps/step7_attribution/`, `src/steps/step2_reviewer/`) —
confirmed zero new lint issues in every file this plan touched.

## Tooling / libraries (decision)
**Principle:** adopt narrow libraries that do *statistical computation* only; never
adopt a framework that makes *empirical / portfolio-construction* decisions for
us (that would violate the controlled-meta-coder constraint). Test: "does this
library compute a statistic, or does it decide empirics?"

Adopt (pinned, in a `research` optional-dependency group):
- **`linearmodels`** — `FamaMacBeth` + clustered/robust SE (Phase 7). Pure new
  code path, low risk.
- **`statsmodels`** — OLS(+HAC) for NEW factor-alpha regressions (Phase 2).
  Do NOT use it to replace the existing hand-rolled `_newey_west_var` (different
  normalization would break golden numbers).

Build-time only (dev group, never imported at run time):
- **`pandas-datareader`** — fetch Ken French FF/rf factors once in
  `scripts/fetch_ff_factors.py`, snapshot to parquet. No WRDS needed.

Validation oracle:
- **OSAP portfolios** (`data/CZ code/Portfolios/`, via `src/evaluation/`) are the
  primary ground truth — same academic conventions as our target.
- **`alphalens-reloaded`**: NOT adopted. Its conventions (forward returns,
  demeaning, own weighting) differ from ours, so it can't provide exact-number
  validation and risks false mismatches. OSAP is the better oracle.

Rejected frameworks (all make empirical/execution decisions — anti-goal):
- **qlib** — ML/execution-driven, opaque `.bin` data layer; its expression DSL is
  worth studying as inspiration for our deterministic signal DSL, not adopting.
- **zipline / backtrader / vectorbt / bt** — event/order-driven, single-asset
  paradigm; wrong fit for monthly cross-sectional sorts.
- **QuantLib** — derivatives/fixed-income pricing; irrelevant (for trading-day
  calendars prefer the lighter `pandas_market_calendars` if needed in Phase 6).

Reproducibility rule: pin all `research` versions in the lockfile; snapshot any
fetched external data (FF factors) — auditability requires stable numbers.

## Relevant files
- `src/steps/step5_engine/__init__.py` — restructure into context + steps +
  registry
- `src/steps/step3_codegen/script_generator.py` — thin wrapper (Phase 0)
- `src/steps/step3_codegen/__init__.py` — `HOOK_SIGNATURES` L36, `_detect_hooks`
  use L147, `_generate_hooks` L257
- `src/infra/models/run_record.py` — `RunMetrics` (fields already present)
- `src/pipeline.py` — `_run_backtest_via_script` L317, `RunMetrics` map L292
- `src/infra/data_layer/` — FF/rf + daily loaders, snapshots
- `scripts/fetch_ff_factors.py` — NEW: one-time Ken French FF/rf fetch ->
  parquet snapshot (Phase 2)
- `src/infra/models/method_spec.py` — enums exist; may add estimator
  resolver
- `src/evaluation/` — OSAP portfolio comparison (validation oracle)
- `tests/test_engine_hooks.py`, `tests/test_*_e2e.py`, `tests/fixtures/`
- `prompts/meta_coder/hook_system.md`, `docs/architecture.md`,
  `CHANGELOG.md`, `pyproject.toml`

## Suggested sequencing
0 -> 1 -> (2 parallel with 2.5 parallel with 3) -> 4 -> 5 -> 6 -> 7 -> 8

## Open considerations
1. **External data** — FF/rf factors come from Ken French (no WRDS) via
   `scripts/fetch_ff_factors.py`, snapshotted to parquet. Daily CRSP still needs
   WRDS. Recommend small synthetic FF/daily fixtures for hermetic tests.
2. **Estimator fork placement** — inline branch in `run()` vs. separate
   `Estimator` classes selected by the registry. Recommend registry-selected
   classes so the Fama-MacBeth estimator (Phase 7) is purely additive.
3. **Scope discipline** — keep v1 axes lean; resist pulling ext axes
   (neutralization variants, IBES/quarterly Compustat, event studies) into the
   default path. They enter as deterministic modules, never as default hooks.
4. **Library discipline** — statistical libs only (linearmodels/statsmodels);
   no empirical-deciding frameworks (qlib/zipline/backtrader/vectorbt). Pin
   versions; snapshot fetched data.
5. Per `AGENTS.md`, update `CHANGELOG.md` for every phase's code changes.
