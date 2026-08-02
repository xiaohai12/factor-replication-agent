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
- The duplicate English multi-config plan and obsolete CHANGELOG release
  history. Historical methodology decisions remain in `docs/decision-log.md`.

### Known Gaps

- Unique multi-config run identity, complete evidence persistence, strict config
  validation, declarative experiment matrices, C&Z signal bridge execution,
  and persisted diagnosis reports are designed but not implemented.
- `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` still needs to be aligned with
  the engine’s supported quantile-count contract and covered by a real-runner
  smoke test.
