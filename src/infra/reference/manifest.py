"""Static `MethodSpec.factor_id` -> C&Z `SignalDoc` acronym manifest for the
step6 UI's C_cz preview (docs/step6.md gap #1). Deliberately hand-verified,
one entry at a time -- NOT auto-matched by string similarity, since our
factor_id naming scheme and C&Z's acronym scheme differ (e.g.
`BlitzHuijMartens_ResidualMomentum` -> `ResidualMomentum`,
`FrazziniPedersen2014_BAB_US_Equity` -> `BetaFP`, cross-referenced via
`data/CZ code/Docs/Comparison_to_MetaReplications.csv`, see docs/step6.md
\u00a712). Add one confirmed entry at a time as more candidate factors are
reviewed; never guess an unverified mapping here.
"""

from __future__ import annotations

CZ_FACTOR_ACRONYM_MANIFEST: dict[str, str] = {
    "AssetGrowth": "AssetGrowth",
    "GP": "GP",
    "Mom6m": "Mom6m",
    # Datar/Naik/Radcliffe 1998, *Liquidity and Stock Returns*. Verified
    # against C&Z's SignalDoc ("ShareVol", Authors "Datar, Naik, Radcliffe",
    # Year "1998") and their Predictors/ShareVol.py. No hashed extraction
    # factor_id exists for this one yet (self-mapped like AssetGrowth/GP/
    # Mom6m above) -- update the key once a real MethodSpec extraction
    # assigns this factor a generated factor_id.
    "ShareVol": "ShareVol",
    # Lakonishok/Shleifer/Vishny 1994, *Contrarian Investment, Extrapolation,
    # and Risk*. Verified against C&Z's SignalDoc ("MeanRankRevGrowth",
    # Authors "Lakonishok, Shleifer, Vishny", Year "1994") and their
    # Predictors/MeanRankRevGrowth.py. Self-mapped like ShareVol above -- no
    # extracted MethodSpec/hashed factor_id exists for it yet.
    "MeanRankRevGrowth": "MeanRankRevGrowth",
    # Dichev (1998), *Is the Risk of Bankruptcy a Systematic Risk?*.
    # Verified against C&Z's SignalDoc and their Placebos/ZScore.py.
    "d5661ba61aae804d": "ZScore",
    # Dichev (1998), *Is the Risk of Bankruptcy a Systematic Risk?*, Ohlson
    # O-score track. Verified against C&Z's SignalDoc ("OScore", Authors
    # "Dichev", Year "1998") and their Predictors/OScore.py.
    "4cd27ae719671ce1": "OScore",
}
