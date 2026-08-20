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
}
