# Changelog

## [Unreleased]

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
