"""Tests for `src.infra.reference.cz_bridge` (Phase C/D bridge, real but
bounded): `asset_growth_from_panel`/`accruals_from_panel` are direct ports of
C&Z's own formulas (`data/CZ code/Signals/pyCode/Predictors/AssetGrowth.py` /
`Accruals.py`), adapted for this repo's annual (not monthly-forward-filled)
panel shape (1-row shift instead of their literal 12-row shift -- see each
function's docstring for why these are the SAME economic quantity on the two
different panel shapes).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.infra.reference.cz_bridge import (
    CZ_BRIDGE_SIGNALS,
    accruals_from_panel,
    asset_growth_from_panel,
    compute_cz_bridge_signal,
    convdebt_from_panel,
)


def _panel(rows):
    return pd.DataFrame(rows, columns=["permno", "time_avail_m", "at"])


class TestAssetGrowthFromPanel:
    def test_matches_hand_computed_growth_rate(self):
        # permno 1: at grows 100 -> 110 (year 1) -> 121 (year 2), a flat 10%/yr.
        panel = _panel([
            (1, 199706, 100.0),
            (1, 199806, 110.0),
            (1, 199906, 121.0),
        ])
        out = asset_growth_from_panel(panel)
        # First observation has no prior year -> dropped (NaN).
        assert len(out) == 2
        assert out.iloc[0]["yyyymm"] == 199806
        assert out.iloc[0]["signal"] == pytest.approx(0.10)
        assert out.iloc[1]["yyyymm"] == 199906
        assert out.iloc[1]["signal"] == pytest.approx(0.10)

    def test_first_observation_per_firm_has_no_prior_year_and_is_dropped(self):
        panel = _panel([(1, 199706, 100.0)])
        out = asset_growth_from_panel(panel)
        assert len(out) == 0

    def test_division_by_zero_treated_as_missing_and_dropped(self):
        panel = _panel([(1, 199706, 0.0), (1, 199806, 50.0)])
        out = asset_growth_from_panel(panel)
        assert len(out) == 0

    def test_negative_growth(self):
        panel = _panel([(1, 199706, 100.0), (1, 199806, 90.0)])
        out = asset_growth_from_panel(panel)
        assert out.iloc[0]["signal"] == pytest.approx(-0.10)

    def test_multiple_firms_independent_groupby(self):
        panel = _panel([
            (1, 199706, 100.0), (1, 199806, 110.0),
            (2, 199706, 200.0), (2, 199806, 180.0),
        ])
        out = asset_growth_from_panel(panel)
        by_permno = {row["permno"]: row["signal"] for _, row in out.iterrows()}
        assert by_permno[1] == pytest.approx(0.10)
        assert by_permno[2] == pytest.approx(-0.10)

    def test_output_columns_match_our_own_signal_parquet_shape(self):
        panel = _panel([(1, 199706, 100.0), (1, 199806, 110.0)])
        out = asset_growth_from_panel(panel)
        assert list(out.columns) == ["permno", "yyyymm", "signal"]


class TestComputeCzBridgeSignalRegistry:
    def test_registered_factor_returns_a_dataframe(self, tmp_path, monkeypatch):
        def fake_assemble(data_dir, sources, lag_months):
            assert sources == {"comp_funda": ["at"]}
            assert lag_months == 6
            return _panel([(1, 199706, 100.0), (1, 199806, 110.0)])

        monkeypatch.setattr(
            "src.infra.data_layer.sources.assemble_signal_master_table_from_sources",
            fake_assemble,
        )
        out = compute_cz_bridge_signal(
            "cooper_gulen_schill_2008_asset_growth", tmp_path
        )
        assert out is not None
        assert list(out.columns) == ["permno", "yyyymm", "signal"]

    def test_unregistered_factor_returns_none(self, tmp_path):
        assert compute_cz_bridge_signal("not_a_registered_factor", tmp_path) is None

    def test_registry_contains_asset_growth(self):
        assert "cooper_gulen_schill_2008_asset_growth" in CZ_BRIDGE_SIGNALS

    def test_registry_contains_accruals(self):
        assert "sloan_1996_accruals" in CZ_BRIDGE_SIGNALS

    def test_registry_contains_convdebt(self):
        assert "Valta_StrategicDefault_ConvertibleDebt" in CZ_BRIDGE_SIGNALS


def _convdebt_panel(rows):
    return pd.DataFrame(rows, columns=["permno", "time_avail_m", "dc", "cshrc"])


class TestConvDebtFromPanel:
    def test_nonzero_dc_gives_one(self):
        panel = _convdebt_panel([(1, 199706, 5.0, 0.0)])
        out = convdebt_from_panel(panel)
        assert out.iloc[0]["signal"] == 1

    def test_nonzero_cshrc_gives_one(self):
        panel = _convdebt_panel([(1, 199706, 0.0, 3.0)])
        out = convdebt_from_panel(panel)
        assert out.iloc[0]["signal"] == 1

    def test_both_zero_gives_zero(self):
        panel = _convdebt_panel([(1, 199706, 0.0, 0.0)])
        out = convdebt_from_panel(panel)
        assert out.iloc[0]["signal"] == 0

    def test_missing_values_treated_as_zero_not_dropped(self):
        panel = _convdebt_panel([(1, 199706, float("nan"), float("nan"))])
        out = convdebt_from_panel(panel)
        assert len(out) == 1  # never dropped, unlike asset_growth/accruals
        assert out.iloc[0]["signal"] == 0

    def test_no_lag_signal_available_same_period_as_input(self):
        """Unlike asset_growth/accruals, ConvDebt has no shift -- even a
        single observation (no prior year) produces a real signal value."""
        panel = _convdebt_panel([(1, 199706, 5.0, 0.0)])
        out = convdebt_from_panel(panel)
        assert len(out) == 1
        assert out.iloc[0]["yyyymm"] == 199706

    def test_duplicate_firm_month_rows_deduplicated_keep_first(self):
        panel = _convdebt_panel([
            (1, 199706, 5.0, 0.0),
            (1, 199706, 0.0, 0.0),  # duplicate, should be ignored
        ])
        out = convdebt_from_panel(panel)
        assert len(out) == 1
        assert out.iloc[0]["signal"] == 1


def _accruals_panel(rows):
    return pd.DataFrame(
        rows, columns=["permno", "time_avail_m", "act", "che", "lct", "dlc", "at", "dp"]
    )


class TestAccrualsFromPanel:
    def test_matches_hand_computed_accruals(self):
        # act grows by 100 each year, everything else constant -> Sloan
        # accruals = (act - l.act) / avg_at = 100 / 1000 = 0.10.
        panel = _accruals_panel([
            (1, 199706, 500.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
            (1, 199806, 600.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
        ])
        out = accruals_from_panel(panel)
        assert len(out) == 1
        assert out.iloc[0]["yyyymm"] == 199806
        assert out.iloc[0]["signal"] == pytest.approx(0.10)

    def test_missing_txp_column_treated_as_zero(self):
        # No "txp" column at all -- same as C&Z's own fillna(0) for missing
        # tax payable.
        panel = _accruals_panel([
            (1, 199706, 500.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
            (1, 199806, 600.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
        ])
        assert "txp" not in panel.columns
        out = accruals_from_panel(panel)
        assert out.iloc[0]["signal"] == pytest.approx(0.10)

    def test_depreciation_reduces_accruals(self):
        panel = _accruals_panel([
            (1, 199706, 500.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
            (1, 199806, 600.0, 0.0, 0.0, 0.0, 1000.0, 50.0),
        ])
        out = accruals_from_panel(panel)
        assert out.iloc[0]["signal"] == pytest.approx((100.0 - 50.0) / 1000.0)

    def test_first_observation_per_firm_dropped(self):
        panel = _accruals_panel([(1, 199706, 500.0, 0.0, 0.0, 0.0, 1000.0, 0.0)])
        out = accruals_from_panel(panel)
        assert len(out) == 0

    def test_duplicate_firm_month_rows_deduplicated_keep_first(self):
        panel = _accruals_panel([
            (1, 199706, 500.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
            (1, 199806, 600.0, 0.0, 0.0, 0.0, 1000.0, 0.0),
            (1, 199806, 999.0, 0.0, 0.0, 0.0, 1000.0, 0.0),  # duplicate, should be ignored
        ])
        out = accruals_from_panel(panel)
        assert len(out) == 1
        assert out.iloc[0]["signal"] == pytest.approx(0.10)


class TestRealSyntheticDataIntegration:
    """Full path: our own DataLayer's real assembly function (not mocked)
    against the SAME synthetic Compustat fixture the MVP e2e test uses,
    proving this bridge produces sane output against our actual data-loading
    code, not just a hand-rolled panel."""

    def test_bridge_matches_synthetic_fixture_growth_rates(self, tmp_path):
        import pyarrow  # noqa: F401 -- skip cleanly if pyarrow isn't available
        from tests.synthetic_data.asset_growth_synthetic_data import (
            GROWTH_RATES,
            build_ccm_link,
            build_compustat_funda,
        )
        from src.infra.data_layer.sources import assemble_signal_master_table_from_sources

        local_dir = tmp_path
        build_compustat_funda().to_parquet(local_dir / "comp_funda.parquet", index=False)
        # The declarative loader's registered "ccm" link table expects the
        # permno column named "lpermno" (see `LinkTableSpec(permno_column=
        # "lpermno")` in src/infra/data_layer/sources.py) -- the synthetic
        # fixture's own "permno" column name matches a different (legacy)
        # loading path, so rename for this one.
        build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
            local_dir / "ccm_lnkhist.parquet", index=False
        )

        panel = assemble_signal_master_table_from_sources(
            local_dir, {"comp_funda": ["at"]}, accounting_lag_months=6
        )
        out = asset_growth_from_panel(panel)

        # Each permno has 2 fiscal-year transitions (1996->1997, 1997->1998)
        # at its own fixed growth rate (see GROWTH_RATES) -- both transitions
        # should recover the same rate for that firm.
        for idx, expected_rate in enumerate(GROWTH_RATES):
            permno = 10000 + idx + 1
            firm_rows = out[out["permno"] == permno]
            assert len(firm_rows) == 2
            for rate in firm_rows["signal"]:
                assert rate == pytest.approx(expected_rate, abs=1e-9)

    def test_accruals_bridge_matches_synthetic_fixture_values(self, tmp_path):
        import pyarrow  # noqa: F401
        from tests.synthetic_data.accruals_synthetic_data import (
            ACCRUAL_VALUES,
            build_compustat_funda as build_accruals_funda,
        )
        from tests.synthetic_data.asset_growth_synthetic_data import build_ccm_link
        from src.infra.data_layer.sources import assemble_signal_master_table_from_sources

        local_dir = tmp_path
        # The shared fixture doesn't include a "txp" column (accruals'
        # design deliberately holds every OTHER non-"at"/"act" field at a
        # constant matching zero) -- add it here (rather than editing the
        # shared fixture module every other accruals test depends on) so
        # the real column-selection path (`comp_funda: [..., "txp"]`)
        # resolves; entirely-missing txp is economically equivalent to the
        # column being present and all-NaN (both fillna(0)).
        funda = build_accruals_funda()
        funda["txp"] = float("nan")
        funda.to_parquet(local_dir / "comp_funda.parquet", index=False)
        build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
            local_dir / "ccm_lnkhist.parquet", index=False
        )

        panel = assemble_signal_master_table_from_sources(
            local_dir,
            {"comp_funda": ["act", "che", "lct", "dlc", "at", "dp", "txp"]},
            accounting_lag_months=6,
        )
        out = accruals_from_panel(panel)

        for idx, expected_value in enumerate(ACCRUAL_VALUES):
            permno = 10000 + idx + 1
            firm_rows = out[out["permno"] == permno]
            assert len(firm_rows) == 2
            for value in firm_rows["signal"]:
                assert value == pytest.approx(expected_value, abs=1e-9)
