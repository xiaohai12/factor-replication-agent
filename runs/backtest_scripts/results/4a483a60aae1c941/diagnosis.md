# Replication Diagnosis: 4a483a60aae1c941

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `reproduced`
- Paper: Lakonishok, Josef, Andrei Shleifer, and Robert W. Vishny (1993), NBER Working Paper No. 4360.
- Generated: 2026-08-24T18:12:59.243342+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | mean_return | 0.00249521 | 0.00383333 | -0.00133812 | true | 1.32687 | 276 |
| cz_actual_config | mean_return | 0.00383313 | 0.00383333 | -2.08288e-07 | true | 2.83471 | 276 |
| factorial_universe | mean_return | 0.00372166 | 0.00383333 | -0.000111674 | true | 2.30459 | 276 |
| factorial_weighting | mean_return | 0.00442189 | 0.00383333 | 0.000588557 | true | 2.44218 | 276 |
| factorial_weighting_universe | mean_return | 0.00411287 | 0.00383333 | 0.000279535 | true | 2.14175 | 276 |
| factorial_breakpoint | mean_return | 0.00461903 | 0.00383333 | 0.000785699 | true | 3.0102 | 276 |
| factorial_breakpoint_universe | mean_return | 0.00334908 | 0.00383333 | -0.000484252 | true | 2.17381 | 276 |
| factorial_breakpoint_weighting | mean_return | 0.00341519 | 0.00383333 | -0.000418142 | true | 1.85251 | 276 |
| cz_factorial_quantiles | mean_return | 0.00347068 | 0.00383333 | -0.000362656 | true | 2.57786 | 276 |
| cz_factorial_universe | mean_return | 0.00481534 | 0.00383333 | 0.000982002 | true | 3.00679 | 276 |
| original_method | mean_return | 0.00479915 | 0.00383333 | 0.000965812 | true | 3.00104 | 276 |

## Gap decomposition

Not available — no ablation_* tracks executed, so per-switch contributions are unmeasured.

## Summary

> C&Z's and HXZ's own published results for this factor DISAGREE with each other -- this is independent of anything our engine ran.

**Compared with C&Z's independent replication of this paper, at least one difference is NOT explained by paper ambiguity or a catalogued C&Z convention -- this warrants human review rather than being written off as expected variation.**

_Rows tagged "C&Z convention" are overridden by C&Z the same way for every factor, regardless of what this paper itself says -- not paper ambiguity, and not a likely implementation error._

- **Number of portfolio groups** [C&Z convention]: ours = 10 groups (deciles), theirs = 5 groups (quintiles). Effect: +0.00133/month (t=2.02), statistically significant.
- **Stock universe** [C&Z convention]: ours = the paper describes it as: "NYSE and AMEX stocks with five years of past data available before inclusion.", theirs = ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says. Effect: -0.00002/month (t=-0.34), not statistically significant.
- **Formation lag** [C&Z convention]: ours = 0 months, theirs = 1 month. Effect: no paired-test evidence is available for this setting.
- **Formation month** [unresolved]: ours = 4, theirs = 6. Effect: no paired-test evidence is available for this setting. Not explained by paper ambiguity or a catalogued C&Z convention -- an open question warranting human review.

- Our spread: +0.00480/month (t=3.00). C&Z's: +0.00383/month (t=2.83). Total difference: +0.00097/month.
- The catalogued setting(s) below have a combined isolated effect of +0.00131/month (136% of the total). The remaining -0.00035/month (-36%) is not produced by any of them -- one-at-a-time from a single baseline: contributions need not be additive, may depend on switch order, and do not identify interactions.
- Running C&Z's exact config through our engine reproduces their own published number closely (0.70x their spread, same sign, both statistically significant) -- our reimplementation of their protocol is trustworthy.
- For the setting(s) a full-factorial design covers (number of portfolio groups +0.00116/month; stock universe -0.00019/month), a Shapley decomposition (exact, averaged over introduction order -- unlike the one-at-a-time figures above) attributes the entire combined effect of just those settings to the shares shown. This does NOT cover 2 other real difference(s) listed above (formation lag, formation month) -- they fall outside this attribution mechanism's tracked-switch vocabulary, so their own effect is neither included in nor excluded from this split; read this Shapley split as exact only among the settings it names, not as "100% of the total gap explained."

