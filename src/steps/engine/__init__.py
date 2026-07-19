"""Controlled Backtesting Lifecycle Engine - Fixed empirical pipeline.

Steps are executed in a fixed order. Each step either runs a standard
implementation (parameterised by config) or calls a hook function from the
signal plugin when the MethodSpec requires non-standard logic.

Hook dispatch pattern (each step):
    fn = self._hooks.get("step_name", self._standard_step)
    result = fn(data, config)
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.infra.models.method_spec import (
    BreakpointSource,
    MissingAction,
    MethodSpec,
    WeightingRule,
)


# ---------------------------------------------------------------------------
# Standard set — values for which BacktestEngine has a built-in implementation.
# Anything outside triggers a hook request to MetaCoder.
# ---------------------------------------------------------------------------

STANDARD: dict[str, set[str]] = {
    "breakpoint_source": {"full_sample", "nyse"},
    "weighting":         {"vw", "ew"},
    "missing_action":    {"drop", "unspecified"},
}


def _ev(v: Any) -> str:
    """Return string value of an enum or plain string."""
    if hasattr(v, "value"):
        return v.value
    return str(v) if v is not None else "unspecified"


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


class BacktestEngine:
    """Controlled backtesting lifecycle engine.

    Executes the fixed empirical pipeline. Standard steps are built-in;
    non-standard steps call hook functions loaded from the signal plugin.

    Steps (order is frozen):
      1. load_data          — load msf.parquet
      2. apply_missing_policy — drop / winsorize
      3. filter_universe    — shrcd / exchcd / sic / seasoning
      4. merge_signal       — expand annual signal to monthly holding period
      5. compute_breakpoints — quantile breakpoints (full_sample or NYSE)
      6. assign_portfolios  — cut stocks into decile/quintile groups
      7. compute_returns    — VW or EW portfolio returns
      8. compute_long_short — extreme-leg spread
      9. compute_metrics    — mean, Newey-West t-stat, coverage
    """

    def __init__(self, data_path: str | None = None):
        self.data_path = Path(data_path) if data_path else Path("./data")
        self._hooks: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Hook detection
    # ------------------------------------------------------------------

    @classmethod
    def _detect_hooks(cls, spec: MethodSpec) -> dict[str, str]:
        """Return {step_name: reason} for steps that need LLM-generated hooks.

        Compares resolved MethodSpec field values against STANDARD sets.
        Steps whose value falls outside STANDARD require a hook function.
        """
        hooks: dict[str, str] = {}

        bp = _ev(spec.breakpoint_source)
        if bp not in STANDARD["breakpoint_source"]:
            hooks["compute_breakpoints"] = f"non-standard breakpoint_source={bp!r}"

        wt = _ev(spec.weighting_rule)
        if wt not in STANDARD["weighting"]:
            hooks["compute_returns"] = f"non-standard weighting={wt!r}"

        ma = _ev(spec.missing_action)
        if ma not in STANDARD["missing_action"]:
            hooks["apply_missing_policy"] = f"non-standard missing_action={ma!r}"

        universe = (spec.portfolio.universe or "").lower()
        if any(k in universe for k in ("industry", "neutral", "size-adj", "conditional")):
            hooks["filter_universe"] = f"non-standard universe: {spec.portfolio.universe[:80]}"

        pf = (spec.portfolio.filter or "").lower()
        if any(k in pf for k in ("double", "conditional", "interact", "two-way")):
            hooks["compute_breakpoints"] = "double/conditional sort"
            hooks["assign_portfolios"] = "double/conditional sort"

        long_leg_text = str(spec.portfolio.long_leg or "").lower()
        short_leg_text = str(spec.portfolio.short_leg or "").lower()
        if any(
            "average of" in t or " and " in t
            for t in (long_leg_text, short_leg_text)
        ):
            hooks["compute_long_short"] = "multi-leg long/short combination (e.g. double-sort average)"

        return hooks

    # ------------------------------------------------------------------
    # Config builder
    # ------------------------------------------------------------------

    def _build_config(self, spec: MethodSpec, overrides: dict | None) -> dict:
        """Build run config entirely from resolved MethodSpec fields."""

        def effective(val: Any, default: str) -> str:
            v = _ev(val)
            return v if v != "unspecified" else default

        # ls_quantile > 1 means "N groups"; < 1 means it's a fraction (1/N groups)
        ls_q = spec.portfolio.breakpoints.ls_quantile or 10.0
        n_quantiles = int(ls_q) if ls_q >= 1 else int(round(1.0 / ls_q))

        config = {
            "breakpoint_source":    effective(spec.breakpoint_source, "full_sample"),
            "breakpoint_quantiles": n_quantiles,
            "weighting_rule":       effective(spec.weighting_rule, "vw"),
            "rebalance_frequency":  _ev(spec.rebalance_frequency),
            "holding_period_months": spec.holding_period_months or 12,
            "accounting_lag_months": spec.accounting_lag_months or 6,
            "missing_action":       effective(spec.missing_action, "drop"),
            "universe":             spec.universe_description,
            "formation_month":      spec.formation_month or 6,
            "skip_month":           spec.skip_month or 0,
            "long_leg":             self._resolve_long_leg(spec),
            "short_leg":            self._resolve_short_leg(spec),
        }
        if overrides:
            config.update(overrides)
        return config

    @staticmethod
    def _resolve_long_leg(spec: MethodSpec) -> str:
        ifd = spec.portfolio.implied_factor_direction
        raw = ifd.get("long_leg") if isinstance(ifd, dict) else None
        raw = raw or spec.portfolio.long_leg
        return BacktestEngine._normalize_leg(raw, default="low")

    @staticmethod
    def _resolve_short_leg(spec: MethodSpec) -> str:
        ifd = spec.portfolio.implied_factor_direction
        raw = ifd.get("short_leg") if isinstance(ifd, dict) else None
        raw = raw or spec.portfolio.short_leg
        return BacktestEngine._normalize_leg(raw, default="high")

    @staticmethod
    def _normalize_leg(value: Any, default: str) -> str:
        """Map a leg descriptor to the 'low'/'high' token used by _compute_long_short.

        MethodSpec long_leg/short_leg fields are often free-text descriptions
        (e.g. "lowest asset-growth decile") rather than the bare 'low'/'high'
        tokens BacktestEngine expects, so match by substring instead of
        equality.
        """
        text = str(value or "").lower()
        if "low" in text:
            return "low"
        if "high" in text:
            return "high"
        return default

    # ------------------------------------------------------------------
    # Hook loader
    # ------------------------------------------------------------------

    def _load_hooks(self, plugin) -> dict[str, Any]:
        """Exec plugin code and extract hook callables."""
        if plugin is None:
            return {}
        ns: dict = {}
        exec(  # noqa: S102
            compile(plugin.code, f"<plugin:{plugin.factor_id}>", "exec"), ns
        )
        loaded: dict[str, Any] = {}
        for step in [
            "filter_universe",
            "compute_breakpoints",
            "assign_portfolios",
            "compute_returns",
            "apply_missing_policy",
            "compute_long_short",
        ]:
            fn_name = f"{step}_hook"
            if fn_name in ns and callable(ns[fn_name]):
                loaded[step] = ns[fn_name]
        return loaded

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        signal: pd.DataFrame,
        spec: MethodSpec,
        config_overrides: dict[str, Any] | None = None,
        plugin=None,
    ) -> dict[str, Any]:
        """Execute controlled backtest lifecycle on a signal.

        Args:
            signal:          DataFrame [permno, yyyymm, signal] from compute_signal()
            spec:            Approved MethodSpec (all decisions resolved in spec fields)
            config_overrides: Optional per-run overrides (for ablation experiments)
            plugin:          PluginRecord — source of hook functions

        Returns:
            Dict with keys: metrics, return_series, config
        """
        config = self._build_config(spec, config_overrides)
        self._hooks = self._load_hooks(plugin)

        data      = self._load_data(config)
        data      = self._dispatch("apply_missing_policy", data, config)
        data      = self._dispatch("filter_universe", data, config)
        merged    = self._merge_signal(data, signal, config)
        bps       = self._dispatch("compute_breakpoints", merged, config)
        ports     = self._dispatch_assign(merged, bps, config)
        rets      = self._dispatch("compute_returns", ports, config)
        ls        = self._dispatch("compute_long_short", rets, config)
        metrics   = self._compute_metrics(ls, config)

        return {"metrics": metrics, "return_series": ls, "config": config}

    def _dispatch(self, step: str, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        """Call hook if present, else standard implementation."""
        if step in self._hooks:
            return self._hooks[step](df, config)
        return getattr(self, f"_{step}")(df, config)

    def _dispatch_assign(
        self, df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        if "assign_portfolios" in self._hooks:
            return self._hooks["assign_portfolios"](df, breakpoints, config)
        return self._assign_portfolios(df, breakpoints, config)

    # ------------------------------------------------------------------
    # Standard step implementations
    # ------------------------------------------------------------------

    def _load_data(self, config: dict) -> pd.DataFrame:
        msf_path = self.data_path / "local" / "msf.parquet"
        if not msf_path.exists():
            raise FileNotFoundError(
                f"MSF data not found at {msf_path}. "
                "Export CRSP monthly from WRDS and place it there."
            )
        df = pd.read_parquet(msf_path)
        if "date" in df.columns and "yyyymm" not in df.columns:
            df["yyyymm"] = (
                pd.to_datetime(df["date"]).dt.year * 100
                + pd.to_datetime(df["date"]).dt.month
            )
        for col in ("permno", "yyyymm"):
            df[col] = df[col].astype(int)
        return df

    def _apply_missing_policy(self, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        action = config.get("missing_action", "drop")
        if action in ("drop", "unspecified"):
            return df.dropna(subset=["ret"]).copy()
        # winsorize / fill_* handled by hook
        return df

    def _filter_universe(self, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        mask = (
            df["shrcd"].isin([10, 11])
            & df["exchcd"].isin([1, 2, 3])
        )
        if "siccd" in df.columns:
            mask &= ~df["siccd"].between(6000, 6999)
        return df[mask].copy()

    def _merge_signal(
        self, df: pd.DataFrame, signal: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        """Expand annual signal to monthly holding period and join with msf."""
        hp = int(config.get("holding_period_months", 12))
        rows: list[dict] = []
        for _, row in signal.iterrows():
            yyyymm = int(row["yyyymm"])
            year, month = divmod(yyyymm, 100)
            for h in range(1, hp + 1):
                m = month + h
                y = year + (m - 1) // 12
                m = (m - 1) % 12 + 1
                rows.append({
                    "permno": int(row["permno"]),
                    "yyyymm": y * 100 + m,
                    "signal": float(row["signal"]),
                })
        expanded = pd.DataFrame(rows)
        return df.merge(expanded, on=["permno", "yyyymm"], how="inner")

    def _compute_breakpoints(self, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        n = int(config.get("breakpoint_quantiles", 10))
        src = config.get("breakpoint_source", "full_sample")

        bp_df = df[df["exchcd"] == 1].copy() if src == "nyse" else df.copy()
        bp_df = bp_df.dropna(subset=["signal"])

        quantile_vals = np.linspace(0, 1, n + 1)
        bp = (
            bp_df.groupby("yyyymm")["signal"]
            .quantile(quantile_vals)
            .unstack()
        )
        bp.columns = [f"q{i}" for i in range(n + 1)]
        return bp

    def _assign_portfolios(
        self, df: pd.DataFrame, breakpoints: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        n = int(config.get("breakpoint_quantiles", 10))
        chunks: list[pd.DataFrame] = []
        for yyyymm, group in df.groupby("yyyymm"):
            if yyyymm not in breakpoints.index:
                continue
            bp = breakpoints.loc[yyyymm]
            bins = [bp[f"q{i}"] for i in range(n + 1)]
            bins[0] = -np.inf
            bins[-1] = np.inf
            g = group.copy()
            g["portfolio"] = pd.cut(
                g["signal"], bins=bins, labels=range(1, n + 1), include_lowest=True
            )
            chunks.append(g)
        if not chunks:
            return pd.DataFrame()
        out = pd.concat(chunks)
        return out.dropna(subset=["portfolio"]).copy()

    def _compute_returns(self, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        wt = config.get("weighting_rule", "vw")
        df = df.copy()
        df["portfolio"] = df["portfolio"].astype(int)

        if wt == "vw":
            def _vw(g: pd.DataFrame) -> float:
                w = g["me"].clip(lower=0)
                s = w.sum()
                return float((g["ret"] * w).sum() / s) if s > 0 else float("nan")

            rets = (
                df.groupby(["yyyymm", "portfolio"])
                .apply(_vw)
                .reset_index(name="ret")
            )
        else:
            rets = (
                df.groupby(["yyyymm", "portfolio"])["ret"]
                .mean()
                .reset_index()
            )
        return rets

    def _compute_long_short(self, rets: pd.DataFrame, config: dict) -> pd.DataFrame:
        n = int(config.get("breakpoint_quantiles", 10))
        long_leg = config.get("long_leg", "low")
        long_port  = 1 if long_leg == "low" else n
        short_port = n if long_leg == "low" else 1

        rows: list[dict] = []
        for yyyymm, g in rets.groupby("yyyymm"):
            port_map = dict(zip(g["portfolio"].astype(int), g["ret"]))
            if long_port in port_map and short_port in port_map:
                rows.append({
                    "yyyymm": yyyymm,
                    "ls_return": port_map[long_port] - port_map[short_port],
                })
        return pd.DataFrame(rows)

    def _compute_metrics(self, ls: pd.DataFrame, config: dict) -> dict[str, Any]:
        series = ls["ls_return"].dropna()
        n = len(series)
        if n < 2:
            return {"mean_monthly_return": float("nan"), "t_stat": float("nan"), "n_months": n}

        mean_ret = float(series.mean())
        lags = min(6, n - 1)
        nw_var = _newey_west_var(series.values, lags)
        t_stat = mean_ret / np.sqrt(nw_var / n) if nw_var > 0 else float("nan")

        return {
            "mean_monthly_return": mean_ret,
            "annualized_return":   mean_ret * 12,
            "t_stat":              float(t_stat),
            "n_months":            n,
        }
