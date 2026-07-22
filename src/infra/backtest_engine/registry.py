"""Run-time hook loading for the controlled backtest lifecycle.

Answers "how does a plugin's hook function get loaded and made callable at run
time" — the one piece of `registry` logic `BacktestExecutor.run_with_config()`
itself actually calls (`self._load_hooks(plugin)` -> `load_hooks()` below).

Everything else that used to live in this module (which steps are "standard",
how a MethodSpec resolves into a run config) is generation-time decision logic
that's only ever called by MetaCoder/script_generator, never by
BacktestExecutor's own dispatch -- see
`src/steps/step3_codegen/registry.py` for that (moved there so step3_codegen
doesn't need to depend on backtest_engine for it; `BacktestExecutor._detect_hooks()`/
`_build_config()`/etc. remain as thin backward-compatible delegates to that
module).
"""

from __future__ import annotations

from typing import Any


def load_hooks(plugin) -> dict[str, Any]:
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
        "merge_signal",
        "compute_breakpoints",
        "assign_portfolios",
        "compute_returns",
        "apply_missing_policy",
        "apply_delisting_returns",
        "neutralize_signal",
        "compute_long_short",
    ]:
        fn_name = f"{step}_hook"
        if fn_name in ns and callable(ns[fn_name]):
            loaded[step] = ns[fn_name]
    return loaded

