"""Step5's paper endpoint must use an opted-in deterministic table spread."""

from types import SimpleNamespace

import pytest

from src.infra.models.method_spec import (
    AdjustmentModel,
    ComparisonDerivation,
    Estimand,
    Period,
    ReportedMetric,
    ReportedResults,
    TimeUnit,
    Unit,
)
from src.steps.step5_backtest_runner import _spec_paper_reported


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
