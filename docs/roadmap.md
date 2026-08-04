# Factor Replication Agent Roadmap

## Research Target

Build a controlled, leakage-proof system that:

1. extracts a paper-first `MethodSpec`;
2. generates only the factor's `compute_signal()` formula;
3. runs the frozen signal through a deterministic backtest engine;
4. compares agent and C&Z implementations without treating C&Z as ground truth;
5. records enough evidence to explain whether differences come from signal implementation, config choices, data, or an unidentified combination.

The detailed experiment/evidence design lives in
[multi-config-evidence-plan.md](multi-config-evidence-plan.md). The broader research methodology lives in
[replication-diagnosis-design.md](replication-diagnosis-design.md).

## Current Baseline

Implemented and tested:

- paper extraction, deterministic review checks, human resolution, and bounded targeted re-extraction;
- formula-only plugin generation and bounded technical repair;
- future-leak validation and `compute_signal` execution smoke test;
- one generated backtest script executed through `BacktestRunner`;
- standardized `BacktestExecutor` lifecycle and registry-based DataLayer;
- synthetic golden-number E2E coverage plus supported real WRDS CSV layouts;
- basic `original_method`, `standardized_hxz`, and one-at-a-time track orchestration;
- `MethodSpec` distinction between `unspecified` (paper silent) and `other` (paper explicit but engine-unsupported), with deterministic substitution provenance.
- calendar-lag/as-of signal alignment for explicit annual formation months:
	accounting data availability remains a data-layer timestamp, while the
	engine samples the latest non-stale signal as of the reviewed formation
	month (default max staleness 11 months, matching a 12-month C&Z-style
	forward-fill window). Monthly/quarterly paths remain on their existing
	lifecycle.
- `BacktestRunner.build_script(track_name=...)`: distinct tracks/configs for
	the same factor no longer collide on the same on-disk script/output path.
	`DualTrackController` now threads its `track_name` through, so
	`original_method`/`standardized_hxz`/ablation tracks each persist to their
	own `{factor_id}__{track_name}` files instead of silently overwriting each
	other (only the in-memory `RunRecord` was previously reliable per track).
- `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]` fixed from an invalid
	percentile list to the engine's actual group-count contract (`10`) --
	`standardized_hxz` was previously unrunnable (`int([...])` raised).
	Verified with a real `DualTrackController.run_experiment()` run
	(original_method + standardized_hxz, same frozen plugin) against real
	`data/local` WRDS data for AssetGrowth.

Not yet implemented:

- complete signal/return/intermediate artifact persistence beyond the script/CSV/metrics files (no evidence-store hashing/provenance yet);
- strict config-key validation and effective-diff calculation;
- matrix-level plugin freezing and invalidation;
- declarative `experiments/<factor_id>.experiments.yaml` authoring;
- C&Z signal bridge execution;
- persisted `ReplicationDiagnosisReport` returned by the pipeline;
- optional evidence-bound LLM explanation layer.

## Immediate Correctness Work

Before multi-config implementation:

1. ~~Fix `HXZ_STANDARD_CONFIG["breakpoint_quantiles"]`~~ — DONE (2026-08-03):
	changed from an invalid percentile list to the resolved integer group count
	(`10`); verified with a real `standardized_hxz` run against real WRDS data.
2. Introduce typed config resolution. Unknown keys, invalid values, and no-op overrides must fail before execution; paper-originated `substitutions` must remain a separate provenance field.
3. Route pre-signal config keys (for example accounting lag) into signal-input assembly rather than storing a config value that does not affect execution.
4. Repair and freeze the plugin before a matrix starts. A track-local formula repair invalidates the whole batch; it must never create comparable runs with different code hashes.
5. Promote signal timing policy fields from implicit config defaults to a
	reviewed MethodSpec contract: at minimum `timing_basis` (`calendar_lag` vs.
	`report_date`) and `signal_max_staleness_months`. The engine currently
	implements the mainstream calendar-lag path; report-date timing should only
	be enabled for papers that explicitly require actual announcement/filing
	dates and after a point-in-time report-date source is registered.

## Multi-Config Implementation Sequence

### Phase 0 — Config and Run Identity

- `ConfigKeySpec` registry with pre-signal/post-signal stage metadata and validators;
- resolved config + effective diff + substitution provenance;
- `RunContext` allocated before script generation;
- unique `execution_id`, `experiment_batch_id`, `experiment_spec_hash`, config/code/data hashes;
- runtime provenance: commit/dirty state, engine source hash, Python/dependency versions, command, external factor-file hashes.

### Phase A1 — Complete Evidence Bundle

Persist atomically per execution:

- MethodSpec, plugin, generated script, resolved config, runtime provenance;
- normalized pre-portfolio signal series;
- breakpoints, assignments, portfolio returns, final returns, diagnostics, metrics, logs;
- artifact hashes and semantic series hashes;
- failure evidence as well as success evidence.

Full intermediate evidence is required for pilot and bridge runs; bulk runs may use a lean evidence level.

### Phase A2 — Declarative Experiment Matrix

- one versioned `experiments/<factor_id>.experiments.yaml` per factor;
- baseline anchored to the reviewed paper-method config;
- named experiments plus declarative sweep grids;
- loader validates the whole file and expands sweeps into `ExperimentSpec` objects;
- experiment family is descriptive; identification level is computed from the actual pairwise resolved diff.

### Phase B — External Reference Contracts

- factor-to-C&Z manifest;
- versioned SignalDoc profiles, firm-level signals, and LS returns;
- one normalization/semantic-hash contract shared by agent and reference signals;
- reference units, sign, sample, and release version recorded explicitly.

### Phase C/D — Deterministic Comparison and Bridge

- pairwise config diff and identification level;
- matched-sample signal coverage, Pearson/Spearman correlation, sign agreement, and extreme-portfolio overlap;
- C&Z signal × our engine bridge under the exact same config as the agent run;
- two-sided OAT for differing settings, factorial analysis only for the interacting subset;
- persisted and pipeline-returned diagnosis report;
- paper/C&Z published comparisons remain observational and carry any engine-substitution caveat.

### Phase E — Optional LLM Explanation

- consumes only a persisted deterministic diagnosis report;
- each claim type is restricted to an allowed evidence schema;
- numbers are inserted by a deterministic renderer;
- output is an `llm_assisted_proposal`, human-reviewable and never written back to MethodSpec/config;
- enabling the LLM must not change the deterministic report hash.

## Data and Scale

- Real WRDS exports are supplied locally; there is no live WRDS service.
- Data snapshots must identify the exact files actually consumed, including any external FF-factor fallback.
- Cross-factor work starts only after AssetGrowth completes the full evidence + bridge workflow.

## Completion Criteria

The next major milestone is complete when one real-data factor:

1. runs a versioned experiment matrix without artifact collisions;
2. preserves one frozen plugin across comparable agent runs;
3. stores complete, hashed run evidence;
4. runs the C&Z signal bridge under a matched config;
5. emits a deterministic diagnosis report with explicit identification levels;
6. reproduces the same report with the LLM disabled.
