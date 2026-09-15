# Replication Diagnosis: 099f6e1136bd316c

> **LLM-assisted proposal.** Wording and attribution below were drafted by an LLM; every figure is inserted by a deterministic renderer from the evidence bundle. This is a hypothesis for human review, not an automatic empirical conclusion.

- Verdict (deterministic): `sign_agrees_magnitude_differs`
- Paper: Cooper, Michael J., Huseyin Gulen, and Michael J. Schill, 2008, Asset Growth and the Cross-Section of Stock Returns, The Journal of Finance 63(4), 1609–1651.
- Generated: 2026-08-18T05:51:11.263970+00:00
- Diagnosis model: gpt-5.6-terra

## Paper vs. tracks

| Track | Comparable metric | Our value | Paper value | Delta | Sign agrees | Our t-stat | Months |
|---|---|---|---|---|---|---|---|
| standardized_hxz | alpha_ff3 | 0.00360709 | 0.007 | -0.00339291 | true | 3.60359 | 432 |
| cz_actual_config | alpha_ff3 | 0.0141695 | 0.007 | 0.00716952 | true | 7.1109 | 432 |
| factorial_universe | alpha_ff3 | 0.0151565 | 0.007 | 0.00815654 | true | 7.44967 | 432 |
| factorial_weighting | alpha_ff3 | 0.00495291 | 0.007 | -0.00204709 | true | 4.10309 | 432 |
| factorial_weighting_universe | alpha_ff3 | 0.00461518 | 0.007 | -0.00238482 | true | 4.0873 | 432 |
| factorial_breakpoint | alpha_ff3 | 0.0112639 | 0.007 | 0.00426394 | true | 6.62456 | 432 |
| factorial_breakpoint_universe | alpha_ff3 | 0.0122437 | 0.007 | 0.00524366 | true | 7.51967 | 432 |
| factorial_breakpoint_weighting | alpha_ff3 | 0.00388367 | 0.007 | -0.00311633 | true | 3.69191 | 432 |
| original_method | alpha_ff3 | 0.0147488 | 0.007 | 0.00774876 | true | 7.32254 | 432 |

## Gap decomposition

Not available — no ablation_* tracks executed, so per-switch contributions are unmeasured.

## Summary

**Compared with C&Z's independent replication of this paper, the only differences are explained by paper ambiguity or C&Z's own conventions, and none has a statistically significant effect.**

- How long after picking which stocks go in a portfolio before that portfolio actually starts trading (a safety delay so the strategy can't accidentally use information before it was realistically available): we use 0 months, C&Z uses 1 month -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: no paired-test evidence is available for this setting.
- Which stocks are allowed into consideration at all: our version excludes financial companies such as banks, insurers, and real estate firms (identified by SIC industry codes 6000-6999), C&Z's version is ordinary common stock listed on the NYSE, AMEX, or Nasdaq exchanges -- C&Z's own fixed cross-factor universe convention, applied identically to every C&Z factor regardless of what any individual paper's own universe description says -- is one of the settings C&Z always overrides with their own cross-factor house convention, regardless of what this paper's own description says -- this divergence reflects C&Z's own standardization choice, not an ambiguity in the paper or a likely implementation error. Effect: +0.00087/month (t=1.78), not statistically significant. On the standardized-HXZ comparison, this same setting's isolated effect does NOT decay after publication.

- Verdict: `sign_agrees_magnitude_differs`
- _Joint test unavailable on this line: need >=2 single-switch tracks with a loadable return series for a joint test, found 1._

**Compared with the fully standardized HXZ protocol, our implementation's effect differs by 0.0059/month, confirmed by a joint significance test (p=7.8e-05).**

- Whether bigger companies count for more in the portfolio, or every stock counts equally: accounts for 96% of the change. Effect: +0.00702/month (t=2.74), statistically significant.
- Which group of stocks is used to decide the cutoffs between portfolio groups: accounts for 31% of the change. Effect: +0.00363/month (t=4.15), statistically significant.
- Which stocks are allowed into consideration at all: accounts for -27% of the change. Effect: -0.00021/month (t=-0.52), not statistically significant.
- LLM-reviewed per-setting significance: whether bigger companies count for more in the portfolio, or every stock counts equally (significant).
- LLM-reviewed joint-significance conclusion: supported by the data.
- LLM flagged as dominant driver(s): whether bigger companies count for more in the portfolio, or every stock counts equally.

- Verdict: `sign_agrees_magnitude_differs`
- _Used as sensitivity context, not itself the reproducibility question._

- Verdict: `sign_agrees_magnitude_differs`

**Compared with the paper's own reported result, our reviewed implementation of the paper's method agrees in sign with it; its magnitude is 2.11x larger.**

- 2 setting(s) were never specified by the paper at all and were filled by an engine default: how many months we wait after a company's fiscal year ends before using its accounting data (real investors can't see the numbers the instant the year ends), what to do with a stock that's missing a required data point.
- _Part of this magnitude gap may reflect these silent defaults rather than a difference in how the paper's stated method was implemented -- this comparison cannot separate the two._

## Findings

### Per-switch analysis

#### Shapley-value gap attribution

- On the vs. HXZ standardized config line, a Shapley-attributed share of the mean-return gap is associated with the weighting switch (full-factorial evidence: the switches' Shapley effects sum exactly to the total gap, but this alone does not establish that the weighting switch's own effect is statistically distinguishable from noise). _[stage: unclassified]_
  - evidence: `shapley_attribution.to_hxz.shapley_effects.weighting` = -0.00564538
  - identification: controlled · evidence strength: high

#### Per-switch paired significance

- On the vs. HXZ standardized config line, the weighting switch's own paired effect (vs. baseline) is statistically significant.
  - evidence: `paired_tests.to_hxz.per_switch.weighting.t_stat` = 2.74168
  - identification: harmonized · evidence strength: medium

### Joint significance gate

#### Joint attribution support

- On the vs. HXZ standardized config line, the switches varied jointly explain a statistically significant share of the gap (joint Wald test).
  - evidence: `joint_test.to_hxz.p_value` = 7.83526e-05
  - identification: harmonized · evidence strength: medium

### Vs. paper

#### Sign agreement

- The original_method track's spread sign agrees with the paper's headline sign.
  - evidence: `derived.tracks.original_method.vs_paper.sign_agrees` = true
  - identification: observational · evidence strength: low

#### Magnitude gap

- The original_method track's spread magnitude is larger than the paper's headline spread.
  - evidence: `derived.tracks.original_method.vs_paper.abs_spread_ratio` = 2.10697
  - identification: observational · evidence strength: low

#### Statistical significance

- The original_method track's spread is statistically significant by the deterministic significance threshold.
  - evidence: `derived.tracks.original_method.vs_paper.track_significant` = true
  - identification: observational · evidence strength: low

#### Configuration divergence

- The standardized_hxz track's configuration differs from the baseline track. _[stage: portfolio]_
  - evidence: `config_diff.pairs.standardized_hxz.details.weighting_rule.baseline_value` = ew, `config_diff.pairs.standardized_hxz.details.weighting_rule.track_value` = vw
  - identification: observational · evidence strength: low

### Auxiliary

#### Evidence limitations

- The evidence needed to determine the requested comparison is not available.
  - evidence: `gap_decomposition.available` = false, `gap_decomposition.reason` = no ablation_* tracks executed, so per-switch contributions are unmeasured
  - identification: unidentified · evidence strength: low

#### Post-publication decay

- The original_method track's spread is significant in-sample but not statistically significant post-publication.
  - evidence: `publication_decay.tracks.original_method.decayed` = true
  - identification: observational · evidence strength: low
