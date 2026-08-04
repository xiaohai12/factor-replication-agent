"""RunRecord - Metadata for a single backtest run."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RunMetrics(BaseModel):
    """Standard metrics from a backtest run."""

    mean_return: Optional[float] = None
    t_stat: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    alpha_capm: Optional[float] = None
    alpha_ff3: Optional[float] = None
    alpha_ff5: Optional[float] = None
    coverage: Optional[float] = None
    microcap_share: Optional[float] = None
    n_months: Optional[int] = None


class RepairAttempt(BaseModel):
    """One bounded technical-repair iteration in the RepairLoop (audit trail).

    Records every time MetaCoder was asked to fix the plugin because a
    validation check or a backtest execution failed. Persisted on the
    RunRecord so the self-debugging history is auditable (never an empirical
    repair -- only syntax/schema/runtime fixes; see src/infra/repair.py).
    """

    attempt_index: int = Field(..., description="0-based repair attempt within one loop")
    trigger_stage: str = Field(..., description="validate|execute -- what failed and triggered the repair")
    trigger_error: str = Field(default="", description="the error text fed back to MetaCoder")
    error_kind: str = Field(default="technical", description="always technical -- empirical issues never repaired here")
    code_hash_before: str = Field(default="")
    code_hash_after: str = Field(default="")
    passed: bool = Field(default=False, description="whether the repaired plugin passed re-validation")


class RunRecord(BaseModel):
    """Registry record for a single backtest experiment run."""

    run_id: str = Field(..., description="Unique run identifier")
    factor_id: str
    plugin_id: str
    track: str = Field(..., description="original_method|standardized_hxz|ablation_*|factorial_*")

    # Provenance hashes
    method_spec_hash: str = Field(default="")
    code_hash: str = Field(default="")
    lifecycle_commit: str = Field(default="")
    data_snapshot_hash: str = Field(default="")
    config_hash: str = Field(default="")

    # Best-effort runtime provenance (docs/multi-config-evidence-plan.md
    # Phase 0.5) -- see src.infra.provenance.collect_runtime_provenance.
    # `lifecycle_commit` above is kept as the single-string git commit for
    # quick display/back-compat; this dict is the fuller record (dirty
    # worktree flag, engine source hash, interpreter/dependency versions,
    # external FF-factor file hash) needed to tell "same script bytes" apart
    # from "same execution logic".
    runtime_provenance: dict = Field(default_factory=dict)

    # Matrix/batch identity (docs/multi-config-evidence-plan.md Phase 0.6):
    # every RunRecord produced by one `DualTrackController.run_experiment()`
    # call shares one `experiment_batch_id`. The whole batch's premise --
    # "every track ran the SAME frozen plugin code, only config differs" --
    # is falsifiable: if any track's execution failure triggered a
    # track-local repair that changed its code_hash away from the batch's
    # `frozen_plugin_hash`, `batch_invalidated` is set True on every record in
    # the batch (not just the repaired one), since the whole batch's
    # cross-track config attribution is compromised, not only that one
    # track's result.
    experiment_batch_id: str = Field(default="")
    frozen_plugin_hash: str = Field(default="")
    batch_invalidated: bool = Field(default=False)
    batch_invalidation_reason: str = Field(default="")

    # True for a C&Z signal BRIDGE track (docs/multi-config-evidence-plan.md
    # Phase C/D -- see src.infra.reference.cz_bridge): this track's signal
    # came from an externally-supplied series, not this factor's own
    # `compute_signal()`, so its `code_hash` is intentionally NOT the agent
    # plugin's hash and must be excluded from the batch's "every track ran
    # identical code" consistency check (`DualTrackController._finalize_batch`)
    # -- a bridge track's whole point is a DIFFERENT signal source under the
    # SAME config, which is a different comparison axis entirely from
    # config-only ablations.
    is_bridge_track: bool = Field(default=False)

    # Results
    metrics: Optional[RunMetrics] = None
    return_series_path: Optional[str] = None
    signal_series_path: Optional[str] = None

    # Status
    status: str = Field(default="pending", description="pending|running|success|failed|needs_review")
    created_at: datetime = Field(default_factory=datetime.now)
    logs: list[str] = Field(default_factory=list)

    # Self-debugging audit trail: every bounded technical-repair iteration the
    # RepairLoop ran to reach this run (empty when the plugin passed first try).
    repair_history: list[RepairAttempt] = Field(default_factory=list)
