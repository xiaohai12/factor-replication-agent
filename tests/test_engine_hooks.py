"""Unit tests for BacktestEngine._detect_hooks() and its ReviewGate safety net.

_detect_hooks() used to guess double-sorts / multi-leg combinations / non-
standard universes by keyword-matching free-text MethodSpec fields
(portfolio.filter / long_leg / short_leg / universe). It now compares
structured, typed fields (reported_results.return_calculation.portfolio_return
.sorts/construction_type/return_combination) against STANDARD sets drawn
directly from the MethodSpec enums -- the same pattern already used for
breakpoint_source/weighting/missing_action.

filter_universe (plan.md Phase 2.5, 2026-07-20): previously unconditional --
every factor's filter_universe step was LLM-generated from
portfolio.universe_filters/universe, since maintaining a STANDARD set of
"known-good" universe filter fields would duplicate steps.filter_universe()'s
hardcoded shrcd/exchcd/siccd logic and couldn't express value-level
differences (e.g. shrcd in (10,11,12) vs (10,11)). This is now handled by a
deterministic FilterOp DSL (steps.apply_universe_filters, driven by
portfolio.universe_filters) instead, so filter_universe is standard by
default -- it is never flagged by detect_hooks() anymore. A plugin-supplied
filter_universe_hook still overrides the standard implementation entirely
when present (a plugin-authoring choice, not something detect_hooks predicts).

Because the sort/construction_type/return_combination structured data is
deeply nested and easy for extraction to leave unpopulated, ReviewGate.
_check_portfolio_structure_consistency() acts as a safety net for those
fields: it blocks approval when free-text fields clearly describe a complex
construction but the structured fields are empty, so a human fills them in
instead of BacktestEngine silently treating the factor as standard.
"""

from __future__ import annotations

from src.infra.models.method_spec import (
    BreakpointSource,
    FilterOp,
    MethodSpec,
    PortfolioConstructionType,
    ReturnCombinationType,
    SignalSpec,
    SortLegSpec,
    UniverseFilterSpec,
    WeightingRule,
)
from src.steps.step5_engine import BacktestEngine
from src.steps.step2_reviewer import ReviewGate


def _minimal_spec() -> MethodSpec:
    """Build a minimal MethodSpec where every pre-existing STANDARD check
    (breakpoint_source/weighting/missing_action) already passes, so tests can
    focus on the sorts/construction_type/return_combination checks added in
    this change without noise from the older checks."""
    spec = MethodSpec(
        factor_id="test_factor",
        factor_name="Test Factor",
        signal=SignalSpec(),
    )
    spec.portfolio.breakpoints.source = BreakpointSource.FULL_SAMPLE
    spec.portfolio.sort.breakpoint_source = BreakpointSource.FULL_SAMPLE
    spec.portfolio.weighting = WeightingRule.VALUE_WEIGHTED
    spec.portfolio.weighting_scheme = WeightingRule.VALUE_WEIGHTED
    return spec


class TestDetectHooksStandardCase:
    def test_all_standard_fields_trigger_no_hooks(self):
        spec = _minimal_spec()
        assert set(BacktestEngine._detect_hooks(spec)) == set()


class TestDetectHooksSorts:
    def test_recognized_characteristic_x_size_double_sort_does_not_trigger_hook(self):
        """Phase 3 (2026-07-20): a characteristic x size double sort is now a
        standard multi-dim sort (steps.compute_breakpoints_multi /
        assign_portfolios_multi), so it no longer needs a hook."""
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_breakpoints" not in hooks
        assert "assign_portfolios" not in hooks

    def test_unrecognized_double_sort_still_flags_breakpoints_and_assign(self):
        """Two dims where NEITHER is recognized as size-like can't be mapped
        (both would collide on the single "signal" column) -- still hooked."""
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="book_to_market"),
            SortLegSpec(variable="momentum"),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_breakpoints" in hooks
        assert "assign_portfolios" in hooks

    def test_triple_sort_still_flags_breakpoints_and_assign(self):
        """3+ dims are out of v1 scope -- still hooked."""
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
            SortLegSpec(variable="momentum"),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_breakpoints" in hooks
        assert "assign_portfolios" in hooks

    def test_single_sort_does_not_trigger_hook(self):
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="asset_growth_decile"),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_breakpoints" not in hooks
        assert "assign_portfolios" not in hooks