- Verdict: `reproduced`
- _No C&Z signal bridge track was run for this factor, so any residual gap above cannot be attributed between a difference in how the signal formula itself was read and a difference in data or sample -- this report cannot separate the two._

**Sensitivity/stability evidence for this replication:**

_Per-setting contribution shares are not shown below: the joint significance test does not confirm the total change is more than noise._

- **Stock universe**: Effect: +0.00108/month (t=1.82), not statistically significant.
- **Breakpoint source**: Effect: +0.00018/month (t=0.58), not statistically significant.
- **Portfolio weighting**: Effect: +0.00038/month (t=0.31), not statistically significant.

- Standardized HXZ protocol (a named case, not a competing replication): compared with the fully standardized HXZ protocol, our implementation's effect differs by 0.0023/month, though a joint test does not confirm this.
- Running HXZ's exact config through our engine lands on a different result from what they themselves report (1.31x their spread), but neither number is statistically significant, so this comparison cannot confirm or rule out a faithful reimplementation.
- Our own replication does NOT decay after publication (in-sample t=3.00, post-publication t=2.53).
- The t-stat gap vs the standardized HXZ protocol is driven mainly by the mean-return channel, not the others -- so it is not simply an artefact of a misaligned sample window.

- Verdict: `reproduced`
- _Used as sensitivity context, not itself the reproducibility question._

**C&Z's own published result differs from the paper's own reported spread by +0.0017 per month.**

- **How the signal itself was computed (plus data-vintage and engine differences)** [largest]: Effect: +0.0017 per month.
- **Portfolio-construction settings alone**: Effect: -0.0010 per month.
- **Our own run's distance from the paper's number**: Effect: +0.0010 per month.

- This is an exact arithmetic split of the total distance, not a controlled experiment: it shows where the distance sits, not what caused it.
- C&Z's own published result is a fixed, hand-filled reference number (no underlying return series on file) -- its sensitivity to the choice of sample window cannot be checked, not because it was found to be zero.

- Verdict: `reproduced`
- _The three components are not equally clean: only the settings component holds the signal fixed on both sides. The first also absorbs data-vintage and engine differences, and the last is our own replication error rather than anything the paper left ambiguous. The four numbers being compared also do not share a common sample window or estimator._

**HXZ's own published result differs from the paper's own reported spread by -0.0057 per month.**

- **How the signal itself was computed (plus data-vintage and engine differences)** [largest]: Effect: -0.0044 per month.
- **Portfolio-construction settings alone**: Effect: -0.0023 per month.
- **Our own run's distance from the paper's number**: Effect: +0.0010 per month.

- This is an exact arithmetic split of the total distance, not a controlled experiment: it shows where the distance sits, not what caused it.
- HXZ's own published result is a fixed, hand-filled reference number (no underlying return series on file) -- its sensitivity to the choice of sample window cannot be checked, not because it was found to be zero.

- Verdict: `reproduced`
- _The three components are not equally clean: only the settings component holds the signal fixed on both sides. The first also absorbs data-vintage and engine differences, and the last is our own replication error rather than anything the paper left ambiguous. The four numbers being compared also do not share a common sample window or estimator._

- Verdict: `reproduced`

**Compared with the paper's own reported result, our reviewed implementation of the paper's method agrees in sign with it; its magnitude is 1.25x larger. By this project's magnitude bands (clean: 0.5x-2.0x; partial: 0.2x-5.0x; outside that, or opposite sign: failed), this counts as a clean reproduction by magnitude.**

- Our own replication's effect does NOT decay after the paper's own publication date (in-sample t=3.00, post-publication t=2.53) -- the gap from the paper's own number does not look like a short-lived, sample-period-specific artifact.
- 2 setting(s) were never specified by the paper at all and were filled by an engine default: accounting lag, missing-data policy.

- _Part of this magnitude gap may reflect these silent defaults rather than a difference in how the paper's stated method was implemented -- this comparison cannot separate the two._
