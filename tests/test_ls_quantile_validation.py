"""Regression test for the 2026-07-28 fix: `registry._resolve_ls_quantile`
must clamp invalid/degenerate `ls_quantile` values to the standard 10-group
default instead of letting them silently produce a nonsensical
`breakpoint_quantiles` (a negative count, or a truncated single-group split)
that would previously reach `compute_breakpoints`/`assign_portfolios`
unvalidated and fail deep inside the engine.
"""

from __future__ import annotations

from src.steps.step3_codegen.registry import _resolve_ls_quantile


class TestResolveLsQuantile:
    def test_none_defaults_to_decile(self):
        assert _resolve_ls_quantile(None) == 10

    def test_negative_value_clamps_to_decile(self):
        # Old behavior: int(round(1.0 / -1)) == -1 groups.
        assert _resolve_ls_quantile(-1) == 10

    def test_single_group_clamps_to_decile(self):
        # A single group can't form a long-short spread.
        assert _resolve_ls_quantile(1) == 10

    def test_fractional_group_count_rounds_not_truncates(self):
        # Old behavior: bare int(1.5) == 1 (silently truncated, same as a
        # single group). Rounding to the nearest whole group count is more
        # faithful to what the paper likely meant (e.g. 1.5 -> round to 2).
        assert _resolve_ls_quantile(1.5) == 2
        assert _resolve_ls_quantile(3.3) == 3

    def test_valid_group_count_passes_through(self):
        assert _resolve_ls_quantile(10) == 10
        assert _resolve_ls_quantile(5) == 5

    def test_valid_fraction_form_converts_to_group_count(self):
        assert _resolve_ls_quantile(0.1) == 10  # decile
        assert _resolve_ls_quantile(0.2) == 5   # quintile

    def test_out_of_range_fraction_clamps_to_decile(self):
        # > 0.5 would mean fewer than 2 groups.
        assert _resolve_ls_quantile(0.6) == 10

    def test_zero_clamps_to_decile(self):
        assert _resolve_ls_quantile(0) == 10
