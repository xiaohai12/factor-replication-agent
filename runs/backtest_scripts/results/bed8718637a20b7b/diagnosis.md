# Replication Diagnosis: bed8718637a20b7b

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `not_reproduced`
- Paper: Novy-Marx, R. (2013). The other side of value: The gross profitability premium. Journal of Financial Economics, 108, 1–28.
- Generated: 2026-08-19T16:55:02.692447+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | mean_return | 0.00189358 | 0.31 | -0.308106 | true | 1.32151 | 576 |
| cz_actual_config | mean_return | 0.0027592 | 0.31 | -0.307241 | true | 1.72465 | 576 |
| cz_factorial_universe | mean_return | 0.00246357 | 0.31 | -0.307536 | true | 1.69561 | 576 |
| cz_factorial_breakpoint | mean_return | 0.00305571 | 0.31 | -0.306944 | true | 1.91327 | 576 |
| original_method | mean_return | 0.00249515 | 0.31 | -0.307505 | true | 1.69922 | 576 |

## Gap decomposition

Not available — no ablation_* tracks executed, so per-switch contributions are unmeasured.

## Summary

**Compared with C&Z's independent replication of this paper, the only differences are explained by paper ambiguity or C&Z's own conventions, and none has a statistically significant effect.**

- Our spread: +0.00250/month (t=1.70). C&Z's: +0.00276/month (t=1.72). Total difference: -0.00026/month.
- The catalogued setting(s) below have a combined isolated effect of -0.00053/month (200% of the total). The remaining +0.00026/month (-100%) is not produced by any of them -- one-at-a-time from a single baseline: contributions need not be additive, may depend on switch order, and do not identify interactions.
- Breakpoint source: we use NYSE-only breakpoints, C&Z uses all-exchange breakpoints -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: -0.00056/month (t=-1.41), not statistically significant.
- Stock universe: the paper describes its universe as: "US stocks excluding financial firms.", C&Z's version is ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: +0.00003/month (t=0.65), not statistically significant.
- Formation lag: we use 0 months, C&Z uses 1 month -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: no paired-test evidence is available for this setting.

- Verdict: `not_reproduced`
- _No C&Z signal bridge track was run for this factor, so any residual gap above cannot be attributed between a difference in how the signal formula itself was read and a difference in data or sample -- this report cannot separate the two._

**Sensitivity/stability evidence for this replication:**

- Standardized HXZ protocol (a named case, not a competing replication): compared with the fully standardized HXZ protocol, our implementation's effect differs by 0.0006/month.
- Stock universe: contribution share not shown (the total change is not statistically confirmed). Effect: +0.00060/month (t=0.31), not statistically significant.
- Post-publication decay is not identifiable here: our own replication was already not statistically significant in-sample.
- The t-stat gap vs the standardized HXZ protocol is driven mainly by the mean-return channel, not the others -- so it is not simply an artefact of a misaligned sample window.

- Verdict: `not_reproduced`
- _Used as sensitivity context, not itself the reproducibility question. Joint test unavailable: need >=2 single-switch tracks with a loadable return series for a joint test, found 1._

- Verdict: `not_reproduced`

**Compared with the paper's own reported result, our reviewed implementation of the paper's method agrees in sign with it; its magnitude is 0.01x the paper's own reported spread.**

- 2 setting(s) were never specified by the paper at all and were filled by an engine default: accounting lag, missing-data policy.
- _Part of this magnitude gap may reflect these silent defaults rather than a difference in how the paper's stated method was implemented -- this comparison cannot separate the two._
