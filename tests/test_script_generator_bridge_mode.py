"""Tests for `generate_backtest_script`'s `precomputed_signal_path` mode
(C&Z bridge track support, docs/multi-config-evidence-plan.md Phase C/D):
the generated script must skip `compute_signal()` entirely and load a given
parquet path directly as the signal when this is set.
"""

from __future__ import annotations

from src.steps.step3_codegen.script_generator import generate_backtest_script
from tests._spec_test_helpers import minimal_resolved_spec


def _spec():
    return minimal_resolved_spec("t")


def _plugin_code() -> str:
    return "def compute_signal(df):\n    return df[['permno', 'time_avail_m']]\n"


class TestPrecomputedSignalPathMode:
    def test_no_precomputed_path_computes_signal_normally(self):
        script = generate_backtest_script(
            _spec(), _plugin_code(), signal_input_mode="crsp_only",
        )
        assert 'PRECOMPUTED_SIGNAL_PATH = ""' in script
        assert "signal = compute_signal(signal_input)" in script

    def test_precomputed_path_skips_compute_signal(self):
        script = generate_backtest_script(
            _spec(), _plugin_code(), signal_input_mode="crsp_only",
            precomputed_signal_path="/tmp/some_bridge_signal.parquet",
        )
        assert 'PRECOMPUTED_SIGNAL_PATH = "/tmp/some_bridge_signal.parquet"' in script
        assert "if PRECOMPUTED_SIGNAL_PATH:" in script
        assert "pd.read_parquet(PRECOMPUTED_SIGNAL_PATH)" in script

    def test_signal_series_persistence_still_happens_in_bridge_mode(self):
        """The realized-signal artifact (Phase A1.1) must still be written
        even when the signal came from a bridge, not compute_signal()."""
        script = generate_backtest_script(
            _spec(), _plugin_code(), signal_input_mode="crsp_only",
            precomputed_signal_path="/tmp/bridge.parquet",
        )
        assert "signal_path = Path(OUTPUT_PATH)" in script
        assert 'signal[["permno", "yyyymm", "signal"]].to_parquet(signal_path' in script
