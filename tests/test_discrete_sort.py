"""Unit tests for the discrete sort form (plan.md CZ-import Phase B).

steps.compute_breakpoints/assign_portfolios now branch on config["cat_form"]
(mirrors CZ Cat.Form):
  - continuous: quantile sort (unchanged, golden-number stable).
  - discrete:   one portfolio per distinct signal value, ranked by the global
                sorted support (categorical scores like governance index).

registry.build_config() clamps cat_form to these two forms and defaults any
other value (e.g. CZ's "custom") to "continuous".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.infra.backtest_engine import steps


def _panel(rows: list[tuple[int, int, float, float]]) -> pd.DataFrame:
    """rows: (permno, yyyymm, signal, me) -> merged-panel-shaped DataFrame."""
    return pd.DataFrame(rows, columns=["permno", "yyyymm", "signal", "me"]).assign(
        ret=0.0, exchcd=1
    )


def test_discrete_one_portfolio_per_value():
    # signal takes 3 distinct categorical values 1/2/3 -> ports 1/2/3
    df = _panel(
        [
            (10, 200001, 1.0, 100.0),
            (11, 200001, 2.0, 100.0),
            (12, 200001, 3.0, 100.0),
            (13, 200001, 1.0, 100.0),
            (14, 200001, 3.0, 100.0),
        ]
    )
    bp = steps.compute_breakpoints(df, {"cat_form": "discrete"})
    assert bp.empty  # discrete needs no numeric cutoffs
    assigned = steps.assign_portfolios(df, bp, {"cat_form": "discrete"})
    port_of = dict(zip(assigned["signal"], assigned["portfolio"]))
    assert port_of[1.0] == 1
    assert port_of[2.0] == 2
    assert port_of[3.0] == 3
    assert set(assigned["portfolio"].unique()) == {1, 2, 3}


def test_discrete_global_support_consistent_across_months():
    # value 5 appears only in month 2 but must still rank above value 1
    df = _panel(
        [
            (10, 200001, 1.0, 100.0),
            (11, 200001, 3.0, 100.0),
            (12, 200002, 1.0, 100.0),
            (13, 200002, 5.0, 100.0),
        ]
    )
    assigned = steps.assign_portfolios(df, pd.DataFrame(), {"cat_form": "discrete"})
    port_of = dict(zip(assigned["signal"], assigned["portfolio"]))
    # global support sorted = [1,3,5] -> ports 1,2,3
    assert port_of[1.0] == 1
    assert port_of[3.0] == 2
    assert port_of[5.0] == 3


def test_custom_form_falls_back_to_continuous_quantile_path():
    # cat_form other than continuous/discrete is clamped to "continuous" by
    # build_config; assign_portfolios only special-cases discrete, so a raw
    # "custom" value here falls through to the quantile (continuous) path.
    df = _panel(
        [
            (10, 200001, 1.0, 100.0),
            (11, 200001, 2.0, 100.0),
        ]
    )
    bp = steps.compute_breakpoints(df, {"cat_form": "custom"})
    # not discrete -> computes quantile breakpoints (the continuous default path)
    assert not bp.empty


def test_long_short_uses_extreme_present_ports_for_discrete():
    # ports 1..3 present; long_leg=low -> long port 1, short port 3
    rets = pd.DataFrame(
        {
            "yyyymm": [200001, 200001, 200001],
            "portfolio": [1, 2, 3],
            "ret": [0.05, 0.02, 0.01],
        }
    )
    ls = steps.compute_long_short(rets, {"cat_form": "discrete", "long_leg": "low"})
    assert ls.loc[0, "ls_return"] == 0.05 - 0.01


def test_continuous_unchanged_when_cat_form_absent():
    # sanity: continuous path still quantile-cuts
    rng = np.random.default_rng(0)
    rows = [(p, 200001, float(rng.normal()), 100.0) for p in range(100)]
    df = _panel(rows)
    bp = steps.compute_breakpoints(df, {"cat_form": "continuous", "breakpoint_quantiles": 10})
    assert not bp.empty
    assigned = steps.assign_portfolios(
        df, bp, {"cat_form": "continuous", "breakpoint_quantiles": 10}
    )
    assert set(assigned["portfolio"].astype(int).unique()).issubset(set(range(1, 11)))
