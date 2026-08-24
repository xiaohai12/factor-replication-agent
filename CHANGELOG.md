# Changelog

## Unreleased

- Expand the thesis's cited literature with targeted work on LLM research
  assistance, reasoning-and-action agents, tool use, software-engineering
  agents, computational reproducibility, many-analyst variation, the factor
  zoo, and the original Shapley value; also cite the existing FF3/FF5 sources
  where those models first enter the pipeline metrics.
- Restyle the thesis bibliography with abbreviated given names, cleaner
  journal-article punctuation, stronger hanging indents, and visible spacing
  between entries while leaving the reference data unchanged.
- Narrow RQ2 to the evidence actually reported: end-to-end executable-track
  completion and the cross-factor concentration of inferred or unspecified
  MethodSpec fields; remove unsupported claims about the fraction of fields
  resolved without human assistance.
- Redefine the disagreement band as an interval in return outcomes rather than
  a subspace of implementations, and condition its lower-bound interpretation
  on both endpoints being admissible readings of the paper; align the data
  limitations with that condition instead of calling every observed range an
  unconditional lower bound.
- Correct RQ1's track description: the three-term identity closes across
  adjacent accounting endpoints, but only its configuration term compares two
  engine-executed tracks; the external endpoint terms remain observational.
- Clarify the thesis's `agent replication residual` as the reviewed agent
  system's residual distance from the paper endpoint, not a pure LLM-error
  term, while retaining the established decomposition label and numbers.
- Put the HXZ aggregate failure-rate comparison on one common basis throughout
  the thesis: original-study samples, with 65.3\% failing under NYSE--VW and
  43.1\% under All-EW at $|t| \geq 1.96$.
- Align the ShareVol robustness discussion with the in-sample ablation
  statistics: report that all $t$-statistics lie between $0.00$ and $0.24$
  with no sign or significance flip, and interpret the result as consistently
  weak rather than fragile.
- Correct the ShareVol C\&Z external-reference endpoint throughout the thesis
  tables and factor-sample text to $0.91\%$ per month with $t=3.87$, keeping
  the original paper's regression $t=-8.86$ confined to the paper endpoint.
- Synchronize all MeanRankRevGrowth thesis text and tables with the rebuilt
  comparison bundle: the normalized paper endpoint is $0.3833\%$ per month
  with $t=4.5$, the C\&Z configuration is paper-aligned, and the updated
  C\&Z/HXZ three-term identities are reported.
- State the MeanRankRevGrowth conclusion consistently as a successful
  reproduction under the C\&Z configuration across the abstract, results,
  discussion, conclusion, and endpoint table.
- Clarify the MeanRankRevGrowth paper benchmark and distinguish it from the
  external C\&Z/HXZ reference endpoints in the results and summary tables.
- Correct the thesis introduction's AssetGrowth gap interpretation: the
  C\&Z-side gap is configuration-dominated ($+0.61\%$ per month, primarily
  from weighting), not dominated by a purported 67\% agent residual.
- Synchronize the LaTeX title-page author and supervisor fields with the
  already-rendered thesis PDF so recompilation preserves the approved names.
- Fix the thesis template's chapter-page style initialization for the standard
  `book` base class, preventing an undefined `\chapter@p@gestyle` error at
  `\begin{document}`.

### frontend: plot external endpoints in Step 7 mean-return / t-stat scatter (2026-08-24)

- Added distinct paper, C\&Z, and HXZ reference points plus an on-chart legend
  to Step 7's in-sample mean-return-versus-$t$-statistic scatter plot.
- The paper point is intentionally omitted when its reported estimand is not a
  portfolio-return spread, so a regression coefficient cannot be mistaken for
  a directly comparable track return; C\&Z and HXZ remain separately labelled
  external reference endpoints.

### frontend: make the Step 7 three-term identity chart taller and narrower (2026-08-24)

- Capped the chart width and increased its per-term vertical space, improving
  readability of the three-way paper-distance decomposition on wide screens;
  also separated its horizontal-axis title from the bottom legend.
- Added one grouped C\&Z-versus-HXZ Shapley-effect chart, while retaining
  each line's own joint-test and paired-test evidence below it in a responsive
  two-column layout; matched the chart's capped-width, taller proportion to
  the three-term identity chart, used thicker bars for clearer contrasts, and
  gave C\&Z/HXZ explicit blue/red colors rather than a muted track color.
- Merged Step 7's separate C\&Z/HXZ full-factorial gap charts into one
  blue/red grouped chart, while preserving that each color's Shapley effects
  sum within its own controlled comparison line.

## [Unreleased]

### docs: align Results and Discussion with the current controlled evidence (2026-08-24)

- Rewrote Chapters 7--8 around the current three-factor evidence bundles,
  replacing stale six-factor/TODO claims and obsolete assertions about
  unimplemented Shapley attribution.
- Distinguished controlled factorial Shapley attribution, harmonized OAT
  sensitivity evidence, observational external comparisons, and the
  deliberately unidentified ShareVol estimand mismatch.
- Updated the reported AssetGrowth, MeanRankRevGrowth, ShareVol, $t$-channel,
  and post-publication conclusions to the persisted comparison outputs.
- Synced the factor-roster table with Section 5.4's corrected attribution of
  MeanRankRevGrowth's C\&Z result ($0.55\%$/month, $t=3.94$).
- Added a Chapter 7 section on the optional Step 8 diagnosis layer, reporting
  its three validated, evidence-cited proposal artifacts while explicitly
  separating bounded claim selection from independent empirical inference.
- Added Chapter 7 figure placeholders for the AssetGrowth track comparison,
  controlled Shapley attribution, ShareVol OAT boundary, publication-decay
  evidence, and the Step 8 evidence-constrained diagnosis view.
- Expanded Section 7.1 with concrete inferred-versus-unspecified MethodSpec
  audit examples for AssetGrowth, MeanRankRevGrowth, and ShareVol.
- Added a representative Step 1--5 audit-trace figure placeholder to Section
  7.1 and documented the \texttt{BacktestRunner}/\texttt{BacktestExecutor}
  execution boundary and fixed lifecycle in Section 4.
- Replaced the Section 7.1 audit-trace placeholder with
  `latex/Figures/representative-audit-trace.png`.
- Replaced the AssetGrowth Step 6 screenshot placeholder with a results table
  showing the paper, C\&Z, HXZ, and all three frozen-signal endpoints on
  their explicitly labelled reported bases.
- Added analogous endpoint tables for MeanRankRevGrowth and ShareVol,
  preserving their external reported bases and flagging ShareVol's estimator
  mismatch rather than treating it as a comparable portfolio-sort result.
- Added Appendix E tables listing every executed agent track, its changed
  configuration dimensions, and its in-sample long--short return, FF3 alpha,
  and $t$-statistic for all three factors.
- Added a compact cross-factor endpoint table in Chapter 7, while retaining
  factor-specific endpoint tables in the main text and the full executed-track
  matrices in Appendix E.
- Constrained all Chapter 7 endpoint tables and Appendix E's full-track
  matrices to the text width, with reduced table spacing for readable pages.
- Corrected AssetGrowth's approved paper-comparison endpoint to the paper's
  VW raw long--short return ($1.05\%$/month, $t=5.04$, after direction
  reconciliation), retaining its FF3 alpha only as a supplementary result.
  Regenerated the deterministic comparison bundle without rerunning any
  backtests, so paper-anchored identities now use raw long--short returns at
  all four endpoints rather than mixing the paper alpha with return spreads.
- Aligned Step 5's displayed primary paper metric to the reviewed engine
  long--short direction using the MethodSpec's target-sort selectors and
  portfolio legs, while leaving the paper's stored table value unchanged.
- Rewrote Section 7.2.1 from the regenerated AssetGrowth Step 7 and Step 8
  artifacts: it now reports the matched raw-return reproduction, updated HXZ
  $t$-statistic, corrected three-term identities, controlled Shapley effects,
  and the diagnosis layer's evidence-strength distinctions.
- Streamlined the AssetGrowth paper endpoint in Section 7.2.1 and made its
  Shapley attributions explicit: VW-to-EW weighting and the actual C\&Z/HXZ
  universe and breakpoint switches now replace generic stage labels.
- Clarified the inferential boundary of the AssetGrowth Shapley results by
  reporting the C\&Z and HXZ joint-test results, and relabeled external table
  endpoints as persisted references rather than uniformly source-reported
  quantities.
- Rewrote the MeanRankRevGrowth and ShareVol results sections around their
  actual Step 7 evidence: reproduced/inconclusive external comparisons,
  residual-dominated and non-comparable paper boundaries, and the distinct
  factorial versus OAT attribution limits.
- Added a Chapter 7 cross-factor table of the paper-anchored three-term gap
  identities, with explicit observational, controlled-configuration, and
  non-comparable-estimand boundaries; linked it from each of the three
  factor-result subsections.
- Made the MeanRankRevGrowth residual discussion concrete by identifying its
  inferred MethodSpec fields, recorded defaults, unapplied rank transform, and
  the absence of counterfactual tracks that could allocate the residual.
- Clarified that MeanRankRevGrowth's reproduced C\&Z comparison is not a
  paper-reproduction verdict, and added the four-endpoint path behind its
  paper-anchored three-term identities.
- Made ShareVol's OAT boundary explicit by listing its simultaneous
  configuration switches, distinguishing a return-sign flip from any
  significance change, and separating the C\&Z portfolio-sort verdict from
  the paper's incomparable regression estimand.
- Added Chapter 7's cross-factor controlled-design boundary: finite menu and
  factorial limits, non-ground-truth external references, and the distinction
  between auditable contrasts and recovery of original-author code.
- Clarified Chapter 7's $t$-channel and publication analysis as accounting and
  descriptive evidence, respectively, and tightened the ShareVol eligibility
  boundary for the log-$t$ decomposition.
- Recast AssetGrowth's publication split as three separate paper, intervening,
  and post-publication windows rather than an implied continuous decline.
- Rewrote Chapter 7's $t$-channel discussion to explain the observed
  paper-window $t$-statistic changes through their mean-return and volatility
  components, and to distinguish this controlled comparison from the separate
  publication-window diagnostic.
- Corrected Step 7's $t$-channel computation to use the paper-window
  in-sample metrics, matching its controlled endpoint comparisons instead of
  mixing in full-history coverage; added regression coverage for that choice.

### docs: add the controlled track-grid figure (2026-08-24)

- Replaced Section 6.1's placeholder with
  `latex/Figures/controlled-track-grid.png`, clarifying the executable
  baseline/endpoint/attribution tracks versus external comparison references.
- Reconciled the Section 6 factorial threshold with the controller's current
  `MAX_FACTORIAL_SWITCHES = 3`: full factorial is used for three or fewer
  differing configuration fields, otherwise the design falls back to OAT.
- Clarified in Section 6.3 that full factorial is the preferred attribution
  design and that OAT is its computational-budget fallback, which does not
  identify interaction effects.
- Rewrote Section 6.3's decomposition in terms of the implemented
  in-sample-mean-return Shapley attribution: complete factorial grids yield
  exact, order-independent field contributions, while interaction effects
  are allocated across those contributions rather than reported separately.
- Defined $R(\varnothing)$ explicitly as the no-switch, all-baseline
  ($\Cagent$) result.
- Added an intuitive Shapley explanation: average each field's incremental
  return effect across all switching orders, thereby allocating joint effects
  without assigning them to an arbitrary first-switched field.
- Reordered Section 6.3 for readability: it now introduces the attribution
  objective and a two-field, four-track example before presenting the general
  Shapley formula and the OAT fallback.
- Aligned Section 6.4 with the implemented $t$-channel calculation: it
  back-solves volatility from persisted metrics, performs the log
  decomposition only for eligible positive-return comparisons, and otherwise
  reports the absolute-$t$ change as a degenerate case.
- Rewrote Section 6.5 as the implemented evidence/attribution hierarchy:
  controlled factorial Shapley evidence supports high-strength claims, OAT
  supports medium-strength claims with an interaction caveat, and
  observational or unidentified evidence supports only low-strength claims.

### docs: correct the C\&Z attribution for MeanRankRevGrowth (2026-08-23)

- Section 5.4 now attributes the reported $0.55\%$/month long-short return
  ($t=3.94$) for sales-growth reversal (\texttt{MeanRankRevGrowth}) directly
  to C\&Z, rather than describing it as a manual transcription from the
  original paper.

### backend/frontend: surface step5/6's sign-corrected paper_reported + return_type in the UI (2026-08-23)

Step5/Step6's "Paper reported" display never reflected the sign-correction
fix made earlier this session to `_spec_paper_reported`
(`src/steps/step5_backtest_runner/__init__.py`) -- both components
independently re-derive the paper's headline metric straight from the raw
resolved MethodSpec (`reportedPrimaryMetric` in `Step5Output.tsx`,
`extractPaperReported` in `SessionDetailPage.tsx` for Step6), bypassing
`comparison.json`/`_spec_paper_reported` entirely, so they showed the
un-corrected (pre-sign-flip) estimate with no indication of what
`return_type` it was.

- `backend/routers/replication.py`'s `GET /steps/6/track-configs` now also
  forwards `bundle["paper_reported"]` verbatim (already sign-corrected,
  plus `sign_correction`/`return_type`) alongside the existing per-track
  config map, response shape changed from `Record<track, config>` to
  `{tracks: Record<track, config>, paper_reported: {...} | null}`.
- `Step6Output.tsx`: `useTrackConfigs` updated for the new response shape;
  the baseline row's "Reported (reference)" cell now prefers this
  sign-corrected number (falling back to the old uncorrected prop only
  before `comparison.json` exists), and shows the metric's `return_type`
  plus a "sign-corrected" badge (tooltip = the note explaining why) when a
  flip was applied.
- `Step5Output.tsx`: left MethodSpec-only per the user's call (step5 may
  render before `comparison.json` exists, and `reportedPrimaryMetric`
  already correctly resolves `comparison_derivation`-synthesized metrics
  like MeanRankRevGrowth's) -- only added an inline
  `estimand`/`adjustment_model` label next to "Paper reported" (e.g.
  "alpha/ff3"), no sign correction here.
- Verified `npx tsc -b --noEmit` clean for both changed files (one
  pre-existing, unrelated `Step7Output.tsx` type error confirmed present
  on `main` via `git stash` before this change).

### fix: false sign-convention mismatch in paper-vs-track comparison for negative-direction "high-minus-low" factors (2026-08-23)

`build_track_vs_paper` (`src/steps/step7_replication_diff/bundle.py`) was comparing the engine's own
`track_spread` (always `long - short`, per `portfolio.legs`/`signal.direction`) against
`paper_reported["main_spread"]` copied VERBATIM from the paper's own headline estimate
(`_spec_paper_reported`, `src/steps/step5_backtest_runner/__init__.py`) with no sign reconciliation.
For **AssetGrowth** (`fae312b1730eefb6`): the signal's `direction` is `negative`, so
`registry.build_config` correctly sets the engine's long leg to the LOW asset-growth decile
(`portfolio.legs`: `low_asset_growth`/long, `high_asset_growth`/short) and `track_spread = low - high =
+0.005052` -- a genuine, economically sensible positive alpha. But the paper's own headline metric
(`vw_ff3_alpha_high_minus_low`, `estimate=-0.007`) is framed the OPPOSITE way: `high - low`. Same
economic fact, opposite sign convention -- not a real disagreement -- yet every track for this factor
showed `sign_agrees: false` cascading into `magnitude_tier: "failed"`.

Added general (not AssetGrowth-hardcoded) sign reconciliation to `_spec_paper_reported`: three new
helpers (`_target_sort_id`, `_engine_long_short_deciles`, `_paper_high_low_deciles`,
`_sign_multiplier`) determine, from data already on the resolved MethodSpec, whether the paper's own
"high" endpoint (from a single metric's `portfolio_selector` carrying both `{sort_id}_high`/
`{sort_id}_low` keys, OR from `comparison_derivation.high_metric_id`/`low_metric_id`'s own
`portfolio_selector`s) is the SAME decile as the engine's long leg (`portfolio.legs`, side="long") or
the OPPOSITE one. When it's the opposite decile, `main_spread`/`main_t_stat` and every `spreads`/
`t_stats` entry with the same determinable orientation are negated before anything downstream
(`build_track_vs_paper`, `build_three_term_identity`, and the persisted `comparison.json`'s own
`paper_reported` block) reads them -- exactly one place this happens. Left unchanged (no flip) whenever
orientation can't be established from the data: a single-leg decile return, a regression coefficient,
or a multi-leg/no-single-target-sort portfolio -- never guessed. A `paper_reported.sign_correction`
block (`applied`/`flipped_metric_ids`/`orientation_checked_metric_ids`/`note`) records whenever a flip
was applied, auditable in `comparison.json` the same way `cz_reference.json`'s `sign: -1` field already
records C&Z's own convention gap.

For AssetGrowth's `original_method` track: `paper_reported.main_spread` `-0.007` -> `0.007`,
`main_t_stat` `-3.84` -> `3.84`; `derived.tracks.original_method.vs_paper.sign_agrees` `false` -> `true`,
`.magnitude_tier` `"failed"` -> `"clean"`, `.spread_delta` `0.012052` -> `-0.001948`;
`three_term_identity.{cz,hxz}.terms.agent_replication_residual` `0.012052` -> `-0.001948`. Same pattern
across all 7 tracks (`original_method`, `standardized_hxz`, `cz_actual_config`, `factorial_universe`,
`factorial_breakpoint`, `cz_factorial_universe`, `cz_factorial_weighting`): `sign_agrees` flips
`false` -> `true` for all 7; `magnitude_tier` improves from `"failed"` to `"clean"` for 5 of them and to
`"partial"` for the other 2 (`cz_actual_config`, `cz_factorial_weighting`) -- a real magnitude gap
remains there, now correctly measured on matching sign conventions instead of masked by a false one.
MeanRankRevGrowth (`4a483a60aae1c941`) and ShareVol (`cc376f708c404f89`) are confirmed UNAFFECTED:
MeanRankRevGrowth's `comparison_derivation`-materialized "high" endpoint (Table-labelled Value, decile
index 0) is already the engine's long leg, so `_sign_multiplier` resolves to `+1` (no flip,
`main_spread` stays `0.046`); ShareVol's headline is a regression coefficient with no
`portfolio_selector`, so orientation is undetermined (no flip, `main_spread` stays `-0.04`) -- verified
by rebuilding all three factors' `comparison.json` and diffing before/after.

Scanned all ~18 `runs/method_specs/resolved/*.resolved.json` (most for factors not in the current
3-paper roster; several fail to parse under the current schema -- stale artifacts from an older
MethodSpec version, unrelated to this fix and not touched) for the same negative-direction +
high-minus-low-paper-metric combination: of the specs that parse, only AssetGrowth triggers a flip.
No other currently-unused factor was flagged as latently affected.

Regenerated `comparison.json` for all three roster factors via the same direct,
already-verified-safe call to `BacktestRunner.write_comparison_summary(spec, tracks_summary,
snapshot_id, diff_result, batch_info)` over the existing on-disk `tracks`/`batch` data (no backtests
re-executed; only `paper_reported`'s sign correction and everything derived from it changed). Added
four regression tests to `tests/test_step5_comparison_derivation.py`: the AssetGrowth-shaped flip case
(asserting both `_spec_paper_reported`'s sign correction AND the resulting `sign_agrees=True` via
`build_track_vs_paper`), the MeanRankRevGrowth-shaped already-matching-orientation case (no flip), and
two undetermined cases (a regression coefficient; the existing derivation test unchanged). Narrow suite
(`test_step_diagnostics.py`, `test_replication_diagnosis.py`, `test_external_reference_persistence.py`,
`test_step5_comparison_derivation.py`: 210 passed) plus full `pytest tests/` (850 passed, 19 skipped, 2
pre-existing failures in `test_session_api.py` unrelated to this change and reproducible on `main`
without this fix) both pass.

### fix: three like-for-like `agent_replication_residual` gaps in the paper-anchored three-term identity (2026-08-23)

`agent_replication_residual` (`three_term_identity.{cz,hxz}.terms`, `src/steps/step7_replication_diff/bundle.py`)
was silently comparing non-like-for-like quantities for three roster factors:

1. **AssetGrowth** (`fae312b1730eefb6`, session `d0420ee21ae14f98bbebdee9c9cd8f82`): the alpha-matching
   code path (`compute_factor_alphas`, feeding `alpha_ff3`/`alpha_capm`/`alpha_ff5`) was silently
   producing empty alpha fields because `statsmodels` was not installed in `.venv`, despite being a
   pinned dependency in `pyproject.toml` -- installed `statsmodels==0.14.6` now. Regenerated all 7
   `*.metrics.json` under `runs/backtest_scripts/results/fae312b1730eefb6/` and `comparison.json` via
   the session's own `POST /steps/5/execute` (fresh `original_method` run) + `POST /steps/6/experiment`
   (remaining 6 tracks) + `POST /steps/7/comparison`. `three_term_identity.cz.endpoints.agent_baseline_spread`
   is now the alpha-basis `0.005052` (`alpha_ff3`, matching `paper_reported.return_type="alpha"`) instead
   of the old apples-to-oranges raw `mean_return` (`~0.0093`); `agent_replication_residual` is now
   `0.01205` against `paper_reported_spread=-0.007` -- a genuine, comparable magnitude/sign disagreement
   (previously not even the right kind of number).
2. **MeanRankRevGrowth** (`4a483a60aae1c941`, session `11c2aab1e8e74ceb93dcfb776d76b4a9`): the paper's
   two already-extracted decile-leg metrics (`gs_decile_1_aab=0.022` "Value"/long,
   `gs_decile_10_aab=-0.024` "Glamour"/short) were never combined into a spread --
   `reported_results.comparison_derivation` was `null`, so `paper_reported.main_spread` was just the
   single decile-1 leg. Added a `comparison_derivation` (`operation: "high_minus_low"`,
   `high_metric_id="gs_decile_1_aab"`, `low_metric_id="gs_decile_10_aab"`, `use_as_primary_comparison:
   true`) to `runs/method_specs/resolved/4a483a60aae1c941.resolved.json` -- decile 1 (Value) is this
   engine's long leg and decile 10 (Glamour) its short leg per the MethodSpec's own `portfolio.legs`
   sides, and `high - low = 0.022 - (-0.024) = +0.046` matches the sign of both this engine's own
   `agent_baseline_spread` (+0.0048) and C&Z's external reference (+0.0055). `paper_reported.main_spread`
   is now `0.046` (was `0.022`); `agent_replication_residual` is now `-0.0412` against
   `total_gap=-0.0405` (was `-0.0172` against `total_gap=-0.0165`).
3. **ShareVol** (`cc376f708c404f89`, session `fe522cc53fec441c9c79165d5c4a0608`): the paper's headline
   is a Fama-MacBeth regression coefficient (`estimand="coefficient"`, e.g. -0.04, t=-8.86) -- a
   structurally different statistic from a portfolio-sort spread, not fixable by unit conversion.
   `_resolve_track_spread` and `build_three_term_identity` (`src/steps/step7_replication_diff/bundle.py`)
   had no guard for this and silently fell back to `metrics["mean_return"]`, producing a number that
   looked real but wasn't. Added a guard, gated on `paper_reported["return_type"] ==
   Estimand.COEFFICIENT.value`: `_resolve_track_spread` now returns `("unavailable", None)` instead of
   defaulting to `mean_return`, and `build_three_term_identity` now returns the whole identity as
   `available: False` with reason `"paper's own reported result is a regression coefficient, not a
   portfolio-sort spread; agent_baseline_spread is not a comparable quantity"`, following the same
   unavailable-case shape as the existing `build_paper_verdict_agreement`. `three_term_identity.cz` is
   now `available: False` with that reason (previously computed a spurious residual against the raw
   `mean_return`; the stale number was overwritten in place and not preserved for a before/after diff).

Added two regression tests to `tests/test_replication_diagnosis.py` covering the coefficient guard
(`TestTrackVsPaper.test_coefficient_headline_does_not_silently_fall_back_to_mean_return`,
`TestThreeTermIdentity.test_coefficient_headline_is_unavailable_not_silently_computed`); narrow suite
(`test_matched_comparison.py`, `test_config_override_validation.py`, `test_replication_diagnosis.py`,
`test_external_reference_persistence.py`, `test_attribution.py`) passes (232 passed, 1 skipped, then
174 passed after the new tests were added). MeanRankRevGrowth's and ShareVol's `comparison.json` were
each rebuilt with a direct (non-API) call to `BacktestRunner.write_comparison_summary` over the
already-persisted `tracks`/`batch` data plus the freshly-edited spec/code, since neither factor's
underlying track metrics changed -- only `paper_reported`/the new guard did, both of which
`write_comparison_summary` recomputes from its inputs on every call.

### latex: readability pass on intro's 4th paragraph (2026-08-23)

Self-review at the user's request caught three more issues in
`01_introduction.tex`'s "Applying this framework..." paragraph, after the
notational-error fix above: (1) the disagreement-cases sentence was a
90+-word run-on covering both MeanRankRevGrowth and ShareVol plus two
interpretive clauses in one breath -- split into one sentence per factor;
(2) "The same pattern is, if anything, sharper in both disagreement
cases" overstated the parallel -- MeanRankRevGrowth's evidence is a
three-term-identity residual magnitude, ShareVol's is ablation-track
dispersion, two different diagnostics, not the same pattern intensified
-- reworded to "related evidence... though of a different kind in each";
(3) MeanRankRevGrowth's config-side cause (breakpoint-and-weighting,
stated when the factor is introduced) and its residual-side cause (the
missing-return-policy menu clamp, stated later in the same paragraph) sat
side by side with no connecting clause, readable as two competing
explanations rather than two terms of the same decomposition -- added "a
residual effect layered on top of the breakpoint-and-weighting story
already given above for its configuration side" to tie them together.
Also fixed the "makes against HXZ's own protocol" grammar nit to "makes
in this paper's opening example."

### latex: fixed a notational error and de-bloated intro's 4th paragraph, moved the same-engine argument to §3 (2026-08-23)

Self-review (prompted by the user asking me to critique the intro's
4th paragraph for contradictions/bloat) caught a real error: a sentence
I'd added to `01_introduction.tex` claimed "$\Acz$ and $\Ahxz$ are run
through the identical engine... the gap between them isolates the
configuration choice alone" -- but `03_conceptual_framework.tex`'s
three-term identity never defines or uses a $\Acz$-vs-$\Ahxz$ gap; the
actual clean comparisons are $\Acz - \Aref$ and $\Ahxz - \Aref$
individually (each vs.\ the paper-faithful baseline, not vs.\ each
other). Also flagged: stacking that sentence right after the
menu-clamp-contaminates-residual sentence made two different uses of
"the same fixed menu" (baseline-construction clamping vs.
identical-engine-across-configs) read as contradictory without room in an
intro paragraph to disambiguate them, and the paragraph had grown
overloaded (introducing 3 factors + reporting headline numbers + 2 stacked
methodological caveats in one paragraph), diluting the 67%-residual
finding it leads with.

Fix: removed the "trustworthy" sentence from `01_introduction.tex`
entirely (per user: keep intro's mention of the menu limitation, but not
this second methodological defense). Added a corrected version to
`03_conceptual_framework.tex`, right after the paper-anchored identity's
term-by-term explanation, with the right notation ($\Acz - \Aref$ /
$\Ahxz - \Aref$, not $\Acz - \Ahxz$) and an explicit statement of what it
does and doesn't claim: the finite menu still has a real cost (already
covered in `\S\ref{sec:scope}`), but because that menu is applied
identically to $\Aref$, $\Acz$, and $\Ahxz$, the configuration term isolates
the configuration effect cleanly, unlike a direct $\CZ$-vs-$\HXZ$
comparison (which would confound configuration choice with each team's own
separate codebase/infrastructure).

### latex: wrote up the menu-clamp-contaminates-residual finding in §7/§8, and swept the stale 6-factor roster out of §5/§7/§8 (2026-08-23)

User feedback on the intro's residual discussion: the agent's fixed
configuration menu (only a specific, in-menu set of weighting rules,
missing-return policies, etc. is supported; an off-menu paper instruction
is silently clamped to a documented default, per `registry.build_config`)
is likely a real driver of the agent replication residual for some
factors, not just agent reading error -- and this is structurally the same
standardization tradeoff HXZ's own fixed protocol makes, which is worth
stating rather than treating purely as a limitation. Verified this against
the actual `menu_deviations`/`clamped_by_track` data in each factor's
`comparison.json` before writing anything:
- **AssetGrowth** (`fae312b1730eefb6`): `original_method` track has zero
  clamps -- its 67%-of-total-gap residual (already cited in the intro) is
  a clean read of agent imprecision.
- **MeanRankRevGrowth** (`4a483a60aae1c941`): the paper's delisting-return
  policy ("replace with a matched size-decile portfolio's return through
  year-end") is off-menu; `original_method` clamps `missing_action` to
  `drop`.
- **ShareVol** (`cc376f708c404f89`): the paper's weighting ("both EW and
  VW are applied") is off-menu; `original_method` clamps `weighting_rule`
  to `vw`.

Wrote this up in `07_results.tex`'s per-factor deep dives (now three
subsections matching the real roster instead of the old
GP/PS/fgr5yrLag/OScore/FailureProbability set) and as a new bullet in
`08_discussion.tex`'s Limitations list, distinguishing AssetGrowth's clean
residual from MeanRankRevGrowth's/ShareVol's clamp-contaminated ones.

This required a consistency sweep beyond just adding the new point, since
the old per-factor prose no longer matched the 3-factor roster and one
existing claim directly contradicted it:
- `07_results.tex`: replaced all five stale per-factor subsections
  (GP/PS/fgr5yrLag/OScore/FailureProbability) with three accurate ones
  (AssetGrowth/MeanRankRevGrowth/ShareVol), fixed the opening paragraph's
  factor-count description, fixed AssetGrowth's stale "13 tracks" claim to
  the actual 7 (verified `comparison.json.tracks`; ShareVol has 12,
  MeanRankRevGrowth has 11), and removed a dangling `fgr5yrLag` mention in
  the post-publication-decay TODO.
- `08_discussion.tex`: replaced the PS/fgr5yrLag/OScore factor-specific
  limitation bullets with MeanRankRevGrowth/ShareVol ones, and fixed the
  "Estimator restriction" bullet, which previously claimed factor
  selection "excludes papers whose headline result is a cross-sectional
  regression coefficient" -- false as written, since ShareVol's own
  headline result (Datar-Naik-Radcliffe 1998) *is* a Fama-MacBeth
  coefficient and it's in the roster. Reworded to state the real
  constraint (Aref/CZ/HXZ must be portfolio-sort spreads, not necessarily
  the paper's own headline result) and named ShareVol as the deliberate
  exception this makes possible.
- `05_data_and_factors.tex` (`\S\ref{sec:selection}`): the same
  contradiction existed at its source -- "a factor's headline result must
  be a portfolio-sort spread... not a Fama-MacBeth coefficient" was stated
  as non-negotiable. Fixed to clarify the constraint binds $\Aref$/$\CZ$/
  $\HXZ$, not the paper's own result, with ShareVol cited as the
  intentional exception. Also updated `\subsection{The factor sample}`'s
  stale TODO (still listing the 6-candidate set) with real prose naming
  the actual 3 factors, and removed a now-inapplicable "data vintage"
  clause from the selection-criteria paragraph (that was fgr5yrLag's
  story, which is no longer in the roster).

**Still not done** (flagged, not fixed, since out of scope for this pass):
`tab_factor_roster.tex` and the other cross-factor tables/figures
(`tab_autonomy_footprint`, `tab_gap_decomposition`, `tab_sensitivity_band`,
`tab_outcomes`, `tab_baseline_vs_paper`) and `appendix_e_per_factor.tex`
still carry the old 6-factor set and need the same 3-factor pass.

### latex: wrote out intro's Two Research Questions / Measurement Unit Convention / Roadmap subsections (2026-08-23)

These three subsections of `01_introduction.tex` were comment-only
placeholders (bullet outlines of RQ1/RQ2, the agent-system-as-unit-of-
measurement point, and a one-paragraph roadmap) carried over from the
original outline. Wrote them out in prose, consistent with the rest of the
section's notation ($\Aref$, $\CZ$, $\HXZ$, $\Cagent$, $\ImplSpace{P}$) and
cross-referencing the sections they describe (confirmed the actual
`\label`s and `\input` order in `main.tex`: related literature ->
conceptual framework -> pipeline -> data -> experimental design -> results
-> discussion). The "Contributions" subsection already had real content
(C1/C2/C3) and was left untouched.

**Left as-is, still a placeholder:** the comment after Contributions
("Explicit, proactive disclosure... tightening the leakage-proof
boundary... see docs/paper-outline.md Ch.1") is a separate open TODO about
disclosing a leakage-proof-boundary caveat, not one of the three
subsections asked about here -- still needs its own pass.

### latex: swapped intro's opening vignette from Piotroski (untested) to MeanRankRevGrowth (2026-08-23)

User feedback: with only 3 factors actually tested, the introduction
shouldn't spend its opening paragraph motivating the paper with a factor
(Piotroski's F-score) that isn't in the test set at all -- it should open
with one of the 3 factors actually run. `01_introduction.tex`'s opening
paragraph previously used `\citet{Piotroski2000}`'s F-score (HXZ $t$ fails,
C&Z $t=3.29$) purely as an external, general-literature hook. Replaced it
with `MeanRankRevGrowth` (Lakonishok-Shleifer-Vishny 1994's sales-growth
reversal signal, one of the 3 roster factors) -- it has the identical
narrative shape (HXZ's standardized protocol misses significance at
$t=1.08$, C&Z's paper-faithful implementation clears it at $t=3.94$) and is
backed by this paper's own real numbers rather than an outside example.
Trimmed the later "applying this framework" paragraph's MeanRankRevGrowth
clause to avoid repeating the same $t$-stats verbatim now that they're
established in the opening paragraph.

### latex: retitled the thesis to lead with "auditable," rebalanced leakage-proof framing across sections (2026-08-23)

User feedback: the previous title ("...A Controlled, Leakage-Proof LLM
Agent...") over-weighted leakage-proofness, which gets comparatively little
page-space in the paper; the agent's evidence-citation/auditability property
(every extracted MethodSpec field carries a cited quote and source
location, per Step 1) is the more central selling point. Changed
`latex/main.tex`'s `\thesistitle` to "Underdetermination in Factor
Replication: An Auditable LLM Agent as an Independent Second Implementer."

Followed through across the sections that echoed the old headline framing,
without deleting the leakage-proof content itself (it's a real, correct
methodological guarantee -- `SignalDoc.csv` never reaches the Step 1
extractor -- just no longer the lead adjective):
- `01_introduction.tex`: the "controlled LLM agent enters" paragraph now
  leads with "auditable" and spells out the evidence-citation property
  before mentioning non-contamination; C3's contribution bullet now leads
  "controlled, auditable" and folds leakage-proof in as a supporting clause.
- `03_conceptual_framework.tex`: the paragraph that used to open "The same
  discipline defines this paper's leakage-proof boundary" now opens by
  naming auditability as what the MethodSpec-confinement discipline
  produces, then introduces the leakage-proof `SignalDoc.csv` guarantee as
  one specific auditability-supporting guarantee, not the top-level claim.
- `08_discussion.tex`: C2's conclusion sentence changed from "a controlled,
  leakage-proof agent pipeline" to "a controlled, auditable agent pipeline
  -- leakage-proof by construction."
- `07_results.tex` and `appendix_d_validator.tex` left unchanged: both use
  "leakage-proof boundary" as a precise cross-reference to the term now
  defined (as subordinate) in `03_conceptual_framework.tex`, not as
  headline framing, so no edit was needed there.

### latex: rewrote intro headline paragraph for the finalized 3-factor roster (2026-08-23)

`latex/sections/01_introduction.tex` previously referenced a 6-factor roster
and a `[TODO: headline numbers]` placeholder (see 2026-08-19 roster-
reconciliation entry below). The user finalized the test set to 3 papers
(`data/test_papers/test_papers_data_sources.xlsx`, updated by the user
mid-task): share turnover (Datar-Naik-Radcliffe 1998), asset growth
(Cooper-Gulen-Schill 2008), and sales-growth reversal /
`MeanRankRevGrowth` (Lakonishok-Shleifer-Vishny 1994) -- not gross
profitability, which was an earlier, incorrect assumption on my part
(that paper has never been run past session creation -- see the tombstones
under `runs/sessions/_tombstones/`, all 3 GP session attempts died at
revision 0). All three actual roster factors do have a `comparison.json`
under `runs/backtest_scripts/results/`: `cc376f708c404f89` (share
turnover), `fae312b1730eefb6` (asset growth), and `4a483a60aae1c941`,
which I'd initially misread as unrelated Lakonishok-Shleifer-Vishny (1993)
leftover noise -- it is in fact `MeanRankRevGrowth`'s run (the paper was
extracted from the 1993 NBER working-paper version of the same
Lakonishok-Shleifer-Vishny piece; `resolved.factor_id.paper.target_name ==
"MeanRankRevGrowth"`). Updated the "six factors" mentions (opening
headline paragraph, C1, C2) to "three factors" and grounded the headline
paragraph in real numbers from all three `comparison.json` files: asset
growth's agent-replication-residual is 67% of its total gap to the C&Z
reference spread (`three_term_identity.cz`, the one case where HXZ/C&Z
verdicts agree); MeanRankRevGrowth's residual exceeds its total gap in
magnitude, partially offset by an opposing config term
(`three_term_identity.cz`, verdict conflict: HXZ t=1.08 vs. C&Z t=3.94);
share turnover's own signal has a 0.79 t-stat range and 1 sign flip across
its 4 ablation tracks (`robustness_summary`), consistent with its own
HXZ/C&Z verdict conflict. Also added `DatarNaikRadcliffe1998` and
`LakonishokShleiferVishny1994` BibLaTeX entries to `latex/refs.bib`
(`NovyMarx2013`/GP's entry from the prior pass is now unused in the intro
but left in the bib file in case another section still cites it).

**Not yet done:** other LaTeX files (`tab_factor_roster.tex`,
`tab_autonomy_footprint.tex`, `tab_sensitivity_band.tex`,
`tab_outcomes.tex`, `tab_baseline_vs_paper.tex`,
`tab_gap_decomposition.tex`, `appendix_e_per_factor.tex`,
`05_data_and_factors.tex`, `07_results.tex`) still reference GP as a
roster member -- out of scope for this pass (only the intro was
requested) but will need the same GP-to-MeanRankRevGrowth correction
before submission.

### fix: silently-dropped `breakpoint_quantiles` paired-test effect + honest Shapley-coverage caveat + magnitude-tiered reproduction verdict + decay clue on the residual (2026-08-22)

Found while reviewing a real MeanRankRevGrowth batch's vs-C&Z card:

1. **`_CONFIG_KEY_TO_SWITCH_NAME` was missing `breakpoint_quantiles ->
   "quantiles"`** (`step8_diagnosis/summary.py`) even though step6's own
   `_ABLATION_SWITCH_TO_CONFIG_KEY` has carried that switch since
   2026-08-22 earlier today. Every `breakpoint_quantiles` divergence row
   was silently reporting "no paired-test evidence available" instead of
   its real (here, statistically significant, t=2.02) effect -- and, worse,
   this fed directly into the card's headline: `any_individually_
   significant` never found it either, so the headline claimed "none has a
   statistically significant effect" when one actually did. Fixed by adding
   the missing entry.
2. **`shapley_attribution.to_cz`'s exact `shapley_sum_check == total_gap`
   identity only covers the switches step6's vocabulary tracks** (here,
   `quantiles`/`universe`) -- `cz_actual_config` can differ from baseline in
   OTHER real config keys (`formation_lag_months`/`formation_month`) that
   aren't in that vocabulary at all, so their effect is invisibly folded
   into the covered switches' Shapley numbers, not excluded from them.
   Presenting the exact-sum property without saying so reads as "100% of
   the gap explained by these settings", which is false precision. New
   `_shapley_coverage_narrative` (`summary.py`) adds this as its own
   `narrative` sentence (never folded into a row's `effect`, since
   `shapley_effects`'s sign convention, `compute_shapley_effects`:
   flipped-track MINUS baseline, is the OPPOSITE of `paired_tests`'
   `paired_switch_significance`: baseline MINUS track -- confirmed by
   reading both functions directly, not inferred; mixing them into the
   same field un-negated would have silently flipped a sign). Extending
   step6's switch vocabulary to close the coverage gap was considered and
   rejected: it would push this line's tracked-switch count past
   `MAX_FACTORIAL_SWITCHES=3` (lowered from 4 specifically to bound track
   count, see the "尽量少跑" entry below), falling back to OAT and losing
   the Shapley exactness for ALL switches on this line, not just the newly
   added ones -- a structural conflict with the existing track-count
   ceiling, not a one-line fix.
3. **New `bundle.MAGNITUDE_TIER_BANDS`/`_magnitude_tier`/
   `vs_paper.magnitude_tier`** (`bundle.py`): `overall_tag` is sign+
   significance only and blind to magnitude -- the same MeanRankRevGrowth
   batch showed a track tagged "reproduced" whose spread was only 0.22x the
   paper's own. `magnitude_tier` (`"clean"` 0.5x-2.0x / `"partial"` 0.2x-5x
   / `"failed"` outside that or opposite sign) is a new PARALLEL field,
   same non-destructive precedent as Q7's tiered significance alongside the
   existing boolean -- `overall_tag`/`classify_overall` unchanged.
   `build_vs_paper_summary`'s headline now states the tier explicitly next
   to the raw ratio.
4. **`build_vs_paper_summary` now cites `publication_decay.tracks.
   <baseline>`** (already computed for the ROBUSTNESS card, no new
   mechanism) as a narrative clue on the "our own replication distance"
   residual -- whether our baseline's own effect decays post-publication
   speaks to whether the gap from the paper looks like a fragile/decaying
   signal or a persistent bias. Does NOT decompose the residual into
   vintage/engine-bug/paper-ambiguity components (that needs a positive-
   control factor this project doesn't have run yet); stated in the
   discussion that led here as an explicit, accepted scope limit.

New tests: `TestMagnitudeTier` (4 cases), 2 `TestVsPaperSummary` cases (decay
clue present/absent), 3 `TestCzNarrative` cases (quantiles effect no longer
dropped + headline flip, Shapley coverage narrative with an uncovered key,
narrative omitted when no Shapley grid). `runs/backtest_scripts/results/
4a483a60aae1c941/comparison.json` (MeanRankRevGrowth, session
`11c2aab1e8e74ceb93dcfb776d76b4a9`) recomputed in place via `build_evidence_
bundle` (no backtest rerun -- `spec_quality`/`universe_description`/`menu_
deviations` preserved from the prior file since recomputing needs a `spec`
this script didn't have -- see the "Step A"/"Step B" and `external_
performance_comparison` entries below for that earlier work).

### feat: step8 summary cards restructured for readability -- shared caveats stated once, per-item prose reserved for what's actually notable (2026-08-22)

User feedback on a real rendered report (MeanRankRevGrowth): the same
boilerplate explanation was repeated verbatim 2-3 times on a single card
(e.g. the full "C&Z always overrides this regardless of the paper" sentence
on every one of 3 house-convention rows; "contribution share not shown
(the total change is not statistically confirmed)" on every one of 3
insignificant switches; the `three_term_identity` purity-notes paragraph
duplicated across the `to_cz`/`to_hxz` cards). Reading it, also found a
real logic bug: `short_portfolios`/`long_portfolios` (mechanically derived
from `breakpoint_quantiles`, not an independent decision -- `registry.py`:
not even a valid override key) showed up as their OWN "unresolved, warrants
human review" row, duplicating an already-explained `breakpoint_quantiles`
divergence and inventing a spurious open question.

Structural fix, not just prose trimming (`src/infra/models/diagnosis.py`,
`src/steps/step8_diagnosis/summary.py`, `render.py`,
`frontend/src/components/steps/Step8Output.tsx`):

1. **New `SummaryRow` model** (`label`/`ours`/`theirs`/`effect`/`tag`/
   `note`) -- one compact row per item in a homogeneous set (config
   divergences, per-switch effects, weak spec fields). `note` is the ONLY
   per-row prose, reserved for rows that genuinely need it (`unresolved`
   classification, or an individually significant effect); a routine/
   explained/insignificant row leaves it empty.
2. **`DiagnosisSummary`/`VsPaperSummary` restructured**: `details: list[str]`
   replaced by `intro: str` (a shared caveat/classification note stated
   ONCE for the whole card -- e.g. "rows tagged 'C&Z convention' are
   overridden by C&Z the same way for every factor...") + `rows:
   list[SummaryRow]` (the compact table) + `narrative: list[str]`
   (standalone sentences not about any one row -- aggregate facts, "Step A"
   verdicts, cross-line callouts).
3. **`_build_cz_summary`**: one `SummaryRow` per diverging config key,
   `tag` = "C&Z convention"/"paper ambiguous"/"unresolved"; the shared
   reasoning for the first two moves to `intro` (stated once); `unresolved`
   keeps its explanation as that row's own `note` (rare enough to warrant
   it). `_DERIVED_CONFIG_KEYS = {"long_portfolios", "short_portfolios"}`
   excluded from every per-key walk -- the bug fix above.
4. **`_build_sensitivity_summary`**: per-switch rows with `tag` = the
   contribution-share percentage (only when the joint test confirms it);
   the "share not shown, not confirmed" caveat moves to `intro`, stated
   once instead of on every row.
5. **`build_three_term_summaries`**: the three components become rows
   (`tag="largest"` on the biggest one) instead of a paragraph; the
   "largest component"/window-sensitivity sentences move to `narrative`.
6. **`build_spec_quality_summary`**: weak fields sharing the exact same
   `(reason, disposition)` pair are GROUPED into one row listing all their
   labels, instead of repeating the same reason text on 2-3 nearly-
   identical rows.
7. **Frontend**: new `SummaryRows`/`NarrativeList`/`SummaryCardBody`
   components; `SummaryCard`/`ReproductionCard` now share one body renderer
   instead of duplicating the same rendering logic.
8. **`render.py`**: `_render_row`/`_render_summary_body` render `intro`
   once, then the compact row list, then `narrative`, then `footnote`.

`_fold_claim_evidence_into_details` renamed `_fold_claim_evidence_into_
narrative` (operates on the renamed field, same logic). No new claim
types, no LLM involvement change -- this is purely a template-generation
restructuring.

Re-verified against the real `MeanRankRevGrowth` `comparison.json` that
prompted this: "Short portfolios: we use [10], C&Z uses [5]" (the false
"unresolved" duplicate) no longer appears as its own row; only "Number of
portfolio groups" (tagged "C&Z convention") remains.

7 new/rewritten tests in `tests/test_replication_diagnosis.py` covering the
row/intro/narrative split, the grouped spec-quality rows, and a dedicated
regression test for the `long_portfolios`/`short_portfolios` exclusion.
164/164 passing in that file. Frontend `npx tsc --noEmit` + `npx oxlint`
clean.

### fix: `external_performance_comparison`/"Step A" could silently compare an alpha to C&Z's/HXZ's raw spread (2026-08-22)

User caught this immediately after the "Step A"/"Step B" feature below shipped:
paper-extracted headline results aren't always a raw mean return -- some
papers' own headline is a factor-model alpha (FF3/CAPM/FF5), and
`_resolve_track_spread` already substitutes `alpha_ff3`/`alpha_capm`/
`alpha_ff5` for `vs_paper.track_spread` whenever `paper_reported.return_type`
is alpha-based. `external_performance_comparison.agent_tracks[*].mean_return`
was sourced from exactly that field, so for any alpha-headline paper it would
have silently held an alpha value while being compared against C&Z's/HXZ's
own numbers -- confirmed via `CZReferenceProfile.mean_return`'s docstring and
`hxz_bridge`'s recomputation from raw decile-portfolio returns to ALWAYS be
the raw long-short spread, never an alpha. `t_stat` was already safe
(RunMetrics never stores an alpha's own t-stat).

Fix: `derived.tracks.*` gains a genuinely-raw `raw_mean_return`/`raw_t_stat`
pair (`build_evidence_bundle`, always `vs_paper_metrics.get("mean_return"/
"t_stat")`, independent of what `_resolve_track_spread` picked for the
paper comparison). `build_external_performance_comparison`'s `agent_tracks`
now reads these instead of `vs_paper.track_spread`/`track_raw_t_stat`, and
gains an explicit `spread_basis: "raw_mean_return"` field so a reader never
has to guess. No other consumer changed: `_cz_level_and_gap_bullets`/
`gap_decomposition`/`shapley_attribution` etc. compare two AGENT tracks
against each other through the SAME paper-comparison basis on both sides,
so they were never affected by this bug in the first place -- only the
agent-vs-EXTERNAL-reference comparison (`agent_vs_cz`/`agent_vs_hxz`) was.

New regression test (`test_agent_tracks_mean_return_uses_the_raw_spread_
not_the_papers_alpha_basis`, `tests/test_external_reference_persistence.
py`) constructs a fixture where `vs_paper.track_spread` deliberately holds
an alpha value different from `raw_mean_return`, asserting `agent_tracks`
reports the raw one. 4 other existing fixtures in that test file updated to
carry the new `raw_mean_return`/`raw_t_stat` fields (mirroring what
`build_evidence_bundle` now actually produces). Re-verified against real
`MeanRankRevGrowth` numbers -- unchanged (that factor's own headline is
`mean_return`, not alpha, so this bug never fired for it; the fix only
changes behavior for alpha-headline papers). 179/179 passing in the
affected test files.

### feat: "Step A"/"Step B" -- verdict on reimplementing C&Z's/HXZ's own config, and whether C&Z's and HXZ's own numbers agree with each other (2026-08-22)

Discussed with the user (docs/step7-8.md "Step A"/"Step B"): `external_
performance_comparison` (added earlier the same day) laid agent tracks and
C&Z's/HXZ's own self-reported numbers side by side with no verdict; nothing
anywhere compared C&Z's own number against HXZ's own number directly. Two
additions, both pure step7 arithmetic (no LLM involvement), following the
same reuse/rename pattern as everything else in `bundle.py`:

1. **"Step A" -- `external_performance_comparison.agent_vs_cz`/
   `.agent_vs_hxz`** (`bundle._verdict_vs_external_reference`): does running
   C&Z's/HXZ's own config through this engine (`cz_actual_config`/
   `standardized_hxz`) reproduce the number THEY themselves report? Reuses
   `build_track_vs_paper`/`classify_overall` verbatim by packaging the
   external reference as a synthetic `paper_reported`-shaped dict -- same
   sign/ratio/significance math, a different endpoint. Verified against real
   `MeanRankRevGrowth` numbers (`runs/backtest_scripts/results/
   4a483a60aae1c941/comparison.json`, session `11c2aab1e8e74ceb93dcfb776
   d76b4a9`): `agent_vs_cz` = `reproduced` (ratio 0.70x, both significant,
   same sign), `agent_vs_hxz` = `inconclusive` (opposite sign, neither side
   significant).
2. **"Step B" -- new top-level `paper_verdict_agreement`**
   (`bundle.build_paper_verdict_agreement`): a plain sign+significance
   comparison of C&Z's own number against HXZ's own number, independent of
   anything this engine ran -- `agree_significant` / `agree_insignificant` /
   `conflict` / `unavailable`. Same `MeanRankRevGrowth` numbers: `conflict`
   (C&Z significant positive t=3.94, HXZ insignificant and oppositely
   signed t=1.08).
3. **step8 wiring**: new `PaperVerdictAgreement` model
   (`src/infra/models/diagnosis.py`) + `ReplicationDiagnosisReport.
   paper_verdict_agreement`, built by `summary.build_paper_verdict_
   agreement_summary` (same zero-LLM discipline as `build_vs_paper_
   summary`) and wired in `ReplicationDiagnoser.diagnose()`. `_build_cz_
   summary`/`_build_sensitivity_summary` (the latter gated to the `to_hxz`
   line) each gain one new bullet via `_format_reference_verdict`, so
   "Step A" surfaces inside the existing vs_cz/robustness cards rather than
   needing a new section. `render.py::_summary_section` prints the "Step B"
   headline first, ahead of everything else, as a blockquote.
4. **New context-only tools** (`EXTERNAL_PERFORMANCE_COMPARISON_TOOL`/
   `PAPER_VERDICT_AGREEMENT_TOOL`, `step8_diagnosis/__init__.py`): no claim
   type cites either section (deliberately -- both are pure classification,
   following the same trend as `build_vs_paper_summary` away from
   claim-gated content), so the prompt's new "What you receive" paragraph
   explicitly tells the LLM not to attempt a claim citing these keys.
5. **Frontend**: `Step8Output.tsx` gains a `PaperVerdictBanner`, rendered
   ahead of every section card (amber for `conflict`, blue for either
   `agree_*` verdict) -- the "Step A" bullets need no new UI code since they
   flow through the existing per-card `details` string list.

New tests: 4 in `tests/test_external_reference_persistence.py`
(`TestBuildExternalPerformanceComparison`'s `agent_vs_cz`/`agent_vs_hxz`
cases) + 6 in the new `TestBuildPaperVerdictAgreement` class there, plus 6
in `tests/test_replication_diagnosis.py` (2 `TestCzNarrative`, 2
`TestSensitivitySummary`, 4 `TestPaperVerdictAgreementSummary`). Frontend
`npx tsc --noEmit` + `npx oxlint` on the changed file both clean.

### feat: persist step6's cz/hxz preview at click time; new `external_performance_comparison` bundle section (2026-08-22)

Follow-up to the `three_term_identity` discussion above: the user pointed
out `MANUAL_PAPER_RETURN_FALLBACK`'s `MeanRankRevGrowth` entry is itself
sourced from the ORIGINAL PAPER's text (not an independent C&Z measurement
-- `data/CZ code/SignalDoc.csv`'s own Notes column says as much), which
means `three_term_identity`'s `X - P` identity is comparing two numbers
from the same paper for that factor, not "paper vs an independent
implementer". Rather than gate `three_term_identity` on an
independent/paper-derived distinction (rejected by the user -- "cz和hxz的
外部数据都在step6时候已经得到，你就当可信的"), added a second, simpler
mechanism that sidesteps `paper_reported` (and its sometimes-wrong-shape/
missing-t-stat problem) entirely:

1. **Persist step6's preview at click time, not at run-experiments time**
   (user: "点击preview后" not "跑实验的时候"). `GET /{session}/steps/6/
   cz-config` and `/hxz-config` (`backend/routers/replication.py`) now take
   an optional `factor_id` query param (`spec.paper.factor_id`, the
   resolved-spec hash `results_dir` is keyed by -- NOT the session's own
   human-readable `factor_id`, a distinct value); when present, the
   endpoint's own response is written via `_persist_reference_preview` to
   `results_dir/cz_reference.json` / `hxz_reference.json` (same directory
   as `comparison.json`) as a side effect, before any track ever runs.
   Frontend: `Step6CzConfigPreview`/`Step6HxzConfigPreview`
   (`frontend/src/pages/SessionDetailPage.tsx`) now extract `spec.paper.
   factor_id` and pass it along; `Step6HxzConfigPreview` gained a new
   `specFactorId` prop for this (it previously had no `spec` access at
   all, only the session's own `sessionFactorId`).
2. **step7 reads the persisted files instead of re-querying**:
   `src/infra/reference/__init__.py`'s new `external_references_for_
   results_dir(results_dir, acronym, ...)` prefers `_load_persisted_cz_
   reference`/`_load_persisted_hxz_reference` (parses the persisted JSON
   back into the same shape `external_reference_endpoints` already
   produces) and falls back to a fresh `external_reference_endpoints`
   query per-endpoint (cz/hxz resolved independently) only when the
   corresponding file is missing -- old sessions/batches that never
   previewed keep working unchanged. `step5_backtest_runner.write_
   comparison_summary` now calls this instead of `external_reference_
   endpoints` directly.
3. **New `external_performance_comparison` bundle section**
   (`build_external_performance_comparison`, `src/steps/step7_replication_
   diff/bundle.py`): every agent track's own `mean_return`/`t_stat`
   (already computed) laid directly alongside C&Z's/HXZ's own reported
   numbers -- no `X - P` subtraction, no identity, no requirement that
   every field be present. Exists specifically because `paper_reported` is
   sometimes the wrong statistic or missing a t-stat entirely (the
   complaint that started this), so a mechanism that never routes through
   it was needed alongside (not instead of) `three_term_identity`, which
   is left unchanged and still useful when `paper_reported` is complete.
4. **Frontend**: `ForestPlot` (`frontend/src/components/AttributionPanel.
   tsx`) gained an optional `externalPerformance` prop -- C&Z's/HXZ's own
   t-stat now plot as extra rows on the same chart as the agent's tracks
   (distinct fill color, "external reference" tooltip note), sorted into
   the same `|t|`-descending order rather than a separate table. Wired in
   `Step7Output.tsx` from `bundle.external_performance_comparison`.

Backfilled `runs/backtest_scripts/results/4a483a60aae1c941/{cz,hxz}_
reference.json` for session `11c2aab1e8e74ceb93dcfb776d76b4a9`
(`MeanRankRevGrowth`) by calling the same functions the preview endpoints
call, since that session's multi-track batch had already run before this
persistence mechanism existed (re-running it was out of scope -- the user
explicitly didn't want to re-run). Recomputed `comparison.json`'s `three_
term_identity`/`external_performance_comparison`/`evidence_keys` in place
from those files, no backtest rerun.

New tests: `tests/test_external_reference_persistence.py` (7 cases --
persisted-preferred, live-fallback per-endpoint independence, missing
`results_dir`, `build_external_performance_comparison` shape).

### fix: `three_term_identity`'s C&Z endpoint no longer silently unavailable when `SignalDoc.csv` isn't downloaded (2026-08-22)

Found while discussing session `11c2aab1e8e74ceb93dcfb776d76b4a9`
(`MeanRankRevGrowth`, docs/step7-8.md Part VII example 7): `comparison.json`
had `three_term_identity.cz.available=false` ("missing: external cz
reference spread") even though `src/infra/reference/__init__.py`'s
`MANUAL_PAPER_RETURN_FALLBACK` has held `MeanRankRevGrowth`'s number
(mean_return=0.0055, t_stat=3.94, from the paper's own text) since before
this session ran.

Root cause: `load_cz_reference_profile` read `SignalDoc.csv` from a
hardcoded default path (`data/osap/SignalDoc.csv`, populated by
`scripts/download_osap.py`) that isn't present in this checkout -- a
`FileNotFoundError` returned `None` immediately, never reaching
`_apply_manual_return_fallback`, which only fires once a row has already
been found. A real copy of the same file exists at `data/CZ code/
SignalDoc.csv`, but the loader never looked there and wasn't passed that
path either.

Fix (per user: don't wire up the CSV path, the fallback dict is already the
source of truth for these acronyms): `load_cz_reference_profile` now treats
"file missing" and "acronym not in the file" the same way -- both fall
through to a new `_manual_fallback_profile(acronym)` that builds a
`CZReferenceProfile` from `MANUAL_PAPER_RETURN_FALLBACK` alone (only
`mean_return`/`t_stat` populated; every other field, e.g. weighting/
breakpoint/sample window, needs a real CSV row and stays `None`).
`external_reference_endpoints`'s `source` string now says
`"MANUAL_PAPER_RETURN_FALLBACK (hand-filled..."` instead of always claiming
`SignalDoc.csv`, so provenance stays honest either way. `runs/
backtest_scripts/results/4a483a60aae1c941/comparison.json` was recomputed
in place (`three_term_identity` + `evidence_keys` only, via
`build_three_term_identities`/`flatten` -- no backtest rerun needed, the
per-track `.metrics.json`/`.csv` were already on disk) to reflect the fix.

### frontend: `ThreeTermIdentityPanel` redesign -- general reading guidance, cross-line verdict, grouped bar chart (2026-08-22)

Same discussion flagged the old table-only rendering as hard to read and
lacking any general guidance on how to interpret the three terms. Redesign,
still deterministic (no LLM, no per-factor hardcoding):

- Fixed "how to read this" paragraph explaining what each term is and,
  specifically, that `agent_replication_residual` caps how much the other
  two terms can be read as saying about the paper -- prefer investigating
  the baseline replication itself over a config/signal story when it's the
  largest term.
- `crossLineVerdict()`: one sentence derived purely from each line's
  `largest_term` -- names it for a single available line, states agreement
  for two lines sharing the same largest term (with a canned interpretation
  for each of the three terms), or says the lines disagree and points back
  to the per-line tables. Works for any factor/number of available lines,
  asserts nothing beyond what `largest_term` already encodes.
- New grouped horizontal diverging bar chart (recharts, same conventions as
  `AttributionPanel.tsx`'s other charts): one row per term, cz/hxz as two
  bars per row, so the two lines are compared directly instead of needing
  to flip between two separate per-line tables.
- Per-line detail kept (table + window-basis footer + residual check) but
  now in a responsive 2-column grid instead of stacked full-width cards, and
  the `largest_term` row gets a small "largest" badge instead of just bold
  text.

### feat: catch `reported_returns`/`formation` extraction mismatches, human-editable in step2 UI (2026-08-22)

Found while auditing `MeanRankRevGrowth` (Lakonishok/Shleifer/Vishny 1994):
step1 had extracted `sample.reported_returns` as byte-identical to
`sample.formation` (1968-1989, copied from a Table 4 caption describing only
FORMATION periods), when the paper's 12-month holding period means the last
formation's returns actually extend through April 1990 -- confirmed by the
paper's own separate data-coverage statement and by C&Z's independently-
reported `SampleEndYear=1990`.

Four changes, all discussed with the user before implementing:

1. **`prompts/extractor/method_spec_extractor.md` §1.9**: added a concrete
   worked example of this exact trap (table caption states formation periods
   only; don't copy that range into `reported_returns` unchanged for a
   holding period >= 12 months -- derive `formation.end_year +
   ceil(holding_period_months/12)` or mark the field `table_only`/`inferred`
   if genuinely uncertain).
2. **Deterministic step2 check** (`src/steps/step2_reviewer/review.py`):
   `_reported_returns_holding_period_mismatch_finding` -- fires a
   `NEEDS_HUMAN_CONFIRMATION` Finding when `formation` and `reported_returns`
   are byte-identical (both start AND end year) despite a >=12-month holding
   period. Deterministic, not LLM-based (this project's empirical numbers
   stay deterministic, see AGENTS.md) -- catches the mismatch regardless of
   whether step1's prompt guidance actually worked on a given paper. Only
   fires on genuinely identical windows, so strategies where the two windows
   legitimately coincide (e.g. rolling monthly rebalance, holding < 12
   months) aren't false-positived.
3. **`sample.reported_returns.start_year`/`end_year` now human-editable**:
   added `_reported_returns_year_findings` (always-shown entries, since
   `Period` isn't a `SourcedValue` and wasn't covered by the existing
   `high_impact_sourced_values` machinery) and `_PATCHABLE_PERIOD_YEAR_FIELDS`
   in `apply_value_patches` (a second small fixed field registry, same
   "never attacker-chosen attribute" posture as the existing one). No new
   frontend code needed for the edit UI itself -- `SessionDetailPage.tsx`'s
   existing generic finding-editor loop already renders a free-text input
   for any `field_path` outside its couple of structured-object exclusions;
   only had to add `sample.reported_returns` (the bare mismatch-finding
   pointer, not a directly patchable field) to that exclusion list so it
   doesn't render its own (would-422) edit box next to the two real
   patchable rows.
4. **`prompts/review_gate/llm_review.md`**: added the same worked example
   to the "cross-field consistency" section's `sample.*` sentence -- the
   step2 LLM review loop has full-trust write access to the spec it returns
   (unlike the deterministic checker, it can actually FIX the value, not
   just flag it), so it benefits from the same concrete rule, not just the
   pre-existing vague "do the three sample periods make sense together?"
   prompt.

Tests: `tests/test_step2_reviewer.py::TestReportedReturnsHoldingPeriodMismatch`,
`tests/test_apply_human_value_patches.py::TestReportedReturnsYearPatches`.
Fixed two now-stale test fixtures (`test_step2_reviewer.py::_base_spec`,
`test_step2_reviewer_llm.py::_minimal_raw_spec`) whose `formation`/
`reported_returns` were identical under a 12-month hold, which the new
check now (correctly) flags -- both changed to a realistic non-identical
pair instead of suppressing the check.

### feat: `breakpoint_quantiles` added as a tracked step6 switch (2026-08-22)

`src/steps/step6_dual_track_controller/__init__.py`'s
`_ABLATION_SWITCH_TO_CONFIG_KEY` gained a 6th entry: `"quantiles":
"breakpoint_quantiles"`. Previously the number of groups the extreme
portfolios are cut into (deciles vs quintiles, ...) was never tracked as its
own switch -- a `cz_config_override`/`HXZ_STANDARD_CONFIG` quantile-count
difference silently rode along inside whatever endpoint track carried it
(`cz_actual_config`/`standardized_hxz`) with no dedicated
`ablation_quantiles`/`factorial_quantiles` track, so step7's attribution
could never isolate how much of a replication gap the group-count choice
alone explains. Decided this materially moves extreme-leg composition
(same order of magnitude as `breakpoint_source`/`weighting_rule`, which are
already tracked), not a minor detail worth leaving out.

Only safe to add now that `_remap_extreme_portfolios_for_quantile_override`
(this same day's `breakpoint_quantiles` fix, see above) makes a single-switch
`breakpoint_quantiles` flip resolve `long_portfolios`/`short_portfolios`/
`sort_dims` correctly -- before that fix, `ablation_quantiles`/
`factorial_quantiles` would have hit the exact same empty-result failure
`cz_actual_config` did.

No API/schema change -- `_diff_switches`/`_factorial_track_specs`/
`_get_ablation_override` are all switch-name-generic, so this is a pure data
addition. Trade-off: a factor whose ①→② or ①→③ comparison now differs on
`breakpoint_quantiles` in addition to other switches has one more switch in
play, making the 3-switch `MAX_FACTORIAL_SWITCHES` OAT-fallback ceiling
easier to hit (more tracks total, but each individual batch stays bounded).
Verified end to end on this session's real factor (`MeanRankRevGrowth`):
`cz_actual_config`'s auto-attribution now correctly produces 2 tracks
(`cz_factorial_quantiles`, `cz_factorial_universe`) instead of 0, since
`quantiles` and `universe` both differ between ① and ②. New tests:
`tests/test_experiment_plan_matrix_merge.py::TestQuantilesSwitch`.

### feat: `cz_actual_config` now applies SignalDoc's per-predictor `Filter` (2026-08-22)

Closes the `docs/step6.md` §10 gap: `cz_profile_to_config_override`
(`src/infra/reference/__init__.py`) previously only set the GLOBAL C&Z
universe backbone (`shrcd∈{10,11,12}`, `exchcd∈{1,2,3}`, from
`SignalMasterTable.py`), never SignalDoc's `Filter` column -- a per-predictor
extra restriction layered on top (e.g. `MeanRankRevGrowth`'s
`exchcd%in%c(1,2)`, excluding NASDAQ). Found while auditing this session's
`cz_actual_config` result against the real C&Z R source
(`data/CZ code/Portfolios/Code/01_PortfolioFunction.R`) for correctness.

Added `CZReferenceProfile.filter_expr` (parsed from SignalDoc's `Filter`),
`CzFilterParseError`, and `_parse_cz_filter_expr` -- translates the R idioms
actually observed in `SignalDoc.csv`: `field%in%c(...)`, `==`/`!=`/`<=`/
`>=`/`<`/`>` comparisons, and `abs(field)>N` (exact translation to
`not_between`, since `abs(x)>N ⟺ NOT(-N<=x<=N)`). Comma-separated clauses
(e.g. `'shrcd<=11, exchcd==1'`) are all applied (AND). Parsed clauses are
APPENDED to the global backbone filter, not a replacement. Unrecognized
patterns raise `CzFilterParseError` -- never silently dropped or
approximated, matching `apply_universe_filters`'s existing fail-loud policy
for a missing field.

**Real coverage**: 76/78 of the 331-predictor SignalDoc's non-null `Filter`
values parse successfully. The 2 failures (`Mom6mJunk`, `BetaBDLeverage`)
use a threshold relative to a dynamic NYSE-percentile variable
(`me_nyse20`/`me_nyse10`), not a literal number -- correctly rejected rather
than mis-parsed.

`backend/routers/replication.py`'s `/steps/6/cz-config` preview endpoint now
surfaces `raw.filter_expr` for human review and returns 422 (with the raw
expression + parse error) instead of a 500 if a factor's `Filter` can't be
translated. Tests: `tests/test_cz_reference_profile.py`
(`TestParseCzFilterExpr`, `TestCzProfileToConfigOverride`'s new cases) and
`tests/test_backend_cz_config_api.py`'s two new endpoint tests.

### fix: `breakpoint_quantiles` override now remaps `long_portfolios`/`short_portfolios` (2026-08-22)

Real bug found via a failed step6 run (`experiment.failed No columns to
parse from file` on a `cz_actual_config` track): `_build_config_from_resolved`
(`src/steps/step3_codegen/registry.py`) bakes `long_portfolios`/
`short_portfolios` in against the paper's OWN `breakpoint_quantiles` (e.g.
`short_portfolios=[10]` under 10 groups), but the override-merge step
(`config.update(overrides)`) only overlaid the new `breakpoint_quantiles`
value -- it never re-derived which bucket number is the new "extreme" edge.
`cz_profile_to_config_override` (`src/infra/reference/__init__.py`) sets
`breakpoint_quantiles` from C&Z's own reported quantile count, which can
differ from the paper's; whenever it did (e.g. paper deciles, C&Z quintiles),
`short_portfolios` kept pointing at bucket 10 under a 5-group sort -- a
bucket that doesn't exist -- so that leg was always empty, the whole track's
`extreme_group_spread` came back with zero rows, and the empty-result CSV
step7 tried to read raised `No columns to parse from file` (pandas on an
effectively-empty file).

Added `_remap_extreme_portfolios_for_quantile_override` (`registry.py`),
called right after `config.update(overrides)` whenever `breakpoint_quantiles`
is in the override dict: re-maps each of `long_portfolios`/
`short_portfolios` to `[1]` or `[new_quantiles]` based on the already-resolved
`long_leg`/`short_leg` ("low"/"high") label. Raises `ConfigOverrideError`
instead of silently mis-mapping if a leg isn't the single-edge-bucket shape
this pipeline always produces (multi-bucket or non-extreme leg). Covered by
new tests in `tests/test_config_override_validation.py`
(`TestBreakpointQuantilesOverrideRemapsExtremePortfolios`).

Same function also fixes a SECOND, previously-latent instance of the exact
same bug class, found while auditing step6 for other `breakpoint_quantiles`-
override fallout: for a double/conditional-sort factor (`len(sorts) >= 2`),
`config["sort_dims"]`'s `role == "target"` entry's own `quantiles` field is
built once at resolution time from the paper's OLD `breakpoint_quantiles`,
independently of `long_portfolios`/`short_portfolios` -- left stale, the
engine would sort the target dimension into the OLD bucket count while the
(now correctly remapped) short/long leg asks for a bucket that only exists
under the NEW count, i.e. the same empty-result failure but for double-sort
factors. No real run has hit this yet (no double-sort factor has had its
`breakpoint_quantiles` overridden in this repo so far), but it's the same
root cause and now fixed in the same place. Covered by
`tests/test_registry_resolved_method_spec.py::TestBuildConfigDoubleSort::
test_breakpoint_quantiles_override_remaps_target_sort_dim`.

Also worth noting: `standardized_hxz` (③) is exposed to the SAME bug for any
paper whose own `breakpoint_quantiles` isn't already 10 --
`data/reference/hxz_standard_config.yaml` hardcodes `breakpoint_quantiles:
10`, so a quintile paper's ③ track would previously have hit the identical
empty-result failure `cz_actual_config` did here (this particular session's
paper happens to already use deciles, so ③ was a no-op override and never
surfaced it). Both `standardized_hxz` and `cz_actual_config` go through the
same `build_config` override path, so this fix covers both.

### step6: lower `MAX_FACTORIAL_SWITCHES` from 4 to 3 (2026-08-22)

`src/steps/step6_dual_track_controller/__init__.py`'s `MAX_FACTORIAL_SWITCHES`
lowered 4 -> 3 to bound worst-case batch size: when both the ①→③ and ①→②
auto-attribution comparisons hit the ceiling at once, `2*(2^n-2)` factorial
tracks stack on top of baseline/②/③, which was `2*(2^4-2)=28` at n=4 vs
`2*(2^3-2)=12` at n=3. Trade-off: batches with >3 differing known switches
now fall back to OAT (linear track count, no interaction/Shapley attribution)
one field earlier than before. Docstring/comment/test references to the old
value of 4 updated in the same module, `src/steps/step7_replication_diff/
attribution.py`, `tests/test_experiment_plan_matrix_merge.py`, and
`docs/step7-8.md`.

### step6 UI: pre-run experiment count + per-track config preview, gated behind a confirm step (2026-08-22)

Added `POST /api/sessions/{session_id}/steps/6/experiment/preview`
(`backend/routers/experiments.py`) and `MultiTrackController.preview_tracks`
(`src/steps/step6_dual_track_controller/__init__.py`) -- runs the SAME
`_plan_to_matrix` resolution `run_experiment` uses, but only to compute each
track's name/family/identification_level/resolved config diff, without
executing any backtest. Lets the step6 UI show "this will run N experiments"
plus every track's resolved-config-diff detail (previously only visible in
the Result panel after the batch finished) BEFORE submitting the job.

`frontend/src/pages/SessionDetailPage.tsx`'s step6 request card now has a
two-phase flow: "Preview experiment count" (or "...from upstream output")
computes and displays the plan, then a "Confirm & run N experiments" button
(only shown once a preview exists) submits the actual job. Editing the
request body invalidates a stale preview. No per-track selection UI --
Confirm always runs every track the preview showed, matching the existing
single-shared-apply-action pattern used elsewhere in the review UI.

### reference: add `ShareVol` to the step6 UI factor picker + manual C&Z/HXZ fallback (2026-08-21)

Added `ShareVol` (Datar/Naik/Radcliffe 1998) to
`src/infra/reference/manifest.py`'s `CZ_FACTOR_ACRONYM_MANIFEST`
(self-mapped, like `AssetGrowth`/`GP`/`Mom6m` -- no extracted MethodSpec
exists for it yet) so it shows up in the step6 UI's `C_cz` preview dropdown
(`/api/reference/cz-factors`, `frontend/src/pages/SessionDetailPage.tsx`'s
"Run against C&Z's actual configuration" selects).

Also added `ShareVol` to `src/infra/reference/__init__.py`'s
`MANUAL_PAPER_RETURN_FALLBACK` (`mean_return=0.0091`, `t_stat=3.87`) and
`src/infra/reference/hxz_bridge.py`'s `MANUAL_HXZ_REPORTED_FALLBACK`
(`mean_return=-0.0011`, `t_stat=0.46`), so step6's C&Z/HXZ reference columns
resolve for this factor even though `data/CZ code/SignalDoc.csv`'s `ShareVol`
row has a `T-Stat` but no `Return`, and no HXZ testing-portfolio CSV exists
for it under `data/hxz/return_ref/`.

### reference: add `MeanRankRevGrowth` to the step6 UI factor picker + manual C&Z/HXZ fallback (2026-08-21)

Added `MeanRankRevGrowth` (Lakonishok/Shleifer/Vishny 1994) to
`src/infra/reference/manifest.py`'s `CZ_FACTOR_ACRONYM_MANIFEST`
(self-mapped, same pattern as `ShareVol` above -- no extracted MethodSpec
exists for it yet) so it shows up in the step6 UI's `C_cz`/HXZ preview
dropdowns.

Also added `MeanRankRevGrowth` to `src/infra/reference/__init__.py`'s
`MANUAL_PAPER_RETURN_FALLBACK` (`mean_return=0.0055`, `t_stat=3.94`) and
`src/infra/reference/hxz_bridge.py`'s `MANUAL_HXZ_REPORTED_FALLBACK`
(`mean_return=-0.0019`, `t_stat=1.08`), since `data/CZ code/SignalDoc.csv`'s
`MeanRankRevGrowth` row has neither a `Return` nor a `T-Stat` field filled in
(only a paper-text note of a double-sort t=4.5, not the LS-portfolio number
this fallback represents), and no HXZ testing-portfolio CSV exists for it
under `data/hxz/return_ref/`.

### backtest_engine: wire `PortfolioSpec.transforms` (winsorize) into the engine (2026-08-21)

Fixed a bug where `PortfolioSpec.transforms` (`paper.portfolio.transforms`,
documented in `src/infra/models/schema_reference.py`) was a real field
populated by extraction/resolution but was never consumed downstream:
`registry.KNOWN_CONFIG_KEYS` had no `transforms` entry (`build_config`
silently dropped it) and `BacktestExecutor` had no winsorize/clip code path
at all. 5 of 14 resolved specs (all Dichev 1998 `oscore`, from 5 separate
extraction attempts) declared `{"kind": "winsorize", "stage":
"after_signal", "bounds": [0.01, 0.99]}` per the paper's own stated
methodology ("the top and bottom 1 percent of observations for each
variable ... are set at the 1st and the 99th percentile"), and none of the
5 generated plugin runs ever applied it -- the computed `oscore` signal had
extreme un-clipped outliers (observed range roughly -2908 to 5604 vs a
normal O-score range of about -10 to +10) that fell disproportionately in
the extreme deciles used for the paper's long-short spread.

Added `src/steps/step3_codegen/registry.py`'s `_applied_transforms`/
`_unapplied_transforms` (mirrors `_applied_universe_filters`/
`_unapplied_universe_filters`): only `{"kind": "winsorize", "stage":
"after_signal"}` is currently implemented and lands in `config["transforms"]`;
anything else lands in `config["unapplied_transforms"]` instead of being
silently dropped, and both keys were added to `KNOWN_CONFIG_KEYS`/
`CONFIG_KEY_STAGE` (classified `signal_input`, since a transform changes the
realized signal value the same way `missing_action` does). Added
`BacktestExecutor.apply_transforms` (`src/infra/backtest_engine/__init__.py`),
called once in `run_with_config` right after `self.signal` is set (same
"correctness-critical processing lives in the engine, not per-plugin"
convention as the existing `pd.to_numeric` signal-dtype normalization):
clips `signal["signal"]` at the given percentile bounds, computed
cross-sectionally PER CALENDAR MONTH (`groupby("yyyymm")`) to match how the
paper's decile portfolios are actually formed monthly. A no-op when
`config["transforms"]` is empty/missing, so every other existing factor is
unaffected. New tests: `tests/test_apply_transforms.py` (per-month clipping
behavior, unsupported kind/stage left un-applied, empty/missing
`transforms` is byte-for-byte no-op) and
`tests/test_registry_resolved_method_spec.py::TestBuildConfigTransforms`
(resolved-spec `transforms`/`unapplied_transforms` serialization).

### backtest_engine: forward-fill low-frequency (Compustat-annual) signals under monthly rebalance (2026-08-21)

Fixed a bug where an annual-cadence signal (e.g. Ohlson O-score, Altman
Z-score -- one row per permno per fiscal year, sourced from
`compustat_fundamental_annual`) combined with `rebalance_frequency:
"monthly"` collapsed to near-zero coverage: `apply_signal_holding_period`'s
`hold = min(holding_period_months, _rebalance_step_months(config))` caps
`hold` at 1 for `rebalance_frequency == "monthly"`, so each annual signal row
only ever expanded into the ONE calendar month right after its own
formation month and then vanished for the other ~11 months of the year --
`signal_max_staleness_months` was defined in every generated config but
never actually wired up for this case (only `_resample_annual_signal_asof`
read it, and that path is gated to `rebalance_frequency == "annual"` only).
Confirmed as a real bug in `oscore`'s (session `d4718bf1865e48f5964e5aa997c4e160`)
`return_series`: dense monthly coverage some years, collapsing to exactly one
observation per year (every July) once accounting-annual-only firms
dominate.

Added a new `signal_cadence` config key (`"monthly"` default -- byte-
identical to today's behavior for every existing config -- or
`"low_frequency"` when any resolved `SIGNAL_INPUT` concept maps to a
non-CRSP source), derived by a new `_signal_cadence()` helper in
`src/steps/step3_codegen/registry.py`'s `build_config`/
`_build_config_from_resolved` (mirrors `script_generator
.pick_signal_input_mode`'s own source classification, computed
independently to avoid a circular import since `script_generator.py`
already imports `registry.py`). Registered in `KNOWN_CONFIG_KEYS` and
`CONFIG_KEY_STAGE` (`"signal_input"` stage) alongside the other signal-input
keys. Threaded automatically into the generated script's `CONFIG` dict
(`script_generator.generate_backtest_script` already embeds `build_config`'s
full output) and available identically on the in-process path
(`assemble_signal_master_table`/direct `BacktestExecutor` callers).

`BacktestExecutor.apply_signal_holding_period` (`src/infra/backtest_engine/__init__.py`)
gained `_forward_fill_low_frequency_signal`, called alongside (not
replacing) `_resample_annual_signal_asof`: when `rebalance_frequency ==
"monthly"` and `config["signal_cadence"] == "low_frequency"`, forward-fills
the annual signal onto every calendar month via `asof_align_to_monthly`
(the same staleness-capped mechanism `join_universe_filter_sources` already
uses for the analogous universe-filter case), capped at
`signal_max_staleness_months` (default 11), BEFORE the existing hold-window
expansion runs -- so each now-monthly row's `hold=1` correctly means "one
row -> one held month" instead of "the annual row disappears for 11
months". Mutually exclusive with `_resample_annual_signal_asof` (annual
rebalance + explicit `formation_month` only) by construction; a config with
no low-frequency evidence keeps `signal_cadence` defaulted to `"monthly"`
and is a complete no-op through this new path.

New tests in `tests/test_calendar_rebalance.py`: forward-fill spreads a
single annual formation across all 12 held months, staleness cutoff still
applies, and the low-frequency gate never fires for an annual-rebalance
config (stays on `_resample_annual_signal_asof`'s path). Confirmed
`tests/test_calendar_rebalance.py::test_monthly_caps_hold_at_one_month`,
`::test_monthly_signal_not_resampled_by_annual_asof_logic`, and
`tests/test_formation_lag_months.py::test_lag_crosses_year_boundary` pass
unmodified (none declare `signal_cadence`, so they stay on the untouched
default-`"monthly"` path). Regenerating `oscore`'s and `zscore`'s stored
resolved configs (`build_config` re-run against their stored `spec.json`)
confirms the only diff from the old stored config is the new
`signal_cadence: "low_frequency"` key -- everything else is byte-identical,
confirming this is a strictly additive, opt-in-by-evidence change.

### data_layer: "time_only" macro signal sources + FRED GDP deflator (2026-08-21)

Added generic support for market-wide, non-permno-keyed macro time series as
a usable `SIGNAL_INPUT`. `DataSource` gained a `keyed_by` property
(`"permno_time"` default vs `"time_only"`); `assemble_signal_master_table_from_sources`
now splits off any `"time_only"` source's frame (`[time_avail_m, *cols]`, no
permno) and broadcasts it onto the already-assembled permno-keyed master via
a `time_avail_m`-only merge, applied AFTER the existing `[permno,
time_avail_m]` outer-merge assembly so every currently-registered
permno-keyed source's behavior is unchanged.

New bespoke `MacroSignalSource` (parallel to `CrspSignalSource`/
`ThirteenFSignalSource`), registered as `fred_gdp_deflator`
(`concept_columns` incl. `"gnp_price_level_index"`/`"gdp_deflator"`) --
FRED's GDP Implicit Price Deflator (series GDPDEF), used as the standard
modern substitute for the GNP price-level index in Ohlson's (1980) O-score
`log(total assets / GNP price-level index)` term (BEA no longer separately
publishes a GNP deflator). Reads a pre-fetched snapshot
(`data/local/gdp_deflator.parquet`, columns `yyyymm`/`value`) built by the
new build-time-only `scripts/fetch_fred_series.py` (mirrors
`scripts/fetch_ff_factors.py`, uses the existing dev-only
`pandas-datareader` dependency -- no new runtime dependency). GDPDEF is
quarterly; the fetch script forward-fills each quarter's value across its 3
months (simplest sane choice for a slowly-changing scaling denominator) and
applies a fixed 1-month availability lag (documented simplification, not a
modeled point-in-time revision schedule). No extractor-prompt change needed:
`SourceName`/`data_catalog` are derived live from the `sources.py` registry,
so the new source is automatically a valid `source_table` choice.

New tests: `tests/test_macro_signal_source.py` (registration, `keyed_by`,
snapshot-missing/lag stamping, broadcast merge, and the macro-only fallback
path). Updated `tests/test_data_catalog.py`'s `_HISTORICAL_SIGNAL_SOURCES`
snapshot to include the new source.

### step2 UI: human-editable universe filters (2026-08-21)

The Step2 review page's "Universe filters" panel now lets a human add, remove,
or edit an existing `universe.filters[]` entry directly -- `concept_id` and
`op` as dropdowns (concept options come from the spec's own `data.fields`;
op options come from the `FilterOp` enum via the schema-reference endpoint),
`value` as a free-text JSON field (a flat list for `in`/`not_in`, a list of
`[low, high]` pairs for `intervals`, a scalar for the rest). Same client-side-
edit convention as the existing `derivation`/`accepted_unapplied` editors
(`FilterSpec`'s scalar fields aren't `SourcedValue`s, so `/patch-value` can't
touch them) -- `state.paper` is resent wholesale on the next `/review` or
`/resolve` call, nothing persisted server-side until then. Findings whose
`field_path` is a `universe.filters[i]` entry (any `kind`, including the new
panel-mismatch check above) are now routed to this editor instead of the
generic scalar value-patch UI, which would 500 on a field_path outside
`apply_value_patches`' fixed known set.

Every add/edit/remove also carries a reason, recorded as an audit trail: an
edit or a newly added filter gets a `human correction: <reason>`
`EvidenceCitation` appended to that filter's own `evidence[]` (mirroring
`apply_value_patches`'s convention for scalar fields); a removal appends a
note to `MethodSpec.notes` instead, since the filter itself no longer exists
afterward to carry a citation.

### extractor/step2: catch a universe filter that scopes the wrong panel (2026-08-21)

When a paper reports the same signal under several parallel panels that
differ only in one sample-restriction dimension (exchange listing, firm
size, industry, sub-period, etc.), the extractor and LLM review prompts
previously tended to anchor on the paper's one generic "our sample includes
NYSE, Amex, and NASDAQ" sentence and always emit the combined
`exchcd in [1, 2, 3]` screen, even when `reported_results.metrics` was
actually read from a narrower panel (e.g. a NASDAQ-only table reported
alongside a separate NYSE+AMEX-only table). Both prompts now state this as a
general "match the filter to the panel you extracted numbers from" rule
(not specific to `exchcd` or any one field) and no longer unconditionally
push the extractor/reviewer toward the combined value. Step2's deterministic
review also gained a new, field-agnostic structural check
(`_universe_filter_panel_mismatch_findings`): when a universe filter's own
citation names a different table than `reported_results.metrics`' citation,
it is flagged `inconsistent` / `needs_human_confirmation`. A filter cited
only by prose (no `table_ref`) is left alone -- that is normal even for a
single-panel paper and this check cannot distinguish it from a genuine
mismatch without re-reading the paper.

### reported results: opt-in deterministic table endpoint spreads (2026-08-21)

`reported_results` can now request an explicit `high_minus_low` comparison
from two cited portfolio table cells. The extractor records the endpoint
facts and selectors only; Step5 deterministically materializes the difference
for the paper-reference endpoint. Step2 rejects mismatched endpoint metadata
or legs that do not implement the same spread, and the dashboard labels the
result as derived. The extension is opt-in: an absent derivation retains the
legacy primary-metric behavior and content hash.

### step2: require cited universe restrictions to reach human review (2026-08-20)

Every declared universe filter is now a high-impact review item. The reviewer
also flags any quoted/table universe-description evidence that is not reused
by an executable filter as an `incomplete` / `needs_human_confirmation`
finding; an unsupported or invented data field cannot satisfy coverage. The
extractor and reviewer prompts include the standard CRSP example
`exchcd in [1, 2, 3]` for an explicitly stated NYSE/AMEX/Nasdaq screen. The
existing `Finding.kind` vocabulary now includes `incomplete` and
`universe_filter` so these cases retain their structural meaning in the UI.

### data layer: preserve raw CCM `gvkey` leading zeros (2026-08-20)

The raw link-table CSV loader now reads its declared identifier key as text.
This prevents pandas from converting CCM `gvkey` values such as `001000` to
`1000`, which previously broke the raw Compustat-to-CCM join and removed most
pre-1990 observations from the Dichev Z-score backtest.

### step6: add Dichev ZScore C&Z/HXZ references (2026-08-20)

Registered the reviewed Dichev Z-score session (`d5661ba61aae804d`) as C&Z
`ZScore`, so it appears in Step 6's OpenAssetPricing C&Z dropdown. Added the
user-provided HXZ reference (`mean_return=0.01`, `t_stat=0.06`) for the same
acronym. It is explicitly labelled as a manual reference without an HXZ
testing-portfolio CSV and is not presented as a window-adjustable
recomputation. The C&Z and HXZ selectors render the C&Z acronym alone rather
than the internal hashed factor ID.

### universe filters: add explicit `intervals` unions (2026-08-20)

Added the `FilterOp.intervals` `{field, op, value}` predicate for a union of
inclusive numeric intervals, preserving the existing top-level AND filter
pattern. The schema and engine validate/evaluate it deterministically; Step2
now flags disjoint same-field `between` filters that would otherwise create
an empty universe, and extraction/review prompts instruct the LLM to emit the
single union predicate. The frontend renders range unions readably and offers
an explicit conversion action for disjoint `between` filters and legacy
invalid `in: [[low, high], ...]` values. The schema now rejects that invalid
legacy shape outright, so it cannot silently reach the backtest engine.

### step4: run validation samples from raw CSV inputs (2026-08-20)

Step4's full-script smoke test now forces the generated script's CSV fallback
and the source loaders recognize `data/local/validation_sample/`'s flat
`*_sample.csv` layout. This prevents optional flattened CRSP/Compustat
parquets from masking the raw-loader path during validation; the existing CCM
parquet link table remains available unchanged. Identifier keys are normalized
textually before the raw-CSV-to-CCM join, covering CSV numeric inference (for
example `gvkey`) without losing identifier semantics.

### latex: organize the pipeline section by agent steps 1--8 (2026-08-20)

Rewrote the controlled-replication-pipeline section to give each pipeline step
its own account, including standalone script execution (Step 5) and
multi-track/refreeze orchestration (Step 6). The description now also states
that Step 8 is an optional, evidence-constrained LLM diagnosis layer, while
preserving the boundary that empirical choices and reported numbers remain
deterministic. It now explicitly identifies registered data availability and
the finite menu (including EW/VW) as operational limitations, with a
cross-reference to the study scope.

### Dichev Z-score: force CCM-aligned CRSP market equity (2026-08-20)

For `Z_score` from *Is the risk of bankruptcy a systematic risk?*, the
user-approved implementation policy now hard-requires CRSP fiscal-year-end
`abs(prc) * shrout / 1000` (through CCM) and Compustat `lt`. Step 1/2 prompts
state the contract, Step 2 records violations, Step 3 refuses non-compliant
specs and builds the fiscal-month CRSP/Compustat join, and Step 4 rejects
plugins that use Compustat market-value/price/share substitutes or omit the
required raw inputs/unit conversion.

### step6: stream per-track experiment progress to the session log (2026-08-20)

Step 6 now logs the planned number of tracks (including reused baselines),
each track's start, and each completion with status, mean monthly return, and
t-stat. A re-freeze batch rerun is logged explicitly. These messages flow
through the existing job SSE stream and persisted session event journal, so
the UI shows useful progress during full-data multi-track runs.

### repo: keep ZIP data archives local by default (2026-08-20)

Added a global ZIP ignore rule and removed the HXZ testing-portfolio archives
from Git tracking while retaining every archive in the local working tree.

### repo: keep CSV data local by default (2026-08-20)

Added a global CSV ignore rule and removed the CSV files accidentally added by
the latest commit from Git tracking. The local files are retained; the older
tracked HXZ reference CSV is unchanged.

### latex: adopted the supplied master's template and UNIL title page (2026-08-20)

Reformatted the existing `latex/` document with the supplied template itself,
including its `MastersDoctoralThesis.cls`, exact margins/spacing/headings,
header and footer scheme, BibLaTeX author-year style, ruled title-page layout,
and original UNIL EPS logo. The adaptation is confined to the formatting
wrapper and copied template assets; thesis section/table text, bibliography
data, citations, equations, and figure placeholders are unchanged.

### data_layer: registered `fopt`/`lt` concept aliases + `fopt` description (2026-08-19)

`compustat_fundamental_annual`'s `fopt` (Funds From Operations - Total) and
`lt` (Total Liabilities) physical columns were selectable but had no
`concept_columns` aliases, so a paper phrase like "funds from operations"/
"total liabilities" (e.g. Ohlson 1980 O-Score) couldn't auto-resolve at
Step1 extraction -- only a bare literal `fopt`/`lt` token would match. Added
aliases (`funds_from_operations`/`funds from operations`/`fopt` -> `fopt`;
`total_liabilities`/`total liabilities`/`lt` -> `lt`) and a
`column_descriptions` entry for `fopt` (`lt` already had one).

### step3_codegen: target sort's `sort_dims` quantiles no longer disagree with `breakpoint_quantiles` (2026-08-19)

In a multi-sort (`len(sorts) >= 2`) MethodSpec whose target dimension left
`group_count` unset, `config["breakpoint_quantiles"]` (used to resolve
`long_portfolios`/`short_portfolios` bucket numbers) defaulted to 10 while
the target's own `config["sort_dims"][i]["quantiles"]` (what the engine
actually buckets into for a multi-dim sort) defaulted to 2 -- a real bucket-
count mismatch that could leave a leg's selector pointing at a bucket that
doesn't exist. `registry.py`'s `_build_config_from_resolved` now has the
target dim's `sort_dims` entry reuse `config["breakpoint_quantiles"]`
directly instead of its own separate `or 2` fallback, so the two paths
always agree for the target dimension. Non-target (conditioning/control)
dimensions are unaffected -- they still default to 2.

### scripts: renamed `build_comp_funda` helper to `build_compustat_fundamental_annual` (2026-08-19)

Follow-up cleanup: `scripts/build_test_papers_synthetic_data.py`'s synthetic
Compustat annual builder function was still named `build_comp_funda` from
before the source-name rename below; renamed to match the registered
`compustat_fundamental_annual` source key it builds data for. No behavior
change (name-only).

### data_layer: renamed `comp_funda` source to `compustat_fundamental_annual`; removed `comp_fundq` (2026-08-19)

Per user request, for readability: the Compustat annual `SourceSpec` registry
key `comp_funda` is now `compustat_fundamental_annual` everywhere -- `sources.py`
(registration, `COMPUSTAT_FUNDAMENTAL_ANNUAL_PHYSICAL_COLUMNS` constant),
`source_enum.py`'s dynamically-generated `SourceName` enum (no code change
needed there, just a comment), `data/reference/hxz_standard_config.yaml`'s
`universe_filter_join_sources` key, the extractor/review-gate LLM prompts'
example source name, `script_generator.py`'s `_BINARY_SIGNAL_SOURCES`,
`app.py`/`backend/state.py`/`scripts/build_synthetic_data.py`/
`scripts/build_real_wrds_samples.py`/`scripts/build_test_papers_synthetic_data.py`'s
`comp_funda.parquet` snapshot filename (renamed the 3 real on-disk files:
`data/synthetic_data/mvp_v1/`, `data/synthetic_data/test_papers_v1/`,
`data/local/validation_sample/`), and every test file referencing the old
string (`tests/test_data_sources.py`, `test_data_catalog.py`,
`test_backend_api.py`, `test_registry_resolved_method_spec.py`,
`test_script_generator_resolved_method_spec.py`,
`test_signal_master_multisource.py`, `test_real_wrds_csv_loaders.py`,
`test_meta_coder_resolved_method_spec.py`, `test_method_spec_contract.py`,
`test_step2_reviewer*.py`, `test_llm_normalized_mapping.py`,
`test_implementation_resolution_llm.py`, `test_accruals_e2e.py`,
`test_mvp_e2e.py`, `test_execute_data_path_override.py`, `test_hashing.py`,
`_spec_test_helpers.py`). Historical CHANGELOG entries and one
`docs/cz-reference.md` decision-log-style narrative deliberately left
referencing the old name (never rewrite history).

Also fully removed `comp_fundq` (quarterly Compustat), requested separately
in the same session: it was only ever registered with 4 fields
(`atq`/`ceqq`/`saleq`/`ibq`) and its `build_comp_fundq` synthetic-data
builder in `scripts/build_test_papers_synthetic_data.py` had become
orphaned/dead code once the source was dropped from the registry --
removed the registration, the golden `_HISTORICAL_SIGNAL_SOURCES` entry in
`tests/test_data_catalog.py`, and the synthetic builder + its `tables` dict
entry.

Separately (earlier in the same 2026-08-19 session): registered ALL 980 raw
columns from `COMPUSTAT_FUNDAMENTALS_ANNUAL.csv` (previously only 26) and
all 87 raw columns from `CRSP_STOCK_MONTH.csv` (previously only 10) in
`sources.py`'s `physical_columns`, with best-effort `column_descriptions`
for the commonly-recognized subset (143 Compustat / 27 CRSP) -- the rest
selectable but intentionally left undescribed rather than guessed. Also
fixed a pre-existing latent gap where `crsp_msf`'s `prc` concept column was
declared but never actually populated by the monthly CIZ loader (only the
daily loader produced it) -- `build_crsp_monthly_panel_ciz` now renames
`MthPrc`->`prc` and numeric-coerces it like `ret`/`me`/`siccd`.

Verified via the full affected test surface (`test_data_sources.py`,
`test_data_catalog.py`, `test_real_wrds_csv_loaders.py`,
`test_backend_api.py`, and the broader resolved-MethodSpec/script-generator/
step2-reviewer suites) -- all passing.

### docs: replace the 6-factor thesis roster with an HXZ-vs-C&Z-verdict-driven list (2026-08-19)

Per user request, replaced `docs/paper-outline.md` §5.3's 6-factor roster
(`AssetGrowth`/`GP`/`PS`/`BrandInvest`/`OperProfRD`/`grcapx3y`) with a new
candidate table derived from the user's own
`data/test_papers/test_papers_data_sources.xlsx`, which selects factors by
actual HXZ-vs-C&Z verdict divergence (agree / HXZ-fails-C&Z-succeeds / data-
vintage divergence / both-fail) rather than only C&Z's `Notes` text. Verified
each candidate against `data/CZ code/SignalDoc.csv` and the local raw CSVs:
- `Leverage` (Bhandari 1988) is a **hard reject** -- `Test in OP = mv reg` and
  empty `LS Quantile`, the same flaw that earlier ruled out `TotalAccruals`/
  `OperProf` (no portfolio-sort spread to compare against, only a regression
  coefficient).
- `fgr5yrLag` (La Porta 1996) needs a new `ibes_ltg` source registration --
  likely the same `IBES_UNADJUSTED_SUMMARY.csv` file with `MEASURE="LTG"`
  instead of the existing `MEASURE="EPS"` filter (mechanical, but the actual
  `MEASURE` value is unverified -- no file-content scan was done, only the
  header). This factor's divergence type (pure data-vintage divergence, not
  explainable by methodology) is flagged as a known blind spot of this
  paper's framework -- valuable for Ch.8's honest-disclosure section.
- `GP`'s xlsx numbers (0.30/2.38) don't match `SignalDoc.csv` (0.31/2.49) --
  flagged for the user to reconcile the source before citing either.
- `AssetGrowth` stays as the already-run anchor; the xlsx adds two further
  published comparison numbers (HXZ's I/A annual version, C&Z's quarterly
  `AssetGrowth_q`) that can enrich, not replace, the existing 13-track case.
- `OScore`/`FailureProbability` carry forward their previously-documented
  engineering caveats (asymmetric quantile split; `mktrf`-as-signal-input +
  quarterly fields, respectively).

Net: 7 candidates in, 1 hard-rejected, final count (6 vs. dropping
`FailureProbability` for 5) still open with the user. Session memory
(`/memories/session/plan.md`) updated with the full reconciliation, and
flagged that `latex/tables/tab_factor_roster.tex` and other factor-count-
dependent LaTeX content still reflect the now-superseded 6-factor list and
need a follow-up pass once the roster is finalized.

### step6/step8: removed `missing_action` as an ablation/factorial attribution switch (2026-08-19)

`_ABLATION_SWITCH_TO_CONFIG_KEY`'s `"missing": "missing_action"` entry (and its
mirror, step8's `_CONFIG_KEY_TO_SWITCH_NAME`) was structurally dead, not just
currently unused: `apply_missing_policy` never reads the config value (see the
2026-08-16 `HXZ_STANDARD_CONFIG` cleanup), and every track this pipeline builds
resolves it to `"drop"` regardless of input (`STANDARD["missing_action"]` clamps
anything else to `"drop"`; `HXZ_STANDARD_CONFIG` omits the key entirely;
`cz_profile_to_config_override` sets it to `"drop"` unconditionally) -- so
`missing_action` can never actually appear in `_diff_switches`'/`config_diff`'s
output. Left in place, it was a latent trap: if some future caller ever forced
it into `ExperimentPlan.ablation_switches`, the resulting track would show a
differing config value while running byte-identical code (the value is
ignored), making a Shapley/OAT "zero contribution" for it unreadable as "this
dimension doesn't matter" vs "this dimension was never actually exercised".
Removed from both switch maps rather than documented-and-kept.
`CZ_HOUSE_CONVENTION_KEYS` (a different, still-accurate concept: which keys
`cz_profile_to_config_override` sets unconditionally) is untouched.
`tests/test_experiment_plan_matrix_merge.py`'s
`test_auto_attribution_falls_back_to_oat_above_four_switches` updated from a
hand-built 6-switch target to 5 (the real remaining switch count); asserts
`len(specs) == 5` instead of 6.

### step7 UI: the gap chart now renders for full-factorial batches too, from Shapley effects (2026-08-18)

`GapWaterfallChart` only ever read `gap_decomposition.contributions`, which
requires `ablation_*` (OAT) tracks. A full-factorial batch runs none, so
`gap_decomposition.available` is `false` and `Step7Output` deliberately hid the
chart entirely (`showGapWaterfall = gap.available === true ||
!anyShapleyAvailable`) to avoid it reading as "attribution failed" -- leaving
such a batch with no gap chart at all.

The chart now falls back to `shapley_attribution.<line>.shapley_effects`, one
panel per comparison line. This is not a degraded substitute: Shapley effects
sum EXACTLY to the total gap (`shapley_sum_check`), unlike OAT contributions,
so those panels carry no residual bar and say so, while the OAT path keeps its
residual bar plus its non-additivity note. `showGapWaterfall` and its now-unused
`gap` binding are gone -- the component picks its own source, and only reports
"No gap decomposition available" when neither source exists.

Verified in-browser against the real AssetGrowth batch (session
`9bf048cba5604856b9d0c5dbe36fbed4`): both `to_cz` and `to_hxz` panels render.

### docs: generate the thesis LaTeX skeleton under `latex/` (2026-08-18)

Materialized the discussion in `docs/paper-outline.md` into an
Overleaf-compilable skeleton: `main.tex` + `preamble.tex` (notation macros
for $A$/$C_{cz}$/$C_{std}$/etc.) + 8 chapter files under `sections/` +
6 appendix files (A-F) + 12 table placeholders under `tables/` (columns
match real `comparison.json`/`.metrics.json` keys, each with a source
comment) + seed `refs.bib` + `figures/` + `README.md`. Chapters follow the
RQ1 (three-term paper-anchored decomposition) / RQ2 (agent autonomy)
split and the six-factor roster (`AssetGrowth`, `GP`, `PS`, `BrandInvest`,
`OperProfRD`, `grcapx3y`) finalized in `docs/paper-outline.md` §5.3. Ch.7 is
organized by each factor's designed divergence axis, not alphabetically.
No local TeX engine was available to compile-test; instead verified
structurally (every `\input` target resolves, braces and
`\begin`/`\end` environments balance across all `.tex` files) -- caught and
fixed one real bug this way: table `\input` paths inside `sections/*.tex`
were written as `../tables/...`, which is wrong (LaTeX resolves `\input`
relative to `main.tex`'s directory, not the including file's), corrected to
`tables/...`.

### step7/step8: `three_term_identity` -- an external implementer's distance from the PAPER's own reported number, split into signal / config / agent-replication residual (2026-08-18)

Implements docs/paper-outline.md's C1. Every existing gap section compares
TRACK vs TRACK (`gap_decomposition` = ①→③, `gap_closure` = ①→②), so nothing was
anchored on the paper's own reported spread and "which implementer is closer to
the paper" was unanswerable. New section decomposes, per external reference:

    X - P = (X - A_hybrid) + (A_hybrid - A) + (A - P)

`P` = paper's reported spread, `A` = `original_method`, `A_hybrid` =
`cz_actual_config`/`standardized_hxz` (agent signal under that implementer's
config), `X` = that implementer's OWN measured result. The identity telescopes,
so `residual` is 0 by construction and is emitted only as an arithmetic audit
check, exactly like `gap_decomposition.residual`.

- **New `src.infra.reference.external_reference_endpoints()`** resolves the two
  external endpoints. This is the first consumer of C&Z's and HXZ's own measured
  numbers as a comparison endpoint -- `CZReferenceProfile` and `hxz_bridge` both
  already existed but neither was ever read by `build_evidence_bundle()`.
  Window/basis provenance travels WITH each endpoint because the two sources
  differ on it: C&Z's SignalDoc `Return`/`T-Stat` are static and window-locked
  (`window_adjustable=False`), while `hxz_bridge` recomputes on any requested
  window with this engine's own Newey-West metrics, so HXZ additionally reports
  `window_sensitivity_spread` (paper's window minus HXZ's own 1967-2016 window)
  -- the measurable part of the mismatch. An unresolvable endpoint returns `{}`,
  never raises.
- **New `bundle.build_three_term_identity()` / `build_three_term_identities()`**,
  plus `STANDARDIZED_HXZ_TRACK` / `THREE_TERM_HYBRID_TRACKS`. Both endpoints
  always get an entry; an unresolvable one is `available=False` with a reason, so
  a missing external reference can never read as "the gap was zero".
  `THREE_TERM_PURITY_NOTES` and `THREE_TERM_WINDOW_CAVEAT` ship inside the
  section: the three terms carry different noise (only the config term holds the
  signal fixed on both sides; the signal term also absorbs data-vintage/engine
  differences; the residual term is the agent's own replication error, not paper
  ambiguity) and the four endpoints share no sample window. Identification is
  pinned at `observational` -- nothing here is a controlled contrast.
- **`build_evidence_bundle()` gains `external_references=`** (optional, same
  degrade-don't-raise contract as `spec`/`results_dir`).
  `_spec_paper_reported()` now also carries `sample.reported_returns`'
  start/end year -- the window the paper's HEADLINE numbers cover, matching
  `registry.build_config`'s same `reported_returns`-over-`formation` choice --
  so the section can state its `P` endpoint's window instead of leaving the
  mismatch undeclared. `write_comparison_summary` resolves the endpoints from
  `spec.resolution.cz_acronym`.
- **step8: new `three_term_gap_component` claim type**, registered across
  `REASON_LAYER_BY_CLAIM_TYPE` (config_sensitivity), `ANALYSIS_STAGE_BY_CLAIM_TYPE`
  (`vs_paper`, since it too is paper-anchored), `CLAIM_RELATIONS`
  (`larger`/`smaller`/`similar` only -- deliberately NOT `associated_change`, an
  accounting split identifies no effect), `CLAIM_EVIDENCE_REQUIREMENTS`
  (`three_term_identity.`), `CLAIM_EVIDENCE_SUBSTRINGS` (`terms.`, forcing the
  claim onto a named component rather than the section's endpoints or window
  metadata) and `IDENTIFICATION_BY_CLAIM_TYPE` (`observational`, no runtime
  upgrade path). New `THREE_TERM_IDENTITY_TOOL`; `_LINE_FROM_NESTED_KEY` extended
  so such a claim must name its reference. `DiagnosisClaim.comparison_line` /
  `DiagnosisSummary.comparison_line` widened to `to_hxz|to_cz|cz|hxz` -- the new
  section nests by external reference, not by track line, so `cz`/`hxz` are
  distinct values rather than aliases. `render.py` gains its three deterministic
  sentence templates (each restating the accounting-split caveat inline),
  `_three_term_subject()`, and the two new `_LINE_LABELS`.
- 13 new tests in `tests/test_replication_diagnosis.py`
  (`TestThreeTermIdentity`, `TestThreeTermClaimValidation`), covering exact
  telescoping, unavailable-not-zero for each missing endpoint, the
  observational ceiling, evidence-whitelist rejection of a metadata-only
  citation, rejection of a causal relation, and the rendered sentence.
- **UI**: neither step7 nor step8 renders bundle sections generically, so the
  new section would otherwise have been invisible. step7 gains
  `ThreeTermIdentityPanel.tsx` -- deliberately a table, not a stacked bar or
  waterfall: the three terms DO sum exactly here, but a stacked visual would
  invite reading them as comparably-clean effects, so the purity note and the
  window caveat render inline rather than behind a disclosure. step8 gains a
  new `gap_split` section: `summary.build_three_term_summaries()` builds it
  straight from the bundle (like every other builder there) so it appears even
  when the LLM makes zero claims about it, `DiagnosisSummary.section` accepts
  `"gap_split"`, and `Step8Output.tsx` gains its ordering/eyebrow/accent.
  `_THREE_TERM_REFERENCE_KEYS` keeps `cz`/`hxz` out of the per-track-line loop
  so a `comparison_line="cz"` claim can't also spawn a duplicate
  robustness-bucketed summary. 7 further tests (`TestThreeTermSummary`).

### docs/paper-outline.md: thesis argument restructured around two parallel RQs + a paper-anchored decomposition (2026-08-18)

Discussion-only doc change, no code touched. Four revisions, in order:

1. **Literature numbers verified against the actual PDFs** (`docs/*.pdf`, extracted
   with pymupdf and checked line by line). A previously circulated second-hand
   summary claiming "437 variables / 63% failed" was **fabricated** and is now
   discarded. Verified replacements recorded in the new §0bis table: HXZ (2020)
   = 452 anomalies, 65% fail |t|≥1.96 under NYSE breakpoints + VW, 82% under the
   2.78 multiple-test hurdle, and 43.1% when switching to EW + NYSE-Amex-Nasdaq
   breakpoints (HXZ's own quantification of the weighting dimension); C&Z =
   319 characteristics, only 3 fail, reproduced-vs-hand-collected t-stat
   regression slope 0.88 / R²=82%; JKP (2023) Figure 1's six bars
   (35 → 55.6 → 61.3 → 82.4 → 75.6 → 82.4%), with its footnote 4 config-difference
   checklist flagged as a cross-validation target for our own `config_diff`.
2. **C1 re-anchored on the paper's own reported number `P`.** The old framing
   compared `CZ` vs `HXZ` -- two third-party implementations with no anchor, so
   "who is closer to the paper" was unanswerable. Now a three-term identity,
   `CZ - P = (CZ - A_cz) + (A_cz - A) + (A - P)`, with the field-level
   `gap_decomposition` explicitly scoped to splitting the *config* term
   `(A_cz - A)`. Confirmed decision: a **fourth window/basis-mismatch residual
   term** is carried explicitly (option a), because `CZReferenceProfile`'s
   SignalDoc numbers have a fixed window while `hxz_bridge` can target the
   paper's own window -- the identity stays exact and the extra term is itself
   informative.
3. **Contributions restructured from "one main line + two supports" to two
   parallel research questions.** RQ1 (the C&Z/HXZ replication-disagreement
   question) and RQ2 (agent capability) were both original motivations; RQ2 is
   no longer written as a support prop for RQ1. C3 is demoted to the shared
   credibility infrastructure both RQs rest on.
4. **Evaluation unit fixed as the agent SYSTEM, not "the LLM".** Human
   confirmation is a designed component of the agent, so C2's metrics changed
   from "extraction fidelity vs a human-audited ground truth" (circular, and it
   would have required a labeling corpus that doesn't exist) to an **autonomy
   footprint**: share of high-impact fields completed autonomously vs
   escalated, end-to-end zero-code-change completion, and where intervention
   concentrates -- split into purely technical vs empirical-value interventions.
   These are a free byproduct of running the 5 factors, since
   `apply_value_patches` already records each confirmation into
   `SourcedValue.evidence`. Consequently the leakage-boundary argument is
   tightened and now stated up front: SignalDoc.csv never enters the pipeline
   (hard), but the human confirmation step's independence rests on operator
   discipline (soft).

### step8: `CONFIG_KEY_LABELS` split into short inline names + a hover-tooltip glossary (2026-08-18)

`_readable_key` previously inlined the FULL 20-33-word zero-background
explanation (e.g. "whether bigger companies count for more in the
portfolio, or every stock counts equally") every time a setting was
mentioned -- in a card with 3+ per-setting bullets, this buried the actual
numbers (t-stats, effect sizes) under repeated prose. Split into
`_SHORT_KEY_LABELS` (used inline, e.g. "portfolio weighting") and the
now-glossary-only `CONFIG_KEY_LABELS` (the long explanation, surfaced as a
tooltip). New `_glossary_for_keys(keys) -> {short_label: long_explanation}`
helper. `DiagnosisSummary`/`VsPaperSummary` gain a `glossary: dict[str,
str] = {}` field, populated per section from the SAME keys that section's
prose already mentions (`_build_cz_summary`'s changed config keys,
`_build_sensitivity_summary`'s Shapley switches, `build_vs_paper_summary`'s
paper-silent fields, `build_spec_quality_summary`'s weak/unsupported field
paths). `_build_cz_summary`/`_build_sensitivity_summary`/
`_build_robustness_summary`/`_dispatch_summary_parts` all extended from
3-tuple `(headline, details, footnote)` to 4-tuple `(..., glossary)`
returns. Frontend (`Step8Output.tsx`): new `GlossaryTerms` component renders
each section's terms as a small "Terms: ..." line with a native `title`
hover tooltip per term -- no new UI dependency. 4 existing test assertions
updated to check the short label in prose + the long text in `.glossary`
instead of the long text inline; `_build_robustness_summary`'s one direct
test call updated for the new 4-tuple return.

### step8: de-boilerplated the LLM-claim "LLM-reviewed"/"LLM flagged" restatement bullets (2026-08-18)

`_fold_claim_evidence_into_details` previously always appended
"LLM-reviewed per-setting significance: ...", "LLM-reviewed
joint-significance conclusion: supported/not supported by the data.", and
"LLM flagged as dominant driver(s): ..." bullets -- these only repeated
numbers the deterministic per-setting bullets (their own "Effect: ..."
text) and the joint-test headline/footnote already showed, and the
"LLM-reviewed" phrasing implied the LLM was judging significance, which it
never does (AGENTS.md: the LLM never decides a number that enters a
conclusion). Replaced with a single CONFLICT-only check: new
`_deterministic_dominant_switch(bundle, line)` finds the single largest-\|t\|
switch on a comparison line from `paired_tests`; if the LLM's own
`dominant_switches` pick disagrees with it, one "Note: the LLM flagged ...
which differs from the setting with the largest measured effect ..." bullet
is added -- agreement adds nothing, since it would just repeat the
per-setting bullet above it. `per_switch_summary`/`joint_supported`/
`dominant_switches` remain on `DiagnosisSummary` for evidence_keys/citation,
just no longer restated as prose. 2 new tests
(`test_llm_dominant_pick_agreeing_with_deterministic_ranking_adds_no_bullet`,
`test_llm_dominant_pick_disagreeing_with_deterministic_ranking_adds_a_conflict_note`);
1 existing markdown-render test updated to assert `"LLM-reviewed"` no
longer appears at all.

### step8: report restructured into 4 reader-facing sections, ordered by READER QUESTION not comparison target (2026-08-18)

Previously three cards organized by comparison TARGET (vs. C&Z / vs. HXZ /
vs. paper), each showing the SAME `overall_tag` badge -- readers misread it
as "we disagree with C&Z" or "we disagree with HXZ" when it only ever meant
"our result vs the paper's". Restructured into 4 sections ordered by what a
reader actually wants to know first: **reproduction** (did it replicate the
paper? -- the only place `overall_tag` renders as a badge now) ->
**robustness** (is it stable? -- ablation `robustness_summary` + the
standardized-HXZ protocol as one named case within this section, no longer
its own top-level card + baseline `publication_decay` + which
`t_channel_decomposition` channel drives any t-stat gap) -> **vs_cz**
(why do we disagree with C&Z? -- now leads with the actual LEVEL on each
side and the total gap via new `gap_closure`, not just per-setting deltas)
-> **spec_quality** (new: how clearly did the paper specify its method? --
one bullet per `spec_quality.weak_fields` entry quoting the review's OWN
reason, plus `menu_deviations.unsupported_paper_fields`).

- `DiagnosisSummary`/`VsPaperSummary` (`src/infra/models/diagnosis.py`) gain
  a `section: Literal["reproduction","robustness","vs_cz","spec_quality"] |
  None` field (optional, so a pre-2026-08-18 persisted `diagnosis.json`
  still loads and renders, just ungrouped). New
  `ReplicationDiagnosisReport.spec_quality_summary: DiagnosisSummary` field.
- `summary.py`: `_build_sensitivity_summary` (was "to_hxz"'s whole card, now
  folded into `_build_robustness_summary` as one named case within it) adds
  a numeric guard -- per-switch contribution SHARES ("accounts for N% of
  the change") are only shown when the joint test actually confirms the
  total change is more than noise; otherwise "contribution share not shown
  (not statistically confirmed)". New `_build_robustness_summary` populates
  the robustness section independent of whether the HXZ factorial grid
  exists at all (previously the whole card vanished with no grid, even
  though `robustness_summary`/baseline `publication_decay` were unrelated
  and often still available). New `build_spec_quality_summary`.
  `_build_cz_summary` gains `_cz_level_and_gap_bullets` (level on each side
  + total gap + `gap_closure`'s explained-fraction/residual, reading
  `derived.tracks.*.vs_paper` for the first time), sorts per-setting
  bullets by \|t-stat\| descending instead of arbitrary config-key order,
  gates the cross-line HXZ-decay callout on the setting's OWN effect being
  itself statistically significant (previously fired even at t=0.56), and
  always states the no-bridge-track identification limit in its footnote.
- Frontend (`Step8Output.tsx`): `ReproductionCard` (new, badge lives here
  only) renders first; `sectionPriority`/`sectionEyebrow`/
  `sectionAccentClass` replace the old `summaryLinePriority`/`lineEyebrow`/
  `lineAccentClass` (grouped by `section`, not `comparison_line`); the
  duplicate page-level `overall: ...` badge removed.
- 3 tests updated (`TestSensitivitySummary`'s old
  `test_unavailable_shapley_yields_no_headline` replaced with 2 tests: one
  confirming robustness evidence still shows without the HXZ grid, one for
  truly-nothing-available); new `TestSpecQualitySummary` (3 tests); new
  `TestGapClosure`-adjacent bullets covered in `TestCzNarrative`; `diagnose()`
  wiring test extended to assert all 4 `section` values.

### step7: `gap_closure["to_cz"]` -- does the catalogued config diff to C&Z actually explain the gap? (2026-08-18)

The C&Z summary previously only listed per-switch config differences and
their isolated effects -- it never stated the TOTAL gap between our
baseline and `cz_actual_config`, nor whether the listed differences add up
to it. Added `bundle.build_gap_closure(derived, paired_tests)`:
`total_gap` (baseline `track_spread` minus `cz_actual_config`'s, same basis
`build_track_vs_paper` already resolved), `sum_of_switch_effects` (sum of
every AVAILABLE `paired_tests["to_cz"].per_switch.*.mean_diff`), `residual`
(`total_gap - sum_of_switch_effects`), and `explained_fraction`. Wired into
`build_evidence_bundle` as `gap_closure.to_cz`, citable via `evidence_keys`,
registered as a step8 tool (`GAP_CLOSURE_TOOL`). Harmonized (OAT) evidence
like `gap_decomposition` -- not additive, order-dependent, no interactions
identified -- so the residual is a lower bound on "unexplained", not a
precise figure. Without a C&Z bridge track (removed below) this residual is
the only evidence available for separating "explained by known settings"
from "not explained by anything catalogued". 5 new tests
(`TestGapClosure`, tests/test_replication_diagnosis.py).

### step7: `classify_overall` verdict now axed on significance first, not sign alone (2026-08-18)

The old 4-tag scheme (`close_replication`/`sign_agrees_magnitude_differs`/
`sign_mismatch`/`inconclusive`) put ANY sign disagreement under
`sign_mismatch`, whether or not either side's estimate was statistically
distinguishable from zero -- conflating "we found nothing (noise)" with "we
found a real, significant, opposite-sign effect", two very different
findings for a reader deciding whether to trust the replication. New 4-tag
scheme in `bundle.classify_overall`:

- `reproduced` -- same sign, and either both sides significant, or (when
  significance can't be assessed, e.g. an alpha-basis paper headline we
  have no alpha t-stat for) sign alone agrees.
- `not_reproduced` -- the paper's effect is significant but ours is not:
  our sign carries no information and must never be read as "reversed".
- `contradicted` -- both sides significant, opposite sign: a real,
  reportable conflict, not noise.
- `inconclusive` -- sign undeterminable, or neither side's significance
  can be assessed and sign disagrees.

A same-sign, both-significant pair with a magnitude ratio outside
`CLOSE_REPLICATION_RATIO_BAND` is now still `reproduced` (the ratio is
reported in the headline narrative, not folded into the badge) -- badge
categories no longer double as a magnitude-closeness signal.
`CLOSE_REPLICATION_RATIO_BAND` itself is unchanged and still used by the
unrelated `magnitude_gap` claim-type validator in step8.

Frontend `overallTagClass` (Step8Output.tsx) accepts both the new tags and
the old persisted ones (`close_replication`/`sign_agrees_magnitude_differs`/
`sign_mismatch`) so existing `diagnosis.json` files on disk keep rendering.
`src/evaluation/diagnostics.py::step7_diagnostics` flags `contradicted`/
`not_reproduced` instead of the removed `sign_mismatch`.

### Removed: C&Z signal bridge track mechanism, never run outside tests (2026-08-18)

The bridge track (`signal_input_ref: "cz_bridge[:factor_id]"`, `RunRecord.
is_bridge_track`, `src/infra/reference/cz_bridge.py`'s 3 hand-ported C&Z
signals, step6's `_run_bridge_track`, step7's `build_bridge_comparison`,
step8's `signal_reproducibility` claim type) was fully implemented but never
triggered by any default matrix, backend router, or frontend UI -- only by
tests. Deleted entirely rather than left dormant:

- `src/infra/reference/cz_bridge.py` removed.
- step6: `_run_bridge_track`, the `signal_input_ref` matrix-loading branch,
  and the bridge exclusion from `_finalize_batch`'s code-hash consistency
  check removed. `ExperimentSpec.signal_input_ref` field removed (`snapshot_ref`
  / data-vintage handling untouched).
- `RunRecord.is_bridge_track` field removed.
- step7 `bundle.py`: `build_bridge_comparison` and the `bridge_comparison`
  bundle section removed.
- step8: `signal_reproducibility` claim type, its `signal_fidelity` reason
  layer, its tool-catalog entry, its validator branch, and its render
  template removed. `ReasonLayer` is now `config_sensitivity`/
  `temporal_pattern` only.
- step3 `script_generator.py` / step5 `BacktestRunner.build_script`: the
  bridge-only `precomputed_signal_path`/`PRECOMPUTED_SIGNAL_PATH` parameter
  and template branch removed (no other caller existed).
- Frontend: `is_bridge_track` badges removed from Step5Output/Step6Output,
  the field dropped from `lib/evidence.ts`'s `RunRecord` type, and the
  bridge mention removed from `SessionDetailPage`'s evidence glossary.
- Tests deleted: `test_cz_bridge.py`, `test_bridge_track_e2e.py`,
  `test_bridge_track_wiring.py`, `test_script_generator_bridge_mode.py`;
  bridge-specific cases removed from `test_experiment_matrix.py`,
  `test_run_from_matrix.py`, `test_replication_diagnosis.py`,
  `test_attribution.py`, `test_experiment_plan_matrix_merge.py`.
- `RunRecord` has no `extra="forbid"` (pydantic default `ignore`), so
  existing `runs/evidence/` records carrying a persisted `is_bridge_track`
  key still load fine.

A real C&Z bridge track (isolating signal-formula differences from
convention differences) remains valuable future work, just not implemented
-- see `docs/step7-8.md`/`docs/cz-reference.md` for the still-relevant
identification-gap discussion.

### step7: Shapley attribution + OAT gap decomposition now prefer in-sample metrics (2026-08-18)

`attribution.py::compute_shapley_effects` and `__init__.py::ReplicationDiff.
diff_ablation` read `metrics.mean_return`/`metrics.t_stat` directly -- this
engine's FULL extended-history metrics, not the paper's own sample window.
Inconsistent with `ForestPlot`/`vs_paper` (`bundle.py`'s
`_in_sample_metrics`) and `PairedTestsTable`/`JointTestBanner`
(`_load_insample_series`), both already in-sample, in the exact same Step7
panel. Added `attribution._in_sample_mean_return`/`__init__._in_sample_t_stat`
helpers (prefer `metrics.by_sample_period.insamp.{mean_monthly_return,t_stat}`,
fall back to the top-level value when `by_sample_period` wasn't configured
for that run -- same preference `bundle.py`/`Step6Output.tsx` already
apply). 4 new tests added (`tests/test_attribution.py`,
`tests/test_replication_diagnosis.py`) locking in the in-sample preference
and the full-history fallback; 143 tests pass.

### step7: remove ConfigDiffHeatmap (unused in practice); fix TrackMetricsChart/TrackScatterChart to use in-sample metrics (2026-08-18)

**Removed** `ConfigDiffHeatmap`/`StageLegend` entirely from
`frontend/src/components/AttributionPanel.tsx` and its usage in
`Step7Output.tsx` (per user: the visualization form -- color legend +
click-to-reveal -- cost more to understand than the plain `config_diff`
data was worth; never proved useful in practice). `configDiff.pairs`/
`baseline_track` are still read (for baseline-track resolution and the
existing "compare against baseline" track checklist), only the heatmap
render is gone.

**Found and fixed while investigating**: `TrackMetricsChart`/
`TrackScatterChart` (the "mean_return vs t_stat -- is the difference real,
or noise?" panel) read `bundle.tracks[*].metrics` directly -- this engine's
FULL extended-history metrics (often decades past the paper's publication
year), NOT the paper's own sample window. Inconsistent with the
`ForestPlot` right above it on the same page (reads `derived.tracks[*].
vs_paper`, already in-sample-preferred via `bundle.py`'s
`_in_sample_metrics`) and with `Step6Output.tsx`'s own `displayMetrics()`
helper, which already does this same in-sample preference per run. Added
the same "prefer `metrics.by_sample_period.insamp` over the top-level
metrics key-by-key" merge in `Step7Output.tsx` before passing tracks to
either chart. `npx tsc --noEmit` / `npx oxlint` clean; verified live that
the heatmap section is gone and the scatter-chart section still renders.

### docs: thesis outline discussion draft (2026-08-18)

Added `docs/paper-outline.md` -- a Chinese-language discussion draft for the
master's thesis structure (English body). Locks the agreed premises (8
chapters, 3-5 factors, Q2 bridge track deferred to future work) and argues
for reframing the Introduction away from the "replication crisis" opening
toward **underdetermination**: the HXZ-vs-C&Z divergence is not an error by
either team but direct evidence that a paper does not uniquely determine its
own implementation. Under that frame the LLM is not a labor-saving tool but a
*controlled independent second implementer* operating under a leakage-proof
boundary. Also enumerates the table/figure inventory mapped to real
`comparison.json` / `.metrics.json` keys, factor-selection criteria, and open
items. No code change; the LaTeX skeleton under `paper/` is not yet generated.

Follow-up (same day): added §4 "Scope and Assumptions", verified against the
code rather than assumed -- registered data sources (`src/infra/data_layer/
sources.py`), the exact allowed-value config menu and clamping behavior
(`src/steps/step3_codegen/registry.py`), monthly-only portfolio returns,
portfolio-construction support matrix, and universe-filter gaps. Two items
that materially constrain the paper and were previously implicit: the
estimator menu contains only `portfolio_sort` (**no Fama-MacBeth**, so factors
whose headline result is a cross-sectional regression cannot be used), and
`data/snapshots/` is empty with no hardcoded date range, so the WRDS vintage
and sample period must be documented manually. Also frames the fixed menu as
an enabling assumption (it is what makes the implementation space enumerable)
and records the **two-sided bias**: the finite menu understates
underdetermination while single-draw LLM extraction overstates it.

Follow-up 2 (same day): added §5.1 -- a verification of five user-proposed
factors against `data/CZ code/SignalDoc.csv`. Two are hard rejects because
C&Z records `Test in OP = mv reg` (Richardson et al. 2005 `TotalAccruals`,
Fama-French `OperProf` -- which C&Z also attributes to FF 2006, not FF 2015),
and the engine has no Fama-MacBeth estimator; the other three are blocked by
unimplemented features (Piotroski `PS` needs a book-to-market quintile
condition = derived-column filter / within-group sort; `OScore` needs SIC
range exclusion plus an asymmetric long-70%/short-10% split; `FailureProbability`
needs `ltq`/`cheq` quarterly columns, `mktrf` as a *signal* input, and a daily
volatility path). Also records the strategic point that four of the five are
multi-input composite scores, which stress signal-formula extraction (Q2,
deferred to future work) rather than portfolio-configuration disagreement
(Q1/Q3, the main thread). Adds an engine-compatibility screen of SignalDoc
(23 of 331 signals pass) and a designed 4-factor slate contrasting
EW/no-NYSE-breakpoint factors against an already-VW+NYSE control, plus a
warning that using HXZ's published `portf_*.csv` returns would downgrade the
identification level to `observational`.

Follow-up 3 (same day): **self-correction** -- an earlier claim in this same
discussion that SIC-range universe filters (e.g. exclude SIC 6000-6999) were
unimplemented was WRONG. `BacktestExecutor._apply_filter_op`
(`src/infra/backtest_engine/__init__.py`) already implements `FilterOp.between`
/ `not_between` via `series.between(lo, hi)`, and CRSP's `siccd` is a plain
`int64` column with no encoding issues (verified against the local raw CSV).
So SIC-range exclusion needs zero engine changes -- only a correctly authored
`UniverseFilterSpec` (`op="not_between", value=[6000, 6999]`). This unblocks
both `GP` (Novy-Marx 2013) and `OperProfRD` (Ball et al. 2016), whose only
prior objection was the (nonexistent) SIC-filter gap. Re-verified all
Compustat field requirements directly against `src/infra/data_layer/
sources.py`'s registered `comp_funda` columns AND the raw local
`COMPUSTAT_FUNDAMENTALS_ANNUAL.csv` header (not assumed) for six
ambiguity-documented candidates (`OPLeverage`, `GP`, `OperProfRD`,
`PctTotAcc`, `OScore`, `PS`); found `PctTotAcc`/`PS`/`OScore` need new column
registrations (`ni`, `prstkcc`, `sstk`, `dvt`, `oancf`, `fincf`, `ivncf`,
`txt`) that ARE present in the raw file (mechanical, low-risk) but not yet in
`sources.py`'s `physical_columns`. `OScore` additionally needs an
asymmetric-quantile split (long low 70% / short high 10%) that
`breakpoint_quantiles` cannot express -- the one remaining candidate that
would touch core sort logic. Recommends `GP` as the single-factor thesis
choice (zero engine/field changes, and C&Z's own notes document a direct
paper-vs-best-implementation contradiction on breakpoint choice), with
`OPLeverage` as a zero-effort fallback and `OScore` as a documented
alternative if the asymmetric-split engine work is worth it.

### frontend: ConfigDiffHeatmap -- add a visible color legend + click-to-reveal detail (2026-08-18)

User couldn't tell what the heatmap's colors meant (no on-screen legend --
the stage->color mapping only existed in this source file's comments) and
the native `title` attribute hover tooltip was unreliable (browser-
dependent delay, easy to miss, doesn't work on touch). Added a `StageLegend`
row above the table (color swatch + plain-language label per pipeline
stage: signal input / portfolio / universe / sample / estimator /
unclassified) and made each cell clickable: clicking pins a persistent
`track · key (stage): baseline_value → track_value` line below the table
(kept the `title` attribute too, for browsers where hover does work).
Verified live: clicking a purple cell in a real session's heatmap now shows
`standardized_hxz · breakpoint_source (portfolio ...): full_sample → nyse`.
`npx tsc --noEmit` / `npx oxlint` clean.

### step2: three fixes from user discussion -- holding_period unit, editable high-impact fields, dropdown dedup (2026-08-18)

1. **`timing.holding_period` is now explicitly documented as ALWAYS in
   months** (`src/infra/models/method_spec.py` docstring +
   `docs/methodspec-v2-plan.md`), regardless of `rebalance_frequency`'s
   unit. Root cause found via a real session: the paper said "held for 1
   year", the extractor wrote `holding_period.value=1` (matching the OLD,
   now-removed "same unit as rebalance_frequency" convention), and
   `registry.build_config` passes it straight through as
   `holding_period_months` with no conversion -- so the backtest held
   positions for 1 MONTH instead of 12, which also explains far fewer
   `N months`/skewed alpha-t-stats than expected. Fixed the convention at
   the extraction side (`prompts/extractor/method_spec_extractor.md` new
   §1.4b: always convert to months) and the review side
   (`prompts/review_gate/llm_review.md`'s cross-field-consistency check)
   rather than changing `registry.py`, since `registry.py` already treats
   the value as months everywhere else. Does NOT retroactively fix any
   already-extracted spec on disk with the old convention -- re-run Step2
   review/resolve for those.
2. **Every high-impact field is now human-editable in Step2**, not just
   `needs_human_confirmation` ones -- `canPatch` in
   `frontend/src/pages/SessionDetailPage.tsx` no longer gates on
   `disposition`, only excludes `missing_mapping` findings (which need a
   `data.fields` fix + re-extract, not a value patch). Lets a human
   override a field the paper stated clearly (e.g. `portfolio.weighting`)
   without first forcing its evidence status down to trigger a block.
3. **Deduplicated the value-correction dropdown's "other" option**: enum
   fields (e.g. `weighting`) already list their own `other` member via
   `allowed_values`; the separate hardcoded "Other (type my own)" free-text
   escape hatch is now only added when `allowedValues` doesn't already
   include `"other"` (still useful for non-exhaustive suggestion lists like
   `source_column`).

`npx tsc --noEmit` / `npx oxlint` clean; verified live by injecting a real
`.resolved.json` into `localStorage` and confirming `portfolio.weighting`
(disposition `auto_approve`) is now editable with a deduped
`["vw", "ew", "other"]` dropdown.

### frontend: Step2's resolved-spec panel rendered blank -- shape mismatch, not a persistence bug (2026-08-18)

`GET /api/methodspecs/resolved/{factor_id}` (and `resolveMutation`'s
`sessionApi.getResolvedMethodSpec`) returns a `ResolvedMethodSpec` wrapper
(`{paper: MethodSpec, review: MethodReview, resolution: ...}` -- see
`backend/routers/methodspecs.py`'s `resolve()`), which was being passed
directly as `spec` to `MethodSpecBoard` in
`frontend/src/pages/SessionDetailPage.tsx`. `MethodSpecBoard` renders a
FLAT `MethodSpec` (reads `spec.signal`/`spec.portfolio`/`spec.reported_
results`/etc. at the top level) -- none of those exist on the wrapper, so
every section silently rendered empty instead of crashing. Fixed by
passing `state.resolved.paper` (the actual `MethodSpec`) to
`MethodSpecBoard` instead of the wrapper; the wrapper itself is still
correctly used as-is for `body.spec` in the step3/4/5 request-template
auto-fill (those backend endpoints validate `ResolvedMethodSpec`, not a
flat spec, via `backend/spec_parsing.py`'s `parse_spec`) -- only the
display call site was wrong. Verified live by injecting a real persisted
`.resolved.json` artifact into `localStorage` and confirming the board
now renders the Signal/Formula/factor_id sections instead of blank.
`npx tsc --noEmit` / `npx oxlint` clean.

### frontend: fix Step1/Step2 output silently disappearing after a localStorage quota failure (2026-08-18 follow-up)

Root-caused why output still didn't show even after the previous
try/catch fix (confirmed live: `QuotaExceededError` from the browser
console). `setMethodSpecWorkflowState`'s old "read current disk state,
merge patch, write" pattern meant that once a write started failing
(quota exceeded), every SUBSEQUENT `patch()` call re-read the same stale/
empty disk copy as its merge base -- so the second of two back-to-back
`patch()` calls in the Step1 extraction-completion effect
(`MethodSpecWorkflowPanel` in `frontend/src/pages/SessionDetailPage.tsx`)
wiped out the `rawSpec`/`paperText` the first call had just set, even
though nothing crashed. Fixed properly: `patch()` now merges against its
own in-memory `state` via a functional `setState` update (independent of
whether persistence succeeds), and persistence is a separate one-shot
`persistMethodSpecWorkflowState(sessionId, fullState)` in
`frontend/src/lib/methodSpecStore.ts` (no more disk-read-merge). Also
added automatic eviction: on a quota failure, it now drops every OTHER
session's cached workflow state (still fully recoverable from the backend
session/methodspecs artifacts) and retries once before giving up and
logging a warning. `npx tsc --noEmit` and `npx oxlint` on both files clean.

### frontend: fix white-screen crash after Step1 extraction + add a top-level ErrorBoundary (2026-08-18)

Root-caused a "blank page after importing a paper" report: `setMethodSpecWorkflowState`
(`frontend/src/lib/methodSpecStore.ts`) called `localStorage.setItem` with no
error handling, while its own `getMethodSpecWorkflowState` already guarded
`localStorage.getItem` with try/catch -- an inconsistency. Every session's
workflow state (raw spec, full paper text ~100-200KB, review rounds) is
persisted under its own never-evicted key, so this key can eventually exceed
the browser's per-origin localStorage quota; `setItem` then throws
synchronously inside a React effect/mutation callback (right after Step1's
extraction job completes, in `MethodSpecWorkflowPanel`'s `patch()` calls),
and with no error boundary anywhere in the app, React unmounted the entire
tree to a blank page. Fixed both sides: `setMethodSpecWorkflowState` now
catches the write failure (logs a warning, state still updates in-memory for
this render, just isn't persisted) instead of throwing; added
`frontend/src/components/ErrorBoundary.tsx` wrapping every top-level route
in `App.tsx` as a last-line-of-defense so any other uncaught render error
shows a message + "Try again" instead of an unexplained blank screen.
`npx tsc --noEmit` and `npx oxlint` on the changed files both clean.

### step2/step1: catch `reported_results.primary_metric_id` pointing at a different weighting than `portfolio.weighting` (2026-08-18)

`ReportedMetric` (`src/infra/models/method_spec.py`) gains an optional
`weighting: WeightingScheme | None` field (ew/vw, `None` = paper doesn't
distinguish or extractor couldn't tell -- never guessed). New
`review.py::_primary_metric_weighting_finding` fires a `kind="inconsistent"`
/ `NEEDS_HUMAN_CONFIRMATION` finding when the primary metric's tagged
weighting disagrees with `portfolio.weighting` -- otherwise Step7's
`build_track_vs_paper` silently compares our vw (or ew) backtest track
against the paper's OTHER weighting column, producing a fake replication
gap. Extractor prompt (`prompts/extractor/method_spec_extractor.md` §1.8)
now instructs tagging `weighting` per metric and capturing BOTH EW/VW
headline variants when the paper reports both, rather than discarding one;
`prompts/review_gate/llm_review.md`'s cross-field-consistency section
mentions the same check. Tests added to `tests/test_step2_reviewer.py`
(mismatch flagged, match not flagged, unset never guessed).

### step2: bump `MAX_REVIEW_ROUNDS` from 3 to 4 (2026-08-18)

`src/steps/step2_reviewer/spec_build.py`'s bounded review loop now allows
one extra validate+LLM-review round before giving up (max 4 full-paper-text
LLM calls instead of 3). No other loop-exit logic changed.

### frontend: restyle Step8Output for visual clarity, no behavior/data change (2026-08-18)

Pure UI polish on `frontend/src/components/steps/Step8Output.tsx` (no schema
or backend change): summary cards now use the shared `Card`/`CardHeader`/
`CardTitle`/`CardContent` components instead of plain bordered `<div>`s, with
a colored left-border accent + small-caps eyebrow label distinguishing the
core `to_cz` comparison from the supporting `to_hxz` one and the vs-paper
card; `overall_tag`/per-card verdict badges are color-coded (emerald for
`close_replication`, destructive-red for `sign_mismatch`, amber for
`sign_agrees_magnitude_differs`) instead of one flat outline badge; detail
bullets use a subtler dot marker with a `Separator` before the footnote
instead of a plain `<ul>`; the top-level Summary `<details>` wrapper (never
useful now that Findings is gone -- Summary is the only content) was
removed so the cards are always visible without an extra click; the
rejected-claims audit box got a light destructive tint and a visible count
in its `<summary>`. `npx tsc --noEmit` and `npx oxlint` on the file both
clean.

### step8: remove the entire "## Findings" per-analysis_stage claims listing; only the Summary section is rendered now (docs/step7-8.md Part XV §15.3) (2026-08-18)

Follow-up to the previous round (which only folded `per_switch`/`joint_gate`
claim evidence into Summary's `details`): user pointed out `## Findings`
still rendered `vs_paper`/`auxiliary`/unstaged claims as their own
collapsible sections too ("not only two stage sections, all sections except
summary"). Since `SummaryCard`/`VsPaperCard` are built directly from the
bundle (Part XI), not from claims, Findings never carried information
Summary structurally couldn't -- so it's dropped entirely, not just two of
its five stages.

`src/steps/step8_diagnosis/render.py`: `render_markdown` no longer emits
`## Findings` at all; removed the now-dead `_STAGE_ORDER`/`_STAGE_HEADINGS`/
`_CLAIM_TYPE_HEADINGS`/`_FINDINGS_HIDDEN_STAGES` constants that only served
that loop. `frontend/src/components/steps/Step8Output.tsx`: removed the
per-stage `<details>` blocks, the `unstaged`/"Other" block, the now-unused
`ClaimCard` component, and the `DiagnosisClaim`/`STAGE_ORDER`/
`STAGE_LABELS`/`LINE_LABELS`/`lineLabel` symbols that only fed it. The page
now shows exactly two things: **Summary** (unchanged) and **Rejected claims
(audit)** (kept -- a validation-failure audit trail, not a duplicate of
already-accepted evidence, out of scope for this request).

`report.claims`/`report_to_jsonable`'s `rendered_sentence` field are
unchanged -- `diagnosis.json` (the API response) still carries the full
claims list with each one's deterministic sentence, for citation/audit by
other consumers; only the UI/markdown rendering of it is gone.
`deterministic_sentence`/`_RELATION_TEMPLATES` (the claim-to-sentence
generator) are unchanged and still used by `report_to_jsonable` -- tests
that previously asserted claim sentences via `render_markdown`
(`test_figures_come_from_the_bundle_and_sentence_from_the_relation`,
`test_part_viii_claim_types_render_switch_and_line_into_the_sentence`) now
call `deterministic_sentence(claim, evidence)` directly instead.

`tests/test_replication_diagnosis.py` 122 passed; broader diagnosis/step8/
replication_diff/attribution suite 156 passed, zero regressions; frontend
`npx tsc --noEmit` and `npx oxlint` on the edited file both clean.

### step8: translate raw config VALUES (not just the setting name) into plain language, and fold per-switch/joint-gate claim evidence into the summary prose instead of a separate section (docs/step7-8.md Part XV) (2026-08-18)

Two follow-up requests on the same narrative:

1. `CONFIG_KEY_LABELS` already explains what a setting IS in plain English
   (e.g. "whether bigger companies count for more..."), but the actual
   VALUE on each side of the comparison was still the raw menu token
   (`"vw"`/`"ew"`) via `_readable_value`'s `str(value)` fallback. New
   `_VALUE_LABELS: dict[key, dict[raw_value, plain_label]]` in
   `src/steps/step8_diagnosis/summary.py` translates menu-governed keys'
   actual values (`weighting_rule`/`breakpoint_source`/`missing_action`/
   `return_combination_type`, menu per `src/steps/step3_codegen/
   registry.py`'s `STANDARD`) into plain terms (`"vw"` -> "value-weighted",
   `"ew"` -> "equal-weighted", etc). New `_quantile_label` for
   `breakpoint_quantiles` (a raw group count -> e.g. "10 groups
   (deciles)") and month-unit formatting for `accounting_lag_months`/
   `formation_lag_months` (`6` -> "6 months"). Falls back to `str(value)`
   only for keys/values not yet in the table (never crashes).

2. `DiagnosisSummary.per_switch_summary`/`joint_supported`/`dominant_
   switches` (LLM-claim-derived, Part IX) were rendered in `render.py`/
   `Step8Output.tsx` as their own separate lines/badges alongside the
   bundle-derived `headline`/`details` (Part XI+), duplicating similar
   information in two places. New `_fold_claim_evidence_into_details` in
   `summary.py` appends these as extra prose bullets onto the SAME
   `details` list (e.g. "LLM-reviewed per-setting significance: ...",
   "LLM-reviewed joint-significance conclusion: supported by the data.",
   "LLM flagged as dominant driver(s): ..."), one bullet per non-empty
   field. The three `DiagnosisSummary` fields themselves are unchanged
   (still populated, still returned by the API, still usable for
   evidence_keys/citation) -- only the separate rendering is removed:
   `render.py`'s `_summary_section` no longer emits the old "Per-switch
   significance:"/"Joint test:"/"Dominant switches:" markdown lines, and
   `Step8Output.tsx`'s `SummaryCard` drops the corresponding badge/
   paragraphs.

Updated `test_findings_are_grouped_by_analysis_stage_and_summary_section_
is_rendered` to assert the new folded-in prose instead of the old separate
lines. `tests/test_replication_diagnosis.py` 121 passed; broader
diagnosis/step8/replication_diff/attribution suite 155 passed, zero
regressions; frontend `npx tsc --noEmit` and `npx oxlint` on the edited
file both clean.

### step7/step8: universe-filter descriptions now come from the MethodSpec's own extracted text, not a hardcoded lookup table (docs/step7-8.md Part XIII §13.5) (2026-08-18)

User pushback on the previous round's `_KNOWN_FILTER_DESCRIPTIONS` table: a
hardcoded per-`(field, op, value)` lookup can never enumerate every future
paper's own universe-filter choices. Fix: the paper's own natural-language
universe description is already extracted at Step1 into `spec.paper.
universe.description` (a `SourcedValue[str]`, with its own paper-quote
evidence) -- this generalizes to any paper automatically, no lookup table
needed. New `build_universe_description(spec)` in `src/steps/step7_
replication_diff/bundle.py` (same pattern as `build_spec_quality`/
`build_menu_deviations`), wired into `build_evidence_bundle` as a new
top-level `universe_description` bundle key; `src/steps/step5_backtest_
runner/__init__.py` already calls `build_evidence_bundle(..., spec=spec,
...)` with a real resolved spec, so this populates automatically in the
real pipeline (does NOT depend on the separate, still-unfixed "`resolved_
spec` never passed to step8's `diagnose()`" gap -- that only affects the
opt_in `field_evidence_detail` tool).

`summary.py`'s new `_universe_filters_clause(bundle, detail, ours)`: OUR
side prefers `bundle["universe_description"]["text"]` (quotes the paper
verbatim: 'the paper describes its universe as: "..."'); C&Z's side is now
a **fixed constant** `_CZ_HOUSE_UNIVERSE_DESCRIPTION` instead of a lookup
too -- it never varies per paper (`cz_profile_to_config_override` always
sets the same `shrcd`/`exchcd` filter for every C&Z factor), so a static
description is the correct design, not something that needs to scale.
`_KNOWN_FILTER_DESCRIPTIONS`/`_readable_filter` from the previous round are
now an explicitly-documented FALLBACK ONLY, used when no resolved spec was
supplied to `build_evidence_bundle`.

Verified against the real extracted AssetGrowth paper text (not invented):
"the paper describes its universe as: \"We use all NYSE, Amex, and NASDAQ
nonfinancial firms (excluding firms with four-digit SIC codes between 6000
and 6999) listed on the CRSP monthly stock return files and the Compustat
annual industrial files\"". New `TestUniverseDescription` (bundle-level,
2 cases) + `test_universe_filters_prefers_the_papers_own_extracted_
description` (summary-level, confirms the paper's own text wins over the
fallback decoder while C&Z's side stays the fixed description either way).
`tests/test_replication_diagnosis.py` 121 passed; broader diagnosis/step8/
replication_diff/attribution suite 155 passed, zero regressions.

### step8: plain-language explanations for a total layperson + a real grammar bug fix (docs/step7-8.md Part XIII) (2026-08-18)

User feedback: even after Part XI's readable labels, someone with no
finance background still can't tell what "lag" means or what `siccd not
between 6000-6999` means. `CONFIG_KEY_LABELS` rewritten to explain what a
setting DOES and WHY it exists, not just restate the technical name in
English -- e.g. `formation_lag_months` was "the lag between signal
formation and portfolio start", now "how long after picking which stocks go
in a portfolio before that portfolio actually starts trading (a safety
delay so the strategy can't accidentally use information before it was
realistically available)". New `_KNOWN_FILTER_DESCRIPTIONS`: an exact
`(field, op, value)` lookup table translating the small, fixed set of
universe-filter code combinations this codebase actually produces into full
sentences (`siccd not_between (6000, 6999)` -> "excludes financial
companies such as banks, insurers, and real estate firms"; `shrcd in (10,
11, 12)` -> "includes only ordinary common shares"; `exchcd in (1, 2, 3)`
-> "includes only stocks listed on the NYSE, AMEX, or Nasdaq exchanges") --
deliberately NOT a general SIC/CRSP-code decoder, just this project's known
combinations; anything unmatched falls back to a generic-but-still-readable
`_readable_field`/`_OP_LABELS` phrasing rather than a raw code.

Also fixed a real grammar bug caught while verifying against the real
bundle: `universe_filters`' readable value is already a full verb clause
("excludes financial companies..."), so the generic "we use {value}, C&Z
uses {value}" template produced broken English ("we use excludes financial
companies..."). New `_CLAUSE_VALUED_KEYS`/`_value_clause` special-cases
clause-valued keys to "our version {clause}"/"C&Z's version {clause}"
instead; multiple filter descriptions now join with "and" instead of ";" so
they read as one sentence. Also replaced `str.capitalize()` (which
lowercases the rest of the string, risking mangling a future embedded
acronym like "NYSE") with a new `_sentence_case` helper that only
uppercases the first character.

Verified against the real AssetGrowth bundle -- now reads: "Which stocks
are allowed into consideration at all: our version excludes financial
companies such as banks, insurers, and real estate firms (identified by
SIC industry codes 6000-6999), C&Z's version includes only ordinary common
shares (not REITs, ADRs, or other special share types) and includes only
stocks listed on the NYSE, AMEX, or Nasdaq exchanges -- ...". 5 test
assertions updated for the new wording. `tests/test_replication_
diagnosis.py` 118 passed; broader suite 152 passed, zero regressions.

### frontend: fixed a step8 page crash on old persisted `diagnosis.json` (2026-08-18)

Old sessions' `diagnosis.json` (generated before Part XII's schema change)
have `summary` entries in the OLD shape (`narrative`/`caveats`, no
`details`/`headline`/`footnote`). `Step8Output.tsx`'s `SummaryCard`/
`VsPaperCard` read `summary.details.length` unconditionally, so opening an
old session's step8 page crashed the whole page with `Cannot read
properties of undefined (reading 'length')`. Fixed with `summary.details ??
[]` defaults in both components -- never assume a persisted artifact
matches the CURRENT schema version. `npx tsc --noEmit`/`npx oxlint` clean.

### step8: `DiagnosisSummary`/`VsPaperSummary` restructured into `headline`/`details`/`footnote` (docs/step7-8.md Part XII) (2026-08-18)

User feedback on Part XI: the single `narrative` string read as one long
run-on paragraph with the conclusion buried at the end, and no separate "vs.
C&Z"/"vs. HXZ" card title should be needed if the headline names its own
comparison target. Schema change: `DiagnosisSummary.narrative`/`.caveats`
removed, replaced with `headline: str` (one-sentence bottom line, always
shown first, self-descriptive -- "Compared with C&Z's independent
replication of this paper, ..."), `details: list[str]` (one bullet per
supporting point, decreasing importance, never merged into one paragraph),
`footnote: str` (de-emphasized technical caveat, e.g. joint-test
availability). `per_switch_summary`/`joint_supported`/`dominant_switches`
kept unchanged (structured data for frontend badges, not prose duplicating
`details`). New `VsPaperSummary` model (`headline`/`details`/`footnote`,
same layout) replaces `ReplicationDiagnosisReport.vs_paper_narrative: str`
as `vs_paper_summary: VsPaperSummary`.

`summary.py`: `_build_cz_narrative`/`_build_sensitivity_narrative` ->
`_build_cz_summary`/`_build_sensitivity_summary`, now returning `(headline,
details, footnote)` tuples instead of one string; `build_vs_paper_narrative`
-> `build_vs_paper_summary`, returning `VsPaperSummary`. Also fixed the
readability gap flagged in the same round: `formation_lag_months`/
`cz_actual_config`-style raw identifiers no longer appear anywhere in
reader-facing text -- new `CONFIG_KEY_LABELS`/`TRACK_LABELS` maps (every key/
track the narrative can mention -> a human-readable phrase, with a generic
underscore->space fallback for anything unlisted) and a `_readable_value`
formatter specifically for `universe_filters` (was an unreadable Python
list-of-dicts repr, now renders as e.g. "siccd not between 6000-6999").

Verified against the real AssetGrowth bundle
(`runs/backtest_scripts/results/099f6e1136bd316c/comparison.json`): e.g.
`to_cz.headline` = "Compared with C&Z's independent replication of this
paper, the only differences are explained by paper ambiguity or C&Z's own
conventions, and none has a statistically significant effect." --
`to_cz.details` lists the two house-convention divergences
(`formation_lag_months`/`universe_filters`) each with their own effect size/
significance and the HXZ-line cross-callout, `to_cz.footnote` notes the
joint test is unavailable (only one setting has paired-test evidence).

`render.py::_summary_section` rewritten for the inverted-pyramid layout (bold
headline first, `details` as a bullet list, `footnote` italicized last) --
no more "### vs. X" line-label heading. `frontend/src/components/steps/
Step8Output.tsx`: `SummaryCard`/new `VsPaperCard` render the same layout;
`Step8Output.tsx`'s own `LINE_LABELS` map is now only used for `ClaimCard`
badges (a claim still names a specific track/line), not for summary titles.

Updated ~10 existing test assertions across `TestCzNarrative` ->
`TestCzNarrative` (kept name, updated bodies), `TestSensitivityNarrative` ->
`TestSensitivitySummary`, `TestVsPaperNarrative` -> `TestVsPaperSummary` for
the new field names; added `test_joint_test_not_significant_is_reflected_in_
the_headline` (the "lacks joint support" caveat that used to live in a
separate `.caveats` list now lives in the headline itself, phrased as
"though a joint test does not confirm this"). `tests/test_replication_
diagnosis.py` 118 passed; broader diagnosis/step8/replication_diff/
attribution suite 152 passed, zero regressions. Frontend `npx tsc --noEmit`/
`npx tsc -b`/`npx oxlint` all clean.

### step8: narrative text no longer exposes raw config-key/track-name identifiers (docs/step7-8.md Part XI readability follow-up) (2026-08-18)

User feedback: `formation_lag_months`/`cz_actual_config`-style raw
identifiers showing up in the narrative aren't readable. New
`src/steps/step8_diagnosis/summary.py::CONFIG_KEY_LABELS`/`TRACK_LABELS`
(every config key and track name Part XI's narrative can mention now maps to
a human-readable phrase, e.g. `formation_lag_months` -> "the lag between
signal formation and portfolio start", `cz_actual_config` -> "C&Z's own
independent replication"; `_readable_key`/`_readable_track` fall back to a
generic underscore->space humanization for anything not yet listed, so an
unlisted key degrades gracefully instead of crashing) and a new
`_readable_value` for `universe_filters` specifically (was printing as an
unreadable Python list-of-dicts repr, e.g. `[{'field': 'siccd', 'op':
'not_between', 'value': [6000, 6999]}]`; now renders as "siccd not between
6000-6999"). Updated `_build_cz_narrative`/`_build_sensitivity_narrative`/
`build_vs_paper_narrative` to use these everywhere a raw key/track name
previously appeared in backticks. Verified against the real AssetGrowth
bundle: the narrative now reads e.g. "On the lag between signal formation
and portfolio start (we use 0, C&Z uses 1), ..." instead of "On
`formation_lag_months` (our value 0 vs C&Z's 1), ...". 2 existing test
assertions updated to check for the readable phrase (and the ABSENCE of the
raw identifier) instead of the raw key. `tests/test_replication_
diagnosis.py` 117 passed; broader suite 151 passed, zero regressions.

### frontend: hide the raw request-JSON textarea for step8, bump Step8Output prose to `text-sm` (2026-08-18)

`SessionDetailPage.tsx`'s step3-8 request editor now also excludes step 8
(`step !== 8` added alongside the existing 3/4/5/6/7 exclusions) -- step 8's
request body (`expected_revision`/`llm_provider`/`llm_model`) is already
fully auto-managed (the sidebar's single provider/model picker + the
existing auto-revision-fill effect), so showing/editing it as raw JSON was
unnecessary clutter; `requestText` state itself is untouched (still
populated by the existing auto-fill effect), so the "Run" button's
`JSON.parse(requestText)` flow is unaffected. `Step8Output.tsx`: the
narrative/rendered-sentence paragraphs (the actual read content) bumped from
`text-xs` to `text-sm`; badges/metadata stay `text-xs` to keep the visual
hierarchy. `npx tsc --noEmit`/`npx tsc -b`/`npx oxlint` all clean.

### step8: redesigned deterministic summary as a cross-referenced narrative, `to_cz`-first (docs/step7-8.md Part XI) (2026-08-17)

User feedback on Part IX's layered summary: didn't like the "①→②/①→③"
labelling, and the content felt shallow. Three changes: (1) dropped the
arrow-circled-number label prefix everywhere (`render.py`/
`Step7Output.tsx`/`Step8Output.tsx`'s line-label maps now show only
`"vs. HXZ standardized config"`/`"vs. C&Z actual config"`; claim sentence
templates changed "On comparison line {line}" -> "On the {line} line" to
avoid "line vs. line" phrasing); (2) reader-facing copy says "choice"
instead of "switch" (internal field/variable names unchanged -- too broad a
rename for too little benefit); (3) **reordered priority to match AGENTS.md's
actual research question** -- inter-implementer agreement (agent vs C&Z,
`to_cz`) is the core question, HXZ standardization (`to_hxz`) is supporting
sensitivity context, not a peer comparison; `to_cz` now always sorts first
(`_summary_line_priority`/frontend `summaryLinePriority`) with proportionally
more analytical depth.

Core new piece: `DiagnosisSummary.narrative` (per line) +
`ReplicationDiagnosisReport.vs_paper_narrative` (report-level), built by new
functions in `src/steps/step8_diagnosis/summary.py` -- **generated directly
from `bundle`, independent of whatever claims the LLM produced** (module
docstring updated: this is MORE deterministic than the claim-based fields,
not less, since it's pure step7 arithmetic with zero LLM involvement).
`_build_cz_narrative` (the primary narrative): for every config key that
differs between baseline and `cz_actual_config`, classifies WHY via
`_divergence_reason` into `house_convention` (the key is one of
`CZ_HOUSE_CONVENTION_KEYS` -- `weighting_rule`/`breakpoint_quantiles`/
`breakpoint_source`/`accounting_lag_months`/`missing_action`/
`formation_lag_months`/`universe_filters`, the set `cz_profile_to_config_
override` unconditionally overrides for every C&Z factor, a structural fact
independent of any one paper) / `paper_ambiguous` (flagged weak in
`spec_quality`) / `unresolved` (neither -- an honest fallback, deliberately
NOT claiming to know it's an implementation error), plus that key's own
paired-test effect size/significance and a cross-line callout (does the same
choice's single-choice track on the `to_hxz` line survive post-publication
decay, echoing Part VII example 6), closing with an explicit
reproducibility-framing sentence. `_build_sensitivity_narrative` (supporting,
for `to_hxz`): total gap + joint-test gate + per-choice Shapley share/
significance, explicitly labelled "sensitivity context, not itself the
reproducibility question" to avoid it reading as equally important.
`build_vs_paper_narrative`: baseline-vs-paper sign/magnitude comparison plus
the honest caveat that config fields the paper never specified at all
(`menu_deviations.clamped_by_track`, filtered to `paper_value in (None,
"unspecified")`) may account for part of any magnitude gap -- verified
against the real AssetGrowth bundle: `original_method` itself has 2 such
fields (`accounting_lag_months`/`missing_action`), so the 2.11x magnitude
ratio can't be entirely attributed to implementation choices.

Verified against the REAL `runs/backtest_scripts/results/099f6e1136bd316c/
comparison.json` (not synthetic) -- and this run surfaced a genuine finding
neither of us had manually checked: `formation_lag_months` (0 vs 1) is ALSO a
`house_convention` divergence between `original_method` and
`cz_actual_config`, alongside the already-discussed `universe_filters`.

New tests: `TestCzNarrative` (6), `TestSensitivityNarrative` (2),
`TestVsPaperNarrative` (3), plus 2 pre-existing tests updated for an
intentional behavior change (line summaries now surface whenever `bundle`
has real evidence for that line, not only when the LLM happened to produce a
matching claim -- `to_cz` in particular must never go missing just because
the LLM said nothing about it, since it's the core research question).
`tests/test_replication_diagnosis.py` 117 passed; broader diagnosis/step8/
replication_diff/attribution suite 151 passed, zero regressions. Frontend
`Step8Output.tsx`: `SummaryCard` now shows `narrative` as its primary content
(sorted `to_cz` first) plus a new "Vs. paper" card for `vs_paper_narrative`;
`npx tsc --noEmit`/`npx tsc -b`/`npx oxlint` all clean. Known limitations
(documented in docs/step7-8.md Part XI §11.4): the config-key-to-MethodSpec-
field matching for `paper_ambiguous` is a substring heuristic, not an exact
mapping; `CZ_HOUSE_CONVENTION_KEYS` is a hardcoded constant that must be
kept in sync by hand if `cz_profile_to_config_override`'s own override set
ever changes; the frontend renders `narrative` as plain text with no extra
formatting yet.

### frontend: Q8 `ForestPlot` + `ConfigDiffHeatmap` (docs/step7-8.md Q8) (2026-08-17)

Two of Q8's four visualization candidates implemented (the two flagged as
lowest-effort/no-new-computation): `AttributionPanel.tsx::ForestPlot` (one
row per track, its own `t_stat` as a point, HXZ's 3 tiered thresholds
(`1.96/2.78/3.39`, Q7) as +/- dashed reference lines, sorted by `|t_stat|`
descending -- reads only `derived.tracks[*].vs_paper.track_raw_t_stat`/
`track_significance_tier`, zero new backend calls) and
`AttributionPanel.tsx::ConfigDiffHeatmap` (track x changed-config-key matrix,
cell color keyed to that key's own pipeline `stage` via `STAGE_COLORS`, hover
title shows `baseline_value -> track_value` -- a direct re-render of
`config_diff.pairs`, no new computation). Both wired into `Step7Output.tsx`.
NOT done this round (documented in docs/step7-8.md Q8 with reasons): the
waterfall chart (Shapley table already covers this need) and the paired-diff
time-series chart (would require `Step7Output` to gain a `sessionId` prop and
a new `fetchReturnSeries`-based query per track -- a structural change bigger
than the other two, deferred as its own task). Verified: `npx tsc --noEmit`,
`npx tsc -b`, `npx oxlint` all clean on the new/changed files.

### step7: implemented Q5's `t_channel_decomposition` (docs/step7-8.md Q5) (2026-08-17)

New `build_t_channel_decomposition(tracks, baseline)` in
`src/steps/step7_replication_diff/bundle.py`, wired into
`build_evidence_bundle` as a new top-level `t_channel_decomposition` key
(baseline-vs-each, same organization as `build_config_diff` -- NOT grouped by
switch/comparison-line like Shapley). Exact log-identity decomposition of
each track's t-stat vs baseline's: `log(t_track) - log(t_baseline) =
[log(mean_return_track) - log(mean_return_baseline)] - [log(sigma_track) -
log(sigma_baseline)] + 0.5*[log(n_months_track) - log(n_months_baseline)]`,
with `sigma` back-solved from `t = mean_return / (sigma / sqrt(n_months))`
(no new persisted field needed). Non-degenerate output carries `log_t_ratio`/
`channels.{mean_return,volatility,sample_size}` (sum exactly equals
`log_t_ratio`, no residual)/`channel_sum_check`/`implied_sigma`. Degenerates
per-track (to `t_stat_abs_delta` = `|t_track| - |t_baseline|` + a `reason`,
never a fabricated channel split) more precisely than Q5's original "mu<0"
framing: requires `mean_return` STRICTLY POSITIVE on BOTH baseline and track
(not merely same-signed -- an individual `log(negative)` is undefined even
though the ratio of two negatives would be positive), plus non-null/non-zero
`t_stat`, positive `n_months`, and sign-consistency between `t_stat` and
`mean_return` (an inconsistency there would back-solve a negative implied
volatility). New `TestTChannelDecomposition` (7 cases: exact-identity sum
check, a pure-n_months-change case isolating the sample_size channel to
`0.5*log(2)` with the other two channels ~0, negative-baseline-mean_return
degenerate case, opposite-signed-track degenerate case, missing-metrics
degenerate case, no-tracks unavailable case, evidence-bundle wiring).
`tests/test_replication_diagnosis.py` 106 passed, zero regressions. NOT done
this round (deferred per Q6's own sequencing -- step7 evidence first, step8
claim contract later): a corresponding step8 `ClaimType` for this evidence
(the `gap_attribution_shapley`/`switch_significance`/
`joint_attribution_support` precedent from Part VIII shows the pattern is
straightforward to replicate when actually needed).

### docs/step7-8.md Part X: multi-factor validation feasibility assessment (2026-08-17, evaluated and deliberately deferred, not executed)

Investigated running a genuinely independent second factor (not AssetGrowth)
through the full Shapley/paired/joint pipeline. Findings recorded in Part X:
(1) `src/infra/models/method_spec.py` (v1 MethodSpec) still exists in this
repo, contradicting an earlier session's memory note claiming full deletion
-- corrected `/memories/repo/methodspec_schema_notes.md` with a note to
re-verify via `file_search` rather than trust that note at face value; (2)
`tests/_spec_test_helpers.py::accruals_resolved_spec()` is a verified v2
`ResolvedMethodSpec` fixture, but its docstring says it reuses
`asset_growth_synthetic_data`'s golden numbers -- running it would validate
the methodology generalizes to a different MethodSpec shape, but would NOT
be an independent real-data economic result; (3) real WRDS columns needed
for `gross_profitability`/`book_to_market` exist in `data/local/`, but their
only fixtures are old v1-schema JSON, requiring a from-scratch v2
`ResolvedMethodSpec` build (mirroring `asset_growth_resolved_spec()`) before
any real run. Decision: deliberately NOT attempted this round -- recorded a
concrete 5-step follow-up plan (pick `gross_profitability`, build its v2
spec, check for a `GP` CZReferenceProfile/SignalDoc entry, run a real
`MultiTrackController` factorial batch, repeat Part VII's verify-before-write
process) as its own future session's task rather than risk generating
plausible-looking but unverified second-factor numbers under time pressure.

### step8/frontend: `rendered_sentence` per claim closes the "frontend shows raw LLM text" gap (2026-08-17)

Follow-up to the previous round's known limitation. New
`render.py::report_to_jsonable(report, bundle)`: same as `report.model_dump()`
but splices `deterministic_sentence(claim, evidence)` into each claim as
`rendered_sentence` -- the identical sentence `diagnosis.md` shows, now
reaching JSON consumers too, so the frontend never has to duplicate
`_RELATION_TEMPLATES`' wording logic (and risk drifting from it).
`write_diagnosis` now writes this augmented dict to `diagnosis.json` (what
`GET .../steps/8/diagnosis` serves) instead of the bare `report.model_dump()`;
`backend/routers/diagnosis.py`'s POST handler's job-result `"report"` key
switched from the generic `to_jsonable(report)` to the same
`report_to_jsonable(report, bundle)` for consistency between the two response
paths (removed the now-unused `to_jsonable` import).
`frontend/src/components/steps/Step8Output.tsx`'s `ClaimCard` now shows
`rendered_sentence` as the primary line and only shows the LLM's own `text`
as a secondary "model wording (not authoritative)" aside when it differs --
mirrors `render.py`'s own dedup logic exactly. New backend tests
`TestReportToJsonable` (3 cases: sentence matches `render_markdown`'s own
template output, survives a JSON round-trip, empty-claims batch doesn't
crash). `tests/test_replication_diagnosis.py` 99 passed; broader diagnosis/
step8/replication_diff/attribution suite 133 passed; the existing
`TestStep8Diagnosis` API integration tests (which exercise the real POST/GET
endpoints end-to-end) also green. Frontend: `npx tsc --noEmit` / `npx oxlint`
both clean.

### frontend: layered step8 UI (`Step8Output.tsx`), closing Part IX §9.4 (2026-08-17)

New `frontend/src/components/steps/Step8Output.tsx`, wired into
`StepOutputView.tsx` in place of the old flat `claim.text`-only list. A
deterministic `## Summary`-equivalent section (expanded `<details>` by
default, one `SummaryCard` per `report.summary` entry: comparison-line label,
`overall_tag`, per-switch significance, joint-test supported/not-supported
badge, dominant switches, caveats) sits above four collapsible `<details>`
sections in Part IX's dependency order (`per_switch` -> `joint_gate` ->
`vs_paper` -> `auxiliary`, plus a final "Other" section for claims with no
`analysis_stage`, e.g. the old OAT-only `gap_attribution` type). Each
`ClaimCard` shows `claim_type`/`relation`/`subject_track`/`comparison_line`/
`identification_level`/`evidence_strength` as badges and visually dims
(opacity) when `evidence_strength === "low"` -- reads the field Part VIII
already computes (e.g. the joint-test gate capping a Shapley claim), no
threshold logic re-derived in the frontend. Rejected-claims audit trail kept
unchanged at the bottom. Known limitation, called out in the component's own
comment: `claim.text` shown per claim is the LLM's raw prose, NOT the
deterministic sentence `render.py::deterministic_sentence` generates for
`diagnosis.md` -- that renderer's logic isn't exposed by the `GET .../steps/
8/diagnosis` endpoint (which returns the raw `ReplicationDiagnosisReport`
JSON, not rendered markdown), so reproducing it in TypeScript was left out of
scope this round rather than half-duplicated and risking drift from the
Python source of truth. Verified: `npx tsc --noEmit` / `npx tsc -b` both
clean, `npx oxlint` clean on the new/changed files.

### step8: implemented Part IX's backend (analysis_stage taxonomy + deterministic `DiagnosisSummary` rollup + stage-grouped rendering) (2026-08-17)

Backend half of Part IX's layered-analysis design (scheme B / summary option
1, confirmed earlier). `src/infra/models/diagnosis.py`: new
`AnalysisStage = Literal["per_switch", "joint_gate", "vs_paper", "auxiliary"]`
+ `ANALYSIS_STAGE_BY_CLAIM_TYPE` static map (`gap_attribution` -- the old
OAT-only type -- deliberately maps to nothing, stays `None`/"unstaged"),
`DiagnosisClaim.analysis_stage` field, new `DiagnosisSummary` model, and
`ReplicationDiagnosisReport.summary: list[DiagnosisSummary]`. New
`src/steps/step8_diagnosis/summary.py::build_deterministic_summary`: pure
function over already-*validated* claims (never re-reads raw bundle evidence
beyond `derived.overall_tag`, copied, and `shapley_attribution` magnitudes for
sorting `dominant_switches` only) -- one `DiagnosisSummary` per comparison
line present among the claims (or a single `comparison_line=None` entry when
no line-scoped claim exists), computing `per_switch_summary`/`joint_supported`
(`None` when not tested, distinct from `False`)/`dominant_switches` (Shapley
claims NOT capped to `evidence_strength="low"` by the Part VIII joint-test
gate, sorted by the switch's own Shapley magnitude)/fixed-template `caveats`.
Wired into `ReplicationDiagnoser.diagnose()` (`report.summary =
build_deterministic_summary(accepted, bundle)`) and `_derive_claim_fields`
(`analysis_stage` derived by static lookup, same pattern as `reason_layer`).
`render.py`: `## Findings` now groups by `analysis_stage` (dependency order:
per_switch -> joint_gate -> vs_paper -> auxiliary -> unstaged) before
`claim_type`, and a new `## Summary` section (rendered from `report.summary`,
above Findings) -- also fixed a latent local-variable name collision (`stage`
was reused for both the outer analysis-stage loop and each claim's own
pipeline `.stage`, e.g. "portfolio"; renamed the inner one to `claim_stage`).
New tests: `TestValidateClaimsPartVIIITypes` (+2 `analysis_stage` cases),
`TestBuildDeterministicSummary` (6 cases), `TestDiagnoseWiresSummary` (1),
`TestRenderMarkdown` (+1, stage-ordering/Summary-section assertions).
`tests/test_replication_diagnosis.py` 96 passed; broader diagnosis/step8/
replication_diff/attribution suite 130 passed, zero regressions. Backend-only
API changes are transparent (`backend/serialization.py::to_jsonable` uses
`model_dump(mode="json")` generically, so `report.summary` reaches the
frontend automatically). NOT done this round (Part IX §9.4, explicitly a
separate follow-up): the layered/collapsible `StepOutputView.tsx` step8 UI --
the frontend still only renders `claim.text` in a flat list and doesn't yet
read `analysis_stage`/`comparison_line`/`evidence_strength`/`report.summary`
at all.

### `render.py`: deterministic sentence templates for Part VIII's 3 new claim types (2026-08-17)

Closes the gap flagged right after Part VIII landed: claims of type
`gap_attribution_shapley`/`switch_significance`/`joint_attribution_support`
validated correctly but rendered as the generic `"claim_type: relation"`
fallback (no switch name, no comparison line, no real sentence). Added
`_RELATION_TEMPLATES` entries for all three, a `_LINE_LABELS` map (`to_hxz`
-> "①→③ (HXZ standardized config)", `to_cz` -> "①→② (C&Z actual config)",
matching the frontend's existing labelling) feeding a new `{line}` template
placeholder, `_per_switch_subject` (extracts the switch name from a
`paired_tests.<line>.per_switch.<switch>.t_stat` key, mirroring
`_switch_subject`'s existing `.contributions.`/now also `.shapley_effects.`
handling). `deterministic_sentence` passes `line=_line_label(claim.
comparison_line)` for every claim type now (a no-op extra `format()` kwarg
for templates that don't reference `{line}`). New test
`TestRenderMarkdown::test_part_viii_claim_types_render_switch_and_line_into_the_sentence`.
Full `tests/test_replication_diagnosis.py` 86 passed, zero regressions.

### step8: implemented Part VIII's 3 new claim types (`gap_attribution_shapley`/`switch_significance`/`joint_attribution_support`) + `comparison_line` field (2026-08-17)

Turns the Part VIII design into code -- step8 can now cite `shapley_attribution`/
`paired_tests`/`joint_test` (previously unreachable). `src/infra/models/
diagnosis.py`: added the 3 `ClaimType` values + their `CLAIM_RELATIONS`/
`CLAIM_EVIDENCE_REQUIREMENTS`/`CLAIM_EVIDENCE_SUBSTRINGS`/
`REASON_LAYER_BY_CLAIM_TYPE`/`IDENTIFICATION_BY_CLAIM_TYPE` entries, and
`DiagnosisClaim.comparison_line: Literal["to_hxz", "to_cz"] | None` (mirrors
`subject_track`'s derivation/validation pattern, needed since these three
bundle sections are nested by comparison line). `src/steps/step8_diagnosis/
__init__.py`: `_cited_lines`/`_comparison_line_reason` (mirror `_cited_tracks`/
`_subject_track_reason`), 3 new entailment branches in `_entailment_reason`
(inline threshold checks reusing `bundle.SIGNIFICANCE_T_THRESHOLD` for
`switch_significance` and a new `JOINT_TEST_ALPHA = 0.05` module constant for
`joint_attribution_support` -- deliberately NOT Q7's 3-tier thresholds, which
are scoped to track-vs-paper only), `comparison_line` derivation in
`_derive_claim_fields`, and the Part VIII §8.4 joint-test gate: a
`gap_attribution_shapley` claim's `evidence_strength` is forced to `"low"`
when the same line's `joint_test.p_value >= JOINT_TEST_ALPHA` even though its
`identification_level` stays `"controlled"` (the grid is still complete --
only the reported strength is capped). Added `SHAPLEY_ATTRIBUTION_TOOL`/
`PAIRED_TESTS_TOOL`/`JOINT_TEST_TOOL` to `STEP8_TOOLS`. `prompts/analysis/
replication_diagnosis.md` updated with the 3 new claim types' evidence
requirements and a `comparison_line` explanation. New tests in
`tests/test_replication_diagnosis.py::TestValidateClaimsPartVIIITypes` (11
cases: accept/reject per new type, the joint-test-gate evidence_strength cap,
and comparison_line auto-derivation/required-on-conflict/mismatch-rejection).
Full `tests/test_replication_diagnosis.py` 85 passed; broader
diagnosis/step8/replication_diff/attribution-related suite 119 passed, zero
regressions. Not done this round (per Part VIII/IX's own explicit scope):
`render.py` templates for the 3 new claim types, and all of Part IX's layered
UI/summary work.

### `docs/step7-8.md` Part IX: step8 layered analysis + deterministic summary design (round 2, after Part VIII) (2026-08-17)

Design only, no code changed. User confirmed: layering scheme B (dependency-
ordered stages -- `per_switch` (`switch_significance`/`gap_attribution_
shapley`) -> `joint_gate` (`joint_attribution_support`) -> `vs_paper`
(`sign_agreement`/`magnitude_gap`/`significance`/`config_divergence`) ->
`auxiliary` (`publication_decay`/`signal_reproducibility`/
`implementation_robustness`/`evidence_limitation`), NOT the existing 3-value
`ReasonLayer`, which stays unchanged and orthogonal); summary option 1
(a deterministic rollup over already-validated claims via a new
`build_deterministic_summary` function, NOT a second LLM-authored free-text
layer -- no new trust surface, no re-reading of raw bundle keys); and
explicit two-round sequencing (Part VIII's new claim types land first, this
layering/rendering work is a separate follow-up round). New `DiagnosisClaim.
analysis_stage` field (static claim_type lookup, mirrors `reason_layer`'s
derivation), new `DiagnosisSummary`/`ReplicationDiagnosisReport.summary`,
`render.py` grouping by stage instead of flat claim_type, and a layered/
collapsible `StepOutputView.tsx` step8 UI (summary expanded on top, 4
collapsible stage sections below, `evidence_strength=low` visually
de-emphasized using the field Part VIII already computes -- no new
threshold logic in the frontend).

### `docs/step7-8.md` Part VIII: step8 claim-contract extension design for `shapley_attribution`/`paired_tests`/`joint_test` (Q6 follow-up) (2026-08-17)

Design only, no code changed. Specifies 3 new `ClaimType` values
(`gap_attribution_shapley`, `switch_significance`, `joint_attribution_support`)
with their evidence-prefix/substring/relation/reason-layer/identification-level
entries, a new `DiagnosisClaim.comparison_line` field (mirrors the existing
`subject_track` derivation pattern, needed since Part VI nests these three
bundle sections by comparison line `to_hxz`/`to_cz`), entailment logic for
each (inline threshold checks, same precedent as the existing
`_n_months_mismatch_reason`), and a joint-test gating rule that caps
`gap_attribution_shapley`'s `evidence_strength` to `low` when the same line's
joint test is available but not significant (data-layer equivalent of the
existing frontend `ShapleyAttributionTable` dim+badge behavior). Explicitly
out of scope this round: no `publication_decay` claim-type changes needed
(example 6 already works under the existing contract), no Q3 pairwise-
interaction or Q5 `t_channel_decomposition` claim types (still pending their
own step7 design decisions).

### `docs/step7-8.md` Part VII: added example 5 (①→② `to_cz` universe paired-test, AGENTS.md's core inter-implementer-agreement question) and example 6 (`publication_decay`, previously computed but never featured) (2026-08-17)

Both use real numbers already on disk in `runs/backtest_scripts/results/
099f6e1136bd316c/comparison.json` -- no new code, doc-only. Example 5
corrects an earlier drafted (never-committed) claim that mis-described
C&Z's universe filter as including a `ceq > 0` check; the real
`cz_actual_config` universe is only `shrcd in [10,11,12]` + `exchcd in
[1,2,3]` (`src/infra/reference/__init__.py::cz_profile_to_config_override`),
vs the agent's `siccd not_between [6000,6999]` -- the previously-drafted
`mean_diff`/`t_stat` numbers (+0.000874/month, t=1.78) were themselves real
(verified against `paired_tests.to_cz.universe`), only the filter
description was wrong. Example 6 surfaces `publication_decay` for the
first time in any Part VII example: `factorial_universe` is the only
single-switch ①→③ track that doesn't decay post-publication, which lines
up with `universe` also being the one dimension example 5 flags as
agent/C&Z's sole point of disagreement -- flagged as a pattern worth
checking across more factors, not yet a generalizable claim.

### `derived.tracks[*].vs_paper` now compares the paper's own in-sample window, not our full extended history (2026-08-17)

Found while building step7 usage examples: `build_track_vs_paper` (and thus
`derived.overall_tag`) was comparing the paper's reported number against
`RunMetrics`' TOP-LEVEL metrics, which cover this engine's full extended
history (often decades past the paper's publication year -- 882 vs 432
months in the real AssetGrowth reference run), instead of
`RunMetrics.by_sample_period.insamp` (the paper's own sample window --
already used correctly by `build_publication_decay` and by the frontend's
`Step6Output.tsx`). A paper's headline number was never computed over that
extra post-publication history, so this was an apples-to-oranges
comparison. Real-world impact on the AssetGrowth reference run:
`abs_spread_ratio` 1.41 -> 2.11, `overall_tag` "close_replication" ->
"sign_agrees_magnitude_differs" -- a materially different headline
verdict, not just a cosmetic number change.

New `_in_sample_metrics(metrics)` merges `by_sample_period.insamp` over the
top-level metrics key-by-key (not all-or-nothing, since `insamp` doesn't
carry every top-level key, e.g. `coverage`), renaming its
`mean_monthly_return` to `mean_return` to match `_resolve_track_spread`'s
expected key; falls back to the unchanged top-level metrics when no
in-sample window was configured (i.e. no behavior change for a run without
`sample_start_year`/`sample_end_year`). `build_evidence_bundle` now feeds
this into both `build_track_vs_paper` and `derived.tracks[*].n_months`.


### Auto-attribution no longer generates the all-switches-flipped corner as a duplicate track (2026-08-17)

Fixes a second, more general instance of the previous entry's "ambiguous
switch" bug: `_auto_attribution_specs`'s full-factorial expansion always
included a combo where EVERY differing switch takes the target value --
but that corner is, for any `n`, identical to the endpoint track built
separately by `_plan_to_matrix` (`cz_actual_config`/`standardized_hxz`),
which flips the same switches to the same values by definition. Both
tracks then reported the same `switches_flipped` key set, and
`attribution.py` correctly refused to pick one (real production example:
`n=1`, only "universe" differs -- `cz_actual_config` and the auto-generated
`cz_factorial_universe` were the exact same config; `n=3` -- `standardized_hxz`
and the auto-generated `factorial_breakpoint_weighting_universe` were the
exact same config). The earlier fix only special-cased `n == 1`; this
generalizes it.

`_factorial_track_specs` gained an `exclude_combos: set[frozenset[str]] |
None` parameter (a manual `factorial_switches` caller, with no separate
endpoint track to collide with, must leave it `None`); `_auto_attribution_specs`
now always passes `exclude_combos={frozenset(switches)}` to drop that one
corner, regardless of `n`. `compute_shapley_effects` is unaffected: it
already reads the full corner off of `tracks` generically (by whichever
track happens to report that full `switches_flipped` set), not from this
generation list, so the endpoint track alone still satisfies the 2^n grid.

Updated `tests/test_experiment_plan_matrix_merge.py`'s
`test_default_plan_auto_generates_factorial_tracks_for_the_real_diff` (7 ->
6 `factorial_*` tracks) and `test_cz_config_override_auto_generates_cz_factorial_tracks`
(3 -> 2 `cz_factorial_*` tracks) to reflect the corrected, non-redundant
counts.

### Attribution (Shapley/paired-test/joint-test) now runs per comparison line, not per batch (2026-08-17)

Fixes the root cause behind the previous entry's "ambiguous switch"
detection, rather than just detecting and excluding it: a batch that ran
both ①→② (`cz_factorial_*`/`cz_ablation_*`, target `cz_config_override`)
and ①→③ (`factorial_*`/`ablation_*`, target `HXZ_STANDARD_CONFIG`) had all
of its tracks pooled into ONE shared calculation, so two different tracks
touching only "universe" (one per line) could collide. New
`attribution.split_tracks_by_comparison_line(tracks, baseline_track)`
splits a batch's tracks into up to two independent groups (`to_cz`/
`to_hxz`, using the existing, already load-bearing `cz_`-prefix naming
split -- not a fragile parse of switch names) BEFORE
`compute_shapley_effects`/`paired_switch_significance`/
`joint_switch_wald_test` ever run, so the two lines' tracks are never in
the same calculation and the collision cannot occur at all (rather than
being caught and one switch dropped).

`bundle.build_shapley_and_significance` now nests its three outputs one
level by comparison line: `{"shapley_attribution": {"to_hxz": {...},
"to_cz": {...}}, "paired_tests": {...same...}, "joint_test": {...same...}}`
-- a batch with only one line present (the common case) has only that one
key; a batch with none has the flat `{"available": false, ...}` shape
directly (unchanged for that case). Considered and explicitly rejected a
third "②→③" (C&Z config vs HXZ config directly) comparison line -- it
would need an entirely new baseline (② itself) and a freshly-run
factorial grid, isn't part of the project's declared core contribution
(Q1, docs/step6.md §25 decision A), and can be approximated well enough
by reading the existing ①→②/①→③ results side by side.

`frontend/src/components/steps/Step7Output.tsx` renders each line as its
own bordered section (labeled "① → ② (C&Z actual config)"/"① → ③ (HXZ
standardized config)") via a new `linesOf()` normalizer in the same file
that handles both the nested and the flat-when-empty shapes.
`AttributionPanel.tsx`'s three components are unchanged -- they always
take a single line's result, now called once per line instead of once
per batch.

New tests: `TestSplitTracksByComparisonLine` (`test_attribution.py`),
`test_two_comparison_lines_no_longer_collide_on_the_same_switch_name`
(`test_replication_diagnosis.py`); updated the one existing test that
asserted the old flat shape. Full suite: 684 passed, 18 skipped, zero
regressions. `tsc -b`/`oxlint` clean on the frontend changes.

### Fix: `paired_switch_significance`/`joint_switch_wald_test` silently picked one of two ambiguous single-switch tracks (2026-08-17)

Found on a real run: a batch with BOTH `factorial_universe` (target
`HXZ_STANDARD_CONFIG`) and `cz_factorial_universe` (target
`cz_config_override`) produces two DIFFERENT tracks whose
`switches_flipped` both touch only `"universe"` (same config key, two
different target values). `compute_shapley_effects` already refused this
case ("ambiguous, refusing to pick one"), but
`paired_switch_significance`/`joint_switch_wald_test` built their
switch->track mapping as a plain dict keyed by switch name --
`single_switch_tracks[switch] = name` -- so the second track silently
overwrote the first with no warning, and the joint test's `universe`
contrast was whichever track happened to be iterated last, not a
documented or deterministic choice.

New shared `_single_switch_track_map(tracks, baseline_track)` returns
`(resolved, ambiguous)`: switches with exactly one candidate track vs.
switches with more than one, used by both functions now. Ambiguous
switches are reported, not resolved: `paired_switch_significance` gives
that switch's `per_switch` entry `{"available": False, "reason":
"multiple tracks map to switch ... -- ambiguous, refusing to pick one"}`;
`joint_switch_wald_test` drops the switch from the test entirely and lists
it in a new `ambiguous_switches_excluded` key (present on both the
available and unavailable return paths). New tests:
`test_two_tracks_mapping_to_the_same_switch_is_reported_not_silently_picked`,
`test_ambiguous_switch_is_excluded_not_silently_picked`. Full suite: 680
passed, 18 skipped, zero regressions.

### `MeasuresExplainer` card gains paper citations, purpose, and worked examples per measure (2026-08-17)

Extended each of the four `MEASURES` entries (`AttributionPanel.tsx`) with
a `paper` (Shapley 1953; Newey & West 1987, Econometrica; Wald 1943's
general test + Ledoit & Wolf 2008's HAC-covariance application; Harvey,
Liu & Zhu 2016 RFS + Hou, Xue & Zhang 2020 RFS for the tier thresholds), a
`purpose` line (what the measure is actually used FOR in this pipeline,
not just what it computes), and an `example` pulled from the real
AssetGrowth batch (Shapley's 96%/31%/−27% split, the weighting switch's
t=2.74 paired test, the 3-switch joint Wald=21.62/p≈0.00008, and the
tier-3-vs-tier-1 contrast between original_method and standardized_hxz).
`tsc -b`/`oxlint` clean.

### step7 output: `MeasuresExplainer` card with formulas for Shapley/paired-test/joint-test/HXZ tiers (2026-08-17)

New `MeasuresExplainer` in `AttributionPanel.tsx` -- a collapsed-by-default
`<details>` card (visually distinct via a primary-tinted border/background
so it stands out from the data tables, not blended in) listing the
formula + one-line explanation for each of the four measures step7 now
computes: Shapley's weighted-marginal-contribution formula (plus its
efficiency property), the paired Newey-West t-stat, the joint Wald
statistic (spelling out why the covariance needs cross terms), and the
HXZ tiered-significance rule. Plain monospace/Unicode notation, not
LaTeX/KaTeX (no math-rendering library in this frontend yet, and adding
one for a handful of static formulas would be disproportionate). Rendered
near the top of `Step7Output.tsx`, ahead of the data panels. `tsc -b`/
`oxlint` clean.

### step7 output: extracted to its own component, config diff gets a track-selection checklist (2026-08-17)

Extracted the `step === 7` branch out of `StepOutputView.tsx` into a new
`frontend/src/components/steps/Step7Output.tsx` (mirrors `Step6Output.tsx`'s
own file split). Added a "Compare against `<baseline>`" checkbox row
(mirrors `Step6Output`'s existing track-selection checklist) so a batch
with 10+ `factorial_*`/`ablation_*` tracks doesn't dump every track's
config diff on screen by default, plus an "Only show tracks with config
differences" toggle (defaults on) that hides tracks whose
`config_diff.pairs[track].changed_keys` is empty. `tsc -b`/`oxlint` clean.

Note: an existing session's `comparison.json` predating the Shapley/
paired/joint work above won't show anything in those three panels or the
gap-decomposition chart -- `switches_flipped` is only set at
`run_from_matrix` EXECUTION time, so a stale `comparison.json` has neither
that field nor the new evidence keys. Step 6 (the experiment batch) needs
to be re-run for a session to see the new panels; the underlying
mean_return/t_stat numbers should come out identical (same plugin, config,
data), only the new evidence blocks are added.

### step7 request panel: replace raw JSON textarea with a "What this step computes" description (2026-08-17)

Step7's request body is just `{expected_revision, experiment_batch_id}` --
an opaque hash with no user-editable content, but it was still shown as a
raw JSON textarea (the only steps with a custom summary instead were
3/4/5 via `RequestFieldsSummary`). Added a step7-specific description
block to `SessionDetailPage.tsx`, modeled on step4's existing "What this
step checks" list: seven `{name, desc}` rows (track vs paper, config
diff, gap decomposition/OAT, Shapley attribution, paired significance
test, joint Wald test, bridge/decay/robustness) explaining what
`build_evidence_bundle` actually computes, replacing the raw textarea
(excluded step 7 from the same condition that already hides it for
3/4/5/6). `tsc -b`/`oxlint` both clean.

### step7 UI: Shapley table, paired-test rows, joint-test banner (docs/step7-8.md Part V) (2026-08-17)

New `frontend/src/components/AttributionPanel.tsx` (`JointTestBanner`,
`ShapleyAttributionTable`, `PairedTestsTable`), wired into
`StepOutputView.tsx`'s `step === 7` branch alongside the existing
`GapWaterfallChart`/`DiffView`. All three read the new `shapley_attribution`/
`paired_tests`/`joint_test` keys directly and render each block's own
`available`/`reason` rather than a generic empty state.

`GapWaterfallChart`'s old "No gap decomposition available" empty state (a
false negative on every full-factorial batch, since `gap_decomposition` is
OAT-only and mutually exclusive with `shapley_attribution` per batch) is
now only shown when `shapley_attribution` ALSO has nothing -- a normal
full-factorial batch shows the Shapley table instead, not an "attribution
failed" message.

`ShapleyAttributionTable` dims itself (opacity + a "lacks joint support"
badge) when `joint_test` is available but not significant (p >= 0.05) --
the visual form of the gate described in docs/step7-8.md Part V: don't let
a single switch's Shapley number read as important without the joint test
backing it, ahead of any step8 claim-contract change. `frontend/src/lib/
evidence.ts`'s `RunRecord` interface gains `switches_flipped` (mirrors the
new backend field). `tsc -b` and `oxlint` both clean on the changed files.

### step7: Shapley-value attribution, paired Newey-West test, joint Wald test (docs/step7-8.md Part V) (2026-08-17)

Implements the three methods identified in a literature review (Menkveld
et al. 2024 "Nonstandard Errors", Soebhag et al. 2024, Ledoit-Wolf 2008)
as directly usable, low-risk upgrades over the existing OAT-only
`gap_decomposition`, which never fires for the now-default full-factorial
batches (only recognizes `ablation_*` track names).

New `src/steps/step7_replication_diff/attribution.py`:
- `compute_shapley_effects`: order-independent decomposition of the
  `mean_return` gap across a full-factorial batch's switches (requires all
  2^n corners present; reports exactly which subsets are missing
  otherwise). `identification_level="controlled"` -- the level
  `src/infra/models/diagnosis.py`'s `IdentificationLevel` docstring already
  reserved for exactly this design, previously unreachable.
- `paired_switch_significance`: per single-switch track, a paired
  Newey-West test (differenced monthly return series over the months both
  tracks report in-sample) of whether that switch's effect is
  distinguishable from zero.
- `joint_switch_wald_test`: one joint Wald test across ALL single-switch
  contrasts at once (HAC covariance matrix including cross-covariances,
  since the contrasts share the same baseline and heavily-overlapping
  months and are NOT independent) -- the gate against picking whichever
  single switch looks biggest without checking they're collectively
  significant (the ANOVA-omnibus-before-post-hoc pattern).

All three verified against a real AssetGrowth batch
(`runs/backtest_scripts/results/099f6e1136bd316c/`): Shapley attributes
96% of the total gap to `weighting` (matches the §8 pre-registered
weighting×breakpoint prediction); paired test on `weighting` gives t=2.74
(432 overlapping in-sample months); joint Wald stat 21.62 (df=3,
p≈0.00008) across all three switches.

Prerequisite plumbing (docs/step7-8.md Part V, Q2): new
`RunRecord.switches_flipped: dict | None` field, populated by
`run_from_matrix` from `ExperimentSpec.resolved_diff` (already computed
for `identification_level`, previously discarded) via a new
`_CONFIG_KEY_TO_SWITCH` reverse map + `_switches_flipped_from_diff` helper
in `step6_dual_track_controller`. Deliberately NOT parsed from the track
name (considered and rejected: unreliable, breaks on any future naming
convention change) -- works for tracks produced by ANY path (factorial,
ablation, sweep, yaml), not just the auto-attribution ones. Threaded into
`tracks_summary`/`comparison.json` alongside the existing `config`/
`metrics`/`is_bridge_track` keys.

`MAX_FACTORIAL_SWITCHES` lowered 5->4 (2^4=16 max runs instead of 32);
kept as the informal ceiling for Shapley's own "is the grid complete"
check via an independent, more generous safety constant
(`_MAX_SWITCHES_FOR_SHAPLEY = 6`) rather than importing the step6 constant
(would create a step6<->step7 circular import).

`bundle.py`'s `build_evidence_bundle` gains a `results_dir: Path | None`
parameter (already computed by `write_comparison_summary`, now threaded
through) producing three new top-level keys: `shapley_attribution` (only
needs `mean_return`, computed regardless of `results_dir`),
`paired_tests`/`joint_test` (need the on-disk `<track>.csv` monthly
series, report `available=False` without `results_dir` rather than
raising).

Also added HXZ's own three-tier significance hurdles (docs/step7-8.md Q7;
verified against `docs/Hou 等 - 2020 - Replicating Anomalies.pdf`:
"thresholds of 1.96, 2.78, and 3.39") as new `paper_significance_tier`/
`track_significance_tier` fields on `build_track_vs_paper`'s output, via a
new independent `SIGNIFICANCE_T_THRESHOLDS` constant -- the existing
`SIGNIFICANCE_T_THRESHOLD`/`paper_significant`/`track_significant`/
`significance_agrees` fields are left untouched (a test imports and
asserts equality against the old constant directly; renaming it would
have broken that test for no benefit).

New tests: `tests/test_attribution.py` (Shapley/paired/joint, including a
skip-if-absent check against the real AssetGrowth run directory),
`TestSwitchesFlipped` in `tests/test_experiment_plan_matrix_merge.py`,
`TestShapleyAndSignificanceWiring` + tier assertions in
`tests/test_replication_diagnosis.py`. Full suite: 678 passed, 18 skipped,
zero regressions.

### "Config per track" table gets a track-selection checklist (defaults to all, baseline pinned), now also filters the chart (2026-08-17)

With auto-attribution's `factorial_*`/`ablation_*`/`cz_factorial_*`/
`cz_ablation_*` tracks, a batch can easily reach 10+ tracks, making the
"Config per track" table (`Step6Output.tsx`) and the return chart very
crowded by default. Added ONE shared checkbox row (defaults to every track
checked, matching the prior always-show-everything behavior) plus
"All"/"None" buttons, controlling BOTH the config table's columns and which
tracks `MultiTrackChart` plots -- the baseline track's checkbox is disabled
(always selected), since both sections use it as the pinned reference/delta
basis; "None" clears everything except the baseline instead of leaving
nothing to compare against.

### Step6 ②/③ preview queries (C&Z config, HXZ reported return) now survive a page reload (2026-08-17)

`GET /steps/6/cz-config` and `GET /steps/6/hxz-config` are intentionally
stateless on the backend (preview-only, never mutate the session), so their
results only ever lived in the step6 request card's own React `useState` --
any page reload (routinely following a dev-server backend restart, since
this repo's uvicorn has no `--reload` hot reload by default) silently reset
them to "never queried", forcing a re-query (a live `openassetpricing` call
for ②, a CSV re-download for ③) just to see the same numbers again. Added
`frontend/src/lib/step6PreviewStore.ts` (same `localStorage`-per-session
pattern as `methodSpecStore.ts`) and wired `step6ConfigDiff`/
`step6HxzReported` plus each preview component's own selected-acronym/result
state to read from and write to it.

### Auto-attribution `universe` switch failed at runtime: `universe_filters` override missing its `universe_filter_join_sources` companion (2026-08-17)

Every auto-attribution factorial/ablation track that flips the `universe`
switch toward `HXZ_STANDARD_CONFIG` (whose `universe_filters` includes a
`ceq > 0` filter on a Compustat-only column) failed at execution with
`ValueError: Universe filter references field 'ceq', which the loaded
returns panel does not have` -- `_get_ablation_override`/
`_factorial_track_specs` only carried over the `universe_filters` key
itself, never the paired `universe_filter_join_sources` key that tells the
generated script's `join_universe_filter_sources()` how to attach `ceq` to
the returns panel in the first place. Added a `_CONFIG_KEY_COMPANIONS`
map (`universe_filters -> universe_filter_join_sources`) consulted by both
functions whenever a switch's value is actually overridden to the target's
value, so the override is self-consistent. Verified directly against
`_factorial_track_specs` output: all universe-inclusive combos now carry
`universe_filter_join_sources: {'comp_funda': ['ceq']}`.

### Auto-attribution factorial track names shortened to switch names, not raw config values (2026-08-17)

`_factorial_track_specs` previously named each track after every
overridden config key AND its raw value (`f"{k}={v}"`), which for a
list-valued switch like `universe_filters` embedded a full Python repr of
a list of dicts into the track name -- unreadable, and unsafe as a
filename/path component since these names are also used as on-disk
script/output directory names. Track names are now just the switch NAMES
that took the target config's value in that combo, joined with `_`
(e.g. `factorial_breakpoint_weighting_universe` instead of
`factorial_breakpoint_source=nyse_weighting_rule=vw_universe_filters=[...]`).
Also replaced the old silent-drop-on-name-collision dedup (which could
lose a track from `comparison.json` with no error) with a running
`_1`/`_2`/... suffix appended to every combo sharing a base name.

### `ExperimentPlan` auto-attribution: `docs/step6.md` §4a's <=5→factorial / >5→OAT policy is now the default, not just documented (2026-08-16)

Previously `ablation_switches`/`factorial_switches` were only ever populated
by an explicit caller -- since the 2026-08-16 step6 UI simplification
removed their manual pickers, every real session's ①→③/①→② comparison ran
with ZERO field-level attribution tracks by default (only the headline
①②③ numbers), even though §4a already prescribes exact full-factorial
attribution whenever <=5 config fields actually differ.

New `ExperimentPlan.auto_attribution: bool = True`: when both switch lists
are left empty, `_plan_to_matrix` now derives the REAL differing fields
(`_diff_switches`, against the known 6-switch vocabulary in
`_ABLATION_SWITCH_TO_CONFIG_KEY`) for ①→③ (vs `HXZ_STANDARD_CONFIG`) and,
when set, ①→② (vs `cz_config_override`) independently, and auto-generates
either a full-factorial expansion (`factorial_*`/`cz_factorial_*`, <=5
fields, exact, residual always 0) or a one-at-a-time fallback
(`ablation_*`/`cz_ablation_*`, >5 fields). Never fires when the caller
already gave explicit switches (no silent doubling-up).

Generalized `_get_ablation_override`/`_factorial_track_specs` (previously
hardcoded to `HXZ_STANDARD_CONFIG` as the only possible "target") to accept
any target config dict, so the same expansion logic now serves both the
①→③ and ①→② comparisons instead of needing a second implementation.
`backend/routers/experiments.py`'s `ExperimentRequest` gained a matching
`auto_attribution: bool = True` passthrough field (no UI control yet).

Updated tests calling the old 2-arg `_get_ablation_override`/
`_factorial_track_specs` signatures, and 3 pre-existing track-count
assertions that now legitimately get extra auto-attribution tracks
(`auto_attribution=False` added where the test's own intent was unrelated
to attribution). New `tests/test_experiment_plan_matrix_merge.py::
TestAutoAttribution` (5 tests): factorial auto-generation for ①→③, explicit
switches suppress auto-attribution, `auto_attribution=False` disables it
entirely, ①→② gets its own independently-named `cz_factorial_*` tracks,
and a hand-built 6-switch diff falls back to OAT. Full suite: 661 passed,
18 skipped, zero regressions.

### Correction: `HXZ_STANDARD_CONFIG`'s `siccd not_between (6000,6999)` citation was conflating two different paragraphs (2026-08-16)

Caught by the user. The earlier entry below ("We exclude financial firms",
"the paper's general sample criterion") was written as if the paper's general
sample paragraph gave the number `6000-6999` directly -- it doesn't. That
paragraph (Section 2) only says "We exclude financial firms and firms with
negative book equity", no SIC number. The `6000-6999` range is cited from a
DIFFERENT, factor-specific paragraph elsewhere in the same paper (the
industry-concentration variable's own construction details), not restated in
the general-sample paragraph. It's the standard Fama-French-style SIC range
for "financial firms" used throughout this literature, so almost certainly
what the general exclusion means in practice -- but this is an inference, not
a verbatim number from the general-sample sentence. Corrected the comment in
`data/reference/hxz_standard_config.yaml` and `docs/cz-reference.md` §7 to
say so explicitly; no value changed (still `[6000, 6999]`).

### `cz_profile_to_config_override`: add C&Z's own universe filter, never previously set (2026-08-16)

Prompted by re-checking whether C&Z applies any universe restriction at all
(they do). Read `data/CZ code/Signals/pyCode/SignalMasterTable.py` -- the
shared "backbone" table EVERY C&Z predictor is built from -- and found:
`df[(df['shrcd'].isin([10, 11, 12])) & (df['exchcd'].isin([1, 2, 3]))]`, with
C&Z's own dev comment noting it's deliberately not recorded in SignalDoc
("TBC: remove and use this filter as default in SignalDoc.csv"). This is why
`CZReferenceProfile`/SignalDoc parsing never surfaced any universe info --
expected, not a missed field on our extraction side.

`cz_profile_to_config_override()` never set `universe_filters` at all, so the
`cz_actual_config` track silently inherited whatever `universe_filters` the
paper's own MethodSpec happened to carry (often none) instead of C&Z's actual
universe. Added `universe_filters: [{shrcd in [10,11,12]}, {exchcd in
[1,2,3]}]`, unconditional for every C&Z factor (matches how
`accounting_lag_months`/`missing_action`/`formation_lag_months` are already
set unconditionally in this same function). Updated
`tests/test_cz_reference_profile.py`'s exact-dict assertion; `docs/step6.md`
§9 (new "Universe" subsection) and §10's field-mapping table. 34 targeted
tests green.

Also checked (prompted by the user questioning the "risk" framing below) and
found NOT a gap after all, correcting an earlier over-cautious note in this
same entry: `01_PortfolioFunction.R:88-89` defaults `longportname='max'`/
`shortportname='min'` (long = highest signal decile, short = lowest) --
constant across every C&Z factor because `Sign` is multiplied onto the raw
signal BEFORE bucketing (`signal$signal = signal$signal*Sign`, line 54), not
by choosing which bucket is "long" afterward. Initially flagged this as too
risky to mirror via a `long_leg`/`short_leg` override without first verifying
our own `sign` handling matched. Re-checked `registry._build_config_from_
resolved` (lines 656-661): `config["long_leg"]`/`config["short_leg"]` are
purely descriptive strings DERIVED FROM `long_portfolios`/`short_portfolios`
(the actual bucket-number lists driving execution), which themselves come
from `_resolve_legs(paper, ...)` reading `paper.portfolio.legs` directly --
the SAME `paper` object for every track of a given factor, untouched by any
config override. There is no per-track leg-override mechanism in this engine
at all, so C&Z's "flip Sign then take fixed max/min" and this repo's "extract
the paper's own stated legs" necessarily converge on the same long/short
bucket assignment for a given factor -- nothing to add to
`cz_profile_to_config_override`.

### Fix: `registry.build_config` used `sample.formation` instead of `sample.reported_returns` for the engine's `sample_start_year`/`sample_end_year` (2026-08-16)

Found while comparing AssetGrowth's `openassetpricing`-reported `sample_end_year`
(2003) against this repo's own extraction (2002) and initially assuming it was
a discrepancy to investigate on the C&Z side -- it wasn't; it exposed a real
wiring bug in `_build_config_from_resolved`.

`MethodSpec.sample` has three distinct windows (`data_coverage`/`formation`/
`reported_returns`) precisely because a paper's portfolio-formation window and
its headline-number return window can differ -- for any annual-rebalance,
hold-a-full-year strategy (the norm for accounting factors), the last
formation date is up to a year earlier than the last month the resulting
holding period actually produces a return for (Cooper/Gulen/Schill 2008:
formation "1968 to 2002" per Table II vs. reported returns "July 1968 to June
2003" per Section II.A). `registry.py` read `paper.sample.formation` for the
engine's `sample_start_year`/`sample_end_year` config keys -- but those two
keys feed ONLY `BacktestExecutor._sample_period_metrics`'s `insamp` segment,
whose entire purpose (per `schema_reference.py`'s own field description:
"the date range the paper's headline reported numbers actually cover") is
comparing our computed number against the paper's own reported one. Reading
`formation` instead of `reported_returns` made `insamp` silently exclude
months the paper's own headline number includes, for any factor where these
two windows differ -- not specific to AssetGrowth, a general-purpose bug
affecting every ①-track in-sample comparison in the step6 UI.

Fixed: `sample_start_year`/`sample_end_year` now read `paper.sample.
reported_returns` instead of `paper.sample.formation`. Verified with a
synthetic spec where the two windows differ (`build_config` now correctly
returns `sample_end_year=2003`, not `2002`). No test asserted the old
`.formation`-sourced values (the generic test fixtures set `data_coverage`/
`formation`/`reported_returns` to the SAME `Period`, so this was invisible to
them) -- full suite: 656 passed, 18 skipped, zero regressions.

### `HXZ_STANDARD_CONFIG`: implement negative-book-equity exclusion, drop dead `missing_action` key (2026-08-16)

Third follow-up in the same-day HXZ config re-verification thread. Two more
findings from re-reading the paper and the engine code together:

- `missing_action: drop` was pure decoration: `BacktestExecutor.
  apply_missing_policy` unconditionally drops rows with a missing return
  and never reads the config value at all (no other implementation
  exists). Removed the key entirely rather than keep an inert override.
- The paper's general sample criterion ("We exclude financial firms and
  firms with negative book equity") had its `siccd` half implemented but
  not its book-equity half, previously recorded as a gap needing new
  engine plumbing. That plumbing already exists and runs today --
  `script_generator.py`'s `join_universe_filter_sources()` reads
  `config["universe_filter_join_sources"]` and point-in-time joins any
  non-CRSP-native column onto the returns panel before `filter_universe`
  runs, the same mechanism `compute_signal`'s own input already uses.
  Added `universe_filters: [{field: ceq, op: gt, value: 0}]` +
  `universe_filter_join_sources: {comp_funda: [ceq]}` -- `ceq` (Compustat
  Annual's "Common/Ordinary Equity - Total") is a single raw column, not
  the paper's full book-equity waterfall used elsewhere for other factors
  (prefer SEQ, else CEQ+PSTK, else AT-LT) -- a reasonable proxy, not a
  byte-exact match; documented as such. Verified end-to-end with
  `registry.build_config(asset_growth_resolved_spec(), HXZ_STANDARD_CONFIG)`
  producing the expected `universe_filters`/`universe_filter_join_sources`
  with no engine changes required. Updated `docs/step6.md` (gap #5,
  Decision C) and `docs/cz-reference.md` §7 to match. 73 targeted tests
  green (added `test_registry_resolved_method_spec.py`/
  `test_script_generator_resolved_method_spec.py` to the run to cover the
  join-sources path specifically).

### `HXZ_STANDARD_CONFIG` moved to a single YAML source + fidelity fix, reversing Decision C (2026-08-16)

Consolidated the `standardized_hxz` track's config into
`data/reference/hxz_standard_config.yaml` -- the single canonical source,
loaded via new `src.infra.reference.load_hxz_standard_config()`/
`HXZ_STANDARD_CONFIG`. `src.steps.step6_dual_track_controller.
HXZ_STANDARD_CONFIG` is now a re-export (`from src.infra.reference import
HXZ_STANDARD_CONFIG as HXZ_STANDARD_CONFIG`), so existing imports elsewhere
(`backend/routers/replication.py`, etc.) keep working unchanged.

While moving it, actually read this repo's own copy of the HXZ paper
(`docs/Hou 等 - 2020 - Replicating Anomalies.pdf`, previously never
converted/read despite being cited) to verify the provenance claims. Found
2 were wrong -- fixed, reversing the same-day-earlier Decision C
(docs/step6.md §25) that deliberately left this fidelity gap unfixed:

- `rebalance_frequency`: was `monthly`, cited as "the HXZ q-factor
  protocol" -- but the paper actually uses ANNUAL June-to-June sorting for
  annually-measured accounting variables (form deciles end of June, hold
  July(t)->June(t+1)), which is what most factors in this repo are. Fixed
  to `annual`.
- `accounting_lag_months`: was `6`, correctly flagged in the old comment as
  "Fama-French's convention, not HXZ's" but the FF value was kept anyway.
  The paper's own value for non-earnings quarterly data is a 4-month lag
  (earnings use actual report dates). Fixed to `4`.

`breakpoint_source`/`breakpoint_quantiles`/`weighting_rule` were already
correct (NYSE breakpoints + VW + deciles, confirmed in the paper). Updated
`docs/step6.md` (§4 `C_std` row, gap #5, Decision C), `docs/cz-reference.md`
§7, `docs/architecture.md` to match. No test asserted the old
`rebalance_frequency`/`accounting_lag_months` values for this specific
track, so no test changes were needed; full suite green.

Follow-up same day: caught (by the user) that `holding_period_months`
stayed at its old value of `1`, which was only correct paired with the old
`rebalance_frequency: monthly` -- `apply_signal_holding_period` expands
each formation row for `min(holding_period_months, rebalance_step)` months,
and `rebalance_step` for `annual` is 12, so `holding_period_months: 1`
would have held the June-formed cohort for only 1 of the 12 months a real
annual strategy needs (July only, with August-June having no portfolio at
all). Fixed to `12`, matching `original_method`'s own default
(`registry.py`'s `holding_period_months` default is already `12`).

Second follow-up same day, per user request to re-verify field-by-field
against the paper and delete the accumulated verbose comment history:
re-read the paper text again and found the FIRST fix above had actually
introduced a NEW error -- `accounting_lag_months` was changed to `4`, but
that literal "4-month lag" quote is for a DIFFERENT regime (monthly-
resorted quarterly non-earnings data, `rebalance_frequency: monthly`), not
the `annual` regime this config actually uses. The paper never states an
explicit lag number for annually-measured variables -- "end of June"
formation from "fiscal year ending in calendar year t-1" data only implies
the same ~6-month lag as Fama-French. Reverted to `6` (now correctly
equal to `original_method`'s own `SENSIBLE_DEFAULTS`, not a divergence).

Also found `universe: "NYSE + AMEX + NASDAQ, exchcd in (1,2,3), shrcd in
(10,11)"` (a plain string) was NEVER read by the engine at all --
`BacktestExecutor.filter_universe()` only reads the structured
`config["universe_filters"]` (field/op/value list); the `universe` string
key is accepted by `registry.build_config`'s override validation (so it
never errored) but has zero actual filtering effect. The `shrcd in
(10,11)` claim was also unverifiable against this paper -- never
mentioned. Replaced with real `universe_filters`: `exchcd in (1,2,3)`
("NYSE, Amex, and NASDAQ stocks", stated directly) and `siccd not_between
(6000, 6999)` ("We exclude financial firms", the paper's general sample
criterion). Left OUT the same sentence's "negative book equity" exclusion
-- book equity isn't a native returns-panel column, so applying it needs a
resolved Compustat concept mapping this config layer doesn't have; recorded
as a known gap rather than faked. Correctly did NOT add a price screen --
the paper explicitly states it imposes none ("microcaps are included").
`_ABLATION_SWITCH_TO_CONFIG_KEY["universe"]` (`step6_dual_track_controller/
__init__.py`) updated to point at `universe_filters` instead of the dead
`universe` key.

Rewrote `data/reference/hxz_standard_config.yaml`'s comments from scratch
(deleted the old verbose "Decision C reversed" narrative) as short,
per-field paraphrased citations. Updated `docs/step6.md` (§4 `C_std` row,
gap #5, Decision C) and `docs/cz-reference.md` §7 to match the corrected
values and citations. Full targeted-test suite green (44 tests across
`test_dual_track_controller.py`/`test_batch_invalidation.py`/
`test_experiment_plan_matrix_merge.py`/
`test_step6_dual_track_resolved_method_spec.py`/
`test_backend_cz_config_api.py`/`test_calendar_rebalance.py`/
`test_formation_universe_eligibility.py`).

### Fix: C&Z's `Return` is "% Monthly", not a decimal fraction -- was off by 100x (2026-08-16)

`data/CZ code/SignalDoc-Browser.html` labels the column `Return (% Monthly)`
-- a raw value of `1.73` means 1.73% monthly, not the decimal fraction
(0.0173) this engine's own `RunMetrics.mean_return` uses everywhere else.
`_profile_from_row` (`src/infra/reference/__init__.py`, shared by both the
local-CSV and live `openassetpricing` paths) now divides by 100, so
`CZReferenceProfile.mean_return` -- and therefore the step6 UI's
"Reported (reference)" column -- is on the SAME scale as our own computed
metrics instead of silently 100x too large. Updated
`tests/test_cz_reference_profile.py`'s expected values accordingly. Full
suite: 656 passed, 18 skipped.

### step6 UI: move C&Z query's config diff / raw fields / reported performance out of the request card, into the Result panel only (2026-08-16)

`Step6CzConfigPreview` (the "Run against C&Z's actual configuration"
section) no longer renders the ①②③ config diff table, SignalDoc raw
fields, or C&Z's reported performance itself -- those already show (via the
earlier `onDataChange` lift) in the Result panel, so showing them twice was
redundant. The request card now only shows the query controls, a
mismatch/error message, and the confirm checkbox; `onDataChange`'s payload
gained a `raw` field so the Result panel can render the SignalDoc raw
fields too. Frontend type-check + `npm run build` both clean.

### step6 UI: Cross-track comparison uses in-sample metrics, not the full extended period (2026-08-16)

Prompted by manually investigating a session where ①/② looked wildly
different: the comparison was mixing the engine's full extended sample
(hundreds of months past publication) against the paper's/C&Z's reported
numbers, which only ever cover the paper's OWN original sample window --
not an apples-to-apples comparison. `Step6Output`'s "Mean return"/"t-stat"/
"Sharpe"/"Alpha (FF3)" columns now read `metrics.by_sample_period.insamp`
(same in-sample window "Reported (reference)" is already on) when a run's
config carried sample_start_year/sample_end_year/publication_year, falling
back to the full-period numbers otherwise (never blank). An "(in-sample)"
tag marks cells using the narrower window. `n_months` follows the same
in-sample/full-period rule so it stays consistent with the return/t-stat
shown next to it. Frontend type-check + `npm run build` both clean.

### step6 UI: event log timestamps + newest-first, drop "Experiment batch" card, Cross-track comparison shows paper's/C&Z's reported performance (2026-08-16)

- Events card: each line now shows `[timestamp] [step] stage.event detail`
  (was missing the timestamp entirely) and renders NEWEST first (was
  oldest-first, so the newest entry required scrolling).
- Removed the step6-specific "Experiment batch" result card
  (`Step6BatchSummaryCard`, now unused/deleted from imports) -- step 6 now
  falls through to the generic `resultCard`, which already carries the
  ①②③ config-diff table (added earlier today) and the job log; no
  information was lost, the batch-consistency badge is still visible in
  `Step6Output`'s own header.
- `Step6Output`'s "Cross-track comparison" table gained a "Reported
  (reference)" column: shows the paper's own reported headline number next
  to ① (`extractPaperReported()`, pulled straight from the request's `spec`
  JSON -- `MethodSpec.paper.reported_results`'s primary metric, no extra API
  call) and C&Z's own reported number next to ② (`cz_reported` from the
  step6 UI's live C&Z-config query). ③ intentionally has no reference
  number here (HXZ's standardized protocol was never meant to match a
  reported result). Plumbed `paperReported`/`czReported` as new optional
  props through `StepOutputView` into `Step6Output`.

Frontend type-check + `npm run build` both clean for this entry.

### step6 UI: ①②③ config diff also shows in the Result panel immediately, not after the run finishes (2026-08-16)

Extracted the ①②③ resolved-config comparison table into its own
`Step6ConfigDiffTable` component and lifted its data (`resolvedConfigs`/
`preview.config_override`) out of `Step6CzConfigPreview` into
`SessionDetailPage` via a new `onDataChange` callback. It's now ALSO
rendered at the top of the "Result" panel (`resultCard`) for step 6,
unconditionally -- not gated on the job finishing. Since every value in
that table is already known client-side the moment ② is queried (no
backtest execution needed to know a config), the Result panel now shows it
the instant it's available, rather than only after `useTrackConfigs` picks
up `comparison.json` once the whole batch of real backtests completes.
The request-card copy (shown right under the query button) is unchanged.
Frontend type-check + `npm run build` both clean.

### step6 UI: block "Run" until ②'s config is queried + confirmed (2026-08-16)

When ② is checked (`step6CzEnabled`) but `cz_config_override` hasn't been
confirmed yet, both "Run" buttons ("Run 6. Multi-track experiment" and
"Re-run from upstream output") are now disabled with an inline hint
("query C&Z's config and confirm it below before running, or uncheck ②").
Previously it was possible to click Run with ② checked but never queried,
silently submitting a batch without ②'s track and no indication why. The
①②③ resolved-config diff table (`Step6CzConfigPreview`, added earlier
today) already stays visible after Run is clicked -- it lives in the
request card, which the run mutation doesn't unmount -- so no separate
change was needed for that. Frontend type-check + `npm run build` both
clean (also fixed a missing `cn` import surfaced by this edit).

### step6: reuse step5's ① run unconditionally, no hash validation (2026-08-16)

`MultiTrackController.run_experiment`/`run_from_matrix` gained a
`reuse_original_run`/`reused_baseline_run` param: when given an
already-persisted `original_method` `RunRecord`, it's deep-copied under a
NEW `run_id` (so it never overwrites the original run's own evidence-store
artifact) and included directly in the batch instead of re-executing ①.
`backend/routers/experiments.py`'s `/steps/6/experiment` resolves this from
the session's own latest successful step5 attempt (`run_original=True`
only). Per explicit instruction, this is UNCONDITIONAL reuse -- an earlier
version of this change added exact code/spec/config/snapshot-hash matching
before allowing reuse (see the now-superseded 2026-08-16 decision-log entry
"C_cz preview: live openassetpricing call..." era discussion); that
validation was removed along with its supporting `_reusable_baseline_error`
method and the now-unused `src.infra.hashing.snapshot_manifest_hash` import.
Tests simplified to match (`tests/test_baseline_run_reuse.py`,
`tests/test_backend_experiment_baseline_reuse_api.py`). Full suite: 656
passed, 18 skipped.

### step6 UI: cite HXZ paper in ③'s explanation (2026-08-16)

③'s subtext now names the source: "Hou, Xue & Zhang (2020, RFS) 'Replicating
Anomalies' standard rules, same for every paper -- not from the paper"
(matches the citation already used in docs/cz-reference.md), instead of the
unattributed "fixed standard rules". Frontend type-check clean.

### step6 UI: explain each ①②③ setup's source, add an ② enable/disable toggle (2026-08-16)

`Step6VersionsPicker` now has three checkboxes, all checked by default,
each labeled with where its config actually comes from: ① "agent-extracted
from the paper", ② "pulled from the openassetpricing library -- query &
confirm below", ③ "fixed standard rules, same for every paper -- not from
the paper". ② has no `run_*` request field of its own -- its checkbox only
enables/disables the `Step6CzConfigPreview` section below (visually greyed
out + non-interactive when unchecked); unchecking it also clears any
already-confirmed `cz_config_override`, so ② never silently runs from a
stale prior confirmation while its checkbox is off. Frontend type-check +
`npm run build` both clean.

### step6 UI: simplify "which versions to run" to plain ①②③, drop ablation/factorial switches + raw JSON view (2026-08-16)

Replaced `Step6TrackPicker` (run_original/run_standardized checkboxes plus a
6-switch "test one change at a time" + collapsible "test changes together"
factorial section) with a plain `Step6VersionsPicker`: just the ① paper's
setup / ③ standardized setup checkboxes, labeled with the ①②③ numbering used
everywhere else in this UI now that `Step6CzConfigPreview` (② ) exists.
Per-field ablation/factorial switches have no UI control anymore -- the
three-track ①②③ comparison is the whole model this page exposes; the
backend fields (`ablation_switches`/`factorial_switches`) and the yaml
matrix path are untouched for anyone who still wants finer-grained control.
`lib/steps.ts`'s step6 request template default changed from
`ablation_switches: ["breakpoint", "weighting"]` to `[]`, since there's no
longer a visible control explaining why those two would silently run.

Also hid the raw request-body JSON textarea for step 6 specifically (still
shown for every other step) -- `spec`/`plugin`/`snapshot_id` are already
set via `MethodSpecPicker`/`SnapshotPicker`, and `run_original`/
`run_standardized`/`cz_config_override` via the two pickers above; nothing
on step6's request body needs hand-editing anymore.

Frontend type-check + `npm run build` both clean; no backend changes in
this entry.

### step6 UI: C_cz preview + confirm flow, `cz_actual_config` track (2026-08-16)

New human-in-the-loop path to actually run track ② (`C_agent` signal + C&Z's
real config) from the session UI, per docs/step6.md gap #1:

- `src/infra/reference/__init__.py`: added `fetch_cz_reference_profile_live()`,
  a live equivalent of `load_cz_reference_profile()` via the
  `openassetpricing` package (`OpenAP(release_year=...).dl_signal_doc()`)
  instead of a local `SignalDoc.csv` copy -- no local file path to keep in
  sync. Pinned to a new `DEFAULT_OPENAP_RELEASE_YEAR = 202510` constant
  (never `None`/"latest") so two reviews of the same factor can't silently
  see different C&Z data. Refactored the CSV-row and live-DataFrame-row
  parsing into one shared `_profile_from_row()` (was two independent
  mappings, now one, with NaN-safe numeric/string coercion for the live
  DataFrame path's `NaN`-instead-of-empty-string convention).
- `src/infra/reference/manifest.py`: new hand-verified
  `CZ_FACTOR_ACRONYM_MANIFEST` (`factor_id -> C&Z acronym`), seeded with
  `AssetGrowth` only; add one confirmed entry at a time.
- `backend/routers/reference.py` (new): `GET /api/reference/cz-factors`
  lists the manifest.
- `backend/routers/replication.py`: `GET /api/sessions/{id}/steps/6/cz-config`
  -- preview-only (never runs a backtest), retries the live fetch up to 3
  times on failure, logs every attempt + the final outcome to the session
  event log, returns SignalDoc raw fields + the derived config override +
  C&Z's own reported return/t-stat (reference only).
- `ExperimentPlan`/`ExperimentRequest` (`step6_dual_track_controller`,
  `backend/routers/experiments.py`): new `cz_config_override` field: when
  set (only after human confirmation in the UI), `_plan_to_matrix` adds a
  `cz_actual_config` track alongside `original_method`/`standardized_hxz` in
  the same batch.
- Frontend: new `Step6CzConfigPreview` card (`SessionDetailPage.tsx`) --
  dropdown (not auto-matched to the session's own factor; flags a mismatch
  but doesn't block it) + manual "Query C&Z config" button + review panel
  (raw fields/derived config/C&Z's reported numbers) + a confirm checkbox
  that sets `cz_config_override` on the step6 request.

New tests: `tests/test_cz_reference_profile.py` (live-fetch, NaN handling),
`tests/test_cz_factor_manifest.py`, `tests/test_backend_cz_config_api.py`
(mocked network, retry/give-up/eventual-success paths),
`tests/test_experiment_plan_matrix_merge.py` (`cz_actual_config` track
wiring). Full suite: 650 passed, 18 skipped, no regressions. Frontend
type-check clean.

### Fix bridge-track identification_by_track bug (docs/step6.md §23.3) (2026-08-16)

`_derive_identification_level` (`experiment_spec.py`) now counts "axes
moved" (differing config keys + the signal-source axis
(`signal_input_ref`) + the data-vintage axis (`snapshot_ref`)), not just
the resolved-config-key diff count -- a bridge track that also changes a
config key now correctly resolves to `unidentified` (2 axes moved), and a
pure signal-only bridge now correctly resolves to `controlled` (1 axis
moved) instead of always `unidentified` regardless of the signal swap.

Separately, `MultiTrackController.run_from_matrix` (`step6_dual_track_
controller/__init__.py`) previously never added a bridge track's name to
`identification_by_track`, so bridge runs got NO `family`/
`identification_level` log line at all, regardless of what the (now-fixed)
derivation above produced -- a track that changed both the signal and
config axis was silently never flagged `unidentified`. Fixed by recording
`identification_by_track[exp.name]` on the bridge-track success path too.

New tests: `tests/test_experiment_matrix.py` (axis-counting derivation),
`tests/test_bridge_track_wiring.py` (labeling now reaches the `RunRecord`
logs for both the pure-bridge and bridge-plus-config-override cases). Full
suite: 639 passed, 18 skipped, no regressions.

### Phase 1 gap #1 + gap #2: `C_cz` runnable config + `formation_lag_months` engine key (2026-08-16)

Added `cz_profile_to_config_override()` (`src/infra/reference/__init__.py`)
converting a `CZReferenceProfile` (SignalDoc-parsed C&Z metadata) into a
`registry.build_config(..., overrides=...)`-compatible dict -- `C_cz` is now
a runnable config (docs/step6.md gap #1). Falls back to C&Z's OWN house
defaults (EW / 5 groups / full-sample, `01_PortfolioFunction.R:83-93`) when
SignalDoc is blank, not the engine's different defaults; unexpected
`stock_weight`/`quantile_filter` values raise rather than silently guess.

Added `formation_lag_months` as a new `registry`/`BacktestExecutor` config
key modeling C&Z's global, undocumented 1-month portfolio-formation lag
(`signal[, yyyymm := yyyymm + 1]`, gap #2). Defaults to `0` (no-op --
verified byte-identical on the full test suite, 636 passed); applied in
`BacktestExecutor._apply_formation_lag` AFTER `_validate_annual_formation_month`
so paper-fidelity validation still checks the MethodSpec's true stated
formation month, with the lag then shifting the calendar the hold-window
expansion and `self.formation` cross-section actually run on. Only ever
non-zero via `cz_profile_to_config_override` (`formation_lag_months=1`),
per the user's requirement that default behavior stays unchanged and only
the C&Z track is affected. New tests: `tests/test_formation_lag_months.py`,
extended `tests/test_cz_reference_profile.py`.

### step6.md: attribution methodology fix + 4 design decisions resolved (2026-08-16)

Replaced the additive-on-t-value attribution example (§4a) and the
"factorial = optional Phase 3" framing (§4c) after review found t-value
decomposition mathematically invalid (t is a ratio, not additive). New
approach: attribution is done on mean monthly return μ (which is
approximately additive), via full factorial + averaged main/interaction
effects when the differing-field count is ≤5 (exact, zero residual);
OAT is demoted to a fallback for >5 fields. t-value changes are now
explained separately via the exact log identity
`log t = log μ − log σ + ½ log N` (three channels sum exactly, no
residual). Added a mandatory paired significance test (differenced return
series over the overlapping-months intersection) before any field can be
called "important". Proposed new `ReplicationDiffResult` fields
`paired_test` and `t_channel_decomposition` (not yet implemented in code).

Also moved gap #2 (engine missing C&Z's 1-month portfolio-formation lag,
`yyyymm + 1`) from "Phase 2 external-dependency" to "Phase 1 blocker" --
it has no external dependency and is part of `C_cz`'s own definition, so
track ② depends on it. Recommended fix: a new `formation_lag_months`
registry menu key (default 0) rather than a hardcoded switch.

Resolved 4 outstanding design decisions (recorded in new §25): (A) Q3
("standardization sensitivity") stays demoted to calibration/background,
not a contribution -- C&Z already published VW-decile variants
(`30_PredictorAltPorts.R`). (B) `cz_bridge` pivots from re-implementing
C&Z's formula to extracting C&Z's implicit config facts (lag, missing
policy, etc.), with a new requirement that the signal-adapter layer (sign
convention, 1-month lag alignment) gets unit tests, since both are
silent-failure risks. (C) `HXZ_STANDARD_CONFIG`'s lag fidelity gap is not
fixed; renamed `C_hxz` -> `C_std` throughout Part I/II and reframed as
"HXZ-style" (three knobs only, not the full HXZ protocol) rather than
faithfully reproducing HXZ. (D) Full step6 restructure per §23 (comparisons
as first-class, grid-coordinate tracks) is deferred until Phase 1 produces
real numbers; the one exception pulled forward now is fixing the bridge-
track `identification_by_track` bug (§23.3, a bridge track that changes
both the signal and config axis is never flagged `unidentified` -- a real
bug, not a design question).

Recorded a deferred prerequisite in `docs/todo.md`: Q1 currently treats
`C_agent` as a single draw from a stochastic LLM extraction process with no
measured run-to-run (within-agent) dispersion, so the measured
agent-vs-C&Z disagreement cannot yet be separated from LLM sampling noise;
Q1 results must carry this as an explicit upper-bound limitation until
that dispersion is measured.

### step6.md: 把实验网格拆成 Phase 1/2/3，加入 OAT/factorial 说明与举例 (2026-08-16)

`step6.md` §4 重写为 Phase 1（①②③ + 两组 OAT，只用 agent 信号，核心，
零外部依赖）/ Phase 2（④⑤⑥，引入 C&Z 信号，含 4 条信号适配层风险清单：
符号约定、重复滞后、1 个月组合滞后错位、样本对齐）/ Phase 3（factorial，
默认跳过，仅 residual 偏大或验证 weighting×breakpoint 交互预测时补跑）。
每个 phase 附"能得出的结论 / 不能得出的结论"边界说明，Phase 1 附一个虚构
数值例子演示 OAT 归因的具体计算方式，并补充 t 值应拆成均值/标准误两部分
解读的提醒（避免把"因子真的变弱"和"估计噪声变大"混为一谈）。Part V 下一步
按 phase 重新排序。

### step6.md: 合并 plan.md + step6 研究设计，并补入 C&Z 源码调研结论 (2026-08-16)

`plan.md`（step6 实现现状描述）已合并进 `step6.md` 并删除，避免两份规划文档
分叉。新 `step6.md` 分四部分：研究设计（权威）/ 已查证的事实基础 / 当前实现
快照（标注为可能因重构而过时）/ 现状与设计的差距。

新增的调研结论（全部来自 `data/CZ code/` 源码，非推测）：C&Z 有一套与 step2
同构的默认值层（`01_PortfolioFunction.R:83-93`，EW / 六月 / 月度 / 五分组 /
全样本断点）；年度 Compustat 固定 6 个月会计滞后、季度用 `max(datadate+3, rdq)`；
所有因子无差别施加 1 个月组合构建滞后（`yyyymm + 1`，未文档化，是校准的主要
风险点）；`Portfolio Period` = 再平衡间隔而非持有期，无重叠组合。212 个
predictor 中 `Quantile Filter` 99% 落默认（全样本断点）——即 HXZ/C&Z 之争最
核心的断点差异在 C&Z 侧是沉默默认值而非论文主张。另确认 C&Z 已发布 VW-decile
等标准化变体（`30_PredictorAltPorts.R`），因此"标准化敏感度"不能作为本项目
贡献，只能作校准与背景。

### Renamed `DualTrackController` to `MultiTrackController` (2026-08-15)

The class runs an arbitrary N-track experiment matrix (original,
standardized, ablations, factorials, sweeps, bridge tracks), not just two
tracks -- "dual" no longer described what it does. Renamed via workspace
rename-symbol (38 edits, 8 files: `src/steps/step6_dual_track_controller/`,
`src/pipeline.py`, tests) plus manual doc/comment updates across `AGENTS.md`,
`app.py`, `backend/routers/*.py`, `docs/architecture.md`,
`docs/multi-config-evidence-plan.md`, `docs/roadmap.md`,
`docs/tools-plus-llm-plan.md`. The module/directory name
(`step6_dual_track_controller`) and `ExperimentPlan`'s "dual" framing are
intentionally left as-is for now (larger blast radius via import paths) --
see `plan.md` for the still-open discussion. `docs/decision-log.md` and
earlier `CHANGELOG.md` entries keep the old name since they're historical
records of what was true at the time.

### Step6 gained a per-track resolved-config comparison table (new backend endpoint) (2026-08-15)

User wanted step6's output to show each track's actual resolved config
(breakpoint_source, weighting_rule, sample years, etc.) side by side
instead of a raw MethodSpec JSON blob. That data (`registry.build_config()`'s
output per track) turned out to already be written to disk as
`comparison.json` -- a side effect of step6's own `run_from_matrix`/
`_finalize_batch` (`write_comparison_summary`,
src/steps/step5_backtest_runner/__init__.py) -- but the only existing read
endpoint, `GET /steps/7/comparison`, requires a step7 attempt to already
exist on the session, so it wasn't usable straight after step6.

Added `GET /steps/6/track-configs?experiment_batch_id=...` in
`backend/routers/replication.py`: same batch→factor_id→comparison.json
resolution and staleness check as the step7 POST endpoint, but read-only
(never registers a step7 attempt or otherwise touches session state) and
returns just `{track: config}` instead of the full bundle.
`tests/test_experiment_replication_diagnosis_api.py` (9) still passes.

`Step6Output.tsx` renders this as a "Config per track" table: rows =
every resolved config key (union across tracks), columns = tracks in the
same baseline-first order as the metrics table, a cell highlighted (amber)
whenever it differs from the baseline track's value for that key. The
step6 request textarea (which still needs the raw `spec` JSON to submit a
valid request) was left alone -- this only addresses where the config gets
DISPLAYED, in the Step-output area. `npm run build` passes.

### Simplified Step6TrackPicker's wording -- plain language, factorial section collapsed by default (2026-08-15)

User found "ablation switches"/"factorial switches" too jargon-heavy.
Reworded `Step6TrackPicker` (`SessionDetailPage.tsx`): "Which versions to
run" (original_method/standardized_hxz), "Test one change at a time"
(ablation, with a one-line hint per switch e.g. "Weighting rule
(equal-weight vs. size-weight)"), and "Advanced: test changes together
(usually not needed)" for factorial, now a collapsed `<details>` since it's
the less commonly needed of the two. No behavior change, same
`ablation_switches`/`factorial_switches` keys underneath. `npm run build`
passes.

### Step6's default snapshot_id changed from synthetic demo data to real WRDS data (2026-08-15)

`lib/steps.ts`'s step6 `requestTemplate` defaulted `snapshot_id` to
`"synthetic_demo_v1"` -- unless a user manually picked a different one from
`SnapshotPicker`, step6's multi-track experiment silently ran on fake demo
data while step5 always runs against `REAL_WRDS_SNAPSHOT_ID`
(`backend/state.py`), making the two steps' numbers incomparable. Default
is now `"real_wrds_local_v1"`, matching step5. Still overridable via the
picker. `npm run build` passes.

### Step6 request editor gained a track picker -- no more hand-editing the JSON to choose tracks (2026-08-15)

Added `Step6TrackPicker` in `SessionDetailPage.tsx` (same slot pattern as
step3's `MethodSpecPicker`/`SnapshotPicker`): checkboxes for
`run_original`/`run_standardized`, plus one checkbox per ablation switch
and one per factorial switch, mirroring `_ABLATION_SWITCH_TO_CONFIG_KEY`'s
6-entry menu (`breakpoint`/`weighting`/`lag`/`missing`/`rebalance`/
`universe` -- `src/steps/step6_dual_track_controller/__init__.py`, the
only switch names the backend actually accepts). Reads/writes the same
request-body JSON textarea the picker sits above, so it stays in sync with
manual edits either direction. `npm run build` passes.

### Step6's default request now runs 4 tracks instead of 1 (2026-08-15)

`lib/steps.ts`'s step6 `requestTemplate` previously defaulted to
`run_standardized: false` and empty `ablation_switches`/`factorial_switches`
-- a fresh session's step6 only ever ran `original_method`, leaving the new
cross-track comparison table with a single row. Defaults now: `run_original:
true`, `run_standardized: true`, `ablation_switches: ["breakpoint",
"weighting"]` (4 tracks total: `original_method`, `standardized_hxz`,
`ablation_breakpoint`, `ablation_weighting`). Still just a starting point in
the request textarea -- freely editable per run. `npm run build` passes.

### Step6 UI: cross-track comparison table + batch status, replacing the per-track stacked tables (2026-08-15)

New `Step6Output.tsx` (`Step6BatchSummaryCard` for the Result slot,
`Step6Output` for the Step-output card), replacing the inline block in
`StepOutputView.tsx` that stacked one `MetricsTable` per track:

- **Batch status bar**: `experiment_batch_id`, track count, and a
  `batch_invalidated` banner (+ reason) when true. Deliberately did NOT add
  a separate "frozen_plugin_hash consistency" indicator -- confirmed in
  `src/steps/step6_dual_track_controller/__init__.py` that
  `batch_invalidated` already IS exactly that check's result (any
  non-bridge track's `code_hash` diverging from `frozen_plugin_hash`), so a
  second indicator would just duplicate it.
- **Cross-track comparison table**: rows = tracks, `original_method` pinned
  first as a best-effort baseline stand-in (step6 has no `baseline_track`
  concept of its own -- that's only computed in step7's `bundle.py`),
  bridge tracks get their own badge, t-stat shows a delta vs baseline.
- **Overlay chart** (existing `MultiTrackChart`) moved below the table.
- **Debug section**: per-track `code_hash`/`frozen_plugin_hash`/
  `config_hash` table, plus `repair_history` (this one IS persisted on
  `RunRecord`, unlike step4's job-transient one).

Known accepted gap (discussed with user, not fixed): the auto-refreeze
mechanism's `refreeze_attempts` count has NO API surface at all currently
(not in the job result, not on `RunRecord`) -- a batch that self-repaired
and reconverged looks identical to one that never needed repair. Left as a
future backend change if ever wanted; `batch_invalidated` alone still
correctly reports whether the batch's comparisons are trustworthy.

Also extended `lib/evidence.ts`'s shared `RunRecord` type with
`experiment_batch_id`/`frozen_plugin_hash`/`batch_invalidated`/
`batch_invalidation_reason`/`repair_history` instead of ad-hoc casts.
`npm run build` passes.

### "Paper reported" row: shortened the label, routed the paper's alpha into the correct alpha column (2026-08-15)

Two bugs in `Step5Output.tsx`'s breakdown table's paper row:
- The label inlined the metric's full `label` (e.g. "Value-weighted
  Fama-French three-factor monthly alpha, low minus high asset-growth
  deciles, all firms"), making the row unreadably wide. Shortened to plain
  "Paper reported", with the full description moved to a `title` tooltip.
  instead of dropped.
- The paper's `estimate` was always placed in the "Mean monthly return"
  column, even when the metric's own `estimand` is `"alpha"` -- so a
  paper-reported FF3 alpha never showed up in any of the three alpha
  columns at all. Added `paperMetricColumn()`, which routes the estimate
  to `alpha_capm`/`alpha_ff3`/`alpha_ff5` based on the metric's
  `adjustment_model` (falls back to the mean column for a raw/other
  estimand). `npm run build` passes.

### Post-publication date range now uses the return series' actual last year, not "present" (2026-08-15)

`periodRange()` in `Step5Output.tsx` hardcoded the post-publication segment
as `{publication_year+1}–present`, assuming the data runs up to today --
wrong whenever the underlying snapshot's data ends earlier than that. Now
takes the ACTUAL last year from the fetched `return_series.csv` (already
computed for the "All (full sample)" row's own date range) and uses that as
the upper bound instead. `npm run build` passes.

### `alpha_capm`/`alpha_ff3`/`alpha_ff5` now computed per sample-period segment too (2026-08-15)

Previously full-sample-only (`BacktestExecutor.compute_factor_alphas()` ran
once against the whole `long_short` series); `compute_metrics`'s
`by_sample_period` (in-sample/between/post-publication) only ever broke out
mean/t-stat/Sharpe, not the factor alphas. Added
`_sample_period_segments()` -- the same year-boundary logic as
`_sample_period_metrics`, but returning each segment's full DataFrame
(`yyyymm`+`ls_return`, needed to merge against `factors`) instead of just
the return Series -- kept as its own function so a bug there can never
touch the existing, golden-number-tested `_sample_period_metrics` output.
`run_with_config` now re-runs `compute_factor_alphas` once per segment and
merges the result into that segment's own `by_sample_period` entry.
`tests/test_sample_period_metrics.py`/`test_factor_alphas.py` (19) and the
broader backtest-engine/eligibility suite (21 passed, 1 pre-existing skip)
still pass. `Step5Output.tsx`'s breakdown table gained three columns
(Alpha CAPM/FF3/FF5) so every row -- not just "All (full sample)" -- shows
its own alpha; the redundant full-sample-only caption line only keeps
`coverage`/`microcap_share` now. `npm run build` passes.

### Step5 UI: removed duplication, switched ReturnChart to a real numeric time axis, unified date granularity (2026-08-15)

Three fixes to `Step5Output.tsx`/`ReturnChart.tsx`:
- **Deduped**: the Result-slot `Step5HeadlineCard` and the Step-output
  breakdown table both showed a per-period mean/t/sharpe table; collapsed
  `Step5HeadlineCard` back to a single compact full-sample glance (3
  numbers), with the per-period detail living ONLY in the Step-output
  table below. Also removed the separate generic "Performance metrics"
  `MetricsTable`, which duplicated the breakdown table's mean/t/sharpe/
  n_months a second time -- the handful of full-sample-only extras
  (alpha_capm/ff3/ff5, coverage, microcap_share) are now one small caption
  line instead of a whole second table.
- **`ReturnChart` X axis**: was a string `category` axis (`dataKey="period"`,
  `interval="preserveStartEnd"`) -- confirmed via disk (`runs/evidence/**`,
  all 883-row files, unchanged) that this was never a data-truncation bug,
  but a category axis with hundreds of points only differs visually by how
  many tick LABELS recharts fits (~24 here), which reads as truncated data
  even though every point is plotted. Switched to a real numeric axis
  (`type="number"`, `dataKey` = decimal year, `domain={['dataMin',
  'dataMax']}`) so ticks are placed evenly across the true date range
  regardless of point count.
- **Unified date granularity**: the "All (engine, full sample)" row showed
  a year+month range (e.g. `195207–202512`) while every other row
  (in-sample/between/post-pub, sourced from `sample_start_year`/
  `sample_end_year`/`publication_year`, which have no month granularity)
  showed year-only. "All" now also shows year-only.

`npm run build` passes.

### Step5's period breakdown now shows date ranges and the paper's own reported result (2026-08-15)

Two changes to `Step5Output.tsx`:
- `Step5HeadlineCard` (the Result-slot card) no longer shows one
  undifferentiated full-sample number; it's now a per-period table (All /
  in-sample / between / post-publication), since a single averaged figure
  can hide whether the effect held up post-publication.
- The "Sample-period breakdown" table (Step output card) gained a "Date
  range" column, computed from `sample_start_year`/`sample_end_year`/
  `publication_year` -- these live only on step3's persisted `config_ref`
  artifact, not on the step5 `RunRecord`, so `Step5Output` now takes a
  `manifest` prop and walks it the same way `Step4RepairCard` already does
  for step3's plugin code (extracted the shared lookup into
  `lib/manifestArtifacts.ts`'s `latestSuccessRef`, deduped from
  `Step4Output.tsx`). Also added a "Paper reported" row sourced from step3's
  persisted `spec_ref` (`spec.paper.reported_results`'s primary metric),
  so the paper's own estimate/t-stat sits directly next to the engine's
  full-sample and per-period numbers for comparison. `npm run build` passes.

### `ReturnChart` now states its own month count/date range (2026-08-15)

User reported step5 showing "882 months" in metrics but the chart looking
like only ~24 months. Verified directly against disk (`runs/evidence/**/return_series.csv`,
`runs/backtest_scripts/results/**/*.csv`): every persisted series is a full,
gapless 882-row run (1952-07 through 2025-12) -- not a data-truncation bug.
The real cause: `XAxis interval="preserveStartEnd"` on a category axis only
THINS the visible tick LABELS to whatever fits the chart's width (recharts
auto-computed ~24 here); every row is still plotted on the line, just very
densely. Added an explicit "`N` months (`first`–`last`)" caption above the
chart in `ReturnChart.tsx` so the true row count is never left to be
inferred from tick density. `npm run build` passes.

### Fixed: Run/Re-run didn't visibly clear a step's stale result (2026-08-14)

`runMutation`'s `onMutate` already reset `jobId`/`syncResult` and removed the
cached `session-step` query, but that query's own background refetch could
immediately re-populate `latestAttempt` with the OLD (still-current on the
backend until the new run actually finishes) attempt, so the Result/Step
output panels never visibly went blank -- looked like clicking re-run did
nothing. Added `isRerunning` (`runMutation.isPending || job.status in
{pending, running}`) in `SessionDetailPage.tsx` and gated every
step's Result-slot card (`Step3ComputeSignalCard`/`Step4RepairCard`/
`Step5HeadlineCard`/the generic diagnostics block) and the "Step output"
card behind it, showing a plain "Running…" placeholder instead of
whatever's cached until the new result actually lands. `JobLogPanel` stays
visible throughout (that's the one thing that SHOULD show live progress).
Steps 1/2 use their own separate `MethodSpecWorkflowPanel` state, not
`runMutation` -- out of scope here. `npm run build` passes.

### Fixed: step5/6's frontend looked runs up by the session's factor_id, which can silently differ from the run's own factor_id (2026-08-14)

Found while debugging "ran step5 but nothing shows" during the step5 UI
build. A session's `factor_id` is a freeform string typed when the run is
created (`RunsPage`); a `RunRecord.factor_id` is `spec.paper.factor_id`
(`_spec_factor_id` in `src/steps/step5_backtest_runner/__init__.py`) --
nothing enforces the two match. `GET /api/runs/{factor_id}` filters strictly
by that path param, so `Step5Output`/`Step5HeadlineCard`/step6's block
querying `/api/runs/{session.factor_id}` silently returned an empty list
whenever the two strings didn't match byte-for-byte, even though the run
existed and was fully persisted. Fixed by having `lib/evidence.ts`'s
`fetchRuns()` hit the GLOBAL, unscoped `GET /api/runs` and having every
caller find its run by `run_id` (always known from `execution_ids`) instead
of by factor_id -- and, critically, using the FOUND run's own `factor_id`
for every subsequent evidence/download call, never the session's. Removed
the now-fully-unused `factorId` prop from `StepOutputView`/`Step5Output`/
`Step5HeadlineCard` as part of this. `npm run build` passes.

### Fixed: step4's `validation.json` artifact was written to step3's directory, making it 404 for the frontend (2026-08-14)

Found while building the new step4 "Step output" panel (`Step4Output.tsx`,
`docs/step-output-display-plan.md`): `/steps/4/validate` in
`backend/routers/sessions.py` wrote `{sha}.validation.json` into `step3_dir`,
but recorded it as step4's own `validation_ref` output_ref. The generic
artifact endpoint (`GET /steps/{step}/artifact/{filename}`) always resolves
`filename` against THAT step's own directory, so fetching step4's
`validation_ref` from `step4_dir` always 404'd -- the report existed on disk,
just one directory over. Changed the write target to `step4_dir` (already in
scope in that closure). Pre-existing bug, not introduced by this session;
apparently never caught because nothing previously read `validation_ref`
back through the artifact endpoint. `tests/test_session_api.py` (16 tests,
needs `source .venv/bin/activate` -- system `python3` lacks `fastapi`) passes
unchanged after the fix.

### `build_config`'s `substitutions` entries now record which config key they resolve (2026-08-14)

Second half of wiring step3's planned "one full config table, every row
annotated with its source" UI (`docs/step-output-display-plan.md`):
`substitutions`' `field` is a human-authored, free-text MethodSpec path
(`Substitution.field_path`, a plain `str`, not an enum -- confirmed by
reading the model and the only real construction site, a test fixture; there
is no reviewer-approval endpoint wired yet) and does not match `build_config`'s
own output keys (e.g. `"portfolio.weighting"` vs. `weighting_rule`), so the
frontend cannot merge a substitution into its config row by string equality.
Added `SUBSTITUTION_FIELD_PATH_TO_CONFIG_KEY` next to `CONFIG_KEY_STAGE` in
`src/steps/step3_codegen/registry.py`, covering every `field_path` seen in
`tests/fixtures/method_specs/*.resolved.methodspec.json` plus
`step2_reviewer/review.py`'s fixed engine-menu paths, and each substitution
entry now carries a `config_key` (`None` when unmapped -- the UI must show an
unmapped entry on its own, never drop it, since this map is best-effort by
construction). Also fixed an editing slip that briefly deleted `stage_of`'s
body while making this change; `tests/test_registry_resolved_method_spec.py`
(23), `tests/test_method_spec_contract.py` (38), and
`tests/test_replication_diagnosis.py` (71) all still pass.

### `build_config`'s `defaults_applied` entries now record the paper's raw pre-clamp value (2026-08-14)

Prep for the step3 UI redesign (see `docs/step-output-display-plan.md`): the
plan calls for one full config table where every row is annotated as
paper-specified / substitution / engine-default, with the paper's original
value shown for all three. `substitutions` already carried `paper_value`,
but `defaults_applied` only recorded the resolved default and a generic
reason string, discarding whatever the paper actually said (or that it said
nothing). Re-deriving that value in the frontend from `spec.json` would mean
reimplementing each config key's own extraction rule (different for nearly
every key) in JS — instead, `_track_clamp`/`_track_or`/`_track_sort_mode`/
`_track_group_type`/the sort-dims trim/the lag-unit-unsupported branch in
`src/steps/step3_codegen/registry.py` now capture the raw value they already
have at hand as a new `paper_value` field on each `defaults_applied` entry
(`ev(val)`, `"unspecified"` string when genuinely absent). Purely additive to
the dict shape; `tests/test_registry_resolved_method_spec.py` (23 tests)
still passes unchanged.

### Plan: rework the step 3-8 output displays in the run-detail UI (2026-08-14)

Added `docs/step-output-display-plan.md` after auditing what each step's
backend artifacts actually contain versus what `StepOutputView.tsx` renders.
The audit found several sections written by the backend but never shown:
step3's `defaults_applied`/`substitutions` menu-clamping audit, step4's
`technical_metrics`/`warnings` and its silent plugin repair, step5's
`by_sample_period`/`runtime_provenance`, step6's `batch_invalidated` and
frozen-hash consistency, and five whole evidence-bundle sections in step7
(`spec_quality`, `menu_deviations`, `bridge_comparison`, `publication_decay`,
`robustness_summary`) plus the `derived.tracks.*.vs_paper` paper-comparison
table. Step8 was the worst case: it renders only `claim.text`, which is
digit-free by construction, so the deterministic figures `render.py`
reinserts never reach the screen — the plan replaces that with the rendered
`diagnosis.md`, which needs one new backend endpoint to serve its content.
No code changed yet.

### Step4 gained an opt-in LLM "faithfulness" check: does compute_signal match the approved formula? (2026-08-14)

Discussed with the user a proposal to run a sample + have an LLM judge
generated-code correctness and loop back to Step 3 on failure. Scoped it down
to ONLY a code-vs-approved-formula faithfulness check (never empirical/
economic correctness -- that stays Review Gate's job, see
docs/decision-log.md's 2026-08-14 entry for the full discussion).

`AdversarialSandbox` now takes an optional `llm_client` (`None` by default,
so every existing/default validation path is unchanged) and, when set, runs
`_check_faithfulness()` after the static checks: an LLM compares
`plugin.code` against `spec.paper.signal.formula` (paper_expression + steps)
and must quote a verbatim substring of each to support a "not faithful"
verdict (`prompts/meta_coder/faithfulness_check.md`) -- an unparsed response
or an unverifiable quote is treated as inconclusive (a warning), never a
failure. A verified mismatch appends to `ValidationReport.errors` (new
`faithful_ok` field) and reuses the EXISTING `RepairLoop` ->
`MetaCoder.repair_plugin` path -- no new loop/retry budget.
`Pipeline(check_faithfulness=True)` wires an already-supplied `llm_client`
into the sandbox (mirrors the existing `run_diagnosis` opt-in pattern for
Step 8). `repair_plugin.md`/its inline fallback now explain how to react to
a "Faithfulness check FAILED" error (fix the implementation of the SAME
quoted approved formula, never invent a different one).
See `tests/test_sandbox_validation.py::TestFaithfulnessCheck`.

### Step4 removed the non-blocking best-effort full-engine smoke test; only `compute_signal` execution is checked now (2026-08-14)

Discussed and agreed the best-effort `BacktestExecutor.run_with_config()`
attempt inside `_check_executes` (`src/steps/step4_validator/__init__.py`)
added complexity without changing any pass/fail decision — it never affected
`report.passed`/`executes_ok`, so it could never actually trigger the repair
loop, and `MetaCoder.repair_plugin` can only rewrite `compute_signal` anyway
(never portfolio-construction/engine-lifecycle code), so a full-engine
failure fed back there would be unactionable noise. Removed the engine
attempt from both the subprocess driver (`_EXECUTE_DRIVER`) and the parent
Python (`engine_error` handling), leaving `_check_executes` scoped to exactly
"join tables the same way the generated script does (`Pipeline.
_build_validation_slice`) -> call `compute_signal` -> only a raised
exception/timeout fails". Full-engine correctness stays Step5's job on full
data, as before. Removed the now-dead `TestFullEngineSmokeTest` class and
`_returns_panel_slice` helper from `tests/test_sandbox_validation.py`.

### 带 `derivation` 的 universe filter 现在自动跳过运行时应用，不再字面量比较（2026-08-13）

延续上一条 changelog 的排查:发现 `compustat_fiscal_year_end >= 2` 这条 filter
之所以能一路无声通过 review/resolve、直到 step4/5 才崩,是因为 `FilterSpec.
derivation` 字段(表示这个条件需要先算出一个派生值,而不是直接拿物理列做字面量
比较)从未被任何代码读取过。用户要求:只要 `derivation != None`,这条 filter
就不应该被当成字面量 op/value 比较去执行。

修复:`src/steps/step3_codegen/registry.py` 的 `_applied_universe_filters`
(唯一被 `config["universe_filters"]` 和 `_universe_filter_join_sources`
共同调用的函数)现在同时排除 `accepted_unapplied` 和 `derivation is not None`
的 filter——两者都不会再进入运行时。`_unapplied_universe_filters`(嵌入
resolved config 的 `unapplied_universe_filters` 审计列表)也同步记录被
derivation 跳过的条目(reason: "derivation not executable by the engine"),
保持"跳过是可审计的,不是静默丢弃"这一原则。刻意没有改动
`ResolvedMethodSpec.unmapped_concepts()`/`unsupported_universe_filters()`
(那是控制 `is_ready`/是否阻断的另一个问题,不在本次改动范围内)。

验证:全量套件 624 passed/18 skipped,零回归。

### session step4 validate 现在真正跑一遍 step5 会跑的完整脚本，不再有"引擎报错只算 warning"的放过机制（2026-08-13）

用户报告：step4 显示 `Validation passed`，step5 用同一个 factor 在全量数据上却
直接崩了（`TypeError: Invalid comparison between dtype=datetime64[ns] and int`，
来自一条把 `datadate`（日期列）和字面量 `2` 直接比较的 universe filter——本意是
"在 Compustat 至少挂了 2 年"这类派生条件，但从未真正被求值成"年数"，这是已知但
未修的 gap，见下方 `compustat_fiscal_year_end` 记录）。追查发现 step4
(`validate_step4_artifact`) 之前只跑 `AdversarialSandbox._check_executes` 这套
宽松的 in-process smoke test：只在内存里对一个小切片调用 `compute_signal`，
只有当这个切片碰巧长得像 returns panel 时才 best-effort 尝试跑一次完整
`BacktestExecutor.run_with_config()`（这次踩雷的 `filter_universe` 就在里面），
而且引擎跑出任何异常都只记 `warning`，从不算失败——所以这个 bug 在 step4 里
从未被真正执行到。

用户明确要求：step4 必须和 step5 跑一模一样的代码（`compute_signal` ->
`BacktestExecutor.run_with_config`），只是数据不同；不允许任何"引擎报错只是
warning"式的放过。改法（只动 `validate_step4_artifact`，没有碰
`AdversarialSandbox`/`RepairLoop` 共享给 `Pipeline.run_from_method_spec`/
`DualTrackController`/`app.py`/`codegen.py` 的部分）：静态检查+
compute_signal 级别的技术修复循环通过之后，新增一个**强制**的第二阶段——把
已验证的脚本原文本真正当子进程跑一遍（`python <script>.py`），用和 step5 execute
一样的 `BACKTEST_DATA_PATH`/`BACKTEST_SIGNAL_DATA_DIR` 环境变量覆盖机制指向
`VALIDATION_SAMPLE_SNAPSHOT_ID` 的小样本数据（而不是 step5 用的
`REAL_WRDS_SNAPSHOT_ID`），非零退出码直接判 `report.passed=False`，不再修复
（和 `execute_step5` 本身"执行失败不自动修复"的姿态一致）。

实现过程中自己踩了一个坑（被测试抓到，不是靠 review）：第一版想直接复用
`BacktestRunner.execute()`，为此用一个新 `track_name="step4_validation"`
重新 `build_script()` 拿路径/config，再把 `built["script_text"]` 换成真正验证过
的原文——但 `execute()` 读 CSV/metrics 是从这次"新 build"算出的
`output_csv` 读回，而脚本里真正写死（不可用环境变量覆盖，只有 DATA_PATH/
SIGNAL_DATA_DIR 可以）的 `OUTPUT_PATH` 仍然是原始脚本的 track（如
`original_method`），两边路径对不上——脚本其实跑成功了，但 `execute()`
去读一个从没写过的 `step4_validation.metrics.json` 时 `FileNotFoundError`。
3 个测试（`test_hard_delete_never_touches_evidence`/
`test_full_chain_matches_golden_numbers`/
`test_execute_rejects_hash_mismatch_against_validated_artifact`）都因此报错。
修复：step4 根本不需要 metrics，只需要成功/失败，所以改成直接
`subprocess.run` 跑这个脚本文件、只看 `proc.returncode`，完全不走
`execute()`的 CSV/metrics 回读那套逻辑。

验证：`tests/test_session_api.py`（16 passed）、`tests/test_backend_api.py`+
`test_step_diagnostics.py`+`test_sandbox_validation.py`（28 passed）、全量套件
624 passed/18 skipped，零回归。

仍未修复（本次只解决"step4 能不能真正暴露这个 bug"，没有解决 bug 本身）：
`099f6e1136bd316c` 这份 MethodSpec 里 `compustat_fiscal_year_end >= 2`
这条 universe filter 依然是错的——它的 `derivation` 字段本来就写明需要
"count_years_since_first_observed"，但引擎的 `apply_universe_filters`/
`_apply_filter_op` 从不读取/执行 `derivation`，只会做字面量比较。真正的修复
需要在 review 阶段拦截（任何 `universe.filters[].concept_id` 若
`derivation` 非空就不该被解析成字面量列比较）或者手动修正/去掉这条过滤器。

### `schema_reference.py` `_walk_model` 递归 bug：composite 字段的 `sub_fields` 被孙子字段污染（2026-08-13）

用户在 Schema Reference 页面发现 `signal` 部分展开树形结构不对。排查发现
`src/infra/models/schema_reference.py::_walk_model` 的 composite（`BaseModel`
嵌 `BaseModel`）分支有真实 bug：`out[path] = _composite_entry(path,
list(nested.keys()))` 在递归调用 `_walk_model(unwrapped, path, nested)`
**之后**才读取 `nested.keys()`，而递归调用本身会把孙子/曾孙字段路径也写进同一个
`nested` 字典（这是故意的，为了让前端能在自己的路径上查到它们）——导致
`sub_fields` 把孙子字段错误地拍平成了当前节点的直接子字段。实测
`signal.formula.sub_fields` 之前包含了 11 项（6 个真正的直接子字段 + `steps`
自己的 5 个孙子字段 `step_id`/`description`/`expression`/`status`/`evidence`），
`signal.estimation` 同样把 `estimation_window`/`measurement_window`
各自的 5 个 `WindowSpec` 叶子字段拍平了进去。前端 `SchemaReferencePage.tsx`
的 `childPaths()` 直接信任 `sub_fields` 是"直接子字段"列表，所以展开 `formula`
节点时孙子字段会作为兄弟节点重复出现、层级不对。

修复：在递归**之前**先用 `unwrapped.model_fields` 算出真正的直接子字段路径
列表，只把这份列表传给 `_composite_entry`，`nested`（含孙子字段）仍然正常
`out.update()` 进全局字典供前端按路径查询，只是不再污染父节点自己的
`sub_fields`。验证：`signal.formula.sub_fields` 从 11 项降到正确的 6 项，
`signal.estimation.sub_fields` 从 17 项降到正确的 7 项。
`pytest tests/test_schema_reference.py`（9 passed）+ 全量套件（518 passed，
32 failed/5 errors 均为环境缺 `pyarrow`/`yaml` 导致，与本次改动无关，逐条核对
确认不含 method_spec/schema_reference 相关用例）验证无回归。

### MethodSpec 信息重复审查记录 + Schema Reference 分组补全 8 个模块（2026-08-13）

用户提出"MethodSpec 有没有信息重复"的讨论。逐条核对了一份真实样本
(`runs/method_specs/resolved/099f6e1136bd316c.resolved.json`) 后写成
[docs/methodspec-redundancy-review.md](docs/methodspec-redundancy-review.md)，
列出 4 处重复点并分类（已修复/建议处理/已知技术债不建议动）。已修复的一处：
`frontend/src/pages/SchemaReferencePage.tsx` 的 `sectionOf`/`SECTION_ORDER`/
`SECTION_LABEL` 之前硬编码只识别 `data`/`signal`/`portfolio`/
`reported_results` 四个前缀，把 `paper`/`sample`/`timing`/`universe` 全部
塞进兜底的 "Top-level" 分组——改为列出 `MethodSpec` 真实的全部 8 个顶层模块，
`other` 只兜底 `factor_id`/`target_name`/`notes`/`schema_version` 这类裸顶层
字段。另外两处（`review.findings` 与 `review.all_high_impact_fields` 的物理
重复、`signal.formula.evidence` 顶层字段确认无消费者）记录在案，等用户确认
后再实现。`npx tsc --noEmit` 无类型错误。

### Schema Reference 页面去重 + 折叠树展示（2026-08-13）

用户反馈 Schema Reference 页面"一口气展示太多，看不过来"。排查发现两处问题：

- `src/infra/models/schema_reference.py`：`_walk_model` 之前会对每一个带
  `evidence: list[EvidenceCitation]` 字段的父路径，把 `EvidenceCitation` 自身的
  `location`/`quote`/`interpretation`/`table_ref`（以及 `table_ref` 里的
  `table`/`row`/`column`）都重新递归展开成独立叶子条目——但这个 citation 结构在
  全 schema 里处处相同，纯粹是同一份信息被复制了 16 遍。改为遇到
  `item_type is EvidenceCitation` 时不再递归展开，只保留父级 `*.evidence`
  这一条 list 摘要（`list_item_fields` 仍列出这四个字段名）。字段总数从 186 降到
  169，去掉的都是纯重复条目。`_notes_for` 顺带给所有 `*.evidence` 路径补了一条
  统一的 fallback 说明文字。
- 确认 `name_in_paper`（早前从 `paper_name` 改名）和 `table_ref` 的
  free-form（非 enum）状态在后端/模型层都已经是对的——之前反馈的"没更新"应是浏览
  器/前端旧构建缓存导致,不是代码问题。
- `frontend/src/pages/SchemaReferencePage.tsx`：把原来"186 个字段全部铺平、每个
  都是一整块详情卡片"的展示方式，改成按 `sub_fields`/`list_item_fields` 组装的可
  折叠树——每个 section 只有一个根节点默认展开，其余节点默认折叠，点击展开才显示
  description/usage/allowed values/example 以及子字段。搜索框仍然保留原来的扁平
  过滤列表（在树里查找深层字段不方便，输入过滤词时临时切换回扁平搜索结果）。
- 验证：`pytest tests/` 624 passed / 18 skipped（无回归），`npx tsc --noEmit`
  无类型错误。

### Universe filter 解析到真实 Compustat 列时，生成脚本自动 join，不再强制 `accepted_unapplied`（2026-08-13）

详细讨论/权衡见 `docs/decision-log.md` 同日条目。实现清单：

- `src/steps/step3_codegen/registry.py`：新增 `_universe_filter_join_sources(paper,
  resolution)`，把已应用（非 `accepted_unapplied`）且 resolve 到「真实注册物理列
  但非 CRSP 原生列」（如 `comp_funda.at`）的 filter 按 `{source: [columns]}` 分组,
  写入新 config key `universe_filter_join_sources`（已注册进
  `KNOWN_CONFIG_KEYS`/`CONFIG_KEY_STAGE`）。
- `src/steps/step3_codegen/script_generator.py`：模板新增
  `join_universe_filter_sources(msf)`,复用 `assemble_signal_master_table_from_
  sources()`（跟 `compute_signal` 自己输入同一套 point-in-time join 机制）把这些
  列左连接到 `msf` 上,在 `main()` 里 `msf` 构建完之后、`compute_signal`/
  `engine.run_with_config` 之前调用——`BacktestExecutor` 本身零改动。
- `src/infra/models/method_spec.py`：`ResolvedMethodSpec.unsupported_universe_
  filters()` 改为只在「resolve 到的列压根没在 `catalog.DATA_CATALOG` 里注册」时
  才拦截（真的没法加载）,不再对「已注册但非原生」的列一律拦截。
- `backend/routers/methodspecs.py`：`_unsupported_universe_filter_findings` 的
  提示文案同步更新（说明 join 机制,提示去 catalog 注册缺失列,而不是笼统地说
  "engine 不支持"）。
- 新增/更新测试：`tests/test_method_spec_contract.py::TestUnsupportedUniverseFilter`
  （新增"真实非原生列不再 unsupported"用例,虚构列仍保持拦截）,
  `tests/test_registry_resolved_method_spec.py::TestUniverseFilterJoinSources`
  （新增,3个用例覆盖真实列/原生列/未注册列三种情况）,
  `tests/test_script_generator_resolved_method_spec.py::
  TestUniverseFilterJoinInGeneratedScript`（新增,确认生成脚本包含 join 调用且
  `compile()` 通过）。624 passed / 18 skipped（`.venv/bin/python3 -m pytest
  tests/`）。
- `docs/todo.md`：拆分成"真实注册列 join——已完成"与"派生列（groupby-min,如
  `compustat_first_datadate`）——仍 deferred，继续用 `accepted_unapplied`"两部分。

### Resolve 面板新增 `accepted_unapplied`/`unapplied_reason` 人工开关（2026-08-13）

`docs/todo.md` 记录过的空白：`FilterSpec.accepted_unapplied`/`unapplied_reason`
字段一直存在但没有任何写入路径。`SessionDetailPage.tsx` 的 resolve 面板里,紧挨着
现有的 `derivation` JSON 编辑框,给每条 `universe.filters[i]` 加了一个理由输入框
+ "Mark accepted_unapplied" 按钮（标记后显示 badge + "Undo" 按钮可反悔）。跟
`derivation` 编辑框同一个模式——纯前端编辑 `state.paper`,不需要新后端接口
（`state.paper` 本来就在每次 `/resolve` 调用时整体重发）。这也是之前讨论的
Compustat-listing-eligibility filter 临时方案的具体落地入口（先标记
`accepted_unapplied` 绕过引擎限制,真正的引擎支持继续留在 `docs/todo.md`）。
`npx tsc --noEmit`/`npm run lint` 均干净。

### `RequiredField` 新增 `source_table`/`source_column`：物理数据源选择进入 MethodSpec（2026-08-13）

详细讨论/权衡见 `docs/decision-log.md` 同日条目（推翻"论文事实层禁止物理映射"
设计原则）。这里只记实现清单：

- 新增 `src/infra/models/source_enum.py`：动态 `SourceName` 枚举，import 时从
  `catalog.DATA_CATALOG` 生成成员（当前 `crsp_msf`/`comp_funda`/`comp_fundq`/
  `ibes_statsumu`/`tr_13f`）+ `OTHER` 逃生舱，新数据源注册后自动多一个合法选项，
  零手工维护。
- `RequiredField` 新增 `source_table: SourcedValue[SourceName]` +
  `source_column: SourcedValue[str]`，交叉校验器确保列真的属于选中的表（`other`
  时跳过校验，走 `unsupported_value`）。
- `src/infra/data_layer/__init__.py`：`_catalog_menu_text()` 改名公开为
  `catalog_menu_text()`（现在有两个调用方：Step1 新工具 + resolve 阶段 LLM 兜底）。
- `src/steps/step1_extractor/extractor.py`：新增真实的 `CATALOG_MENU_TOOL`
  （`data_catalog`），把完整 catalog 菜单塞进 Step1 的 Tool Prelude。
  `prompts/extractor/method_spec_extractor.md` 删掉"禁止写物理表/列名"的旧规则，
  新增 §1.8d 指导怎么填这两个字段（含 other + unsupported_value 的用法）。
- `src/steps/step2_reviewer/spec_build.py`：review 循环也加了同一个 catalog
  菜单工具（`CATALOG_MENU_TOOL`，静态参考、零额外 LLM 开销）。**没有**在循环里
  跑真正的 resolve 尝试——这条边界维持不变（`docs/tools-plus-llm-plan.md` §5：
  spec 还在改，跑一次意义不大）。`prompts/review_gate/llm_review.md` 新增指导
  review LLM 核对/纠正这两个字段。
- `src/steps/step2_reviewer/review.py`：`data.fields[].source_table`/
  `source_column` 加进 `high_impact_sourced_values`，走跟 `weighting` 一样的
  D2/engine-menu 审查 + 现有的人工纠正 UI（零新前端组件，`schemaFieldInfo`/
  `patch-value` 机制天然支持索引路径）。
- `src/steps/step2_reviewer/implementation_resolution.py`：
  `build_implementation_resolution` 现在优先直接读 `source_table`/
  `source_column`（已经在 spec 构建时被 Pydantic 按真实 catalog 校验过），只有
  未设置/`other`的字段、以及 `universe.filters[]`独有的 filter-only 概念，才
  退回旧的 `normalize_fields()`/`normalize_fields_with_llm()` 字符串匹配路径
  （完全向后兼容，旧 spec 行为不变）。
- 前端：`sessionApi.getDataCatalog()`（复用现成的 `GET /api/data-catalog`
  endpoint，无需新后端代码）+ `SessionDetailPage.tsx` 的 `sourceColumnOptions()`
  —— `source_column` 下拉框的选项跟随同一条目 `source_table` 的当前值动态过滤，
  `source_table` 本身的下拉框零改动就能用（`allowed_values` 自动从动态枚举生成）。
- 新增测试 `tests/test_step2_reviewer.py::TestResolutionBuilder::
  test_explicit_source_table_and_column_win_over_string_matching`（故意用字符串
  匹配器找不到的 `paper_source_hint`，证明 `source_table`/`source_column` 优先
  生效）。过程中顺带修了一个自己引入的真实 bug：`_spec_test_helpers.py`
  `minimal_resolved_spec` 默认用了不存在于 catalog 里的占位列名 "x"，改为固定用
  真实存在的 `comp_funda.at`，跟它自己的 `concept_source`/`concept_column`
  参数（喂给 OLD `resolution.concept_mapping`，无 catalog 校验）解耦。
  `.venv/bin/python3 -m pytest tests/ -q` 619 passed / 18 skipped，`npm run
  build`（`tsc --noEmit`）/`npm run lint` 均干净。

### `RequiredField.paper_name` renamed to `name_in_paper`（2026-08-13）

用户指出 `paper_name` 容易被误读成"论文的名字/标题"，实际存的是"论文对这个概念的
措辞"（如 "total assets"）。用 `vscode_renameSymbol` 改了 Python 侧全部引用
（`method_spec.py`/`implementation_resolution.py`/`review.py`/
`step3_codegen/__init__.py` + 9 个测试文件），再手动补了 rename 工具碰不到的字符
串字面量（3 个测试里的 JSON dict key、`MethodSpecBoard.tsx` 的 `f.paper_name`、
`prompts/extractor/method_spec_extractor.md` 的 prose、`docs/methodspec-v2-plan.md`
的示例代码块）。不算 schema breaking change（字段改名，非结构变化），无已提交的
`tests/fixtures/`/`data/test_method_specs_human_labeled/` JSON 用到这个 key，无需
迁移数据。历史 CHANGELOG 条目（如 2026-08-08 那条 `paper_name` 提及）按惯例不回填
改名。全量相关测试 126 passed，零回归。

### 新增 `docs/todo.md`：记录 Compustat 派生 universe-eligibility filter 的延后修法（2026-08-13）

讨论背景：一次 resolve 卡在 `compustat_listing_start_date`（无物理列）+
`total_assets` filter（解析到列但引擎不支持,`RETURNS_PANEL_NATIVE_COLUMNS`
之外)。当场决定：先用 `FilterSpec.accepted_unapplied`/`unapplied_reason`
把这两条记录成已知未套用的偏差,解锁 resolve -> step3,不碰引擎。真正的修法
（`comp_funda` 派生 `first_datadate` 列 + 给 `BacktestExecutor` 加一条
point-in-time 的 Compustat-eligibility join 通道,插在 `apply_signal_
holding_period`/`form_portfolios` 之间)记录进 `docs/todo.md`,留待以后作为
正式的引擎改动/architecture decision 排期。同时记录了 `accepted_unapplied`/
`unapplied_reason` 目前在 `backend/`/`frontend/` 里零写入路径这个已知空白。

### Step3-8：导航离开再回来能恢复实时日志流（2026-08-13）

Step1/2 的进度存在前端 `localStorage`（见下一条 entry），但 step3-8 是走后端
session manifest 的（`session_store.start_attempt`/`complete_attempt_with_retry`），
manifest 本身一直能正确恢复 running/success/failed 状态——唯独 SSE 实时日志流
丢失：`StepAttempt.job_id` 字段虽然一直存在于 schema 里，但从来没有代码写过它，
永远是 `None`，导航离开再回来时前端拿不到 job_id 就没法重新订阅
`GET /api/jobs/{id}/stream`。

- `SessionStore.start_attempt` 新增可选 `job_id` 参数，在**同一次** CAS 写入里
  连同 running 状态一起记录（而不是额外再写一次——最初实现过一版"先
  `start_attempt`,再单独一次`update`回填`job_id`"的方案,会多消耗一次
  `revision`,破坏了大量测试硬编码`expected_revision`序号的假设,已撤销）。
  为了让 `job_id` 在 `start_attempt` 调用时就已知，四个后台 job 路由
  （`backend/routers/sessions.py` 的 step4 validate / step5 execute，
  `experiments.py` 的 step6，`diagnosis.py` 的 step8）调整为**先**
  `job_manager.create_job(...)` 拿到 `job_id`，**再** `start_attempt(...,
  job_id=job_id)`——这个顺序是安全的：路由 handler 在这两行之间没有
  `await`，`asyncio.ensure_future` 调度的 job 协程要等 handler 让出控制权
  （返回或 await）之后才会真正开始跑，不会在 `start_attempt` 落盘前就抢先
  调用 `complete_attempt_with_retry`。
- 前端 `SessionDetailPage.tsx` 的通用 step runner（steps 3-8 共用同一个
  组件）新增一个 effect：`jobId` 为空时,如果 `stepQuery`（session manifest
  的 step attempt）显示最新一次 attempt 是 `running` 且带 `job_id`,就
  `setJobId(attempt.job_id)` 自动接回那个 job 的 `useJobStream` 订阅——不需要
  额外的前端持久化层（不像 step1/2 那样得自己存 localStorage,这里"running"
  这份真相本来就活在 session manifest 里）。
- 回归验证：`tests/test_backend_api.py`/`test_experiment_replication_diagnosis_api.py`/
  `test_session_store.py`/`test_batch_invalidation.py`（43 passed）+ 全量
  `pytest tests/`（618 passed, 18 skipped，跟改动前基线一致）+ `tsc --noEmit`
  干净。

### 前端：新增 Tool Prelude 结果面板（"tool panel"）（2026-08-13）

后端 `src/infra/tooling/` 基础设施 + Step1/Step2 接入其实 2026-08-12 已经落地
（`ExtractionResult.tool_results`/`SpecBuildOutcome.tool_results`），只是从未
在前端展示过——之前误判成"整个 Tool Prelude 方案都还没做"（只看了
`docs/tools-plus-llm-plan.md` 头部仍写着"待实施"的过期状态行）。这次补的是
纯展示层：

- `backend/routers/methodspecs.py`：`_extract_job`/`_review_loop_job` 的返回
  dict 里补上 `tool_results` 字段（`ExtractionResult`/`SpecBuildOutcome` 早就
  有这个字段，只是没被 job 返回值转发出去）。`to_jsonable` 本来就会递归处理
  `ToolResult` dataclass，无需额外序列化代码。
- 新增 `frontend/src/components/ToolResultsPanel.tsx`：渲染 `name`/`status`
  （ok/error/skipped 三态 badge）/`error`，`payload` 折叠展开后 JSON 美化输出。
- `frontend/src/lib/types.ts` 新增镜像 `src/infra/tooling/types.py` 的
  `ToolResult` 接口；`methodSpecStore.ts` 新增 `extractToolResults`/
  `reviewToolResults` 持久化字段（同一个 localStorage 存储,理由同上一条
  entry）。`SessionDetailPage.tsx` 的 Step1/Step2 面板各挂一个
  `ToolResultsPanel`（Step1 显示 `schema_skeleton` 占位工具结果；Step2 显示
  `schema_validation`/`engine_menu_and_capability` 最后一轮的结果）。
- Step3/Step8 的工具化（`docs/tools-plus-llm-plan.md` §7 步骤 5-8：
  `sandbox_validate` 技术指标白名单、`field_evidence_detail` opt-in 工具、
  伪 tool call `tool_requests` 解析、原生 tool use 后门）仍未实现——本次只补
  已经存在的 Step1/Step2 结果的前端展示，不是把整个方案做完。

### 前端：移除 Pipeline E2E 页面 + Step1/Step2 状态持久化改为 localStorage（2026-08-13）

- 删除 `frontend/src/pages/PipelineE2EPage.tsx`（旧的手动串联 extract/review/
  codegen/backtest 的演示页），及 `App.tsx`/`AppLayout.tsx` 里对应的路由、
  导航项；首页重定向从 `/pipeline` 改为 `/runs`（session-centric 流程是唯一
  入口）。`sessionApi.ts`/`types.ts` 里提到它的注释同步更新。
- `methodSpecStore.ts`（Step1/Step2 的前端进度存储）从 `sessionStorage` 换成
  `localStorage`：前者关标签页就清空、且各标签页互相隔离，导致"重新打开
  session 就要重跑 step1"。同时把 `extractJobId`/`reviewJobId` 也存进去，
  组件挂载时从存储恢复——之前这两个 job id 只活在 React state 里，切换页面
  卸载组件就丢失，即使后端 job 其实还在跑/已经跑完（`JobManager` 是独立于
  HTTP 连接的 asyncio 任务，`GET /api/jobs/{id}` 保留结果 `JOB_TTL_SECONDS`=
  3600 秒），前端也无法再找回。

### 13F 正式注册 + liquidity_factors 走 ff_factors_path 同款路径 + LLM 自动生成 derivation（2026-08-13）

讨论详见对话记录（13F 是否已注册的追问）。三件事：

- **13F 正式注册进 `sources.py` 的 concept-mapping 目录**：`load_institutional_
  ownership_13f()` 从 `data_layer/__init__.py` 挪到 `sources.py`（`__init__.py`
  改为 re-export,保持 import 路径不变),新增 `ThirteenFSignalSource`（跟
  `CrspSignalSource` 一样绕开通用的 `_load_generic_signal_frame`/
  `link_to_permno`,因为它自己的 CUSIP→permno 匹配是"取最近一次观察到的
  permno",不是 CCM/IBES 那种带 valid_from/valid_to 的点时点 link table),
  注册为 `tr_13f`（`instown_perc` 概念,固定 2 个月上报滞后的保守近似)。
  2026-07-31 曾经因为"假设 permno-keyed 但实际是 cusip-keyed"移除过一次
  `tr_13f`——这次不是同一个错误,已经在类文档里写清楚区别。更新了
  `tests/test_data_catalog.py` 的黄金字面量（新增 `tr_13f` 条目)。
- **liquidity_factors（Pastor-Stambaugh)**：没有 `permno` 列,是市场层面时间
  序列,跟 Compustat/IBES 那种按股票的 signal source 不是一回事,硬塞进
  `sources.py` 注册表在架构上是错的。改为跟 `ff_factors_path` 完全同款的
  写死路径机制——`step5_backtest_runner.build_script()` 跟 `ff_factors.
  parquet` 一样探测 `<snapshot>/local/liquidity_factors.csv` /
  `<data_layer>/local/liquidity_factors.csv`,新增
  `liquidity_factors_data_dir` 参数一路传进 `generate_backtest_script()`,
  生成脚本里的 `load_factors()` 现在把 FF factors 和 liquidity factors
  merge 成同一个 `factors` frame（按 `yyyymm` outer join)。
  `BacktestExecutor.compute_factor_alphas()` 的 `factor_specs` 新增
  `"liq": ["ps_vwf"]`——只要 `factors` 里有 `ps_vwf` 列就会算出
  `alpha_liq`/`beta_liq_ps_vwf`,不影响原有 capm/ff3/ff5。
  `collect_runtime_provenance()` 新增 `liquidity_factors_hash`（跟
  `ff_factors_hash` 同款审计字段)。新增测试：
  `tests/test_factor_alphas.py::TestComputeFactorAlphasLiquidity`（2）、
  `tests/test_runtime_provenance.py` 的两条 liquidity_factors_hash 测试。
- **LLM 自动生成 `derivation`（而不是人工手填 JSON)**：`prompts/extractor/
  method_spec_extractor.md` 新增 §1.8c——某个 universe filter 如果真的是
  "需要计算"（比如"上市满 2 年"),提取阶段就该顺手把
  `universe.filters[].derivation`（一个 `FormulaSpec`,跟 `signal.formula`
  同构)填上,而不是只留一个 `data.fields` 条目干等着；如果只是读原始列
  （比如"SIC code == 49"),`derivation` 保持 `null`。`prompts/review_gate/
  llm_review.md` 同步加了对应的复查项——检查 `derivation` 该填的填了、不该
  填的没瞎填,列进"commonly error-prone areas"清单。两个文件都是纯 prompt
  改动,`derivation` 字段本身早已是 `FilterSpec`/`MethodSpec` 的一部分,
  JSON shape 的自动拼接（`schema_render.render_model`)不用改代码就已经会
  展示这个字段。
- 全量测试 618 passed / 18 skipped（较之前 +4,零回归)。

### 修复 re-run Step2 时 stepper 显示错乱（Step1 变 not_started、Step2 不显示 running）（2026-08-13）

上一条改动引入的连锁 bug：`reviewLoopMutation`/`reviewMutation` 的
`onMutate` 会清空 `paper`（Step2 的输出),而 `StepStepper.tsx` 的
`specStepStatus()` 一直是**用 `paper` 是否存在来判断 Step1 是否成功**——
两个字段搞混了（`rawSpec` 才是 Step1 自己的输出,`paper` 是 Step2 的收敛
结果,`MethodSpecWorkflowState` 的注释本来就写清楚了),所以清空 `paper`
连带把 Step1 的徽章从 success 打回 not_started。同时 Step2 自己的状态判断
只看 `review`/`resolved` 是否有值,压根不知道"现在有个 job 正在跑",所以
重新拉起 loop 时 Step2 会显示 not_started 而不是 running。

- **`StepStepper.tsx`**：Step1 状态改成看 `specState.rawSpec`（不再是
  `paper`),不会再被 Step2 的清空动作连带影响。
- **`MethodSpecWorkflowState` 新增 `reviewRunning?: boolean`**
  （`methodSpecStore.ts`）——纯前端瞬时标志,`reviewLoopMutation`/
  `reviewMutation` 的 `onMutate` 置 true,`reviewJob` 的 completed/failed
  分支（loop 版)和各自的 `onSuccess`/`onError`（rules-only 版)置 false。
  `specStepStatus()` 现在优先看这个标志,为 true 时直接返回 `"running"`,
  不用等 `review`/`resolved` 有内容才能显示状态。
- `tsc --noEmit`、`npm run build` 均通过。

### Re-run 时立即清空这个 step 当前显示的旧输出（2026-08-13）

上一条加的几个 re-run 按钮点击后,新结果要等一次网络往返才回来——这段时间
页面上一直显示的是"这一步"旧的、马上要被扔掉的输出,容易让人误以为按钮没反应
或者新结果已经出来了。改成点击的瞬间（`onMutate`,请求真正发出前)就清空：

- **Step 3-8 通用面板**：`runMutation` 新增 `onMutate`——清空
  `jobId`/`syncResult`/`requestError`,并用 `queryClient.removeQueries()`
  丢掉 `["session-step", sessionId, step]` 的缓存（`setQueryData(key,
  undefined)` 在 TanStack Query 里是空操作,不会真的清空,只能用
  `removeQueries`),让"Result"卡片里的 readiness/diagnostics 框跟着变回
  "还没有数据"而不是停留在上一次的旧内容上。
- **Step 2 Review 面板**：`reviewMutation`（"Re-run rules-only review")
  新增 `onMutate`,立即 `patch({ review: undefined, resolved: undefined,
  ... })`；`reviewLoopMutation`（"Re-run from Step 1 output"/首次自动触发的
  loop）新增 `onMutate`,立即清空 `paper`/`review`/`resolved`/`totalDiff`/
  `history` 并重置 `reviewJobId`——顺带的好处是 `paper` 变成
  `undefined` 后,页面会自动落回"Step2 review loop 正在跑"那个已有的
  fallback 界面,不用另外写一个"正在重跑"的状态。
- `tsc --noEmit`、`npm run build` 均通过。

### 每个 step 页面加"用上游最新输出重跑"按钮（2026-08-13）

- **Step 3-8（通用 request/response 面板）**：`runMutation` 支持
  `{ fromUpstream: true }` 变体——重新拉一次 session manifest,用跟首次进页面
  同一套 `buildAutoFilledRequest()` 逻辑,从上游 step 的最新一次成功输出重建
  request body（不是用当前文本框里的内容,那可能是这个 step 自己之前手改/
  跑过的旧内容),写回文本框后立即提交。原来的"Run {label}"按钮不变（还是提交
  文本框里现有的内容),旁边新增"Re-run from upstream output"按钮。
- **Step 2（Review 自定义面板)**：新增"Re-run from Step 1 output"按钮,丢弃
  这个 step 里做过的任何编辑（value patch/status override 等),直接拿
  Step 1 的原始 `rawSpec` 重新跑一遍完整 LLM review loop（`reviewLoopMutation`)。
  跟原有的"Re-run rules-only review"（只对当前 spec 重跑无 LLM 的规则检查)
  是两个不同粒度的操作,文案里做了区分。
- Step 1 没有上游 step,不适用,未加按钮。
- `tsc --noEmit`、`npm run build` 均通过。

### Review 面板显示全部 high-impact 字段,按 disposition 决定是否可编辑（2026-08-12）

之前 Review 面板只显示"需要人工确认"的字段（`MethodReview.findings`,
`AUTO_APPROVE` 的字段被静默跳过,人工完全看不到)。现在改成：全部展示,
`AUTO_APPROVE` 的只读、不出下拉框,其余 disposition 保持原来的可编辑行为。

- **`MethodReview` 新增 `all_high_impact_fields: list[Finding]`**（`src/infra/
  models/method_spec.py`）——纯新增字段,不影响 `findings` 原有语义（`findings`
  依然只表示"需要关注",既有的"no findings"徽章、`isBlocked`、LLM review loop
  的 `needs_human` 判断全部不变)。
- **`review.py` 新增 `_all_high_impact_field_findings()`**：跟 `_compute_findings`
  同样的 per-field disposition 逻辑,但对 `AUTO_APPROVE` 也构造一条 `Finding`
  （复用 `_evidence_status_finding` 新增的 `always=True` 参数),而不是像
  `_compute_findings` 那样直接跳过。`review_method_spec()` 把结果写进
  `all_high_impact_fields`。
- **前端 `SessionDetailPage.tsx`**：Review 列表的渲染源从 `findings` 换成
  `[...allHighImpactFields, ...findings 里路径不在 all_high_impact_fields 里的那些]`
  （保留 `missing_mapping`/非 high-impact 的 capability finding,不丢失原有信息)。
  `canPatch` 判断不变（只有 `disposition === "needs_human_confirmation"` 才出
  下拉框/输入框),`auto_approve` 的条目改用 `secondary` 徽章、只读展示
  `paper_value`,没有编辑控件。新增测试
  `tests/test_step2_reviewer.py::TestReviewCleanBaseline::
  test_fully_clear_spec_still_lists_every_high_impact_field`/
  `test_all_high_impact_fields_includes_needs_human_confirmation_entries`。
  全量测试 614 passed / 18 skipped,零回归。

### Review 面板两处修复（2026-08-12）

- **`schema_reference.py::_walk_model` 递归进 `list[BaseModel]` 字段的子模型**：
  之前遇到 `portfolio.sorts: list[SortDimension]` 这类字段只登记了一条摘要
  （`list_item_fields` 列子字段名),从不递归进 `SortDimension` 本身,导致
  `portfolio.sorts[i].breakpoints.basis`（实际是个三值 enum:
  `full_sample`/`nyse`/`other`）在 schema 里查不到,前端 review 面板只能退化
  成自由文本框而不是下拉框。现在递归进子模型时复用同一个不带下标的
  `path`（跟前端 `fieldPath.replace(/\[\d+\]/g, "")` 的查找方式对齐),`data.
  fields.concept_id` 之类的路径现在也会出现在 schema 里。更新
  `tests/test_schema_reference.py` 里原先把这个 gap 断言成"预期行为"的
  测试。
- **`apply_value_patches` 新增 `unsupported_values` 参数 + `/patch-value`
  新增 `unsupported_values` 请求字段**：human 把某个高影响字段的下拉值改成
  `other` 时,现在能同时填一份 `SourcedValue.unsupported_value`（论文的原始
  措辞),不再是"选了 other 但没地方记录论文原话是什么"。补的字段只在目标值
  确实是 `"other"` 时才写入,从 `other` 改回其他值时会清空残留的
  `unsupported_value`（配合模型自身的校验器）。前端
  `SessionDetailPage.tsx`：drafted 值等于 `"other"` 时,在下拉框下面多渲染
  一个"Paper's original wording (unsupported_value)"文本框,提交时随
  `patches` 一起发给后端。新增测试
  `tests/test_apply_human_value_patches.py::test_patching_to_other_stores_
  unsupported_value`/`test_patching_away_from_other_clears_stale_
  unsupported_value`。
- **前端：resolve 阻断面板里新增 `universe.filters[i].derivation`（`FormulaSpec`）
  的最小可用编辑器** -- 一个 unmapped concept（如 `compustat_listing_history`）
  未必真的缺物理列映射,可能只是需要一个"计算派生条件"（`derivation`,2026-08-12
  那次 resolve 诊断盲区 problem 1 修复引入的字段,`FilterSpec.derivation:
  FormulaSpec | None`,见 `docs/resolve-diagnostics-gaps.md`）。这个字段不是
  `SourcedValue`,走不了 `/patch-value`,所以是纯前端态编辑：只读展示当前
  `derivation`（`JsonTree`）+ 一个大文本框粘贴/编辑整段 `FormulaSpec` JSON,
  "Apply"直接更新 `state.paper`（不落后端,跟其余 in-session 编辑一样,靠下次
  /review 或 /resolve 把整份 paper 重新发过去）。留空文本框等于清空该 filter
  的 `derivation`。JSON 解析失败会显示错误,不静默吞掉。

### `/runs` 列表页上线（UI 重设计 Part 1，2026-08-12）

按 [docs/ui-redesign-plan.md](docs/ui-redesign-plan.md) §2.1 落地第一个页面：

- `frontend/src/pages/SessionsPage.tsx` 重命名为 `RunsPage.tsx`（`git mv` 保留历史），
  新增搜索框（按 factor_id/paper_id 模糊匹配）、Paper 列、基于 `STEP_REGISTRY` 的
  8 点进度摘要（`ProgressDots`， stale 步骤额外加珀色环）。
- 去掉归档按钮，只保留删除（二次确认）。（`POST .../archive` 仍保留在 `sessionApi`
  里供后端使用，只是不在 UI 上暴露。）
- 前端路由从 `/sessions`，`/sessions/:sessionId/steps/:step` 改为
  `/runs`，`/runs/:sessionId/step/:step`（`App.tsx`、`AppLayout.tsx` 导航项、
  `SessionDetailPage.tsx` 内部导航、`ReviewResolvePage.tsx` 同步更新）。后端
  `/api/sessions/*` 端点未变。
- 未实现（需后端支持，待后续阶段）：Fork 血缘标记、行内展开 tool 调用。

### 新增 UI 重新设计方案文档（2026-08-12，仅文档）

新增 [docs/ui-redesign-plan.md](docs/ui-redesign-plan.md)：把前端从 9 个各自为政的
页面收敛为 4 个区（Runs / Telemetry / Reference / Settings），核心是 8 个步骤共用一个
`StepWorkbench` 组件，「单步测试」表达为 step 的输入来源（上一步产物 / 其他 run /
fixture / 手写 JSON）而不是另一个页面。另含统一 telemetry 事件流
（`llm_call` + `tool_call` 同流、token 用量含 `~估算` 标记）、data 与 MethodSpec 两个
可反查字典、以及后端端点统一（三套风格 → `POST /api/sessions/{id}/steps/{n}/run`）。
决策记录见 [docs/decision-log.md](docs/decision-log.md) 同日条目。**尚未实施代码。**

### Step8 完整重新设计落地：三个新 claim_type + `reason_layer` + Tool 化 + 重试循环 + `field_evidence_detail`（2026-08-12）

按 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md) §4.3 把 Step8 的
剩余部分（新 claim_type 命名、Tool 注册、重试循环、opt_in 工具）全部落地，这是
"tools+LLM"改造里唯一新增了真正扩大 LLM 能力边界的一步。

- **`src/infra/models/diagnosis.py`**：新增 3 个 claim_type
  （`signal_reproducibility`/`publication_decay`/`implementation_robustness`，
  各自的 relation 见下表）+ `reason_layer` 字段（`config_sensitivity`/
  `signal_fidelity`/`temporal_pattern`，由 `claim_type` 确定性推导，不是 LLM
  写的）。

  | claim_type | relation | 引用要求 | reason_layer |
  |---|---|---|---|
  | `signal_reproducibility` | `reproduces`/`diverges` | `bridge_comparison.signal_implementation_agreement` + `subject_track` 必须是 own_track 或 bridge_track | `signal_fidelity` |
  | `publication_decay` | `decayed`/`stable` | `publication_decay.tracks.*.decayed` | `temporal_pattern` |
  | `implementation_robustness` | `robust`/`fragile` | `robustness_summary.robust` | `config_sensitivity` |

- **`src/steps/step8_diagnosis/__init__.py`**：
  - `_entailment_reason` 新增 3 个新 claim_type 的关系校验分支（跟现有
    `sign_agreement`/`magnitude_gap` 等同一套模式：断言的 relation 必须匹配
    引用证据的实际值）；`_cited_tracks` 扩展识别
    `publication_decay.tracks.<track>.` 前缀，让 `subject_track` 能自动推导
  - `Step8ToolContext` + 8 个占位型 `Tool`（`spec_quality`/`menu_deviations`/
    `derived`/`config_diff`/`gap_decomposition`/`bridge_comparison`/
    `publication_decay`/`robustness_summary`）——真正的计算都发生在 Step7 的
    `build_evidence_bundle()`，`fn` 只是从 `ctx.bundle` 读现成结果（跟 Step1
    的 `schema_skeleton` 同一种占位模式）
  - **`diagnose()` 加有界重试循环**（默认 `max_rounds=2`）：round1 之后如果有
    `rejected_claims`，round2 只把被拒的 claim + 拒绝原因重新喂给 LLM，让它
    修或删；接受的 claim 跨轮按内容去重（防止一个"傻" LLM 每轮都原样重交整份
    答案时被重复计数——这是实现阶段发现的真实 bug，用 dedup 而不是信任
    "LLM 只会交被拒的那几条"这个假设来修复）
  - **`field_evidence_detail`**（唯一真正 `opt_in` 工具）：LLM 通过
    `tool_requests` 请求后，才现场从 `resolved_spec.paper` 读取某个弱字段完整
    的 `SourcedValue.evidence[]`（论文原文引用），没传 `resolved_spec` 时
    自报 `status="skipped"`。**简化**（跟 plan 最初设想的
    `"field_evidence_detail:field_path"` 冒号参数化不同）：一次性返回
    `spec_quality.weak_fields` 里全部弱字段的证据，不做单字段参数化——避免
    给 `ToolRunner` 引入"请求名里带参数"的解析机制，这类字段数量本来就有限
  - `diagnose()` 新增可选参数 `resolved_spec`/`tool_policy`/`max_rounds`，
    现有 5 个非测试调用点（`backend/routers/diagnosis.py`、
    `scripts/analyze_comparison.py`、`step6_dual_track_controller`）零改动
- **`src/steps/step8_diagnosis/render.py`**：3 个新 claim_type 的确定性句子
  模板
- **`prompts/analysis/replication_diagnosis.md`**：加 `TOOLS:CATALOG` marker、
  3 个新 claim_type 的文档、输出 JSON 加 `tool_requests`
- 14 个新测试（新 claim_type 校验、`reason_layer`、重试循环去重、
  `field_evidence_detail` 请求/不可用两种情况）。全量测试 609 通过/18 跳过
  （609 = 595 + 14 新，零回归）。

### Step3 迁移：`column_mapping` 变成 Tool + `sandbox_validate` 新增 dtype 检查/技术指标（2026-08-12）

按 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md) §4.2/§5 的结论——
Step3 不加任何新循环（"成功也强制回喂一轮"已在讨论阶段撤销），只做两件事。

- **`column_mapping` 从手写箭头文本迁移成 `Tool`**
  （[src/steps/step3_codegen/__init__.py](src/steps/step3_codegen/__init__.py)）：
  `_build_prompt_from_resolved()` 里 `at → df["at"]` 那段硬编码渲染删掉，改成
  `COLUMN_MAPPING_TOOL`（`Step3ToolContext`），`generate_plugin()` 在唯一一次
  LLM 调用之前跑一次（跟 Step1 一样是 prelude-only，`generate_plugin()` 本身
  就是单次调用，不新增循环）。`prompts/meta_coder/signal_plugin_system.md`
  加了 `TOOLS:CATALOG` marker。[tests/test_meta_coder_resolved_method_spec.py](tests/test_meta_coder_resolved_method_spec.py)
  里断言精确箭头文本的用例按计划改成断言 JSON payload。
- **`sandbox_validate` 新增 `technical_metrics` + `dtype` 硬性检查**
  （[src/steps/step4_validator/__init__.py](src/steps/step4_validator/__init__.py)）：
  `_EXECUTE_DRIVER` 子进程 driver 在算完 `compute_signal` 后，顺手算
  `nan_ratio`/`n_permno`/`n_months`/`missing_columns`/`dtype`（白名单字段，
  绝不含任何 return/alpha/t-stat/Sharpe），写进 `ValidationReport.
  technical_metrics`（新字段，纯加，不影响 `passed` 判定）。`signal` 列非数值
  dtype（比如意外输出字符串但不抛异常）现在是**新的确定性失败条件**，直接走
  现有的 `report.errors → repair_plugin` 分支——`repair_plugin(plugin,
  errors: list[str])` 本身是通用字符串列表接口，不需要任何新代码路径。
- `sandbox_validate` **没有**包成 `Tool`——它的实际调用方是 `RepairLoop`
  的多轮 build→validate→repair 循环，不是一次性 prelude，没有自然的
  `ToolRunner` 接入点，本次不强行包装。
- `column_mapping` 迁移新增/更新 2 个测试，`sandbox_validate` 新增 3 个测试
  （dtype 硬失败、technical_metrics 内容、白名单不含绩效数字）。全量测试
  595 通过/18 跳过（595 = 591 + 4 新，零回归）。

### Step2 LLM review循环迁移到 Tool Prelude 基础设施（2026-08-12）

按 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md) §5 把
`spec_build.py` 现有的 `_PRE_LLM_TOOLS`/`_run_pre_llm_tools` 雏形改造成正式的
`Tool`/`ToolRunner` 用法，这是"tools+LLM"改造里第一个真正有多轮循环的 step。

- `_schema_validation_tool`/`_engine_menu_and_capability_tool` 原样保留逻辑，
  各自包一层 `Tool`（`SCHEMA_VALIDATION_TOOL`/`ENGINE_MENU_TOOL`，均
  `tier="always"`），组成 `STEP2_TOOLS` 注册表。新增 `Step2ToolContext`
  （`spec_dict` + `parsed_spec`——`parsed_spec` 是专门字段，不是塞进
  `ctx.results`，因为 `ctx.results` 类型是 `dict[str, ToolResult]`，不该放
  裸的 `MethodSpec` 对象，这是实现时对 plan 原始伪代码的一处必要修正）。
  `_engine_menu_fn` 读不到 `ctx.parsed_spec` 时自己返回
  `status="skipped"`（无 `depends_on`/拓扑排序，见 §2）。
- `ReviewRound.error_log` 从存储字段降级为**渲染 property**（从新增的
  `tool_results: list[ToolResult]` 字段拼出旧格式文本），兼容
  [tests/test_step2_reviewer_llm.py](tests/test_step2_reviewer_llm.py) 原有的
  宽松断言（`==""`/`!=""`/子串匹配），但 3 个直接断言精确旧标签格式
  （`[schema_validation]`/`[engine_menu_and_capability_findings]`）的测试
  按计划改成断言新的 `### tool_name` 渲染格式。
- `SpecBuildOutcome` 新增 `tool_results`（存最后一轮，语义同 `spec`/`review`）。
- **循环骨架加了 `tool_requests` 解析**（即使 Step2 目前没有任何 `opt_in`
  工具，仍按跨 step 一致性要求接入）：LLM 输出 JSON 新增可选字段
  `tool_requests: list[str]`（`.get(..., [])` 兜底，不破坏现有 Fake LLM 测试），
  下一轮把请求的名字传给 `ToolRunner`；请求了未注册的名字会在下一轮的
  catalog 里追加"未知工具名"提示，不中断循环。
- **`prompts/review_gate/llm_review.md`**：第 0 节从手写的 `[tag]` 说明文字
  换成 `<!-- TOOLS:CATALOG:START/END -->` 动态渲染；第 6 节输出 JSON 加
  `tool_requests: []`。
- 4 个新测试（2 个更新格式断言 + 2 个新增：`SpecBuildOutcome.tool_results`
  取最后一轮、未知工具请求下一轮出现提示不崩溃）。全量测试 591 通过/18
  跳过（591 = 589 + 2 新，零回归）。

### 新增 `src/infra/tooling/`（Tool Prelude 基础设施）+ Step1 接入（2026-08-12）

按 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md) §2/§4.1 实现的第一批
代码：通用的 Tool Prelude 基础设施，以及 Step1（抽取）的接入——Step1 架构上是严格
单次 LLM 调用，所以这次接入不含任何轮次/`tool_requests`，纯前置。

- **`src/infra/tooling/`**：`Tool`（单层 dataclass，同时是说明书和可执行单元，
  无 Protocol/`FunctionTool` 两层）、`ToolContext`（共享基类）、`ToolResult`、
  `ToolPolicy`、`ToolRunner`（按 list 顺序跑，无 `depends_on`/拓扑排序；`always`/
  `on_failure`/`opt_in` 三档；失败隔离；`prior_round_failed` 由调用方计算好传入，
  runner 自己不判断"什么算失败"）、`catalog.py`（`render_tool_catalog`/
  `render_tool_results`/`splice_tool_catalog`，splice 行为照抄
  `schema_render.splice_schema_skeleton`：marker 缺失就原样返回，不报错）。
  15 个新测试（`tests/test_tooling.py`），覆盖失败隔离/自报告依赖/`disable`/
  `opt_in`+`tool_requests`/未知工具名/`on_failure`分档/tracer可选/catalog splice。
- **Step1 接入**（[src/steps/step1_extractor/extractor.py](src/steps/step1_extractor/extractor.py)）：
  新增 `Step1ToolContext`、占位型 `SCHEMA_SKELETON_TOOL`（payload 只指向系统
  prompt 里"Required JSON Shape"示例，不重复渲染 JSON 骨架本身）、`STEP1_TOOLS`
  注册表。`MethodSpecExtractor.extract()`/`_call_llm_extract()` 新增可选参数
  `tool_policy`（默认全跑），跑一次 `ToolRunner` 后把 catalog 拼进 system prompt
  （`prompts/extractor/method_spec_extractor.md` 新增"# 0. Tool catalog"段 +
  `TOOLS:CATALOG` marker）、把 `TOOL RESULTS` JSON 拼进 user message；结果存进
  新增字段 `ExtractionResult.tool_results`。**没有加 `tool_requests` 字段**——
  Step1 是单次调用，没有下一轮可以执行它。3 个新测试
  （`tests/test_step1_extractor.py::TestStep1ToolPrelude`）。
- 全量测试 589 通过/18 跳过（589 = 571 + 18 新，零回归）。

### Step8 诊断新增三层归因证据：spec_quality / menu_deviations / bridge_comparison / publication_decay / robustness_summary（2026-08-12）

按 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md) §4.3 的 Step8 重设计，
先落地不依赖 tooling 基础设施的部分——五个新的 `bundle.py` 纯函数，`comparison.json`
的 `evidence_keys` 白名单随之扩大，为以后接入 LLM diagnosis 的三层归因框架打基础。

- **`build_spec_quality(spec)`**：现场重新调用 `review_method_spec(spec.paper)`
  （纯函数，Step2 用过一次就再没人调），摘出 `kind="ambiguous"` 的 Finding 作为
  "弱字段"列表。**零新持久化**。
- **`build_menu_deviations(spec, tracks)`**：读 `spec.paper` 里各高影响字段的
  `SourcedValue.unsupported_value`（论文方法在引擎菜单外时的原始措辞）+ 每条
  track 的 `config["defaults_applied"]`（`registry.build_config` 早已内嵌，一路
  原样写进了 `comparison.json`，核实后发现之前"算了但丢了"的判断是错的）。
  **零新持久化**。
- **`build_bridge_comparison(tracks, paper_reported)`**：找到 `is_bridge_track=
  True` 的 track（C&Z 参考信号跑过跟我们相同的下游配置）配对常规 track，比较
  两者各自是否独立复现论文的符号，产出 `signal_implementation_agreement`
  （`both_reproduce`/`only_bridge`/`only_own`/`neither`）——直接回答"信号本身能否
  复现"（inter-implementer agreement），不只是"收益差多少"。**小改动**：
  `write_comparison_summary` 组装 `tracks_summary` 时补一行
  `"is_bridge_track": r.is_bridge_track`（[step6_dual_track_controller](src/steps/step6_dual_track_controller/__init__.py)）。
- **`build_publication_decay(tracks)`**：对比每条 track 样本内/发表后的 t-stat
  （McLean-Pontiff 式衰减）。**真正的 schema 新增**：`RunMetrics`
  （[src/infra/models/run_record.py](src/infra/models/run_record.py)）此前根本
  没有 `by_sample_period` 字段——`backtest_engine` 算出的这份数据会在构造
  `RunMetrics(...)` 时被静默丢弃，现已补上并在 `make_run_record` 里接上。
- **`build_robustness_summary(tracks)`**：汇总所有 `ablation_*` track 相对
  baseline 的 t-stat 极差/符号翻转数/显著性翻转数，给出整体 `robust: true/false`
  判断（实现敏感度/鲁棒性），零新持久化。
- `build_evidence_bundle()` 新增可选参数 `spec: ResolvedMethodSpec | None`，五个
  新 section 都进了 `evidence_keys` 白名单。`COMPARISON_SCHEMA_VERSION` 从 2 bump
  到 3（纯加字段，不破坏现有消费方）。
- `src/steps/step2_reviewer/review.py`：`_high_impact_sourced_values` 改名为
  公开的 `high_impact_sourced_values`（重命名，非私有），供 `bundle.py` 复用。
- 15 个新测试（`tests/test_replication_diagnosis.py`），全量测试 571 通过/18
  跳过（571 = 556 + 15，零回归）。
- 尚未做的部分（`Tool` 包装、`diagnose()` 的重试循环、`field_evidence_detail`
  opt_in 工具、新 claim_type/`reason_layer`）留给后续依赖 `src/infra/tooling/`
  基础设施的阶段。

### 新增 Tools + LLM（Tool Prelude 模式）重构方案文档（2026-08-12）

新增 [docs/tools-plus-llm-plan.md](docs/tools-plus-llm-plan.md)：把每个有 LLM 参与的
步骤统一改造成「确定性工具全跑 → 工具说明书 + JSON 输出进 prompt → LLM 只做判断/生成」。
因为走 CLI 调用，LLM 无法在推理中途选工具，所以是 Tool Prelude 而非 function calling。

- 该模式在 `spec_build.py` 的 `_PRE_LLM_TOOLS` 已有雏形，本次是抽成通用基础设施
  （计划中的 `src/infra/tooling/`）后推广到 step1 / step3 / step8。
- 兼容策略：所有 LLM 入口只加可选参数 `tool_policy`，8 个非测试调用点零改动；
  持久化的 Pydantic 模型（`PluginRecord` / `ReplicationDiagnosisReport` /
  `comparison.json`）一律不动，工具结果只进 `trace.py` 事件流。
- 目前仅文档，尚未动代码。

### Step2 LLM review loop 现在能看到 `review_method_spec` 的 Finding（2026-08-12）

跟进问题 3 讨论中发现的一个独立缺口：`spec_build.build_reviewed_method_spec`
的 `error_log` 此前只有 `model_validate()` 的 Pydantic 校验错误一个来源，
`review_method_spec(paper).findings`（D2 + missing_mapping + 这次新加的
engine-menu/capability 系列）从来没有喂给过 LLM——只有人工调用独立的
`/review` 端点时才会被算出来展示给人看。

- **`spec_build.py`** 新增两个"pre-LLM tool"函数：`_schema_validation_tool`
  （现有 `model_validate` 逻辑，不变）+ `_engine_menu_and_capability_tool`
  （跑 `review_method_spec`，把 findings 转成带 `[engine_menu_and_capability_
  findings]` 标签的文本）。`_run_pre_llm_tools()` 依次跑完所有 tool（schema
  校验优先，因为后续 tool 需要一个真正校验过的 `MethodSpec`，不是可能无效的
  裸 dict），输出拼成一份 `error_log` 喂给 LLM。`_PRE_LLM_TOOLS` 列表设计成
  可扩展——以后加新检查只需要往列表里加函数。
- 循环收敛条件**不变**——仍然只看 schema 校验通不通过，Finding 只是给 LLM
  的额外上下文，不阻塞循环退出（跟 Finding 本身"非阻塞"的设计一致）。
- **`prompts/review_gate/llm_review.md`** 新增"第 0 节"，介绍每个带标签的
  block 是什么意思（`[schema_validation]`/`[engine_menu_and_capability_
  findings]`），让 LLM 在看到具体内容之前先知道这些"工具"各自的用途——
  第 2 节措辞同步更新，明确指向 `[schema_validation]` 这个标签。
- 新增测试：`tests/test_step2_reviewer_llm.py::TestPreLlmTools`（3：engine-
  menu finding 出现在 prompt 里、spec 干净时不出现、schema 校验失败时
  engine-menu tool 跳过不跑）。全量测试 556 passed / 18 skipped（零回归）。

### Resolve 诊断盲区 problem 3 修复：universe filter 的值编码翻译（2026-08-12）

讨论详见 `docs/resolve-diagnostics-gaps.md`（"问题 3"节讨论结论）。

- **真实事故修复**：filter 的 `concept_id` 正确解析到了 `exchcd` 这类物理
  native 列后，`value` 之前一直是论文原文措辞（`["NYSE","Amex","NASDAQ"]`），
  直接传给 `.isin()` 对数字列永远是 `False`——universe 被悄悄筛成 0 行，
  错误几步之后才在 `compute_breakpoints` 冒出一个不相关的报错。
- **`FILTER_VALUE_ENCODINGS`**（`src/infra/models/method_spec.py`，紧挨
  `RETURNS_PANEL_NATIVE_COLUMNS`）：`exchcd`/`shrcd` 两列的"论文措辞(小写)
  -> 物理编码"手工登记表，一次性注册、对所有论文复用——不做成 LLM 生成，
  因为这是 WRDS/CRSP 数据源自己的编码约定，论文原文通常不解释，LLM 只能
  凭常识猜、没有论文证据可验证。`siccd`（行业排除通常是 SIC 区间而非单值
  标签）本次不做，留给以后单独设计。
- **`registry._translate_filter_value()`**：`universe_filters` 构造时对每
  个 filter 的 `value` 做一次翻译，查到就换成编码；已是数字或列没注册映射
  的原样透传；**字符串查不到对应编码时 `ValueError`**（不悄悄放过，避免
  重演"全筛空 + 报不相关的错"）。
- 跟问题 1 的 `FilterSpec.derivation`/LLM codegen 是两回事、不复用——那套
  机制适合"需要逐行计算"的场景（如上市时长），值编码翻译只是纯静态查表。
- 新增测试：`tests/test_registry_resolved_method_spec.py::
  TestUniverseFilterValueEncodingTranslation`（5）。全量测试
  553 passed / 18 skipped（零回归）。

### Resolve 诊断盲区 problem 2 修复：construction-capability 不再阻塞 `is_ready`，改为统一自动降级 + 通知（2026-08-12）

讨论详见 `docs/resolve-diagnostics-gaps.md`（"问题 2"节 + "实现前复查"）+
`docs/decision-log.md` 同日条目（"部分恢复 D4 的可见性"）。

- **`ResolvedMethodSpec._construction_within_capability()` 删除**，`is_ready`
  不再检查 sort 维度数/`group_type`——全部改为 `registry.build_config` 自动
  clamp + `defaults_applied` 记录 + `review.py` 无条件 Finding 通知，不阻塞。
- **模型改动**（`src/infra/models/method_spec.py`）：`GroupType`/`SortMode`
  加 `OTHER` 成员（`categorical`/`threshold`/`within_group` 仍是具名的已知
  引擎能力缺口，不折叠进 `other`）；`SortDimension.mode`/`group_type` 从裸
  枚举升级为 `SourcedValue[Enum]`；新增 `ReturnCombinationScheme` 枚举（含
  `OTHER`），`PortfolioSpec.return_combination` 从 `SourcedValue[str]` 升级
  为 `SourcedValue[ReturnCombinationScheme]`，与 `weighting` 同构。
- **`registry.py` 统一自动降级**：sort 维度数超过 `MAX_SUPPORTED_SORT_
  DIMENSIONS` 时保留 target + 按 `order`（同序按 `sort_id` 字母序 tie-break）
  排前的非 target 维度，多余的砍掉；非 quantile 的 `group_type` 只记录偏差
  （引擎本来就只执行 quantile 分组，无需真的切换执行逻辑）；
  `rebalance_frequency`/`accounting_lag_months` 的 `lag_unit` 遇到
  `TimeUnit.DAY` 时给出诚实归因（不再谎称"unspecified"，因为论文其实说了
  只是换算不了）；`sort.mode="within_group"` 原样透传给引擎（新增
  `"mode"` config key），不再被裸 `==` 判断误判成 `sequential`——只有真正
  的 `"other"` 才 clamp 成 `independent` 默认值。
- **引擎 fail-loud**（`src/infra/backtest_engine/__init__.py::
  assign_portfolios_multi`）：收到 `mode="within_group"`（尚未实现）时直接
  报错，不再静默当 `sequential` 跑错误的经济学假设。
- **`review.py` 统一通知层**：新增 `_engine_menu_unsupported_finding()`（对
  `weighting`/`return_combination`/`construction_type`/`breakpoints.basis`/
  `missing_policies[].action`/`group_type`/`sort.mode` 生效，`value=="other"`
  时无条件生成 Finding，替代而非叠加 D2 的 evidence-status 检查——修复了
  D2 只看 `EvidenceStatus`、`status=clear` 时 `(CLEAR,HIGH)=AUTO_APPROVE`
  导致"分类成 other 却完全没有可见性"的真实 bug）+ 三个独立的
  paper-only 检查（`_rebalance_frequency_capability_finding`/
  `_lag_unit_capability_finding`/`_sort_dimension_count_finding`，对应
  `TimeUnit.DAY`/结构性 sort 维度超限，这些不是"other"分类问题，是"已知
  但特定下游用不了"问题，不需要给 `TimeUnit` 加 `OTHER`）。
- **`prompts/review_gate/llm_review.md` 同步更新**：高影响字段清单、
  `unsupported_value` 适用字段清单、第 3 节分类规则都补上
  `return_combination`/`group_type`/`sort.mode` 的判断标准。
- 新增/更新测试：`tests/test_registry_resolved_method_spec.py::
  TestEngineMenuAutoClamp`（6）、`tests/test_step2_reviewer.py::
  TestEngineMenuUnconditionalFindings`（7）、
  `tests/test_double_sort_engine.py::TestWithinGroupModeFailsLoud`（1）、
  更新 `tests/test_method_spec_contract.py`/`tests/_spec_test_helpers.py`/
  多个既有测试文件里手动构造 `SortDimension` 的地方（`mode`/`group_type`
  包 `SourcedValue`）。全量测试 548 passed / 18 skipped（较之前 +14，零
  回归）。前端 `MethodSpecBoard.tsx` 同步修正 `mode`/`group_type` 的
  `SourcedValue` 解包，`npm run build` 干净。

### Resolve 诊断盲区 problem 1 修复：`FilterSpec.derivation` + resolve-time `resolution_findings`（2026-08-12）

讨论详见 `docs/resolve-diagnostics-gaps.md`（"问题 1"节 + 讨论结论）。

- **`FilterSpec.derivation: FormulaSpec | None = None`**（`src/infra/models/
  method_spec.py`）：描述如何从 concept 的底层物理列推导出 filter 用到的值
  （如 "NYSE/Amex/NASDAQ" -> exchcd 1/2/3 的编码映射，或"上市满 2 年"这类需要
  计算的派生条件）。跟 `SignalSpec.formula` 同构（`inputs` 引用抽象
  concept_id，不含物理列），因此可以在 Step2 review 阶段被完整审查，不需要
  等 resolve 之后。新增字段带默认值，非 breaking change，`schema_version`
  不变。
- **`/resolve` 新增 `resolution_findings` 字段**（`backend/routers/
  methodspecs.py`）：`_unsupported_universe_filter_findings()` 用
  `resolution.concept_mapping`（resolve 阶段才有）构造 `Finding`
  （`kind="unsupported"`，复用 D4 移除后空出的 literal；
  `disposition=NEEDS_HUMAN_CONFIRMATION`），暴露"哪个 filter 解析到了哪一列、
  但引擎的 returns panel 不认识这一列"，而不是让用户只看到一个不透明的
  `is_ready: false`。之所以没有塞进 Step2 `review_method_spec(paper)`（跟其余
  9 个 high-impact 字段共用同一条路径）：那个函数只吃 `paper`，拿不到
  `concept_mapping`，判断天然依赖 resolve 之后才有的数据。
- **`schema_reference.py`**：`universe.filters` 的 `_FIELD_NOTES` 描述文字
  补充说明 `derivation` 字段用途。
- **Step3 codegen**：`MetaCoder` 新增 `generate_filter_derivation_plugin()` +
  `_build_prompt_for_filter_derivation()`，跟 `generate_plugin`/
  `_build_prompt_from_resolved` 同构（读 `filt.derivation` + resolve 阶段的
  物理列，生成 `compute_filter_value(df) -> pd.Series`），复用同一个
  LLM 调用/`_strip_code_fences`/repair 基础设施，新增独立 system prompt
  `prompts/meta_coder/filter_derivation_plugin_system.md`（filter derivation
  的规则跟 signal 公式不同，不能共用同一份 prompt）。**尚未**接入
  `script_generator`/Step4/Step5——这次只做了 codegen 入口，实际把生成的
  derivation 代码接进回测执行链路是后续工作。
- 新增/更新测试：`tests/test_method_spec_contract.py::
  TestFilterDerivation`（3）、`tests/test_filter_derivation_codegen.py`（3，
  新文件）、`tests/test_backend_methodspecs_api.py::
  test_unsupported_universe_filter_findings_reports_column_and_native_list`
  （1）。全量测试 534 passed / 18 skipped（零回归）。前端 `npm run build`/
  `npm run lint` 均干净。

### Follow-up (2026-08-11，第三次)：轮次语义修正 + Step1/Step2 拆成两个独立 job

- **`MAX_REVIEW_ROUNDS` 语义修正**：`spec_build.py` 的 `total_rounds` 之前是
  `max_rounds + 1`（"1 次预检 + max_rounds 次重试"），导致 `MAX_REVIEW_ROUNDS=3`
  实际跑 4 次 LLM 调用。改为 `total_rounds = max_rounds`——现在设成 3 就正好
  跑 3 轮（3 次 validate + 3 次 LLM 调用）。相应更新了
  `tests/test_step2_reviewer_llm.py` 里硬编码轮次数的测试。
- **Step1 提取与 Step2 审核循环拆成两个独立 job**：此前 `POST /extract*`
  一个 job 里顺序做完 Step1 提取 + Step2 循环，导致 Step1 页面只有等 Step2
  也跑完才会显示"成功"。现在：
  - `_extract_job()` 只做 Step1（提取 + 落盘裸 JSON），返回
    `{raw_spec, error, token_usage, paper_text}`，提取一结束就算"成功"。
  - 新增 `POST /api/methodspecs/review-loop`（`_review_loop_job()`）单独跑
    `build_reviewed_method_spec()`，返回
    `{spec, error, review, history, total_diff, llm_notes}`，job
    `step=2`/`stage="review_loop"`。
  - 前端 `sessionApi.ts` 新增 `runReviewLoop()`；`SessionDetailPage.tsx` 的
    `MethodSpecWorkflowPanel` 现在维护两个独立的 `useJobStream`
    （`extractJob`/`reviewJob`）：Step1 提取一结束就 patch `rawSpec` 并跳转到
    Step2，同时立刻自动调用 `runReviewLoop`（无需用户手动点）；Step2 页面
    在 `state.paper` 还没生成时展示审核循环的实时日志/状态，并提供"手动
    重跑"按钮（应对页面刷新后本地 `reviewJobId` 丢失的情况——`documentId`/
    `targetName` 已经持久化进 `methodSpecStore.ts`，可以重新发起）。
  - `MethodSpecWorkflowPanel` 在 step1↔step2 之间导航时不会重新挂载（同一个
    路由 `element`，`step` 只是变化的 prop），所以本地的 `reviewJobId` 状态
    在两个页面之间是延续的，不需要额外持久化就能让 SSE 日志跨页面继续显示。

### Added

- **Step1/Step2 重构（`docs/step1-step2-refactor-plan.md`）：Step1 精简为一次纯 LLM
  调用，Step2 承担全部 validate/normalize/review，单条有界循环收敛。**
  - `SourcedValue` 新增 `unsupported_value: str | None = None` 字段
    （`src/infra/models/method_spec.py`），配一个跨字段一致性 `@model_validator`：
    非空时 `value` 必须是 `"other"`，反之必须为 `None`。放宽 D2：
    `DISPOSITION_MATRIX` 中 `(TABLE_ONLY, HIGH)` 由 `NEEDS_HUMAN_CONFIRMATION`
    改为 `AUTO_APPROVE`。
  - `src/steps/step1_extractor/extractor.py` 精简：`MethodSpecExtractor.extract()`
    现在只返回裸 dict（`ExtractionResult.raw_spec`），删除
    `normalize_engine_vocabulary`/`_normalize_*`/`_repair_bare_sourced_scalars`/
    `build_method_spec`，不再做任何校验；新增 `persist_raw_spec()` 落盘到
    `runs/method_specs/raw/`。
  - `src/steps/step2_reviewer/review.py`：删除 D4（`_capability_findings`及其
    `ENGINE_*_MENU` 阻断逻辑），保留 `universe.filters[].concept_id` 检查但改归类
    为 `kind="missing_mapping"`/`NEEDS_HUMAN_CONFIRMATION`；删除
    `apply_human_status_overrides` 与旧的快照式 `review_method_spec_with_llm`；
    `apply_human_value_patches` 泛化为 `apply_value_patches(..., source="llm"|"human")`。
  - 新增 `src/steps/step2_reviewer/spec_build.py`：`build_reviewed_method_spec()`
    单条有界循环（`MAX_REVIEW_ROUNDS=3`，即最多 4 次 LLM 调用）——每轮先
    `model_validate()` 再 LLM review，只合并 LLM 明确声明的
    `field_assessments`/`evidence_assessments`（自动生效）与 4 个菜单分类字段
    （`weighting`/`construction_type`/`sorts[].breakpoints.basis`/
    `missing_policies[].action`），其余字段一律强制沿用上一轮的值（防漂移护栏）；
    `value_corrections` 仅作为人工待确认提议，从不自动写入；预算耗尽返回
    `error`（不抛异常）。
  - 重写 `prompts/extractor/method_spec_extractor.md`（菜单字段改写论文原文措辞，
    不再强制分类）与 `prompts/review_gate/llm_review.md`（审核整份 spec，四类
    结构化输出：`field_assessments`/`value_corrections`/`evidence_assessments`/
    `additional_findings`）。
  - `backend/routers/methodspecs.py`：`/extract` 现在内部先跑 Step1 提取再跑
    Step2 review 循环；删除已废弃的 `/review/llm`、`/review/override` 端点
    （旧的快照式 LLM review 与人工状态覆盖已不存在）；`/patch-value` 改用
    `apply_value_patches(source="human")`。`app.py` 的 paper-first 提取面板
    同步接入新的两步调用。
  - 测试：`tests/test_method_spec_contract.py` 新增
    `TestUnsupportedValueConsistency`；`tests/test_step1_extractor.py` 全部
    改写为测试裸 dict 提取契约；`tests/test_step2_reviewer.py` 的 D4 相关测试
    替换为 `TestMissingMappingFindings`；`tests/test_step2_reviewer_llm.py` 全部
    改写为测试 `spec_build.build_reviewed_method_spec`（收敛、预算耗尽、
    菜单分类合并、护栏丢弃未声明字段、`field_assessments`/`value_corrections`
    的应用/不应用边界）。全量 `pytest tests/` 524 passed / 18 skipped。
  - **已知未完成（推迟）**：`frontend/src/pages/SessionDetailPage.tsx` 的四项
    人工审核 UI 契约（§5.1：推荐值/下拉/source/字段解释）尚未实现，仍是旧的
    交互；`Disposition.BLOCKED`/`MethodReview.is_blocked` 在 D4 删除后已无任何
    代码路径能产出，是否清理待定。

### Follow-up (2026-08-11)

- **前端接线**：`SessionDetailPage.tsx` 的 `MethodSpecWorkflowPanel` 接入新后端
  契约——`/extract*` 现在一次性返回 `{spec, review, value_corrections}`（Step1+
  Step2 循环已经跑完），不再有单独的 LLM-review 任务；删除已废弃的
  `reviewPaperSpecLlm`/`reviewPaperSpecOverride`（对应后端 `/review/llm`、
  `/review/override` 端点已删除）。Step2 面板现在实现了计划 §5.1 的四项人工
  审核契约：推荐值（`value_corrections` 匹配上则预填，否则显示当前值）、
  enum 下拉（复用 `schema_reference.py` 的 `allowed_values`）、source（`Finding.
  evidence[]` 的 quote/table_ref/interpretation）、字段解释（`allowed_values`
  旁的 `description`）；同时新增一个"全部 LLM value_corrections 提议"列表
  （逐条可一键填入草稿，仍需手动 Apply 才生效——`value_corrections` 从不
  自动写入）。`methodSpecStore.ts` 新增 `valueCorrections` 字段持久化。
  `npx tsc -b` 通过，无类型错误。
- **`Disposition.BLOCKED`/`MethodReview.is_blocked` 清理**：确认 D4 删除后
  `BLOCKED` 已无任何代码路径可达，直接删除该枚举成员与 `is_blocked` 属性；
  `ResolvedMethodSpec.is_ready` 不再检查 `review.is_blocked`（其余三项检查
  ——`_all_concepts_mapped`/`_universe_filters_supported`/
  `_construction_within_capability`——不变）。同步修正
  `backend/routers/methodspecs.py`/`app.py` 里引用 `disposition=="blocked"` 的
  展示逻辑，改为展示 `needs_human_confirmation`。相关测试更新/删除
  （`tests/test_method_spec_contract.py`、`tests/test_step2_reviewer.py`）。
  全量 `pytest tests/` 523 passed / 18 skipped。

### Follow-up (2026-08-11，第二次)：Step2 循环改为全信任 + 前端 diff 展示

- **`src/steps/step2_reviewer/spec_build.py` 彻底重写合并策略**：删除"只合并
  声明字段"的护栏（`_merge_menu_fields`/`_apply_field_assessments`/
  `_apply_evidence_assessments` 等全部删除）。现在 LLM 每轮重写的**整份 spec
  直接生效**（唯一例外仍是 `factor_id`/`schema_version`/`paper.document_id`
  这 3 个 D7 字段，每轮都强制重新注入，不管 LLM 写了什么）。新增
  `_diff_json()` 通用递归 JSON diff，产出 `ReviewRound.diff`（每轮改了什么）
  与 `SpecBuildOutcome.total_diff`（从 Step1 裸提取到最终收敛结果的总账），
  `ReviewRound` 同时保存 `spec_before`/`spec_after` 两份完整快照。循环出口
  条件从"validate 通过且没有声明的新修正"改为"validate 通过且这一轮 diff
  为空"。`field_assessments`/`value_corrections`/`evidence_assessments` 降级
  为解释性注释（存进 `SpecBuildOutcome.llm_notes`），不再是生效开关。
  **实际效果**：此前"裸标量 `formation_month` 永远修不好、循环必然耗尽预算"
  的已知缺陷被修复——LLM 的结构修复现在直接生效，循环能正常收敛。
- **`prompts/review_gate/llm_review.md`**：更新开场说明，明确"你写的每个字段
  都会直接生效"；新增一份"这些字段直接驱动回测结果，请格外仔细核对"的提醒
  清单（即原来的 9 个高影响字段）；§2 的"不得借修结构之名改经验值"从硬性
  禁止软化为"改了也行，但要在 `value_corrections` 里说明原因"（因为现在没有
  单独的门禁去区分"结构修复"和"经验值修正"了）；§4 重写为"这些是解释性
  标注，不是生效开关"。
- **前端**：`SessionDetailPage.tsx` 新增 `DiffTable` 组件——渲染
  `total_diff`/`history[i].diff`，每一条改动展示 `field_path` + 旧值（删除线）
  + 新值（红色高亮），多轮情况下可切换"总账"或某一轮单独查看。移除了基于
  `value_corrections` 的"推荐值预填"逻辑（现在 LLM 的纠正已经直接体现在
  `spec` 里，不再是待确认提议）。`methodSpecStore.ts` 的 `valueCorrections`
  字段替换为 `totalDiff`/`history`。`backend/routers/methodspecs.py` 的
  `/extract` 任务结果新增 `history`/`total_diff`/`llm_notes` 三个字段
  （复用现有 `to_jsonable` 对 dataclass 的递归序列化，无需额外改动）。
- **已知取舍**：原先"9 个高影响字段的 `value_corrections` 必须人工逐条
  接受/拒绝才能写入"这条硬性门禁被取消——这些字段现在和其它字段一样被直接
  信任。D2 的规则审核（`inferred`/`unspecified`/`conflicting` →
  `NEEDS_HUMAN_CONFIRMATION`，需要人工补一个值）不受影响，继续保留。详见
  `docs/decision-log.md` 2026-08-11 条目的完整取舍讨论。
- 测试：`tests/test_step2_reviewer_llm.py` 全部改写（新增
  `TestFullyTrustedRewrite`/`TestDiffAndHistory`，`TestLoopConvergence` 新增
  "结构修复现在能真正收敛"的回归测试）。

- **`review_method_spec_with_llm` (Step2 LLM-assisted review) 现在会把完整
  `MethodSpec` JSON 也发给 LLM**（此前只发送 9 个高影响字段的 snapshot +
  论文全文），让它能对 snapshot 之外的任意字段（`signal.formula`、
  `data.fields`、`sample.*`、`reported_results.metrics`、`portfolio.legs`
  等）通过既有的 `additional_findings` 机制提出问题。`field_assessments`
  （改 `EvidenceStatus`）的可用字段范围保持不变，仍只限那 9 个 snapshot
  字段——只是"提出新问题"的可见范围扩大了，"改状态"的权限边界没变，
  `additional_findings` 的 disposition 也依然被硬编码为
  `NEEDS_HUMAN_CONFIRMATION`，LLM 无法借此自我批准或绕过 D4 能力检查。
  同步更新了 `prompts/review_gate/llm_review.md`：明确"两层"输入契约，并
  新增一份"重点关注"清单（formula 公式步骤、`signal.estimation` 完整性、
  `data.fields` 语义正确性、三段 sample 期间一致性、`reported_results`
  主指标匹配、`portfolio.legs` 多空方向）引导 LLM 该往哪儿找问题。新增 2
  个测试（`tests/test_step2_reviewer_llm.py`）验证完整 spec 确实进了
  prompt，且 snapshot 之外的字段也能落地成一个可用的 finding。

- **Step4 (`AdversarialSandbox._check_executes`) 的执行冒烟测试，除了原有
  的 `compute_signal(df)` 调用，现在还会在切片本身已经长得像返回面板
  （有 `ret`/`me`/`exchcd`/`shrcd`/`siccd` 列，即 "crsp_only" 模式）时，
  额外尝试一次 `BacktestExecutor.run_with_config()`，把只有跑到 Step5 全量
  数据才会暴露的引擎生命周期问题（`filter_universe` 等）提前到 Step4 就
  看到**。刻意保持跟现有设计同一套"宽松"姿态：只有 40 个 permno 的薄切片
  完全可能因为样本太小（比如撑不起十分位断点）而让引擎抛异常，这不代表
  代码有 bug——所以引擎这一步的任何异常都只记成 `report.warnings`，从不
  让 `executes_ok`/`report.passed` 变成 `False`；只有切片本身不具备返回
  面板列（"compustat"/"multi_source" 模式的信号输入切片，没有 `ret`/`me`
  等列）时才完全跳过这次尝试，避免对每个非 CRSP 因子都产生毫无信息量的
  噪音警告。Step5 的全量真实执行依然是唯一会真正阻断（fail loud）的地方。
  新增 `tests/test_sandbox_validation.py::TestFullEngineSmokeTest`（3 个：
  正常薄切片跑通不报警、universe filter 解析到返回面板没有的列时引擎报错
  但只警告不失败、非返回面板形状的切片完全跳过这次尝试）。全量测试
  533 passed / 18 skipped，零回归。

- **`FilterSpec.accepted_unapplied`/`unapplied_reason`（universe filter 的
  "other" 逃生舱）+ `ResolvedMethodSpec.unsupported_universe_filters()` 把
  "这条 universe filter 解析出的物理列不在返回面板上"（例如一条
  Compustat-only 的 backfill-bias 筛选，引擎的 `filter_universe` 只能看到
  CRSP 返回面板自身的 8 列)从"跑到
  Step5 才 `ValueError` 崩溃"提前到"resolve 阶段的 `is_ready` 就直接
  block"，跟 `WeightingScheme.OTHER` 那类 D4 "论文说了但引擎不支持"字段
  同一个处理姿态：默认仍然阻塞,只有人显式登记
  `accepted_unapplied=True` + `unapplied_reason`（人工决定"这条限制先不
  应用"),才会放行——`registry.build_config` 把这类 filter 单独收进
  `config["unapplied_universe_filters"]`（record 用,永不参与
  `filter_universe`/引擎执行),从不静默丢弃。新增
  `RETURNS_PANEL_NATIVE_COLUMNS`（`src/infra/models/method_spec.py`,一个
  写死的、CRSP 返回面板列名的静态集合，不是数据层查询——真正的
  eligibility-panel 支持（把 Compustat 等其他源的列 join 到返回面板上再
  跑 filter）本次有意不做，见 CHANGELOG 决策讨论。
  新增测试：`tests/test_method_spec_contract.py::TestUnsupportedUniverseFilter`
  （3 个）、`tests/test_registry_resolved_method_spec.py::
  TestAcceptedUnappliedUniverseFilter`（3 个）。全量测试 539 passed / 18
  skipped，零回归。

- **`apply_human_value_patches` + `POST /api/methodspecs/patch-value`
  ——人工直接改字段的值（不只是改 evidence status）**。这是"human review
  能不能像 v1 一样推荐值/自己选值"这个讨论的落地：`_review/override` 只能
  改 `EvidenceStatus`（论文证据等级),改不了提取器写错的实际内容；这次新增
  的路径专门解决"提取器把值本身写错了"（比如论文写 annual，提取器写成
  quarterly）的情况。
  - `apply_human_value_patches(paper, patches, reason)` 只允许改
    `_high_impact_sourced_values(paper)` 已知的那个固定字段清单（含带下标
    的 `portfolio.sorts[i].breakpoints.basis`）——`field_path` 来自前端输入，
    故意不做"任意字符串按 `.`/`[i]` 解析成 getattr 链"这种通用反射，只在
    这张已知安全的字段表里查,不会被引导到任意属性。改完的字段
    `status` 会被标成 `clear`（人工确认过了),并在 `evidence[]` 里留一条
    "human correction: <reason>" 的记录。返回一份新的 `MethodSpec`,不改
    原对象。
  - 加了一层类型感知的强制转换（`_coerce_to_current_type`）：前端文本框
    永远只会传字符串,但有些高影响字段本身是 `int`（`timing.
    holding_period`)或 `Enum`（`signal.direction` 等),直接赋值不会做
    pydantic 校验,字符串会静默存进本该是 int/enum 的字段。现在会按当前
    值的类型尝试转换,转不了就直接报错（不猜)。
  - 前端：`SessionDetailPage.tsx` 的 review 面板里,"needs_human_
    confirmation"的字段现在除了 status 下拉框,还多了一个"改值"的文本
    框,点"Apply N value correction(s)"提交后会清空当前 `review`/
    `resolved` 状态（不再有 hash 自动检测陈旧了——2026-08-09 早些时候的
    改动——所以这里手动清空,提示用户重新跑一遍 review 作为替代信号）。
  - 新增 `tests/test_apply_human_value_patches.py`（9 个测试：改值 + 标记
    clear / 不改原对象 / 未知字段拒绝 / 带下标字段可改 / 一次改多个 /
    字符串转 int 成功与失败 / 字符串转 enum 成功与失败）。全量测试
    533 passed。
  - **同一天的跟进（复刻 v1 的字段说明 + 下拉选择体验）**：改值那个输入框
    现在会先查 `GET /api/methodspecs/schema`（`build_schema_reference()`
    直接从 `MethodSpec` pydantic 模型机械生成的字段参考,`SchemaReferencePage.tsx`
    也在用同一份数据,不是新写的接口）——如果这个字段是枚举类型
    （比如 `portfolio.weighting` 只能是 `vw`/`ew`/`other`，`signal.direction`
    只能是 `positive`/`negative`/`non_monotonic`/`unspecified`），改值的
    输入框会自动换成下拉选择（带"Other"逃生舱可以手打),而不是让人瞎猜
    枚举值怎么拼；同时每个字段上面会显示一行简短的字段说明
    （`_FIELD_NOTES` 里已经写好的 `description`，比如 weighting 会显示
    "How portfolio returns are weighted across constituent stocks."）。
    自由文本字段（`timing.formation_rule`/`universe.description` 这类）
    没有 `allowed_values`，照旧是文本框。前端新增 `sessionApi.
    getSchemaReference()`，纯读取现成端点，后端零改动。

### Removed

- **移除了 `MethodReview`/`ImplementationResolution`/`ResolvedMethodSpec` 的
  paper/review 哈希绑定陈旧检测（`paper_spec_hash`/`review_hash`/
  `_hashes_current`）**——用户明确要求，权衡过"会破坏一个已有测试覆盖的
  安全机制"之后仍然选择去掉。具体改动：
  - `MethodReview` 去掉 `paper_spec_hash` 字段和 `content_hash()` 方法；
    `ImplementationResolution` 去掉 `paper_spec_hash`/`review_hash` 字段；
    `ResolvedMethodSpec` 去掉 `_hashes_current()`，`is_ready` 不再校验这层
    陈旧性——现在只看 `review.is_blocked` / 所有 concept 是否已映射 /
    sort 维度是否在引擎能力范围内。
  - **`MethodSpec.content_hash()` 本身保留**——`app.py`/
    `src/steps/step3_codegen/__init__.py`/`src/steps/step5_backtest_runner/
    __init__.py` 还在用它做插件/脚本命名的确定性 ID，这跟"陈旧检测"是两
    件独立的事，没有一起删。
  - `review_method_spec`/`review_method_spec_with_llm`/
    `apply_human_status_overrides`/`build_implementation_resolution` 都不
    再往 `MethodReview`/`ImplementationResolution` 里塞 `paper_spec_hash`/
    `review_hash`。
  - 更新了 `tests/_spec_test_helpers.py`、
    `tests/test_meta_coder_resolved_method_spec.py`、
    `tests/test_registry_resolved_method_spec.py`、`tests/test_step2_reviewer.py`、
    `tests/test_method_spec_contract.py` 里所有构造
http://localhost:5173/pipeline    `MethodReview(...)`/`ImplementationResolution(...)` 时传的
    `paper_spec_hash`/`review_hash` 关键字参数；删掉了两个专门测这层陈旧
    检测的测试（`test_review_bound_to_current_paper_hash`、
    `test_not_ready_when_paper_hash_stale`）。全量测试 524 passed（526 -
    2 个被删的陈旧检测测试）。
  - **注意（已知副作用，用户已确认接受）**：现在如果在 review/resolve 跑
    完之后又改了 paper 的内容（比如重新提取、或者以后加的"人工改值"功能），
    系统**不会再自动检测到"review 已经过期"并拦住 `is_ready`**——需要人
    自己记得改完东西要重新跑一遍 review/resolve，没有自动兜底了。见
    `docs/decision-log.md` 2026-08-09 条目里权衡的完整记录。

### Added

- **`build_implementation_resolution` 接上了已经写好但从没接线的 LLM 概念匹配
  兜底（`DataDictionary.normalize_fields_with_llm`）**。此前 `/resolve` 只跑
  确定性别名/子串匹配（`normalize_fields`），一个 paper concept 只要没在
  catalog 别名表里精确/子串命中就直接判定 unmapped——即使 LLM 兜底匹配器
  (`normalize_fields_with_llm`，连同硬校验、`tests/test_llm_normalized_
  mapping.py`) 早就写好了，只是没有任何生产代码调用它。现在：
  1. `build_implementation_resolution(...)` 新增可选 `llm_client=None` 参数：
     `None`（默认）行为完全不变，纯确定性；传入 client 时，对确定性匹配
     仍解析不出来的 concept 再跑一次 LLM 兜底（LLM 的每个选择依旧要通过
     `normalize_fields_with_llm` 自带的硬校验——source/column 必须是真实
     已注册的，选不出来的直接丢弃，不会静默瞎猜）。
  2. `ImplementationResolution` 新增 `llm_matched_concepts: list[str]` 字段，
     记录"只有 LLM 兜底才解析出来"的 concept（跟确定性解析的做区分，方便
     人工重点复核），`/resolve` 响应体和 session event 日志都带上这个列表。
  3. `POST /api/methodspecs/resolve` 新增可选 `llm_provider`/`llm_model`：
     不传（默认）完全不建 LLM client，行为跟以前一模一样；传了才会在
     确定性匹配失败时多尝试一次。`SessionDetailPage.tsx` 的 Resolve 按钮
     现在总是带上侧边栏选的 provider/model（反正只有真的有解析不出来的
     concept 时才会真的触发 LLM 调用），并在结果里高亮"LLM 匹配的 concept，
     请重点复核"。
  - **提醒：这解决的是"论文写法 vs 目录别名对不上"这一类（比如论文写
    "book equity"，目录里叫 `ceq`）**，不解决 `compustat_listing_duration`
    这种"目录里根本没有任何列能代表这个概念，因为它本质是需要计算的衍生量"
    的情况——LLM 面对这种情况应该、也会正确地返回"匹配不上"，这是
    `docs/known-gaps-paper-first-v2.md` gap #3 里描述的问题，需要单独的
    "衍生 filter 能力"设计（还没开始做）。
  - 新增 `tests/test_implementation_resolution_llm.py`（3 个测试：无
    llm_client 时行为不变 / 合法 LLM 匹配被记录进 `llm_matched_concepts` /
    LLM 提议一个没注册过的 source-column 时照样被丢弃、保持 unmapped）。

- **Session Step2 现在有 LLM-backed review 和人工字段决议 UI 了**。之前的
  gap：`src/steps/step2_reviewer/review.py` 的 `review_method_spec()` 是纯
  规则检查（D2 evidence-status matrix + D4 engine-capability menu），文档里
  自己写着"an optional LLM-assisted discovery pass ... is deferred to a
  later iteration"；同时 `SessionDetailPage.tsx` 的 Step2 面板只能跑这个
  规则版 review，且明确写着"this step has no manual field-editing UI yet"。
  旧版 `PipelineE2EPage.tsx` 里看起来有 LLM review 按钮和逐字段决议表单，
  但那套 `/api/methodspecs/review/llm` 端点和 `ReviewResult`/`spec` 请求体
  属于 2026-08-07 已经删除的 v1 `backend/routers/methodspecs.py`，实际上
  是死代码（会直接 422），不是一个可用的替代方案。
  现在补上（新增 `review_method_spec_with_llm()` / `apply_human_status_overrides()`，
  两者跟 `review_method_spec()` 共享同一个 `_compute_findings()` helper，
  `DISPOSITION_MATRIX` 仍然是唯一决定 disposition 的地方）：
  1. `POST /api/methodspecs/review/llm`（异步 job，同 `/extract` 模式）：
     用 `prompts/review_gate/llm_review.md` 让 LLM 重新读一遍论文原文，
     只能对已提取的高影响 `SourcedValue` 字段提出 `EvidenceStatus` 重新判定
     （写进 `MethodReview.status_overrides`），或者提出新的
     `kind="inconsistent"` finding——但新 finding 永远被强制成
     `NEEDS_HUMAN_CONFIRMATION`，LLM 自己没有批准/拦截的权力；D4 engine-
     capability 检查完全不受 LLM 影响。
  2. `POST /api/methodspecs/review/override`（同步，不调 LLM）：人工直接
     给某个 D2 字段指定"我确认论文其实写清楚了"这类修正后的
     `EvidenceStatus`，同样只是喂给 `DISPOSITION_MATRIX` 重新算，不是让人
     直接写 disposition。
  3. `_extract_job` 现在把 `paper_text` 一起塞进 job 结果（之前只有
     `spec`/`error`/`raw_llm_output`/`token_usage`），因为 LLM review 需要
     原始论文文本；`MethodSpecWorkflowState`（`lib/methodSpecStore.ts`）新增
     `paperText`/`reviewSource` 字段做 sessionStorage 持久化。
  4. `SessionDetailPage.tsx` 的 Step2 面板：新增"Run LLM-backed review"
     按钮（跟规则版并列，用 source badge 区分是 rules/llm/human 产出的）；
     每条 `disposition=needs_human_confirmation` 且 `kind!="unsupported"`
     的 finding 旁边现在有一个 `EvidenceStatus` 下拉框，选完点"Apply N
     human override(s)"调用上面的 `/review/override`。
  - **已知局限，没有在这次改动里处理**：`MethodReview.is_blocked`/
    `ResolvedMethodSpec.is_ready` 目前只看 `Disposition.BLOCKED`（D4），
    `NEEDS_HUMAN_CONFIRMATION`（D2）本身并不会让 `is_ready` 变 false——这
    是重构前就有的既存行为（`test_step2_reviewer.py` 里显式断言了
    `not review.is_blocked`），所以这次新增的人工 override 面板改的是
    finding 本身是否存在/其 evidence_status 是否准确，而不会让 Resolve
    按钮从"不可用"变"可用"。真正会拦住 Resolve 的只有 D4 unsupported 项
    （引擎能力menu之外的选择），这类项本来就不允许被覆盖。
  - 新增 `tests/test_step2_reviewer_llm.py`（5 个测试，覆盖 LLM 只能重判
    它被给到的字段 / 不能碰 D4 blocked / additional finding 强制
    needs_human_confirmation / 人工 override 不调 LLM 也能重算 disposition）。

- **上面那版的两个跟进修正（同一天）**：
  1. **`paper_text` 现在持久化到磁盘，不再只活在 sessionStorage/job 结果
     里**。之前 `paper_text` 只塞进内存态的 job 结果和前端
     `MethodSpecWorkflowState.paperText`（sessionStorage），对已经提取过
     的旧 spec（sessionStorage 被清过，或 job 早就过了
     `JOB_TTL_SECONDS` 过期）完全找不回来，LLM review 会直接报"No paper
     text available"。现在 `_extract_job`（`backend/routers/
     methodspecs.py`）复用 `backend/routers/papers.py` 已有的
     `data/paper_text_cache/{document_id}.txt` 缓存约定，把 paper_text
     按 `document_id` 落盘；前端新增 `sessionApi.getPaperText(documentId)`
     调用既有的 `GET /api/papers/{paper_id}`，在点"Run review"时如果
     `state.paperText` 没有，先按 `paper.paper.document_id` 去查这个缓存，
     查到就用、查不到才真正退化成规则版。
  2. **Step2 面板的"规则版"/"LLM 版"两个按钮合并成一个"Run review"**。
     因为 `review_method_spec_with_llm()` 内部本来就是通过共享的
     `_compute_findings()` 把 D2/D4 规则检查跑一遍（LLM 只是在这基础上
     叠加 evidence_status 修正），所以 LLM 版本身就是规则版的超集，两个
     并列按钮容易让人以为要"二选一"（这是 v1 `review_with_llm` 的设计：
     LLM 版恒定合并规则版结果，不作为平行选项）。现在只有一个"Run
     review"：paper_text 能拿到（无论是当次提取自带的还是上面缓存查到
     的）就跑 LLM 版，拿不到才 fallback 成同步的规则版并照常展示结果，
     不再要求用户自己二选一。

### Fixed

- **`portfolio.missing_policies[].action` 也改成真正的 Enum**
  （`MissingActionScheme(str, Enum)`: `drop`/`other`，跟之前 `weighting`
  的 `WeightingScheme` 完全同一套模式）。根因：这个字段之前是纯
  `SourcedValue[str]`，`review.py` 里从来没有对它做过 D4 引擎能力检查（不像
  `weighting`/`return_combination` 早就有），所以论文原话式的自由文本
  （实测真实提取结果是 `"Require nonzero total assets in both input years."`
  这种完整句子）会一路静默流到 `registry.build_config`，被 `_track_clamp`
  悄悄替换成默认值 `"drop"`，全程没有任何可见的拦截点。现在：(1) 模型层
  加了 `MissingActionScheme` 枚举，`other` 是逃生舱（同
  `WeightingScheme.OTHER`/`ConstructionType.OTHER` 模式，论文原话仍保留在
  `evidence[]` 引用里）；(2) `review.py` 新增 `ENGINE_MISSING_ACTION_MENU`
  + D4 检查，任何不是 `drop` 的值现在会在 review 阶段就 `blocked`；(3)
  `extractor.py` 的 `normalize_engine_vocabulary()` 新增
  `_normalize_missing_action()`（关键词匹配 `drop`/`exclud`/`remov`/
  `require`/`omit`/`discard`，命中则归一化成 `"drop"`，否则归一化成
  `"other"`——因为字段现在是真枚举，任意自由文本会在 `MethodSpec.
  model_validate()` 时直接校验失败，而不只是像以前那样留到 review 才拦截）；
  (4) 提取 prompt 新增 §1.7c，明确要求 LLM 对"排除/丢弃类"的缺失值处理写
  `drop`，其余写 `other`。新增 4 个测试（`tests/test_step1_extractor.py`
  2 个 + `tests/test_step2_reviewer.py` 2 个）。全量测试 505 passed/18
  skipped（501+4 新增）。

- **真实 400 bug：step3 报 `concept_id 'total_assets_t_minus_1' has no
  physical column mapping`**。根因是 LLM 提取时把 `signal.formula.steps[]`
  里用到的 lag 变量名（比如 `total_assets_t_minus_1`/`_2`，只是公式内部的
  临时命名）直接当成 `universe.filters[].concept_id` 写了进去，但这两个
  名字从未在 `data.fields` 里注册过——`ImplementationResolution.
  concept_mapping` 只从 `data.fields`（+ universe.filters 自身，用裸
  `{"field": concept_id}` shim）匹配物理列，一个连 `data.fields` 都没有的
  filter concept 永远不可能解析成功，此前完全没在 review 阶段拦截，直到
  step3 `build_config` 才报错，而且报错信息完全看不出是"提取时把公式内部
  变量误当成 filter concept"这个根因。
  修了两处：(1) `src/steps/step2_reviewer/review.py` 的 `_capability_findings`
  新增一条 D4 检查：任何 `universe.filters[].concept_id` 若不在
  `data.fields[].concept_id` 里，直接 `kind="unsupported"`,
  `disposition=BLOCKED`，在 review 阶段就挡住，不再等到 step3 才炸出一个
  莫名其妙的 400（`docs/known-gaps-paper-first-v2.md` gap #3 的其中一种情形，
  现已修复其中"lag 变量名当 filter concept"这个子问题）。(2)
  `prompts/extractor/method_spec_extractor.md` 新增 §1.8b，明确告诉 LLM：
  `universe.filters[].concept_id` 必须也是一个真正的 `data.fields` 条目，
  绝不能直接借用公式步骤里的 lag 后缀变量名。新增 2 个回归测试
  （`tests/test_step2_reviewer.py`）。全量测试 501 passed/18 skipped
  （499+2 新增）。已用真实触发这个 bug 的 draft 直接对 `/api/methodspecs/
  review` 发请求验证：现在正确返回 3 条 blocked finding，而不是悄悄放行到
  step3 才报错。

### Changed

- **Session step1/2 页面布局改为单列（Events → 步骤内容 → Result），且 step1 已提取过时直接内联展示 `MethodSpecBoard`**。
  之前 step1/2 和 step3-8 共用同一套两栏 request/result 网格，`MethodSpecBoard`
  内容偏长偏密，两栏挤在一半宽度里很局促；且 step1 若已经提取过，只显示一行
  "Already extracted... 去 Step 2"提示，看不到实际提取结果，得跳到 step2 才
  能看。现在 step1/2 改成单列：`Events` 卡片在最上面（extract/review job 的
  进度是这两步最先要看的），中间是该步骤自己的卡片（extract 面板 / review+
  resolve 面板），下面是 `Result` 卡片；step3-8 的两栏布局完全不变（把两个
  Events 卡片实例提成一个共享的 `eventsCard` JSX 变量，避免两个分支各写一份
  再走样）。同时 step1 只要 `state.paper` 已经存在（之前提取过），就直接在
  同一张卡片里内联渲染 `MethodSpecBoard`（而不是仅一行文字提示），再提取会
  覆盖它。`npm run build`/`npm run lint` 均干净，浏览器手动验证过单列顺序，
  全量后端测试 499 passed/18 skipped 不受影响（纯前端改动）。

- **Step2 review 面板重做**：去掉 review 之前就一直显示的完整
  `MethodSpecBoard`（未 review 的 spec 没必要占地方），"Run review"/
  "Resolve to a codegen-ready MethodSpec" 两个按钮 pending 时改成
  "Reviewing…"/"Resolving…" 文字（之前 sync 请求没有任何进度反馈，看起来像
  卡住了——实测 `/api/methodspecs/review` 对真实 spec 只要 ~25ms，纯前端缺反馈
  问题，不是后端慢）。findings 列表改成每条一个带 disposition 徽章
  （blocked 红色/其余 outline）的卡片，field_path 加粗、reason 单独一行，
  比之前一整行纯文字更容易一眼看出"review 之后哪些字段被标记了"。
  `MethodSpecBoard.tsx` 里 "Breakpoint population" 表头改名
  "Breakpoint basis"（对应 v1 时代就用的术语，`portfolio.sorts[].
  breakpoints.population` 字段名本身不改）。
  另外说明一下 `portfolio.missing_policies[].action` 的问题：这个字段本来就
  设计成自由文本（`SourcedValue[str]`），存的是论文原话（比如实测真实提取
  结果是 `"Require nonzero total assets in both input years."` 这种完整
  句子），不是 `drop` 这种规范 token——这是有意为之，`MethodSpecBoard` 显示
  整句话是对的。`registry.build_config` 会在生成 engine 配置时把它 clamp 成
  `drop`/`unspecified` 两个菜单值之一，但那只影响最终 resolved config，不
  影响这里展示的原始论文原话，两者不冲突。
### Fixed

- **Session 里 step1/2 现在完成后会变色并自动跳转下一步，且 step1/step2 页面不再是同一个面板**。
  之前两个问题都在：(1) `MethodSpecWorkflowPanel` 不管 URL 是 `steps/1` 还是
  `steps/2` 都渲染同一整套 extract+review+resolve UI，两页看起来一模一样；
  (2) step1/2 的完成状态只存在 `sessionStorage`（`methodSpecStore`），从不
  写回 session manifest 的 step attempts，所以 `StepStepper` 的颜色徽章永远
  是 `not_started`，且没有任何步骤（包括 3-8）在成功后自动跳到下一步。
  现在：`MethodSpecWorkflowPanel` 按 `step` 拆成两个真正不同的视图——step1
  只有"上传 PDF /抽取"，抽取成功后立刻跳到 step2；step2 若还没有
  `state.paper` 则显示"还没抽取，去 Step 1"提示，否则显示 review + resolve，
  resolve 成功（`is_ready`）后立刻跳到 step3。`SessionDetailPage` 新增
  `specState`（把 `MethodSpecWorkflowPanel` 的 sessionStorage 状态提升到父
  组件），传给 `StepStepper` 做 step1/2 的颜色覆盖（`specStepStatus`：
  `paper` 存在 -> success；`review` 存在但被 block -> blocked；`review` 存在
  未 block -> running；`resolved` 存在 -> success）。同时给 step3-8 的
  `runMutation`/job 完成也补上了自动跳转（新增 `isFailureResult()`
  辅助函数——不是"HTTP 调用没抛异常就算成功"，而是识别 `passed`/`is_ready`/
  `success`/`status` 里任何明确的失败标记，没有才跳转，避免把 step4
  validate 的 `passed:false` 之类误判成成功后跳走）。`npm run build`/
  `npm run lint` 均干净，浏览器手动验证 step1/step2 渲染的内容确实不同，
  且从 step1 抽取成功会自动进入 step2。全量后端测试 499 passed/18 skipped
  不受影响（纯前端改动）。

- **React 的 Extractor / Review & Resolve 不再是失效的 sidebar 占位项，且不再错误地依附于 session step1/2。** 新增独立 `/extract` 与 `/review` 页面：Extractor 支持 PDF、document id、target factor、全局 LLM provider/model、SSE job progress、结构化 MethodSpec preview，并把成功结果直接带到 review；Review & Resolve 从后端持久化的 `runs/method_specs/{unreviewed,reviewed,...}` 生命周期加载 draft/review，展示 deterministic findings、blocked 状态和 implementation resolution。Sidebar 现在可直接进入两个页面；新 session 和 session 列表从真正属于 session 的 Step 3 开始，stepper 隐藏已从 session backend 删除的 Step 1/2，旧的 `/sessions/:id/steps/{1,2}` URL 分别重定向到独立页面。修复了此前“独立 MethodSpec API，却用 sessionStorage + session id 模拟 step1/2”的 UI/架构错位。

- **（同日，用户要求撤回上一条的重定向部分）Step1/2 重新并入 session 详情页**。
  上一条改动把 `/sessions/:id/steps/{1,2}` 重定向去独立的 `/extract`/`/review`
  页面、并把 stepper 过滤成只显示 Step 3 起——用户明确要求改回去。撤销了
  `App.tsx` 里那两条 `<Navigate>` 重定向路由（`/sessions/:sessionId/steps/:step`
  这条通用路由现在会正常匹配 step=1/2，交给 `SessionDetailPage`）和
  `StepStepper.tsx` 的 `.filter((def) => def.step >= 3)`，恢复显示全部 8 步。
  `SessionDetailPage.tsx` 里原有的 `MethodSpecWorkflowPanel`（`step === 1 ||
  step === 2` 时渲染，调用独立的 `/api/methodspecs/*` 生命周期端点）本来就没被
  删掉，只是路由绕过了它——所以这次是纯撤销路由/stepper 改动，没有恢复任何
  逻辑代码。独立的 `/extract`、`/review` 页面本身保留未删，仍在 sidebar 里，
  只是 session 内的 step1/2 不再重定向过去。`npm run build`/`npm run lint`
  均干净，浏览器手动验证 `/sessions/{id}/steps/1` 重新在 session 详情页内
  渲染 Extract 面板。

- **`GET /api/methodspecs/schema` 重新实现，`SchemaReferencePage.tsx` 恢复可用**。
  该端点属于已删除的 v1 `backend/routers/methodspecs.py`，v2 迁移时从未补建
  v2 等价物；今天早些时候把 `paper_methodspecs.py` 重命名为 `methodspecs.py`
  后，前端这个调用从"路由完全不存在"变成命中新路由的 `/{stage}` catch-all
  （`stage="schema"`），依然是 404（"Unknown stage 'schema'"），最终表现
  不变但排查路径变了。新增 `src/infra/models/schema_reference.py::
  build_schema_reference()`，直接从 `MethodSpec` 模型机械生成
  `{fields: {dotted_path: {...}}, json_schema}`（复用 `schema_render.py`
  "从模型元数据生成，而不是手写文档" 的思路），`allowed_values`/`example`/
  `sub_fields`（复合对象的直接子字段路径）/`list_item_fields`（list 字段
  项本身的字段名）全部机械推导；`description`/`usage`/`engine_consumed`
  这三项无法从类型标注推导，来自模块内一份按 dotted path 索引的精选表
  （对照 `registry.py::_build_config_from_resolved` 逐项核实哪些字段真正
  进了 engine 的 resolved config，未在表里的字段默认 `engine_consumed=
  False`）；`origin` 固定为 `"llm"`（`MethodSpec` 现在只是 Step1 抽取产物，
  不再像 v1 那样混有 review/resolution 状态）。新增
  `@router.get("/schema")`（注册在 `backend/routers/methodspecs.py` 的
  `/{stage}` catch-all之前，避免被吞掉）。
  过程中发现并修复一个真实的检测 bug：Pydantic v2 会把 `SourcedValue[T]`
  具体化成一个真正的类（而非 `typing._GenericAlias`），`typing.get_origin()`
  对它返回 `None`——之前用这个检测的写法会把 `portfolio.weighting`
  这类字段误判成普通嵌套 BaseModel，把 `allowed_values` 埋进
  `portfolio.weighting.value` 子字段里，而不是直接挂在 `portfolio.weighting`
  本身。改用 `__pydantic_generic_metadata__` 检测后确认正确（
  `schema_render.py` 里同样的检测写法凑巧没受影响，因为它的用途下两种
  渲染结果碰巧一致，未改动那个文件）。新增
  `tests/test_schema_reference.py`（8 tests，含专门覆盖这个检测 bug 的
  回归测试）。全量测试 499 passed/18 skipped，前端页面已在浏览器里手动
  验证渲染正常（description/usage/allowed values/engine-consumed badge/
  has-fields 全部正确显示）。

- **`MethodSpecBoard.tsx` 重写以匹配当前 paper-first `MethodSpec` schema**
  （之前整个组件还是按已删除的 v1 扁平 schema 写的：`spec.factor_name`/
  `spec.review_status`/`spec.codegen_ready`/`spec.ambiguous_fields`/
  `spec.paper_ref`/`spec.sign`/`signal.timing.*`/`portfolio.sort.*`/
  `portfolio.weighting`（裸字符串）/`reported_results.return_calculation.*`
  这些字段路径在当前 schema 里根本不存在，导致 Session 详情页 step1
  "2. Review" 里展示的 MethodSpecBoard 几乎全是"—"）。现在按
  `src/infra/models/method_spec.py` 的真实嵌套结构重写：`paper`（citation/
  publication_year）、`signal`（definition/economic_intuition/direction/
  formula.steps[]/estimation，均为 `SourcedValue` 展示 value+evidence+
  status）、`timing`（formation_rule/formation_month/rebalance_frequency/
  holding_period/data_availability）、`sample`（三段独立采样区间）、
  `universe`（description + filters[] 表格）、`portfolio`
  （construction_type/weighting/return_combination + sorts[]/legs[]/
  missing_policies[]/transforms[] 表格）、`data.fields[]`、
  `reported_results.metrics[]`。`Field` 组件现在能直接接收一个
  `SourcedValue`-形状的对象并自动拆出 value/evidence/status，不用每处调用
  都手动 `.value`/`.evidence`。`npm run build`/`npm run lint` 均干净。
  **未动**（已有文档记录的、独立的、超出本次范围的已知问题）：
  `PipelineE2EPage.tsx`/`SchemaReferencePage.tsx` 仍直接调用已删除的 v1
  `/api/methodspecs/{extract,schema}` 端点（`SchemaReferencePage` 现在会命中
  新路由的 `/{stage}` catch-all，返回 404 "Unknown stage 'schema'"——同样是
  404，只是错误信息变了，行为本质没变）；这两个页面在 2026-08-07/08-08 就已
  被记录为独立的遗留页面，需要单独的一次性工作（重建 `field_help.py` 的 v2
  等价物/迁移 Pipeline E2E 页面的提取调用），不在本次"schema 与展示不匹配"
  修复范围内，需要用户单独确认是否要做。

### Changed

- **移除代码/文件/路由里纯粹为了区分已删除 v1 而加的 `paper_`/`Paper` 前缀**
  （v1 `MethodSpec` 已在 2026-08-07 完全删除，这个前缀失去存在意义）。
  文件：`src/infra/models/paper_method_spec.py`→`method_spec.py`、
  `src/steps/step1_extractor/paper_extractor.py`→`extractor.py`、
  `src/steps/step2_reviewer/paper_review.py`→`review.py`、
  `backend/routers/paper_methodspecs.py`→`methodspecs.py`、
  `prompts/extractor/paper_method_spec_extractor.md`→`method_spec_extractor.md`，
  以及对应的 4 个测试文件。符号：`PaperMethodSpec`→`MethodSpec`、
  `PaperExtractor`→`MethodSpecExtractor`、`PaperExtractionResult`→
  `ExtractionResult`、`build_paper_method_spec`→`build_method_spec`、
  `review_paper_method_spec`→`review_method_spec`、`build_paper_extractor`→
  `build_extractor`（均用 IDE rename 保证全部引用同步）。API 路由
  `/api/paper-methodspecs/*`→`/api/methodspecs/*`（v1 的同名路由已删除，
  路径空出）。前端 `paperFirstStore.ts`→`methodSpecStore.ts`，
  `PaperFirstState`/`getPaperFirstState`/`setPaperFirstState`/
  `PaperFirstPanel`→`MethodSpecWorkflowState`/
  `getMethodSpecWorkflowState`/`setMethodSpecWorkflowState`/
  `MethodSpecWorkflowPanel`。**明确保留不动**（这些 `paper`/`Paper` 是真实
  领域词，不是版本消歧前缀）：`PaperRef` 类、`MethodSpec.paper`/
  `paper_ref`/`paper_name`/`paper_expression`/`paper_source_hint` 等字段、
  `data/papers/`、`paper_text_cache`、"paper-first" 这个研究设计名称本身
  （README/AGENTS.md/docs 里的用法）、CHANGELOG 历史条目与
  `docs/decision-log.md`/`docs/methodspec-v2-plan.md`（按现有约定，历史记录
  保留写作时的真实名称，不回填重命名）。全量测试 491 passed/18 skipped，
  `npm run build`/`npm run lint`（frontend）均干净。

### Fixed

- **`portfolio.weighting` 从自由字符串改为真正的 Enum**
  （`WeightingScheme(str, Enum)`: `vw`/`ew`/`other`，`src/infra/models/
  method_spec.py`）。根因见下一条 CHANGELOG：`schema_render.py` 只会给真正
  的 Python `Enum` 字段自动把允许值拼进 prompt，`weighting` 之前是纯
  `SourcedValue[str]`，完全吃不到这个机制。现在改成 Enum 后，prompt 的
  schema skeleton 会自动显示 `"vw | ew | other"`，不再需要单靠 prompt 里
  一句话提醒。`other` 是逃生舱（同 `ConstructionType.OTHER` 的既有模式）：
  论文真实描述的自由文本仍保留在该字段的 `evidence[]` 引用里，只是分类
  `.value` 被约束到菜单内。`return_combination` 保持 `SourcedValue[str]`
  不变（其自由文本形态远比 weighting 多样，枚举化会丢信息，本次未改）。
  联动修复：`normalize_engine_vocabulary()`（extractor.py）现在把无法识别
  的 weighting 自由文本映射到 `"other"` 而不是原样保留（否则会在
  Pydantic 校验时直接报错，而不是像以前那样留到 review 阶段才拦截）；
  `review_method_spec`（review.py）的 D4 weighting 检查改用
  `getattr(weighting, "value", weighting)` 兼容"直接属性赋值绕过校验"的
  测试写法（Pydantic v2 attribute assignment 默认不校验/不强制转换）。
  更新了 2 个受影响的测试。全量测试 491 passed/18 skipped。

- **`pytest tests/` 不再污染真实 `runs/` 目录**。`test_session_api.py`/
  `test_backend_api.py`/`test_experiment_replication_diagnosis_api.py`/
  `test_backend_paper_methodspecs_api.py` 都在模块顶层 `from backend.main
  import app`，而 `backend.state.RUNS_DIR` 只在 import 时解析一次
  `FACTOR_AGENT_RUNS_DIR` 环境变量——之前完全没有任何 conftest 兜底，一次全量
  `pytest tests/` 实测在真实 `runs/` 下留下了 114 个 session/evidence/
  method_specs/backtest_scripts 杂散文件。新增 `tests/conftest.py`，在
  collection 阶段（早于任何测试模块 import）把 `FACTOR_AGENT_RUNS_DIR`
  默认设为 `.runs_scratch`（复用已有的 gitignored 手动 live-test 约定）。
  已清理本次误产生的全部 114 个文件（未触碰用户真实的 session/工作数据）。

- **提取 prompt 现在直接告诉 LLM `weighting`/`return_combination` 的规范 token**
  （`prompts/extractor/paper_method_spec_extractor.md` 新增 §1.7b）。根因
  更深：`schema_render.py` 会自动把真正的 Python `Enum` 字段的允许值拼成
  `"vw | ew"` 这种提示塞入 prompt 的 schema skeleton，但 `PortfolioSpec.
  weighting`/`return_combination` 在模型里是普通 `SourcedValue[str]`（故意不用
  enum，保留记录引擎不支持的自由文本的能力），所以这个自动机制对这两个字段
  完全不生效——prompt 里之前没有任何一句话告诉 LLM 常见情况下应该写哪个
  规范 token，这才是 gap #1 的更深层根因。新增 §1.7b 明确要求：匹配
  vw/ew/extreme_group_spread/average_leg_spread/single_signal_portfolio_
  return/full_portfolio_return 时必须写精确 token，真正不匹配时才写自由
  文本。与上一条 CHANGELOG 里 `normalize_engine_vocabulary()` 的事后归一化
  互补（事前预防 + 事后容错两道防线），不相互取代。已验证
  `tests/test_step1_extractor_paper_spec.py`（15 passed）不受影响。

- **Step1 extractor 现在会归一化 `portfolio.weighting`/`portfolio.
  return_combination` 的自由文本到 engine 菜单 token**
  （`src/steps/step1_extractor/paper_extractor.py::normalize_engine_vocabulary`，
  在 `build_paper_method_spec` 里、`PaperMethodSpec.model_validate` 之前调用）。
  修复 `docs/known-gaps-paper-first-v2.md` gap #1：之前 LLM 提取常把
  `weighting` 写成 `"value-weighted"`/`"equally weighted"` 这类自然语言而不是
  `vw`/`ew`，`return_combination` 写成整句话而不是
  `extreme_group_spread`/`average_leg_spread` 等 token。这不仅让 Step2 review
  的 D4 引擎能力检查永久 `blocked`（此前没有任何 resolution 步骤能解开），
  一旦有人手动放行，`registry.build_config`/`_clamp_with_provenance` 还会把
  这个不在菜单里的值**静默 clamp 成默认值**（`vw`/`extreme_group_spread`），
  这是真实的正确性 bug，不只是体验问题。归一化只做已知同义词的精确映射
  （如 `"value-weighted"→"vw"`、同时出现 long/short 措辞→
  `extreme_group_spread`），无法识别的文本原样保留，review 仍会照常拦截，
  不会静默猜测经验参数。新增 7 个测试
  （`tests/test_step1_extractor_paper_spec.py::TestEngineVocabularyNormalization`）。
  全量测试 491 passed/18 skipped，无回归。

### Added

- **v1 `MethodSpec` 完全删除**（`src/infra/models/method_spec.py` 已不存在）。
  论文优先 schema（`PaperMethodSpec`/`MethodReview`/`ImplementationResolution`/
  `ResolvedMethodSpec`，`src/infra/models/paper_method_spec.py`）现在是仓库里
  唯一的 MethodSpec 模型。所有 `isinstance(spec, ResolvedMethodSpec)` 双分派
  分支都已收敛为单一路径：`registry.build_config`、`MetaCoder.
  generate_plugin`/`_build_prompt_from_resolved`、`script_generator.
  pick_signal_input_mode`/`generate_backtest_script`、`step4_validator.
  validate`、`step5_backtest_runner`（`_spec_factor_id` 等 4 个辅助函数简化为
  直接属性访问）、`step6_dual_track_controller` + `experiment_spec.py`、
  `RepairLoop`、`Pipeline.run_from_method_spec`/`_build_validation_slice`、
  `assemble_signal_master_table`、`backend/spec_parsing.py`、`app.py` 的
  MetaCoder/Backtest 页面 spec 选择器。
  **整体删除**（无 v2 等价物，且已确认无其他引用）：`SemanticExtractor`
  （`step1_extractor/__init__.py` 清空为占位说明）、`ReviewGate` +
  `resolution.py`（`apply_decisions`）+ `field_help.py` + `cz_suggest.py`
  （`step2_reviewer/__init__.py` 同样清空）、`field_contract.py`、
  `Pipeline.run_full_pipeline`/`PipelineStatus`/`MAX_REEXTRACT`、
  `backend/routers/methodspecs.py`、`backend/routers/evaluations.py`（连带
  `scripts/run_extraction_eval.py`）、`scripts/{extract_methodspecs,
  resolve_review_blocks,review_methodspecs,validate_methodspecs,
  run_real_asset_growth_experiment}.py`、`src/evaluation/helpers.py`
  （唯一还有用的 `load_signaldoc` 迁到了 `src/infra/reference/__init__.py`，
  它自己的 C&Z reference profile 逻辑的唯一消费者）。`backend/routers/
  sessions.py` 的 step1(extract)/step2(review/resolve) 端点整体删除——
  session 现在从 step3（脚本构建）开始，没有 session 内的抽取/评审 UI 流程了，
  只有独立的 `backend/routers/paper_methodspecs.py` API + app.py 的
  "Paper-First Workflow" 页面。
  **测试文件**：删除 ~18 个纯 v1 专属测试文件（`test_extractor.py`、
  `test_field_contract.py`、`test_formula_symbol_coverage.py`、
  `test_holding_period_derivation.py`、`test_llm_enum_false_positive_filter.py`、
  `test_meta_coder_prompt.py`、`test_method_spec_sign_validation.py`、
  `test_no_default_source.py`、`test_reextraction_loop.py`、
  `test_resolution.py`、`test_reviewer_silent_defaults.py`、
  `test_unsupported_fields.py`、`test_pipeline_status_artifacts.py`、
  `test_evaluations_api.py`）；5 个被 `_resolved_method_spec` 姊妹版本取代的
  e2e 测试文件重命名为规范名（`test_mvp_e2e.py`/
  `test_execute_data_path_override.py`/`test_bridge_track_e2e.py`/
  `test_accruals_e2e.py`/`test_real_wrds_samples_e2e.py`，v1 原版删除）；
  合并 `test_step_diagnostics.py`（原 step1/2 v1 专属类删除，step3/4 换成
  `asset_growth_resolved_spec()`，step5-8 本就与 spec 无关，原样保留）；
  修复 `test_experiment_replication_diagnosis_api.py`/`test_session_api.py`/
  `test_backend_api.py`/`test_signal_master_multisource.py`/
  `test_bridge_track_wiring.py`/`test_llm_normalized_mapping.py` 等混合内容
  文件里残留的 v1 fixture 构造；`tests/_spec_test_helpers.py` 的
  `asset_growth_resolved_spec()` 新增 `factor_id` 参数（多 session 测试要求
  同一经济学场景下有不同 factor_id 避免 RunRegistry 碰撞）。
  全量套件 483 passed / 18 skipped（较之前的 630 减少是因为删除了纯 v1
  专属测试，不是回归——每一步都验证过 0 failure），`ruff check --select
  F401,F821,F811` 全绿。Streamlit 应用烟雾测试通过。
  **已知未验证/未跟进的缺口（有意不做，明确告知用户）**：React 前端
  （`frontend/src/`）仍在调用已删除的 `/api/methodspecs/*`、
  `/api/evaluations/*`、`/api/sessions/{id}/steps/1/extract*`、
  `/api/sessions/{id}/steps/2/review*` 端点（`sessionApi.ts`、`steps.ts`、
  `BacktestExperimentsPage.tsx`、`PipelineE2EPage.tsx`、
  `SchemaReferencePage.tsx`、`SessionDetailPage.tsx`）——本轮完全没有触碰
  前端代码，这些调用点现在会 404。

- 黄金数值 e2e 测试迁移收尾（6/6 全部完成）：新增
  `tests/_spec_test_helpers.accruals_resolved_spec()`（Sloan 1996 accruals，
  6 个 SIGNAL_INPUT concept 映射到 comp_funda 的 act/lct/che/dlc/dp/at，
  与 v1 fixture 同样复用 asset_growth 的黄金数值/合成数据，`build_config`
  逐字段核对一致）+ `test_accruals_e2e_resolved_method_spec.py`（golden
  numbers 匹配 `rel=1e-9`）。发现 `test_real_wrds_samples_e2e.py` 其实
  **并未被跳过**——`data/local/validation_sample/` 真实样本数据本机已存在，
  之前误判为"依赖不存在的私有数据"；该文件只是 smoke test（不校验黄金数值，
  只断言 n_months>0/非 NaN），且只调用已双分派的
  `assemble_signal_master_table`/`registry.build_config`，属于低风险快速
  转换：新增 `test_real_wrds_samples_e2e_resolved_method_spec.py`（复用
  `asset_growth_resolved_spec()`，对真实 WRDS 样本 CSV 跑通)。
  全量套件 630 passed / 26 skipped，无回归。至此 6 个黄金数值 e2e 测试
  全部有了 `ResolvedMethodSpec` 姊妹版本（v1 原文件保留不动，双轨并存）。

- 黄金数值 e2e 测试迁移（4/6）：新增 `tests/_spec_test_helpers.
  asset_growth_resolved_spec()`——与 v1 committed fixture
  `cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json` 经济学完全
  等价的 `ResolvedMethodSpec`（formation_month=6、年度调仓、6 个月会计滞后、
  vw、10 分位、long=最低/short=最高资产增长分位；`build_config` 解析出的
  config dict 逐字段核对与 v1 一致），复用同一个 `compute_signal` 插件
  （spec 无关代码）。新增 4 个 `*_resolved_method_spec.py` 姊妹测试文件：
  `test_mvp_e2e_resolved_method_spec.py`（通过 `Pipeline.run_from_method_spec`
  跑出与 `expected_metrics()` 完全一致的黄金数值，`rel=1e-9`）、
  `test_execute_data_path_override_resolved_method_spec.py`（`BacktestRunner.
  build_script`/`execute` 的数据路径覆盖机制）、
  `test_bridge_track_e2e_resolved_method_spec.py`（C&Z bridge track 真实
  subprocess 执行）、`test_step_diagnostics_resolved_method_spec.py`
  （`diagnostics.step3_diagnostics`/`step4_diagnostics`，均是 spec-agnostic
  下游对象，只需换 fixture）。全量套件 626 passed / 26 skipped，无回归。
  **未迁移**：`test_accruals_e2e.py`（不同因子/公式，需要一套新的多字段
  accruals fixture，本轮未做）、`test_real_wrds_samples_e2e.py`（依赖本机
  不存在的真实 WRDS 私有数据，当前本就是 skipped，无法在本地验证转换是否
  正确，未做）。`test_step_diagnostics.py` 的 step1/step2 诊断测试仍保留
  v1——`step1_diagnostics`/`ReviewGate` 用的是 v1 专属的 `ambiguous_fields`/
  评审概念，没有 v2 等价物。

- `src/pipeline.py`/`src/infra/data_layer/sources.py` 双分派收尾：
  `Pipeline.run_from_method_spec`/`_build_validation_slice` 的 `spec` 类型
  加宽为 `MethodSpec | ResolvedMethodSpec`（本就只调用已双分派的
  `MetaCoder.generate_plugin`/`RepairLoop`/`BacktestRunner.*`，唯一的真实
  v1 专属读取是 `_build_validation_slice` 里的
  `spec.data.normalized_mapping`，现按 isinstance 分派到
  `resolution.concept_mapping`）。`assemble_signal_master_table` 新增
  ResolvedMethodSpec 分支（复用 `script_generator.
  signal_input_sources_from_resolved` + `registry.build_config` 取
  `accounting_lag_months`，而不是 v1 的 `signal_input_sources`/
  `spec.accounting_lag_months`）。新增
  `tests/test_signal_master_multisource.py::
  test_master_table_dispatches_on_resolved_method_spec`（复用已有的
  synthetic `test_papers_v1` 数据）。`tests/_spec_test_helpers.py` 的
  `minimal_resolved_spec` 新增 `concept_source`/`concept_column` 参数。
  全量套件 619 passed / 26 skipped，无回归。
  **`Pipeline.run_full_pipeline`（含 `SemanticExtractor`/`ReviewGate` 的
  完整 v1 提取-评审循环）、`src/evaluation/diagnostics.py` 的
  `step1_diagnostics`（依赖 v1 专属的 `ambiguous_fields`/
  `reextraction_attempts`）、`src/evaluation/helpers.py`（提取准确率评估，
  整体对标 v1 `SemanticExtractor`）、`scripts/*.py`（extract/review/
  resolve/validate 系列 CLI，均是 v1 工作流专属工具，没有 v2 版本）判定为
  没有 v2 等价概念、有意保留 v1，直到 v1 整体删除或未来单独做"v2 版
  CLI/诊断"功能——不在本轮"迁移消费者"范围内。

- 测试 fixture 迁移第一批(11 个文件改用 `ResolvedMethodSpec`)：新增
  `tests/_spec_test_helpers.py`（`minimal_resolved_spec(factor_id, weighting,
  breakpoint_source)` 通用最小 fixture + `spec_factor_id(spec)` 双分派辅助函数，
  供只把 `MethodSpec(...)` 当成"随便一个合法 spec"的测试文件复用）。已转换：
  `test_batch_invalidation.py`、`test_dual_track_controller.py`、
  `test_experiment_matrix.py`、`test_experiment_plan_matrix_merge.py`、
  `test_run_from_matrix.py`、`test_run_identity.py`、
  `test_sandbox_validation.py`、`test_repair_loop.py`、
  `test_script_generator_bridge_mode.py`、
  `test_script_generator_lag_override.py`、
  `test_config_override_validation.py`。这些测试所覆盖的模块
  （DualTrackController/RepairLoop/registry.build_config/BacktestRunner/
  AdversarialSandbox/script_generator）本就已双分派，转换只是把 fixture 换掉、
  FakeRunner 里的 `spec.factor_id` 换成 `spec_factor_id(spec)`，逻辑不变。
  全量套件仍是 618 passed / 26 skipped，无回归。
  **未转换**（有意保留 v1，原因各不相同）：约 18 个文件直接测试 v1 专属组件
  （`SemanticExtractor`/`ReviewGate`/`apply_decisions`/v1 `field_contract`/
  签名校验/持有期推导/reextraction loop 等），没有 v2 对应概念，只能在
  v1 整体删除时一并处理；另外一小撮（`test_accruals_e2e.py`、
  `test_execute_data_path_override.py`、`test_step_diagnostics.py`、
  `test_bridge_track_e2e.py`、`test_mvp_e2e.py`、
  `test_real_wrds_samples_e2e.py`）用的是**已提交的真实黄金数值 fixture**
  （`tests/fixtures/method_specs/*.resolved.methodspec.json`）跑
  `Pipeline`/真实经济数据端到端对账，换成等价的 v2 fixture 需要重新构造并
  核实相同的黄金数值——风险较高，本轮未做，留给后续单独处理。

- Phase D 收尾 + 新增论文优先(paper-first)工作流的独立 UI/API 面：
  - `backend/spec_parsing.py`（新增）：`parse_spec(raw_dict)`/`spec_factor_id(spec)`
    共享双分派辅助函数（按 payload 形状——`{paper, review, resolution}` 三个顶层键
    即视为 `ResolvedMethodSpec`，否则走扁平 v1 `MethodSpec`）。接入
    `backend/routers/backtest.py`/`codegen.py`/`experiments.py`
    三个路由（原先都是 `MethodSpec.model_validate(req.spec)` 直接构造，现在都走
    `parse_spec`），下游调用的 `MetaCoder.generate_plugin`/`BacktestRunner.
    build_script`/`AdversarialSandbox.validate`/`DualTrackController.run_experiment`
    本就已双分派，无需改动。新增 `tests/test_backend_spec_parsing.py`（2 个测试）。
  - `backend/routers/methodspecs.py` 与 `app.py` 的既有 Extractor/Review & Resolve
    页面判定为纯 v1 专属工作流（`ReviewStatus.APPROVED`/`codegen_ready` 字段、
    `ReviewGate`/`apply_decisions`，v2 没有对应概念），不做双分派改造，
    保持原样不动。
  - 新增独立的论文优先工作流（不与 v1 工作流共享文件/端点，双方永不冲突）：
    - `src/steps/step1_extractor/paper_extractor.py` 新增 `PaperExtractor` 类
      （沿用 `SemanticExtractor` 的 LLM 调用/重试/PDF 附件逻辑，但产出
      `PaperMethodSpec`）。
    - 新增后端路由 `backend/routers/paper_methodspecs.py`：
      `POST /api/paper-methodspecs/extract`（LLM job）、`/extract-pdf`、
      `POST /api/paper-methodspecs/review`（同步，调用
      `review_paper_method_spec`）、`POST /api/paper-methodspecs/resolve`
      （同步，调用 `build_implementation_resolution` 并组装
      `ResolvedMethodSpec`，返回 `is_ready`）、`GET /{stage}`、
      `GET /{stage}/{factor_id}`（stage ∈ drafts/reviews/resolutions/resolved）。
      产物落在 `runs/method_specs/paper_{drafts,reviews,resolutions,resolved}/`
      （`backend/state.py` 新增对应目录常量 + `build_paper_extractor`），
      与 v1 的 `unreviewed/reviewed/resolutions/resolved` 完全分开。已在
      `backend/main.py` 注册。新增 `tests/test_backend_paper_methodspecs_api.py`
      （2 个测试，review+resolve 全流程走 TestClient，无 LLM 调用）。
    - `app.py` 新增第 8 个侧边栏页面 "Paper-First Workflow"（Extract/Review/
      Resolve 三个 tab，直接调用上述模块而非走 HTTP，与其余页面的既有架构
      一致）。同时把 MetaCoder 与 Backtest & Experiments 两个既有页面的
      MethodSpec 选择器扩展为可加载 `paper_resolved/` 下的 `ResolvedMethodSpec`
      文件（新增 `_load_any_spec`/`_spec_factor_id`/`_spec_codegen_ready`/
      `_spec_stable_hash` 模块级辅助函数，按 isinstance 分派；v1 专属字段
      `review_status`/`codegen_ready`/`model_copy` 强制审批的写法只在
      v1 分支保留）。
  - 全量套件 618 passed / 26 skipped，无回归；Streamlit 应用启动烟雾测试通过
    （无导入期报错）。

- 新增 `docs/methodspec-v2-plan.md`：一份处于讨论阶段的计划，用于分离
	论文事实、评审决策、实现映射与引擎配置；同时定义了拟议的横截面因子覆盖范围、
	严格 schema 契约、类型化报告指标、不支持方法策略、迁移阶段、测试要求，
	以及实施前必须完成定案的决策事项。
- 引擎新增双排序执行能力：`BacktestExecutor` 新增 `compute_breakpoints_multi`/
  `assign_portfolios_multi`/`compute_portfolio_returns_multi`/
  `combine_portfolio_returns_multi`（`src/infra/backtest_engine/__init__.py`），
  由 `form_portfolios`/`compute_portfolio_returns`/`combine_portfolio_returns`
  在 `config["sort_dims"]` 恰好 2 维时分发，单维路径代码与行为完全不变。这是对
  2026-07-24"精简引擎到单一 vanilla 路径"决定的部分反转（仅恢复双排序，
  Fama-MacBeth/overlapping/discrete/microcap 均不恢复），详见
  `docs/decision-log.md` 2026-08-07 条目。新增 `tests/test_double_sort_engine.py`
  （7 个测试，手算验证 2x2 独立双排序的断点/分组/组合收益）。同时把
  `MAX_SUPPORTED_SORT_DIMENSIONS` 从计划里的 3 改为 2（与引擎真实能力一致，
  避免 schema 层放行引擎实际跑不动的构造）。全量套件 594 passed / 26 skipped，
  无回归。**尚未接入** `registry.build_config`/`MetaCoder`/
  `step6_dual_track_controller`——推导 `config["sort_dims"]` 仍是待办工作
  （见 `docs/methodspec-v2-plan.md` 迁移 Phase D）。

- Phase D 第一块：`registry.build_config` 改为双分派（`spec: MethodSpec |
  ResolvedMethodSpec`），新增 `_build_config_from_resolved` 从 `ResolvedMethodSpec`
  （paper+review+resolution）推导出与 v1 完全相同的 config dict 形状，
  `BacktestExecutor` 不用改。覆盖单排序与双排序两种情况：`sort_dims` 里 `target`
  维度固定映射到引擎的字面 `"signal"` 列（论文自己的信号，由
  `compute_signal()` 产出），非 target 维度（如 size）才走物理列解析
  （`ImplementationResolution.concept_mapping`）——这是接线时发现的一个关键点，
  最初实现搞混了会导致断点算在不存在的列上。`PortfolioLeg.selector` 的
  0-based 分组号转换成引擎的 1-based 桶号。`TimingSpec` 补了一个此前遗漏的
  结构化字段 `formation_month`（v1 有 `formation_month: int`，v2 之前只有自由文本
  `formation_rule`，会导致年度信号对齐逻辑拿不到月份）。新增
  `tests/test_registry_resolved_method_spec.py`（6 个测试，含单排序/双排序两条
  真实端到端 `BacktestExecutor.run_with_config()` 跑通）。全量套件 600 passed /
  26 skipped，无回归。仍未接入 `MetaCoder`/`script_generator`/`step6`/backend/
  `app.py`——这些还在直接构造 v1 `MethodSpec` 并调用 `build_config(v1_spec, ...)`，
  走的是保留不变的 v1 分支。

- `MetaCoder.generate_plugin`/`_build_prompt` 同样改为双分派：
  `_build_prompt_from_resolved` 从 `ResolvedMethodSpec` 读 `signal.formula.steps`
  （取代 v1 单一 `formula.expression`）、`timing.formation_month`/
  `rebalance_frequency`、按 `stage=="signal"` 过滤的 `missing_policies` 条目，
  物理列通过 `resolution.concept_mapping` 解析（取代 v1 的
  `data.normalized_mapping`）。就绪判断用 `resolved.is_ready`，取代 v1 的
  `review_status=="approved" and codegen_ready`。新增
  `tests/test_meta_coder_resolved_method_spec.py`（3 个测试，用假 LLM 客户端跑
  `generate_plugin`）。全量套件 603 passed / 26 skipped，无回归。v1 分支/
  `method_spec.py` 仍保留，等 script_generator/step4-6/backend/app.py 全部
  迁移完才一起删除（用户已确认最终要删掉 v1，不是长期保留）。

- `script_generator.py` 同样双分派：`pick_signal_input_mode`/新增
  `signal_input_sources_from_resolved` 从 `resolution.concept_mapping` 按
  `FieldRole.SIGNAL_INPUT` 分组物理列（取代 v1 的 `data_layer.
  signal_input_sources`/`resolved_sources()`）；`generate_backtest_script`
  的 `factor_id`/`factor_name`/`paper_ref` 模板变量按 `isinstance` 分支取值。
  新增 `tests/test_script_generator_resolved_method_spec.py`（5 个测试）。
  全量套件 608 passed / 26 skipped，无回归。

- `step4_validator`：`AdversarialSandbox.validate` 的 `spec` 参数本来就没在
  方法体内被读取过，只放宽类型注解为 `MethodSpec | ResolvedMethodSpec`。
  `step5_backtest_runner`：新增 `_spec_factor_id`/`_spec_paper_ref`/
  `_spec_stable_hash`/`_spec_paper_reported` 四个双分派辅助函数，`build_script`/
  `write_comparison_summary`/`make_run_record`/`make_failed_run_record` 都
  改用它们取代直接访问 `spec.factor_id`/`spec.paper_ref`/`spec.stable_hash()`/
  `spec.reported_results`；`ResolvedMethodSpec` 的 `ReportedResults`（D5 的
  primary+secondary 类型化指标）被拍平成和 v1 相同的
  `{return_type, spreads, t_stats, main_spread, main_t_stat}` 形状，供
  `step7_replication_diff.bundle.build_evidence_bundle` 直接消费不用改。新增
  `tests/test_step5_backtest_runner_resolved_method_spec.py`（3 个测试）。
  全量套件 611 passed / 26 skipped，无回归。

- `step6_dual_track_controller`：新增 `_spec_factor_id` 辅助函数，`run_experiment`/
  `_plan_to_matrix`/`run_from_matrix`/`_run_bridge_track`/`_get_ablation_override`
  等方法的 `spec` 参数类型全部放宽为 `MethodSpec | ResolvedMethodSpec`（这些方法
  本身只把 `spec` 转手传给已双分派的 `build_config`/`runner.build_script`，唯一
  需要改的是 3 处直接读 `spec.factor_id` 的地方）。`experiment_spec.py` 的
  `build_experiment_spec`/`load_experiment_matrix` 同样放宽。`RepairLoop`
  （`src/infra/repair.py`）的 `build_validate_repair`/`execute_with_repair` 也
  放宽类型（同理，只是转手传递）。新增
  `tests/test_step6_dual_track_resolved_method_spec.py`（3 个测试）。全量套件
  614 passed / 26 skipped，无回归。

### Decisions Approved

- **D4（不支持执行策略）** 已定案：
  - 第一阶段支持双排序（2维）和基础三维排序
  - 更复杂的方法（Fama-MacBeth、自定义权重）在 `original_method` 上硬阻断
  - 允许单排序近似轨道，并行报告透明化gap
  - 基于 Fama-French 数据库标准做法和现有数据集统计（16.7% 需要多维排序）
- **D6（论文目标粒度）** 已定案：每个可独立执行的目标一个 MethodSpec，共享 `paper_ref`；信号内部组合仍是单 MethodSpec
- **D1（ResolvedMethodSpec 形态）** 已定案：实时重建（paper+review → 内存合并），同时写审计快照到 `runs/resolved/` 供调试；快照是输出产物，不作为输入读取
- **D2（evidence-status 归属）** 已定案：两层（LLM 打标 + 人工可覆盖）；v2 要求 Step1 每个字段必须有 `evidence_status` + 原文引用；审批矩阵维持现有逻辑，人工仅在"不确定 + 高影响"时介入
- **D5（报告指标粒度）** 已定案：`primary`（必填结构化）+ `secondary`（≤3个可选）；`metric_type` 枚举绑定引擎输出名；引擎没有的指标用 `other` 标记；`source` 支持 `clear`（原文 quote）和 `table_only`（table/row/column 定位）两种 evidence_status，后者是常态，走人工核实路径
- **D3（公式中间表示）** 已定案：选结构化文本步骤（不引入 AST）；`FormulaSpec` 扩展为有序步骤列表；用正则提取变量名做轻量符号验证；Step4 沙箱执行是主要验证手段
- **D7（稳定标识符）** 已定案：`factor_id = sha256(paper_ref + "::" + target_name)[:16]`，确定性生成无需人工维护；ablation/多 track 通过 `run_config` 区分，不影响 factor_id
- **D8（迁移切换策略）** 已定案：一次切换，旧 artifacts 直接作废重生；不维护 v1/v2 并行路径；旧 schema_version 报错提示重新生成

### Changed

- `docs/methodspec-v2-plan.md` §6 从概念草案改写为定稿级 schema：给出 `PaperMethodSpec` /
  `MethodReview` / `ImplementationResolution` / `ResolvedMethodSpec` 四个工件的完整
  Pydantic 形态，并新增 §6.10 字段审计（v1 → v2 的移出 8 项、删除 13 项、新增 16 项）。
- 新增 `src/infra/models/method_spec_v2.py`：Phase A 契约冻结实现，落地计划 §6 的
  `PaperMethodSpec` / `MethodReview` / `ImplementationResolution` / `ResolvedMethodSpec`
  四个 Pydantic 模型，含 `content_hash()`（D1 陈旧检测）、`make_factor_id()`（D7 确定性
  ID）、`DISPOSITION_MATRIX`（D2 五档证据矩阵）与 `ResolvedMethodSpec.is_ready`（取代
  v1 `codegen_ready` 布尔标志的推导式就绪判断）。尚未接入 `src/steps/*` 任何消费方
  （按计划 §9 Phase A 要求，先冻结契约再迁移消费方）。
- 新增 `tests/test_method_spec_v2_contract.py`（29 个测试）：`extra="forbid"` 拒绝
  未知字段、无损往返、`factor_id`/`content_hash` 稳定性、四个代表性 schema 场景
  （简单会计比率单排序 / 滚动残差估计信号 / 序贯双重排序 / 显式记录的不支持自定义
  加权替代）、`DISPOSITION_MATRIX` 形状、以及 `ResolvedMethodSpec.is_ready` 的五种
  失效路径。全量套件 567 passed / 26 skipped，无回归。
- Phase B：新增 `src/infra/models/schema_render_v2.py`（从 `PaperMethodSpec` 模型
  字段直接生成 JSON schema 骨架，杜绝 v1 那种"提示词比模型更丰富"的漂移问题）、
  `prompts/extractor/methodspec_extractor_v2.md`（v2 抽取提示词，schema 骨架块由
  `schema_render_v2` 在加载时拼接生成，不手工维护）、`src/steps/step1_extractor/v2.py`
  （`build_paper_method_spec` 直接用 `PaperMethodSpec.model_validate()` 校验 LLM 输出，
  无需 `normalize_curated_schema` 式的展平层；`factor_id`/`schema_version` 由流水线
  计算，不取信 LLM 填写）。新增 `tests/test_step1_extractor_v2.py`（13 个测试）。
  全量套件 575 passed / 26 skipped，无回归。**尚未接入** `src.pipeline` / v1
  `SemanticExtractor`——Step2/Step3 仍消费 v1 `MethodSpec`，真正切换要等 Phase C/D
  完成后一次性进行（避免中途破坏可测试的主分支）。
- Phase C：新增 `src/steps/step2_reviewer/v2.py`（`review_paper_method_spec`：
  D2 证据状态矩阵 + D4 引擎能力矩阵两条独立判定路径产出 `MethodReview`；能力菜单
  `ENGINE_WEIGHTING_MENU`/`ENGINE_RETURN_COMBINATION_MENU` 与 schema 词汇分离，
  论文即使清晰陈述了不支持的方法，也照样 `kind="unsupported"` + `BLOCKED`）、
  `src/steps/step2_reviewer/resolution_v2.py`（`build_implementation_resolution`
  复用既有 `DataDictionary.normalize_fields()` 目录匹配器，未解析的 concept 直接
  从 `concept_mapping` 中省略，绝不静默猜测）。同时修正 Phase A 的一个疏漏：
  `ResolvedMethodSpec._hashes_current` 此前只校验 `paper_spec_hash`，未校验
  `resolution.review_hash` 是否对应 review 的当前内容——新增 `MethodReview.
  content_hash()` 并补上这层校验，使 D1 的陈旧检测在 paper→review→resolution
  三层之间完整闭合。新增 `tests/test_step2_reviewer_v2.py`（12 个测试）。全量
  套件 587 passed / 26 skipped，无回归。仍未接入 `src.pipeline`。

### Renamed

- 去掉上面三条 Phase A/B/C 文件名里的 `_v2` 后缀（`schema_version` 里的
  `"methodspec.v2"` 等字面量保留，那是持久化数据的版本标识，不算代码命名）：
  `method_spec_v2.py` → `paper_method_spec.py`、`schema_render_v2.py` →
  `schema_render.py`、`step1_extractor/v2.py` → `step1_extractor/
  paper_extractor.py`、`step2_reviewer/v2.py` → `step2_reviewer/paper_review.py`、
  `step2_reviewer/resolution_v2.py` → `step2_reviewer/
  implementation_resolution.py`、`prompts/extractor/methodspec_extractor_v2.md`
  → `prompts/extractor/paper_method_spec_extractor.md`，以及对应的三个测试文件。
  重命名后全量套件重新验证 587 passed / 26 skipped。
