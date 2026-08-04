"""Human-facing help metadata for the fields a human is asked to resolve
during step2 review -- answers two recurring UX questions:

1. "What is this field actually for?" -- `FIELD_DESCRIPTIONS`, a one-line
   plain-language explanation per dotted `MethodSpec` path, scoped to
   exactly the fields `ReviewGate` can ever block
   (`src.steps.step2_reviewer.HIGH_IMPACT_FIELDS`) plus a couple of other
   commonly-blocked non-"high-impact" paths seen in practice
   (`returns_universe`, `data.normalized_mapping`).
2. "Can I pick from a list instead of typing a value?" -- `FIELD_OPTIONS`,
   built directly from the real `MethodSpec` enums (not a hand-duplicated
   list) for fields backed by one, so the options shown are guaranteed to
   stay in sync with what the engine actually accepts. Every enum here
   already carries an `OTHER`/`UNSPECIFIED` member (see method_spec.py) --
   selecting `other` is a legitimate choice, not a special case bolted on
   here. Fields with no natural enum (e.g. a numeric lag, free-text universe
   description) simply have no entry -- the UI falls back to a plain text
   input for those, same as today.

Never used to make an empirical decision itself -- purely descriptive help
text/options for a human filling in `POST /api/methodspecs/resolve`'s
`new_value`.
"""

from __future__ import annotations

from src.infra.models.method_spec import (
    BreakpointSource,
    RebalanceFrequency,
    ReturnCombinationType,
    WeightingRule,
)

FIELD_DESCRIPTIONS: dict[str, str] = {
    "signal.formula": "The executable formula compute_signal implements (e.g. asset growth rate, accruals).",
    "signal.sign": "Whether a HIGHER signal value should be sorted into the LONG (+1) or SHORT (-1) leg.",
    "signal.timing.accounting_lag": "How many months after fiscal year-end the accounting data is assumed to become public (avoids look-ahead bias).",
    "timing.accounting_lag_months": "How many months after fiscal year-end the accounting data is assumed to become public (avoids look-ahead bias).",
    "signal.timing.formation_month": "The calendar month (1-12) each year when portfolios are re-formed/re-sorted.",
    "signal.timing.rebalance_frequency": "How often portfolios are re-formed and re-weighted (monthly/quarterly/annual).",
    "signal.timing.holding_period": "How many months a formed portfolio is held before the next rebalance.",
    "signal.missing_policy": "What to do with firm-months where the signal can't be computed (drop, winsorize, etc.).",
    "portfolio.sort.breakpoint_source": "Which universe's cutoffs define the sort breakpoints (e.g. NYSE-only vs. the full sample) -- affects how many stocks fall in each decile.",
    "portfolio.sort.ls_quantile": "How many groups the sort splits stocks into (e.g. 10 for deciles, 5 for quintiles).",
    "portfolio.weighting": "How stocks are weighted within a portfolio (value-weighted by market cap vs. equal-weighted).",
    "portfolio.universe": "Which stocks are eligible at all (exchange listing, share-code, industry exclusions, etc.).",
    "portfolio.universe_filters": "Explicit row-level filters applied to the universe (e.g. exclude financial firms, exclude SIC codes 6000-6999).",
    "portfolio.long_leg": "Which side of the sort (low or high signal value) is bought (the LONG leg).",
    "portfolio.short_leg": "Which side of the sort (low or high signal value) is sold short (the SHORT leg).",
    "portfolio.implied_factor_direction": "The paper's stated long-minus-short direction, used to align the backtest's sign with the paper's own reporting convention.",
    "portfolio.construction_type": "How the portfolio is built from the signal (characteristic sort is the only engine-supported method today).",
    "portfolio.return_combination": "How the long and short leg returns are combined into one reported spread return.",
    "reported_results.return_horizon": "Over what holding period the paper's headline return figures are computed/reported.",
    "reported_results.spreads": "The paper's own reported return/alpha spread figures, used later for the replication-gap comparison (step7).",
    "returns_universe": "Which registered stock-return panel/universe (e.g. CRSP monthly) supplies the portfolio-construction return series.",
    "data.normalized_mapping": "How the paper's named accounting/return concepts map onto actual physical data columns (e.g. Compustat item 6 -> 'at').",
}

FIELD_OPTIONS: dict[str, list[str]] = {
    "signal.timing.rebalance_frequency": [e.value for e in RebalanceFrequency],
    "portfolio.sort.breakpoint_source": [e.value for e in BreakpointSource],
    "portfolio.weighting": [e.value for e in WeightingRule],
    "portfolio.return_combination": [e.value for e in ReturnCombinationType],
    # Not a MethodSpec enum -- `normalize_leg()` (registry.py) only ever
    # recognizes these two tokens (substring match), falling back to a
    # field-specific default for anything else. Offered as a convenience
    # list, not a hard schema constraint.
    "portfolio.long_leg": ["low", "high", "other"],
    "portfolio.short_leg": ["low", "high", "other"],
}


def get_field_help(field_path: str) -> dict:
    return {
        "description": FIELD_DESCRIPTIONS.get(field_path, ""),
        "options": FIELD_OPTIONS.get(field_path, []),
    }


def all_field_help() -> dict[str, dict]:
    paths = set(FIELD_DESCRIPTIONS) | set(FIELD_OPTIONS)
    return {path: get_field_help(path) for path in sorted(paths)}
