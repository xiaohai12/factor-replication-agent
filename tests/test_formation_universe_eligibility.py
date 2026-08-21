"""Regression test for the 2026-07-28 point-in-time formation-eligibility fix
(third pass on the same code path -- see docs/decision-log.md for the full
history): `self.formation`'s `universe_filters` exclusion (and `exchcd` for
`breakpoint_source="nyse"`) must be evaluated at each (permno, cohort)'s OWN
formation-month row, not aggregated across the stock's whole history.

First pass: `self.formation` was built directly from the raw `signal`
DataFrame, never run through `filter_universe` at all. Second pass: fixed
that, but used a permno-WIDE eligible/ineligible set (a stock that passed
the filter at ANY point in its history was never excluded, even at a
different cohort where it fails) and still read `exchcd` from the
post-`filter_universe` panel (which never contains a formation-month row
under this engine's held-months-only convention, so `breakpoint_source="nyse"`
was effectively broken). This third pass fixes both by looking up
formation-month attributes point-in-time in `self._pre_missing_policy_data`.
"""

from __future__ import annotations

import pandas as pd

from src.infra.backtest_engine import BacktestExecutor

_CONFIG = {
    "holding_period_months": 3,
    "breakpoint_quantiles": 2,  # median split: portfolio 1 (low) / 2 (high)
    "breakpoint_source": "full_sample",
    "weighting_rule": "ew",
    "universe_filters": [{"field": "shrcd", "op": "in", "value": [10, 11]}],
}


def _signal() -> pd.DataFrame:
    # Formation cross-section (200001): signals 1, 2, 3, 4.
    return pd.DataFrame({
        "permno": [1, 2, 3, 4],
        "yyyymm": [200001, 200001, 200001, 200001],
        "signal": [1.0, 2.0, 3.0, 4.0],
    })


def _panel_with_one_ineligible_stock() -> pd.DataFrame:
    """permno 4 (the highest-signal stock) has shrcd=99 at its OWN formation
    month (200001) AND in every held month it appears -- it fails the
    universe_filters screen (shrcd in [10, 11]) point-in-time at formation,
    but it DOES have valid returns in all three held months (unlike the
    look-ahead scenario, where the excluded stock has NO returns at all)."""
    rows = [(p, m) for p in (1, 2, 3, 4) for m in (200001, 200002, 200003, 200004)]
    shrcd = {1: 10, 2: 10, 3: 10, 4: 99}
    return pd.DataFrame({
        "permno": [p for p, _ in rows],
        "yyyymm": [m for _, m in rows],
        "ret": [0.01] * len(rows),
        "me": [100.0] * len(rows),
        "exchcd": [1] * len(rows),
        "shrcd": [shrcd[p] for p, _ in rows],
    })


def _run_pipeline_steps(panel: pd.DataFrame) -> BacktestExecutor:
    """Drive the engine through the real Step 3 -> Step 4 -> Step 6 order
    (apply_missing_policy BEFORE filter_universe, matching run_with_config)
    so `self._pre_missing_policy_data` is populated the same way a real run
    would populate it."""
    engine = BacktestExecutor()
    engine.data = panel
    engine.apply_missing_policy(config=_CONFIG)
    engine.filter_universe(config=_CONFIG)
    return engine


class TestFormationExcludesUniverseFilterFailures:
    def test_filter_universe_drops_the_ineligible_permno_from_data(self):
        engine = _run_pipeline_steps(_panel_with_one_ineligible_stock())
        assert sorted(engine.data["permno"].unique()) == [1, 2, 3]

    def test_formation_also_excludes_the_ineligible_permno(self):
        """Before this fix, self.formation reconstructed from the raw signal
        and still contained permno 4 even though it fails universe_filters
        at its own formation month."""
        engine = _run_pipeline_steps(_panel_with_one_ineligible_stock())
        engine.apply_signal_holding_period(signal=_signal(), config=_CONFIG)

        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3]

    def test_breakpoint_reflects_the_eligible_population_only(self):
        """Median of the eligible signals [1,2,3] is 2.0 -- NOT 2.5 (the
        biased number computed when the ineligible permno 4 leaked in)."""
        engine = _run_pipeline_steps(_panel_with_one_ineligible_stock())
        engine.apply_signal_holding_period(signal=_signal(), config=_CONFIG)
        bp = engine.compute_breakpoints(config=_CONFIG)

        assert bp.loc[200001, "q1"] == 2.0


class TestEligibilityIsCohortSpecificNotPermnoWideHistory:
    """A stock that fails universe_filters ONLY at its own formation month
    (and passes at an unrelated earlier/later month) must still be excluded
    from ITS OWN cohort -- eligibility is not a permno-wide aggregate across
    the stock's whole history."""

    def test_stock_ineligible_only_at_its_own_formation_is_excluded(self):
        signal = pd.DataFrame({
            "permno": [1, 2, 3, 4],
            "yyyymm": [200002] * 4,
            "signal": [1.0, 2.0, 3.0, 4.0],
        })
        rows = []
        for p in (1, 2, 3):
            for m in (200001, 200002, 200003, 200004, 200005):
                rows.append((p, m, 10))
        # permno 4: shrcd=10 at an unrelated month (200001), shrcd=99 AT ITS
        # OWN FORMATION MONTH (200002) and held months, shrcd=10 again later
        # (200005) -- the ONLY month that matters for this cohort's
        # eligibility is 200002.
        rows += [(4, 200001, 10), (4, 200002, 99), (4, 200003, 99), (4, 200004, 99), (4, 200005, 10)]
        panel = pd.DataFrame({
            "permno": [r[0] for r in rows],
            "yyyymm": [r[1] for r in rows],
            "shrcd": [r[2] for r in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
        })
        config = {**_CONFIG, "holding_period_months": 3}

        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)

        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3]
        bp = engine.compute_breakpoints(config=config)
        assert bp.loc[200002, "q1"] == 2.0


