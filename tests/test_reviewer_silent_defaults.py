"""Regression test for the 2026-07-28 fix: `ReviewGate.review()` must not
approve (and stamp `paper_faithful=True` on) a MethodSpec whose high-impact
empirical fields (breakpoint_source, weighting, missing policy, rebalance
frequency, formation month, holding period, accounting lag, sign, universe,
universe_filters, return_combination) are left at their menu-default
"unspecified" sentinel with no `ambiguous_fields` entry explaining why.

Before the fix, `_check_required_fields` only checked that `signal.formula`,
`signal.required_fields`, and `portfolio.long_leg`/`short_leg` were non-empty
(the latter pair already default to "high"/"low", so they pass even when
untouched) -- a MethodSpec with every OTHER empirical field left silent
sailed through `review()` as `approved=True, codegen_ready=True,
paper_faithful=True`, exactly reproducing an external technical review's
finding. See docs/decision-log.md (2026-07-28 entry).
"""

from __future__ import annotations

from src.infra.models.method_spec import AmbiguousField, EvidenceSource, MethodSpec
from src.steps.step2_reviewer import ReviewGate


def _minimal_spec(**overrides) -> MethodSpec:
    """A MethodSpec with only signal.formula + required_fields set (the
    reviewer's own minimum bar) -- every other empirical field left at its
    schema default."""
    payload = {
        "factor_id": "x",
        "factor_name": "X",
        "signal": {"required_fields": ["f"], "formula": {"expression": "f"}},
        "data": {"normalized_mapping": {"f": "ret"}},
    }
    payload.update(overrides)
    return MethodSpec.model_validate(payload)


class TestSilentHighImpactFieldsAreBlocked:
    def test_minimal_spec_is_not_approved_or_paper_faithful(self):
        gate = ReviewGate(data_dictionary=None)
        result = gate.review(_minimal_spec())

        assert result.approved is False
        assert result.paper_faithful is False
        assert result.codegen_ready is False
        assert result.disposition == "blocked"

    def test_blocked_fields_include_the_silent_empirical_choices(self):
        gate = ReviewGate(data_dictionary=None)
        result = gate.review(_minimal_spec())

        # These are exactly the fields registry.build_config would otherwise
        # silently clamp to a menu default (see registry.py `_clamp`/`or`
        # fallbacks) -- none of them were actually specified here.
        for field in (
            "portfolio.sort.breakpoint_source",
            "portfolio.weighting",
            "signal.missing_policy",
            "signal.timing.rebalance_frequency",
            "signal.timing.formation_month",
            "signal.timing.holding_period",
            "signal.timing.accounting_lag",
            "signal.sign",
            "portfolio.universe",
            "portfolio.universe_filters",
            "portfolio.return_combination",
            "portfolio.sort.ls_quantile",
        ):
            assert field in result.blocked_fields, f"expected {field!r} to be blocked"

    def test_already_flagged_field_is_not_duplicated(self):
        """If the extractor DID record an ambiguous_fields entry for a
        silent high-impact field, the deterministic backstop must not add a
        second, duplicate blocked_fields entry for it -- the existing
        `_check_ambiguous_fields` matrix already owns that field's
        disposition."""
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(ambiguous_fields=[
            AmbiguousField(
                field="portfolio.sort.breakpoint_source",
                source=EvidenceSource.UNSPECIFIED,
                reason="paper silent on breakpoint universe",
            ).model_dump(mode="json"),
        ])
        result = gate.review(spec)

        assert result.blocked_fields.count("portfolio.sort.breakpoint_source") == 1


