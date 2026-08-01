# Changelog

## [Unreleased]

### Docs — DataLayer refactor Round 1 P5 (doc sync; Round 1 complete)
- Synced the current-state docs to the post-refactor data layer (no code change):
  `AGENTS.md` Module Map row for `src/infra/data_layer/` (now: `sources.py`
  registry = single source of truth + derived `catalog` + `DataLayer` facade)
  and the signal-source hard-constraint (register a `SourceSpec` in `sources.py`);
  `docs/architecture.md` §4.5 rewritten to the DataSource-registry/declarative
  model + directory-tree comments; `docs/roadmap.md` MVP-chain references
  (`assemble_signal_master_table` instead of the deleted
  `DataLayer.get_signal_master_table`/`TimeAvailComputer`/`CCMLinker`);
  `plan.md` status marked Round 1 (P1–P5) complete. Historical `CHANGELOG`/
  `docs/decision-log.md` entries left as-is (records). Round 1 of the DataLayer
  refactor is done; Round 2 (agent source-onboarding) remains doc-only.

### Removed — legacy snapshot-based signal-master path merged into one loader (DataLayer refactor Round 1 P4)
- Deleted the "B-group": `CCMLinker`, `TimeAvailComputer`,
  `DataLayer.get_signal_master_table`, `DataLayer.get_snapshot_data` (and the
  `self.ccm_linker`/`self.time_avail` instances). Its job — resolve a Compustat
  gvkey to `permno` point-in-time and stamp `time_avail_m` — is now done ONLY by
  the declarative D-group loader (`assemble_signal_master_table` /
  `link_to_permno` in `sources.py`). There is now one signal-master path.
- **Golden numbers unchanged, verified two ways:** (1) a read-only equivalence
  check confirmed the B-group and D-group produced byte-identical
  `[permno, time_avail_m, *cols]` on the mvp/asset_growth + accruals fixtures
  before deletion (see docs/decision-log.md P4 entry); (2) the mvp/accruals
  golden-number e2e — which run the actual generated standalone script via
  subprocess — pass unchanged through the D-group.
