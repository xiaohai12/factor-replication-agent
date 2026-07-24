"""Controlled Backtesting Lifecycle Engine - Fixed empirical pipeline.

Steps are executed in a fixed order. Each step runs a standard implementation
parameterised by config. The engine is fully standardized: there is no
LLM-generated hook code — every portfolio-construction choice is *selected*
from a fixed menu of built-in implementations by `build_config`, and an
out-of-menu value is deterministically clamped to the menu default.

Module layout:
  - `__init__.py` (this file) — orchestration: `BacktestExecutor`, `Step`
    Protocol, `BacktestContext`, `run()`/`run_with_config()`/`_dispatch()`.
  - `steps.py` — the standard step pure functions (computation).

The generation-time decision layer (how a MethodSpec resolves into a run
config: `build_config`, `resolve_long_leg`/`resolve_short_leg`/`normalize_leg`)
lives in `src/steps/step3_codegen/registry.py` instead — it's only ever called
at generation time (by script_generator), never by this module's own dispatch,
so step3_codegen owns it and doesn't need to depend on this package for it.
`BacktestExecutor._build_config()`/etc. below remain as thin
backward-compatible delegates to that module for existing callers (including
tests) that use those names.

Lives in `src/infra/` (not `src/steps/`) because this is shared computation
infrastructure used by many callers with no single "owning" step —
`pipeline.py` (orchestration), `step6_dual_track_controller` (ablation
experiments), `app.py` (dashboard), and a dozen unit tests that exercise
`steps.py` directly as a standalone computation library, the same way
`src/infra/data_layer` (`DataLayer`/`CCMLinker`/`TimeAvailComputer`) is used
by many callers rather than being one step's private implementation. "Step 5"
as a pipeline action is just build-script + validate + subprocess-execute
(see `Pipeline._build_script`/`_execute_script`) — this package is the engine
library that script imports and runs, not the action of running it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from src.infra.models.method_spec import MethodSpec
from src.steps.step3_codegen import registry as codegen_registry
from src.infra.backtest_engine import estimators, steps


class Step(Protocol):
    """Uniform contract every standard step function satisfies: `(*args,
    config) -> DataFrame`. `*args` carries whatever positional data the step
    needs (just `df` for most steps, `df, breakpoints` for assign_portfolios),
    so `_dispatch()` can call every step identically with no special-casing
    anywhere else in the engine."""

    def __call__(self, *args: Any, config: dict[str, Any]) -> Any: ...


@dataclass
class BacktestContext:
    """Carries all state through one `run_with_config()` call.

    Steps themselves stay stateless pure functions (see `steps.py`); this
    dataclass is populated by the orchestrator as each step runs so every
    intermediate result is inspectable/traceable in one place rather than
    scattered across local variables.
    """

    config: dict[str, Any]
    data: pd.DataFrame | None = None
    merged: pd.DataFrame | None = None
    breakpoints: pd.DataFrame | None = None
    portfolios: pd.DataFrame | None = None
    returns: pd.DataFrame | None = None
    long_short: pd.DataFrame | None = None
    factors: pd.DataFrame | None = None
    metrics: dict[str, Any] | None = None
    trace: list[str] = field(default_factory=list)


class BacktestExecutor:
    """Controlled backtesting lifecycle engine.

    Executes a fixed *prep* chain, then hands off to a swappable *estimator*
    (see `estimators.py`). All steps/estimators are built-in and selected from
    config — the engine is fully standardized (no hook code).

    Prep chain (order is frozen):
      1. load_data          — load returns table by name
      2. apply_delisting_returns — fold CRSP dlret into ret (deterministic;
                              no-op when no dlret column, plan.md Phase 2.5)
      3. apply_missing_policy — drop
      4. filter_universe    — baseline screen + deterministic universe_filters
                              DSL (plan.md Phase 2.5)
      5. apply_excess_returns — subtract rf when factor data is supplied
                              (no-op otherwise, plan.md Phase 6)
      6. merge_signal       — expand annual signal to monthly holding period
                              (overlapping-cohort variant when
                              signal.timing.overlapping_portfolios is true)

    Estimator (selected by `config["estimator"]`; see `estimators.py`):
      - `portfolio_sort` (default): form_portfolios (breakpoints + assignment
        in one unit) -> compute_returns -> compute_long_short ->
        compute_metrics (+ factor alphas when factor data is supplied)
      - `fama_macbeth`: single-characteristic cross-sectional regression,
        no portfolio sort at all

    This class is orchestration only — see `steps.py`/`estimators.py` for
    what each standard step/estimator actually computes and
    `src/steps/step3_codegen/registry.py` for how config is decided. `run()`
    below is the entry point and reads like a table of contents for the whole
    pipeline.
    """

    def __init__(self, data_path: str | None = None):
        self.data_path = Path(data_path) if data_path else Path("./data")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        signal: pd.DataFrame,
        spec: MethodSpec,
        config_overrides: dict[str, Any] | None = None,
        plugin=None,
        data: pd.DataFrame | None = None,
        factors: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Execute controlled backtest lifecycle on a signal.

        Args:
            signal:          DataFrame [permno, yyyymm, signal] from compute_signal()
            spec:            Approved MethodSpec (all decisions resolved in spec fields)
            config_overrides: Optional per-run overrides (for ablation experiments)
            data:            Optional pre-loaded MSF DataFrame. When given, skips
                             `_load_data()` (which locates the returns table by
                             name at `<data_path>/raw/<returns_table>.parquet`,
                             falling back to the legacy `<data_path>/local/msf.parquet`)
                             — lets callers with a different data layout (e.g. a
                             per-snapshot path) load the file themselves and pass
                             it in directly.
            factors:         Optional FF factor + rf DataFrame (`yyyymm` +
                             `mktrf`/`smb`/`hml`/`rmw`/`cma`; see
                             `scripts/fetch_ff_factors.py`). When given,
                             `alpha_capm`/`alpha_ff3`/`alpha_ff5` (+ betas) are
                             added to the metrics dict (plan.md Phase 2).

        Returns:
            Dict with keys: metrics, return_series, config
        """
        config = self._build_config(spec, config_overrides)
        return self.run_with_config(signal, config, plugin=plugin, data=data, factors=factors)

    def run_with_config(
        self,
        signal: pd.DataFrame,
        config: dict[str, Any],
        plugin=None,
        data: pd.DataFrame | None = None,
        factors: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Execute the 9-step lifecycle from an already-resolved config dict.

        This is the single implementation shared by `run()` (which builds
        `config` from a MethodSpec) and by the standalone scripts generated by
        `src/steps/step3_codegen/script_generator.py` (which already has a resolved
        config dict baked in at generation time and just needs to execute the
        lifecycle) — so the in-process engine and the generated scripts can
        never drift out of sync with each other.

        Args:
            signal:  DataFrame [permno, yyyymm, signal] from compute_signal()
            config:  Already-resolved run config, e.g. from `_build_config()`
            data:    Optional pre-loaded MSF DataFrame; see `run()`.
            factors: Optional FF factor + rf DataFrame; see `run()`.

        Returns:
            Dict with keys: metrics, return_series, config
        """
        ctx = BacktestContext(config=config, factors=factors)

        ctx.data = data if data is not None else self._load_data(config)
        ctx.trace.append("load_data")
        ctx.data      = self._dispatch("apply_delisting_returns", ctx.data, config=config)
        ctx.trace.append("apply_delisting_returns")
        ctx.data      = self._dispatch("apply_missing_policy", ctx.data, config=config)
        ctx.trace.append("apply_missing_policy")
        ctx.data      = self._dispatch("filter_universe", ctx.data, config=config)
        ctx.trace.append("filter_universe")
        # Not dispatched via _dispatch()/hooks: needs ctx.factors (rf), which
        # isn't part of the standard (df, config) Step signature. No-op
        # unless factors with an `rf` column were supplied (plan.md Phase 6).
        ctx.data      = steps.apply_excess_returns(ctx.data, ctx.factors, config)
        ctx.trace.append("apply_excess_returns")
        ctx.merged    = self._dispatch("merge_signal", ctx.data, signal, config=config)
        ctx.trace.append("merge_signal")

        estimator = estimators.get_estimator(config.get("estimator"))
        result = estimator(ctx.merged, config, self._dispatch, ctx.factors, ctx.trace)
        ctx.metrics = result["metrics"]
        ctx.long_short = result["return_series"]

        return {"metrics": ctx.metrics, "return_series": ctx.long_short, "config": config}

    #: Steps that get routed to a `_multi` counterpart in `steps.py` when
    #: `config["sort_dims"]` has 2+ dimensions (plan.md Phase 3).
    #: `form_portfolios` is NOT listed here -- it resolves multi-dim sorts
    #: internally (see `steps.form_portfolios`) rather than via `_dispatch()`
    #: name-mangling, since it's the single unit for "how portfolios
    #: get formed" regardless of dimensionality.
    _MULTI_DIM_STEPS = {
        "compute_returns",
        "compute_long_short",
    }

    #: Steps that get routed to an `_overlap` counterpart in `steps.py` when
    #: `config["overlapping"]` is true (plan.md Phase 5). Takes priority over
    #: `_MULTI_DIM_STEPS` routing (the two aren't combined in this v1; an
    #: overlapping multi-dim sort falls back to the single-dim overlapping
    #: path).
    _OVERLAP_STEPS = {
        "merge_signal",
        "form_portfolios",
        "compute_returns",
        "compute_long_short",
    }

    def _dispatch(self, step: str, *args: Any, config: dict) -> pd.DataFrame:
        """Call the standard step function of the given name in `steps.py` (or
        its `_overlap`/`_multi` counterpart for overlapping-cohort holding /
        a resolved multi-dimensional sort, respectively).

        `*args` carries whatever positional data this step needs — just `df`
        for most steps, `df, breakpoints` for assign_portfolios — so a single
        dispatcher covers every step regardless of its argument count.
        """
        if config.get("overlapping") and step in self._OVERLAP_STEPS:
            return getattr(steps, f"{step}_overlap")(*args, config)
        is_multi_dim = len(config.get("sort_dims") or []) > 1
        fn_name = f"{step}_multi" if (is_multi_dim and step in self._MULTI_DIM_STEPS) else step
        return getattr(steps, fn_name)(*args, config)

    # ------------------------------------------------------------------
    # load_data is kept as an engine method (not a plain `steps.py`
    # function) because it depends on `self.data_path`, which is instance
    # state set at construction time — every other step is a pure function
    # of its arguments only.
    # ------------------------------------------------------------------

    def _load_data(self, config: dict) -> pd.DataFrame:
        """Step 1: load the historical monthly stock return data.

        The returns universe (which stock-return panel to load) is NOT defaulted
        here — it must come from the reviewed spec via
        `config["returns_table"]`/`config["returns_layout"]`, which
        `build_config` fills in from `MethodSpec.returns_universe` (a
        `catalog.RETURNS_UNIVERSES` entry). If neither is present we fail loud
        rather than silently assuming CRSP.

        Two layouts (`config["returns_layout"]`):

        - "panel": a single pre-flattened parquet located BY NAME at
          `<data_path>/raw/<returns_table>.parquet`. Only when `returns_table`
          is literally `"crsp_msf"` (the legacy default table name) does a
          missing raw/ file fall back to `<data_path>/local/msf.parquet` (a
          FILE-location compatibility shim for pre-catalog snapshots/tests,
          not a data-source default) -- for every OTHER registered returns
          universe, a missing raw/ file fails loud instead of silently
          substituting the CRSP legacy file (that substitution would be
          exactly the silent-default-to-CRSP bug this design is meant to
          prevent).

        - "crsp_raw": assemble the panel from the raw, SEPARATE WRDS-shaped
          tables (crsp_msf + crsp_msenames + crsp_msedelist) in the directory
          `config["returns_dir"]` (default `<data_path>`) via
          `data_layer.build_crsp_monthly_panel` — this is what reads the
          realistic multi-source layout produced by
          scripts/build_test_papers_synthetic_data.py.
        """
        if config.get("returns_layout") == "crsp_raw":
            from src.infra.data_layer import build_crsp_monthly_panel
            returns_dir = config.get("returns_dir") or self.data_path
            return build_crsp_monthly_panel(returns_dir)

        name = config.get("returns_table")
        if not name:
            raise ValueError(
                "No returns universe specified: config has neither returns_table nor "
                "returns_layout='crsp_raw'. The stock-return panel must come from the "
                "reviewed MethodSpec.returns_universe (a registered "
                "catalog.RETURNS_UNIVERSES entry, e.g. 'us_equity_crsp') — the "
                "pipeline never defaults to a CRSP returns panel."
            )
        raw_path = self.data_path / "raw" / f"{name}.parquet"
        if raw_path.exists():
            return steps.load_msf(raw_path)
        if name == "crsp_msf":
            # Legacy pre-catalog file-location shim: existing snapshots/tests
            # store CRSP at <data_path>/local/msf.parquet instead of
            # raw/crsp_msf.parquet. Scoped to this exact table name so a
            # missing file for any OTHER returns universe fails loud instead
            # of silently loading CRSP data for the wrong universe.
            legacy_path = self.data_path / "local" / "msf.parquet"
            if legacy_path.exists():
                return steps.load_msf(legacy_path)
        raise FileNotFoundError(
            f"Returns table {name!r} not found at {raw_path} (no legacy fallback "
            f"applies to this table name). Export/place the returns panel there — "
            "the pipeline never substitutes a different returns universe's data."
        )

    # ------------------------------------------------------------------
    # Config resolution — thin delegation to step3_codegen.registry (the
    # generation-time decision layer), kept as a method here for backward
    # compatibility (existing callers use `engine._build_config(spec,
    # overrides)`).
    # ------------------------------------------------------------------

    def _build_config(self, spec: MethodSpec, overrides: dict | None) -> dict:
        """Build run config entirely from resolved MethodSpec fields."""
        return codegen_registry.build_config(spec, overrides)

    @staticmethod
    def _resolve_long_leg(spec: MethodSpec) -> str:
        return codegen_registry.resolve_long_leg(spec)

    @staticmethod
    def _resolve_short_leg(spec: MethodSpec) -> str:
        return codegen_registry.resolve_short_leg(spec)

    @staticmethod
    def _normalize_leg(value: Any, default: str) -> str:
        return codegen_registry.normalize_leg(value, default)

