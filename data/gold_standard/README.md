# Gold Standard Annotation Guide

## Purpose

Hand-annotated ground truth for evaluating Extractor accuracy. Each entry represents information **directly stated in the original paper** (not C&Z's standardized choices).

## CSV Columns

| Column | Type | Format | Description | Where to Find |
|--------|------|--------|-------------|---------------|
| `factor_id` | string | — | Unique factor ID matching SignalDoc Acronym (e.g. "AssetGrowth") | SignalDoc.csv `Acronym` column |
| `pdf_file` | string | — | Exact PDF filename in `data/papers/` | `data/papers/` directory listing |
| `factor_name` | string | — | Human-readable factor name | Paper title or first mention of the anomaly |
| `economic_intuition` | string | — | 1-2 sentence economic rationale | Introduction or "Hypothesis" section |
| `detailed_definition` | string | — | Exact signal definition in words | "Variable Construction" / "Data" / "Methodology" section |
| `formula` | string | — | Signal formula using database variable names (e.g. `(at - lag(at)) / lag(at)`) | Same as above; translate verbal def to Compustat/CRSP variable names |
| `required_fields` | string | `field:dataset.table:desc; ...` | Semicolon-separated. Each entry: `variable_name:dataset.table:description` | "Data" section — look for "from Compustat/CRSP" statements |
| `cat_form` | string | `continuous` or `discrete` | Whether the signal is continuous or categorical | Implicit: if paper sorts into quantiles from a continuous variable → `continuous`; if signal is a dummy/count → `discrete` |
| `sign` | int | `1` or `-1` | 1 = high signal → high returns; -1 = high signal → low returns | Main results table — check if High portfolio has higher or lower return than Low |
| `formation_month` | int or empty | — | Month when portfolios are formed (e.g. 6 for June). **Leave empty for monthly-rebalanced factors** | "Portfolio Formation" paragraph (e.g. "portfolios formed in June each year") |
| `rebalance_frequency` | string | `annual` / `monthly` / `quarterly` | How often portfolios are reformed | Same paragraph; "held for 12 months" → annual, "reformed monthly" → monthly |
| `holding_period` | int | — | Months the portfolio is held (1 = monthly, 12 = annual) | Same as rebalance_frequency source |
| `accounting_lag` | int | — | Months between fiscal year-end and portfolio formation (e.g. 6) | "We require fiscal year-end data to be available by June" → lag=6 |
| `skip_month` | int or empty | — | Months skipped between signal measurement and formation (e.g. 1 for momentum) | Momentum-type papers: "we skip the most recent month" |
| `stock_weight` | string | `ew` / `vw` / `capped_vw` | Portfolio weighting. If paper reports both, use the **primary** one | Results table header: "Equal-Weighted" vs "Value-Weighted" |
| `ls_quantile` | float | — | Long-short cutoff: 0.1 = deciles, 0.2 = quintiles, 0.3 = terciles, 0.5 = median | Results table: count portfolio columns (D1-D10 → 0.1; Q1-Q5 → 0.2) |
| `breakpoint_source` | string | `nyse` / `full_sample` | Which stocks determine quantile cutoffs | "Breakpoints are based on NYSE stocks" or no mention → likely full_sample |
| `long_leg` | string | `high` / `low` | Which quantile is the long portfolio | Derived from `sign`: if sign=1, long_leg=high; if sign=-1, long_leg=low |
| `short_leg` | string | `high` / `low` | Which quantile is the short portfolio | Opposite of long_leg |
| `universe` | string | — | Sample universe description (e.g. "NYSE + AMEX + NASDAQ, common shares") | "Data" / "Sample" section: "all common stocks on NYSE, AMEX, and NASDAQ" |
| `filter` | string | — | Additional stock-level filters (e.g. `abs(prc)>5, exchcd %in% c(1,2)`) | "We exclude..." statements in Data section |
| `missing_policy` | string | `drop` / `fill_zero` / `fill_median` | How missing signal values are handled | Usually implicit (drop); look for "firms with missing data are excluded" |
| `winsorize_bounds` | string or empty | `1,99` or `0.5,99.5` | Winsorization percentile bounds if `missing_policy` includes winsorization. Leave empty if not used | "Variables are winsorized at the 1st and 99th percentiles" |
| `overlapping_portfolios` | bool or empty | `true` / `false` | Whether the paper uses overlapping holding periods (e.g. 12-month holds formed monthly). Leave empty if not stated | "We use Jegadeesh-Titman overlapping portfolio approach" |
| `return_horizon` | string | `monthly` / `quarterly` / `annual` | Time horizon of `reported_return_spread` (needed to normalize against LS return series in Attribution Layer) | Results table: "Monthly Returns" vs "Annual Returns" in header |
| `cz_acronym` | string | — | Exact `Acronym` value in C&Z SignalDoc.csv. Usually matches `factor_id`; explicit when casing or naming differs | SignalDoc.csv |
| `reported_return_spread` | float or empty | — | Long-short return (%) from paper's main table, in the horizon stated by `return_horizon` | Main results table: "High-Low" or "L/S" column |
| `reported_t_stat` | float or empty | — | t-statistic of LS spread from paper's main table | Same row as return_spread, in parentheses or adjacent column |
| `return_type` | string | `raw` / `ff3_alpha` / `ff5_alpha` / `capm_alpha` | Whether reported return is raw LS spread or risk-adjusted alpha | Table title/header: "Raw Returns" vs "FF3 Alpha" |
| `data_frequency` | string | `annual` / `quarterly` / `monthly` / `daily` | Frequency of underlying data used to compute the signal | "Data" section: "annual Compustat" → annual; "daily CRSP returns" → daily |
| `sample_start_year` | int | — | Paper's sample start year | "Data" section: "Our sample covers 1963-2003" |
| `sample_end_year` | int | — | Paper's sample end year | Same sentence as sample_start_year |
| `paper_ref` | string | — | Full citation (Authors, Year) | Paper title page |
| `paper_sections` | string | `Section A; Table 1; ...` | Semicolon-separated sections/tables where info was found | Record as you annotate — which sections/tables you pulled from |
| `annotator_notes` | string | — | Free-text notes on ambiguities or annotation decisions | Your own notes during annotation |

## Annotation Rules

1. **Only annotate what the paper explicitly states.** If a field is ambiguous or not mentioned, leave it empty.
2. **For monthly-rebalanced factors**, leave `formation_month` empty — there is no fixed formation calendar month.
3. **For `sign`**: +1 means the paper finds that HIGH signal predicts HIGH returns. -1 means HIGH signal predicts LOW returns.
4. **For `long_leg`/`short_leg`**: These follow from `sign`. If sign = -1 (high → low returns), then long_leg = "low", short_leg = "high".
5. **For `reported_return_spread`**: Use the **equal-weighted** long-short return if both EW and VW are reported (unless the paper's primary result is VW). Record the value in the horizon stated by `return_horizon`.
6. **For `return_horizon`**: Always fill this in. Default is `monthly` — only use `quarterly` or `annual` if the paper's main table explicitly reports in those units.
7. **For `formula`**: Use Compustat/CRSP variable names where possible (at, ceq, sale, prcc_f, ret, vol, etc.)
8. **For `required_fields`**: List ALL data fields needed, with source database. Format: `fieldname:compustat.funda:description`
9. **Multi-factor papers**: Add one row per factor. Use the same `pdf_file` for all factors from the same paper.
10. **For `cz_acronym`**: Check the C&Z SignalDoc.csv `Acronym` column. If it matches `factor_id` exactly, you can leave this empty (the converter will fall back to `factor_id`). Only fill if they differ.
11. **For `winsorize_bounds`**: Only fill when `missing_policy = fill_zero` or the paper explicitly describes winsorization. Format: `low_pct,high_pct` (e.g. `1,99`).
12. **For `overlapping_portfolios`**: Use `true` if the paper forms new portfolios every month but holds for >1 month (monthly-updated overlapping). Use `false` for clean calendar-year holds. Leave empty if not stated.

## Conversion

Run the converter to generate JSON for evaluation:

```bash
python scripts/csv_to_gold_standard.py
```

Output: `data/gold_standard/gold_standard.json`

## Target Papers (10)

| # | PDF | Factors | Category |
|---|-----|---------|----------|
| 1 | Asset Growth and the Cross Section of Stock Returns.pdf | AssetGrowth | investment |
| 2 | Abnormal returns to a fundamental analysis strategy.pdf | ChInvIA, GrSaleToGrInv, GrSaleToGrOverhead | investment/sales |
| 3 | Illiquidity and stock returns cross-section and time-series effects.pdf | Illiquidity | liquidity |
| 4 | Accruals, cash flows, and operating profitability...pdf | CBOperProf | profitability |
| 5 | Contrarian investment, extrapolation, and risk.pdf | CF, MeanRankRevGrowth | valuation |
| 6 | The Cross Section of Volatility and Expected Returns.pdf | betaVIX, IdioVol3F, RealizedVol | volatility |
| 7 | Empirical evidence on capital investment, growth options...pdf | grcapx, grcapx3y | investment growth |
| 8 | Maxing out Stocks as lotteries...pdf | MaxRet, AM, BMdec, BookLeverage | mixed |
| 9 | Seasonality in the cross-section of stock returns.pdf | ~10 factors | seasonality |
| 10 | Streaks in earnings surprises...pdf | EarningsStreak, NumEarnIncrease | earnings |
