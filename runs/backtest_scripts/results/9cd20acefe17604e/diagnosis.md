# Replication Diagnosis: 9cd20acefe17604e

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `contradicted`
- Paper: Cooper, Michael J., Huseyin Gulen, and Michael J. Schill, 2008, Asset Growth and the Cross-Section of Stock Returns, The Journal of Finance 63(4), 1609–1651.
- Generated: 2026-08-19T05:59:38.269899+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | alpha_ff3 | 0.00360709 | -0.007 | 0.0106071 | false | 3.60359 | 432 |
| cz_actual_config | alpha_ff3 | 0.0141695 | -0.007 | 0.0211695 | false | 7.1109 | 432 |
| factorial_universe | alpha_ff3 | 0.00461518 | -0.007 | 0.0116152 | false | 4.0873 | 432 |
| factorial_breakpoint | alpha_ff3 | 0.00396487 | -0.007 | 0.0109649 | false | 3.73498 | 432 |
| cz_factorial_universe | alpha_ff3 | 0.0050977 | -0.007 | 0.0120977 | false | 3.98627 | 432 |
| cz_factorial_weighting | alpha_ff3 | 0.0154895 | -0.007 | 0.0224895 | false | 7.39237 | 432 |
| original_method | alpha_ff3 | 0.00505329 | -0.007 | 0.0120533 | false | 4.12391 | 432 |

## Gap decomposition

Not available — replication diff not computed (requires both an original_method and a standardized_hxz run).

## Summary

**Compared with C&Z's independent replication of this paper, the differences are explained by paper ambiguity or C&Z's own conventions, but at least one has a statistically significant effect.**

- Our spread: +0.00505/month (t=4.12). C&Z's: +0.01417/month (t=7.11). Total difference: -0.00912/month.
- The catalogued setting(s) below have a combined isolated effect of -0.00721/month (79% of the total). The remaining -0.00190/month (21%) is not produced by any of them -- one-at-a-time from a single baseline: contributions need not be additive, may depend on switch order, and do not identify interactions.
- Portfolio weighting: we use value-weighted, C&Z uses equal-weighted -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: -0.00764/month (t=-3.04), statistically significant.
- Stock universe: the paper describes its universe as: "NYSE, Amex, and NASDAQ nonfinancial firms listed on CRSP, excluding firms with SIC codes from 6000 through 6999.", C&Z's version is ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: +0.00043/month (t=0.56), not statistically significant.
- Formation lag: we use 0 months, C&Z uses 1 month -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: no paired-test evidence is available for this setting.

- Verdict: `contradicted`
- _No C&Z signal bridge track was run for this factor, so any residual gap above cannot be attributed between a difference in how the signal formula itself was read and a difference in data or sample -- this report cannot separate the two._

**Sensitivity/stability evidence for this replication:**

- Standardized HXZ protocol (a named case, not a competing replication): compared with the fully standardized HXZ protocol, our implementation's effect differs by 0.0022/month, though a joint test does not confirm this.
- Breakpoint source: contribution share not shown (the total change is not statistically confirmed). Effect: +0.00180/month (t=1.29), not statistically significant.
- Stock universe: contribution share not shown (the total change is not statistically confirmed). Effect: +0.00052/month (t=0.87), not statistically significant.
- Our own replication DOES decay after publication (in-sample t=4.12, post-publication t=0.16).
- The t-stat gap vs the standardized HXZ protocol is driven mainly by the mean-return channel, not the others -- so it is not simply an artefact of a misaligned sample window.

- Verdict: `contradicted`
- _Used as sensitivity context, not itself the reproducibility question._

**HXZ's own published result differs from the paper's own reported spread by +0.0131 per month.**

- Our own run's distance from the paper's number: +0.0121 per month
- How the signal itself was computed (plus data-vintage and engine differences): +0.0025 per month
- Portfolio-construction settings alone: -0.0014 per month
- The largest single component is our own run's distance from the paper's number. This is an exact arithmetic split of the total distance, not a controlled experiment: it shows where the distance sits, not what caused it.
- Recomputing HXZ's own published result over its own paper's sample window instead of this paper's moves it by +0.0016 per month -- a measure of how much the choice of sample window alone matters here.

- Verdict: `contradicted`
- _The three components are not equally clean: only the settings component holds the signal fixed on both sides. The first also absorbs data-vintage and engine differences, and the last is our own replication error rather than anything the paper left ambiguous. The four numbers being compared also do not share a common sample window or estimator._

- Verdict: `contradicted`

**Compared with the paper's own reported result, our reviewed implementation of the paper's method has the OPPOSITE sign from it; its magnitude is 0.72x the paper's own reported spread.**

- 2 setting(s) were never specified by the paper at all and were filled by an engine default: accounting lag, missing-data policy.
- _Part of this magnitude gap may reflect these silent defaults rather than a difference in how the paper's stated method was implemented -- this comparison cannot separate the two._
