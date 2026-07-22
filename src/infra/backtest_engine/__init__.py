"""Controlled Backtesting Lifecycle Engine - Fixed empirical pipeline.

Steps are executed in a fixed order. Each step either runs a standard
implementation (parameterised by config) or calls a hook function from the
signal plugin when the MethodSpec requires non-standard logic.

Hook dispatch pattern (each step):
    fn = self._hooks.get("step_name", <standard step function>)
    result = fn(data, config)

Module layout (see plan.md "Progressive file split"):
  - `__init__.py` (this file) — orchestration: `BacktestExecutor`, `Step`
    Protocol, `BacktestContext`, `run()`/`run_with_config()`/`_dispatch()`.
  - `steps.py` — the standard step pure functions (computation).
  - `registry.py` — `load_hooks` only (run-time hook loading; the one piece
    of "registry" logic `run_with_config()` itself calls).

The generation-time decision layer (which steps are "standard", how a
MethodSpec resolves into a run config: `STANDARD`, `detect_hooks`,
`build_config`, `resolve_long_leg`/`resolve_short_leg`/`normalize_leg`) lives
in `src/steps/step3_codegen/registry.py` instead — it's only ever called at
generation time (by MetaCoder/script_generator), never by this module's own
dispatch, so step3_codegen owns it and doesn't need to depend on this package
for it. `BacktestExecutor._detect_hooks()`/`_build_config()`/etc. below remain
as thin backward-compatible delegates to that module for existing callers
(including tests) that use those names.

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
from src.infra.backtest_engine import registry, steps


class Step(Protocol):
    """Uniform contract every standard step function and every LLM-generated
    hook function satisfies: `(*args, config) -> DataFrame`. `*args` carries
    whatever positional data the step needs (just `df` for most steps, `df,
    breakpoints` for assign_portfolios). Because both a standard step and its
    hook replacement share this exact shape, `_dispatch()` can swap one for
    the other with no special-casing anywhere else in the engine."""

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
    hooks: dict[str, Any] = field(default_factory=dict)
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

    Executes the fixed empirical pipeline. Standard steps are built-in;
    non-standard steps call hook functions loaded from the signal plugin.

    Steps (order is frozen):
      1. load_data          — load returns table by name
      2. apply_delisting_returns — fold CRSP dlret into ret (deterministic;
                              no-op when no dlret column, plan.md Phase 2.5)
      3. apply_missing_policy — drop / winsorize
      4. filter_universe    — baseline screen + deterministic universe_filters
                              DSL (plan.md Phase 2.5); a filter_universe_hook
                              still overrides this when supplied
      5. apply_excess_returns — subtract rf when factor data is supplied
                              (no-op otherwise, plan.md Phase 6)
      6. merge_signal       — expand annual signal to monthly holding period
                              (hooked when signal.timing.overlapping_portfolios is true)
      7. neutralize_signal  — deterministic neutralization scaffold, no-op by
                              default (plan.md Phase 2.5)
      8. compute_breakpoints — quantile breakpoints (full_sample or NYSE)
      9. assign_portfolios  — cut stocks into decile/quintile groups
     10. compute_returns    — VW or EW portfolio returns
     11. compute_long_short — extreme-leg spread
     12. compute_metrics    — mean, Newey-West t-stat, Sharpe (+ factor
                              alphas when factor data is supplied)

    This class is orchestration only — see `steps.py` for what each standard
    step actually computes and `src/steps/step3_codegen/registry.py` for how
    hook-need/config are decided. `run()` below is the entry point and reads
    like a table of contents for the whole pipeline.
    """

    def __init__(self, data_path: str | None = None):
        self.data_path = Path(data_path) if data_path else Path("./data")
        self._hooks: dict[str, Any] = {}

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
            plugin:          PluginRecord — source of hook functions
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
            plugin:  PluginRecord — source of hook functions
            data:    Optional pre-loaded MSF DataFrame; see `run()`.
            factors: Optional FF factor + rf DataFrame; see `run()`.

        Returns:
            Dict with keys: metrics, return_series, config
        """
        self._hooks = self._load_hooks(plugin)
        ctx = BacktestContext(config=config, hooks=self._hooks, factors=factors)

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

        # Fama-MacBeth (plan.md Phase 7) is a genuinely different ESTIMATOR,
        # not a variant of the portfolio-sort pipeline -- branch here instead
        # of continuing into breakpoints/assign/returns/combine at all.
        if config.get("estimator") == "fama_macbeth":
            ctx.metrics = steps.compute_fama_macbeth(ctx.merged, config)
            ctx.trace.append("compute_fama_macbeth")
            return {"metrics": ctx.metrics, "return_series": pd.DataFrame(), "config": config}

        ctx.merged    = self._dispatch("neutralize_signal", ctx.merged, config=config)
        ctx.trace.append("neutralize_signal")
        ctx.breakpoints = self._dispatch("compute_breakpoints", ctx.merged, config=config)
        ctx.trace.append("compute_breakpoints")
        ctx.portfolios  = self._dispatch("assign_portfolios", ctx.merged, ctx.breakpoints, config=config)
        ctx.trace.append("assign_portfolios")
        ctx.returns     = self._dispatch("compute_returns", ctx.portfolios, config=config)
        ctx.trace.append("compute_returns")
        ctx.long_short  = self._dispatch("compute_long_short", ctx.returns, config=config)
        ctx.trace.append("compute_long_short")
        ctx.metrics     = steps.compute_metrics(ctx.long_short, config)
        ctx.trace.append("compute_metrics")
        if ctx.factors is not None:
            ctx.metrics.update(steps.compute_factor_alphas(ctx.long_short, ctx.factors, config))
            ctx.trace.append("compute_factor_alphas")

        return {"metrics": ctx.metrics, "return_series": ctx.long_short, "config": config}

    #: Steps that get routed to a `_multi` counterpart in `steps.py` when
    #: `config["sort_dims"]` has 2+ dimensions (plan.md Phase 3). A plugin
    #: hook for the plain step name still takes priority over either variant.
    _MULTI_DIM_STEPS = {
        "compute_breakpoints",
        "assign_portfolios",
        "compute_returns",
        "compute_long_short",
    }

    #: Steps that get routed to an `_overlap` counterpart in `steps.py` when
    #: `config["overlapping"]` is true (plan.md Phase 5). Takes priority over
    #: `_MULTI_DIM_STEPS` routing (the two aren't combined in this v1 — see
    #: `step3_codegen.registry.detect_hooks()`, which still requests a hook
    #: for that specific combination).
    _OVERLAP_STEPS = {
        "merge_signal",
        "compute_breakpoints",
        "assign_portfolios",
        "compute_returns",
        "compute_long_short",
    }

    def _dispatch(self, step: str, *args: Any, config: dict) -> pd.DataFrame:
        """Call the plugin's hook for `step` if one was loaded, else fall back
        to the standard step function of the same name in `steps.py` (or its
        `_overlap`/`_multi` counterpart for overlapping-cohort holding /
        a resolved multi-dimensional sort, respectively).

        `*args` carries whatever positional data this step needs — just `df`
        for most steps, `df, breakpoints` for assign_portfolios — so a single
        dispatcher covers every step regardless of its argument count. This is
        the `Step` contract in practice: every branch is called identically.
        """
        if step in self._hooks:
            return self._hooks[step](*args, config)
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
        """Step 1: load the historical monthly stock return data (CRSP).

        Two layouts (config["returns_layout"], default "panel"):

        - "panel" (default): a single pre-flattened parquet located BY NAME
          (Option B directory convention) at
          `<data_path>/raw/<returns_table>.parquet`, `returns_table` default
          "crsp_msf". Falls back to the legacy `<data_path>/local/msf.parquet`
          when the raw/ file isn't present, so existing data/snapshots and the
          golden-number tests keep working unchanged.

        - "crsp_raw": assemble the panel from the raw, SEPARATE WRDS-shaped
          tables (crsp_msf + crsp_msenames + crsp_msedelist) in the directory
          `config["returns_dir"]` (default `<data_path>`) via
          `data_layer.build_crsp_monthly_panel` — this is what reads the
          realistic multi-source layout produced by
          scripts/build_test_papers_synthetic_data.py.
        """
        if config.get("returns_layout", "panel") == "crsp_raw":
            from src.infra.data_layer import build_crsp_monthly_panel
            returns_dir = config.get("returns_dir") or self.data_path
            return build_crsp_monthly_panel(returns_dir)

        name = config.get("returns_table", "crsp_msf")
        raw_path = self.data_path / "raw" / f"{name}.parquet"
        legacy_path = self.data_path / "local" / "msf.parquet"
        path = raw_path if raw_path.exists() else legacy_path
        return steps.load_msf(path)

    # ------------------------------------------------------------------
    # Hook detection & config resolution — thin delegation to
    # step3_codegen.registry (the generation-time decision layer), kept as
    # methods/classmethods here for backward compatibility (existing callers
    # use `BacktestExecutor._detect_hooks(spec)` and
    # `engine._build_config(spec, overrides)`).
    # ------------------------------------------------------------------

    @classmethod
    def _detect_hooks(cls, spec: MethodSpec) -> dict[str, str]:
        """Return {step_name: reason} for steps that need LLM-generated hooks."""
        return codegen_registry.detect_hooks(spec)

    def _build_config(self, spec: MethodSpec, overrides: dict | None) -> dict:
        """Build run config entirely from resolved MethodSpec fields."""
        return codegen_registry.build_config(spec, overrides)

    def _load_hooks(self, plugin) -> dict[str, Any]:
        """Exec plugin code and extract hook callables."""
        return registry.load_hooks(plugin)

    @staticmethod
    def _resolve_long_leg(spec: MethodSpec) -> str:
        return codegen_registry.resolve_long_leg(spec)

    @staticmethod
    def _resolve_short_leg(spec: MethodSpec) -> str:
        return codegen_registry.resolve_short_leg(spec)

    @staticmethod
    def _normalize_leg(value: Any, default: str) -> str:
        return codegen_registry.normalize_leg(value, default)

