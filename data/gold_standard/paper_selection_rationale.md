# Why These 10 Papers Were Selected

This note records why we selected these 10 papers for gold-standard annotation.

## Selection Goal

Build a compact set of papers that maximizes extractor stress coverage, not just finance popularity.

Principles:
- Paper-first extraction challenge coverage (what is hard to read from paper text)
- Construction diversity (sorts, regressions, recursive formulas, rank-weighting)
- Return calculation diversity (raw spread, alpha, BHAR, average-leg spread)
- Data-source diversity (accounting, returns, analyst, options, patents/citations)
- Timing/implementation traps (skip month, overlapping portfolios, lag conventions)
- Ambiguity exposure (sign conventions, undocumented implementation details)

## Final 10 and Why

### Printable Paper Name List

Use this list when you need paper names in a clean printable format.

Priority is highest to lowest (1 = highest priority).

1. (High) Cooper, Gulen, and Schill (2008) - Asset Growth and the Cross-Section of Stock Returns
2. (High) Frazzini and Pedersen (2014) - Betting Against Beta
3. (High) Ball, Gerakos, Linnainmaa, and Nikolaev (2016) - Accruals, Cash Flows, and Operating Profitability in the Cross Section of Stock Returns
4. (High) Blitz, Huij, and Martens (2011) - Residual Momentum
5. (High) Abarbanell and Bushee (1998) - Abnormal Returns to a Fundamental Analysis Strategy
6. (Medium) Loh and Warachka (2012) - Streaks in Earnings Surprises and the Cross-Section of Stock Returns
7. (Medium) Eisfeldt and Papanikolaou (2013) - Organization Capital and the Cross-Section of Expected Returns
8. (Medium) Valta (2016) - Strategic Default, Debt Structure, and Stock Returns
9. (Low) Hirshleifer, Hsu, and Li (2013) - Innovative Efficiency and Stock Returns
10. (Low) An, Ang, Bali, and Cakici (2014) - The Joint Cross Section of Stocks and Options

1. AssetGrowth (2008)
- Role: Baseline anchor
- Why included: Clean and simple characteristic sort; useful for calibration and sanity checks
- Key dimensions: one-way sort, equal-weighted long-short, low ambiguity

2. Abarbanell and Bushee (1998)
- Role: Composite and regression-heavy design
- Why included: Multiple signals combined with regression weighting; includes BHAR-style return framing
- Key dimensions: regression-weighted construction, multi-signal composition, nontrivial mapping from text to schema

3. Ball et al. (2016) Operating Profitability
- Role: Canonical Fama-French style benchmark
- Why included: 2x3 independent sorts, NYSE breakpoints, value-weighting, average-leg spread construction
- Key dimensions: characteristic_sort with FF-style mechanics, highly reusable template for many papers

4. Betting Against Beta (BAB, 2014)
- Role: Nonstandard portfolio mechanics
- Why included: Rank-weighting plus beta-leverage scaling; construction is formula-driven and easy to mis-implement
- Key dimensions: rank-weighted zero-investment style, daily beta estimation dependencies

5. Earnings Streaks (2012)
- Role: Conditional and nested sorting challenge
- Why included: Sorting logic is conditional/nested and tied to analyst data conventions; uses factor-model alpha reporting
- Key dimensions: nested sort logic, IBES-style data dependency, multiple return reporting modes

6. Innovative Efficiency (CitationsRD, 2013)
- Role: Alternative data source stress test
- Why included: Uses patents/citations style inputs and less standard signal engineering language
- Key dimensions: non-CRSP/Compustat flavored variables, field-source attribution difficulty

7. Stocks and Options (dVolCall, 2014)
- Role: Derivatives data integration case
- Why included: Option-implied measures and first-difference style signal definitions test parser robustness
- Key dimensions: options data source, transformed signal (delta/changes), timing interpretation risk

8. Organization Capital (OrgCap, 2013)
- Role: Recursive formula extraction
- Why included: Perpetual-inventory recursion with parameter assumptions (depreciation/growth) and industry adjustment
- Key dimensions: recursive signal construction, parameter extraction, long definition chain

9. Residual Momentum (2011)
- Role: Timing trap and overlap stress test
- Why included: Explicit skip-month and overlapping portfolio returns; signal built from regression residual returns
- Key dimensions: skip_month, overlapping portfolios, residual-based momentum signal

10. Strategic Default (ConvDebt, 2016)
- Role: Non-portfolio empirical design
- Why included: Fama-MacBeth style regression framing with dummy-like treatment variables and sign ambiguity
- Key dimensions: regression-centric methodology, ambiguity handling, weaker direct portfolio mapping

## Coverage Matrix (High-Level)

- Baseline simple sort: AssetGrowth
- FF-style 2x3 sort + VW + NYSE breakpoints: Ball 2016
- Rank-weighted and leverage-adjusted construction: BAB
- Composite regression-weighted signal: AB1998
- Nested/conditional sorting: Earnings Streaks
- Recursive formula signal: OrgCap
- Skip-month and overlapping holdings: Residual Momentum
- FM regression-centric paper: Strategic Default
- Alternative data pipeline challenge: CitationsRD
- Options-derived signal challenge: dVolCall

## If We Need to Drop Papers Later

Recommended drop order (lowest incremental extraction coverage first):
1. dVolCall
2. CitationsRD
3. Strategic Default

Keep the core set if reduced to 7:
- AssetGrowth
- AB1998
- Ball 2016
- BAB
- Earnings Streaks
- OrgCap
- Residual Momentum

## Annotation Note

When annotating, always prioritize paper-native evidence quotes and locations. Do not rely on C&Z/OSAP metadata to fill missing paper details.