class TestExplicitInvalidLsQuantileIsBlocked:
    """`ls_quantile=None` (unset) is blocked -- but so must an EXPLICIT,
    numerically invalid value be: `registry._resolve_ls_quantile` silently
    clamps `-1`/`0`/an out-of-range fraction to the standard 10-group
    default at build_config time (to keep the engine crash-safe), but that
    clamp must not happen on an APPROVED, `paper_faithful` spec -- an
    explicit invalid value should never have passed review in the first
    place."""

    def test_negative_ls_quantile_is_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(portfolio={"sort": {"ls_quantile": -1}})
        result = gate.review(spec)

        assert "portfolio.sort.ls_quantile" in result.blocked_fields
        assert result.approved is False
        assert result.paper_faithful is False

    def test_single_group_ls_quantile_is_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(portfolio={"sort": {"ls_quantile": 1}})
        result = gate.review(spec)

        assert "portfolio.sort.ls_quantile" in result.blocked_fields

    def test_out_of_range_fraction_is_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(portfolio={"sort": {"ls_quantile": 0.9}})
        result = gate.review(spec)

        assert "portfolio.sort.ls_quantile" in result.blocked_fields

    def test_valid_group_count_is_not_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(portfolio={"sort": {"ls_quantile": 10}})
        result = gate.review(spec)

        assert "portfolio.sort.ls_quantile" not in result.blocked_fields

    def test_valid_fraction_is_not_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(portfolio={"sort": {"ls_quantile": 0.1}})
        result = gate.review(spec)

        assert "portfolio.sort.ls_quantile" not in result.blocked_fields


class TestExplicitInvalidFormationMonthIsBlocked:
    """`formation_month=None` (unset) is blocked -- but so must an EXPLICIT
    out-of-range calendar month (e.g. 13, or 0) be, rather than being
    approved as `paper_faithful` and silently passed through by
    build_config."""

    def _spec(self, fm):
        return _minimal_spec(signal={
            "required_fields": ["f"],
            "formula": {"expression": "f"},
            "timing": {"formation_month": fm},
        })

    def test_formation_month_13_is_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        result = gate.review(self._spec(13))

        assert "signal.timing.formation_month" in result.blocked_fields
        assert result.approved is False
        assert result.paper_faithful is False

    def test_formation_month_0_is_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        result = gate.review(self._spec(0))

        assert "signal.timing.formation_month" in result.blocked_fields

    def test_valid_formation_month_is_not_blocked(self):
        gate = ReviewGate(data_dictionary=None)
        result = gate.review(self._spec(6))

        assert "signal.timing.formation_month" not in result.blocked_fields


class TestFullySpecifiedSpecStillPasses:
    def test_no_false_positive_when_every_field_is_explicit(self):
        """A spec that actually specifies every one of these fields must not
        be blocked by the new check -- it should only catch genuine silence,
        not penalize a complete spec."""
        gate = ReviewGate(data_dictionary=None)
        spec = _minimal_spec(
            signal={
                "required_fields": ["f"],
                "formula": {"expression": "f"},
                "sign": 1,
                "timing": {
                    "formation_month": 6,
                    "holding_period": 12,
                    "accounting_lag": 6,
                    "rebalance_frequency": "annual",
                },
                "missing_policy": {"action": "drop"},
            },
            universe={"description": "NYSE/AMEX/NASDAQ common shares", "filters": [
                {"field": "shrcd", "op": "in", "value": [10, 11]},
            ]},
            portfolio={
                "long_leg": "high", "short_leg": "low",
                "weighting": "vw",
                "sort": {"breakpoint_source": "nyse", "ls_quantile": 10},
                "return_combination": {"type": "extreme_group_spread"},
            },
        )
        result = gate.review(spec)

        for field in (
            "portfolio.sort.breakpoint_source",
            "portfolio.weighting",
            "signal.missing_policy",
            "signal.timing.rebalance_frequency",
            "signal.timing.formation_month",
            "signal.timing.holding_period",
            "signal.timing.accounting_lag",
            "signal.sign",
            "portfolio.universe",
            "portfolio.universe_filters",
            "portfolio.return_combination",
            "portfolio.sort.ls_quantile",
        ):
            assert field not in result.blocked_fields, f"{field!r} should not be blocked"
