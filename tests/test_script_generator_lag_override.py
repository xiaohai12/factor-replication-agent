"""Regression test for D4 (docs/multi-config-evidence-plan.md /
docs/decision-log.md 2026-08-03): `generate_backtest_script`'s
`ACCOUNTING_LAG_MONTHS` used to be an independently-templated constant baked
from `spec.accounting_lag_months or 6`, completely ignoring any
`config_overrides={"accounting_lag_months": ...}` passed alongside it -- an
"ablation_lag_12" experiment silently ran on the paper's own lag with zero
effect. Now `ACCOUNTING_LAG_MONTHS = CONFIG["accounting_lag_months"]` at
script run time, so an override that changed the *resolved config* actually
changes what the generated script uses.
"""

from __future__ import annotations

import re

from src.steps.step3_codegen.script_generator import generate_backtest_script
from tests._spec_test_helpers import minimal_resolved_spec


def _spec(accounting_lag_months: int = 6):
    return minimal_resolved_spec("t")


def _plugin_code() -> str:
    return (
        "def compute_signal(df):\n"
        "    return df[['permno', 'time_avail_m']]\n"
    )


class TestAccountingLagMonthsReadsFromConfig:
    def test_no_override_bakes_the_spec_value_into_config(self):
        script = generate_backtest_script(
            _spec(accounting_lag_months=6),
            _plugin_code(),
            signal_input_mode="crsp_only",
        )
        # The resolved CONFIG dict itself carries the spec's own value...
        assert re.search(r'"accounting_lag_months":\s*6,', script)
        # ...and ACCOUNTING_LAG_MONTHS is read from CONFIG at script run time,
        # not templated as its own separate literal.
        assert 'ACCOUNTING_LAG_MONTHS = CONFIG["accounting_lag_months"]' in script
        assert not re.search(r"^ACCOUNTING_LAG_MONTHS = \d+\s*$", script, re.MULTILINE)

    def test_override_changes_the_resolved_config_value(self):
        script = generate_backtest_script(
            _spec(accounting_lag_months=6),
            _plugin_code(),
            signal_input_mode="crsp_only",
            config_overrides={"accounting_lag_months": 12},
        )
        assert re.search(r'"accounting_lag_months":\s*12,', script)
        assert not re.search(r'"accounting_lag_months":\s*6,', script)

    def test_override_is_the_only_source_of_truth_for_the_runtime_constant(self):
        """ACCOUNTING_LAG_MONTHS must read CONFIG, not a second baked literal
        that could drift out of sync with an override."""
        script = generate_backtest_script(
            _spec(accounting_lag_months=6),
            _plugin_code(),
            signal_input_mode="crsp_only",
            config_overrides={"accounting_lag_months": 12},
        )
        assert 'ACCOUNTING_LAG_MONTHS = CONFIG["accounting_lag_months"]' in script