class TestDetectHooksConstructionType:
    def test_regression_weighted_does_not_trigger_hook(self):
        """Phase 7 (2026-07-20): regression_weighted routes to the standard
        Fama-MacBeth estimator (steps.compute_fama_macbeth) instead of
        compute_returns entirely, so it's no longer flagged."""
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.construction_type = (
            PortfolioConstructionType.REGRESSION_WEIGHTED
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_returns" not in hooks

    def test_non_standard_construction_type_flags_compute_returns(self):
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.construction_type = (
            PortfolioConstructionType.FACTOR_MODEL_ALPHA
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_returns" in hooks

    def test_characteristic_sort_does_not_trigger_hook(self):
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.construction_type = (
            PortfolioConstructionType.CHARACTERISTIC_SORT
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_returns" not in hooks


class TestDetectHooksReturnCombination:
    def test_average_leg_spread_does_not_trigger_hook(self):
        """Phase 4 (2026-07-20): average_leg_spread is standard now (see
        steps.compute_long_short) -- it only actually averages multiple
        portfolios per leg when long_portfolios/short_portfolios are given
        explicitly, but that's a config-default question, not a hook one."""
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.return_combination.type = (
            ReturnCombinationType.AVERAGE_LEG_SPREAD
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_long_short" not in hooks

    def test_full_portfolio_return_does_not_trigger_hook(self):
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.return_combination.type = (
            ReturnCombinationType.FULL_PORTFOLIO_RETURN
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_long_short" not in hooks

    def test_extreme_group_spread_does_not_trigger_hook(self):
        spec = _minimal_spec()
        spec.reported_results.return_calculation.portfolio_return.return_combination.type = (
            ReturnCombinationType.EXTREME_GROUP_SPREAD
        )
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_long_short" not in hooks


class TestDetectHooksFilterUniverseIsDeterministic:
    """Phase 2.5 (2026-07-20): filter_universe is standard by default -- see
    module docstring. These replace the old
    TestDetectHooksFilterUniverseAlwaysHook checks."""

    def test_filter_universe_is_not_hooked_regardless_of_free_text_universe(self):
        spec = _minimal_spec()
        spec.portfolio.universe = "NYSE, Amex, and NASDAQ common stocks"
        hooks = BacktestEngine._detect_hooks(spec)
        assert "filter_universe" not in hooks

    def test_filter_universe_is_not_hooked_with_structured_universe_filters(self):
        spec = _minimal_spec()
        spec.portfolio.universe_filters = [
            UniverseFilterSpec(field="shrcd", op=FilterOp.IN, value=[10, 11]),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "filter_universe" not in hooks

    def test_filter_universe_is_not_hooked_with_no_universe_filters(self):
        spec = _minimal_spec()
        assert spec.portfolio.universe_filters == []
        hooks = BacktestEngine._detect_hooks(spec)
        assert "filter_universe" not in hooks


class TestDetectHooksOverlappingPortfolios:
    def test_overlapping_portfolios_does_not_trigger_hook(self):
        """Phase 5 (2026-07-20): overlapping-cohort holding is standard now
        (steps.merge_signal_overlap + friends)."""
        spec = _minimal_spec()
        spec.signal.timing.overlapping_portfolios = True
        hooks = BacktestEngine._detect_hooks(spec)
        assert "merge_signal" not in hooks

    def test_overlapping_combined_with_multi_dim_sort_still_flags_hook(self):
        """The overlapping-cohort path and the multi-dim sort path aren't
        combined in this v1 (BacktestEngine._dispatch() only routes to one
        alternate path at a time) -- still hooked together."""
        spec = _minimal_spec()
        spec.signal.timing.overlapping_portfolios = True
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
        ]
        hooks = BacktestEngine._detect_hooks(spec)
        assert "merge_signal" in hooks

    def test_non_overlapping_portfolios_does_not_trigger_hook(self):
        spec = _minimal_spec()
        spec.signal.timing.overlapping_portfolios = False
        hooks = BacktestEngine._detect_hooks(spec)
        assert "merge_signal" not in hooks

    def test_unspecified_overlapping_portfolios_does_not_trigger_hook(self):
        spec = _minimal_spec()
        assert spec.signal.timing.overlapping_portfolios is None
        hooks = BacktestEngine._detect_hooks(spec)
        assert "merge_signal" not in hooks


class TestBreakpointSourceConditionalBugFix:
    def test_conditional_breakpoint_source_is_not_collapsed_to_unspecified(self):
        assert MethodSpec._normalize_breakpoint_source("conditional") == "conditional"

    def test_paper_specific_breakpoint_source_is_not_collapsed_to_unspecified(self):
        assert MethodSpec._normalize_breakpoint_source("paper_specific") == "paper_specific"

    def test_conditional_breakpoint_source_flags_compute_breakpoints_hook(self):
        spec = _minimal_spec()
        spec.portfolio.breakpoints.source = BreakpointSource.CONDITIONAL
        spec.portfolio.sort.breakpoint_source = BreakpointSource.CONDITIONAL
        hooks = BacktestEngine._detect_hooks(spec)
        assert "compute_breakpoints" in hooks


class TestReviewGatePortfolioStructureSafetyNet:
    def test_double_sort_prose_without_structured_data_is_blocked(self):
        spec = _minimal_spec()
        spec.portfolio.filter = (
            "double sort: independent 2x3 sort on size and book-to-market"
        )
        result = ReviewGate().review(spec)
        assert "reported_results.return_calculation.portfolio_return" in result.blocked_fields
        assert result.disposition == "blocked"

    def test_double_sort_prose_with_structured_data_is_not_blocked_by_this_check(self):
        spec = _minimal_spec()
        spec.portfolio.filter = (
            "double sort: independent 2x3 sort on size and book-to-market"
        )
        spec.reported_results.return_calculation.portfolio_return.sorts = [
            SortLegSpec(variable="size"),
            SortLegSpec(variable="book_to_market"),
        ]
        result = ReviewGate().review(spec)
        assert "reported_results.return_calculation.portfolio_return" not in result.blocked_fields

    def test_plain_prose_is_not_blocked(self):
        spec = _minimal_spec()
        spec.portfolio.filter = ""
        spec.portfolio.universe = "NYSE, Amex, and NASDAQ common stocks"
        result = ReviewGate().review(spec)
        assert "reported_results.return_calculation.portfolio_return" not in result.blocked_fields
