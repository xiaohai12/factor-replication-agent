"""Step5's paper endpoint must use an opted-in deterministic table spread."""

from types import SimpleNamespace

import pytest

from src.infra.models.method_spec import (
    AdjustmentModel,
    ComparisonDerivation,
    Estimand,
    MetricStatistic,
    Period,
    ReportedMetric,
    ReportedResults,
    SortRole,
    TimeUnit,
    Unit,
)
from src.steps.step5_backtest_runner import _spec_paper_reported
from src.steps.step7_replication_diff.bundle import build_track_vs_paper


def _sort(sort_id: str, role: SortRole = SortRole.TARGET) -> SimpleNamespace:
    return SimpleNamespace(role=role, sort_id=sort_id)


def _leg(side: str, sort_id: str, index: int) -> SimpleNamespace:
    return SimpleNamespace(side=side, selector={sort_id: index})


def test_paper_reported_uses_opted_in_high_minus_low_endpoint() -> None:
    common = dict(
        estimand=Estimand.MEAN_RETURN,
        adjustment_model=AdjustmentModel.RAW,
        unit=Unit.PERCENT,
        frequency=TimeUnit.MONTH,
        sample_period=Period(start_year=1981, end_year=1995),
    )
    results = ReportedResults(
        primary_metric_id="port1",
        metrics=[
            ReportedMetric(metric_id="port1", label="Port 1", estimate=0.48, **common),
            ReportedMetric(metric_id="port10", label="Port 10", estimate=1.07, **common),
        ],
        comparison_derivation=ComparisonDerivation(
            metric_id="port10_minus_port1",
            label="Port 10 − Port 1",
            operation="high_minus_low",
            high_metric_id="port10",
            low_metric_id="port1",
            use_as_primary_comparison=True,
        ),
    )
    spec = SimpleNamespace(
        paper=SimpleNamespace(
            reported_results=results,
            sample=SimpleNamespace(reported_returns=Period(start_year=1981, end_year=1995)),
        )
    )

    endpoint = _spec_paper_reported(spec)

    assert endpoint["return_type"] == "spread"
    assert endpoint["main_spread"] == pytest.approx(0.59)
    assert endpoint["spreads"]["port10_minus_port1"] == pytest.approx(0.59)
    assert endpoint["comparison_derivation"]["high_metric_id"] == "port10"


def test_paper_reported_sign_flips_high_minus_low_against_negative_direction_long_leg() -> None:
    """AssetGrowth-shaped case: the paper's own headline metric is a single
    table cell framed "high minus low" (`portfolio_selector` carrying both
    `{sort_id}_high`/`{sort_id}_low` endpoints), but the engine's long leg
    -- per `portfolio.legs` -- is the LOW-characteristic decile (a
    negative-direction signal). Before the fix this produced a false
    `sign_agrees=False`: same economic fact, opposite sign convention."""
    common = dict(
        estimand=Estimand.ALPHA,
        adjustment_model=AdjustmentModel.FF3,
        unit=Unit.DECIMAL,
        frequency=TimeUnit.MONTH,
        sample_period=Period(start_year=1968, end_year=2003),
    )
    results = ReportedResults(
        primary_metric_id="alpha_high_minus_low",
        metrics=[
            ReportedMetric(
                metric_id="alpha_high_minus_low",
                label="High minus low",
                estimate=-0.007,
                portfolio_selector={"growth_decile_high": 9, "growth_decile_low": 0},
                statistic=MetricStatistic(kind="t_stat", value=-3.84),
                **common,
            ),
        ],
    )
    spec = SimpleNamespace(
        paper=SimpleNamespace(
            reported_results=results,
            sample=SimpleNamespace(reported_returns=Period(start_year=1968, end_year=2003)),
            portfolio=SimpleNamespace(
                sorts=[_sort("growth_decile")],
                legs=[
                    _leg("long", "growth_decile", 0),  # low-characteristic decile is long
                    _leg("short", "growth_decile", 9),  # high-characteristic decile is short
                ],
            ),
        )
    )

    endpoint = _spec_paper_reported(spec)

    assert endpoint["sign_correction"]["applied"] is True
    assert endpoint["sign_correction"]["flipped_metric_ids"] == ["alpha_high_minus_low"]
    assert endpoint["main_spread"] == pytest.approx(0.007)
    assert endpoint["main_t_stat"] == pytest.approx(3.84)
    assert endpoint["spreads"]["alpha_high_minus_low"] == pytest.approx(0.007)
    assert endpoint["t_stats"]["alpha_high_minus_low"] == pytest.approx(3.84)

    # The engine's own track_spread (long - short = low - high) is a
    # genuine positive number for this economic fact -- once the paper's
    # spread is sign-corrected to the same (long-short) orientation, the
    # two signs should agree instead of falsely disagreeing.
    vs_paper = build_track_vs_paper(endpoint, {"mean_return": 0.005052, "t_stat": 2.5})
    assert vs_paper["sign_agrees"] is True


