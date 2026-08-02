"""Unit tests for sample-period segmented metrics.

`BacktestExecutor.compute_metrics` gains an optional `by_sample_period` split
(in-sample / between / post-publication) mirroring CZ's sumportmonth
insamp/between/postpub tags, driven by sample_start_year/sample_end_year/
publication_year in config. The top-level metrics must be byte-identical
whether or not the sample window is supplied, so existing golden numbers are
unaffected.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.infra.backtest_engine import BacktestExecutor


def _ls(years: range, ret: float = 0.01) -> pd.DataFrame:
    """One month per January of each year, constant long-short return."""
    return pd.DataFrame({"yyyymm": [y * 100 + 1 for y in years], "ls_return": ret})


def test_no_sample_window_omits_segmented_block():
    ls = _ls(range(2000, 2011))
    metrics = BacktestExecutor().compute_metrics(ls, config={})
    assert "by_sample_period" not in metrics
    assert metrics["n_months"] == 11


def test_top_level_metrics_unchanged_with_window():
    ls = pd.DataFrame(
        {"yyyymm": [200001, 200002, 200003, 200004], "ls_return": [0.01, -0.02, 0.03, 0.005]}
    )
    base = BacktestExecutor().compute_metrics(ls, config={})
    withwin = BacktestExecutor().compute_metrics(
        ls, config={"sample_start_year": 2000, "sample_end_year": 2000, "publication_year": 2005}
    )
    for key in ("mean_monthly_return", "t_stat", "n_months", "sharpe_ratio", "annualized_return"):
        assert withwin[key] == base[key] or (
            np.isnan(withwin[key]) and np.isnan(base[key])
        )


def test_three_segments_split_by_year():
    # in-sample 2000-2004, between 2005-2007 (pub=2007), postpub 2008+
    ls = _ls(range(2000, 2011))  # 2000..2010
    metrics = BacktestExecutor().compute_metrics(
        ls,
        config={"sample_start_year": 2000, "sample_end_year": 2004, "publication_year": 2007},
    )
    seg = metrics["by_sample_period"]
    assert seg["insamp"]["n_months"] == 5   # 2000-2004
    assert seg["between"]["n_months"] == 3  # 2005-2007
    assert seg["postpub"]["n_months"] == 3  # 2008-2010


def test_no_publication_year_omits_between_and_postpub():
    ls = _ls(range(2000, 2011))
    metrics = BacktestExecutor().compute_metrics(
        ls, config={"sample_start_year": 2000, "sample_end_year": 2004}
    )
    seg = metrics["by_sample_period"]
    assert "insamp" in seg
    assert "between" not in seg
    assert "postpub" not in seg
    assert seg["insamp"]["n_months"] == 5


def test_empty_segment_skipped():
    # all months are post-publication; insamp/between have zero months
    ls = _ls(range(2010, 2013))
    metrics = BacktestExecutor().compute_metrics(
        ls,
        config={"sample_start_year": 1990, "sample_end_year": 1995, "publication_year": 1998},
    )
    seg = metrics["by_sample_period"]
    assert "insamp" not in seg
    assert "between" not in seg
    assert seg["postpub"]["n_months"] == 3


def test_full_portfolio_return_shape_unaffected():
    # no ls_return column -> early return, no segmentation attempted
    grid = pd.DataFrame({"yyyymm": [200001, 200001], "portfolio": [1, 2], "ret": [0.01, 0.02]})
    metrics = BacktestExecutor().compute_metrics(
        grid, config={"sample_start_year": 2000, "sample_end_year": 2000}
    )
    assert "by_sample_period" not in metrics
    assert "note" in metrics
