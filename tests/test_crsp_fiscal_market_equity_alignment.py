"""Focused tests for the Dichev Z-score CRSP fiscal-month alignment."""

from __future__ import annotations

import pandas as pd

from src.infra.data_layer import sources


def test_crsp_price_and_shares_match_compustat_fiscal_month_before_lag(monkeypatch, tmp_path):
    compustat = pd.DataFrame({
        "permno": [10], "time_avail_m": [200306], "lt": [50.0],
    })
    crsp = pd.DataFrame({
        "permno": [10, 10], "time_avail_m": [200212, 200306],
        "prc": [-20.0, -99.0], "shrout": [5_000.0, 7_000.0],
    })

    monkeypatch.setattr(sources, "_load_link_tables", lambda _: {})
    monkeypatch.setattr(
        sources,
        "_load_source_frame",
        lambda _d, name, _cols, _lag, _links: compustat if name == "compustat_fundamental_annual" else crsp,
    )

    out = sources.assemble_signal_master_table_from_sources(
        tmp_path,
        {"compustat_fundamental_annual": ["lt"], "crsp_msf": ["prc", "shrout"]},
        accounting_lag_months=6,
        crsp_fiscal_year_end_columns=["prc", "shrout"],
    )

    assert out.loc[0, "time_avail_m"] == 200306
    assert out.loc[0, "prc"] == -20.0
    assert out.loc[0, "shrout"] == 5_000.0
