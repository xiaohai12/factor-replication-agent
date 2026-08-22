"""Tests for `registry.build_config`'s override validation (Phase 0.2, see
docs/multi-config-evidence-plan.md).

Before this change, `build_config` did a blind `config.update(overrides)`:
an unknown key, an off-menu value, or a value that happened to already equal
the resolved default all passed through silently. That makes any
config-diff-based attribution ("track X differs from baseline only in
weighting") unverifiable -- the override might have been a typo that never
took effect. This file locks in the three behaviors `_validate_overrides`
now enforces:

- unknown override key -> `ConfigOverrideError` (hard failure)
- off-menu value for a menu-governed key -> `ConfigOverrideError`
- override value identical to the already-resolved default -> `UserWarning`
  only (not raised -- see `_validate_overrides`'s docstring for why a named
  track bundling several settings must not be rejected wholesale just
  because one of them coincides with the paper's own choice).
"""

from __future__ import annotations

import pytest

from src.steps.step3_codegen.registry import (
    ConfigOverrideError,
    build_config,
    stage_of,
)
from tests._spec_test_helpers import minimal_resolved_spec


def _minimal_spec(weighting: str = "vw"):
    return minimal_resolved_spec("x", weighting=weighting)


class TestUnknownOverrideKeyRejected:
    def test_typo_key_raises(self):
        spec = _minimal_spec()
        with pytest.raises(ConfigOverrideError, match="Unknown config override key"):
            build_config(spec, overrides={"weighitng_rule": "ew"})

    def test_nonexistent_engine_concept_raises(self):
        spec = _minimal_spec()
        with pytest.raises(ConfigOverrideError, match="Unknown config override key"):
            build_config(spec, overrides={"neutralization": "industry"})


class TestOffMenuOverrideValueRejected:
    def test_bad_weighting_rule_value_raises(self):
        spec = _minimal_spec()
        with pytest.raises(ConfigOverrideError, match="must be one of"):
            build_config(spec, overrides={"weighting_rule": "capped_vw"})

    def test_bad_breakpoint_source_value_raises(self):
        spec = _minimal_spec()
        with pytest.raises(ConfigOverrideError, match="must be one of"):
            build_config(spec, overrides={"breakpoint_source": "conditional"})

    def test_valid_menu_value_is_accepted(self):
        spec = _minimal_spec(weighting="vw")  # resolves to "vw"
        config = build_config(spec, overrides={"weighting_rule": "ew"})
        assert config["weighting_rule"] == "ew"


class TestNoOpOverrideWarnsButDoesNotRaise:
    def test_override_matching_resolved_default_warns(self):
        spec = _minimal_spec(weighting="vw")  # resolves to "vw" already
        with pytest.warns(UserWarning, match="no-op"):
            config = build_config(spec, overrides={"weighting_rule": "vw"})
        assert config["weighting_rule"] == "vw"

    def test_override_differing_from_default_does_not_warn(self):
        spec = _minimal_spec(weighting="vw")
        with _no_warnings_context():
            config = build_config(spec, overrides={"weighting_rule": "ew"})
        assert config["weighting_rule"] == "ew"


class _no_warnings_context:
    """Small helper: assert no warning is raised inside the block."""

    def __enter__(self):
        import warnings

        self._catcher = warnings.catch_warnings(record=True)
        self._records = self._catcher.__enter__()
        warnings.simplefilter("always")
        return self._records

    def __exit__(self, exc_type, exc, tb):
        assert not self._records, f"Unexpected warnings: {self._records}"
        self._catcher.__exit__(exc_type, exc, tb)


class TestBreakpointQuantilesOverrideRemapsExtremePortfolios:
    """`breakpoint_quantiles` override must remap `long_portfolios`/
    `short_portfolios` -- otherwise a leg still pointing at the OLD quantile
    count's edge bucket (e.g. `short_portfolios=[10]` under 10 groups)
    references a bucket that doesn't exist once the group count changes,
    silently producing zero rows for the whole track (`extreme_group_spread`
    with an always-empty short leg). Real bug hit by `cz_actual_config` on a
    factor where C&Z's reported quantile count (5) differs from the paper's
    own (10); see docs/decision-log.md 2026-08-22."""

    def test_lower_quantile_count_remaps_both_legs(self):
        # `_minimal_spec` resolves to 10 groups, long=bucket 10 (leg "high"),
        # short=bucket 1 (leg "low") -- see `minimal_resolved_spec`'s legs.
        spec = _minimal_spec()
        baseline = build_config(spec, overrides=None)
        assert baseline["breakpoint_quantiles"] == 10
        assert baseline["long_portfolios"] == [10]
        assert baseline["short_portfolios"] == [1]

        config = build_config(spec, overrides={"breakpoint_quantiles": 5})
        assert config["breakpoint_quantiles"] == 5
        assert config["long_portfolios"] == [5]
        assert config["short_portfolios"] == [1]

    def test_higher_quantile_count_remaps_both_legs(self):
        spec = _minimal_spec()
        config = build_config(spec, overrides={"breakpoint_quantiles": 20})
        assert config["long_portfolios"] == [20]
        assert config["short_portfolios"] == [1]

    def test_non_extreme_leg_raises_instead_of_silently_mismapping(self):
        spec = minimal_resolved_spec("t", weighting="vw")
        spec.paper.portfolio.legs[1].selector["sort1"] = 3  # bucket 4 -- not an edge bucket
        with pytest.raises(ConfigOverrideError, match="Cannot remap"):
            build_config(spec, overrides={"breakpoint_quantiles": 5})


class TestStageTaxonomySingleSourceOfTruth:
    """registry.CONFIG_KEY_STAGE is now the single source of truth; bundle.py
    re-imports it. See docs/multi-config-evidence-plan.md Decision 2."""

    def test_signal_input_stage(self):
        assert stage_of("accounting_lag_months") == "signal_input"

    def test_portfolio_stage(self):
        assert stage_of("breakpoint_source") == "portfolio"

    def test_unclassified_key(self):
        assert stage_of("some_future_key") == "unclassified"

    def test_bundle_module_reexports_same_object(self):
        from src.steps.step3_codegen import registry
        from src.steps.step7_replication_diff import bundle

        assert bundle.CONFIG_KEY_STAGE is registry.CONFIG_KEY_STAGE
        assert bundle.stage_of is registry.stage_of
