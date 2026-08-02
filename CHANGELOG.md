# Changelog

## [Unreleased]

### Changed

- Consolidated active documentation around the current research target:
  paper-first MethodSpec extraction, formula-only plugin generation,
  deterministic backtesting, independent C&Z comparison, and planned
  multi-config evidence/bridge diagnosis.
- Replaced the historical phase-by-phase roadmap with a concise current roadmap.
- Consolidated the multi-config implementation plan into one canonical Chinese
  document: `docs/multi-config-evidence-plan.md`.
- Renamed active “Ground Truth” terminology:
  human-labeled MethodSpecs are “Curated Reference Specs”; C&Z artifacts are
  post-hoc/independent replication references, never empirical ground truth.
- Configured pytest to collect only `tests/`, preventing accidental collection
  of third-party C&Z scripts under `data/CZ code/`.
- Clarified the parallel UI migration: Streamlit remains the complete research
  UI while React/FastAPI reaches feature parity; both reuse `src/` logic.

### Added

- MethodSpec distinction between `unspecified` (paper silent) and `other`
  (paper explicit but engine-unsupported), with the literal paper value stored
  in `unsupported_fields`.
- Deterministic `build_config` substitution provenance and dedicated ReviewGate
  handling for unsupported paper values.
- Regression coverage for unsupported fields, including the Novy-Marx
  `capped_vw` MethodSpec fixture.
- Python 3.11 project pin and optional `openassetpricing==0.0.2` evaluation
  dependency for C&Z reference downloads.

### Removed

- Dead hook-era dashboard code and comments.
- `scripts/test_codegen.py`, which called removed hook APIs.
- The stale MethodSpec markdown template; the Pydantic model and extractor
  prompt are the authoritative contracts.
- Unreferenced hook-era HXZ/Novy-Marx plugin fixtures and dead hook code from
  the active Sloan fixture.
- Unused `Evaluator` stubs, the orphan `FactorSpec` model, and the obsolete
  `csv_to_gold_standard.py` workflow.
- Tracked macOS `.DS_Store` metadata (already covered by `.gitignore`).
- Redundant BacktestExecutor config-resolution compatibility delegates; engine,
  script generation, and dashboard now use the single codegen registry source.
- The duplicate English multi-config plan and obsolete CHANGELOG release
  history. Historical methodology decisions remain in `docs/decision-log.md`.

### Fixed

- Dashboard plugin generation no longer calls removed hook APIs.
- Dashboard backtest execution now passes the supported `signal_data_dir`
  argument instead of removed `compustat_data_path`/`ccm_link_path` arguments.
- Removed the non-functional Attribution dashboard path and replaced it with an
  honest Replication Diagnosis status view.
- Plugin Registry documentation now reflects its active in-memory use.

### Known Gaps

- Unique multi-config run identity, complete evidence persistence, strict config
  validation, declarative experiment matrices, C&Z signal bridge execution,
  and persisted diagnosis reports are designed but not implemented.
- `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` still needs to be aligned with
  the engine’s supported quantile-count contract and covered by a real-runner
  smoke test.
