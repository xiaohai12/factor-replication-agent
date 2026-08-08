"""C&Z (Chen & Zimmermann) external reference contract (Phase B,
docs/multi-config-evidence-plan.md): a normalized, versioned profile of what
C&Z's OWN metadata (`SignalDoc.csv`) reports for one factor -- their reported
monthly return/t-stat, sign, weighting, breakpoint filter, and sample
window.

Scope, stated plainly: this is metadata-only. It does NOT compute or load
C&Z's actual firm-level signal values -- that requires running C&Z's own
Predictors/*.py or Portfolios/Code/*.R source (see `data/CZ code/`) against
real WRDS data, which is a separate, substantial data-integration task this
module does not attempt. `matched_comparison.py` in this package is written
to consume a real firm-level C&Z signal series WHEN one is loaded by some
future adapter; this module only supplies the reported summary numbers that
are already available today without that adapter.

Reads `SignalDoc.csv` directly via `load_signaldoc` below (moved here from
the retired v1 extraction-eval helpers module) -- this module's
`CZReferenceProfile` is a DIFFERENT normalized shape for a different purpose
(replication-gap comparison, not MethodSpec field-by-field accuracy
scoring), but reads the identical rows.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

_SIGNALDOC_PATH = Path(__file__).resolve().parents[3] / "data" / "osap" / "SignalDoc.csv"


def load_signaldoc(signaldoc_path: Path | None = None) -> dict[str, dict]:
    """Load SignalDoc.csv into {Acronym: row_dict}."""
    path = signaldoc_path or _SIGNALDOC_PATH
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[row["Acronym"]] = row
    return rows


@dataclass
class CZReferenceProfile:
    """One factor's C&Z-reported summary numbers, normalized.

    `acronym` is the SignalDoc.csv `Acronym` this was loaded from -- the
    join key between a `MethodSpec.factor_id` and this profile (that mapping
    itself lives outside this module; a factor->acronym manifest is the
    remaining piece of Phase B's "factor-to-C&Z manifest schema").
    """

    acronym: str
    mean_return: float | None = None      # SignalDoc "Return" (already monthly %, per C&Z convention)
    t_stat: float | None = None           # SignalDoc "T-Stat"
    sign: int | None = None               # +1 / -1
    stock_weight: str | None = None       # "ew" | "vw"
    ls_quantile: float | None = None
    quantile_filter: str | None = None    # e.g. breakpoint universe filter
    portfolio_period: int | None = None   # holding period, months
    start_month: int | None = None        # formation month
    sample_start_year: int | None = None
    sample_end_year: int | None = None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: str | None) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def load_cz_reference_profile(
    acronym: str, signaldoc_path: str | Path | None = None
) -> CZReferenceProfile | None:
    """Load one factor's `CZReferenceProfile` from `SignalDoc.csv` by
    `Acronym`. Returns None if the acronym isn't found or the file isn't
    available (e.g. `data/osap/SignalDoc.csv` not downloaded --
    `scripts/download_osap.py`)."""
    path = Path(signaldoc_path) if signaldoc_path else None
    try:
        rows = load_signaldoc(path) if path else load_signaldoc()
    except FileNotFoundError:
        return None

    row = rows.get(acronym)
    if row is None:
        return None

    return CZReferenceProfile(
        acronym=acronym,
        mean_return=_to_float(row.get("Return")),
        t_stat=_to_float(row.get("T-Stat")),
        sign=_to_int(row.get("Sign")),
        stock_weight=(row.get("Stock Weight") or "").strip().lower() or None,
        ls_quantile=_to_float(row.get("LS Quantile")),
        quantile_filter=(row.get("Quantile Filter") or "").strip() or None,
        portfolio_period=_to_int(row.get("Portfolio Period")),
        start_month=_to_int(row.get("Start Month")),
        sample_start_year=_to_int(row.get("SampleStartYear")),
        sample_end_year=_to_int(row.get("SampleEndYear")),
    )
