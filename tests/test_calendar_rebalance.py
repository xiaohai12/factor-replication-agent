"""Unit tests for rebalance-frequency-aware non-overlapping hold.

BacktestExecutor.apply_signal_holding_period now caps the hold window at the
rebalance step derived from config["rebalance_frequency"] (annual=12,
quarterly=3, monthly=1), so a non-overlapping quarterly/monthly factor holds
one rebalance interval instead of a stale holding_period_months. Annual is
unchanged (min(12,12)=12), keeping golden numbers byte-identical.
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor


def _signal_one_row() -> pd.DataFrame:
    # one formation at 2000-06 (June)
    return pd.DataFrame({"permno": [1], "yyyymm": [200006], "signal": [0.5]})


def _msf_full_year() -> pd.DataFrame:
    # 18 consecutive months of returns for permno 1 starting 2000-06
    months = [200006 + i for i in range(7)] + [200101 + i for i in range(12)]
    return pd.DataFrame(
        {"permno": 1, "yyyymm": months, "ret": 0.01, "me": 100.0, "exchcd": 1}
    )


def test_annual_holds_twelve_months_unchanged():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "annual"},
    )
    # June formation -> held July(200007)..June(200106) = 12 months
    assert len(merged) == 12
    assert merged["yyyymm"].min() == 200007
    assert merged["yyyymm"].max() == 200106


def test_quarterly_caps_hold_at_three_months():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "quarterly"},
    )
    # capped at 3 months: 200007, 200008, 200009
    assert sorted(merged["yyyymm"]) == [200007, 200008, 200009]


def test_monthly_caps_hold_at_one_month():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 12, "rebalance_frequency": "monthly"},
    )
    assert sorted(merged["yyyymm"]) == [200007]


def test_unspecified_frequency_falls_back_to_holding_period():
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 6, "rebalance_frequency": "unspecified"},
    )
    # no cap -> uses holding_period_months=6
    assert len(merged) == 6
    assert merged["yyyymm"].max() == 200012


def test_hold_never_exceeds_holding_period_even_if_step_larger():
    # holding_period_months=3 with annual step 12 -> min(3,12)=3
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        _signal_one_row(),
        {"holding_period_months": 3, "rebalance_frequency": "annual"},
    )
    assert sorted(merged["yyyymm"]) == [200007, 200008, 200009]


def test_annual_explicit_formation_month_asof_resamples_multi_fye_signal():
    data = pd.DataFrame(
        {
            "permno": [1] * 13,
            "yyyymm": [200006 + i for i in range(7)] + [200101 + i for i in range(6)],
            "ret": 0.01,
            "me": 100.0,
            "exchcd": 1,
        }
    )
    signal = pd.DataFrame(
        {
            "permno": [1, 1],
            # 2000-03 is a non-June availability month, but still stale enough
            # to be the valid as-of signal at the 2000-06 formation date.
            "yyyymm": [199903, 200003],
            "signal": [0.2, 0.7],
        }
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "annual",
            "formation_month": 6,
            "formation_month_explicit": True,
            "signal_max_staleness_months": 11,
        },
    )

    assert len(merged) == 12
    assert set(merged["cohort"]) == {200006}
    assert set(merged["signal"]) == {0.7}
    assert merged["yyyymm"].min() == 200007
    assert merged["yyyymm"].max() == 200106


def test_annual_defaulted_formation_month_asof_resamples_monthly_signal():
    # 2026-08-22 fix: `_resample_annual_signal_asof` used to gate on
    # `formation_month_explicit` (True only when the paper's MethodSpec
    # stated a formation month), so a CRSP-cadence MONTHLY signal (e.g.
    # turnover/momentum) riding along on an `annual` override
    # (HXZ_STANDARD_CONFIG / a C&Z cz_config_override, where formation_month
    # is always engine-DEFAULTED, never explicit) skipped resampling
    # entirely. Every one of its ~monthly formation rows then got its own
    # 12-month hold window in apply_signal_holding_period, producing
    # overlapping cohorts (a correctness bug) and an O(rows * 12) blowup.
    # `formation_month_explicit=False` here (the defaulted case) must now
    # collapse to exactly one annual cohort, identical in shape to the
    # explicit case above.
    data = pd.DataFrame(
        {
            "permno": [1] * 13,
            "yyyymm": [200006 + i for i in range(7)] + [200101 + i for i in range(6)],
            "ret": 0.01,
            "me": 100.0,
            "exchcd": 1,
        }
    )
    signal = pd.DataFrame(
        {
            "permno": [1, 1, 1, 1],
            # A monthly-cadence signal with a fresh value every month --
            # NOT restated only once a year like an accounting factor.
            "yyyymm": [200003, 200004, 200005, 200006],
            "signal": [0.1, 0.2, 0.3, 0.9],
        }
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "annual",
            "formation_month": 6,
            "formation_month_explicit": False,
            "signal_max_staleness_months": 11,
        },
    )

    # Collapsed to the single June formation cohort (this stock's June
    # signal value), held for 12 months -- NOT 4 overlapping cohorts (one
    # per signal row) each independently held for 12 months.
    assert len(merged) == 12
    assert set(merged["cohort"]) == {200006}
    assert set(merged["signal"]) == {0.9}
    assert merged["yyyymm"].min() == 200007
    assert merged["yyyymm"].max() == 200106


def test_annual_asof_respects_max_staleness():
    signal = pd.DataFrame({"permno": [1], "yyyymm": [199903], "signal": [0.2]})
    merged = BacktestExecutor().apply_signal_holding_period(
        _msf_full_year(),
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "annual",
            "formation_month": 6,
            "formation_month_explicit": True,
            "signal_max_staleness_months": 11,
        },
    )
    assert merged.empty


def test_monthly_signal_not_resampled_by_annual_asof_logic():
    signal = pd.DataFrame({"permno": [1], "yyyymm": [200003], "signal": [0.7]})
    data = pd.DataFrame(
        {"permno": 1, "yyyymm": [200003, 200004, 200005], "ret": 0.01, "me": 100.0, "exchcd": 1}
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {"holding_period_months": 12, "rebalance_frequency": "monthly"},
    )

    assert sorted(merged["yyyymm"]) == [200004]
    assert set(merged["cohort"]) == {200003}


def test_low_frequency_signal_forward_filled_across_monthly_rebalance():
    # Annual-cadence signal (one row per permno per fiscal year, like
    # Ohlson O-score/Altman Z-score from Compustat) combined with
    # rebalance_frequency="monthly" + signal_cadence="low_frequency" should
    # persist/be reused across every intervening month (up to
    # signal_max_staleness_months), NOT just the single month right after
    # its own formation row -- see docs/decision-log.md 2026-08-21 fix.
    signal = pd.DataFrame({"permno": [1], "yyyymm": [200006], "signal": [0.5]})
    data = pd.DataFrame(
        {
            "permno": 1,
            "yyyymm": [200006 + i for i in range(7)] + [200101 + i for i in range(6)],
            "ret": 0.01,
            "me": 100.0,
            "exchcd": 1,
        }
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "monthly",
            "signal_cadence": "low_frequency",
            "signal_max_staleness_months": 11,
        },
    )

    # One row per month is now held (hold=1 on a now-monthly signal frame),
    # not just the single 200007 month the pre-fix hold=1-on-annual-row
    # behavior would have produced.
    assert len(merged) == 12
    assert merged["yyyymm"].min() == 200007
    assert merged["yyyymm"].max() == 200106
    assert set(merged["signal"].unique()) == {0.5}


def test_low_frequency_signal_respects_max_staleness():
    # A signal older than signal_max_staleness_months should stop being
    # forward-filled once staleness is exceeded, rather than persisting
    # forever.
    signal = pd.DataFrame({"permno": [1], "yyyymm": [200001], "signal": [0.5]})
    months = [200001 + i for i in range(12)] + [200101 + i for i in range(6)]
    data = pd.DataFrame(
        {"permno": 1, "yyyymm": months, "ret": 0.01, "me": 100.0, "exchcd": 1}
    )
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "monthly",
            "signal_cadence": "low_frequency",
            "signal_max_staleness_months": 3,
        },
    )
    # Signal available 200001..200004 (0..3 months stale); held one month
    # forward each -> 200002..200005. Beyond that the signal is too stale
    # and drops out of the merged panel entirely.
    assert sorted(merged["yyyymm"].unique().tolist()) == [200002, 200003, 200004, 200005]


def test_low_frequency_gate_mutually_exclusive_with_annual_asof():
    # signal_cadence="low_frequency" must NOT fire the forward-fill for an
    # annual rebalance -- that case is handled exclusively by
    # _resample_annual_signal_asof, and the two gates must never both fire
    # on the same signal.
    data = pd.DataFrame(
        {
            "permno": [1] * 13,
            "yyyymm": [200006 + i for i in range(7)] + [200101 + i for i in range(6)],
            "ret": 0.01,
            "me": 100.0,
            "exchcd": 1,
        }
    )
    signal = pd.DataFrame({"permno": [1], "yyyymm": [200006], "signal": [0.5]})
    merged = BacktestExecutor().apply_signal_holding_period(
        data,
        signal,
        {
            "holding_period_months": 12,
            "rebalance_frequency": "annual",
            "signal_cadence": "low_frequency",
            "formation_month": 6,
            "formation_month_explicit": True,
            "signal_max_staleness_months": 11,
        },
    )
    # Unaffected by the new forward-fill path -- unchanged annual behavior
    # (single formation cohort, held for the full 12 months).
    assert len(merged) == 12
    assert set(merged["cohort"]) == {200006}
