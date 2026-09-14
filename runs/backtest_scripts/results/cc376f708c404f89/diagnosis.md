# Replication Diagnosis: cc376f708c404f89

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `inconclusive`
- Paper: Datar, Vinay T., Narayan Y. Naik, and Robert Radcliffe. 1998. "Liquidity and stock returns: An alternative test." Journal of Financial Markets 1: 203-219.
- Generated: 2026-08-24T09:35:33.175645+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | unavailable | n/a | -0.04 | n/a | n/a | 0.0265051 | 348 |
| cz_actual_config | unavailable | n/a | -0.04 | n/a | n/a | 0.893605 | 360 |
| ablation_breakpoint | unavailable | n/a | -0.04 | n/a | n/a | 0.0286797 | 348 |
| ablation_lag | unavailable | n/a | -0.04 | n/a | n/a | 0.0286797 | 348 |
| ablation_rebalance | unavailable | n/a | -0.04 | n/a | n/a | 0.243675 | 348 |
| ablation_universe | unavailable | n/a | -0.04 | n/a | n/a | 0.00247198 | 348 |
| cz_ablation_weighting | unavailable | n/a | -0.04 | n/a | n/a | 1.02845 | 348 |
| cz_ablation_lag | unavailable | n/a | -0.04 | n/a | n/a | 0.0286797 | 348 |
| cz_ablation_rebalance | unavailable | n/a | -0.04 | n/a | n/a | 0.243675 | 348 |
| cz_ablation_universe | unavailable | n/a | -0.04 | n/a | n/a | 0.107204 | 348 |
| cz_ablation_quantiles | unavailable | n/a | -0.04 | n/a | n/a | 0.00641653 | 348 |
| original_method | unavailable | n/a | -0.04 | n/a | n/a | 0.0286797 | 348 |

## Gap decomposition

Not available — replication diff not computed (requires both an original_method and a standardized_hxz run).

## Summary

> C&Z's and HXZ's own published results for this factor DISAGREE with each other -- this is independent of anything our engine ran.

**Compared with C&Z's independent replication of this paper, at least one difference is NOT explained by paper ambiguity or a catalogued C&Z convention -- this warrants human review rather than being written off as expected variation.**

_Rows tagged "C&Z convention" are overridden by C&Z the same way for every factor, regardless of what this paper itself says -- not paper ambiguity, and not a likely implementation error._

- **Portfolio weighting** [C&Z convention]: ours = value-weighted, theirs = equal-weighted. Effect: -0.00258/month (t=-2.20), statistically significant.
- **Rebalance frequency** [unresolved]: ours = monthly, theirs = annual. Effect: -0.00068/month (t=-0.73), not statistically significant. Not explained by paper ambiguity or a catalogued C&Z convention -- an open question warranting human review.
- **Stock universe** [C&Z convention]: ours = the paper describes it as: "All non-financial firms on the NYSE.", theirs = ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says. Effect: -0.00023/month (t=-0.55), not statistically significant.
- **Number of portfolio groups** [C&Z convention]: ours = 10 groups (deciles), theirs = 5 groups (quintiles). Effect: +0.00007/month (t=0.07), not statistically significant.
- **Accounting lag** [C&Z convention]: ours = 1 month, theirs = 6 months. Effect: no paired-test evidence is available for this setting.
- **Formation lag** [C&Z convention]: ours = 0 months, theirs = 1 month. Effect: no paired-test evidence is available for this setting.
- **Holding period** [unresolved]: ours = 1, theirs = 12. Effect: no paired-test evidence is available for this setting. Not explained by paper ambiguity or a catalogued C&Z convention -- an open question warranting human review.
- **Sample start year** [unresolved]: ours = 1963, theirs = 1962. Effect: no paired-test evidence is available for this setting. Not explained by paper ambiguity or a catalogued C&Z convention -- an open question warranting human review.

- Verdict: `inconclusive`
- _Joint test unavailable on this line: HAC covariance matrix of the contrast means is singular. No C&Z signal bridge track was run for this factor, so any residual gap above cannot be attributed between a difference in how the signal formula itself was read and a difference in data or sample -- this report cannot separate the two._

**Across 4 alternative implementation choice(s), the result is NOT fully stable: 1 sign flip(s), 0 significance-threshold crossing(s) (t-stat range 0.79).**

- Post-publication decay is not identifiable here: our own replication was already not statistically significant in-sample.
- The t-stat gap vs the standardized HXZ protocol is driven mainly by the volatility channel, not the others -- so it is not simply an artefact of a misaligned sample window.

- Verdict: `inconclusive`
- _Used as sensitivity context, not itself the reproducibility question._

- Verdict: `inconclusive`