def test_paper_reported_no_flip_when_paper_and_engine_orientation_already_match() -> None:
    """MeanRankRevGrowth-shaped case: a `comparison_derivation`-materialized
    metric whose 'high' endpoint (Table-labelled Value, decile index 0) is
    ALSO the engine's long leg -- same orientation, no correction needed."""
    common = dict(
        estimand=Estimand.MEAN_RETURN,
        adjustment_model=AdjustmentModel.RAW,
        unit=Unit.PERCENT,
        frequency=TimeUnit.MONTH,
        sample_period=Period(start_year=1981, end_year=1995),
    )
    results = ReportedResults(
        primary_metric_id="decile1_value",
        metrics=[
            ReportedMetric(
                metric_id="decile1_value",
                label="Decile 1 (Value)",
                estimate=1.07,
                portfolio_selector={"rank_growth_decile": 0},
                **common,
            ),
            ReportedMetric(
                metric_id="decile10_glamour",
                label="Decile 10 (Glamour)",
                estimate=0.48,
                portfolio_selector={"rank_growth_decile": 9},
                **common,
            ),
        ],
        comparison_derivation=ComparisonDerivation(
            metric_id="value_minus_glamour",
            label="Value minus glamour",
            operation="high_minus_low",
            high_metric_id="decile1_value",
            low_metric_id="decile10_glamour",
            use_as_primary_comparison=True,
        ),
    )
    spec = SimpleNamespace(
        paper=SimpleNamespace(
            reported_results=results,
            sample=SimpleNamespace(reported_returns=Period(start_year=1981, end_year=1995)),
            portfolio=SimpleNamespace(
                sorts=[_sort("rank_growth_decile")],
                legs=[
                    _leg("long", "rank_growth_decile", 0),  # Value (decile 1) is long
                    _leg("short", "rank_growth_decile", 9),  # Glamour (decile 10) is short
                ],
            ),
        )
    )

    endpoint = _spec_paper_reported(spec)

    assert endpoint["sign_correction"]["applied"] is False
    assert endpoint["main_spread"] == pytest.approx(0.59)


def test_paper_reported_no_flip_when_orientation_undetermined() -> None:
    """A regression coefficient (no `portfolio_selector`, no
    `comparison_derivation`) can't be assigned a high/low decile
    orientation -- must be left exactly as before, never guessed."""
    common = dict(
        estimand=Estimand.COEFFICIENT,
        adjustment_model=AdjustmentModel.RAW,
        unit=Unit.DECIMAL,
        frequency=TimeUnit.MONTH,
        sample_period=Period(start_year=1981, end_year=1995),
    )
    results = ReportedResults(
        primary_metric_id="gls_slope",
        metrics=[
            ReportedMetric(
                metric_id="gls_slope",
                label="GLS slope",
                estimate=-0.04,
                statistic=MetricStatistic(kind="t_stat", value=-2.1),
                **common,
            ),
        ],
    )
    spec = SimpleNamespace(
        paper=SimpleNamespace(
            reported_results=results,
            sample=SimpleNamespace(reported_returns=Period(start_year=1981, end_year=1995)),
            portfolio=SimpleNamespace(
                sorts=[_sort("turnover_quintile")],
                legs=[
                    _leg("long", "turnover_quintile", 0),
                    _leg("short", "turnover_quintile", 9),
                ],
            ),
        )
    )

    endpoint = _spec_paper_reported(spec)

    assert endpoint["sign_correction"]["applied"] is False
    assert endpoint["main_spread"] == pytest.approx(-0.04)
    assert endpoint["main_t_stat"] == pytest.approx(-2.1)
