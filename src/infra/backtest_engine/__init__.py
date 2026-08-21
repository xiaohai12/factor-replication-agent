"""Controlled Backtesting Lifecycle Engine — single-file implementation.

Everything (orchestration + every step's computation) lives in one class,
`BacktestExecutor`, in this one file. Each pipeline step is one method;
`run_with_config()` calls them in a fixed order and reads top-to-bottom as
the complete pipeline — there is no separate `steps.py`/`estimators.py`
module or generic `_dispatch()`-by-name indirection to jump through to see
what a run actually does.

State (`self.data`/`self.merged`/`self.portfolios`/... — see `__init__`) is
threaded through the pipeline on the instance: each step method reads the
previous step's output straight off `self` and writes its own result back
to `self`, so `run_with_config()` doesn't need to pass anything between
calls. Every step method ALSO accepts its inputs as optional explicit
arguments (falling back to the matching `self.*` attribute when omitted),
so each step stays independently unit-testable exactly like a plain
function (`engine.combine_portfolio_returns(rets, config)`) without needing
to run the whole pipeline first.

The engine is fully standardized: there is no LLM-generated hook code —
every portfolio-construction choice is *selected* from a fixed menu of
built-in implementations by `build_config` (`src/steps/step3_codegen/registry.py`),
and an out-of-menu value is deterministically clamped to the menu default.
This engine intentionally covers only one vanilla path plus one deliberately
re-added extension — non-overlapping holding, a continuous quantile sort
(single-dimension, or an independent/sequential double sort when
`config["sort_dims"]` has 2 entries -- see `form_portfolios`/
`compute_breakpoints_multi`), with a portfolio-sort estimator (see
docs/decision-log.md for what else was removed and why: overlapping-cohort
holding, the discrete/categorical sort form, the Fama-MacBeth estimator,
microcap exclusion -- none of those are back).

The generation-time decision layer (how a MethodSpec resolves into a run
config: `build_config`, `resolve_long_leg`/`resolve_short_leg`)
lives in `src/steps/step3_codegen/registry.py`. The engine calls that single
implementation when its convenience `run()` entry receives a MethodSpec.

Lives in `src/infra/` (not `src/steps/`) because this is shared computation
infrastructure used by many callers with no single "owning" step —
`pipeline.py` (orchestration), `step6_dual_track_controller` (ablation
experiments), `app.py` (dashboard), and unit tests that exercise individual
step methods directly, the same way `src/infra/data_layer`
(`DataLayer` + the `sources.py` DataSource registry) is used by many callers
rather than being one step's private implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.infra.models.method_spec import ResolvedMethodSpec
from src.steps.step3_codegen import registry as codegen_registry

from src.infra.data_layer import DataLayer

class BacktestExecutor:
    """Controlled backtesting lifecycle engine — one class, one file.

    Pipeline (order is frozen; `run_with_config()` calls these ten methods
    in exactly this order):
      1.  load_data                  — load returns table by name
      2.  apply_delisting_returns     — fold CRSP dlret into ret (no-op when
                                        no dlret column)
      3.  apply_missing_policy        — drop rows with missing ret
      4.  filter_universe             — deterministic universe_filters DSL
      5.  apply_excess_returns        — subtract rf when factor data supplied
                                        (no-op otherwise)
      6.  apply_signal_holding_period — expand signal to monthly holding
                                        period, hold window capped at the
                                        rebalance step (annual=12/quarterly=3/
                                        monthly=1); tags each row with its
                                        formation `cohort`
      7.  form_portfolios             — formation-locked breakpoints +
                                        portfolio assignment, locked at each
                                        signal's own `cohort` and held fixed
                                        for the whole holding period
      8.  compute_portfolio_returns   — each portfolio's own monthly return
                                        (`config["weighting_rule"]`: vw or ew)
      9.  combine_portfolio_returns   — combine per-portfolio returns into
                                        the final reported return series
                                        (`config["return_combination_type"]`;
                                        not always a long-short spread — see
                                        that method's docstring)
      10. compute_metrics             — mean/t-stat/Sharpe (+ factor alphas
                                        via `compute_factor_alphas` when
                                        factor data is supplied)

    Every method mutates `self` (see `__init__` for the full attribute
    list) AND returns its own result, and accepts its own inputs as optional
    explicit arguments — so `run_with_config()` calls each with no arguments
    (reading/writing `self.*`), while a unit test can call the same method
    directly with explicit inputs (`engine.combine_portfolio_returns(rets,
    config)`) without needing to run the rest of the pipeline first.
    """

    def __init__(self, data_path: str | None = None):
        self.data_path = Path(data_path) if data_path else Path("./data")

        # Populated progressively by run_with_config() as each step runs;
        # also directly settable by a test that wants to call one step in
        # isolation (e.g. `engine.merged = ...; engine.form_portfolios()`).
        self.config: dict[str, Any] = {}
        self.signal: pd.DataFrame | None = None
        self.factors: pd.DataFrame | None = None
        self.plugin = None
        self.data: pd.DataFrame | None = None
        self.merged: pd.DataFrame | None = None
        #: Formation cross-section built by `apply_signal_holding_period`:
        #: one row per (permno, cohort) with `signal` (+ `exchcd` as of the
        #: formation month, if available) -- INDEPENDENT of whether that
        #: permno has any valid return in its future held months. This is
        #: the population `compute_breakpoints` uses by default (see that
        #: method's docstring for why `self.merged` must not be used for
        #: this). None until `apply_signal_holding_period` runs, or when the
        #: signal/base panel were never supplied (e.g. `assign_portfolios`
        #: exercised in isolation from a hand-built `self.merged`).
        self.formation: pd.DataFrame | None = None
        #: Snapshot of the returns panel taken by `apply_missing_policy`
        #: BEFORE it drops rows with a missing `ret` -- lets
        #: `apply_signal_holding_period` determine universe-filter
        #: eligibility (shrcd/exchcd/siccd-type static attributes) for
        #: `self.formation` independently of whether a given stock-month's
        #: RETURN happened to be missing. None if `apply_missing_policy`
        #: never ran (e.g. `apply_signal_holding_period` exercised directly
        #: in isolation) -- falls back to whatever panel is on hand then.
        self._pre_missing_policy_data: pd.DataFrame | None = None
        #: Fraction of value-weighted held rows whose prior-month market
        #: equity (`me_{t-1}`) could not be resolved (and were therefore
        #: EXCLUDED from that month's value-weighting -- see
        #: `compute_portfolio_returns`/`_attach_lagged_me`). Set by
        #: `compute_portfolio_returns` on a vw run (None on an ew run or
        #: before it runs); surfaced as `metrics["vw_lagged_me_missing_frac"]`.
        self._vw_lag_me_missing_frac: float | None = None
        self.breakpoints: pd.DataFrame | None = None
        self.portfolios: pd.DataFrame | None = None
        self.returns: pd.DataFrame | None = None
        self.long_short: pd.DataFrame | None = None
        self.metrics: dict[str, Any] | None = None
        self.trace: list[str] = []

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def run(
        self,
        signal: pd.DataFrame,
        spec: ResolvedMethodSpec,
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
                             loading the returns table from disk — lets callers
                             with a different data layout (e.g. a per-snapshot
                             path) load the file themselves and pass it in directly.
            factors:         Optional FF factor + rf DataFrame (`yyyymm` +
                             `mktrf`/`smb`/`hml`/`rmw`/`cma`; see
                             `scripts/fetch_ff_factors.py`), optionally also
                             carrying `ps_vwf` (Pastor-Stambaugh liquidity
                             factor; see `load_liquidity_factors`). When
                             given, `alpha_capm`/`alpha_ff3`/`alpha_ff5`/
                             `alpha_liq` (+ betas) are added to the metrics
                             dict, whichever columns are present -- and, when
                             `by_sample_period` is also present, the SAME
                             regressions are re-run on each period's own
                             segment and merged into that period's own dict.

        Returns:
            Dict with keys: metrics, return_series, config
        """
        config = codegen_registry.build_config(spec, config_overrides)
        return self.run_with_config(signal, config, plugin=plugin, data=data, factors=factors)

    def run_with_config(
        self,
        signal: pd.DataFrame,
        config: dict[str, Any],
        plugin=None,
        data: pd.DataFrame | None = None,
        factors: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Execute the whole 10-step lifecycle from an already-resolved
        config dict — read this method top to bottom for the complete
        pipeline, in the exact order it runs.

        This is the single implementation shared by `run()` (which builds
        `config` from a MethodSpec) and by the standalone scripts generated
        by `src/steps/step3_codegen/script_generator.py` (which already has a
        resolved config dict baked in at generation time and just needs to
        execute the lifecycle) — so the in-process engine and the generated
        scripts can never drift out of sync with each other.

        Args:
            signal:  DataFrame [permno, yyyymm, signal] from compute_signal()
            config:  Already-resolved run config from
                `src.steps.step3_codegen.registry.build_config()`.
            data:    Optional pre-loaded MSF DataFrame; see `run()`.
            factors: Optional FF factor + rf DataFrame; see `run()`.

        Returns:
            Dict with keys: metrics, return_series, config
        """
        self.config = config
        self.signal = signal
        self.plugin = plugin
        self.factors = factors
        self.trace = []

        self.load_data(data)
        self.apply_delisting_returns()
        self.apply_missing_policy()
        self.filter_universe()
        self.apply_excess_returns()
        self.apply_signal_holding_period()
        self.form_portfolios()
        self.compute_portfolio_returns()
        self.combine_portfolio_returns()
        self.compute_metrics()
        if self.factors is not None:
            self.metrics.update(self.compute_factor_alphas())
            self.trace.append("compute_factor_alphas")

            # Same CAPM/FF3/FF5/liq regressions, but per sample-period segment
            # (in-sample/between/post-publication) -- lets a caller see
            # whether an alpha survives out-of-sample, not just the
            # mean/t-stat `compute_metrics` already breaks out by period.
            by_period = self.metrics.get("by_sample_period")
            if by_period:
                for name, seg_df in self._sample_period_segments(self.long_short, self.config).items():
                    if name in by_period:
                        by_period[name].update(
                            self.compute_factor_alphas(ls=seg_df, factors=self.factors, config=self.config)
                        )
                self.trace.append("compute_factor_alphas_by_sample_period")

        return {"metrics": self.metrics, "return_series": self.long_short, "config": self.config}

    # ------------------------------------------------------------------
    # Step 1: load_data
    # ------------------------------------------------------------------

    def load_data(self, data: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 1: load the historical monthly stock return data.

        The returns universe (which stock-return panel to load) is NOT defaulted
        here — it must come from the reviewed spec via
        `config["returns_table"]`/`config["returns_layout"]`, which
        `build_config` fills in from `MethodSpec.returns_source` (a
        `catalog.RETURNS_UNIVERSES` entry). If neither is present we fail loud
        rather than silently assuming CRSP.

        If `data` is given directly (a pre-loaded MSF DataFrame), disk
        loading is skipped entirely.

        Only one layout (`config["returns_layout"]`):

        - "crsp_ciz": assemble the panel from a real WRDS "new CIZ" export
          (`CRSP_STOCK_MONTH.csv` + `CRSP_DELISTING.csv`, a single
          already-point-in-time table) in `config["returns_dir"]` (default
          `<data_path>`) via `DataLayer.load_returns_by_layout` — the
          `CrspReturnsUniverse` DataSource in `data_layer/sources.py` (the
          registry is the single source of truth; see that class for the
          documented exchcd/shrcd approximations). This is the ONLY
          raw-multi-table CRSP assembly path (the legacy 3-table
          crsp_msf/crsp_msenames/crsp_msedelist "crsp_raw" layout was
          removed 2026-07-31, and the single-pre-flattened-parquet "panel"
          layout + `load_msf`/`load_daily_msf` were removed 2026-07-31 too —
          see docs/decision-log.md same date).
        """
        config = self.config if config is None else config
        if data is not None:
            self.data = data
            self.trace.append("load_data")
            return self.data

        if config.get("returns_layout") == "crsp_ciz":
            returns_dir = config.get("returns_dir") or self.data_path
            self.data = DataLayer(str(self.data_path)).load_returns_by_layout(
                config["returns_layout"], returns_dir
            )
            self.trace.append("load_data")
            return self.data

        raise ValueError(
            "No returns universe specified: config has no returns_layout='crsp_ciz'. "
            "The stock-return panel must come from the reviewed "
            "MethodSpec.returns_source (a registered catalog.RETURNS_UNIVERSES "
            "entry, e.g. 'us_equity_crsp') — the pipeline never defaults to a "
            "CRSP returns panel."
        )

    # ------------------------------------------------------------------
    # Step 2: apply_delisting_returns
    # ------------------------------------------------------------------

    def apply_delisting_returns(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 2: fold CRSP delisting returns into `ret` when a `dlret`
        column is present, via the standard convention
        `ret_adj = (1+ret)*(1+dlret) - 1`.

        Documented simplification: rows where `dlret` is missing/NaN are left as
        plain `ret` (no fixed delisting-return imputation by exchange, unlike the
        fuller Shumway/Johnson convention). No-op when no `dlret` column exists
        or when `config["apply_delisting_returns"]` is explicitly set to False
        (e.g. for an ablation run).
        """
        df = self.data if df is None else df
        config = self.config if config is None else config

        if config.get("apply_delisting_returns", True) and "dlret" in df.columns:
            df = df.copy()
            dlret = df["dlret"]
            has_dlret = dlret.notna()
            df.loc[has_dlret, "ret"] = (
                (1 + df.loc[has_dlret, "ret"].fillna(0)) * (1 + dlret[has_dlret]) - 1
            )

        self.data = df
        self.trace.append("apply_delisting_returns")
        return df

    # ------------------------------------------------------------------
    # Step 3: apply_missing_policy
    # ------------------------------------------------------------------

    def apply_missing_policy(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 3: what to do when the return is missing (standardized: drop).

        Snapshots the pre-drop `df` into `self._pre_missing_policy_data` --
        see `apply_signal_holding_period`'s docstring for why the formation
        cross-section needs a universe-eligibility source that isn't
        conflated with return-availability.
        """
        df = self.data if df is None else df
        config = self.config if config is None else config
        self._pre_missing_policy_data = df
        # `missing_action` is always clamped to "drop" by build_config; no
        # other implementation exists (no bespoke winsorize/fill).
        out = df.dropna(subset=["ret"]).copy()
        self.data = out
        self.trace.append("apply_missing_policy")
        return out

    # ------------------------------------------------------------------
    # Step 4: filter_universe
    # ------------------------------------------------------------------

    def filter_universe(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 4: which stocks count. Deterministic ResearchDesign step:
        applies ONLY the structured `universe_filters` resolved from the
        MethodSpec's `portfolio.universe_filters` (via the FilterOp DSL in
        `apply_universe_filters`) -- no hardcoded common-stock/major-exchange/
        ex-financials screen is applied here (that would assume every returns
        panel has CRSP-shaped `shrcd`/`exchcd`/`siccd` columns, contradicting
        the "no silent default data source" principle). A paper's actual
        universe restriction -- including the common "ordinary common
        shares, NYSE/AMEX/NASDAQ, ex-financials" boilerplate -- is expected
        to be captured as explicit `UniverseFilterSpec` entries by the
        extractor, the same as any other paper-specific restriction.
        """
        df = self.data if df is None else df
        config = self.config if config is None else config
        out = self.apply_universe_filters(df, config.get("universe_filters") or [])
        self.data = out
        self.trace.append("filter_universe")
        return out

    @staticmethod
    def apply_universe_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
        """Apply a list of {field, op, value} universe filters (the deterministic
        DSL behind `UniverseFilterSpec`/`FilterOp` in method_spec.py) to `df`.

        Point-in-time by construction: filters are evaluated row-wise on the
        already-point-in-time monthly panel (each row is one stock-month
        snapshot), so applying them here introduces no look-ahead.

        Fails loud (raises `ValueError`) when a filter references a `field`
        absent from the loaded panel: a MethodSpec that explicitly requires
        e.g. `shrcd in [10,11]` must NOT silently keep every row when the
        returns panel has no `shrcd` column (that would run a DIFFERENT
        universe than the paper stated while still reporting success). The
        reviewer can't validate column availability at spec-review time --
        different returns universes have different columns -- so this is
        caught here, at run time, where the actual panel columns are known.
        """
        if not filters:
            return df
        mask = pd.Series(True, index=df.index)
        for f in filters:
            field_name = f.get("field")
            if field_name not in df.columns:
                raise ValueError(
                    f"Universe filter references field {field_name!r}, which the "
                    f"loaded returns panel does not have (columns: "
                    f"{sorted(df.columns)}). The reviewed MethodSpec requires this "
                    "filter, but this returns universe can't supply the field -- "
                    "register an equivalent column for this returns universe, or "
                    "correct the MethodSpec's universe_filters. The pipeline never "
                    "silently ignores a stated universe restriction."
                )
            op = f.get("op", "nonmissing")
            mask &= BacktestExecutor._apply_filter_op(df[field_name], op, f.get("value"))
        return df[mask].copy()

    @staticmethod
    def _apply_filter_op(series: pd.Series, op: str, value: Any) -> pd.Series:
        """Evaluate one FilterOp (src/infra/models/method_spec.py FilterOp enum)
        against a column. Mirrors the vocabulary 1:1 so the deterministic DSL
        covers every value the extraction schema can produce."""
        if op == "eq":
            return series == value
        if op == "neq":
            return series != value
        if op == "in":
            return series.isin(value)
        if op == "not_in":
            return ~series.isin(value)
        if op == "between":
            lo, hi = value
            return series.between(lo, hi)
        if op == "intervals":
            if not isinstance(value, list) or not value:
                raise ValueError("FilterOp 'intervals' requires a non-empty list of [low, high] ranges")
            mask = pd.Series(False, index=series.index)
            for interval in value:
                if (
                    not isinstance(interval, (list, tuple))
                    or len(interval) != 2
                    or not all(isinstance(bound, (int, float)) and not isinstance(bound, bool) for bound in interval)
                    or interval[0] > interval[1]
                ):
                    raise ValueError(
                        "FilterOp 'intervals' requires every range to be a numeric [low, high] pair with low <= high"
                    )
                lo, hi = interval
                mask |= series.between(lo, hi)
            return mask
        if op == "not_between":
            lo, hi = value
            return ~series.between(lo, hi)
        if op == "gt":
            return series > value
        if op == "gte":
            return series >= value
        if op == "lt":
            return series < value
        if op == "lte":
            return series <= value
        if op == "nonmissing":
            return series.notna()
        if op == "nonzero":
            return series != 0
        if op == "is_true":
            return series.astype(bool)
        if op == "is_false":
            return ~series.astype(bool)
        raise ValueError(f"Unknown FilterOp: {op!r}")

    # ------------------------------------------------------------------
    # Step 5: apply_excess_returns
    # ------------------------------------------------------------------

    def apply_excess_returns(
        self,
        df: pd.DataFrame | None = None,
        factors: pd.DataFrame | None = None,
        config: dict | None = None,
    ) -> pd.DataFrame:
        """Step 5: convert raw returns to excess-of-risk-free returns, when
        `config["return_basis"] == "excess"` (the canonical default) and
        risk-free-rate data is available via `factors` (see
        `scripts/fetch_ff_factors.py`). No-op when `factors` is None/missing
        an `rf` column, or when `config["return_basis"] == "raw"` is
        explicitly requested (e.g. for an ablation). Note: for the standard
        long-short spread this makes no numeric difference (`rf` cancels in
        `long - short`) -- it matters for `single_signal_portfolio_return`/
        `full_portfolio_return` single-leg modes, which do NOT have rf
        canceled out.
        """
        df = self.data if df is None else df
        factors = self.factors if factors is None else factors
        config = self.config if config is None else config

        if config.get("return_basis", "excess") == "excess" and factors is not None and "rf" in factors.columns:
            rf = factors[["yyyymm", "rf"]]
            merged = df.merge(rf, on="yyyymm", how="left")
            merged["ret"] = merged["ret"] - merged["rf"].fillna(0)
            df = merged.drop(columns=["rf"])

        self.data = df
        self.trace.append("apply_excess_returns")
        return df

    # ------------------------------------------------------------------
    # Step 6: apply_signal_holding_period
    # ------------------------------------------------------------------

    def apply_signal_holding_period(
        self,
        df: pd.DataFrame | None = None,
        signal: pd.DataFrame | None = None,
        config: dict | None = None,
    ) -> pd.DataFrame:
        """Step 6: expand a low-frequency signal into one row per held month
        and join it with the monthly returns panel.

        Assumes non-overlapping ("clean calendar hold") portfolios: the most
        recently formed signal value is held flat until the next formation, then
        replaced. Each signal row already sits at its own formation month, so
        holding it forward from that row supports any formation/start month for
        free (the "rebalance calendar" is encoded in the signal rows themselves).

        Hold window is capped at the rebalance step derived from
        `config["rebalance_frequency"]` (annual=12, quarterly=3, monthly=1)
        when specified -- so a quarterly-rebalanced factor holds 3 months,
        not a stale 12. `rebalance_frequency="unspecified"` falls back to
        `holding_period_months` verbatim.

        Also builds `self.formation` (see `__init__`): the formation
        cross-section (`signal` + formation-month attributes), BEFORE the
        `how="inner"` join with future returns below drops any permno that
        has no valid return in ANY of its held months (e.g. a stock
        delisted immediately after formation). `compute_breakpoints` reads
        from `self.formation`, not from this method's returned/`merged`
        DataFrame, precisely to avoid that future-return-availability leak
        into the breakpoint population -- see docs/decision-log.md for the
        2026-07-28 fix this implements.

        `self.formation`'s `universe_filters`/`exchcd` attributes are looked
        up POINT-IN-TIME at each (permno, cohort)'s OWN formation month in
        `self._pre_missing_policy_data` (the panel BEFORE `apply_missing_policy`
        dropped missing-return rows) -- NOT from `df` (which never contains a
        formation-month row at all under this engine's held-months-only
        convention: held months start at `h=1`, i.e. strictly AFTER
        formation), and NOT aggregated across the stock's whole history
        (which would let a stock's attributes from an unrelated month decide
        its OWN cohort's eligibility/exchange classification). A
        (permno, cohort) with NO matching formation-month row in the source
        (e.g. the panel simply never recorded that stock-month) is NOT
        excluded by `universe_filters` -- there is no positive evidence
        against it -- but its `exchcd` is left `NaN`, meaning it's honestly
        left unclassified for `breakpoint_source="nyse"` rather than
        silently misclassified. Falls back to `df` when
        `self._pre_missing_policy_data` is unset (e.g. this method
        exercised directly, bypassing `apply_missing_policy`). See
        docs/decision-log.md for the two rounds of fixes this closes: the
        original 2026-07-28 look-ahead fix, a same-day follow-up that fixed
        `universe_filters` exclusion but used a permno-wide (not
        cohort-specific) eligibility set and left `exchcd` reading from
        `df` (so `breakpoint_source="nyse"` was still effectively broken),
        and this point-in-time rewrite.
        """
        df = self.data if df is None else df
        signal = self.signal if signal is None else signal
        config = self.config if config is None else config

        signal = self._resample_annual_signal_asof(signal, df, config)
        self._validate_annual_formation_month(signal, config)
        # Applied AFTER the above so paper-fidelity validation still checks
        # the MethodSpec's TRUE stated formation month; the lag then shifts
        # the calendar C&Z's own portfolio-formation logic actually runs on
        # (docs/step6.md gap #2) -- default 0, no-op for any existing config.
        signal = self._apply_formation_lag(signal, config)

        hp = int(config.get("holding_period_months", 12))
        step = self._rebalance_step_months(config)
        hold = min(hp, step) if step is not None else hp
        rows: list[dict] = []
        for _, row in signal.iterrows():
            yyyymm = int(row["yyyymm"])
            year, month = divmod(yyyymm, 100)
            for h in range(1, hold + 1):
                m = month + h
                y = year + (m - 1) // 12
                m = (m - 1) % 12 + 1
                rows.append({
                    "permno": int(row["permno"]),
                    "cohort": yyyymm,
                    "yyyymm": y * 100 + m,
                    "signal": float(row["signal"]),
                })
        expanded = pd.DataFrame(rows)
        if expanded.empty:
            self.merged = df.iloc[0:0].copy()
            self.formation = signal.rename(columns={"yyyymm": "cohort"}).copy()
            self.trace.append("apply_signal_holding_period")
            return self.merged
        merged = df.merge(expanded, on=["permno", "yyyymm"], how="inner")

        # Formation cross-section: every (permno, cohort) with a signal
        # value, regardless of whether that permno survives into `merged`
        # above. Attributes (universe_filters fields, exchcd) are attached
        # from that (permno, cohort)'s OWN formation-month row -- see
        # docstring above.
        formation = signal.rename(columns={"yyyymm": "cohort"}).copy()
        formation["permno"] = formation["permno"].astype(int)

        attrs_source = self._pre_missing_policy_data if self._pre_missing_policy_data is not None else df
        attrs_at_formation = attrs_source.rename(columns={"yyyymm": "cohort"}).copy()
        attrs_at_formation["permno"] = attrs_at_formation["permno"].astype(int)
        attrs_at_formation = attrs_at_formation.drop_duplicates(subset=["permno", "cohort"])

        formation = formation.merge(
            attrs_at_formation, on=["permno", "cohort"], how="left", indicator="_has_formation_row"
        )
        has_formation_row = formation["_has_formation_row"] == "both"

        universe_filters = config.get("universe_filters") or []
        if universe_filters:
            passes = pd.Series(True, index=formation.index)
            for f in universe_filters:
                field_name = f.get("field")
                if field_name not in formation.columns:
                    raise ValueError(
                        f"Universe filter references field {field_name!r}, which the "
                        f"formation cross-section does not have (columns: "
                        f"{sorted(formation.columns)}). Same fail-loud rule as "
                        "filter_universe/apply_universe_filters -- a stated universe "
                        "restriction must never be silently ignored. Register an "
                        "equivalent formation-time column for this returns universe, "
                        "or correct the MethodSpec's universe_filters."
                    )
                op = f.get("op", "nonmissing")
                passes &= self._apply_filter_op(formation[field_name], op, f.get("value"))
            # Exclude only (permno, cohort) pairs with POSITIVE evidence of
            # failing the filter: a formation-month row exists AND it fails.
            # A pair with no formation-month data at all is kept regardless
            # (no positive evidence of exclusion -- see docstring).
            excluded_mask = has_formation_row & ~passes
            excluded = formation.loc[excluded_mask, ["permno", "cohort"]].drop_duplicates()
            formation = formation[~excluded_mask]
            # CRITICAL: the SAME exclusion must reach the actual portfolio
            # assignment/return population (`merged`), not just the
            # breakpoint population (`formation`). Otherwise a stock
            # excluded from defining the breakpoints would still be sorted
            # BY those breakpoints and contribute returns -- a self-
            # inconsistent state. See docs/decision-log.md for the fix this
            # implements.
            if not excluded.empty:
                merged = merged.merge(
                    excluded.assign(_excluded=True), on=["permno", "cohort"], how="left"
                )
                merged = merged[merged["_excluded"].isna()].drop(columns=["_excluded"])

        formation = formation.drop(columns=["_has_formation_row"])

        self.merged = merged
        self.formation = formation
        self.trace.append("apply_signal_holding_period")
        return merged

    @staticmethod
    def _yyyymm_to_month_index(values: pd.Series) -> pd.Series:
        values = values.astype(int)
        return (values // 100) * 12 + (values % 100) - 1

    @staticmethod
    def _apply_formation_lag(signal: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Shift `signal["yyyymm"]` forward by `config["formation_lag_months"]`
        months (default 0 -- a no-op, unchanged behavior for every existing
        config). Models C&Z's global, undocumented 1-month portfolio-
        formation lag (`signal[, yyyymm := yyyymm + 1]`, docs/step6.md gap
        #2): they overwrite the signal's own timestamp before their
        portfolio-formation logic runs, so it stacks with (doesn't replace)
        this engine's own next-month holding convention. Only ever non-zero
        when the config was built from `C_cz` (`cz_profile_to_config_override`)."""
        lag = int(config.get("formation_lag_months", 0) or 0)
        if lag == 0 or signal is None or signal.empty:
            return signal
        signal = signal.copy()
        shifted = BacktestExecutor._yyyymm_to_month_index(signal["yyyymm"]) + lag
        signal["yyyymm"] = (shifted // 12) * 100 + (shifted % 12) + 1
        return signal

    @staticmethod
    def _resample_annual_signal_asof(signal: pd.DataFrame, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Align accounting signals to an explicit annual formation month by
        taking each stock's most recent already-available signal as of that
        formation month.

        This separates data availability (`signal.yyyymm`, produced upstream
        from accounting lag / report availability) from the portfolio formation
        calendar (`config["formation_month"]`). For monthly/quarterly factors,
        or annual specs without an explicit formation month, this is a no-op.
        For already-aligned annual signals (all cohorts already in the stated
        month), it is also a no-op so existing golden-number paths stay on the
        original code path.
        """
        if str(config.get("rebalance_frequency", "unspecified")).lower() != "annual":
            return signal
        if not config.get("formation_month_explicit"):
            return signal
        formation_month = config.get("formation_month")
        if formation_month is None or signal is None or signal.empty or "yyyymm" not in signal.columns:
            return signal

        formation_month = int(formation_month)
        cohort_months = {int(v) % 100 for v in signal["yyyymm"].dropna().unique()}
        if cohort_months <= {formation_month}:
            return signal

        max_stale = int(config.get("signal_max_staleness_months", 11))
        if max_stale < 0:
            raise ValueError("signal_max_staleness_months must be non-negative")

        formation_rows = df.loc[(df["yyyymm"].astype(int) % 100) == formation_month, ["permno", "yyyymm"]]
        if formation_rows.empty:
            return signal.iloc[0:0].copy()

        targets = formation_rows.drop_duplicates().rename(columns={"yyyymm": "cohort"}).copy()
        targets["permno"] = targets["permno"].astype(int)
        targets["_target_m"] = BacktestExecutor._yyyymm_to_month_index(targets["cohort"])

        source = signal[["permno", "yyyymm", "signal"]].dropna(subset=["signal"]).copy()
        source["permno"] = source["permno"].astype(int)
        source["_signal_m"] = BacktestExecutor._yyyymm_to_month_index(source["yyyymm"])

        aligned = pd.merge_asof(
            targets.sort_values(["_target_m", "permno"]),
            source.sort_values(["_signal_m", "permno"]),
            by="permno",
            left_on="_target_m",
            right_on="_signal_m",
            direction="backward",
            tolerance=max_stale,
        )
        aligned = aligned.dropna(subset=["signal"])
        if aligned.empty:
            return signal.iloc[0:0].copy()
        out = aligned[["permno", "cohort", "signal"]].rename(columns={"cohort": "yyyymm"})
        out["permno"] = out["permno"].astype(int)
        out["yyyymm"] = out["yyyymm"].astype(int)
        return out.sort_values(["permno", "yyyymm"]).reset_index(drop=True)

    @staticmethod
    def _validate_annual_formation_month(signal: pd.DataFrame, config: dict) -> None:
        """Fail loud when an ANNUAL-rebalanced strategy carries a signal whose
        formation cohorts don't all sit in the MethodSpec's stated
        `formation_month`.

        Only annual strategies are validated, and only when `formation_month`
        was set EXPLICITLY in the reviewed MethodSpec (`formation_month_explicit`
        in config). Rationale:

        - Annual rebalancing implies a single formation month per year (e.g. an
          accounting-based factor formed every June). If the signal's cohorts
          land in a DIFFERENT month than the reviewed `formation_month`, the
          engine and the MethodSpec disagree about WHEN the portfolio is formed
          -- a silent inconsistency that would run a different calendar than the
          paper stated while still reporting success. That's exactly the class
          of silent-empirical-drift bug the controlled pipeline exists to catch.
        - Quarterly/monthly are deliberately NOT validated here: their
          cohort-month sets are convention-dependent (which 4 months? fiscal vs
          calendar quarters?), and the engine must not invent a calendar the
          MethodSpec didn't state. Enforcing one would wrongly reject legitimate
          signals.
        - When `formation_month` was only DEFAULTED (not explicit in the spec),
          the signal's own cohort months are authoritative -- validating against
          a defaulted 6 would raise false positives for any non-June annual
          factor whose spec simply left formation_month unset.
        """
        if str(config.get("rebalance_frequency", "unspecified")).lower() != "annual":
            return
        if not config.get("formation_month_explicit"):
            return
        formation_month = config.get("formation_month")
        if formation_month is None:
            return
        if signal is None or signal.empty or "yyyymm" not in signal.columns:
            return
        cohort_months = {int(v) % 100 for v in signal["yyyymm"].dropna().unique()}
        off = sorted(cohort_months - {int(formation_month)})
        if off:
            raise ValueError(
                f"Annual strategy declares formation_month={int(formation_month)}, but "
                f"the signal has formation cohorts in month(s) {off} "
                f"(all cohort months: {sorted(cohort_months)}). For an annual "
                "rebalance the signal must form in the MethodSpec's stated month; "
                "this mismatch means the engine and the reviewed spec disagree on "
                "the formation calendar. Correct MethodSpec.formation_month or the "
                "signal's formation dates so they agree."
            )

    @staticmethod
    def _rebalance_step_months(config: dict) -> int | None:
        """Number of months between rebalances implied by
        `config["rebalance_frequency"]`, or None when unspecified/unknown (caller
        falls back to `holding_period_months`)."""
        freq = str(config.get("rebalance_frequency", "unspecified")).lower()
        return {"annual": 12, "quarterly": 3, "monthly": 1}.get(freq)

    # ------------------------------------------------------------------
    # Step 7: form_portfolios (breakpoints + assignment)
    # ------------------------------------------------------------------

    def form_portfolios(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 7: form portfolios from the merged signal panel -- computes
        breakpoints and assigns each stock to a group. Single-dimension
        continuous quantile sort (the vanilla Fama-French-style decile
        sort) by default; dispatches to the double-sort path instead when
        `config["sort_dims"]` has 2 entries (see `compute_breakpoints_multi`/
        `assign_portfolios_multi`) -- the discrete/categorical sort form,
        3+ dimensions, and the Fama-MacBeth estimator remain out of scope
        (see docs/decision-log.md).

        Breakpoints are computed from `self.formation` (the formation
        cross-section built by `apply_signal_holding_period`), NOT from `df`
        -- see `compute_breakpoints`'s docstring for why using the
        return-availability-filtered panel for the breakpoint population
        would leak future information into formation-time eligibility.
        Falls back to `df` when `self.formation` wasn't built (e.g. `self.merged`
        was set by hand for isolated testing, bypassing
        `apply_signal_holding_period`) -- that fallback reproduces the old,
        biased behavior, since the true formation population can't be
        reconstructed from the post-join panel alone.
        """
        df = self.merged if df is None else df
        config = self.config if config is None else config
        formation = self.formation if self.formation is not None else df

        if len(config.get("sort_dims") or []) >= 2:
            breakpoints = self.compute_breakpoints_multi(formation, config)
            portfolios = self.assign_portfolios_multi(df, breakpoints, config)
        else:
            breakpoints = self.compute_breakpoints(formation, config)
            portfolios = self.assign_portfolios(df, breakpoints, config)
        self.portfolios = portfolios
        self.trace.append("form_portfolios")
        return portfolios

    def compute_breakpoints(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """The numeric quantile cutoffs used to sort stocks into groups.

        Formation-locked (standard form-once-hold-fixed convention, matches
        Fama-French/Ken French Data Library/AQR-style factor replication):
        computed ONCE per formation `cohort` (the formation yyyymm
        `apply_signal_holding_period` tags every row with), not re-derived
        every current month. De-duplicating to one row per (permno, cohort)
        before quantiling is equivalent to computing breakpoints once at
        formation time -- which specific held month's row `drop_duplicates`
        keeps doesn't matter, since `signal` is constant across a cohort's
        held months by construction.

        `df` defaults to `self.formation` (NOT `self.merged`). `self.merged`
        is the signal panel AFTER an inner join with future held-month
        returns -- a permno with NO valid return in ANY of its held months
        (e.g. delisted immediately after formation) is entirely absent from
        it, so computing breakpoints from `self.merged` silently drops that
        permno from its own cohort's breakpoint population based on
        information (future return availability) that didn't exist at
        formation time -- a future-availability/survivorship leak. Falls
        back to `self.merged` only when `self.formation` was never built
        (see `form_portfolios`). See docs/decision-log.md for the fix this
        implements.
        """
        if df is None:
            df = self.formation if self.formation is not None else self.merged
        config = self.config if config is None else config

        n = int(config.get("breakpoint_quantiles", 10))
        src = config.get("breakpoint_source", "full_sample")

        if src == "nyse" and "exchcd" not in df.columns:
            raise ValueError(
                "config['breakpoint_source'] == 'nyse' requires an 'exchcd' column "
                "(exchcd == 1 selects NYSE-listed stocks) but the loaded returns panel "
                "has none -- this returns_universe isn't CRSP-shaped, or the column was "
                "dropped upstream. Register a real 'exchcd'-equivalent column for this "
                "returns universe, or use breakpoint_source='full_sample' instead."
            )
        bp_df = df[df["exchcd"] == 1].copy() if src == "nyse" else df.copy()
        bp_df = bp_df.drop_duplicates(subset=["permno", "cohort"]).dropna(subset=["signal"])

        if bp_df.empty:
            raise ValueError(
                f"No stocks available to compute breakpoints (breakpoint_source={src!r}). "
                + (
                    "No formation-time 'exchcd' value resolved to NYSE (exchcd == 1) for "
                    "any stock -- the returns panel likely never records a row at each "
                    "stock's own formation month (see apply_signal_holding_period's "
                    "docstring), so 'nyse' can't be evaluated point-in-time for this "
                    "panel. Use breakpoint_source='full_sample', or supply a returns "
                    "panel with a formation-month row for each signal."
                    if src == "nyse" else
                    "The formation signal cross-section is empty after dropping rows "
                    "with a missing signal value."
                )
            )

        quantile_vals = np.linspace(0, 1, n + 1)
        bp = (
            bp_df.groupby("cohort")["signal"]
            .quantile(quantile_vals)
            .unstack()
        )
        bp.columns = [f"q{i}" for i in range(n + 1)]
        self.breakpoints = bp
        return bp

    def assign_portfolios(
        self,
        df: pd.DataFrame | None = None,
        breakpoints: pd.DataFrame | None = None,
        config: dict | None = None,
    ) -> pd.DataFrame:
        """Which group each stock falls into, given the breakpoints.

        Formation-locked: looks up breakpoints by `cohort` (formation yyyymm)
        instead of the current `yyyymm`, so every row for a given cohort (across
        however many current months it's held) uses that cohort's own
        formation-date breakpoints and portfolio assignment stays fixed for the
        whole holding period -- it is never re-derived from a later month's
        cross-section.
        """
        df = self.merged if df is None else df
        breakpoints = self.breakpoints if breakpoints is None else breakpoints
        config = self.config if config is None else config

        n = int(config.get("breakpoint_quantiles", 10))
        chunks: list[pd.DataFrame] = []
        for cohort, group in df.groupby("cohort"):
            if cohort not in breakpoints.index:
                continue
            bp = breakpoints.loc[cohort]
            bins = [bp[f"q{i}"] for i in range(n + 1)]
            bins[0] = -np.inf
            bins[-1] = np.inf
            if len(set(bins)) != len(bins):
                # Degenerate cohort: too few distinct signal values in this
                # formation's cross-section to cut into `n` distinct groups
                # (duplicate quantile breakpoints). Skip forming portfolios for
                # this cohort rather than silently collapsing to fewer groups,
                # which would make its portfolio numbers mean something
                # different from every other (non-degenerate) cohort's.
                continue
            g = group.copy()
            g["portfolio"] = pd.cut(
                g["signal"], bins=bins, labels=range(1, n + 1), include_lowest=True
            )
            chunks.append(g)
        out = pd.concat(chunks) if chunks else pd.DataFrame()
        out = out.dropna(subset=["portfolio"]).copy() if chunks else out
        self.portfolios = out
        return out

    # ------------------------------------------------------------------
    # Step 7b: double sort (re-added -- see docs/decision-log.md 2026-07-24
    # for the original removal, and the D4 entry for why it came back:
    # Hirshleifer/Hsu/Li 2012's independent size x innovation-index sort
    # needs it. Deliberately narrow: independent or sequential (dependent-
    # on-dimension-0) sort, exactly 2 dimensions, quantile grouping only.
    # ------------------------------------------------------------------

    @staticmethod
    def _dimension_breakpoints(bp_df: pd.DataFrame, column: str, quantiles: int) -> pd.Series:
        """One cohort's breakpoint cutoffs for one sort dimension."""
        qs = np.linspace(0, 1, quantiles + 1)
        return bp_df[column].quantile(qs)

    @staticmethod
    def _assign_bucket(values: pd.Series, breakpoints: pd.Series, quantiles: int) -> pd.Series:
        bins = list(breakpoints.values)
        bins[0] = -np.inf
        bins[-1] = np.inf
        return pd.cut(values, bins=bins, labels=range(1, quantiles + 1), include_lowest=True)

    def compute_breakpoints_multi(self, df: pd.DataFrame | None = None, config: dict | None = None) -> list[dict]:
        """Multi-dim counterpart of `compute_breakpoints`.

        Dependent (`independent=False`) dimensions need breakpoints computed
        *within* dimension 0's bucket, which requires per-row assignment
        data this split doesn't have yet -- so this just returns
        `config["sort_dims"]` unchanged, and `assign_portfolios_multi` does
        the real per-dimension breakpoint + assignment work together. This
        still satisfies the `compute_breakpoints(df, config) -> breakpoints`
        / `assign_portfolios(df, breakpoints, config) -> df` contract shape
        without duplicating logic between the two methods.
        """
        config = self.config if config is None else config
        dims = config.get("sort_dims") or []
        self.breakpoints = dims
        return dims

    def assign_portfolios_multi(
        self,
        df: pd.DataFrame | None = None,
        breakpoints: list[dict] | None = None,
        config: dict | None = None,
    ) -> pd.DataFrame:
        """N-dimensional (currently: 2) sort assignment, formation-locked.

        Unlike the original (removed) `assign_portfolios_multi`, this derives
        breakpoints from `self.formation` (not from `df`/`self.merged`) --
        same reasoning as the single-dim `compute_breakpoints`: `self.merged`
        has already been inner-joined against future held-month returns, so
        computing cutoffs from it would leak future-return-availability into
        the formation-time breakpoint population. `self.formation` is used
        ONLY to derive each cohort's cutoffs; the actual bucket assignment
        (via those cutoffs) is then applied to `df` (`self.merged`), the
        population that actually gets sorted/traded -- matching the
        single-dim path's formation-locked-breakpoints fix (see
        docs/decision-log.md; the original double-sort removal's own
        trade-offs note flagged this as needed if double sorts ever came
        back).

        `breakpoints` is the resolved `sort_dims` list from
        `compute_breakpoints_multi` (each: {column, quantiles, source,
        independent}), in the paper's specified dimension order -- dimension
        0's cutoffs are always computed on its own configured universe
        (nyse/full_sample); dimension i>0 is either independent (its own
        cutoffs on its own universe) or dependent (cutoffs computed
        separately within each dimension-0 formation bucket -- the standard
        convention for e.g. a size-then-value sequential double sort).
        Deliberately scoped to condition only on dimension 0 (not the
        running intersection of all prior dimensions), which covers the
        common 2-way double sort.

        Output columns: `portfolio_0`, `portfolio_1` (plus the original
        columns). No combined string label is produced;
        `compute_portfolio_returns_multi`/`combine_portfolio_returns_multi`
        group on the `portfolio_i` columns directly.
        """
        df = self.merged if df is None else df
        dims = self.breakpoints if breakpoints is None else breakpoints
        config = self.config if config is None else config
        formation = self.formation if self.formation is not None else df

        if not dims:
            self.portfolios = pd.DataFrame()
            return self.portfolios

        for dim in dims:
            if dim.get("mode") == "within_group":
                raise ValueError(
                    "sort_dims entry has mode='within_group', which "
                    "assign_portfolios_multi does not implement (only "
                    "independent/sequential) -- see docs/resolve-diagnostics-"
                    "gaps.md problem 2. Never silently treated as sequential."
                )

        chunks: list[pd.DataFrame] = []
        for cohort, cohort_df in df.groupby("cohort"):
            cohort_df = cohort_df.copy()
            if cohort not in formation["cohort"].values:
                continue
            formation_cohort = formation[formation["cohort"] == cohort]

            dim0 = dims[0]
            bp_universe0 = (
                formation_cohort[formation_cohort["exchcd"] == 1]
                if dim0.get("source") == "nyse" else formation_cohort
            )
            bp_universe0 = bp_universe0.dropna(subset=[dim0["column"]])
            if bp_universe0.empty:
                continue
            bp0 = self._dimension_breakpoints(bp_universe0, dim0["column"], dim0["quantiles"])
            if len(set(bp0.values)) != len(bp0.values):
                # Degenerate cohort for dimension 0 (too few distinct values
                # to cut into the requested groups) -- skip, same policy as
                # the single-dim path's degenerate-cohort handling.
                continue
            cohort_df["portfolio_0"] = self._assign_bucket(cohort_df[dim0["column"]], bp0, dim0["quantiles"])
            formation_cohort = formation_cohort.copy()
            formation_cohort["portfolio_0"] = self._assign_bucket(
                formation_cohort[dim0["column"]], bp0, dim0["quantiles"]
            )

            for i, dim in enumerate(dims[1:], start=1):
                col = dim["column"]
                nq = dim["quantiles"]
                src = dim.get("source", "full_sample")
                independent = dim.get("independent", True)

                if independent:
                    bp_universe_i = (
                        formation_cohort[formation_cohort["exchcd"] == 1]
                        if src == "nyse" else formation_cohort
                    )
                    bp_universe_i = bp_universe_i.dropna(subset=[col])
                    if bp_universe_i.empty:
                        cohort_df[f"portfolio_{i}"] = np.nan
                        continue
                    bp_i = self._dimension_breakpoints(bp_universe_i, col, nq)
                    cohort_df[f"portfolio_{i}"] = self._assign_bucket(cohort_df[col], bp_i, nq)
                else:
                    # Dependent on dimension 0: compute this dimension's
                    # cutoffs separately within each of formation's own
                    # dimension-0 buckets, then apply the matching bucket's
                    # cutoffs to `cohort_df` rows sharing that same bucket.
                    assigned = pd.Series(index=cohort_df.index, dtype="float64")
                    for bucket, bucket_formation in formation_cohort.groupby("portfolio_0", observed=True):
                        bp_universe_i = (
                            bucket_formation[bucket_formation["exchcd"] == 1]
                            if src == "nyse" else bucket_formation
                        )
                        bp_universe_i = bp_universe_i.dropna(subset=[col])
                        if bp_universe_i.empty:
                            continue
                        bp_i = self._dimension_breakpoints(bp_universe_i, col, nq)
                        bucket_rows = cohort_df["portfolio_0"] == bucket
                        assigned.loc[bucket_rows] = self._assign_bucket(
                            cohort_df.loc[bucket_rows, col], bp_i, nq
                        ).astype(float)
                    cohort_df[f"portfolio_{i}"] = assigned

            chunks.append(cohort_df)

        if not chunks:
            self.portfolios = pd.DataFrame()
            return self.portfolios

        out = pd.concat(chunks)
        portfolio_cols = [f"portfolio_{i}" for i in range(len(dims))]
        out = out.dropna(subset=portfolio_cols).copy()
        self.portfolios = out
        return out

    # ------------------------------------------------------------------
    # Step 8: compute_portfolio_returns
    # ------------------------------------------------------------------

    def compute_portfolio_returns(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 8: each portfolio's OWN monthly return (not yet combined into
        a single reported series -- that's `combine_portfolio_returns`,
        Step 9) -- value-weighted (by PRIOR-month `me`) or equal-weighted,
        selected by `config["weighting_rule"]` (vw/ew).

        Dispatches to `compute_portfolio_returns_multi` when `self.portfolios`
        carries `portfolio_0`/`portfolio_1` columns (the double-sort path;
        see `form_portfolios`) instead of the single `portfolio` column.

        Value-weighting uses each stock's market equity as of the PRIOR
        month-end (`me_{t-1}`), not the same month `t` whose return is being
        weighted -- see `_attach_lagged_me`. Weighting month-`t` returns by
        month-`t` end-of-month market cap would be a subtle look-ahead: the
        end-of-`t` cap already reflects the very return being weighted, so a
        winner gets a mechanically larger weight in the same month it won
        (e.g. two stocks +10%/-10% from equal starting caps net to 0% under
        prior-month weights but a spurious +1% under same-month weights).
        See docs/decision-log.md for the fix this implements.
        """
        df = self.portfolios if df is None else df
        config = self.config if config is None else config

        if "portfolio_0" in df.columns:
            return self.compute_portfolio_returns_multi(df, config)

        wt = config.get("weighting_rule", "vw")
        df = df.copy()
        df["portfolio"] = df["portfolio"].astype(int)

        if wt == "vw" and "me" not in df.columns:
            raise ValueError(
                "config['weighting_rule'] == 'vw' requires an 'me' (market equity) "
                "column for value-weighting but the loaded returns panel has none -- "
                "this returns_universe doesn't supply market equity under that name, "
                "or the column was dropped upstream. Register the market-equity column "
                "for this returns universe, or use weighting_rule='ew' instead."
            )
        if wt == "vw":
            df = self._attach_lagged_me(df)
            # A held row whose prior-month ME couldn't be resolved is EXCLUDED
            # from that month's value-weighting (you can't value-weight a
            # stock with no market cap) rather than silently reweighted by a
            # look-ahead-prone same-month cap. Record the missing fraction as
            # a coverage diagnostic (surfaced in metrics).
            self._vw_lag_me_missing_frac = (
                float(df["me_lag"].isna().mean()) if len(df) else 0.0
            )

            def _vw(g: pd.DataFrame) -> float:
                me_lag = g["me_lag"]
                valid = me_lag.notna() & (me_lag > 0)
                if not valid.any():
                    return float("nan")
                w = me_lag[valid]
                r = g["ret"][valid]
                return float((r * w).sum() / w.sum())

            rets = (
                df.groupby(["yyyymm", "portfolio"])
                .apply(_vw)
                .reset_index(name="ret")
            )
        else:
            self._vw_lag_me_missing_frac = None
            rets = (
                df.groupby(["yyyymm", "portfolio"])["ret"]
                .mean()
                .reset_index()
            )

        self.returns = rets
        self.trace.append("compute_portfolio_returns")
        return rets

    def compute_portfolio_returns_multi(self, df: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Multi-dim counterpart of `compute_portfolio_returns`: VW (via the
        same prior-month-lagged `me` as the single-dim path -- see
        `_attach_lagged_me`) or EW return for each joint
        (yyyymm, portfolio_0, portfolio_1) cell.
        """
        df = self.portfolios if df is None else df
        config = self.config if config is None else config

        wt = config.get("weighting_rule", "vw")
        df = df.copy()
        portfolio_cols = [c for c in df.columns if c.startswith("portfolio_")]
        for c in portfolio_cols:
            df[c] = df[c].astype(int)
        group_cols = ["yyyymm"] + portfolio_cols

        if wt == "vw" and "me" not in df.columns:
            raise ValueError(
                "config['weighting_rule'] == 'vw' requires an 'me' (market equity) "
                "column for value-weighting but the loaded returns panel has none."
            )
        if wt == "vw":
            df = self._attach_lagged_me(df)
            self._vw_lag_me_missing_frac = float(df["me_lag"].isna().mean()) if len(df) else 0.0

            def _vw(g: pd.DataFrame) -> float:
                me_lag = g["me_lag"]
                valid = me_lag.notna() & (me_lag > 0)
                if not valid.any():
                    return float("nan")
                w = me_lag[valid]
                r = g["ret"][valid]
                return float((r * w).sum() / w.sum())

            rets = df.groupby(group_cols).apply(_vw).reset_index(name="ret")
        else:
            self._vw_lag_me_missing_frac = None
            rets = df.groupby(group_cols)["ret"].mean().reset_index()

        self.returns = rets
        self.trace.append("compute_portfolio_returns")
        return rets

    def _attach_lagged_me(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach a `me_lag` column: each held row's market equity as of the
        PRIOR calendar month (`me_{t-1}`), for value-weighting month-`t`
        returns without the same-month look-ahead (see
        `compute_portfolio_returns`).

        Prior-month `me` is looked up from `self._pre_missing_policy_data`
        (falling back to `self.data`) -- the fullest available `[permno,
        yyyymm, me]` time series, so month `t-1` is found even when it isn't
        one of the held rows in `df` (e.g. `t` is the first held month and
        `t-1` is the formation month). When a prior-month `me` genuinely
        can't be found (the panel never recorded that stock-month), `me_lag`
        is left `NaN` -- the caller (`compute_portfolio_returns`) EXCLUDES
        those rows from value-weighting rather than falling back to the
        row's own current-month `me` (which would reintroduce the same-month
        look-ahead this method exists to remove) and reports the missing
        fraction as a coverage diagnostic.
        """
        source = self._pre_missing_policy_data if self._pre_missing_policy_data is not None else self.data
        out = df.copy()
        month = out["yyyymm"] % 100
        out["_prev_yyyymm"] = np.where(
            month == 1, (out["yyyymm"] // 100 - 1) * 100 + 12, out["yyyymm"] - 1
        )
        if source is not None and "me" in source.columns:
            me_lag = (
                source[["permno", "yyyymm", "me"]]
                .rename(columns={"yyyymm": "_prev_yyyymm", "me": "me_lag"})
                .drop_duplicates(subset=["permno", "_prev_yyyymm"])
            )
            out = out.merge(me_lag, on=["permno", "_prev_yyyymm"], how="left")
        else:
            out["me_lag"] = np.nan
        return out.drop(columns=["_prev_yyyymm"])

    # ------------------------------------------------------------------
    # Step 9: combine_portfolio_returns
    # ------------------------------------------------------------------

    def combine_portfolio_returns(self, rets: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Step 9: combine Step 8's per-portfolio returns into the final
        reported return series. Despite the common `long_short` mental model,
        this is NOT always a long-minus-short spread -- the actual behavior
        is selected via `config["return_combination_type"]`
        (default `"extreme_group_spread"`):
          - `extreme_group_spread` (default): single top portfolio minus single
            bottom portfolio. (long - short)
          - `average_leg_spread`: average of `config["long_portfolios"]` minus
            average of `config["short_portfolios"]` (explicit portfolio-number
            lists) -- defaults to the same single top/bottom pair as
            extreme_group_spread when those aren't given. (long - short)
          - `single_signal_portfolio_return`: report one portfolio's return
            as-is (`config["single_portfolio"]`, default: the "long" extreme),
            no spread -- NOT long-short.
          - `full_portfolio_return`: report every portfolio's return untouched,
            no combination -- NOT long-short; consumed differently by
            `compute_metrics` (no single `ls_return`/t-stat; see there).

        Dispatches to `combine_portfolio_returns_multi` when `rets` carries
        `portfolio_0`/`portfolio_1` columns (the double-sort path).
        """
        rets = self.returns if rets is None else rets
        config = self.config if config is None else config

        if "portfolio_0" in rets.columns:
            return self.combine_portfolio_returns_multi(rets, config)

        combo = config.get("return_combination_type", "extreme_group_spread")
        n = int(config.get("breakpoint_quantiles", 10))
        long_leg = config.get("long_leg", "low")

        default_long_port  = 1 if long_leg == "low" else n
        default_short_port = n if long_leg == "low" else 1

        if combo == "full_portfolio_return":
            out = rets.copy()
        elif combo == "single_signal_portfolio_return":
            single = config.get("single_portfolio", default_long_port)
            rows: list[dict] = []
            for yyyymm, g in rets.groupby("yyyymm"):
                port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
                if single in port_map:
                    rows.append({"yyyymm": yyyymm, "ls_return": port_map[single]})
            out = pd.DataFrame(rows)
        else:
            # extreme_group_spread / average_leg_spread: both are
            # "average(long legs) - average(short legs)"; extreme_group_spread
            # is just the 1-leg case.
            long_ports = config.get("long_portfolios") or [default_long_port]
            short_ports = config.get("short_portfolios") or [default_short_port]

            rows = []
            for yyyymm, g in rets.groupby("yyyymm"):
                port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
                long_vals = [port_map[p] for p in long_ports if p in port_map]
                short_vals = [port_map[p] for p in short_ports if p in port_map]
                if long_vals and short_vals:
                    rows.append({
                        "yyyymm": yyyymm,
                        "ls_return": float(np.mean(long_vals)) - float(np.mean(short_vals)),
                    })
            out = pd.DataFrame(rows)

        self.long_short = out
        self.trace.append("combine_portfolio_returns")
        return out

    def combine_portfolio_returns_multi(self, rets: pd.DataFrame | None = None, config: dict | None = None) -> pd.DataFrame:
        """Multi-dim counterpart of `combine_portfolio_returns`: the standard
        "average across control-dimension groups" double-sort convention.

        Finds whichever `config["sort_dims"]` entry has `role == "target"`
        (the paper's own characteristic being studied -- see
        `SortDimension.role` in `method_spec.py`), computes its
        extreme-decile spread separately within every combination of the
        OTHER ("control"/"conditioning") dimensions, then averages those
        spreads -- e.g. for a characteristic x size sort, this is "average
        the characteristic spread across size groups", the standard
        construction in the literature (Fama-French SMB/HML, Hirshleifer et
        al 2012's innovation-efficiency factor, etc.).

        Output shape matches the single-dim path's (`yyyymm`, `ls_return`),
        so `compute_metrics` needs no changes to consume either path.
        """
        rets = self.returns if rets is None else rets
        config = self.config if config is None else config

        dims = config.get("sort_dims") or []
        if not dims:
            self.long_short = pd.DataFrame()
            return self.long_short

        signal_idx = next((i for i, d in enumerate(dims) if d.get("role") == "target"), 0)
        signal_col = f"portfolio_{signal_idx}"
        n_signal = dims[signal_idx]["quantiles"]
        other_cols = [f"portfolio_{i}" for i in range(len(dims)) if i != signal_idx]

        long_leg = config.get("long_leg", "low")
        long_bucket  = 1 if long_leg == "low" else n_signal
        short_bucket = n_signal if long_leg == "low" else 1

        rows: list[dict] = []
        for yyyymm, g in rets.groupby("yyyymm"):
            spreads: list[float] = []
            if other_cols:
                for _, sub in g.groupby(other_cols):
                    port_map = dict(zip(sub[signal_col], sub["ret"]))
                    if long_bucket in port_map and short_bucket in port_map:
                        spreads.append(port_map[long_bucket] - port_map[short_bucket])
            else:
                port_map = dict(zip(g[signal_col], g["ret"]))
                if long_bucket in port_map and short_bucket in port_map:
                    spreads.append(port_map[long_bucket] - port_map[short_bucket])
            if spreads:
                rows.append({"yyyymm": yyyymm, "ls_return": float(np.mean(spreads))})

        out = pd.DataFrame(rows)
        self.long_short = out
        self.trace.append("combine_portfolio_returns")
        return out

    # ------------------------------------------------------------------
    # Step 10: compute_metrics
    # ------------------------------------------------------------------

    def compute_metrics(self, ls: pd.DataFrame | None = None, config: dict | None = None) -> dict[str, Any]:
        """Step 10: summary statistics — mean monthly return, Newey-West
        t-stat (is the return statistically distinguishable from zero, given
        that monthly returns are autocorrelated), Sharpe, and how many
        months of data went into it.

        `full_portfolio_return` combination has no single `ls_return` spread
        to summarize this way -- `ls` is the full per-portfolio grid instead,
        so this reports basic coverage diagnostics for it rather than a
        mean/t-stat (the full grid itself is always available in
        `return_series`).

        Sample-period segmentation: when `config` carries
        `sample_start_year`/`sample_end_year`/`publication_year`, a nested
        `by_sample_period` dict is added with the same mean/t-stat computed
        separately over the paper's in-sample window, the
        sample-end-to-publication gap, and the post-publication period.
        """
        ls = self.long_short if ls is None else ls
        config = self.config if config is None else config

        if "ls_return" not in ls.columns:
            if ls.empty:
                metrics = {"n_months": 0, "portfolios": [], "note": "full_portfolio_return: empty result"}
            else:
                metrics = {
                    "n_months": int(ls["yyyymm"].nunique()),
                    "portfolios": sorted(ls["portfolio"].dropna().astype(int).unique().tolist()),
                    "note": (
                        "full_portfolio_return: no single long-short spread computed; "
                        "see return_series for per-portfolio returns"
                    ),
                }
        else:
            series = ls["ls_return"].dropna()
            metrics = self._series_metrics(series)

            by_period = self._sample_period_metrics(ls, config)
            if by_period is not None:
                metrics["by_sample_period"] = by_period

        if getattr(self, "_vw_lag_me_missing_frac", None) is not None:
            metrics["vw_lagged_me_missing_frac"] = self._vw_lag_me_missing_frac

        self.metrics = metrics
        self.trace.append("compute_metrics")
        return metrics

    @staticmethod
    def _series_metrics(series: pd.Series) -> dict[str, Any]:
        """Mean / Newey-West t-stat / Sharpe / n_months for one return series.

        Factored out of `compute_metrics` so the whole-sample series and each
        sample-period segment share one implementation."""
        n = len(series)
        if n < 2:
            return {"mean_monthly_return": float("nan"), "t_stat": float("nan"), "n_months": n}

        mean_ret = float(series.mean())
        std_ret = float(series.std())
        lags = min(6, n - 1)
        nw_var = BacktestExecutor._newey_west_var(series.values, lags)
        t_stat = mean_ret / np.sqrt(nw_var / n) if nw_var > 0 else float("nan")
        # Guard against floating-point noise on a (near-)constant series producing
        # a tiny-but-nonzero std that blows up the ratio instead of dividing by
        # the intended zero.
        sharpe = (mean_ret / std_ret * np.sqrt(12)) if std_ret > 1e-12 else float("nan")

        return {
            "mean_monthly_return": mean_ret,
            "annualized_return":   mean_ret * 12,
            "t_stat":              float(t_stat),
            "n_months":            n,
            "sharpe_ratio":        float(sharpe),
        }

    @staticmethod
    def _sample_period_segments(ls: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
        """Same year-boundary logic as `_sample_period_metrics`, but returns
        each segment's full DataFrame (`yyyymm` + `ls_return`), not just the
        return Series -- needed so `compute_factor_alphas` can merge each
        segment against `factors` on `yyyymm` too. Deliberately a separate
        function (not shared internals with `_sample_period_metrics`) so a
        bug here can never change that function's existing
        (golden-number-tested) mean/t-stat output.
        """
        start = config.get("sample_start_year")
        end = config.get("sample_end_year")
        pub = config.get("publication_year")
        if start is None and end is None and pub is None:
            return {}
        if "ls_return" not in ls.columns:
            return {}
        df = ls.dropna(subset=["ls_return"]).copy()
        if df.empty:
            return {}
        year = (df["yyyymm"] // 100).astype(int)

        segments: dict[str, pd.DataFrame] = {}
        if start is not None or end is not None:
            lo = start if start is not None else -np.inf
            hi = end if end is not None else np.inf
            segments["insamp"] = df.loc[(year >= lo) & (year <= hi)]
        if end is not None and pub is not None:
            segments["between"] = df.loc[(year > end) & (year <= pub)]
        if pub is not None:
            segments["postpub"] = df.loc[year > pub]
        return {name: seg for name, seg in segments.items() if not seg.empty}

    @staticmethod
    def _sample_period_metrics(ls: pd.DataFrame, config: dict) -> dict[str, Any] | None:
        """Split the long-short series into in-sample / between / post-publication
        segments and compute `_series_metrics` for each.

        Segments (by calendar year of each month):
          - insamp:  sample_start_year <= year <= sample_end_year
          - between: sample_end_year   <  year <= publication_year
          - postpub: year > publication_year

        Returns None (so `compute_metrics` omits the nested dict entirely) when no
        sample window is configured. `between`/`postpub` are omitted individually
        when `publication_year` isn't known. Segments with no months are skipped.
        """
        start = config.get("sample_start_year")
        end = config.get("sample_end_year")
        pub = config.get("publication_year")
        if start is None and end is None and pub is None:
            return None

        df = ls.dropna(subset=["ls_return"]).copy()
        if df.empty:
            return None
        year = (df["yyyymm"] // 100).astype(int)

        segments: dict[str, pd.Series] = {}
        if start is not None or end is not None:
            lo = start if start is not None else -np.inf
            hi = end if end is not None else np.inf
            segments["insamp"] = df.loc[(year >= lo) & (year <= hi), "ls_return"]
        if end is not None and pub is not None:
            segments["between"] = df.loc[(year > end) & (year <= pub), "ls_return"]
        if pub is not None:
            segments["postpub"] = df.loc[year > pub, "ls_return"]

        out: dict[str, Any] = {}
        for name, seg in segments.items():
            if len(seg) > 0:
                out[name] = BacktestExecutor._series_metrics(seg)
        return out or None

    @staticmethod
    def _newey_west_var(x: np.ndarray, lags: int) -> float:
        """Newey-West variance estimate for a demeaned series."""
        n = len(x)
        xd = x - x.mean()
        nw = float(np.dot(xd, xd)) / n
        for lag in range(1, lags + 1):
            w = 1.0 - lag / (lags + 1)
            gamma = float(np.dot(xd[lag:], xd[:-lag])) / n
            nw += 2.0 * w * gamma
        return max(nw, 0.0)

    # ------------------------------------------------------------------
    # Extra step (only when factor data supplied): compute_factor_alphas
    # ------------------------------------------------------------------

    def compute_factor_alphas(
        self,
        ls: pd.DataFrame | None = None,
        factors: pd.DataFrame | None = None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        """Regress the combined return series on factor returns for CAPM/FF3/FF5
        alpha estimates, using `statsmodels` OLS with Newey-West (HAC) standard
        errors -- independent of the hand-rolled Newey-West t-stat
        `compute_metrics` uses for the primary spread (kept unchanged there for
        golden-number stability).

        Args:
            ls: the combined return series from `combine_portfolio_returns` (must
                have an `ls_return` column -- returns {} for the
                `full_portfolio_return` shape, which has no single series to
                regress).
            factors: DataFrame with a `yyyymm` column plus whichever of
                `mktrf`/`smb`/`hml`/`rmw`/`cma`/`ps_vwf` are available (see
                `scripts/fetch_ff_factors.py` / `load_liquidity_factors`).
                CAPM needs `mktrf`; FF3 needs `mktrf`+`smb`+`hml`; FF5 adds
                `rmw`+`cma`; the liquidity model (`alpha_liq`) needs only
                `ps_vwf`. An alpha is silently omitted if its required
                columns aren't present.

        Returns {} (no error) if `statsmodels` isn't installed -- it's an
        optional `research` dependency (see pyproject.toml), not a core one, so
        the rest of the engine works without it.
        """
        ls = self.long_short if ls is None else ls
        factors = self.factors if factors is None else factors
        config = self.config if config is None else config

        if "ls_return" not in ls.columns or factors is None or factors.empty:
            return {}
        try:
            import statsmodels.api as sm
        except ImportError:
            return {}

        merged = ls.merge(factors, on="yyyymm", how="inner")
        if len(merged) < 3:
            return {}

        results: dict[str, Any] = {}

        factor_specs = {
            "capm": ["mktrf"],
            "ff3": ["mktrf", "smb", "hml"],
            "ff5": ["mktrf", "smb", "hml", "rmw", "cma"],
            #: Pastor-Stambaugh (2003) traded liquidity factor -- independent
            #: one-factor model, only computed when `factors` actually
            #: carries `ps_vwf` (see `load_liquidity_factors`/
            #: `script_generator.py`'s `load_factors()`, 2026-08-13).
            "liq": ["ps_vwf"],
        }
        for name, cols in factor_specs.items():
            if not all(c in merged.columns for c in cols):
                continue
            sample = merged[["ls_return", *cols]].replace([np.inf, -np.inf], np.nan).dropna()
            n = len(sample)
            if n < 3:
                continue
            y = sample["ls_return"].to_numpy()
            lags = min(6, n - 2)
            x = sm.add_constant(sample[cols].to_numpy())
            model = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
            results[f"alpha_{name}"] = float(model.params[0])
            results[f"alpha_{name}_tstat"] = float(model.tvalues[0])
            for i, col in enumerate(cols, start=1):
                results[f"beta_{name}_{col}"] = float(model.params[i])

        return results