- **Behavioral decision (user-approved "keep"):** `CCMLinker` dropped a
  Compustat row whose linked `permno` is absent from the CRSP returns panel;
  the D-group `link_to_permno` KEEPS it (CRSP-centric: permno is the identity;
  the engine's inner-join with returns drops it downstream anyway). No effect on
  the fixtures (every permno is in CRSP).
- Consumers migrated: the generated script's "compustat" mode now shares the
  "multi_source" declarative loader (`assemble_signal_master_table_from_sources`)
  — the two modes differ only in how the RETURNS panel is loaded;
  `pipeline._build_validation_slice`, the mvp/accruals e2e fixtures + shape
  tests, `backend/state.py`, `app.py`, and `scripts/build_synthetic_data.py` all
  switch to the declarative loader.
- **Snapshot layout change:** a snapshot dir's signal tables are now
  `comp_funda.parquet` + `ccm_lnkhist.parquet` (CCM keyed on the real WRDS
  column `lpermno`) instead of `compustat_funda.parquet` + `ccm_link.parquet`
  (keyed on `permno`). `generate_backtest_script` dropped its
  `compustat_data_path`/`ccm_link_path` params (the loader reads the source
  tables from `signal_data_dir`). Updated the `TimeAvailComputer` reference in
  `AGENTS.md`. Full suite: 197 passed, 26 skipped; ruff-clean (touched files).

### Changed — Compustat/IBES signal sources + link tables migrated to the registry; catalog derived (DataLayer refactor Round 1 P3)
- Migrated the whole declarative signal-input layer (the "D-group") into
  `sources.py`, reading directly from the DataSource registry (the single
  source of truth) instead of the old catalog-derived dicts:
  - Added `LinkTableSpec` + a link-table registry (`register_link_table` /
    `get_link_table`); registered `ccm` + `ibes_crsp_link` (with their on-disk
    parquet stem / raw-CSV fallback + CCM validity/primary filters).
  - Registered the four signal sources as `SourceSpec`s: `crsp_msf` (a
    `CrspSignalSource` — CRSP's §2④ signal role), `comp_funda`, `comp_fundq`,
    `ibes_statsumu` (generic `SignalSource`s). Slimmed `CrspLinkSpec` to the
    source-side fields (native_key/link_table/link_date); the shared link
    schema lives on `LinkTableSpec`.
  - Implemented `SignalSource.load` + moved `link_to_permno` /
    `_load_link_tables` / `_read_raw_*` / `_load_source_frame` /
    `signal_input_sources` / `assemble_signal_master_table*` into `sources.py`.
    Raw-input dedup filters are now declarative `SourceSpec.raw_filters`
    (`{"indfmt": "INDL"}`, `{"measure": "EPS", "fiscalp": "ANN", "fpi": "1"}`).
- `catalog.py` now DERIVES its whole query surface from the registry —
  `DATA_CATALOG` / `LINK_TABLES` / `RETURNS_UNIVERSES` are built via
  `sources.data_catalog_view()` / `link_tables_view()` / `returns_universes_view()`,
  and are **byte-identical** to the historical literals (so
  `signal_sources()` / `concept_map()` / `source_of_column()` /
  `resolve_concept()` keep their signatures and values — MethodSpec/reviewer
  unchanged, per plan §6b). Removed the hand-written `DATA_CATALOG` /
  `LINK_TABLES` / `LINK_TABLE_FILES` / `RAW_CSV_*` literals from the catalog.
- Deleted the D-group from `data_layer/__init__.py`; the public loader names
  (`link_to_permno` / `assemble_signal_master_table` /
  `assemble_signal_master_table_from_sources` / `signal_input_sources` /
  `_load_source_frame` / `_load_link_tables`) are re-exported from `sources.py`
  so every importer (incl. the generated multi_source script) is unchanged.
- Reviewer needs no change (still reads the re-exported `SIGNAL_SOURCES`);
  `test_data_catalog` passes unchanged (byte-identical derivation);
  `test_signal_master_multisource`'s date-less-source regression now registers a
  throwaway `SignalSource` instead of monkeypatching `SIGNAL_SOURCES`. Full
  suite: 197 passed, 26 skipped; mvp/accruals golden numbers unchanged; ruff clean.

### Changed — CRSP returns universe migrated to the DataSource registry (DataLayer refactor Round 1 P2)
- Migrated the CRSP "new CIZ" returns backbone into `sources.py` as the first
  concrete `DataSource`: the `CrspReturnsUniverse` class (bespoke, since it
  needs multi-file assembly + exchcd/shrcd derivation + delisting merge) plus
  the moved `build_crsp_monthly_panel_ciz` / `load_daily_msf_ciz` / `_ciz_shrcd`
  and the CIZ column/exchcd constants. Registered under alias `us_equity_crsp`
  and engine-config layout tag `crsp_ciz`.
- Added a returns-universe sub-registry (`register_returns_universe`,
  `get_returns_universe`, `get_returns_universe_by_layout`) — both fail loud on
  an unknown alias/layout (never a silent default panel).
- `DataLayer` gained the returns facade (`load_returns(universe_name)` /
  `load_returns_by_layout(layout)`), resolving through the registry.
  `BacktestExecutor.load_data` now obtains the CRSP panel via
  `DataLayer.load_returns_by_layout("crsp_ciz", returns_dir)` instead of calling
  the free assembler directly.
- Deleted the C-group block from `data_layer/__init__.py`; the two public
  assemblers are re-exported from `sources.py` so existing importers (the
  generated multi_source script, `_load_source_frame`, tests) are unchanged.
- Moved the CIZ schema constants out of `catalog.py` into `sources.py` (they're
  CRSP-source physical detail, and `sources.py` can't import `catalog` under the
  `sources <- catalog <- __init__` layering).
- Added P2 tests to `tests/test_data_sources.py` (CRSP universe registration,
  unknown-universe fail-loud, DataLayer facade delegates to the registry). Full
  suite: 196 passed, 26 skipped; mvp/accruals golden numbers unchanged; ruff
  clean.

### Added — DataSource registry scaffold (`sources.py`, DataLayer refactor Round 1 P1)
- New `src/infra/data_layer/sources.py`: the CRSP-centric, class-based successor
  to `catalog.py`'s flat dicts (see repo `plan.md`, Round 1). Declares the
  `CrspLinkSpec`/`SourceSpec` config dataclasses, the
  `DataSource`/`SignalSource`/`ReturnsUniverse` hierarchy, and the registry
  (`register`/`get_source`/`has_source`/`iter_sources`/`clear_registry`).
- Pure, side-effect-free addition: nothing is registered and nothing imports
  this module yet. Actual read/link/time_avail logic (and the CRSP CIZ returns
  universe) is MOVED in from `__init__.py` in P2 (CRSP) / P3 (Compustat/IBES);
  `SignalSource.load`/`ReturnsUniverse.load` raise `NotImplementedError` naming
  the wiring phase for now.
- `SourceSpec` is deliberately MINIMAL (plan §0): only fields a Round-1 consumer
  reads; `snapshot_table`/`frequency` are intentionally omitted until a consumer
  exists. Layering is one-directional (`sources.py` ← `catalog.py` ← `__init__`);
  `sources.py` must not import `__init__.py`.
- Added `tests/test_data_sources.py` (7 tests) locking the registry contract
  (register/get_source roundtrip, duplicate + unknown-source fail-loud,
  `CrspLinkSpec.is_permno_keyed`, `SourceSpec` fields, role validation, unwired
  `load()` raises). Full suite: 193 passed, 26 skipped.

### Removed — `BacktestExecutor.load_msf`/`load_daily_msf` and the "panel" returns_layout
- Per explicit user confirmation (after being shown the exact blast radius),
  deleted `BacktestExecutor.load_msf`/`load_daily_msf` (the two static methods
  that read an already-pre-flattened parquet in final engine schema) and the
  `"panel"` returns_layout + its `<data_path>/local/msf.parquet` legacy
  file-location shim from `load_data()`. `load_data()` now only supports an
  explicit `data=` DataFrame or `returns_layout="crsp_ciz"` — no other file
  dispatch.
- Consolidated `catalog.RETURNS_UNIVERSES`: `"us_equity_crsp"` now points
  directly at `returns_layout="crsp_ciz"` (the separate `"us_equity_crsp_ciz"`
  entry was redundant and removed).
- Confirmed empirically (ran the full suite after deleting, rather than
  auditing every call site by hand) that `tests/test_mvp_e2e.py`,
  `tests/test_accruals_e2e.py`, `tests/test_backend_api.py`, `app.py`, and
  `backend/state.py` are ALL UNAFFECTED — they execute the actual backtest via
  `BacktestRunner.execute()` running a generated standalone script
  (`script_generator.py`'s OWN independent `load_msf()` reimplementation,
  baked into the generated script template), never through
  `BacktestExecutor.load_data()`'s file dispatch. Only 6 tests actually broke:
  all 3 in `tests/test_daily_frequency.py::TestLoadDailyMsf` (deleted — they
  directly exercised the removed `load_daily_msf`; daily-frequency data now
  goes through `data_layer.load_daily_msf_ciz` instead) and 3 in
  `tests/test_no_default_source.py` (one deleted — tested the removed legacy
  file-location shim; two updated to assert `returns_layout == "crsp_ciz"`
  instead of `"panel"`). Full suite now 186 passed (down from 190), 26 skipped.
  See docs/decision-log.md (2026-07-31 fourth entry).

### Changed — moved remaining table/column/join metadata into catalog.py (pure refactor, no behavior change)
- Per user request to keep ALL per-table declarative metadata (columns,
  join/link info, filters needed) in `catalog.py` and have
  `data_layer/__init__.py` just reference it: moved `_CIZ_EXCHCD_MAP`
  (PrimaryExch->exchcd mapping), `_CIZ_MONTHLY_USECOLS`/`_CIZ_DAILY_USECOLS`
  (raw column lists read from `CRSP_STOCK_MONTH.csv`/`CRSP_STOCK_DAILY.csv`),
  and `_RAW_CSV_SOURCE_FILTER_COLS` (extra columns each raw-CSV source's dedup
  filter needs) into `catalog.py` as `CIZ_EXCHCD_MAP`, `CIZ_MONTHLY_USECOLS`,
  `CIZ_DAILY_USECOLS`, `RAW_CSV_SOURCE_FILTER_COLS`. `data_layer/__init__.py`
  now just aliases them (same pattern already used for `LINK_TABLE_FILES`/
  `RAW_CSV_SOURCE_FILES`). The actual filter LOGIC (`_filter_raw_indfmt_indl`/
  `_filter_raw_ibes_statsumu`) stays in `data_layer/__init__.py` since it's
  behavior, not declarative data. No functional change — verified via a
  build_crsp_monthly_panel_ciz smoke test + full suite (still 190 passed, 26
  skipped).

### Removed — legacy 3-table CRSP assembler (SOURCE_SCHEMA/assemble_panel/build_crsp_monthly_panel); standardized on real WRDS CIZ format
- Per explicit user direction ("旧格式就不要了吧，全都按照sample文件为准"), deleted the
  legacy multi-table CRSP assembler that read `crsp_msf`/`crsp_msenames`/
  `crsp_msedelist` as three separate WRDS-shaped tables and point-in-time-joined
  them (`SOURCE_SCHEMA`, `_DERIVE_OPS`, `_load_base`, `_apply_pit_attrs`,
  `_apply_fold_last`, `assemble_panel`, `build_crsp_monthly_panel` — all in
  `src/infra/data_layer/__init__.py`). `build_crsp_monthly_panel_ciz` (the real
  WRDS "new CIZ" format loader added 2026-07-30) is now the ONLY raw-tables
  CRSP assembler.
- `BacktestExecutor.load_data()`'s `returns_layout="crsp_raw"` option was
  removed (only `"panel"` — a single pre-flattened parquet, unrelated
  infrastructure still used by the MVP/accruals e2e tests and the Streamlit
  demo — and `"crsp_ciz"` remain). `catalog.RETURNS_UNIVERSES["us_equity_crsp_raw"]`
  was removed accordingly.
- `_load_source_frame`'s special-cased `crsp_msf` signal-source branch and
  `script_generator.py`'s generated multi-source backtest script template now
  both call `build_crsp_monthly_panel_ciz` instead (reading from
  `<data_dir>/local/`, where the real WRDS CIZ export lives).
- Deleted `tests/test_crsp_raw_panel.py` entirely (all 5 tests directly
  exercised the removed assembler/layout), and two tests in
  `tests/test_signal_master_multisource.py` that depended on it transitively:
  `test_apply_pit_attrs_fallback_for_coverage_gap` (called `assemble_panel()`
  directly) and `test_generated_multi_source_script_runs` (ran a generated
  multi-source script against `data/synthetic_data/test_papers_v1`'s legacy
  3-table CRSP synthetic fixtures, which the new template no longer reads).
  Full suite now 190 passed (down from 197 — 7 tests removed), 26 skipped.
- Confirmed SAFE / unaffected (verified via targeted test runs, not just
  code reading): `scripts/build_synthetic_data.py`, `tests/synthetic_data/
  asset_growth_synthetic_data.py`/`accruals_synthetic_data.py`,
  `tests/test_mvp_e2e.py`, `tests/test_accruals_e2e.py`,
  `tests/test_backend_api.py`, `app.py`, `backend/state.py`,
  `Pipeline.run_from_method_spec()` — none of these ever used the legacy
  3-table assembler; they all pass pre-flattened data directly (the `"panel"`
  layout, or `data=`/DataLayer-snapshot passthrough), which is untouched.
  `scripts/build_test_papers_synthetic_data.py` (the sole generator of the
  now-orphaned `crsp_msf`/`crsp_msenames`/`crsp_msedelist`/`crsp_dsf`/
  `crsp_msedist` legacy fixtures under `data/synthetic_data/test_papers_v1/`)
  was left as-is — it still generates comp_funda/comp_fundq/ccm_lnkhist/
  ibes_statsumu/ibes_crsp_link fixtures that `test_signal_master_multisource.py`'s
  remaining tests still use; the CRSP-specific fixtures it also writes are now
  simply unused, harmless leftover files. See docs/decision-log.md (2026-07-31
  third entry) for the full rationale and blast-radius audit.

### Fixed — explicit date format for raw WRDS CSV parsing (perf + correctness discovery from real data)
- Validated the 2026-07-30 real-data loaders against the curated
  `data/local/samples/` (see prior entries) and found `CRSP_COMPUSTAT_LINK.csv`'s
  `LINKENDDT` uses the literal string `"E"` for still-open links (not blank) —
  this forced pandas' slow per-row `dateutil` fallback (with a `UserWarning`)
  everywhere a date column was parsed without an explicit format, since all
  real WRDS date columns here are consistently `YYYY-MM-DD`. Added
  `format="%Y-%m-%d"` to every date parse scoped to a known real WRDS file
  (`build_crsp_monthly_panel_ciz`, `load_daily_msf_ciz`,
  `_read_raw_link_table_csv`, `_read_raw_source_csv` — the last one now
  pre-parses the source's own `date` column so the later generic
  `link_to_permno` call becomes a cheap no-op — plus `load_crsp_index_factors`/
  `load_liquidity_factors`/`load_institutional_ownership_13f`/
  `load_ibes_recommendation_detail`/`load_ibes_unadjusted_actual`).
  Deliberately did NOT touch the generic, source-agnostic `link_to_permno`/
  `_load_source_frame` date parsing (must stay format-flexible for any future
  non-WRDS source). `"E"` still parses to `NaT` -> `Timestamp.max` exactly as
  before (behavior-preserving, `errors="coerce"` unchanged) — pure perf/warning
  fix, no numbers change. Measured ~18% faster on the full real
  `comp_fundq` load (68.1s -> 56.3s). Also documented a real-data quirk found
  along the way: a delisted stock's CIZ row for its own delisting month
  commonly has `PrimaryExch`/`SecurityType`/`SICCD` blanked out (so it maps to
  `exchcd=0`/`shrcd=0` that one month) — not a bug, just how the export
  reports it; documented in `build_crsp_monthly_panel_ciz`'s module comment.
  Full suite still 197 passed, 26 skipped. See docs/decision-log.md
  (2026-07-31 second entry).

### Removed — catalog.py sources with no real data behind them (optionm_vsurf, optionm_crsp_link, tr_13f, patents_nber)
- `src/infra/data_layer/catalog.py`'s `DATA_CATALOG`/`LINK_TABLES` no longer
  register `optionm_vsurf`/`optionm_crsp_link` (no OptionMetrics data file
  exists anywhere in this project) or `patents_nber` (no NBER patents data
  exists either). `tr_13f` was also removed: it assumed an already
  permno-keyed source, but the real 13F export we now have
  (`data/local/13F.csv`) is cusip-keyed — keeping that entry registered
  would misrepresent how the real file actually joins. Real 13F data is
  loaded by `data_layer.load_institutional_ownership_13f()` instead,
  deliberately outside the catalog (see the 2026-07-30 entry above and
  docs/decision-log.md 2026-07-31 entry). Updated `tests/test_data_catalog.py`
  (golden-literal dicts + one assertion) and
  `tests/test_signal_master_multisource.py` (dropped the removed
  `optionm_vsurf` parametrize case; switched the "permno-keyed source"
  no-op test from `tr_13f` to `crsp_msf`; the `patents_nber`
  date-column-fail-loud regression test now monkeypatches a temporary fake
  source into `SIGNAL_SOURCES` instead, so that regression coverage isn't
  lost). Full suite 197 passed (down from 198 — one fewer parametrized
  case), 26 skipped. `scripts/build_test_papers_synthetic_data.py`'s
  `build_optionm_vsurf`/`build_optionm_crsp_link`/`build_tr_13f`/
  `build_patents_nber` synthetic-fixture builders were left in place
  (harmless now-unused fixtures, out of scope for this cleanup).

### Added — real WRDS raw CSV data support (CRSP "new CIZ", Compustat, CCM/IBES links, IBES summary, CRSP index, liquidity factors, 13F)
- `data/local/` now holds real bulk WRDS exports (gitignored, developer-local)
  instead of only synthetic/legacy-parquet data. `src/infra/data_layer/__init__.py`
  gained direct CSV readers so the pipeline can run against them without a
  separate parquet-conversion step:
  - **CRSP monthly/daily ("new CIZ" format)**: `build_crsp_monthly_panel_ciz()`
    and `load_daily_msf_ciz()` read `CRSP_STOCK_MONTH.csv`/`CRSP_STOCK_DAILY.csv`
    (+ `CRSP_DELISTING.csv` for `dlret`) directly — this format bundles what
    legacy CRSP splits into three point-in-time-joined tables
    (crsp_msf/crsp_msenames/crsp_msedelist) into one already-point-in-time row
    per (permno, month/day), so no windowed join is needed. New
    `returns_layout="crsp_ciz"` wired into `BacktestExecutor.load_data` and
    registered as `catalog.RETURNS_UNIVERSES["us_equity_crsp_ciz"]`. Documented
    approximations: `exchcd` only maps CIZ's unambiguous `PrimaryExch` codes
    (N/A/Q); `shrcd` has no CIZ equivalent at all and is approximated from
    SecurityType/SecuritySubType/ShareType/USIncFlg (see decision-log).
  - **Compustat annual/quarterly, CCM link, IBES-CRSP link, IBES summary**:
    `_load_source_frame`/`_load_link_tables` now fall back to reading the raw
    CSV directly (`data/local/COMPUSTAT_FUNDAMENTALS_ANNUAL.csv`,
    `..._QUATER.csv`, `CRSP_COMPUSTAT_LINK.csv`, `IBES_CRSP_Link.csv`,
    `IBES_UNADJUSTED_SUMMARY.csv`) when the pre-converted `<name>.parquet`
    isn't present, registered in `catalog.RAW_CSV_SOURCE_FILES`/
    `RAW_CSV_LINK_TABLE_FILES`. Compustat annual/quarterly are filtered to
    `indfmt=="INDL"` (the raw export also carries a financial-services "FS"
    format variant of the same gvkey+datadate); IBES summary is filtered to
    the standard FY1 annual EPS consensus (`measure=="EPS", fiscalp=="ANN",
    fpi==1`) so each (ticker, statpers) resolves to one row.
  - **Supplementary factors**: `load_crsp_index_factors()` (CRSP's own
    vw/ew market index + S&P 500, monthly or daily) and
    `load_liquidity_factors()` (Pastor-Stambaugh 2003 level/innovation/
    traded factors, `-99` missing-placeholder converted to NaN). Neither
    carries a risk-free rate — a supplement to `ff_factors.parquet`, not a
    replacement.
  - **Best-effort, not catalog-wired** (no signal plugin consumes these yet):
    `load_institutional_ownership_13f()` (13F.csv, linked to permno via a
    non-point-in-time CUSIP match — documented limitation) and
    `load_ibes_recommendation_detail()`/`load_ibes_unadjusted_actual()`
    (lower-case/date-parse pass-through only, no permno link yet).
    `COMPUSTAT_GLOBAL_STOCK_MONTH.csv` (a different, international returns
    universe) is intentionally NOT wired up — out of scope, needs its own
    returns-universe design.
  - New `tests/test_real_wrds_csv_loaders.py` (8 tests, all skip gracefully
    when the real files aren't present — CI never has them). Full suite still
    198 passed / 26 skipped. See `docs/decision-log.md` (2026-07-30 entry) for
    the exchcd/shrcd mapping rationale and other simplifications.

### Fixed — fail-loud on missing filter field; annual formation-month consistency; VW excludes (not fabricates) missing prior-month ME
- Three fifth-pass fixes on `apply_signal_holding_period` /
  `compute_portfolio_returns`: (1) both universe-filter sites
  (`apply_universe_filters` on the returns panel and the formation
  cross-section loop) silently skipped a filter whose field was absent from
  the panel — running a DIFFERENT universe than the MethodSpec stated while
  reporting success. Both now raise `ValueError` naming the field and the
  available columns (column availability can't be validated at spec-review
  time, so run time is the only place it's known). (2) Nothing verified that
  an annual-rebalanced signal formed in its declared `formation_month`. Added
  `_validate_annual_formation_month`, which raises when an annual + EXPLICIT-
  `formation_month` signal has any formation cohort in a different month.
  Quarterly/monthly are deliberately not validated (convention-dependent
  cohort-month sets), and a merely DEFAULTED `formation_month` doesn't trigger
  it (new `formation_month_explicit` flag from `registry.build_config`). (3)
  When prior-month market equity `me_{t-1}` was missing, `_attach_lagged_me`
  fell back to same-month ME — silently reintroducing the same-month look-ahead
  the fourth pass removed. VW now excludes NaN/non-positive `me_lag` rows
  (weight 0) and surfaces `vw_lagged_me_missing_frac` in `compute_metrics`
  (None under EW). No golden-number changes: the single-stock-per-decile
  fixtures gained a June-1998 formation-month row in
  `asset_growth_synthetic_data.build_crsp_msf` so `me_{t-1}` resolves for the
  first held month under the new exclude rule (real CRSP panels always have
  that row); the gitignored cached snapshot under `data/synthetic_data/mvp_v1/`
  was regenerated. Full suite 190 passed, up from 182. See
  `docs/decision-log.md` (2026-07-28 fifth-pass entry) and
  `tests/test_round5_faithfulness_fixes.py`;
  `tests/test_research_design.py`'s unknown-field test was flipped from
  expecting a skip to expecting a raise. This supersedes the fourth-pass note
  that listed missing-filter-field fail-loud as "deliberately not changed".

### Fixed — eligibility now reaches portfolio assignment; VW uses prior-month ME; `formation_month` range-validated
- Three further fixes (fourth pass on `apply_signal_holding_period`): (1) the
  point-in-time universe-eligibility exclusion from the previous fix only
  reached the breakpoint population (`self.formation`), not the actual
  assignment/return population (`self.merged`) — a stock excluded from
  DEFINING the breakpoints was still sorted BY them and contributed returns.
  Now the same `(permno, cohort)` exclusion is anti-joined out of `self.merged`
  too. (2) Value-weighting used same-month end-of-month market equity, which
  already reflects the return being weighted (a look-ahead: two stocks
  +10%/-10% from equal caps spuriously net to +1% instead of 0%). Added
  `_attach_lagged_me` and switched VW to prior-month ME (`me_{t-1}`), sourced
  from the pre-missing-policy panel. (3) `formation_month=13` (out of the
  valid 1–12 range) was approved as `paper_faithful`; the reviewer now blocks
  an out-of-range value via `_is_invalid_formation_month`. The VW change is a
  no-op for both golden-number e2e tests (single-stock-per-decile designs,
  where VW return = own return regardless of ME timing) — full suite 182
  passed, up from 175, no golden-number changes. See `docs/decision-log.md`
  (2026-07-28 fourth-pass entry); `tests/test_eligibility_and_vw_weighting.py`
  and `tests/test_reviewer_silent_defaults.py` for regression coverage.
  Deliberately NOT changed (documented design tradeoffs, not bugs):
  engine-enforced formation calendar (would wrongly reject monthly/quarterly
  signals), missing-filter-field fail-loud, `ls_quantile` non-integer
  rejection.

### Fixed — formation eligibility/`exchcd` made point-in-time and cohort-specific (third pass); explicit invalid `ls_quantile` now blocked
- Two further regressions found in the same-day universe-eligibility fix
  below: (1) eligibility was computed permno-wide across a stock's ENTIRE
  history, not per-cohort — a stock that passed `universe_filters` at ANY
  point in its history was never excluded even from a different cohort
  where it fails the filter at formation; (2) `breakpoint_source="nyse"`'s
  `exchcd` was still read from the post-`filter_universe` panel, which
  never contains a row at a cohort's own formation month at all under this
  engine's held-months-only convention — `nyse` breakpoints were effectively
  non-functional (crashed with an opaque pandas error), not merely biased.
  Rewrote `apply_signal_holding_period` to look up BOTH `universe_filters`
  fields and `exchcd` point-in-time from `self._pre_missing_policy_data` at
  each `(permno, cohort)`'s own formation month; a pair with no matching
  formation-month row is left unclassified (not excluded — no positive
  evidence). Added a clear `ValueError` in `compute_breakpoints` for an
  empty breakpoint population instead of a confusing crash. Also fixed
  `ReviewGate`'s `ls_quantile` check to catch explicit invalid values
  (`-1`, `1`, `0.9`), not just an unset `None` — `registry._resolve_ls_quantile`
  silently clamps those to a decile at build time, but an approved,
  `paper_faithful` spec should never have contained one. See
  `docs/decision-log.md` (2026-07-28 third-pass entry) for full rationale;
  `tests/test_formation_universe_eligibility.py` (rewritten with
  formation-month rows + 3 new test classes) and
  `tests/test_reviewer_silent_defaults.py` (5 new tests) for regression
  coverage. No-op for existing fixtures (full suite passes unchanged, 175
  passed).

### Fixed — `self.formation` didn't inherit universe-filter eligibility; `ls_quantile` unvalidated
- Regression from the same-day breakpoint look-ahead fix below: `self.formation`
  was rebuilt straight from the raw `signal` DataFrame, which is never run
  through `filter_universe` (that step only touches the returns panel
  `self.data`) — so a stock explicitly excluded by `config["universe_filters"]`
  still contributed its signal to its cohort's breakpoint. Fixed by computing
  `excluded_permnos` (permnos seen anywhere in the panel BEFORE
  `apply_missing_policy` drops missing-return rows, but that fail
  `universe_filters` there) and removing only those from `self.formation` —
  a permno with zero rows anywhere (no evidence either way) is left alone,
  preserving the original look-ahead fix. Also extracted
  `registry._resolve_ls_quantile`: `ls_quantile` values that previously
  produced nonsense (`-1` -> `-1` "groups", `1.5`/`3.3` silently truncated to
  `1`/`3`) now clamp to the standard 10-group default (or round instead of
  truncate), and an unset `ls_quantile` is now covered by
  `ReviewGate._check_silent_high_impact_fields` (requires human confirmation
  instead of silently defaulting on an approved/`paper_faithful` spec). See
  `docs/decision-log.md` (2026-07-28 entry) for full rationale/empirical
  impact; `tests/test_formation_universe_eligibility.py` and
  `tests/test_ls_quantile_validation.py` for the regression tests. No-op for
  existing fixtures (full suite passes unchanged, 167 passed).

### Fixed — `ReviewGate` approved fully-defaulted specs as `paper_faithful`
- A MethodSpec with only `signal.formula`/`required_fields`/`long_leg`/
  `short_leg` set (the last two already default to "high"/"low") and every
  other empirical field left silent (`breakpoint_source`/`weighting`/
  `missing_policy`/`rebalance_frequency` "unspecified",
  `formation_month`/`holding_period`/`accounting_lag`/`sign` all `None`,
  `universe`/`universe_filters` empty) was previously approved with
  `paper_faithful=True` — `_check_ambiguous_fields` only reacts to fields
  the extractor proactively flagged, so a spec where nothing was flagged at
  all sailed through with `registry.build_config`'s menu-default clamping
  completely unreviewed. Added `ReviewGate._check_silent_high_impact_fields`,
  a deterministic backstop that blocks approval when one of a fixed,
  individually-verified subset of `HIGH_IMPACT_FIELDS` is left at its
  unambiguous "unspecified" sentinel with no `ambiguous_fields` entry
  explaining why. See `docs/decision-log.md` (2026-07-28 entry) for the
  exact field list covered and rationale, and
  `tests/test_reviewer_silent_defaults.py` for the regression tests. No-op
  for existing fixtures (full suite passes unchanged); only newly blocks
  specs matching this exact silent-defaults pattern.

### Fixed — breakpoint population leaked future return availability (look-ahead / survivorship)
- `compute_breakpoints` computed formation-cohort quantile breakpoints from
  `self.merged` (the signal panel AFTER an inner join with future held-month
  returns), so a stock delisted immediately after formation (no valid return
  in any held month) was silently excluded from its own cohort's breakpoint
  population — a future-availability leak into a formation-time statistic.
  `apply_signal_holding_period` now also builds `self.formation` (the pure
  formation cross-section: signal + formation-month `exchcd`, built before
  the future-returns join), and `form_portfolios` now computes breakpoints
  from that instead. See `docs/decision-log.md` (2026-07-28 entry) for full
  rationale/empirical impact and `tests/test_no_lookahead_breakpoints.py`
  for the regression test. No-op for signals/universes with no
  delisting/missing-return churn during the holding period (full existing
  suite passes unchanged); changes numbers only for cohorts affected by that
  churn.

### Fixed — fail loud instead of raw KeyError for CRSP-specific optional columns
- `compute_breakpoints` (`breakpoint_source == "nyse"`) and
  `compute_portfolio_returns` (`weighting_rule == "vw"`) each unconditionally
  accessed a CRSP-shaped column (`exchcd`, `me`) that only matters for that
  specific config choice. If a non-CRSP `returns_universe` were ever
  registered without that column, these raised an opaque pandas `KeyError`
  instead of a clear, actionable message. Added explicit `ValueError` checks
  with guidance (register the column for that returns universe, or switch to
  `full_sample`/`ew`). No behavior change for the existing CRSP-based returns
  universes (`us_equity_crsp`/`us_equity_crsp_raw`), which always have both
  columns.

### Fixed — `data/local/` was not gitignored
- `data/local/` (CRSP `msf.parquet` legacy-location shim, `ff_factors.parquet`
  from `scripts/fetch_ff_factors.py`) is downloaded/local data of the same
  kind as `data/papers/`/`data/CZ code/`, but was missing from `.gitignore`
  and showed up as untracked in `git status`. Added `data/local/` to
  `.gitignore` alongside the other data-artifact entries.

### Docs — fixed stale `MethodSpec.returns_universe` docstring
- The field comment still said "deliberately NO default... reviewer hard-blocks
  a spec that leaves this unset", which contradicted the actual behavior in
  `catalog.returns_universe_config`/`DEFAULT_RETURNS_UNIVERSE` (defaults unset
  to `"us_equity_crsp"`) and `AGENTS.md`'s documented policy. Updated the
  comment to match: unset defaults to CRSP monthly; an explicitly-set but
  unregistered universe name is still hard-blocked at review. No behavior
  change — comment-only.

### Removed — dead/duplicate MethodSpec fields + orphaned evaluation module
- An audit of every `MethodSpec` field's actual production readers (registry,
  engine, reviewer, extractor, evaluation) found 3 fields that were populated
  at extraction time but never read anywhere downstream, and one entire
  orphaned module:
  - `PortfolioSortSpec.quantiles` (`list[int]`) — duplicated `ls_quantile`
    (the field the engine actually reads via `registry.build_config`); never
    consumed. Removed the field and the dead `quantiles`-derivation block in
    `src/steps/step1_extractor/__init__.py`'s fallback flat-schema
    constructor.
  - `ReturnCombinationSpec.long_leg`/`short_leg` — duplicated
    `PortfolioSpec.long_leg`/`short_leg` (the fields `registry.resolve_long_leg`/
    `resolve_short_leg` actually read); the nested copies were populated by
    `normalize_curated_schema`'s legacy-nesting lift but never read
    separately.
  - `AmbiguousField.confidence` — written by the extractor and by
    `step2_reviewer/resolution.py`'s `apply_decisions` but never read by any
    reviewer/pipeline logic (`empirical_impact` is the field that actually
    drives review-blocking decisions).
  - `src/evaluation/gt_matcher.py` (`GroundTruthMatcher` class) — zero
    production callers anywhere in the repo (`app.py`/`scripts/`/`backend/`
    never imported it). The real extraction-accuracy evaluation paths are
    `scripts/run_extraction_eval.py` (own field-comparison logic) and
    `src/evaluation/__init__.py::Evaluator` (SignalDoc.csv comparison, used
    by `tests/test_extractor.py`). Deleted the file outright.
  - Note: the richer "curated annotation" extractor-output schema (top-level
    `paper`/`timing`/`universe`/`portfolio` keys with per-field
    `{location, quote, interpretation}` evidence, normalized into the flat
    `MethodSpec` shape by `MethodSpec.normalize_curated_schema`) was
    evaluated for removal in the same pass and deliberately KEPT — it is the
    live extractor-prompt contract (`prompts/extractor/methodspec_extractor.md`)
    and the mechanism providing per-field paper-evidence citations for
    `economic_intuition`/`detailed_definition`/`sign`, which the flat
    `MethodSpec` fields have no other way to carry. See
    `docs/decision-log.md` for the full rationale.
- Full suite green after the change (one test,
  `tests/test_resolution.py::test_apply_decisions_writes_value_clears_ambiguous_and_resets_status`,
  updated to drop its assertion on the removed `confidence` field): 147
  passed, 26 skipped (unchanged from baseline). `ruff check` clean on every
  touched file.

### Fixed — data-loader audit findings (`src/infra/data_layer/`)
- **CCM link-quality filter missing from the multi-source join path**:
  `link_to_permno()` (used by `assemble_signal_master_table`/`multi_source`
  codegen mode) previously joined through EVERY `ccm_lnkhist` row regardless
  of `linktype`/`linkprim`, unlike the legacy `CCMLinker` class which
  correctly restricts to `linktype IN ('LC','LU')` / `linkprim IN ('P','C')`.
  Its docstring also falsely claimed "primary link wins on ties" (the actual
  tie-break was just smallest permno). Added optional `valid_filters`/
  `primary_filter` keys to `catalog.LINK_TABLES["ccm"]` (declarative, so a
  future link table can declare its own quality flags) and updated
  `link_to_permno()` to apply them, matching `CCMLinker`'s semantics. See
  `docs/decision-log.md` 2026-07-25 for full rationale.
- **`_apply_pit_attrs` silently dropped panel rows with a `msenames` coverage
  gap** instead of falling back as its own comment claimed. Now falls back to
  the earliest known attrs record for that key instead of dropping the row.
- **`patents_nber` (registered with `join.date=None`) silently produced zero
  rows forever** in `_load_source_frame` (computed an all-NaN `time_avail_m`
  then immediately dropped every row). Now raises a clear `ValueError` when a
  source has no usable observation-date column, so a MethodSpec mapped to
  such a source fails loud instead of quietly getting an empty signal input.
- New regression tests in `tests/test_signal_master_multisource.py`
  (`test_link_to_permno_drops_bad_linktype_and_prefers_primary`,
  `test_load_source_frame_raises_for_source_without_date_column`,
  `test_apply_pit_attrs_fallback_for_coverage_gap`) and updated the
  `LINK_TABLES` golden-literal in `tests/test_data_catalog.py`. Full suite
  green (147 passed, 26 skipped) after the fixes.

### Changed — clearer step 8/9 method names in `BacktestExecutor`
- Renamed `BacktestExecutor.compute_returns` -> `compute_portfolio_returns`
  and `BacktestExecutor.compute_long_short` -> `combine_portfolio_returns`
  (`src/infra/backtest_engine/__init__.py`). Pure rename, no behavior change:
  clarifies that Step 8 computes each portfolio's *own* return (not yet
  combined), and Step 9 combines those into the final reported series --
  which, depending on `config["return_combination_type"]`, is not always an
  actual long-short spread (`single_signal_portfolio_return`/
  `full_portfolio_return` aren't). Updated all call sites, docstrings, and
  `docs/architecture.md`; historical `CHANGELOG.md`/`docs/decision-log.md`
  entries that reference the old names are left as-is (accurate at the time
  they were written). Full suite re-verified after rename.

### Added — web UI backend scaffolding (Phase A of Streamlit -> React/FastAPI migration)
- New `web` optional-dependencies group in `pyproject.toml`: `fastapi`,
  `uvicorn[standard]`, `python-multipart`. Backend code will live in a new
  `backend/` package (FastAPI app wrapping the existing `Pipeline`/step
  classes; no pipeline logic is being rewritten, only wrapped).
- Extracted the resolution-apply logic that previously lived only in
  `scripts/resolve_review_blocks.py` (a CLI script) into
  `src/steps/step2_reviewer/resolution.py`
  (`get_path`/`set_path`/`build_decision`/`apply_decisions`), so both the CLI
  script and the new backend's future `/api/resolve` endpoint share one
  implementation instead of duplicating it. Pure refactor, no behavior
  change. New tests: `tests/test_resolution.py` (6 tests). Full suite
  re-verified: 140 passed, 26 skipped (was 134/26).
- See `docs/decision-log.md` 2026-07-24 ("Replace Streamlit dashboard with a
  React + FastAPI website") for the full migration rationale/plan.
- Backend implemented: `backend/main.py` (FastAPI app + CORS + startup hook
  that repopulates `RunRegistry` from `EvidenceStore`'s on-disk runs),
  `backend/state.py` (one shared `Pipeline` instance; per-request LLM client
  construction), `backend/jobs.py` (generic `JobManager` for SSE-streamed
  background jobs -- extraction/LLM-review/codegen/backtest execution all
  run through it), `backend/serialization.py` (recursive pydantic/dataclass/
  DataFrame -> JSON helper), and routers `papers`/`methodspecs`/`codegen`/
  `backtest`/`evidence`/`jobs`. Added two small additive methods needed by
  the evidence/backtest routers: `RunRegistry.list_all()`
  (`src/infra/evidence/__init__.py`) and `SnapshotManager.list_snapshots()`
  (`src/infra/data_layer/__init__.py`) -- both non-breaking, existing classes
  had no "list everything" accessor before. New `tests/test_backend_api.py`
  (4 tests, no LLM calls; exercises rules-based review, human resolution,
  and the full plugin -> backtest -> evidence-store flow against the same
  synthetic-data golden numbers as `tests/test_mvp_e2e.py`). Full suite:
  144 passed, 26 skipped. `ruff check src/ backend/` clean.
- Frontend scaffolded: `frontend/` (Vite + React + TypeScript), Tailwind CSS
  v4 + shadcn/ui (radix-nova style) + Recharts + `@tanstack/react-query` +
  `react-router-dom`. Layout shell (`src/layout/AppLayout.tsx`, sidebar nav +
  LLM provider/model selectors shared via `src/lib/llmContext.tsx`), shared
  components (`JobLogPanel`, `MethodSpecViewer`, `MetricsTable`,
  `ReturnChart`), `src/lib/api.ts` fetch client + `src/lib/useJobStream.ts`
  SSE hook (falls back to a one-shot `GET /api/jobs/{id}` poll if the SSE
  connection drops without a terminal event). Three pages wired up:
  `PipelineE2EPage` (extract -> review -> resolve -> codegen -> validate ->
  backtest, stage by stage), `BacktestExperimentsPage` (single-run backtest
  against a resolved spec + pasted plugin code + picked snapshot),
  `TraceLogsPage` (run registry table + evidence file browser/download).
  `npx tsc -b`, `npm run build`, and `npm run lint` (oxlint) all clean.
  Manually smoke-tested both dev servers together (`uvicorn` on :8000, Vite
  on :5173 proxying `/api/*` to :8000).

### Changed — backtest engine consolidated into a single `BacktestExecutor` class/file
- `src/infra/backtest_engine/steps.py` and `estimators.py` are deleted;
  everything (orchestration + every step's computation) now lives in one
  class, `BacktestExecutor`, in `src/infra/backtest_engine/__init__.py`.
  `_dispatch()`/`Step` Protocol/`BacktestContext` dataclass are gone —
  `run_with_config()` is now a flat, readable sequence of `self.<step>()`
  calls in fixed order (10 steps: `load_data` -> `apply_delisting_returns` ->
  `apply_missing_policy` -> `filter_universe` -> `apply_excess_returns` ->
  `apply_signal_holding_period` -> `form_portfolios` -> `compute_returns` ->
  `compute_long_short` -> `compute_metrics`, + `compute_factor_alphas` when
  factor data is supplied).
- Every step method accepts its inputs as optional explicit arguments
  (falling back to the matching `self.*` attribute when omitted), so each
  step stays independently unit-testable exactly like the old pure
  functions (e.g. `BacktestExecutor().compute_long_short(rets, config)`)
  without needing to run the whole pipeline first.
- 9 test files updated to call `BacktestExecutor().<method>(...)` /
  `BacktestExecutor.<static_method>(...)` (for the few pure utilities kept
  as `@staticmethod`: `load_msf`, `load_daily_msf`, `apply_universe_filters`)
  instead of the deleted `steps.<function>(...)`. No behavior/assertion
  changes; full suite re-verified: 134 passed, 26 skipped (unchanged).
- See `docs/decision-log.md` 2026-07-24 for full rationale and the
  testability trade-off considered.

### Fixed — backtest engine: formation-locked (cohort-based) breakpoints/portfolio assignment
- `steps.apply_signal_holding_period` (renamed from `merge_signal`, see
  below) now tags every expanded row with a `cohort` column
  (the signal's original formation `yyyymm`). `compute_breakpoints`/
  `assign_portfolios` group/look up by `cohort` instead of the current
  `yyyymm`, so a stock's portfolio membership is computed once at formation
  and held fixed for its whole holding period (the standard
  form-once-hold-fixed factor-replication convention), instead of being
  re-derived fresh every current month. A cohort whose de-duplicated
  cross-section produces duplicate quantile breakpoints (too few distinct
  signal values) is skipped for that cohort rather than crashing.
- New tests: `tests/test_formation_locked_breakpoints.py`.
- See `docs/decision-log.md` 2026-07-24 for full rationale and empirical
  impact.

### Changed — renamed `steps.merge_signal` to `steps.apply_signal_holding_period`
- The old name only described the trailing `.merge()` call, not the
  non-trivial work (expanding a low-frequency signal into one row per held
  month, capped at the rebalance step) — renamed to match the existing
  `apply_*` step-naming convention (`apply_delisting_returns`/
  `apply_missing_policy`/`apply_excess_returns`). Pure rename, no behavior
  change; full suite re-verified (134 passed, 26 skipped).

### Removed — non-standard backtest engine capabilities (standardize to one vanilla single-dim portfolio-sort path)
- Removed overlapping-cohort holding (`config["overlapping"]`,
  `merge_signal_overlap`/`compute_breakpoints_overlap`/
  `assign_portfolios_overlap`/`compute_returns_overlap`/
  `compute_long_short_overlap`, `SignalTiming.overlapping_portfolios`/
  `skip_month`), the discrete/categorical sort form (`cat_form="discrete"`,
  `MethodSpec.cat_form`), the optional microcap-exclusion filter
  (`config["microcap_exclude"]`), multi-dimensional (double) sorts
  (`config["sort_dims"]`, `compute_breakpoints_multi`/
  `assign_portfolios_multi`, `registry.resolve_sort_dims`,
  `PortfolioSpec.sorts[]`/`SortLegSpec`), and the Fama-MacBeth
  cross-sectional-regression estimator (`estimator="fama_macbeth"`,
  `steps.compute_fama_macbeth`, `PortfolioConstructionType.REGRESSION_WEIGHTED`,
  the optional `linearmodels` dependency).
- Deleted fixtures/tests tied to the removed capabilities: 9 Asness-Bender
  1998 fixtures (`data/test_method_specs_human_labeled/AB1998_*`), 2
  LohWarachka 2011 fixtures, 3 Ball 2016 double-sort fixtures, 3 orphaned
  momentum/double-sort fixtures+plugins under `tests/fixtures/`,
  `tests/test_overlapping_holding.py`, `tests/test_multi_sort.py`,
  `tests/test_fama_macbeth.py`, `tests/test_discrete_sort.py`, and the
  microcap tests in `tests/test_research_design.py`.
- Updated `src/steps/step1_extractor/__init__.py` (extraction schema/field
  mapping), `src/steps/step2_reviewer/__init__.py` (fixed a latent
  `AttributeError` in `_check_portfolio_structure_consistency` that referenced
  the now-removed `portfolio.sorts`), `src/evaluation/gt_matcher.py`,
  `src/evaluation/helpers.py`, `app.py`, `scripts/run_extraction_eval.py`,
  and `prompts/extractor/methodspec_extractor.md` to stop referencing the
  removed fields.
- Full suite after both changes: 134 passed, 26 skipped (was 193/26 before
  either change — the 59 fewer are the deleted tests for removed
  capabilities, not a regression). See `docs/decision-log.md` 2026-07-24 for
  full rationale.

### Fixed — README.md was still describing the pre-restructure, unimplemented framework
- Answering "is README.md up to date": no — it hadn't been touched since the
  original framework proposal. Updated it to match the current repo:
  - "Architecture" diagram now shows the real 7 numbered steps
    (`step1_extractor` … `step7_replication_diff`) instead of a generic
    9-module list that didn't match any actual folder names.
  - "Project Structure" tree replaced with the real `src/steps/stepN_*/` +
    `src/infra/*` layout (previously showed flat, long-gone paths like
    `src/extractor/`, `src/controller/`, `src/engine/`, `src/attribution/`).
  - "Status" changed from `**Framework stage** — high-level module
    interfaces are defined; implementation details are in progress.` (wrong)
    to `**Implemented, single-factor pilot stage.**`, pointing at
    `docs/architecture.md` §10 for the authoritative per-module status table.

### Fixed — docs/architecture.md stale file-layout section
- Audited the repo for leftover pre-restructure content. No stale source
  duplicates remain under `src/` (a `grep_search` hit for `src/steps/step5_engine/`
  and `src/steps/engine|controller|attribution/` was a stale search-index
  phantom — confirmed via `file_search`/`list_dir` that none of those paths
  exist on disk; matches were only in `CHANGELOG.md`/`docs/decision-log.md`
  historical entries, which is expected).
- `docs/architecture.md` §5 File Layout and two §7/§10 references still
  described the pre-`src/steps/stepN_*`/`src/infra/*` layout (flat
  `src/extractor/`, `src/review_gate/`, `src/meta_coder/`, `src/sandbox/`,
  `src/engine/`, `src/controller/`, `src/data_layer/`, `src/models/`,
  `src/pdf_mapper.py`, `src/llm.py`) even though §4.3/§4.6 already referenced
  the current names. Updated the file tree and the `HXZ_STANDARD_CONFIG`
  location to match the real current layout (`src/steps/step1_extractor/` …
  `step7_replication_diff/`, `src/infra/{pdf_mapper.py,llm.py,trace.py,
  repair.py,backtest_engine/,data_layer/,evidence/,models/,registry/}`).
  Bumped doc version 9 → 10, `updated: 2026-07-24`.

### Changed — pipeline simplification: remove LLM hook codegen, standardize the engine- **The Meta-Coder LLM now generates only `compute_signal()` (the pure signal
  formula).** All LLM-generated *hook* code is removed. Portfolio construction
  is fully standardized: every empirical choice (weighting vw/ew, breakpoints
  nyse/full_sample, missing policy, return combination, sort form, estimator)
  is *selected* from a fixed menu by `step3_codegen.registry.build_config`. A
  MethodSpec value outside its menu is deterministically clamped to the menu
  default (`_clamp`) instead of triggering code generation.
- **Removed hook machinery (deleted cleanly, no stubs):**
  - `step3_codegen.registry.detect_hooks` and `MetaCoder._generate_hooks` /
    `HOOK_SIGNATURES` / `HOOK_RETURN_DOCS` / hook system prompt.
  - `src/infra/backtest_engine/registry.py` (run-time `load_hooks`) — file
    deleted; `BacktestExecutor._load_hooks`/`_detect_hooks`/`self._hooks` and
    the hook branch of `_dispatch()` removed. `_dispatch` now only routes to
    the deterministic `_overlap`/`_multi` step variants and the standard steps.
  - `PluginRecord.hooks` and `ValidationReport.hooks_ok`; the step4
    `AdversarialSandbox._check_hooks`/`_hook_arity` static hook-contract check.
  - `prompts/meta_coder/hook_system.md`.
- **Returns table defaults to CRSP monthly.** `catalog.returns_universe_config`
  now defaults to `us_equity_crsp` (`DEFAULT_RETURNS_UNIVERSE`) when
  `returns_universe` is unset; the reviewer's `_check_returns_universe` warns +
  defaults instead of hard-blocking (an explicitly-set unregistered universe is
  still blocked). Signal-input sources stay multi-source via the catalog.
- **Tests/fixtures:** deleted `tests/test_engine_hooks.py` and the ball2016
  hook-demonstration e2e (its golden numbers were tied to a multi-leg hook
  construction that is no longer supported — clamped to the standard
  combination); removed the hook-detection/`hooks_ok` assertions from
  `test_accruals_e2e.py` and `test_sandbox_validation.py`; updated
  `test_no_default_source.py` for the CRSP-default returns behavior. Full suite
  green (161 passed, 26 skipped).

### Changed — MethodSpec schema simplification (moderate prune)
- **Merged `portfolio.sort` + `portfolio.breakpoints`** into a single `sort`
  block (`PortfolioSortSpec`: `breakpoint_source`, `ls_quantile`, `quantiles`).
  Deleted the `BreakpointSpec` model and the `PortfolioSpec.model_post_init`
  dual-sync. `MethodSpec.breakpoint_source` now reads `portfolio.sort`.
- **Removed dead fields (extra keys ignored on load, no JSON migration needed):**
  `signal.field_sources` (+ the `FieldSource` model), `portfolio.weighting_scheme`
  (duplicate of `weighting`), `portfolio.filter` (legacy free-text). Readers in
  `step3_codegen.registry`, `step1_extractor`, `step2_reviewer`
  (`HIGH_IMPACT_FIELDS`/`SENSIBLE_DEFAULTS`), `src/evaluation`, and
  `scripts/validate_methodspecs.py` repointed to `portfolio.sort`. All
  human-labeled specs still parse; golden numbers unchanged.

### Changed — MethodSpec schema flatten + enum pruning (B5)
- **Flattened `reported_results`.** Portfolio-return construction
  (`construction_type`, `sorts`, `return_combination`) moved from the deep
  `reported_results.return_calculation.portfolio_return` nesting onto
  `PortfolioSpec`. Deleted `ReturnCalculationSpec` and `PortfolioReturnSpec`;
  `ReportedResultsSpec` now holds only reported numbers
  (`return_horizon`/`return_type`/`spreads`/`t_stats`/`main_spread`/`main_t_stat`),
  and `comparison_policy`/`input_return` are dropped. `MethodSpec.normalize_curated_schema`
  lifts the legacy nested fields onto `portfolio` on load, so existing JSON
  (fixtures + ~26 human-labeled specs) keeps working with no migration.
- **Pruned hook-only enum values** (legacy values coerced to `unspecified` on
  load, then clamped by `build_config` — no JSON migration): `BreakpointSource`
  drops `conditional`/`paper_specific`; `MissingAction` drops
  `fill_zero`/`fill_median`/`fill_forward`/`winsorize` (engine is drop-only);
  `PortfolioConstructionType` drops `factor_model_alpha`/`event_window_return`;
  `ReturnCombinationType` drops `alpha_estimate`. Coercion wired via
  `PortfolioSortSpec`/`MissingPolicy`/`ReturnCombinationSpec`/`PortfolioSpec`
  before-validators.
- **Fixed a latent load bug:** `ReturnCombinationSpec.long_leg`/`short_leg`
  (typed `str`) now coerce a JSON `null` to `""` — the 9 AB1998 human-labeled
  specs that previously failed to load now parse. All 26 labeled specs load.
- Readers repointed to the flat fields: `registry.build_config`/`resolve_sort_dims`,
  `step2_reviewer` (`HIGH_IMPACT_FIELDS`, `_check_reported_results_contract`,
  `_check_portfolio_structure_consistency`), `tests/test_multi_sort.py`. Full
  suite green (161 passed, 26 skipped); golden numbers unchanged.

### Fixed — leftover lint + stale-doc cleanup
- `ruff check src/` is now fully clean: removed the unused `spec_to_paper` in
  `src/evaluation/gt_matcher.py`, and resolved the pre-existing `F821` in
  `src/infra/llm.py` (the documentary `"LLMClient"` back-reference is now a
  `TYPE_CHECKING` alias).
- Purged the removed hook/schema vocabulary from docs/prompts:
  `docs/architecture.md` (principle table, Meta-Coder/§4.6 sections + banners,
  flowchart, status rows), `prompts/extractor/methodspec_extractor.md`
  (flat JSON skeleton + enum "Allowed Values" + §4.7/§4.8 prose + checklist),
  `prompts/review_gate/methodspec_audit.md` (enum lists + flat portfolio refs),
  `schemas/methodspec-json-template.md` (authoritative top banner + breakpoint
  enum list + §2.11 weighting).

### Changed — removed remaining silent CRSP defaults (universe screen + legacy file-path fallback)
- **`filter_universe` no longer applies any hardcoded `shrcd`/`exchcd`/`siccd`
  baseline screen.** That screen assumed every returns panel is CRSP-shaped,
  which contradicts the "no silent default data source" principle the
  `catalog.py`/`RETURNS_UNIVERSES` design already established for the returns
  side. `filter_universe` now applies ONLY `config["universe_filters"]`
  (already MethodSpec-driven, via `spec.portfolio.universe_filters`) plus the
  optional `microcap_exclude` diagnostic exclusion. All 9 golden e2e tests are
  byte-identical (the underlying synthetic test panels don't contain
  disqualifying rows, so the hardcoded screen was a no-op for them anyway);
  only the 2 unit tests that directly asserted the old hardcoded baseline
  needed updating (`tests/test_research_design.py`).
- **Extractor prompt updated** (`prompts/extractor/methodspec_extractor.md`
  §4.5.2, new): the common "ordinary common shares / NYSE-AMEX-NASDAQ /
  ex-financials" boilerplate that most US-equity papers state (often just by
  citation) must now be captured as explicit `universe.filters` entries by
  the extractor -- there is no code-level fallback that applies it anymore.
  `portfolio.universe`/`portfolio.universe_filters` are already in
  `step2_reviewer`'s `HIGH_IMPACT_FIELDS`, so missing/low-evidence universe
  filters are already covered by the existing review-gate evidence check;
  no new reviewer check was added.
- **Fixed a latent silent-default-to-CRSP bug in `BacktestExecutor._load_data()`.**
  The `<data_path>/local/msf.parquet` legacy file-location fallback
  previously applied UNCONDITIONALLY whenever `<data_path>/raw/<returns_table>.parquet`
  was missing, regardless of what `returns_table` actually named -- so a
  registered non-CRSP returns universe with a missing raw file would have
  silently loaded CRSP data instead of failing loud. Scoped the fallback to
  `returns_table == "crsp_msf"` only; any other returns table with a missing
  raw file now raises `FileNotFoundError` instead. New test:
  `tests/test_no_default_source.py::test_load_data_does_not_fall_back_to_crsp_for_a_different_returns_table`.
  This was found via a full-repo audit for this class of bug (prompted by a
  design review); everything else audited (config defaults for
  breakpoint_source/weighting_rule/cat_form/etc., the canonical internal
  panel schema permno/yyyymm/ret/me/exchcd/shrcd/siccd, `pick_signal_input_mode()`,
  the reviewer's hard-block checks) was confirmed to already be MethodSpec-
  /catalog-driven with no silent defaults.

### Changed — estimator-strategy layer + form_portfolios merge; deleted the dead neutralize_signal scaffold
- **New `src/infra/backtest_engine/estimators.py`** — `BacktestExecutor.run_with_config()`
  now runs a fixed *prep* chain (load/delisting/missing-policy/universe/excess-returns/
  merge_signal) then hands the merged panel to a swappable **estimator** looked up by
  `config["estimator"]`: `run_portfolio_sort` (the sort/weight/combine chain, default)
  or `run_fama_macbeth` (single-characteristic cross-sectional regression). The old
  inline `if config.get("estimator") == "fama_macbeth"` branch in `run_with_config()`
  is gone; adding a genuinely different estimator (e.g. a future `custom` estimator
  delegating entirely to an `estimator_hook`) means adding one function + a registry
  entry, not touching `run_with_config()` again. No behavior change (golden e2e
  byte-identical).
- **Merged `compute_breakpoints` + `assign_portfolios` into one hookable
  `form_portfolios` step** (`steps.py`). These two Step-contract functions were
  never useful independently — `compute_breakpoints_multi` (the multi-dim
  counterpart) didn't even do real work, it just returned `config["sort_dims"]`
  unchanged so `assign_portfolios_multi` could do the actual per-dimension logic,
  a "fake step" kept only to satisfy the two-step dispatch contract. `form_portfolios`
  composes the existing `compute_breakpoints`/`assign_portfolios` (and their
  `_multi` counterparts internally, when `config["sort_dims"]` has 2+ entries) into
  a single unit; `form_portfolios_overlap` does the same for the overlapping-cohort
  variants. The underlying `compute_breakpoints`/`assign_portfolios`/`_multi`/
  `_overlap` functions are unchanged and still directly unit-tested.
  - **Hook contract:** `form_portfolios_hook(df, config) -> df` REPLACES
    `compute_breakpoints_hook` + `assign_portfolios_hook` (one hook point for "how
    portfolios get formed", regardless of dimensionality). Updated
    `HOOK_SIGNATURES`/`HOOK_RETURN_DOCS` (`step3_codegen/__init__.py`),
    `detect_hooks()` (`step3_codegen/registry.py`, now emits a single
    `hooks["form_portfolios"]` key), `load_hooks()`
    (`backtest_engine/registry.py`), and `_MULTI_DIM_STEPS`/`_OVERLAP_STEPS`
    (`backtest_engine/__init__.py`). Migrated the two fixture plugins that hand-write
    these hooks (`ball2016_cash_based_operating_profitability_factor.py`,
    `fama_french_1993_double_sort_hml.py`) to a single merged `form_portfolios_hook`.
    Updated the corresponding unit/e2e test assertions
    (`test_engine_hooks.py`, `test_ball2016_e2e.py`, `test_sandbox_validation.py`).
    Golden e2e numbers unchanged.
- **Deleted `neutralize_signal`** (`steps.py`) — a no-op scaffold with no
  MethodSpec field ever driving it (`config["neutralization"]` was always
  `"none"` in practice; any other value just raised `NotImplementedError`).
  Pure YAGNI: a step slot, dispatch call, and hook contract entry
  (`neutralize_signal_hook`) existed for a feature nothing used. Removed the
  dispatch call from `estimators.run_portfolio_sort`, the `neutralize_signal`
  hook-loading entry (`backtest_engine/registry.py`), the `HOOK_SIGNATURES`/
  `HOOK_RETURN_DOCS` entries, the `"neutralization": "none"` config default
  (`step3_codegen/registry.py`), and `tests/test_research_design.py`'s
  `TestNeutralizeSignalScaffold`. Signal neutralization, if a paper ever needs it,
  should be reintroduced later as a real `MethodSpec`-driven field + hook, not
  a speculative always-no-op step.
- **Docs updated:** `docs/architecture.md` §4.6 tables, `prompts/meta_coder/hook_system.md`'s
  column-availability note, and this file. See `docs/decision-log.md` for the
  rationale (why estimator-as-strategy + a single `form_portfolios` hook point
  makes the engine more general, not less).

### Changed — no silent default data source (signal + returns), unified via a declarative data catalog
- **New `src/infra/data_layer/catalog.py`** — one declarative catalog is now the
  single source of truth for data sources, unifying four previously-scattered
  fragments (`_CONCEPT_MAP`, `SIGNAL_SOURCES`, `LINK_TABLES`, and the empty
  `DataDictionary`). Each source declares its `join` ({key, link, date, lag}),
  `physical_columns`, and concept→column `columns`; `_link_tables` describes how
  each native key (gvkey/ticker/secid) resolves to `permno` point-in-time.
  `SIGNAL_SOURCES`/`LINK_TABLES` in `data_layer/__init__.py` are now DERIVED from
  the catalog (byte-identical to the old literals — see `tests/test_data_catalog.py`).
  Registering a new data source (IBES/OptionMetrics/13F/…, or a new returns
  universe) is now a single catalog entry.
- **Signal source no longer defaults to Compustat.**
  `method_spec._normalize_mapping_entry` used to infer `crsp_msf` for known CRSP
  columns and silently `comp_funda` for *everything else* — misattributing
  IBES/OptionMetrics/etc. columns to Compustat. It now resolves a plain-column
  mapping via `catalog.source_of_column`; an unknown column returns source=""
  (unresolved), never a guess. New `MethodSpec.unresolved_source_fields()`
  surfaces these. `DataDictionary.normalize_fields` now emits the richer
  `{source, column}` form via the catalog (was plain strings).
- **Reviewer hard-blocks unresolved/unknown sources** (`ReviewGate._check_source_mapping_resolved`):
  a formula field whose column resolves to no registered source, or a mapping
  naming an unregistered source, blocks approval with a message to register it
  in the catalog once.
- **Codegen fails loud instead of defaulting.** `script_generator.pick_signal_input_mode`
  is now fully source-driven and raises on an empty/unresolved mapping (removing
  the old `_signal_needs_compustat` empty→Compustat default). app.py's duplicate
  heuristic was removed in favor of a non-raising UI wrapper over the shared
  function.
- **Returns universe now comes from the spec, not a hardcoded CRSP panel.** New
  `MethodSpec.returns_universe` field (default None) + `catalog.RETURNS_UNIVERSES`
  registry (CRSP US equity is one entry, not a default). `build_config` fills
  `returns_table`/`returns_layout` from it; `BacktestExecutor._load_data` no
  longer defaults to `crsp_msf` and raises when neither is set; the reviewer
  (`_check_returns_universe`) hard-blocks an unset/unregistered returns universe.
- **Fixtures migrated (golden numbers unchanged):** the 9 resolved golden
  fixtures gained `returns_universe: us_equity_crsp`; `ball2016` gained an
  explicit `normalized_mapping` (was empty, previously relying on the
  empty→Compustat default). These add explicit values only — no metric changed.
- **New tests:** `tests/test_data_catalog.py` (derived structures == historical
  literals + lookups) and `tests/test_no_default_source.py` (fail-loud signal +
  returns behavior). Full suite green (187 passed / 26 skipped); golden e2e
  (accruals/ball2016/mvp) byte-identical.
- **Note:** `src/steps/step5_engine/` (a stale engine duplicate flagged in the
  plan) no longer exists on disk — nothing to remove.

### Changed — MetaCoder signal/hook prompts no longer hard-code CRSP/Compustat as the only data sources
- `prompts/meta_coder/signal_plugin_system.md`'s "Input table schema" section
  previously listed only Compustat mnemonics (at, sale, ceq, ...) and CRSP
  fields (ret, shrout, prc, ...) as if those were the only possible input
  columns. The signal-input source registry (`SIGNAL_SOURCES` in
  `src/infra/data_layer/__init__.py`) actually supports several more sources
  (`ibes_statsumu`, `optionm_vsurf`, `tr_13f`, `patents_nber`), whose columns
  (e.g. IBES's `meanest`) don't look like CRSP/Compustat mnemonics at all.
  Rewrote the section to say the authoritative column names always come from
  the per-request "Column Mapping" block (already injected by
  `MetaCoder._build_prompt`), with CRSP/Compustat/IBES/OptionMetrics/13F/
  patents listed only as examples of what a source *can* look like.
- **Bigger bug, same root cause:** `prompts/meta_coder/hook_system.md` claimed
  the DataFrame passed to hooks has "Additional Compustat columns as
  available: at, sale, ceq, dltt, ib, etc." — this is simply false, not just
  misleading. Traced the actual data flow: hooks receive the CRSP monthly
  panel from `load_msf()` (permno/yyyymm/ret/me/shrcd/exchcd/siccd/
  prc/shrout/date) plus `dlret` when present; `merge_signal()`
  (`src/infra/backtest_engine/steps.py`) only carries the plugin's own
  computed `signal` column across from the signal-formula table — raw
  Compustat/IBES/OptionMetrics source columns used inside `compute_signal()`
  are never merged into the hook-facing df at any pipeline stage. A hook
  written against the old prompt's claim would `KeyError` on any Compustat
  column reference. Rewrote the section to state the CRSP-only column set
  precisely, call out that `signal` is only present in hooks running after
  `merge_signal` (not `filter_universe_hook`/`apply_missing_policy_hook`),
  and note `dlret` is only relevant to `apply_delisting_returns_hook`. No
  code changes — prompt-only fix in both files.

### Changed — feedback-loop redesign: two bounded automatic loops + shared RepairLoop + step 7 rename
- **New shared `RepairLoop`** (`src/infra/repair.py`) consolidates the three
  near-duplicate technical repair loops (previously in
  `Pipeline._validate_with_repair`, `Pipeline.run_from_method_spec`'s inline
  execute loop, and `DualTrackController._run_track`) into one class with
  `build_validate_repair()` + `execute_with_repair()`. `Pipeline` and
  `DualTrackController` both delegate to it; `MAX_REPAIR_RETRIES` now lives in
  one place. Behavior preserved (golden-number e2e tests unchanged).
- **Repair audit trail:** new `RepairAttempt` model (`src/infra/models/run_record.py`)
  records every technical-repair iteration (attempt index, trigger stage
  validate|execute, error text, code hash before/after, passed). Accumulated by
  `RepairLoop` and persisted on `RunRecord.repair_history` via the evidence store.
- **New Review→Extractor targeted re-extraction loop** in
  `Pipeline.run_full_pipeline` (`MAX_REEXTRACT=2`): when the LLM reviewer returns
  `remediation_mode == TARGETED_REEXTRACTION` and backs a flagged high-impact
  field with a paper quote, the pipeline re-extracts just those fields (feeding
  the extractor the reviewer's citation) and re-reviews, bounded. Paper-silent
  fields (no citation), `FULL_REGENERATION`, or an exhausted budget escalate to a
  human (`needs_manual`). New helpers `Pipeline._review` (prefers `review_with_llm`
  so `remediation_mode` is actually decided) and `Pipeline._build_reextract_feedback`.
  `SemanticExtractor.extract()` gained a `reextract_feedback` param + a prompt hook
  (`REEXTRACT_FEEDBACK_TEMPLATE`); `MethodSpec` gained a `reextraction_attempts`
  counter.
- **Renamed step 7 `attribution` → `replication_diff`:** directory
  `src/steps/step7_attribution/` → `src/steps/step7_replication_diff/`;
  `AttributionLayer` → `ReplicationDiff`, `AttributionResult` → `ReplicationDiffResult`,
  `attribute_ablation` → `diff_ablation`, `attribute_shapley` → `diff_shapley`.
  Updated `pipeline.py` (`self.replication_diff`, stage label `replication_diff`),
  `app.py`, `AGENTS.md` Module Map, `docs/architecture.md`. It is a terminal
  reporting step (compare vs C&Z/paper, decompose the gap), not a loop trigger.
- **Design principle recorded** (`docs/decision-log.md`): each loop feeds back
  "the problem / what to re-check", never the answer; technical fixes are
  automated, empirical judgments stay human-gated (Review Gate). No automatic
  empirical backtrack from later stages.
- Docs updated: `docs/architecture.md` §3.1 (rewritten to describe the two real
  loops) + §4/§5, `docs/roadmap.md` (loop-redesign note + deferred future
  improvements: degenerate-result auto-flag, per-field evidence differentiation).
- New tests: `tests/test_repair_loop.py` (RepairLoop audit trail + outcome
  contract), `tests/test_reextraction_loop.py` (Review→Extractor loop control flow).
  Full suite: 174 passed, 26 skipped; `ruff check src/` clean.

### Added — `Pipeline.run_full_pipeline()` re-wires steps 1/2/6/7 into the orchestrator
- Restored constructor wiring removed earlier the same day:
  `self.extractor` (`SemanticExtractor`), `self.review_gate` (`ReviewGate`),
  `self.controller` (`DualTrackController`), `self.attribution`
  (`AttributionLayer`), and their imports (`ExperimentPlan` too).
- New `Pipeline.run_full_pipeline(factor_id, snapshot_id, paper_text, plan=None,
  config_overrides=None) -> tuple[list[RunRecord], PipelineStatus]`: chains all
  7 steps (extract → review → generate → validate → execute → dual-track/
  ablations → attribute). Reuses `_validate_with_repair()` for steps 3-4 (same
  Sandbox→Meta-Coder repair loop `run_from_method_spec()` uses) and
  `self.controller.run_experiment()` for steps 5-6 (each track builds+executes
  its own config variant with its own per-track repair loop, unchanged).
- Restored `PipelineStatus` dataclass (`factor_id`, `stage`, `error`,
  `needs_manual` — no `backtrack_count` this time, see below).
- **Deliberately fail-fast, no fake backtrack:** unlike the removed
  `run_factor()`, `run_full_pipeline()` makes no claim of automatically
  retrying Review→Extractor / Sandbox→Review(empirical) / Attribution→Review.
  A rejection at any stage sets `PipelineStatus.stage="failed"` with `.error`
  describing why and returns immediately; the caller re-invokes manually
  (e.g., `pipeline.extractor.extract()` with edited `paper_text`) to retry.
  Real cross-stage backtrack remains Phase 2 scope (`docs/roadmap.md`).
- **Every step independently callable for testing**, by design: with the
  constructor wiring restored, `pipeline.extractor.extract(...)`,
  `pipeline.review_gate.review(...)`, `pipeline.meta_coder.generate_plugin(...)`,
  `pipeline.sandbox.validate(...)`, `pipeline.runner.build_script()/.execute()`,
  `pipeline.controller.run_experiment(...)`, and
  `pipeline.attribution.attribute_ablation(...)` can each be driven standalone
  without going through `run_full_pipeline()`.
- Updated `docs/architecture.md` §3.1 (feedback-loop table now describes
  `run_full_pipeline()`'s real fail-fast behavior instead of the old removed
  `run_factor()`) and §4, `docs/roadmap.md` Phase 1 status note, and added a
  `docs/decision-log.md` entry explaining why this was re-added as fail-fast
  rather than re-implementing the old stub backtrack loops.
- Verified: full `pytest tests/` (163 passed, 26 skipped) and
  `ruff check src/pipeline.py` clean; smoke-tested `Pipeline()` instantiation
  wires all four sub-components correctly.

### Removed — dead code cleanup across `src/pipeline.py` and `src/steps/`/`src/infra/`
- **`Pipeline.run_factor()`** and its dedicated helpers (`_has_empirical_issues`,
  `_is_anomalous`, `PipelineStatus` dataclass, `MAX_BACKTRACK_DEPTH` constant),
  plus the constructor wiring that only existed to support it
  (`self.extractor`/`SemanticExtractor`, `self.review_gate`/`ReviewGate`,
  `self.controller`/`DualTrackController`+`ExperimentPlan`,
  `self.attribution`/`AttributionLayer`, and their imports). Confirmed via
  repo-wide grep (`app.py`, `scripts/`, `tests/`) that `run_factor()` had zero
  callers anywhere; three of its four "feedback loop" branches were TODO stubs
  that failed immediately instead of retrying (see the two entries below —
  this is the conclusion of that same investigation). `Pipeline`'s sole
  remaining entry point is `run_from_method_spec()`. See
  `docs/decision-log.md` 2026-07-22 for full rationale. Also updated
  `docs/architecture.md` §3.1/§4 and `docs/roadmap.md` to reflect the removal.
- **`_newey_west_var`** deprecated alias in `src/infra/backtest_engine/__init__.py`
  — zero callers anywhere in the repo.
- **`STANDARD`/`FILTER_UNIVERSE_ALWAYS_HOOK_REASON`** backward-compat re-exports
  in `src/infra/backtest_engine/__init__.py` — nothing imports these from
  `backtest_engine` (only from their real home, `step3_codegen.registry`).
- **`cz_metadata`/`osap_code`** parameters on `run_factor()` — accepted but
  never used in the method body, and `SemanticExtractor.extract()` doesn't
  even have parameters for them (removed earlier for information-leakage
  reasons), so passing them silently did nothing.
- Unused imports flagged by `ruff --select F401`: `get_factor_to_pdf` in
  `src/evaluation/helpers.py`, `dataclasses.field` + `typing.Any` in
  `src/infra/trace.py`, `typing.Any` in `src/steps/step5_backtest_runner/__init__.py`.
- Verified: full `pytest tests/` (163 passed, 26 skipped — unrelated
  slow/LLM-gated tests) and `ruff check src/` both clean after these removals.

### Changed — re-attributed "build the standalone backtest script" from Step 5 to Step 3 (docs/comments only)
- `AGENTS.md` Module Map previously credited Step 5 (`BacktestRunner`) with
  both "build the script" and "execute it". Script assembly
  (`generate_backtest_script`) is conceptually part of Step 3's output (it
  turns the plugin's `compute_signal` + hooks into the one complete
  standalone script) — `BacktestRunner.build_script()` only lives in the
  step5 module because it also needs `DataLayer` snapshot-path resolution,
  which `step3_codegen` doesn't have. Step 5 now means execute-only
  (`BacktestRunner.execute()`). Updated: `AGENTS.md`'s step3/step5 Module Map
  rows, `step5_backtest_runner/__init__.py`'s module docstring, and
  `Pipeline`'s class docstring (the workflow list, and the
  `run_from_method_spec()` vs `run_factor()` comparison — with this
  relabeling `run_from_method_spec()` is now a clean linear 3→4→5, no more
  "interleaves 4 and 5"; `run_factor()` instead defers step 3's "build" half
  until `DualTrackController.run_experiment()`). No code or behavior changed.

### Fixed — docs/comments overstated `Pipeline.run_factor()` feedback-loop completeness
- `src/pipeline.py` module/class docstrings and `docs/architecture.md` §3.1 previously
  described Review Gate → Extractor, Sandbox → Review Gate (empirical), and
  Attribution → Review Gate as implemented backtrack loops. In the actual code
  all three sites increment `backtrack_count` and then immediately set
  `status.stage = "failed"` and return — they never re-invoke the upstream
  stage, so today they behave as "fail on first trigger" rather than a retry
  loop. Only the Sandbox → Meta-Coder technical-repair loop (inside the
  `validate` stage's `for attempt in range(...)`) actually retries. Updated the
  docstrings, inline `# TODO` comments at all three stub sites, and the
  architecture.md §3.1 table / §4 status row to say "not yet implemented"
  instead of "implemented", so the comments match current behavior. No
  behavior changed.
- Also re-numbered the `Pipeline` class docstring's workflow list from 8 steps
  to 7, matching `AGENTS.md`'s Module Map (EvidenceStore is infra, not a
  numbered pipeline step).

### Added — `src/steps/step5_backtest_runner/` (real Step 5 module) + fixed `DualTrackController._run_track()` stub
- "Step 5" as a pipeline action (build the standalone script, execute it via
  subprocess) had no dedicated module — its logic lived as private methods on
  `Pipeline` (`_build_script`/`_execute_script`/`_make_failed_run_record`),
  unlike every other numbered step (1–4, 6, 7), which each expose a class
  `Pipeline` orchestrates. New `src/steps/step5_backtest_runner/` /
  `BacktestRunner` class restores that consistency:
  `build_script()` / `execute()` (moved verbatim from `Pipeline`) plus
  `make_run_record()` / `make_failed_run_record()` (also moved, so the exact
  same RunRecord-building logic is shared rather than duplicated between
  `Pipeline` and `DualTrackController`, added below). Deliberately has zero
  dependency on `src.infra.backtest_engine` (`BacktestExecutor`) — it only
  calls `step3_codegen.registry.build_config` + `generate_backtest_script`;
  the actual engine is only ever imported by the generated script itself, in
  its own subprocess.
- `Pipeline` now holds `self.runner = BacktestRunner(...)` instead of
  `self.engine = BacktestExecutor(...)` (which was only ever used for
  `_build_config`, now called directly via `step3_codegen.registry.build_config`
  from inside `BacktestRunner`) and delegates to it throughout
  `run_from_method_spec`/`_validate_with_repair`.
- **Fixed `DualTrackController._run_track()`**, previously
  `raise NotImplementedError` — i.e. `Pipeline.run_factor()`'s "run" stage
  (the numbered 8-stage pipeline) could never actually execute a backtest;
  only the separate `run_from_method_spec()` bypass path worked. `_run_track()`
  now calls `BacktestRunner.build_script()`/`.execute()` per track, with its
  own bounded repair loop on an execution failure (`MetaCoder.repair_plugin()`
  + a quick `AdversarialSandbox.validate()` re-check, then rebuild+retry,
  ≤`MAX_REPAIR_RETRIES`) — the same Step-5-fails→Step-3-repairs pattern
  `Pipeline.run_from_method_spec` already used for the single-track path,
  now available per-track for ablations/dual-track too. On exhaustion, a
  `status="failed"` RunRecord comes back instead of an unhandled exception.
- `DualTrackController.__init__` signature changed:
  `engine: BacktestExecutor` → `runner: BacktestRunner, meta_coder: MetaCoder,
  sandbox: AdversarialSandbox` (needs the repair-loop collaborators, not the
  engine). `run_experiment()`/`_run_track()` gained a required `snapshot_id`
  parameter (needed to build the script) — `Pipeline.run_factor()` gained the
  same required `snapshot_id` parameter to pass through (previously
  `run_factor()` had no way to reference registered data at all, a pre-existing
  gap this closes as a side effect of wiring step5→step6).
- Tests: new `tests/test_dual_track_controller.py` (fakes for
  runner/meta_coder/sandbox — no real subprocess/data/LLM): single-track happy
  path, multi-track (original+standardized+ablation) produces one RunRecord
  per track with distinct configs, execute-fails-then-repairs-then-succeeds,
  execute-always-fails-returns-failed-RunRecord.
- Updated `AGENTS.md` Module Map (re-added the `step5_backtest_runner/` row,
  `step6_dual_track_controller`'s role note updated).
- `python3 -m pytest tests/`: 128 passed / 28 skipped / 14 pre-existing
  pyarrow-related failures (same 14 as before this change; 4 new tests added).
- Rationale (why a real Step5 module, why fix the stub now, why the
  repair-loop boundary sits in step6 not step5) recorded in
  `docs/decision-log.md` (2026-07-22).

### Changed — `BacktestExecutor` engine library moved from `src/steps/step5_executor/` to `src/infra/backtest_engine/`
- `src/steps/step5_executor/` (the `BacktestExecutor` class, `steps.py`'s 12-step
  computation functions, `registry.py`'s `load_hooks`) was never itself "Step 5"
  as a pipeline action — the actual action ("generate script → validate →
  execute via subprocess") lives entirely in `src/pipeline.py`
  (`_build_script`/`_execute_script`, literally `subprocess.run([sys.executable,
  script_path])`). The directory name implied it *was* the step-5 action; it's
  really a shared computation library with no single "owning" step — grep-
  verified real callers are `pipeline.py` (orchestration),
  `step6_dual_track_controller` (ablation experiments), `app.py` (dashboard),
  `scripts/test_codegen.py`, the generated script's own runtime import, and 13
  unit-test files that exercise `steps.py` directly as a standalone computation
  library (same shape as `src/infra/data_layer`'s `DataLayer`/`CCMLinker`/
  `TimeAvailComputer`, which nobody would call "one step's private code").
- Moved (via `git mv`) `src/steps/step5_executor/` → `src/infra/backtest_engine/`
  unchanged (class/function names, file layout, and the step3_codegen ⇄
  backtest_engine relationship from the previous entry are all preserved —
  only the containing package moved). Updated every
  `from src.steps.step5_executor import ...` across `src/pipeline.py`,
  `src/steps/step6_dual_track_controller/`, `src/steps/step3_codegen/script_generator.py`
  (both its own import and the generated script's `_TEMPLATE` runtime import),
  `app.py`, `scripts/test_codegen.py`, and 14 test files to
  `from src.infra.backtest_engine import ...`.
- `src/steps/` now contains only genuine pipeline actions (extract, review,
  codegen, validate, dual-track, attribution) — "Step 5" has no corresponding
  numbered folder; it's the build+execute action in `pipeline.py`, consistent
  with how it actually works.
- Updated `AGENTS.md` Module Map (added `src/infra/backtest_engine/` row,
  re-pointed the "Step 5" row at `pipeline.py`'s build/execute methods) and
  `docs/architecture.md` §4.6 accordingly.
- No behavior change: `python3 -m pytest tests/` unchanged (124 passed / 28
  skipped / 14 pre-existing pyarrow-related failures, identical before/after).
- Rationale recorded in `docs/decision-log.md` (2026-07-22).

### Changed — codegen decision layer (`detect_hooks`/`build_config`/`STANDARD`) moved from `step5_executor` to `step3_codegen`
- `src/steps/step5_executor/registry.py` used to hold two unrelated kinds of
  logic bundled in one file: generation-time decisions (`STANDARD`,
  `detect_hooks`, `build_config`, `resolve_long_leg`/`resolve_short_leg`/
  `normalize_leg`, `resolve_sort_dims`) that are only ever called by
  `MetaCoder`/`script_generator` at plugin-generation time, and run-time hook
  loading (`load_hooks`) that only `BacktestExecutor.run_with_config()` itself
  calls. Because step3 could only reach the generation-time functions through
  `BacktestExecutor`'s classmethod/staticmethod wrappers
  (`BacktestExecutor._detect_hooks(spec)`, `engine._build_config(...)`),
  `step3_codegen` ended up importing the execution engine class just to reach
  two pure functions of a `MethodSpec` — backwards, since step5 is meant to
  *only execute the already-generated code*, never decide anything.
- New `src/steps/step3_codegen/registry.py`: the generation-time decision
  layer, verbatim (`STANDARD`, `FILTER_UNIVERSE_ALWAYS_HOOK_REASON`, `ev`,
  `detect_hooks`, `build_config`, `resolve_sort_dims`,
  `resolve_long_leg`/`resolve_short_leg`/`normalize_leg`). `step3_codegen`
  (`MetaCoder.generate_plugin` and `script_generator.generate_backtest_script`)
  now calls these directly — no more importing `BacktestExecutor` for this.
- `src/steps/step5_executor/registry.py` now holds only `load_hooks` — the one
  piece of "registry" logic the engine's own `run_with_config()` calls.
- `BacktestExecutor._detect_hooks()`/`_build_config()`/`_resolve_long_leg()`/
  `_resolve_short_leg()`/`_normalize_leg()` remain on the class as thin
  backward-compatible delegates to `step3_codegen.registry` (existing callers,
  including `tests/test_engine_hooks.py`'s extensive direct use of
  `BacktestExecutor._detect_hooks(spec)`, keep working unchanged) —
  `_load_hooks()` still delegates to the local (now-tiny) `registry.py`.
  This makes the dependency strictly one-directional: `step5_executor` imports
  `step3_codegen.registry` for these five delegate methods only;
  `step3_codegen` has zero imports of `step5_executor` (verified — no cycle).
- Updated `tests/test_multi_sort.py`'s `resolve_sort_dims` import and
  `docs/architecture.md` §4.6 accordingly.
- No behavior change: `python3 -m pytest tests/` unchanged (124 passed / 28
  skipped / 14 pre-existing pyarrow-related failures, same as before this move).
- Rationale recorded in `docs/decision-log.md` (2026-07-22).

### Added — validator hook contract check + execution smoke test on the ONE real script + Step-5 repair net
- `AdversarialSandbox` (step4) was purely static and only checked that
  `compute_signal` existed — it never executed the generated code and never
  checked hook functions, so a missing/misnamed hook (silently ignored at run
  time, making a non-standard factor run as standard) and any runtime error in
  `compute_signal` reached run time with no safety net.
- New `_check_hooks`: for every hook the MethodSpec required (`PluginRecord.hooks`),
  statically verifies the named function is defined with an argument count
  matching the canonical `HOOK_SIGNATURES` contract (imported from step3; no
  import cycle). New `ValidationReport.hooks_ok`.
- New `_check_executes`: **imports the exact standalone backtest script Step5
  will later execute** (built once via `Pipeline._build_script`, which wraps
  `script_generator.generate_backtest_script()`) in a subprocess with a
  timeout, and calls its `compute_signal` on a small real-data slice. Importing
  (not running) the script never triggers its `main()` (guarded by
  `if __name__ == "__main__":` in the template), so no full snapshot load or
  full `BacktestExecutor` run happens during validation — only the
  module-level `exec(compile(PLUGIN_CODE, ...))` line runs, defining
  `compute_signal` (and any hooks, left uncalled). This validates the SAME
  artifact byte-for-byte, instead of a separately hand-rolled "how do I exec
  the plugin" runner. **Lenient**: only a raised exception or a hang fails it
  (`executes_ok=False`); an empty/degenerate result on a thin slice is
  inconclusive (a warning, not a failure); no script/slice ⇒ skipped
  (`executes_ok` stays True, so `app.py`'s inline static-validate button and
  other 2-arg `validate()` callers are unaffected). Hooks are not executed
  here. New `ValidationReport.executes_ok`. The subprocess driver pickles the
  slice (no parquet/pyarrow dependency).
- `Pipeline._build_script`: the single place the standalone script is
  assembled from a plugin (replaces the old generate-and-run-in-one-call
  `_run_backtest_via_script`, split into `_build_script` (assemble, no
  execution) + `_execute_script` (write + subprocess-run an already-built
  script)). `_validate_with_repair` calls `_build_script` fresh on every
  attempt (including after a repair produces new plugin code) and validates
  THAT text; `run_from_method_spec` then calls `_execute_script` on the exact
  same built dict — so "what was validated" and "what gets executed" are
  always the same bytes, never independently regenerated.
- `Pipeline._build_validation_slice`: best-effort real-data slice for the smoke
  test, sliced **by permno keeping full month history** (preserves momentum /
  year-over-year lookbacks — never sliced by row/month), preferring permnos with
  non-null coverage in the signal's required columns; returns None (skips the
  smoke test) for multi-source signals or any build problem.
- `Pipeline.run_from_method_spec` now wraps `_execute_script` in a bounded
  run-with-repair loop: on a `RuntimeError`, feeds the run's stderr back into
  the same MetaCoder repair loop used for validation errors — which rebuilds
  AND re-validates the script from the new plugin code via
  `_validate_with_repair` before the next execution attempt, preserving the
  same-bytes invariant on every retry — and, when repair is
  exhausted/unavailable, persists a `status="failed"` RunRecord
  (`_make_failed_run_record`) instead of leaving an unhandled exception with a
  registered plugin and no run record. This is the guaranteed net that covers
  hook runtime bugs and full-data-only failures the (lenient, signal-only,
  slice-based) early smoke test can't.
- Rationale, alternatives, the security trade-off (subprocess+timeout, not a
  full sandbox), and the decision to keep C&Z ground truth out of the
  validation/repair loop (post-hoc evaluation only) are recorded in
  `docs/decision-log.md` (2026-07-21), with literature references
  (HumanEval arXiv:2107.03374, CodeT arXiv:2207.10397, Self-Debugging
  arXiv:2304.05128).
- Tests: `tests/test_sandbox_validation.py` builds the real script via
  `generate_backtest_script()` for each case (hook missing/wrong-arity →
  `hooks_ok=False`; good plugin passes; `compute_signal` raising →
  `executes_ok=False`; empty output → inconclusive warning, still passes; no
  script_text → check skipped; in-memory slices, no parquet).

### Changed — `BacktestEngine` renamed to `BacktestExecutor` (class + folder)
- Renamed the `src/steps/step5_engine/` class `BacktestEngine` → `BacktestExecutor`
  (naming clarity: "Engine" read as ambiguous next to `MetaCoder`'s actual code
  generation — `BacktestExecutor` makes explicit that this component only
  *executes* the fixed, pre-resolved lifecycle and never generates/decides
  anything itself). Also renamed the containing folder
  `src/steps/step5_engine/` → `src/steps/step5_executor/` (via `git mv`) so the
  module path matches the class name; updated every `from
  src.steps.step5_engine import ...` across `src/`, `tests/`, `scripts/`,
  `app.py` to `src.steps.step5_executor`. Updated all real references
  (imports, instantiations, docstrings, comments) plus current docs
  (`AGENTS.md` Module Map, `docs/architecture.md` §4.6, `plan.md`
  file-path pointers). Historical `CHANGELOG.md` entries and most of
  `plan.md`'s phase narrative (which predates this rename) were left
  referring to the old `BacktestEngine`/`step5_engine` names, consistent with
  this repo's existing convention of not rewriting historical records.
- Critically, this includes the `_TEMPLATE` string in
  `src/steps/step3_codegen/script_generator.py` that becomes the actual
  generated standalone backtest script's source code — a plain rename tool
  wouldn't catch this since it's a string literal, not a live symbol
  reference; verified separately.
- Left `src/steps/engine/` and `src/steps/reviewer/` (unreferenced duplicate
  leftovers from the step-numbering rename below) untouched — not imported
  anywhere; candidates for deletion in a follow-up cleanup.

### Changed — numbered `src/steps/` subfolders for pipeline order
- Renamed all `src/steps/` subpackages to include their pipeline-order prefix
  (matching the AGENTS.md Module Map step numbers), since Python module names
  can't start with a digit alone: `extractor` → `step1_extractor`,
  `reviewer` → `step2_reviewer`, `codegen` → `step3_codegen`,
  `validator` → `step4_validator`, `engine` → `step5_engine`,
  `controller` → `step6_dual_track_controller`, `attribution` →
  `step7_attribution`. `controller` is now a full top-level step (6, renamed
  after the `DualTrackController` class it contains) rather than `5b`, and
  `attribution` shifted to 7 to keep the sequence contiguous.
- Updated all `src.steps.*` imports and path references across `app.py`,
  `src/`, `scripts/`, `tests/`, and current docs (`AGENTS.md`, `plan.md`,
  `docs/architecture.md`) accordingly. Historical `CHANGELOG.md`/
  `docs/decision-log.md` entries referencing the old paths were left as-is.

### Added — decision log for paper write-up
- New `docs/decision-log.md`: append-only record of challenging/major decisions
  (context, options, rationale, empirical impact, trade-offs) to preserve the
  reasoning behind methodology and reference-deviation choices for the paper.
- `AGENTS.md` workflow now requires logging such decisions there.
- Backfilled the log with the BacktestEngine (fixed step order + standard/hook
  dispatch; ResearchDesign-as-config + daily-source-only) and DataLayer
  (layer-level lag, declarative panel assembly, concept→column dictionary)
  decisions and their rationale.

## [0.14.0] - 2026-07-20

### Added — CZ-import engine generality (plan.md CZ-import Phases A/B/C)
- Phase A — sample-period segmented metrics: `steps.compute_metrics` emits an
  optional nested `by_sample_period` (in-sample / between / post-publication),
  mirroring C&Z `sumportmonth`; top-level metrics byte-identical when no window
  supplied. Added `MethodSpec.publication_year`; `build_config` passes
  start/end/publication years. Core split factored into `_series_metrics` /
  `_sample_period_metrics`. Tests: `tests/test_sample_period_metrics.py`.
- Phase B — discrete sort form: `compute_breakpoints`/`assign_portfolios`
  branch on `config["cat_form"]` (mirrors C&Z `Cat.Form`), fixing a
  silent-wrong path where discrete categorical signals were quantile-cut.
  `continuous` (quantile) + `discrete` (one portfolio per distinct value,
  global sorted support) are STANDARD; anything else (incl. C&Z "custom") is
  left to a hook. `compute_long_short` uses min/max present portfolio for
  discrete. Tests: `tests/test_discrete_sort.py`.
- Phase C — rebalance-frequency-aware hold: `steps.merge_signal` caps the
  non-overlapping hold window at the rebalance step from
  `config["rebalance_frequency"]` (annual=12/quarterly=3/monthly=1) via
  `_rebalance_step_months`; annual unchanged (min(12,12)=12). Tests:
  `tests/test_calendar_rebalance.py`.

### Changed — data loading: locate by name + read realistic multi-source layout
- `BacktestEngine._load_data` locates the returns table by name
  (`<data_path>/raw/<returns_table>.parquet`, default `crsp_msf`; legacy
  `local/msf.parquet` fallback) and gains `config["returns_layout"]`:
  `"panel"` (default, pre-flattened file) or `"crsp_raw"` (assemble from the
  separate raw WRDS tables in `config["returns_dir"]`). Golden tests unchanged.
- `data_layer`: declarative `SOURCE_SCHEMA` (each source declares a ROLE:
  `base` / `pit_attrs` / `fold_last`) + one generic `assemble_panel()` builds
  the flat `[permno, yyyymm, ret, me, exchcd, shrcd, siccd (+dlret)]` panel
  from the separate CRSP tables (msf + msenames point-in-time + msedelist
  folded into last month). `build_crsp_monthly_panel` is a thin wrapper.
  Deterministic controlled infra (not an LLM hook), same declarative spirit as
  `DataDictionary`/`FilterOp`. Tests: `tests/test_crsp_raw_panel.py`.
- Removed a pre-existing unused `dataclasses.field` import in `data_layer`.

### Added — realistic WRDS-schema synthetic data for the 10 test papers
- `scripts/build_test_papers_synthetic_data.py` generates 16 tables to
  `data/synthetic_data/test_papers_v1/` mirroring REAL WRDS schemas (column
  names from `data/CZ code/.../DataDownloads/*.py` + OptionMetrics `vsurfd`).
  Faithful table separation (crsp_msf/msenames/msedelist/msedist) and REAL
  independent link tables (ccm_lnkhist, ibes_crsp_link, optionm_crsp_link) with
  realistic validity windows — nothing pre-joined. Includes rows to exercise
  universe filters, negative `prc`, missing returns, and delistings.

Full suite: 136 passed / 26 skipped; ruff clean.

## [0.13.15] - 2026-07-20

### Changed — Phase 8: prune hooks + docs (plan.md) — plan complete
- Reviewed `registry.detect_hooks()` holistically; confirmed it's already
  narrow after Phases 2.5-7's incremental pruning (no further changes to
  the function itself this phase — see plan.md Phase 8 for the reasoning,
  including why `missing_action != drop` is deliberately kept hooked rather
  than guessed at, verified against the real `sloan_1996_accruals` fixture).
- `src/steps/codegen/__init__.py`: added `HOOK_SIGNATURES`/`HOOK_RETURN_DOCS`
  entries for `apply_delisting_returns`/`neutralize_signal` (completing the
  documented contract to match `registry.load_hooks()`'s hookable-step
  list), each noting what the standard implementation already covers.
- `prompts/meta_coder/hook_system.md`: updated config-keys section
  (`universe_filters` DSL, `skip_month`) and noted most factors need zero
  hooks now.
- `docs/architecture.md`: rewrote §4.6 (module split into
  `engine/{__init__,steps,registry}.py`, current `STANDARD` sets, full
  current `detect_hooks()` table, "no longer unconditional" summary for
  filter_universe/multi-dim sort/return_combination/overlapping/
  Fama-MacBeth, updated standard step list) plus smaller fixes elsewhere
  that referenced the old "11 fixed steps"/"filter_universe always hooked"
  design.
- `plan.md`: marked all phases (0-8) complete with a status header.
- Verified: `pytest tests/` unaffected (115 passed / 26 skipped, no test
  changes needed this phase); `ruff check src/` shows only pre-existing
  issues in files untouched throughout this entire plan (`src/evaluation/`,
  `src/infra/llm.py`, `src/infra/trace.py`, `src/steps/attribution/`,
  `src/steps/reviewer/`) — zero new lint issues anywhere this plan touched.

**This completes the BacktestEngine Generalization Plan** (`plan.md`,
Phases 0-8). Summary of the whole effort: unified the previously-duplicated
in-process engine and generated-script code paths into one implementation;
split it into context/steps/registry modules with a uniform `Step` contract;
built a deterministic ResearchDesign layer (universe filter DSL, delisting
returns, neutralization scaffold) so sample-construction choices no longer
default to LLM hooks; generalized sorting to standard N-dim (characteristic
x size) double sorts; generalized return combination to all four standard
types (fixing a real single-leg bug along the way); added the standard
overlapping-cohort (Jegadeesh-Titman) holding model; added factor-model
alphas (CAPM/FF3/FF5 via `statsmodels`) and Sharpe ratio; added daily-source-
data loading + excess-return support; added a genuinely separate Fama-MacBeth
estimator via `linearmodels`; and finally confirmed the hook surface is now
narrow and honestly documented. 71 new tests added across 8 new test files,
all with hand-computed/exact-recovery expected values; zero regressions in
the pre-existing 44-test golden-number suite at every step.

## [0.13.14] - 2026-07-20

### Changed — Phase 7: Fama-MacBeth regression estimator (plan.md)
- `src/steps/engine/steps.py`: added `compute_fama_macbeth(merged, config)`
  — regresses `ret` on `signal` (+constant) period-by-period via
  `linearmodels.panel.FamaMacBeth`, averaging the slope over time with
  Fama-MacBeth SEs. Supports `config["winsorize_signal_pct"]` (deterministic
  clipping, not a hook). Raises `RuntimeError` if `linearmodels` isn't
  installed (it's the explicitly requested estimator, unlike
  `compute_factor_alphas`'s graceful `{}` degradation).
- `src/steps/engine/registry.py`: added `REGRESSION_WEIGHTED` to
  `STANDARD["portfolio_construction"]`; `build_config()` now resolves
  `config["estimator"]` (`"fama_macbeth"` when `construction_type ==
  "regression_weighted"`, else `"portfolio_sort"`).
- `src/steps/engine/__init__.py`: `run_with_config()` branches to
  `compute_fama_macbeth` entirely (skipping breakpoints/assign/returns/
  combine) right after `merge_signal` when `config["estimator"] ==
  "fama_macbeth"`; returns an empty `return_series` for this estimator (no
  portfolio-level series).
- `tests/test_fama_macbeth.py` (new, 5 tests): synthetic balanced panel
  recovering exact intercept/slope for positive/negative/near-zero true
  slopes; winsorization changes the recovered slope with an injected
  outlier; missing-data rows dropped correctly.
- `tests/test_engine_hooks.py`: updated the construction-type hook test
  (`FACTOR_MODEL_ALPHA` is now the "still non-standard" exemplar, since
  `REGRESSION_WEIGHTED` is standard).
- Verified: `pytest tests/` — 115 passed / 26 skipped (was 109/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.13] - 2026-07-20

### Changed — Phase 6: daily source data + excess returns (plan.md)
- `src/steps/engine/steps.py`: added `load_daily_msf(path)` — loads daily
  CRSP-shaped data and compounds it into the standard `yyyymm`-keyed monthly
  panel (`ret` = compounded monthly return, `me` from the last trading day
  of the month), so signals needing daily prices as input can flow through
  the existing monthly-rebalanced engine unchanged. Documented v1 scope
  limit: "daily source data, monthly output", not genuine daily-frequency
  rebalancing (deferred as an explicit ext, per the original plan). Added
  `apply_excess_returns(df, factors, config)` — subtracts `rf` when
  `config["return_basis"] == "excess"` and factor data with an `rf` column
  is supplied; no-op otherwise.
- `src/steps/engine/registry.py`: `build_config()` now resolves
  `return_basis` (default `"excess"`, the canonical default) and
  `return_frequency` (from `spec.reported_results.return_horizon`; not yet
  consumed by the standard steps, which are already frequency-agnostic given
  a `yyyymm`-keyed panel — this documents intent for now).
- `src/steps/engine/__init__.py`: `run_with_config()` now calls
  `apply_excess_returns` directly (not via `_dispatch()`/hooks, since it
  needs `ctx.factors`) right after `filter_universe`; a no-op for every
  existing test (none currently supply `factors`). Class docstring step
  list renumbered.
- `tests/test_daily_frequency.py` (new, 8 tests): hand-computed compounding
  across multiple trading days/permnos/months, last-trading-day `me`, and
  all `apply_excess_returns` branches.
- Verified: `pytest tests/` — 109 passed / 26 skipped (was 101/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.12] - 2026-07-20

### Changed — Phase 2: factor data + rich metrics (plan.md)
- `scripts/fetch_ff_factors.py` (new): fetches monthly FF3/FF5/UMD/rf via
  `pandas-datareader` (Ken French Data Library, no WRDS needed) and writes a
  parquet snapshot. Build-time only, never called at run time. Verified
  against the live Ken French site (network-reachable from this
  environment).
- `src/steps/engine/steps.py`: added `compute_factor_alphas(ls, factors,
  config)` — CAPM/FF3/FF5 alpha regressions via `statsmodels` OLS with
  Newey-West (HAC) SEs, gracefully returning `{}` if `statsmodels` isn't
  installed or `ls` has no single series (`full_portfolio_return` shape).
  Added `sharpe_ratio` directly to `compute_metrics` (no new dependency).
  Kept the existing hand-rolled `newey_west_var` unchanged for the primary
  t-stat (statsmodels HAC uses different normalization/df conventions —
  golden numbers stay byte-identical).
- `src/steps/engine/__init__.py`: `run()`/`run_with_config()` gained an
  optional `factors` parameter (mirrors Phase 0's `data` parameter); when
  given, `compute_factor_alphas`'s output is merged into the metrics dict.
- `src/steps/codegen/script_generator.py`: `generate_backtest_script()`
  gained an optional `ff_factors_path` parameter; the generated script loads
  it (if present at run time) and passes `factors=` through.
- `src/pipeline.py`: `_run_backtest_via_script()` now looks for
  `ff_factors.parquet` per-snapshot first, then falls back to the shared
  `data/local/ff_factors.parquet` — alphas are simply omitted when neither
  exists. `RunMetrics` mapping now populates `sharpe_ratio`/`alpha_capm`/
  `alpha_ff3`/`alpha_ff5` (fields already existed on the model, unused until
  now).
- `pyproject.toml`: updated `research` extra pins to the actually-installed/
  tested versions (`statsmodels==0.14.6`, `linearmodels==7.0`; superseding
  the earlier placeholder pins `0.14.2`/`6.0`).
- `tests/test_factor_alphas.py` (new, 10 tests): synthetic
  `ls_return = alpha + beta*mktrf` series (zero noise) so OLS recovers the
  exact alpha/beta; missing rmw/cma, no factors, too-few-months, and
  full_portfolio_return edge cases; `sharpe_ratio` correctness including a
  float-precision guard for near-constant series.
- **Deferred, documented as an honest gap, not attempted this pass**:
  `coverage`/`microcap_share` as populated metrics (need portfolio-level
  universe-size context not yet threaded to the metrics step); excess-vs-raw
  return basis for single-leg combination modes (moot for the long-short
  spread itself, since rf cancels in a long/short difference).
- Verified: `pytest tests/` — 101 passed / 26 skipped (was 91/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.11] - 2026-07-20

### Changed — Phase 5: overlapping-cohort holding as standard (plan.md)
- `src/steps/engine/steps.py`: added `merge_signal_overlap`,
  `compute_breakpoints_overlap`, `assign_portfolios_overlap`,
  `compute_returns_overlap`, `compute_long_short_overlap` — the standard
  Jegadeesh-Titman overlapping-cohort convention: each formation month opens
  a "cohort" held for `holding_period_months` (after `skip_month`); several
  cohorts can be simultaneously open; each computes its own breakpoints/
  portfolio assignment from its own formation-date signal cross-section; the
  reported series averages every open cohort's long-short spread each month.
- `src/steps/engine/registry.py`: `build_config()` now resolves
  `config["overlapping"]`. `detect_hooks()` no longer flags `merge_signal`
  for `overlapping_portfolios=true` alone; still flags it when combined with
  a multi-dimensional sort (not supported together in this v1).
- `src/steps/engine/__init__.py`: `_dispatch()` now routes `merge_signal`/
  `compute_breakpoints`/`assign_portfolios`/`compute_returns`/
  `compute_long_short` to their `_overlap` counterparts when
  `config["overlapping"]` is true (`_OVERLAP_STEPS`), checked before the
  Phase 3 multi-dim routing.
- `tests/test_overlapping_holding.py` (new, 8 tests): hand-built 2-stock/
  3-cohort scenario with a deliberately swapped cohort so multi-cohort
  months genuinely exercise per-cohort breakpoints and averaging across
  differing (not just repeated) compositions; every month's expected
  `ls_return` is hand-computed and matched exactly.
- `tests/test_engine_hooks.py`: updated overlapping-portfolio tests for the
  new (intentional) hook-detection contract.
- Confirmed safe: no existing e2e test exercises
  `jegadeesh_titman_1993_momentum` (fixture defines no hooks, isn't wired
  into any golden-number test).
- Verified: `pytest tests/` — 91 passed / 26 skipped (was 82/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.10] - 2026-07-20

### Changed — Phase 4: generalized return combination (plan.md)
- `src/steps/engine/steps.py`: `compute_long_short` now implements all four
  `ReturnCombinationType` values via `config["return_combination_type"]`
  (`extreme_group_spread`, `average_leg_spread`, `single_signal_portfolio_return`,
  `full_portfolio_return`). Kept the `compute_long_short`/
  `compute_long_short_hook` name for hook-contract backward compatibility
  (a rename to `combine_returns` is deferred to Phase 8). **Bug fix**:
  `single_signal_portfolio_return` was already marked STANDARD but the old
  implementation always computed a spread regardless of combination type —
  any such factor run through the standard path silently got a wrong
  result; fixed. `compute_metrics` now detects the `full_portfolio_return`
  shape (no `ls_return` column) and reports coverage diagnostics instead of
  a mean/t-stat for it.
- `src/steps/engine/registry.py`: added `AVERAGE_LEG_SPREAD`/
  `FULL_PORTFOLIO_RETURN` to `STANDARD["return_combination"]`; `build_config()`
  now resolves `config["return_combination_type"]`.
- `tests/test_return_combination.py` (new, 8 tests): all four combination
  modes + the metrics shape-detection.
- `tests/test_engine_hooks.py` / `tests/test_ball2016_e2e.py`: updated
  hook-detection expectations for the new (intentional) contract —
  `average_leg_spread`/`full_portfolio_return` no longer flagged; ball2016's
  multi-dim sort remains correctly hooked (Phase 3's heuristic doesn't
  recognize its variable names), with no runtime effect either way since its
  plugin's hand-written hooks always take priority.
- Verified: `pytest tests/` — 82 passed / 26 skipped (was 73/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.9] - 2026-07-20

### Changed — Phase 3: generalized N-dim sorting (plan.md)
- `src/steps/engine/steps.py`: added `compute_breakpoints_multi`,
  `assign_portfolios_multi`, `compute_returns_multi`,
  `compute_long_short_multi` (+ `_dimension_breakpoints`/`_assign_bucket`
  helpers) — a standard multi-dimensional sort supporting independent and
  dependent (conditional) breakpoints per dimension.
- `src/steps/engine/registry.py`: added `resolve_sort_dims()` (+
  `_sort_variable_column()`) mapping `portfolio_return.sorts[]` onto the
  engine's available columns (`signal`, `me`) — narrowly scoped to
  exactly-2-dimensional characteristic x size sorts. `build_config()` now
  resolves `config["sort_dims"]`. `detect_hooks()` no longer flags
  `compute_breakpoints`/`assign_portfolios` for multi-dim sorts that
  `resolve_sort_dims()` can map; anything it can't (3+ dims, or 2 dims
  without exactly one size-like dimension) still requests a hook.
- `src/steps/engine/__init__.py`: `_dispatch()` now routes
  `compute_breakpoints`/`assign_portfolios`/`compute_returns`/
  `compute_long_short` to their `_multi` counterparts when
  `config["sort_dims"]` has 2+ entries (`_MULTI_DIM_STEPS`); a plugin hook
  for the plain step name still takes priority over either variant.
- `tests/test_multi_sort.py` (new, 11 tests): hand-checkable 2x2
  independent-sort panel verifying exact bucket assignment, per-cell
  returns, and the averaged long-short spread; `resolve_sort_dims` mapping
  tests (2-dim resolves, unrecognized/degenerate/3-dim cases correctly
  don't).
- `tests/test_engine_hooks.py`: updated sort tests for the new (intentional)
  hook-detection contract — a resolvable characteristic x size double sort
  is no longer hooked; unresolvable multi-dim sorts still are.
- Confirmed safe for the ball2016 (2x3 double-sort) golden e2e test: its
  hand-written plugin already defines `compute_breakpoints_hook`/
  `assign_portfolios_hook`/`compute_long_short_hook`, and `_dispatch()`
  always prefers a loaded plugin hook over any standard function (single-
  or multi-dim) regardless of what `detect_hooks()`/`resolve_sort_dims()`
  predict — so this change is purely additive there too.
- Verified: `pytest tests/` — 73 passed / 26 skipped (was 60/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.8] - 2026-07-20

### Changed — Phase 2.5: deterministic ResearchDesign layer (plan.md)
- `src/steps/engine/steps.py`: added `apply_universe_filters` +
  `_apply_filter_op` (deterministic `FilterOp` DSL — eq/neq/in/not_in/
  between/not_between/gt/gte/lt/lte/nonmissing/nonzero/is_true/is_false),
  `apply_delisting_returns` (folds CRSP `dlret` into `ret`, no-op without a
  `dlret` column), and `neutralize_signal` (no-op scaffold, config
  `neutralization="none"` default; raises `NotImplementedError` for any
  other value pending a plugin hook). `filter_universe` now layers
  `universe_filters` DSL results + optional `microcap_exclude` (NYSE p20 ME
  threshold, off by default) on top of the existing baseline screen.
- `src/steps/engine/registry.py`: **removed the unconditional
  `filter_universe -> hook` rule** from `detect_hooks()` — filter_universe is
  standard by default now (a `filter_universe_hook` in a plugin still
  overrides it). `build_config()` now also resolves `universe_filters`
  (serialized from `spec.portfolio.universe_filters`), plus
  `apply_delisting_returns`/`microcap_exclude`/`neutralization` defaults.
  `load_hooks()`'s hookable-step list gained `apply_delisting_returns` and
  `neutralize_signal`.
- `src/steps/engine/__init__.py`: `run_with_config()` now dispatches
  `apply_delisting_returns` (after `load_data`) and `neutralize_signal`
  (after `merge_signal`); class docstring step list updated.
- `tests/test_engine_hooks.py`: updated for the new hook-detection contract
  (filter_universe no longer flagged); replaced
  `TestDetectHooksFilterUniverseAlwaysHook` with
  `TestDetectHooksFilterUniverseIsDeterministic`.
- `tests/test_research_design.py` (new): 14 unit tests for the DSL/delisting/
  neutralization/microcap functions directly.
- Confirmed safe for existing golden e2e tests: none of the
  accruals/ball2016/mvp fixture specs populate `universe_filters`, none of
  their synthetic CRSP fixtures have a `dlret` column, and none of their
  hand-written plugins define a `filter_universe_hook` (they already relied
  on the deterministic fallback) — so this is purely additive for them.
- Verified: `pytest tests/` — 60 passed / 26 skipped (was 44/26; all new
  tests, zero regressions). `ruff check` clean.

## [0.13.7] - 2026-07-20

### Changed — Phase 1: split BacktestEngine into context/steps/registry (plan.md)
- `src/steps/engine/__init__.py`: now orchestration-only. Added `Step`
  Protocol (documents the existing `(*args, config) -> DataFrame` contract
  that both standard steps and LLM hooks satisfy) and `BacktestContext`
  dataclass (carries config/hooks/data/merged/breakpoints/portfolios/
  returns/long_short/metrics/trace through one `run_with_config()` call, for
  traceability). `_dispatch()` now looks up standard steps via
  `getattr(steps, step)` instead of `getattr(self, f"_{step}")`.
- `src/steps/engine/steps.py` (new): the 9 standard step implementations as
  plain functions (`load_msf`, `apply_missing_policy`, `filter_universe`,
  `merge_signal`, `compute_breakpoints`, `assign_portfolios`,
  `compute_returns`, `compute_long_short`, `compute_metrics`,
  `newey_west_var`) — no class state, byte-identical logic to before.
- `src/steps/engine/registry.py` (new): `STANDARD`,
  `FILTER_UNIVERSE_ALWAYS_HOOK_REASON`, `detect_hooks()`, `build_config()`,
  `load_hooks()`, `resolve_long_leg`/`resolve_short_leg`/`normalize_leg` — the
  "what needs an LLM hook / how does a MethodSpec resolve into config" logic,
  moved out of `BacktestEngine` verbatim.
- `BacktestEngine`'s public API is unchanged: `_detect_hooks` (classmethod),
  `_build_config`, `_load_hooks`, `_resolve_long_leg`/`_resolve_short_leg`/
  `_normalize_leg` all still exist as thin delegations to `registry.py`, so
  every existing caller (`pipeline.py`, `script_generator.py`, `app.py`,
  `tests/test_engine_hooks.py`, etc.) is unaffected.
- Verified: `pytest tests/` unchanged at 44 passed / 26 skipped;
  `ruff check` clean on all three engine files.

## [0.13.6] - 2026-07-20

### Changed — Phase 0: unify BacktestEngine execution path (plan.md)
- `src/steps/engine/__init__.py`: added `BacktestEngine.run_with_config(signal,
  config, plugin=None, data=None)` — the 9-step lifecycle now lives in exactly
  one place, shared by `run()` (which builds `config` from a `MethodSpec`) and
  by the standalone scripts `script_generator.py` produces. Also added an
  optional `data` param to `run()`/`run_with_config()` so callers with a
  different data layout (e.g. a per-snapshot path) can load the MSF file
  themselves and pass it in, instead of going through `_load_data()`'s fixed
  `<data_path>/local/msf.parquet` assumption. Purely additive — no existing
  call site changes behavior (`data=None` preserves prior `_load_data()` path).
- `src/steps/codegen/script_generator.py`: rewrote the generated backtest
  script to be a thin wrapper — it now imports `BacktestEngine` and calls
  `run_with_config()` instead of re-implementing the 9-step lifecycle inline.
  Also replaced the inline CCM-linking/time_avail logic with
  `src.infra.data_layer.CCMLinker` + `TimeAvailComputer` (the same classes
  `DataLayer.get_signal_master_table()` uses), removing a second, separate
  duplication. Plugin code is now embedded as a `repr()`-escaped string
  constant (`PLUGIN_CODE`) and `exec()`'d once, then reused both to define
  `compute_signal`/hooks at module level and to build a `PluginRecord` for
  `BacktestEngine._load_hooks()` — so hook loading goes through the same code
  path as the in-process engine.
  - Dropped `std_monthly`/`sharpe_annual` and `ret_long`/`ret_short` from the
    generated script's output (the in-process `BacktestEngine._compute_metrics`/
    `_compute_long_short` never had them; confirmed via `tests/` grep that
    nothing reads these fields). Phase 2 will reintroduce Sharpe (and add
    alpha) properly as canonical engine metrics.
  - Accepted tradeoff (per plan.md "Decisions"): the generated script now
    depends on this repo being installed/importable (`from src...`) rather
    than being fully self-contained.
- **Real bug found & fixed while wiring this up**: this repo's editable
  install (`__editable__.factor_replication_agent-*.pth`) points
  `sys.path` at `<repo>/src` itself, NOT the repo root — so `from src.xxx
  import ...` only ever resolved when the process's cwd happened to be the
  repo root (e.g. `pytest` invoked from there), never via the editable
  install itself. Since Python puts a script's *own directory* on
  `sys.path[0]` (not the cwd), the generated script — written to
  `runs/backtest_scripts/` or a pytest `tmp_path` — could not `import src...`
  when run via `subprocess.run([sys.executable, script_path])`. Fixed by
  explicitly setting `PYTHONPATH` to the repo root for the subprocess in both
  `src/pipeline.py:_run_backtest_via_script()` and `app.py`'s equivalent
  helper (`os` import added to both).
- Verified: `pytest tests/` unchanged at 44 passed / 26 skipped before and
  after (same golden numbers for `test_accruals_e2e.py`,
  `test_ball2016_e2e.py`, `test_mvp_e2e.py`).

## [0.13.5] - 2026-07-20

### Added — Engine generalization plan + tooling decisions
- `plan.md` (repo root): phased plan to restructure `BacktestEngine` into a
  methodology-aware, config-driven engine with a single source of truth
  (unify in-process engine + `script_generator` inline duplicate). Covers a
  paper-agnostic canonical standard set (tiered v1/ext), a deterministic
  ResearchDesign layer (Phase 2.5) so sample construction/filters/timing/
  delisting/neutralization never fall to LLM hooks, and a four-layer design
  (SignalBuilder / ResearchDesign / Estimator / Evaluator).
- `plan.md`: tooling decision — adopt narrow statistical libs only
  (`linearmodels` for Fama-MacBeth, `statsmodels` for factor-alpha regressions),
  fetch Ken French FF/rf factors once via `scripts/fetch_ff_factors.py` and
  snapshot (no WRDS), use OSAP portfolios as the validation oracle. Explicitly
  reject qlib/zipline/backtrader/vectorbt/QuantLib/alphalens (they make
  empirical/execution decisions, violating the controlled-meta-coder constraint).
- `pyproject.toml`: added pinned `research` optional-dependency group
  (`statsmodels==0.14.2`, `linearmodels==6.0`) and build-time `pandas-datareader`
  in `dev` (never imported at run time).
- `plan.md`: added modularity approach (uniform `Step` Protocol + stateless
  pure-function steps + `BacktestContext` dataclass; classes only at
  polymorphism points) and a progressive file-split policy — Phase 1 splits the
  single engine file into 3 by concern (`__init__.py`/`steps.py`/`registry.py`),
  further files only when a layer gains a second implementation.

## [0.13.4] - 2026-07-20

### Changed — `merge_signal` is now hookable (overlapping portfolios)
- `_merge_signal()`'s standard implementation assumes non-overlapping ("clean calendar hold")
  portfolios: it takes the most recently formed signal value and holds it flat for
  `holding_period_months`. This silently produces the wrong result for papers with **overlapping**
  portfolios (e.g. Jegadeesh-Titman 1993 momentum, which forms a new cohort every month and blends
  returns across the several still-open cohorts) — `spec.signal.timing.overlapping_portfolios` was
  already extracted and stored on `MethodSpec` but nothing read it, and `merge_signal` wasn't even
  in the list of hookable steps
- `src/steps/engine/__init__.py`: added `"merge_signal"` to `_load_hooks()`'s hookable-step list;
  `_detect_hooks()` now flags `merge_signal` whenever `signal.timing.overlapping_portfolios` is
  true; `run()` now dispatches `merge_signal` through `_dispatch()` like every other step
- `src/steps/codegen/__init__.py`: added `HOOK_SIGNATURES`/`HOOK_RETURN_DOCS` entries for
  `merge_signal_hook(df, signal, config)` so MetaCoder knows what to generate
- Note: `tests/fixtures/method_specs/jegadeesh_titman_1993_momentum.resolved.methodspec.json`
  already has `overlapping_portfolios: true`, but its existing hand-written plugin
  (`tests/fixtures/plugins/jegadeesh_titman_1993_momentum.py`) has no `merge_signal_hook` — this
  fixture isn't exercised by any current e2e test, so nothing broke, but it's a pre-existing gap
  worth fixing before this fixture is wired into a golden-number test
- `tests/test_engine_hooks.py`: added coverage for the true/false/unspecified cases

## [0.13.3] - 2026-07-19

### Changed — `BacktestEngine` reordered for readability (no behavior change)
- `src/steps/engine/__init__.py`: reordered `BacktestEngine`'s methods to match reading order
  instead of implementation-history order. `run()` now comes right after `__init__` (it reads like
  a table of contents for the whole pipeline), followed immediately by the 9 standard step methods
  in the same order `run()` calls them, each with a one-line docstring naming the real-world
  backtesting question it answers. `_detect_hooks`/`_build_config`/`_load_hooks` (the "controlled
  codegen" internal machinery, not needed to understand what a backtest *does*) moved to a clearly
  labeled section at the bottom of the class
- Merged `_dispatch`/`_dispatch_assign` into a single `_dispatch(self, step, *args, config)` —
  `*args` covers both the 2-arg (`df`) and 3-arg (`df, breakpoints`) cases, so there's no longer a
  second near-duplicate dispatcher just because `assign_portfolios` needs one extra argument
- Purely a code move + one merge; `python3 -m pytest tests/` passes unchanged (41 passed, 26 skipped)

## [0.13.2] - 2026-07-19

### Changed — `BacktestEngine._detect_hooks()` no longer keyword-matches free text
- `_detect_hooks()` used to decide whether a factor needs a double-sort/multi-leg/non-standard
  universe hook by keyword-matching free-text `portfolio.filter`/`long_leg`/`short_leg`/`universe`
  strings (e.g. checking for `"double"`, `"average of"`, `"industry"`). Replaced with the same
  deterministic `STANDARD` set pattern already used for `breakpoint_source`/`weighting`/
  `missing_action`: compares typed `MethodSpec` fields against `STANDARD` sets drawn directly from
  the model's own enums
- `src/infra/models/method_spec.py`: promoted `reported_results.return_calculation.portfolio_return`
  from a loose `dict[str, Any]` to a typed `PortfolioReturnSpec` model (`construction_type`,
  `sorts: list[SortLegSpec]`, `return_combination: ReturnCombinationSpec`), and added
  `portfolio.universe_filters: list[UniverseFilterSpec]`. New enums `PortfolioConstructionType`,
  `ReturnCombinationType`, `FilterOp` mirror the vocabulary already documented in
  `prompts/extractor/methodspec_extractor.md`'s Allowed Values section. `_detect_hooks()` now flags
  `compute_breakpoints`/`assign_portfolios` when `len(portfolio_return.sorts) > 1`,
  `compute_returns` when `construction_type` isn't `characteristic_sort`, and `compute_long_short`
  when `return_combination.type` isn't `extreme_group_spread`/`single_signal_portfolio_return`
- `filter_universe` is now **unconditionally** LLM-generated instead of being gated by a `STANDARD`
  field-name comparison — comparing only `universe_filters[].field` against `{shrcd, exchcd,
  siccd}` duplicated `_filter_universe()`'s hardcoded logic in a second, independently-maintained
  location and couldn't express value-level differences (e.g. `shrcd in (10,11,12)` vs the
  standard implementation's `(10,11)` would have silently passed as "standard"). Every factor's
  `filter_universe_hook` is now generated by MetaCoder from `portfolio.universe_filters`/`universe`
  every time; `BacktestEngine._filter_universe()` remains only as a defensive fallback for runs
  with no plugin/hook
- Bug fix: `MethodSpec._normalize_breakpoint_source()` was collapsing extractor-stated
  `"conditional"`/`"paper_specific"` breakpoint sources to `"unspecified"`, which
  `BacktestEngine._build_config()` then silently defaulted to `"full_sample"` — a paper-stated
  conditional sort was being run as a standard full-sample sort with no hook and no warning.
  `BreakpointSource` enum gained `CONDITIONAL`/`PAPER_SPECIFIC` members; the normalizer now passes
  them through instead of discarding them
- `src/steps/reviewer/__init__.py`: new `ReviewGate._check_portfolio_structure_consistency()` acts
  as a safety net for the `sorts`/`construction_type`/`return_combination` checks above — that
  structured field is deeply nested and easy for extraction to leave unpopulated even when the
  shallower prose fields clearly describe a complex construction. This check blocks approval
  (`blocked_fields`) when `portfolio.filter`/`long_leg`/`short_leg` prose suggests a double-sort or
  multi-leg combination but `portfolio_return` is empty — instead of `_detect_hooks()` silently
  treating the spec as standard. (No equivalent check is needed for `universe_filters` since
  `filter_universe` is now unconditionally hooked.) Also added
  `portfolio.filter`/`portfolio.universe_filters` and the finer-grained `portfolio_return.*` dotted
  paths to `HIGH_IMPACT_FIELDS`, and fixed a `.get("weighting")` dict-style access in
  `_check_reported_results_contract()` that would have broken once `portfolio_return` became a
  typed model (now `.weighting` attribute access)
- Migrated 3 existing fixtures to populate the new structured fields so they keep triggering the
  same hooks as before: `tests/fixtures/method_specs/fama_french_1993_double_sort_hml`,
  `hou_xue_zhang_2015_investment`, `moskowitz_grinblatt_1999_industry_momentum`
  `.resolved.methodspec.json`
- New `tests/test_engine_hooks.py`: unit tests for every `_detect_hooks()` STANDARD branch
  (positive + negative case each) and the new `ReviewGate` safety-net check

## [0.13.1] - 2026-07-19

### Changed
- `app.py`: **Backtest & Experiments → Single Run** and **Pipeline — End to End** result displays now surface the generated standalone backtest script — a caption showing the `runs/backtest_scripts/{factor_id}_backtest.py` path it was saved to, plus a "View generated backtest script" expander with the full code and a download button. The script was already being generated and persisted there by `_run_backtest_via_script()`; it just wasn't shown in the UI, so it looked like only the MetaCoder page's separate "Generate Backtest Script" button produced a visible/downloadable script
- Also added a "Resolution Eval vs Ground Truth" file picker on the Review & Resolve page's Eval tab: dropdowns to manually choose which resolved MethodSpec (from `runs/method_specs/resolved/` or `tests/fixtures/method_specs/`) and which ground-truth factor to compare, instead of being limited to whatever was auto-matched from the current page session

## [0.13.0] - 2026-07-19

### Changed — folder structure redesign: all generated artifacts under `runs/`, gitignored
- New `runs/` directory (fully gitignored) is now the single home for every pipeline-run-generated
  artifact: `runs/method_specs/{unreviewed,reviewed,resolutions,resolved}/`, `runs/plugins/`,
  `runs/backtest_scripts/` (+ its `results/` scratch output), `runs/evidence/`. Previously these
  were scattered across `data/method_specs/*`, `data/plugins/`, `data/backtest_scripts/`, and a
  top-level `evidence/` — none of which were gitignored, so ad-hoc pipeline runs kept showing up
  as untracked files
- New `tests/fixtures/` directory (committed, NOT gitignored) holds the resolved MethodSpecs +
  plugins that golden-number tests and manual dashboard testing depend on:
  `tests/fixtures/method_specs/` (9 resolved specs) and `tests/fixtures/plugins/` (9 plugins,
  including asset_growth/accruals/ball2016 used by `tests/test_*_e2e.py`). These were previously
  committed under `data/method_specs/{resolved,test}/` and `data/plugins/`, which would have been
  silently lost had those folders been gitignored wholesale
- Removed the now-empty legacy `data/method_specs/{unreviewed,reviewed,resolutions,resolved,test,impl_config}/`,
  `data/plugins/`, `data/backtest_scripts/`, and top-level `evidence/` directories
- Updated all path references: `app.py` (path constants now `RUNS_DIR`-based +
  `FIXTURES_DIR`/`FIXTURE_METHODSPEC_DIR`/`FIXTURE_PLUGINS_DIR`; dropdowns on the Backtest &
  Experiments, Review & Resolve, MetaCoder, and Pipeline E2E pages now merge `runs/` output with
  `tests/fixtures/` reference specs/plugins, labeled `[fixture]`), `src/pipeline.py`
  (`Pipeline.__init__()` defaults: `evidence_path="./runs/evidence"`,
  `scripts_path="./runs/backtest_scripts"`), `scripts/extract_methodspecs.py`,
  `scripts/review_methodspecs.py`, `scripts/resolve_review_blocks.py`,
  `scripts/validate_methodspecs.py`, `scripts/test_codegen.py` (all default dirs now point into
  `runs/`, with `test_codegen.py` reading resolved specs from `runs/method_specs/resolved/` or
  `tests/fixtures/method_specs/`), and the 3 golden-number tests
  (`tests/test_mvp_e2e.py`, `tests/test_accruals_e2e.py`, `tests/test_ball2016_e2e.py`) now read
  their fixture spec/plugin from `tests/fixtures/`
- `.gitignore`: added `runs/`
- Docs updated to reflect the new layout: `docs/architecture.md` §5 file layout, `docs/roadmap.md`,
  `AGENTS.md` (new "Generated Artifacts vs. Fixtures" section)
- Verified: all 26 tests pass; the 3 persisted backtest scripts regenerated in
  `runs/backtest_scripts/` reproduce exact golden numbers (asset_growth/accruals: mean=1.004%,
  t=35.18; ball2016: mean=0.780%, t=35.18); `git status` confirms `runs/` no longer appears as
  untracked

## [0.12.1] - 2026-07-19

### Changed
- `app.py`: both Streamlit backtest entry points — **Backtest & Experiments → Single Run** and **Pipeline — End to End → Stage 6** — now use the same "generate script + execute via subprocess" flow as `Pipeline.run_from_method_spec()`, instead of calling `BacktestEngine.run()` in-process. New shared helper `_run_backtest_via_script()` generates `data/backtest_scripts/{factor_id}_backtest.py`, runs it with `subprocess.run([sys.executable, ...])`, and reads results back from the CSV/`.metrics.json` it writes. Uploaded CRSP files are materialized to `data/backtest_scripts/_uploads/` first since the generated script reads from a real path on disk. This closes the gap where the dashboard's in-process execution had drifted from the backend's audit-script-based execution
- Removed now-dead helpers `_get_or_register_synthetic_snapshot()` and `_call_compute_signal()` (no longer needed — the generated script does its own CCM/time_avail merge and `compute_signal()` call internally) and the unused `SYNTHETIC_SNAPSHOT_ID` constant
- Renamed the "Signal Input" radio option from "Compustat + CRSP (via DataLayer)" to "Compustat + CRSP (via generated script)" on both pages to reflect that the Compustat/CCM merge now happens inline inside the generated script, not through `DataLayer.get_signal_master_table()`

## [0.12.0] - 2026-07-19

### Changed
- `src/pipeline.py`: `Pipeline.run_from_method_spec()` no longer runs the backtest in-process via `BacktestEngine.run()`. It now generates a standalone backtest script (`generate_backtest_script()`), writes it to `data/backtest_scripts/{factor_id}_backtest.py`, and executes it via `subprocess.run([sys.executable, ...])`; results are read back from the CSV/`.metrics.json` the script itself writes. The generated script is now the actual source of every run's reported metrics, not just an optional export — every call leaves behind an independently re-runnable audit artifact. Data is NOT auto-generated by this method: the registered snapshot's `crsp_msf.parquet` (+ `compustat_funda.parquet`/`ccm_link.parquet` for Compustat-based signals) must already exist on disk
- `Pipeline.__init__()`: new `scripts_path` parameter (default `./data/backtest_scripts`) controlling where generated scripts are written — needed so tests can redirect script output to a tmp dir instead of overwriting the repo's real scripts (this was a real bug caught while implementing: running the test suite was clobbering `data/backtest_scripts/*.py` with paths into a since-deleted pytest tmp directory)
- `src/steps/codegen/script_generator.py`: `generate_backtest_script()` gained a `config_overrides` parameter so ablation-style overrides can be baked into the generated script's `CONFIG` dict, matching what the old in-process `BacktestEngine.run(config_overrides=...)` supported
- `tests/test_mvp_e2e.py`, `tests/test_accruals_e2e.py`, `tests/test_ball2016_e2e.py`: pass `scripts_path=str(tmp_path / "backtest_scripts")` to `Pipeline(...)` so test runs no longer mutate `data/backtest_scripts/`; all 3 golden-number tests still pass unmodified (subprocess execution reproduces byte-identical metrics to the previous in-process path)

## [0.11.1] - 2026-07-19

### Fixed
- `src/steps/codegen/script_generator.py`: `generate_backtest_script()` had the exact same bugs found and fixed in `app.py` earlier this session — it called `compute_signal(msf)` directly on raw CRSP monthly data with no Compustat/CCM wiring and no hook dispatch at all (not even `apply_missing_policy`), so any hook-dependent plugin (accruals winsorize, ball2016 double-sort) or Compustat-based plugin would silently produce wrong results or crash. Rewrote the generated script template to mirror `BacktestEngine.run()`'s real step order (`apply_missing_policy` → `filter_universe` → `merge_signal` → `compute_breakpoints` → `assign_portfolios` → `compute_returns` → `compute_long_short`) with a generic `_dispatch()` that uses any of the plugin's `*_hook` functions when present, and added an inline (dependency-free) CCM-link + accounting-lag merge for `signal_input_mode="compustat"` so Compustat-based factors work standalone, with no reliance on this repo's `src/` package
- `generate_backtest_script()`: new `signal_input_mode` ("compustat"/"crsp_only", auto-guessed from `spec.data.normalized_mapping` same as `app.py`'s heuristic), `compustat_data_path`, `ccm_link_path` parameters

### Added
- `data/synthetic_data/accruals_v1/` and `data/synthetic_data/ball2016_v1/`: persisted synthetic Compustat+CRSP+CCM snapshots for `sloan_1996_accruals` and `ball2016_cash_based_operating_profitability_factor` (previously only `mvp_v1/` existed, covering `cooper_gulen_schill_2008_asset_growth`)
- `data/backtest_scripts/{cooper_gulen_schill_2008_asset_growth,sloan_1996_accruals,ball2016_cash_based_operating_profitability_factor}_backtest.py`: standalone, independently-runnable backtest scripts for all 3 Phase 1 MVP factors, generated via the fixed `generate_backtest_script()` and verified (`python3 data/backtest_scripts/<factor>_backtest.py`) to reproduce the exact golden numbers from each factor's `tests/test_*_e2e.py`

## [0.11.0] - 2026-07-19

### Added
- `src/steps/engine/__init__.py`: New general `compute_long_short` hook point on `BacktestEngine`, following the exact same "predefined signature, AI-generated implementation" pattern as the existing 5 hooks (`filter_universe`/`compute_breakpoints`/`assign_portfolios`/`compute_returns`/`apply_missing_policy`) — the framework only adds a dispatch point + signature contract (`compute_long_short_hook(df, config) -> DataFrame[yyyymm, ls_return]`), it does not hardcode any factor-specific combination logic. `_detect_hooks()` now flags `compute_long_short` as needed when a spec's `portfolio.long_leg`/`short_leg` description implies a multi-leg average (e.g. "average of small-robust and big-robust..."), which a plain decile spread can't express
- `src/steps/codegen/__init__.py`: Added `compute_long_short` to `MetaCoder`'s `HOOK_SIGNATURES`/`HOOK_RETURN_DOCS` so future LLM-generated plugins for double-sort factors (e.g. Fama-French style RMW/HML) can have this hook generated automatically like the others
- `data/plugins/ball2016_cash_based_operating_profitability_factor.py`: Added `compute_breakpoints_hook` (2x3 independent sort: size via NYSE median, profitability via NYSE 30th/70th percentile), `assign_portfolios_hook` (portfolio ids 1-6, mirroring `fama_french_1993_double_sort_hml.py`'s existing double-sort pattern), and `compute_long_short_hook` (`0.5*(small-robust+big-robust) - 0.5*(small-weak+big-weak)`, i.e. the paper's actual RMW CbOP construction) using the new hook point. Also fixed a stray `import numpy as pd` (dead import, harmless but confusing — `compute_signal` never used numpy)
- `tests/synthetic_data/ball2016_synthetic_data.py` + `tests/test_ball2016_e2e.py`: Phase 1 MVP golden-number test for this factor — verifies `_detect_hooks()` flags `compute_long_short`, and that the full `Pipeline.run_from_method_spec()` chain (now exercising all 3 of this factor's hooks) matches an independently-derived closed-form long-short series

## [0.10.9] - 2026-07-19

### Fixed
- `app.py`, `scripts/run_extraction_eval.py`, `src/evaluation/gt_matcher.py`: Updated all references from the old `data/test_method_specs/` path to `data/test_method_specs_human_labeled/` (renamed outside this session — see 0.10.8's note). `GroundTruthMatcher` now correctly discovers all 26 ground-truth factors again instead of silently finding zero

## [0.10.8] - 2026-07-19

### Added
- `tests/synthetic_data/ab1998_synthetic_data.py`: Synthetic Compustat annual data for all 9 Abarbanell & Bushee (1998) fundamental signals (`AB1998_AQ`/`AR`/`CAPX`/`EQ`/`ETR`/`GM`/`INV`/`LF`/`SA`), one builder per factor matching `data/test_method_specs_human_labeled/AB1998_*.methodspec.json`'s `data.required_fields`. Reuses the existing 10-permno CRSP monthly panel and CCM link table from `asset_growth_synthetic_data.py`. Data-only (no plugins/resolved specs/golden-number tests) — the paper's actual return construction uses daily buy-and-hold abnormal returns against a size-decile benchmark, which this repo's monthly-only `BacktestEngine` doesn't implement. Verified all 9 factors merge cleanly (zero CCM link issues) through the real `DataLayer.get_signal_master_table()`

### Note
- `data/test_method_specs/` was renamed to `data/test_method_specs_human_labeled/` outside this session — code that still references the old path (`app.py`'s `TEST_SPECS_DIR`, `scripts/run_extraction_eval.py`'s `GT_DIR`, `src/evaluation/gt_matcher.py`'s `_SPECS_DIR`) has not been updated yet and will silently find 0 ground-truth files until fixed

## [0.10.7] - 2026-07-18

### Fixed
- `app.py` ("Pipeline — End to End" page): Stage 3 (Resolve) previously auto-applied `SENSIBLE_DEFAULTS` (or the LLM's `candidate_value`) to *every* ambiguous field indiscriminately, including ones `ReviewGate` flagged as `needs_human_confirmation` — and unconditionally set `codegen_ready=True`/`review_status="approved"` regardless, silently bypassing the human-in-the-loop gate the "Review & Resolve" page enforces. This contradicted the project's core "LLMs do not control empirical conclusions" constraint (AGENTS.md)

### Added
- `app.py`: `_e2e_run_stage_3_to_7()` — Stage 3–7 extracted into its own function so the page can pause between Stage 2 (Review) and Stage 3 (Resolve). When `review_result.field_notes` contains any `needs_human_confirmation` field, the pipeline now stops, persists the extract/review artifacts already produced, and renders an inline resolution form (same `st.selectbox` pattern as the "Review & Resolve" page) for each such field; only `approve_with_default`/`needs_llm_review` fields still get `SENSIBLE_DEFAULTS` automatically. Clicking "Continue Pipeline" applies the human's choices and resumes Stage 3 through Stage 7. `data/method_specs/resolutions/{factor_id}.resolution.json` now records each decision's `decision_type` (`human_confirmed` vs `sensible_default`) instead of just a resolved-field count

## [0.10.6] - 2026-07-18

### Fixed
- `app.py`: LLM-generated plugins for factors other than `cooper_gulen_schill_2008_asset_growth` / `sloan_1996_accruals` reference Compustat/CRSP columns the bundled synthetic snapshot doesn't have (e.g. `drc`, `xacc`, `rect` for a Ball 2016 profitability variant), which surfaced as a raw, unhandled `KeyError` traceback when running "Compustat + CRSP" signal input in either the "Pipeline — End to End" or "Backtest & Experiments" pages. Added `_call_compute_signal()` — wraps every `compute_signal()` call and turns a missing-column `KeyError` into an actionable message (which column is missing, what columns *are* available, and that the bundled synthetic data only covers those two factors' fields) instead of an opaque crash. This is an expected data-coverage gap, not a bug in the plugin or the pipeline — see `tests/synthetic_data/` for the pattern to extend synthetic coverage to another factor, or `docs/roadmap.md` Phase 4 for wiring in a real WRDS snapshot

## [0.10.5] - 2026-07-18

### Added
- `tests/synthetic_data/accruals_synthetic_data.py`: Synthetic Compustat data (`act`/`che`/`lct`/`dlc`/`dp`/`at`) for `sloan_1996_accruals`, reusing the CRSP monthly panel, CCM link table, and long-short golden numbers from `asset_growth_synthetic_data.py` unchanged (same 10 permnos/decile mapping, since the CRSP-return side of the golden numbers doesn't depend on which Compustat fields feed the signal)
- `tests/test_accruals_e2e.py`: Second Phase 1 MVP golden-number end-to-end test (curated/resolved MethodSpec → `DataLayer.get_signal_master_table()` → real generated plugin's `compute_signal()` → `BacktestEngine.run()` (dispatching `apply_missing_policy` to the plugin's hook, since `missing_action='winsorize'` is non-standard) → `Pipeline.run_from_method_spec()` → `EvidenceStore`); also asserts `BacktestEngine._detect_hooks()` correctly flags this spec's non-standard missing-value policy

### Fixed
- `data/plugins/sloan_1996_accruals.py`: `compute_signal()`'s per-formation-date winsorization and `apply_missing_policy_hook()`'s per-month winsorization both used `df.groupby(col, group_keys=False).apply(fn)` where `fn` returned the full group DataFrame — in the current pandas version this silently drops the grouping column (`time_avail_m`/`yyyymm`) from the result, causing a downstream `KeyError` the first time this plugin was actually run end-to-end (it had never been exercised by a test before). Rewrote both as per-column `.groupby(col)[col].transform(...)` clips, which cannot drop columns and are the more idiomatic pandas pattern for this operation anyway

## [0.10.4] - 2026-07-18

### Fixed
- `app.py` ("Pipeline — End to End" page): the one-click pipeline previously never persisted any intermediate artifact to disk — the extracted MethodSpec, review report, resolved MethodSpec, and generated plugin all only lived in `st.session_state` and vanished on refresh, unlike the individual Extractor/Review & Resolve/MetaCoder pages which each save explicitly. Now each stage writes its artifact: Stage 1 → `data/method_specs/unreviewed/{factor_id}.methodspec.json`, Stage 2 → `data/method_specs/reviewed/{factor_id}.review_report.json`, Stage 3 → `data/method_specs/resolutions/{factor_id}.resolution.json` + `data/method_specs/resolved/{factor_id}.resolved.methodspec.json`, Stage 4 → `data/plugins/{factor_id}.py`

### Added
- `app.py`: `_ensure_synthetic_data()` — auto-generates the bundled synthetic demo data (via the same builder as `scripts/build_synthetic_data.py`) the first time it's needed, instead of just hiding the "Bundled synthetic demo data" option when `data/synthetic_data/` doesn't exist yet. Wired into both the "Backtest & Experiments" Single Run tab and the "Pipeline — End to End" page's backtest stage

## [0.10.3] - 2026-07-17

### Added
- `app.py`: Added `claude-sonnet-5` as a selectable model for both the `copilot` and `claude` LLM providers in the sidebar's Model dropdown
- `src/infra/llm.py`: Added `claude-sonnet-5` to `CopilotCLIClient.SUPPORTED_MODELS` and `ClaudeCodeCLIClient.SUPPORTED_MODELS`

## [0.10.2] - 2026-07-17

### Fixed
- `app.py` ("Backtest & Experiments" → Single Run tab): the page previously called `compute_signal(msf)` directly on the raw CRSP monthly parquet for every plugin — this only ever worked for CRSP-only signals, and even those were broken because `msf` has a `yyyymm` column, not the `time_avail_m` column every plugin's `compute_signal()` actually expects. Compustat-based plugins (`cooper_gulen_schill_2008_asset_growth` and 5 others) raised `KeyError` since `msf.parquet` has no accounting fields at all. Added a "Signal Input" mode toggle: **Compustat + CRSP (via DataLayer)** builds the SignalMasterTable via `DataLayer.get_signal_master_table()` (CCM link + accounting lag), **CRSP monthly only** aliases `yyyymm` → `time_avail_m` before calling `compute_signal()`; default mode is auto-guessed from the resolved spec's `data.normalized_mapping`
- `app.py` ("Pipeline — End to End" page, Stage 6 Backtest): applied the same fix as the Single Run tab — added the "Signal Input" mode toggle (with an `"Auto-detect"` option using the same heuristic) and "Bundled synthetic demo data" data source; Stage 6 now builds the SignalMasterTable via `DataLayer` for Compustat-based specs instead of always feeding raw `msf` straight into `compute_signal()`. Stage 6 results are now persisted as an auditable `RunRecord` (track=`dashboard_e2e`) via `EvidenceStore.save_run()`
- `app.py`: added a "Bundled synthetic demo data" data-source option (backed by `data/synthetic_data/`, registered on the fly as a `DataLayer` snapshot) so the page has usable data out of the box — previously `data/local/msf.parquet` didn't exist in the repo and the Run button stayed disabled unless a file was manually uploaded
- `app.py`: Single Run results are now persisted as an auditable `RunRecord` via `EvidenceStore.save_run()` (track=`dashboard_single_run`) instead of living only in `st.session_state` and disappearing on refresh

## [0.10.1] - 2026-07-17

### Changed
- Renamed `data/method_specs/curated/` to `data/method_specs/unreviewed/` — "curated" was ambiguous (it holds the pre-`ReviewGate` draft MethodSpec regardless of whether it was hand-written or LLM-extracted; "unreviewed" states its actual pipeline stage). Updated all references: `app.py` (`CURATED_METHODSPEC_DIR` → `UNREVIEWED_METHODSPEC_DIR`, UI labels), `scripts/extract_methodspecs.py` (`DEFAULT_OUTPUT_DIR`), `scripts/review_methodspecs.py` (`DEFAULT_INPUT_DIR`), `scripts/validate_methodspecs.py` (`DEFAULT_METHODSPEC_DIR`), `docs/architecture.md` and `docs/roadmap.md` file-layout references
- `scripts/run_extraction_eval.py`: New batch extraction-accuracy script — for each of the 10 papers in `data/test_papers/paper_spec_mapping.json`, extracts all mapped factors (one `extract_batch()` call per multi-factor paper) and scores field-by-field against `data/test_method_specs/` ground truth (normalizing the ground truth's curated-annotation schema through `MethodSpec.model_validate()` first, fixing a comparison bug where most fields silently failed to line up between the two schemas and produced bogus >100% coverage numbers); writes `data/eval_history/extraction_eval_10papers.json`

## [0.10.0] - 2026-07-17

### Added
- `tests/synthetic_data/asset_growth_synthetic_data.py`: Deterministic synthetic CRSP/Compustat/CCM data (10 permnos, 3 fiscal years, 24 months) with an independently-derived closed-form golden `mean_monthly_return`/`t_stat`/`n_months` for the `cooper_gulen_schill_2008_asset_growth` factor
- `scripts/build_synthetic_data.py`: Persists the synthetic data as parquet under `data/synthetic_data/mvp_v1/` (`crsp_msf`, `compustat_funda`, `ccm_link`) and `data/synthetic_data/local/msf.parquet`
- `tests/test_mvp_e2e.py`: Phase 1 MVP end-to-end test — curated/resolved MethodSpec → `DataLayer.get_signal_master_table()` → real generated plugin's `compute_signal()` → `BacktestEngine.run()` → `Pipeline.run_from_method_spec()` → `EvidenceStore`; asserts output metrics match the golden numbers, not just reproducibility
- `src/pipeline.py`: `Pipeline.run_from_method_spec()` — the curated-MethodSpec MVP chain from `docs/roadmap.md` Phase 1 (approved MethodSpec → MetaCoder/repair loop if no plugin supplied → Sandbox → DataLayer signal master table → plugin `compute_signal()` → BacktestEngine → EvidenceStore), bypassing extraction and `DualTrackController` which are out of scope for the MVP chain; helper `_validate_with_repair()` and `_compute_signal()`

### Fixed
- `src/infra/data_layer/__init__.py`: Implemented `CCMLinker.merge()` (point-in-time gvkey→permno resolution honoring `linkdt`/`linkenddt` and `linkprim='P'` priority, with `link_issues` logging) and `CCMLinker.check_coverage()`; implemented `TimeAvailComputer.compute_time_avail_m()` (fiscal date + lag → YYYYMM) and `TimeAvailComputer.build_signal_master_table()`; `DataLayer.get_signal_master_table()` now loads the CCM link table and wires the two together instead of raising `NotImplementedError`
- `src/steps/engine/__init__.py`: `_resolve_long_leg()`/`_resolve_short_leg()` now match `long_leg`/`short_leg` and `implied_factor_direction` text by substring (`"low"`/`"high"`) instead of exact equality — resolved MethodSpecs store descriptive text like `"lowest asset-growth decile"`, which previously always fell through to the `short`-leg default and silently inverted the long-short spread

### Changed
- `pyproject.toml`: Added explicit `pyarrow>=14.0` dependency (required by `pandas.read_parquet`/`to_parquet`, used throughout `DataLayer` and the new synthetic data)

## [0.9.0] - 2026-06-29

### Changed
- **Major restructure of `src/`** — pipeline steps and infrastructure separated into clear namespaces:
  - `src/steps/extractor/` — Step 1: Paper → MethodSpec (was `src/extractor/`)
  - `src/steps/reviewer/` — Step 2: Review + Resolution (was `src/review_gate/`)
  - `src/steps/codegen/` — Step 3: MethodSpec → Plugin (was `src/meta_coder/`)
  - `src/steps/validator/` — Step 4: Syntax/Schema/Leak check (was `src/sandbox/`)
  - `src/steps/engine/` — Step 5: Backtest (was `src/engine/`)
  - `src/steps/controller/` — Step 5b: Multi-track experiments (was `src/controller/`)
  - `src/steps/attribution/` — Step 6: Gap decomposition (was `src/attribution/`)
  - `src/infra/models/` — Pydantic models (was `src/models/`)
  - `src/infra/data_layer/` — Data loading + CCM (was `src/data_layer/`)
  - `src/infra/evidence/` — Evidence store + RunRegistry (was `src/evidence/`)
  - `src/infra/registry/` — Plugin registry (was `src/registry/`)
  - `src/infra/llm.py` — LLM client (was `src/llm.py`)
  - `src/infra/trace.py` — Pipeline tracer (was `src/trace.py`)
  - `src/infra/pdf_mapper.py` — PDF tools (was `src/pdf_mapper.py`)
- All imports across app.py, scripts/, tests/, and internal modules updated to new paths

## [0.8.1] - 2026-06-29

### Added
- `prompts/meta_coder/signal_plugin_system.md`: Signal plugin generation system prompt (extracted from inline code)
- `prompts/meta_coder/hook_system.md`: Hook function generation system prompt
- `prompts/meta_coder/repair_plugin.md`: Plugin repair prompt template (with `{errors}` and `{code}` placeholders)
- `src/evaluation/gt_matcher.py`: `GroundTruthMatcher` — matches agent-extracted specs to ground truth via PDF filename → factor_id → field comparison; supports exact factor_id, variable_name, formula similarity, and substring matching
- `data/test_method_specs/spec_paper_mapping.json`: Mapping file (26 entries) with forward index (factor→paper) and reverse index (filename→factors)

### Changed
- `src/meta_coder/__init__.py`: Prompts now loaded from `prompts/meta_coder/*.md` files via `_load_prompt()`; inline string fallback preserved for backward compatibility

## [0.8.0] - 2026-06-29

### Added
- `src/trace.py`: `PipelineTracer` — lightweight timestamped event logger for pipeline execution; used by E2E page and Trace & Logs page
- `app.py`: Complete 7-page Streamlit dashboard redesign:
  - **Pipeline — End to End** — one-click PDF-to-backtest with progress bar, stage-by-stage expandable output, feedback loop indicators, and trace
  - **Extractor** — PDF upload + extraction + eval vs ground truth (`data/test_method_specs/`), batch eval across all 26 ground truth specs
  - **Review & Resolve** — 3 tabs (Review / Resolution / Eval); resolution eval compares resolved values against ground truth
  - **MetaCoder** — preserved from v0.7; load spec → hook detect → generate → sandbox → backtest script
  - **Backtest & Experiments** — 3 tabs (Single Run / Dual-Track [disabled] / Ablation); config overrides, cumulative+monthly charts
  - **Attribution** — load evidence runs, run ablation attribution, contribution breakdown bar chart, anomaly detection
  - **Trace & Logs** — 3 tabs (Run Registry / Evidence Browser / Pipeline Trace); download artifacts and trace JSON

### Changed
- `app.py`: Ground truth source changed from SignalDoc.csv to `data/test_method_specs/*.methodspec.json` (26 human-curated specs)
- `app.py`: Removed SignalDoc dependency for evaluation; all eval now uses field-level comparison against test MethodSpecs

### Removed
- `app.py`: Batch Evaluation and Evaluation History pages (replaced by per-page Eval panels)

## [0.7.0] - 2026-06-29

### Added
- `src/meta_coder/script_generator.py`: `generate_backtest_script()` — generates a standalone runnable Python script combining signal plugin code + inline backtest engine + MethodSpec-derived config; output is a single file executable with `python3 <script>.py`
- `app.py`: New **Backtest** page in Streamlit dashboard — select a plugin and resolved MethodSpec, load CRSP data (local or uploaded parquet), configure overrides (n_quantiles, breakpoint source, weighting, holding period, long leg, skip month), run BacktestEngine, display key metrics (mean return, t-stat, annualized return), cumulative and monthly return charts, signal diagnostics, and download results as CSV/JSON
- `app.py`: MetaCoder page step 8 "Generate Backtest Script" — after sandbox passes, generates a self-contained backtest script with download/save options

### Changed
- `app.py`: Sidebar navigation now includes "Backtest" between MetaCoder and Batch Evaluation pages
- `app.py`: Sidebar status shows Sandbox ✅ and Backtest ✅

## [0.6.9] - 2026-06-21

### Added
- `src/data_layer/__init__.py`: `DataDictionary.normalize_fields(required_fields)` — maps paper concept field names to physical parquet column names via `_CONCEPT_MAP`; three-pass resolution (exact field name → exact source_detail → substring, ≥4-char keys only to avoid false positives like "at" matching inside "compustat")
- `data/method_specs/resolved/cooper_gulen_schill_2008_asset_growth.resolved.methodspec.json`: `data.normalized_mapping` populated (`total_assets→at`, `monthly_return→ret`, `market_equity_june→me`, `listing_exchange→exchcd`, `sic_code→siccd`); unspecified fields resolved in spec (`breakpoint_source=full_sample`, `weighting=vw`, `missing_action=drop`); 4 new `resolution_log` entries

### Changed
- `src/meta_coder/__init__.py`: `generate_plugin(spec)` — no longer accepts `impl_config`; column mapping read from `spec.data.normalized_mapping`; `_detect_hooks(spec)` call drops `impl_config` param
- `src/engine/__init__.py`: `_detect_hooks(spec)` — `impl_config` param removed; reads only from resolved MethodSpec fields; `_build_config()` reads entirely from spec
- `scripts/test_codegen.py`: Removed step 2.5 (impl_config load); step 2 now shows `normalized_map` from `spec.data.normalized_mapping`; step 2.5b `_detect_hooks(spec)` call updated
- `docs/architecture.md` (v9): Removed step 2.5 and §4.3 impl_config as separate pipeline stage; integrated column mapping population into step 2 (Resolution Applier bullet points); `_detect_hooks()` signature updated throughout; §10 status: Meta-Coder and BacktestEngine both marked ✅ fully implemented

### Removed
- `data/method_specs/impl_config/`: No longer needed — all implementation decisions and column mappings live in the resolved MethodSpec (`spec.data.normalized_mapping` + resolved fields + `resolution_log`)

## [0.6.8] - 2026-06-21

### Added
- `src/engine/__init__.py`: Full BacktestEngine implementation — `STANDARD` dict per step, `_detect_hooks(spec, impl_config)` classmethod, `_build_config()` with impl_config override support, all 7 standard step implementations (`_apply_missing_policy`, `_filter_universe`, `_merge_signal`, `_compute_breakpoints`, `_assign_portfolios`, `_compute_returns`, `_compute_long_short`, `_compute_metrics` with Newey-West t-stat), hook loader via `exec()`, and hook dispatch in `run()`
- `src/meta_coder/__init__.py`: `HOOK_SYSTEM_PROMPT`, `HOOK_SIGNATURES`, `HOOK_RETURN_DOCS` constants; `_generate_hooks(spec, impl_config, hooks_needed)` method for LLM hook function generation; `generate_plugin()` now runs two-phase flow: (1) `_detect_hooks()` to identify non-standard steps, (2) generate `compute_signal()` + hook functions in separate LLM calls, then concatenate into single plugin file; `PluginRecord.hooks` field populated with `{step: fn_name}` map
- `src/models/plugin.py`: `hooks: dict[str, str]` field on `PluginRecord` mapping step name → hook function name in plugin code

### Changed
- `scripts/test_codegen.py`: Added step 2.5b showing `_detect_hooks()` output before MetaCoder call; added hooks display in plugin summary

## [0.6.7] - 2026-06-21

### Changed
- `docs/architecture.md` (v8): Added standard-vs-hook design for BacktestEngine:
  - §2 Design Principles: updated to reflect "LLM generates signal + hooks"; added "standard vs hook driven by MethodSpec" principle
  - §3 Pipeline: step 3 Meta-Coder now shows two-phase flow (hook detection → LLM codegen)
  - §4.4 Meta-Coder: documented two-phase generation (Phase 1: `_detect_hooks`; Phase 2: LLM generates `compute_signal` + per-step hook functions only when step exceeds standard set)
  - §4.7 BacktestEngine: rewrote as "Standard Set + Hook mechanism" — defines `STANDARD` dict per step, `_detect_hooks()` logic, hook dispatch pattern, and attribution guarantee
  - §10 status: Meta-Coder marked partial (signal ✅, hooks ⏳); BacktestEngine split into standard steps (WIP) and hook dispatch (not yet)

## [0.6.6] - 2026-06-21

### Added
- `data/method_specs/impl_config/cooper_gulen_schill_2008_asset_growth.impl_config.json`: First impl_config — maps paper field names to physical column names (`total_assets→at`, `monthly_return→ret`, etc.) and pins unspecified implementation decisions (`breakpoint_source=full_sample`, `weighting=vw`, `quantiles=10`, `accounting_lag_months=6`, `missing_action=drop`)
- `scripts/test_codegen.py`: End-to-end test script for pipeline steps 2.5→3→4; loads impl_config and resolved MethodSpec, calls MetaCoder via `codex` CLI (gpt-5.4), runs Future-Leak Scan, saves plugin to `data/plugins/`

### Changed
- `src/meta_coder/__init__.py`: `generate_plugin()` now accepts optional `impl_config: dict` parameter; `_build_prompt()` injects `column_mapping` and `implementation_decisions` as explicit prompt sections when provided

## [0.6.5] - 2026-06-21

### Changed
- `docs/architecture.md` (v8): Simplified pipeline based on pilot-stage decision — Adversarial Sandbox collapsed to Future-Leak Scan only (syntax/schema/reproducibility checks removed as redundant; only `shift(-`/`.future`/`lead(` pattern scan retained); Plugin Registry deferred to post-pilot; §3 pipeline diagram, §3.1 feedback loop table, §4.5, §5 file layout, and §10 status table updated accordingly

## [0.6.4] - 2026-06-21

### Changed
- `docs/architecture.md` (v7): Comprehensive update to align with actual codebase state:
  - §3 pipeline diagram made non-linear — added explicit feedback loop arrows (Sandbox→MetaCoder, Sandbox→ReviewGate, ReviewGate→Extractor, Attribution→ReviewGate)
  - Added §3.1 Feedback Loops table (was referenced by `src/pipeline.py` but absent from the document)
  - §4 module details: added §4.5 Adversarial Sandbox (full validation suite, not just future-function scan), §4.6 Plugin Registry, renumbered Data Layer and BacktestEngine; §4.4 MetaCoder now documents `repair_plugin()`
  - §5 file layout: updated to match actual `src/` structure (added sandbox, registry, controller, attribution, evidence, evaluation, pipeline.py, pdf_mapper.py, app.py, evidence/ output dir); fixed `data/method_specs/` subdirs (resolutions/ exists, impl_config/ does not); marked `data/local/` as not yet created
  - §6 end-to-end example: replaced non-existent `scripts/run_factor_backtest.py` with actual entry points (Streamlit dashboard + `Pipeline` class usage + real CLI scripts)
  - §7 DualTrackController: noted `HXZ_STANDARD_CONFIG` in `src/controller/__init__.py`
  - §9 Attribution: added anomaly detection thresholds (sign flip, >50% gap)
  - §10 replaced "Currently Deferred" stub list with accurate implementation status table (✅ implemented / 🚧 WIP / ⏳ not yet built)

## [0.6.3] - 2026-06-20

### Added
- `src/meta_coder/__init__.py`: Implemented `MetaCoder.generate_plugin()` — builds a structured prompt from the resolved MethodSpec (formula, data fields, timing, missing policy) and calls the configured LLM client to generate a signal plugin; also implemented `repair_plugin()` for bounded syntax-only repairs (max 3 attempts)
- `app.py`: New **MetaCoder** sidebar page — loads resolved MethodSpecs, shows approval gate with human-override checkbox for specs that passed human review but not full rules re-review, generates plugin code via LLM, runs AdversarialSandbox validation inline, supports auto-repair loop (up to 3 attempts), and saves plugins to `data/plugins/`
- `app.py`: Sidebar MetaCoder status now reflects plugin count from `data/plugins/`

### Changed
- `app.py`: Sidebar navigation now includes "MetaCoder" between single-paper and batch-evaluation pages
- `app.py`: "Apply All Resolutions" now marks `codegen_ready=true` and `review_status=approved` whenever there are no hard structural errors (missing formula, empty required_fields, etc.), regardless of remaining ambiguous_field metadata flags — the human's explicit approval action supersedes the rules re-review's field-level blocks
- `app.py`: MetaCoder approval gate is now strict (no force-approve bypass) since resolved JSONs are written with correct approval status

## [0.6.2] - 2026-06-20

### Added
- `app.py`: Single-paper upload flow now persists extracted PDF text to `data/paper_text_cache/<pdf_stem>.txt` for auditability and downstream reuse alongside the existing Streamlit session cache
- `app.py`: Single-paper workflow can now resume from a saved curated `*.methodspec.json` or an uploaded MethodSpec JSON, with optional paper-text cache selection for continuing LLM review after a restart
- `scripts/extract_methodspecs.py`: New CLI for extracting MethodSpecs from single PDFs or PDF directories, with batch support, provider/model selection, and JSON or text summaries
- `src/llm.py`: Added Claude Code CLI support, CLI binary auto-detection helpers, streaming callbacks for CLI-backed providers, and token-usage estimation helpers for Codex/Copilot/Claude responses
- `src/review_gate/__init__.py`: Added prompt-backed `review_with_llm()` flow that converts raw LLM audit JSON into structured `ReviewResult`
- `AGENTS.md`: Added explicit Streamlit startup instructions and port-selection guidance for local dashboard use

### Changed
- `app.py`: Extractor UI now records and displays the saved paper-text cache path after upload, while keeping review/extraction on the same already-extracted text instead of re-running `pymupdf`
- `app.py`: LLM review and LLM-assisted resolution now reload paper text from the saved cache path before falling back to session memory, so saved artifacts survive Streamlit restarts
- `app.py`: When review starts from an extractor session that still has PDF bytes but no cached text in memory, reviewer now auto-extracts and re-caches paper text for non-Claude providers instead of forcing a manual re-upload
- `app.py`: Review artifact saving now serializes nested `EvidenceCitation` objects correctly, and the UI distinguishes review-execution failures from artifact-persistence failures
- `scripts/review_methodspecs.py`: LLM review mode now delegates to `ReviewGate.review_with_llm()` and supports the `claude` provider instead of hand-building review JSON prompts inline
- `src/extractor/__init__.py`: Extraction now loads prompts from `prompts/extractor/methodspec_extractor.md` when present, captures token usage, accepts optional PDF bytes, and first attempts direct rich-schema `MethodSpec.model_validate()` before falling back to the legacy flat-schema mapper
- `src/llm.py`: Codex and Copilot CLI execution moved to streaming `Popen` flows so the UI can surface incremental output while preserving JSON-mode parsing
- `src/llm.py` and `src/review_gate/__init__.py`: JSON-mode parsing now tolerates explanatory preambles before the first JSON object, and review results map legacy `patch_existing_json` remediation output to the current `resolve_existing_json` schema value
- `tests/test_extractor.py`: Relaxed evaluation summary assertion to accept either `80%` or `80.0%`

### Removed
- `data/method_specs/curated/`, `data/method_specs/reviewed/`, `data/method_specs/resolved/`, and `data/method_specs/resolutions/`: Removed the previous bulk curated/reviewed AssetGrowth-era artifacts from the working tree, leaving the new `cooper_gulen_schill_2008_asset_growth_vw.methodspec.json` curated sample and moving `AssetGrowth.methodspec.json` under `data/test_papers/`
- `tmp/assetgrowth_paper.txt` and `tmp/assetgrowth_review_input.txt`: Removed temporary review-input scratch files from the repo working tree

## [0.6.1] - 2026-06-20

### Added
- `scripts/review_methodspecs.py`: New `--backend llm` mode that can call configured CLI/API LLM backends (`codex`, `copilot`, or `openrouter`) for paper-aware MethodSpec review
- `scripts/review_methodspecs.py`: Local PDF text extraction for LLM review via `pdftotext -layout`, with `pymupdf` fallback when `pdftotext` is unavailable
- `scripts/review_methodspecs.py`: LLM review output now writes both structured `review_report.json` for downstream resolution tooling and human-readable `*.llm_review.md`

### Changed
- `scripts/review_methodspecs.py`: Added prompt/paper/backend CLI flags (`--prompt`, `--paper`, `--papers-dir`, `--provider`, `--model`) so a single command can trigger external CLI-backed review against the original paper

## [0.6.0] - 2026-06-20

### Added
- `AGENTS.md`: Canonical shared instruction file for Codex, Claude, Copilot, and other coding agents with compact project rules and model-selection guidance
- `scripts/validate_methodspecs.py`: Validates curated MethodSpecs against the current schema — reports missing required fields, type errors, and enum violations
- `scripts/review_methodspecs.py`: Runs curated MethodSpecs through Review Gate — produces per-factor `review_report.json` and `reviewed.methodspec.json` under `data/method_specs/reviewed/`
- `scripts/resolve_review_blocks.py`: Interactive CLI to resolve Review Gate blocked fields — reads a `review_report.json`, prompts field-by-field with smart suggestions (candidate values, field-specific option lists), writes a `resolution.json` and final `resolved.methodspec.json`
- `data/method_specs/reviewed/`: Reviewed MethodSpecs and review reports for 25+ factors (AB1998 suite, AnAngBaliCakici2013 volatility factors, Ball2016 profitability factors, BlitzHuijMartens residual momentum, EisfeldtPapanikolaou OMK, FrazzinPedersen BAB, KoHsuLi innovation factors, LohWarachka streak factors, MertonStrategicDefault suite)
- `data/method_specs/resolutions/AssetGrowth.resolution.json`: Resolution decisions for AssetGrowth blocked fields
- `data/method_specs/resolved/AssetGrowth.resolved.methodspec.json`: Final resolved MethodSpec for AssetGrowth, ready for codegen
- `docs/roadmap.md`: Full project roadmap covering MVP workflow, MethodSpec quality, meta-coder, backtest engine, and production data integration phases
- `ReviewGate._get_field_value()`: Best-effort dotted-path lookup with path-alias resolution for populating review context
- `FieldReviewNote`: Extended with `current_value`, `candidate_value`, `empirical_impact`, and `evidence` fields so resolvers have full context without re-reading the spec

### Changed
- `CLAUDE.md` and `.github/copilot-instructions.md`: Converted to thin compatibility wrappers that point agents to `AGENTS.md`
- `src/models/method_spec.py`: `PatchLogEntry` renamed to `ResolutionLogEntry` (terminology shift: "resolve" not "patch")
- `src/models/method_spec.py`: `RemediationMode.PATCH_EXISTING_JSON` renamed to `RemediationMode.RESOLVE_EXISTING_JSON`
- `src/models/method_spec.py`: `SignalSpec.sign` and `MethodSpec.sign` changed from `int = 1` to `Optional[int] = None` — unspecified sign is now explicitly nullable rather than defaulting to positive
- `src/models/method_spec.py`: `PortfolioSpec.implied_factor_direction`, `ReturnCalculationSpec.input_return`, `ReportedResultsSpec.comparison_policy`, `spreads`, and `t_stats` types widened to `T | dict[str, Any]` to tolerate structured LLM output without validation errors
- `src/models/method_spec.py`: Added `normalize_curated_schema` `model_validator` to coerce legacy curated JSON into the current schema on load
- `src/review_gate/__init__.py`: `ReviewGate.review()` now populates full field context (current value, candidate value, empirical impact, evidence) in each `FieldReviewNote`
- `src/review_gate/__init__.py`: `ReviewResult.remediation_mode` default updated to `resolve_existing_json`
- `src/models/__init__.py`: Exports `ResolutionLogEntry` instead of `PatchLogEntry`
- `docs/architecture.md`: Updated to reflect current module boundaries and MVP workflow

## [0.5.4] - 2025-05-28

### Added
- `data/gold_standard/paper_selection_rationale.md`: Records why the 10-paper annotation set was chosen, the extraction-difficulty coverage dimensions, and a recommended drop order if reducing scope
- `src/llm.py`: Model selection support — Codex CLI now uses `-m` flag for model (gpt-5.5, gpt-5.4); Copilot CLI supports claude-opus-4-6, claude-sonnet-4-6, gpt-5.4
- `app.py`: Model selector dropdown in sidebar — dynamically shows available models based on selected provider
- `src/models/method_spec.py`: `reported_return_spread` and `reported_t_stat` fields on MethodSpec — stores paper's reported long-short return and t-stat for Attribution comparison
- `src/extractor/__init__.py`: Extraction schema now extracts `reported_return_spread` and `reported_t_stat` from paper text in a single LLM call
- `data/gold_standard/gold_standard.csv`: Human-annotated ground truth CSV template (24 fields) with AssetGrowth example row
- `data/gold_standard/README.md`: Field documentation and annotation guidelines for gold standard
- `scripts/csv_to_gold_standard.py`: Converter from flat CSV annotations to nested JSON matching MethodSpec schema
- `data/gold_standard/gold_standard.csv`: Added `return_type`, `data_frequency`, `annotator_notes` columns (now 27 fields)
- `data/gold_standard/gold_standard.csv`: Added `_source` columns for each substantive field — annotators can record where in the paper each value was found
- `data/gold_standard/README.md`: Added "Where to Find" column to field documentation table

### Changed
- `data/gold_standard/paper_selection_rationale.md`: Reordered the printable 10-paper list by annotation priority (High/Medium/Low) from highest to lowest
- `data/gold_standard/paper_selection_rationale.md`: Added a printable full-name list for all 10 selected papers (author-year-title) to support annotation logging and reporting
- `src/llm.py`: `CodexCLIClient` default model changed from "default" to "gpt-5.4"
- `src/llm.py`: `CopilotCLIClient` default model changed from "opus" to "claude-opus-4-6" (full name)
- `src/llm.py`: `CodexCLIClient._create()` now ignores caller's model param (e.g. hardcoded "gpt-4o") and always uses the configured default model
- `app.py`: Both `create_llm_client` calls now pass selected model

## [0.5.3] - 2025-05-28

### Added
- `src/llm.py`: `CopilotCLIClient` — uses VS Code's bundled Copilot CLI binary via subprocess with your GitHub Copilot subscription; supports LLM mode (tools disabled) and agent mode (tools enabled)
- `app.py`: LLM Provider selector in sidebar — choose between codex, copilot, or openrouter at runtime
- `src/extractor/__init__.py`: `extract_batch()` method — extracts all factors from the same paper in a single LLM call (saves tokens and API calls for multi-factor papers)
- `src/extractor/__init__.py`: `RateLimitExhausted` exception — raised immediately on rate limit so caller can checkpoint and stop (no retry, since quota recovery takes hours)
- `app.py`: Checkpoint/resume system for batch evaluation — saves progress after each paper to `data/eval_history/_checkpoint.json`; on next run, skips already-completed papers
- `app.py`: "Clear Checkpoint" button to start fresh

### Changed
- `app.py`: Batch evaluation uses `extract_batch()` — one LLM call per paper instead of one per factor
- `app.py`: On rate limit, stops gracefully with saved progress instead of retrying
- `app.py`: Paper selection adds "First N PDFs" mode with slider (e.g., first 30, 50 papers)

## [0.5.2] - 2025-05-27

### Added
- `scripts/convert_papers_to_md.py`: PDF→Markdown conversion script using pymupdf4llm (preserves headings, tables, equations); outputs to `data/papers_md/`
- `src/evaluation/helpers.py`: `extract_pdf_text()` now prefers pre-converted MD files from `data/papers_md/`, falls back to PyMuPDF extraction
- `src/extractor/__init__.py`: LLM extraction now requires `reasons` field — a dict mapping each extracted field to the verbatim quote from the paper supporting that value
- `src/extractor/__init__.py`: `ExtractionResult.reasons` field stores per-field citations from LLM output
- `src/evaluation/helpers.py`: New shared module with evaluation utilities (no pytest dependency) — used by both `app.py` and tests

### Changed
- `app.py`: Per-Factor Results table columns renamed from "Expected"/"Actual" to "Ground Truth"/"Extracted", added "Reason" column showing paper citations
- `app.py`: Imports evaluation utilities from `src.evaluation.helpers` instead of `tests.test_extractor` (fixes Streamlit import error)
- `src/evaluation/helpers.py`: `build_field_details()` now accepts optional `reasons` dict and includes reason in each field detail
- `tests/test_extractor.py`: Refactored to import shared utilities from `src.evaluation.helpers` instead of duplicating code

## [0.5.1] - 2025-05-25

### Changed
- `src/pdf_mapper.py`: Complete rewrite — replaced complex author-based matching with simple Paper title matching from SignalDoc.csv (55/56 PDFs → 67 factors mapped)

### Added
- `tests/test_pdf_mapper.py`: Comprehensive test suite for pdf_mapper (33 tests) — covers normalization, title loading, integration with real data, cache behavior, edge cases, and known mapping spot checks

## [0.5.0] - 2025-05-25

### Added
- `src/pdf_mapper.py`: New content-based PDF-to-factor mapping utility — reads first page of each PDF via PyMuPDF, matches author last names against SignalDoc entries using word-boundary regex, year matching, and confidence scoring
- `src/pdf_mapper.py`: Caching system (`.pdf_factor_map_cache.json`) to avoid re-scanning unchanged PDFs
- `src/pdf_mapper.py`: `build_pdf_factor_map()`, `get_factor_to_pdf()`, `invalidate_cache()` public API

### Changed
- `tests/test_extractor.py`: Replaced hardcoded `PDF_FACTOR_MAP` dict with dynamic mapping via `src.pdf_mapper.build_pdf_factor_map()` — works with any PDF filenames

### Fixed
- `scripts/download_papers.py`: Rewrote CrossRef search to use all author last names + journal keywords (instead of just first author + partial description), with scored result validation (threshold 0.5) to avoid matching wrong papers
- `scripts/download_papers.py`: Added `_validate_crossref_item()` scoring (author match 40%, year 30%, journal 20%, title presence 10%) to rank and filter search results
- `scripts/download_papers.py`: Added post-download `validate_pdf_content()` that checks PDF contains expected author names in raw text

### Added
- `scripts/download_papers.py`: `--force` flag to re-download papers even if file already exists
- `scripts/download_papers.py`: `--revalidate` mode to check all existing PDFs contain expected author names without downloading
- `scripts/download_papers.py`: Logs DOI found for each paper during download; reports invalid PDFs to `data/papers/invalid_pdfs.txt`

### Changed
- `app.py`: Replaced tabs with left sidebar navigation (pipeline steps); batch eval page now renders independently without `st.stop()` interference
- `app.py`: Batch Evaluation page — added multi-select paper picker (radio: "All PDFs" / "Select specific PDFs"), progress status text, and explicit "Run Evaluation" button
- `app.py`: Fixed `use_container_width` deprecation; progress now shows "3/60 done — processing X.pdf → FactorID ..."
- `app.py`: Added "Evaluation History" page — reports auto-saved to `data/eval_history/` after each batch run; browse, view full details, download, or delete past reports from the sidebar
- `app.py`: Added per-field accuracy summary table in batch eval results
- `src/extractor/__init__.py`: `evaluate_extraction()` now treats unspecified/None/N/A ground truth as correct (no penalty)
- `tests/test_extractor.py`: `_build_field_details()` also treats unspecified ground truth as correct
- `tests/test_extractor.py`: Complete redesign — removed all mock LLM tests, replaced with real LLM (codex CLI) + real PDF extraction + SignalDoc.csv ground truth evaluation pipeline
- `FACTOR_PDF_MAP` now maps 80+ SignalDoc factors to 33 actual PDFs in `data/papers/`, generated by matching SignalDoc Authors+Year to PDF filenames
- Added `FactorEvalResult` and `EvalReport` dataclasses for structured evaluation output (JSON + text summary)
- Added `TestRealExtraction` class: parametrized tests using real PDFs + real LLM calls
- Added `TestFullEvaluation` class: full eval suite producing `data/eval_output/` reports
- Added `TestEvaluationLogic` class: unit tests for evaluation helpers (no LLM needed)
- Added `run_evaluation()` standalone function for programmatic/CLI evaluation
- Eval output: `data/eval_output/extraction_eval_report.json` + `extraction_eval_summary.txt`
- Restructured mapping to `PDF_FACTOR_MAP` (PDF → factor list) as primary, with `FACTOR_TO_PDF` reverse lookup; `test_full_eval_report` iterates by PDF to avoid redundant reads
- `SemanticExtractor` docstring clarified: one paper may define multiple factors; each extract() call produces exactly one MethodSpec for one factor_id

### Added
- Expanded eval fields: `formula_keywords` (Compustat/CRSP variable keyword matching from Detailed Definition), `sample_start_year`, `sample_end_year`, `rebalance_frequency` (derived from Portfolio Period), `accounting_lag` (derived from Start Month)
- Scoring system: `PASS_THRESHOLD=80`, `_compute_score()`, `FactorEvalResult.score`/`.passed`, `EvalReport.passed_count`/`.failed_count`/`.pass_rate`/`.avg_score`/`.compute_aggregates()`
- `_extract_formula_keywords()` helper with `_KNOWN_VARIABLES` set for Compustat/CRSP variable detection
- `SemanticExtractor._values_match()` now supports `field_key="formula_keywords"` for partial-credit keyword matching (>=50% threshold)
- `app.py`: Added "Batch Evaluation" tab — select individual PDF or run all, progress bar, aggregate metrics (avg score, pass rate), per-factor expandable results with field detail tables, JSON report download

## [0.4.0] - 2025-05-25

### Changed
- `src/extractor/__init__.py`：`required_fields` 从简单字符串列表改为结构化格式 `[{field, source, description}]`，LLM 直接从 paper 提取数据源（不再假设只有 Compustat/CRSP），解析后自动填充 `SignalSpec.field_sources`

### Removed
- `src/extractor/__init__.py`：删除 `_get_data_fields_context()` 及 user template 中的 data_fields 占位符，LLM 自行从 paper 识别数据源和字段名
- `tests/test_extractor.py`：删除 `TestDataFieldsContext` 测试类（对应方法已移除）

### Fixed
- `src/extractor/__init__.py`：Rules 中 stock_weight 说明补充 "capped_vw" 选项

### Added
- `README.md`：添加 "Key Enums Explained" 子章节（WeightingRule / EvidenceSource / EmpiricalImpact 用途说明 + pipeline 关联）
- `README.md`：添加 "What a Good MethodSpec Looks Like" 章节（BM factor 完整示例 + 评判标准 + 常见错误）
- `src/models/method_spec.py`：为所有 class 和 enum 添加详细 docstring（含 SignalDoc 统计数据、示例、pipeline 角色说明）
- `app.py`：Streamlit dashboard，PDF-first 流程（上传 PDF → 自动匹配 SignalDoc factor → 提取 → ground truth 对比）
- `src/llm.py`：LLM client 抽象层，支持 Codex CLI（默认 model 5.5）和 OpenRouter 两种后端
- `streamlit>=1.30`, `pymupdf>=1.24` 加入 pyproject.toml dependencies
- `match_factor_from_text()` 自动从 PDF 文本匹配 SignalDoc factor（基于 author names + year + keywords）
- 移除 sidebar factor selector，改为 PDF 上传驱动的自动识别 + 手动确认
- Semantic Extractor 完整实现：paper-first LLM extraction pipeline (`_call_llm_extract`, `_build_method_spec_from_llm`)
- Extraction system prompt (`EXTRACTION_SYSTEM_PROMPT`) 和 user template，结构化 JSON 输出
- `_get_data_fields_context()` 提供 data dictionary context 给 LLM
- `_parse_enum()` 安全 enum 解析（大小写不敏感 + fallback）
- `_values_match()` fuzzy 比对用于 evaluation
- Ambiguity auto-tagging：LLM 返回 "unspecified" 字段自动标记为 `AmbiguousField`
- `tests/test_extractor.py`：22 个单元测试覆盖 MethodSpec 构建、enum 解析、evaluation metrics、端到端提取、data dictionary context
- `TestSignalDocGroundTruth`：7 个集成测试使用真实 SignalDoc.csv 作为 ground truth，验证 evaluation pipeline（BM perfect score、negative sign factors、batch pilot、imperfect detection、全量 parse）

### Changed
- `src/models/method_spec.py`：每个 Enum class 新增 `choices(allow_unspecified)` classmethod，返回 schema 可选值字符串；model class 的 `EXTRACTION_SCHEMA` 直接引用 enum 的 `choices()` 而非内联拼接
- `src/models/method_spec.py`：每个 model class 新增 `EXTRACTION_SCHEMA: ClassVar[dict]` 类变量，定义该 class 在 LLM 提取 prompt 中对应的 schema 字段和可选值
- `src/extractor/__init__.py`：`_build_extraction_schema()` 改为从各 class 的 `EXTRACTION_SCHEMA` 组合，不再手写 schema 描述
- `src/extractor/__init__.py`：将 EXTRACTION_SYSTEM_PROMPT 中的硬编码 JSON schema 重构为 `EXTRACTION_SCHEMA_FIELDS` 字典 + `_build_schema_json_block()` 函数，从 model enum 类自动生成 schema 描述
- **LLM output schema 重构**：对齐 SignalDoc.csv 字段结构
  - `weighting` → `stock_weight` (ew/vw)
  - `breakpoint_quantiles` → `ls_quantile` (float: 0.1=decile, 0.2=quintile, 0.3=tercile)
  - 新增 `filter` (stock-level filters, e.g. abs(prc)>5, exchcd%in%c(1,2))
  - 新增 `cat_form` (continuous/discrete)
  - 新增 `sign` (+1/-1 预测方向)
  - 新增 `detailed_definition` (文字描述 formula)
  - 新增 `sample_start_year` / `sample_end_year`
- `MethodSpec` model 新增字段：`detailed_definition`, `cat_form`, `sign`, `sample_start_year`, `sample_end_year`
- `PortfolioSpec` 新增 `filter` 字段；`BreakpointSpec` 新增 `ls_quantile`
- `EXTRACTION_SYSTEM_PROMPT` 重写：新增 sign/ls_quantile/filter/cat_form 解释和提取指导
- `_build_method_spec_from_llm()` 支持 `stock_weight`、`ls_quantile`→quantiles 转换、`filter` 解析
- `evaluate_extraction()` core_fields 扩展为 8 个核心字段，field_map 支持所有 SignalDoc 字段
- `_parse_signaldoc_row()` (app.py + tests) 新增 `sign`, `ls_quantile`, `filter`, `cat_form` 解析
- `TestExtractEndToEnd`: 替换 mock LLM 为真实 codex CLI 调用，5 个 E2E 测试验证完整提取流程
- `_build_method_spec_from_llm()`: 添加 `_safe_int()` 处理 LLM 返回 "unspecified" 或非数字字段
- `app.py` 结果页面重构：LLM 提取结果与 SignalDoc ground truth 左右并排显示，取消 tabs 布局

### Removed
- `app.py`: 移除 mock LLM 选项和 `_build_mock_response()` 函数，Streamlit 现在仅使用真实 codex CLI 提取

## [0.3.0] - 2026-05-24

### Added
- `scripts/download_papers.py`：从 Semantic Scholar 下载 SignalDoc.csv 中引用的论文 PDF（open-access），下载不到的记录到 `data/papers/missing.txt`
- `README.md`：项目概述、架构图、目录结构、数据源表、设计决策、引用格式
- `src/evaluation/` 模块：`Evaluator` 类实现三层评估（extraction vs SignalDoc、signal vs C&Z firm-level、portfolio vs C&Z LS returns）
- `TimeAvailComputer` 类：Data Layer 中统一处理 `time_avail_m` point-in-time 可用日期
- `DataLayer.get_signal_master_table()` 方法：构建 [permno, time_avail_m] 面板供 plugin 使用
- `MetaCoder.load_few_shot_examples()` 方法：从 OSAP Predictors/ 加载 few-shot 示例代码
- Meta-Coder 新增 `reference_code_path` 参数和 `PLUGIN_OUTPUT_COLS` schema 定义

### Changed
- **Semantic Extractor** 文档明确：SignalDoc.csv 不作为输入（避免信息泄漏），仅用于 post-hoc evaluation
- **Meta-Coder** 重写：明确 plugin 输出格式为 `[permno, yyyymm, signal]`；lag 由 Data Layer 处理（time_avail_m），plugin 只做 formula computation
- **Data Layer** 新增 `TimeAvailComputer`，`DataLayer` facade 增加 `time_avail` 和 `get_signal_master_table`

## [0.2.0] - 2026-05-24

### Changed
- **MethodSpec** 重构为嵌套结构（`signal.*`, `portfolio.*`, `extraction_sources`, structured `ambiguous_fields`），匹配 docs/architecture.md Section 4.2 YAML schema
- **Semantic Extractor** 改为 multi-source triangulation 策略（C&Z → OSAP → paper fill-in → ambiguity tagging），新增 `ExtractionMetrics` 评估
- **Review Gate** 新增 Review Decision Matrix（evidence × impact 分类）、`Disposition` 枚举、LLM Reviewer picky 策略、sensible defaults、structured `FieldReviewNote`
- **Pipeline** 新增完整 feedback loop / backtrack 逻辑（Sandbox→Meta-Coder repair, Sandbox→Review empirical, Review→Extractor, Attribution→Review anomaly），max backtrack depth=3
- **BacktestEngine** `_build_config` 适配新 MethodSpec 属性名
- **DualTrackController** HXZ config 和 ablation map 更新字段名，新增 `universe` ablation switch

### Added
- `src/data_layer/` 模块：DataDictionary（字段注册表）、SnapshotManager（versioned data pulls）、CCMLinker（point-in-time CRSP-Compustat linking）、DataLayer facade
- `PipelineStatus` dataclass 跟踪 factor 执行状态和 backtrack 计数
- MethodSpec 新增 `FieldSource`、`SignalTiming`、`MissingPolicy`、`SignalSpec`、`PortfolioSpec`、`BreakpointSpec`、`ExtractionSource`、`AmbiguousField` 子模型
- Review Gate 新增 `classify_disposition()` 函数实现决策矩阵
- Extractor 新增 `evaluate_extraction()` 方法对标 C&Z ground truth

### Fixed
- `factor_spec.py` 修复 `Optional` import 位置错误

## [0.1.0] - 2026-05-20

### Added
- 项目基本框架搭建
- 核心数据模型：`MethodSpec`、`FactorSpec`、`PluginRecord`、`RunRecord`
- Semantic Extractor 模块（接口定义）
- Review Gate 模块（基础验证逻辑）
- Controlled Meta-Coder 模块（接口定义）
- Adversarial Sandbox 模块（语法检查、schema 检查、forbidden pattern 扫描）
- Plugin Registry 模块（增删查改）
- Controlled Backtesting Lifecycle Engine 模块（接口定义）
- Dual-Track + Factorial Controller 模块（original/standardized/ablation track）
- Evidence Store + Run Registry 模块（JSON 持久化）
- Factorial Attribution Layer 模块（ablation 归因框架）
- Pipeline orchestrator 串联全流程
- `pyproject.toml` 项目配置
- `.github/copilot-instructions.md` agent 指令（强制每次修改更新 changelog）
