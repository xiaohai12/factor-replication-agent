# Replication Diagnosis: fae312b1730eefb6

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `reproduced`
- Paper: Cooper, Michael J., Huseyin Gulen, and Michael J. Schill, 2008, Asset Growth and the Cross-Section of Stock Returns, The Journal of Finance 63(4), 1609–1651.
- Generated: 2026-08-24T09:35:39.170394+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | mean_return | 0.00713173 | 0.0105 | -0.00336827 | true | 3.60359 | 432 |
| cz_actual_config | mean_return | 0.0153624 | 0.0105 | 0.00486239 | true | 7.10924 | 432 |
| factorial_universe | mean_return | 0.00877491 | 0.0105 | -0.00172509 | true | 4.0873 | 432 |
| factorial_breakpoint | mean_return | 0.00749264 | 0.0105 | -0.00300736 | true | 3.73494 | 432 |
| cz_factorial_universe | mean_return | 0.00886729 | 0.0105 | -0.00163271 | true | 3.98618 | 432 |
| cz_factorial_weighting | mean_return | 0.016925 | 0.0105 | 0.006425 | true | 7.39023 | 432 |
| original_method | mean_return | 0.00929338 | 0.0105 | -0.00120662 | true | 4.12386 | 432 |

## Gap decomposition

Not available — replication diff not computed (requires both an original_method and a standardized_hxz run).

## Summary

> C&Z's and HXZ's own published results for this factor agree with each other: both report a statistically significant effect in the same direction.

**Compared with C&Z's independent replication of this paper, the differences are explained by paper ambiguity or C&Z's own conventions, but at least one has a statistically significant effect.**

_Rows tagged "C&Z convention" are overridden by C&Z the same way for every factor, regardless of what this paper itself says -- not paper ambiguity, and not a likely implementation error._

- **Portfolio weighting** [C&Z convention]: ours = value-weighted, theirs = equal-weighted. Effect: -0.00763/month (t=-3.03), statistically significant.
- **Stock universe** [C&Z convention]: ours = the paper describes it as: "NYSE, Amex, and NASDAQ nonfinancial firms listed on CRSP monthly stock return files and Compustat annual industrial files, excluding firms with four-digit SIC codes from 6000 through 6999.", theirs = ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says. Effect: +0.00043/month (t=0.56), not statistically significant.
- **Formation lag** [C&Z convention]: ours = 0 months, theirs = 1 month. Effect: no paired-test evidence is available for this setting.

- Our spread: +0.00929/month (t=4.12). C&Z's: +0.01536/month (t=7.11). Total difference: -0.00607/month.
- The catalogued setting(s) below have a combined isolated effect of -0.00721/month (119% of the total). The remaining +0.00114/month (-19%) is not produced by any of them -- one-at-a-time from a single baseline: contributions need not be additive, may depend on switch order, and do not identify interactions.
- Running C&Z's exact config through our engine reproduces their own published number closely (0.89x their spread, same sign, both statistically significant) -- our reimplementation of their protocol is trustworthy.
- For the setting(s) a full-factorial design covers (portfolio weighting -0.00706/month; stock universe +0.00099/month), a Shapley decomposition (exact, averaged over introduction order -- unlike the one-at-a-time figures above) attributes the entire combined effect of just those settings to the shares shown. This does NOT cover 1 other real difference(s) listed above (formation lag) -- they fall outside this attribution mechanism's tracked-switch vocabulary, so their own effect is neither included in nor excluded from this split; read this Shapley split as exact only among the settings it names, not as "100% of the total gap explained."

- Verdict: `reproduced`
- _No C&Z signal bridge track was run for this factor, so any residual gap above cannot be attributed between a difference in how the signal formula itself was read and a difference in data or sample -- this report cannot separate the two._

**Sensitivity/stability evidence for this replication:**

_Per-setting contribution shares are not shown below: the joint significance test does not confirm the total change is more than noise._

- **Breakpoint source**: Effect: +0.00180/month (t=1.28), not statistically significant.
- **Stock universe**: Effect: +0.00052/month (t=0.87), not statistically significant.

- Standardized HXZ protocol (a named case, not a competing replication): compared with the fully standardized HXZ protocol, our implementation's effect differs by 0.0022/month, though a joint test does not confirm this.
- Running HXZ's exact config through our engine reproduces their own published number closely (1.17x their spread, same sign, both statistically significant) -- our reimplementation of their protocol is trustworthy.
- Our own replication DOES decay after publication (in-sample t=4.12, post-publication t=0.16).
- The t-stat gap vs the standardized HXZ protocol is driven mainly by the mean-return channel, not the others -- so it is not simply an artefact of a misaligned sample window.

- Verdict: `reproduced`
- _Used as sensitivity context, not itself the reproducibility question._

**C&Z's own published result differs from the paper's own reported spread by +0.0068 per month.**

- **Portfolio-construction settings alone** [largest]: Effect: +0.0061 per month.
- **How the signal itself was computed (plus data-vintage and engine differences)**: Effect: +0.0019 per month.
- **Our own run's distance from the paper's number**: Effect: -0.0012 per month.

- This is an exact arithmetic split of the total distance, not a controlled experiment: it shows where the distance sits, not what caused it.
- C&Z's own published result is a fixed, hand-filled reference number (no underlying return series on file) -- its sensitivity to the choice of sample window cannot be checked, not because it was found to be zero.

- Verdict: `reproduced`
- _The three components are not equally clean: only the settings component holds the signal fixed on both sides. The first also absorbs data-vintage and engine differences, and the last is our own replication error rather than anything the paper left ambiguous. The four numbers being compared also do not share a common sample window or estimator._

**HXZ's own published result differs from the paper's own reported spread by -0.0044 per month.**

- **Portfolio-construction settings alone** [largest]: Effect: -0.0022 per month.
- **Our own run's distance from the paper's number**: Effect: -0.0012 per month.
- **How the signal itself was computed (plus data-vintage and engine differences)**: Effect: -0.0010 per month.

- This is an exact arithmetic split of the total distance, not a controlled experiment: it shows where the distance sits, not what caused it.
- Recomputing HXZ's own published result over its own paper's sample window instead of this paper's moves it by +0.0016 per month -- a measure of how much the choice of sample window alone matters here.

- Verdict: `reproduced`
- _The three components are not equally clean: only the settings component holds the signal fixed on both sides. The first also absorbs data-vintage and engine differences, and the last is our own replication error rather than anything the paper left ambiguous. The four numbers being compared also do not share a common sample window or estimator._

- Verdict: `reproduced`

**Compared with the paper's own reported result, our reviewed implementation of the paper's method agrees in sign with it; its magnitude is 0.89x the paper's own reported spread. By this project's magnitude bands (clean: 0.5x-2.0x; partial: 0.2x-5.0x; outside that, or opposite sign: failed), this counts as a clean reproduction by magnitude.**

- Our own replication's effect ALSO decays after the paper's own publication date (in-sample t=4.12, post-publication t=0.16) -- consistent with part of the gap from the paper being a genuinely fragile or decaying signal, not only a fixed implementation or config difference.