class TestNoFormationMonthRowMeansNoPositiveEvidenceSoNotExcluded:
    """When the panel has NO row at all for a (permno, cohort) pair (its own
    formation month was never recorded), there is no positive evidence the
    stock fails universe_filters -- it must be kept, not excluded. This
    matters because this engine's held-months-only convention (held months
    start at h=1, i.e. strictly AFTER formation) means many real panels
    won't have a formation-month row either; the fix must degrade to
    "can't evaluate, so don't exclude" rather than silently misclassifying."""

    def test_missing_formation_month_row_does_not_exclude(self):
        signal = _signal()
        # No row at all for yyyymm=200001 (the formation month) for ANY
        # permno -- only held months 200002-200004, all shrcd=10 (including
        # permno 4, which would otherwise be considered eligible anyway).
        rows = [(p, m) for p in (1, 2, 3, 4) for m in (200002, 200003, 200004)]
        panel = pd.DataFrame({
            "permno": [p for p, _ in rows],
            "yyyymm": [m for _, m in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
            "shrcd": [10] * len(rows),
        })
        engine = _run_pipeline_steps(panel)
        engine.apply_signal_holding_period(signal=signal, config=_CONFIG)

        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3, 4]


class TestFormationDoesNotReintroduceTheLookAheadBug:
    """A permno with ZERO rows anywhere in the panel (delisted before any
    data was ever recorded) must still be treated as eligible -- there is no
    POSITIVE evidence it fails universe_filters, only an absence of data,
    which is exactly the case the original 2026-07-28 look-ahead fix
    protects."""

    def test_permno_absent_from_panel_entirely_is_not_excluded(self):
        signal = _signal()  # permnos 1-4
        # permno 4 has ZERO rows anywhere (not even a shrcd=99 row) --
        # simulates delisting before any return was ever recorded.
        rows = [(p, m) for p in (1, 2, 3) for m in (200002, 200003, 200004)]
        panel = pd.DataFrame({
            "permno": [p for p, _ in rows],
            "yyyymm": [m for _, m in rows],
            "ret": [0.01] * len(rows),
            "me": [100.0] * len(rows),
            "exchcd": [1] * len(rows),
            "shrcd": [10] * len(rows),
        })
        engine = _run_pipeline_steps(panel)
        engine.apply_signal_holding_period(signal=signal, config=_CONFIG)

        # permno 4 was never "seen" by the universe-filter eligibility
        # check, so it is NOT excluded -- self.formation still has all 4.
        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3, 4]
        bp = engine.compute_breakpoints(config=_CONFIG)
        assert bp.loc[200001, "q1"] == 2.5  # true 4-stock median, unbiased


class TestNoUniverseFiltersConfiguredIsANoOp:
    def test_no_filtering_applied_when_universe_filters_is_empty(self):
        config = {k: v for k, v in _CONFIG.items() if k != "universe_filters"}
        engine = BacktestExecutor()
        engine.data = _panel_with_one_ineligible_stock()
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=_signal(), config=config)

        # No universe_filters configured -> nothing excluded on eligibility
        # grounds; permno 4 stays in self.formation.
        assert sorted(engine.formation["permno"].unique()) == [1, 2, 3, 4]


class TestNyseExchcdIsPointInTimeAndDecoupledFromReturnAvailability:
    """breakpoint_source='nyse' must classify a stock by its OWN
    formation-month exchcd, independent of whether that stock's HELD-month
    returns are missing (previously: exchcd was read from the post-
    apply_missing_policy panel, which drops rows with missing returns, so a
    stock's exchcd went NaN whenever ITS OWN held-month return happened to
    be missing -- and, separately, was ALWAYS NaN in practice because the
    post-join panel never contains a formation-month row at all)."""

    def test_missing_held_month_return_does_not_blank_out_exchcd(self):
        signal = pd.DataFrame({"permno": [1, 2, 3], "yyyymm": [200001] * 3, "signal": [1.0, 2.0, 3.0]})
        rows = []
        # formation-month row (200001) present for all three, all NYSE.
        for p in (1, 2, 3):
            rows.append((p, 200001, 1, 0.01))
        # held months: permno 1,2 have normal returns; permno 3's held-month
        # RETURN is missing in every held month (but it IS NYSE at formation).
        for p in (1, 2):
            for m in (200002, 200003, 200004):
                rows.append((p, m, 1, 0.01))
        for m in (200002, 200003, 200004):
            rows.append((3, m, 1, None))
        panel = pd.DataFrame({
            "permno": [r[0] for r in rows],
            "yyyymm": [r[1] for r in rows],
            "exchcd": [r[2] for r in rows],
            "ret": [r[3] for r in rows],
            "me": [100.0] * len(rows),
        })
        config = {
            "holding_period_months": 3,
            "breakpoint_quantiles": 2,
            "breakpoint_source": "nyse",
            "weighting_rule": "ew",
        }
        engine = BacktestExecutor()
        engine.data = panel
        engine.apply_missing_policy(config=config)
        engine.filter_universe(config=config)
        engine.apply_signal_holding_period(signal=signal, config=config)

        assert engine.formation["exchcd"].tolist() == [1, 1, 1]
        bp = engine.compute_breakpoints(config=config)
        assert bp.loc[200001, "q1"] == 2.0

