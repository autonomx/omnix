# Prospective economic SHADOW v1

Status: **frozen prospective research contract**  
Prospective epoch: **2026-08-24 onward**  
Execution authority: **none**  
Historical sealed holdout: **2026-03-31 through 2026-04-28**

This document closes the V3-V8 historical recovery-research lineage and freezes the rules for the next evidence phase. Historical exploration scripts remain in the repository for audit/reproduction, but the one-shot PR-triggered workflows are retired so ordinary implementation commits cannot rerun old experiments or create accidental post-hoc evidence.

## Scientific conclusion from V3-V8

The recovery phenomenon is observable, but the historically tradeable subset has not shown stable temporal generalization.

- **V3** found a high-precision causal recovery classifier in Oct-Dec 2025 and initially survived Jan-Feb 2026, but the sealed March 2026 holdout falsified it: 5 trades, 1W/4L, -0.644R expectancy. The classifier itself fell to 40% eventual >=30% recovery precision in March.
- **V4** required confirmed recovery/retest/rebreak. Descriptive recovery precision improved to roughly 86-89%, but entry became too late and no variant cleared the economic development gate.
- **V5** preserved earlier entry and used recovery-headroom geometry. The 0.75R variant looked strong in development (10 trades, 80%, +0.341R) but collapsed in untouched Jan-Sep 2025 external evidence (5 trades, 40%, -0.412R). V5 is retired; neighboring thresholds are not searched.
- **V6** used only 2-3 minutes of micro-acceptance. It predicted eventual >=30% recovery at roughly 82-88% precision but traded at only roughly 36-39% wins with negative expectancy. Path diagnostics showed the label was economically exhausted by entry: 28 of 29 true recoveries had <1R remaining to the 30% threshold.
- **V7** replaced the descriptive label with the direct economic label `+1R before -1R within 60m`. The raw causal watch population was 37/70 = 52.9% wins, but deteriorated from 62.5% in 2025 H1 to 51.5% in H2 and 38.5% in 2026 Q1. A bounded one/two-predicate search produced 12 H1 candidates and **zero** that survived the predeclared H2 + Q1 stability gates.
- **V8** tested a bounded 3x3 earlier rebound/retracement grid. All nine variants failed temporal stability; none was allowed to proceed to realistic execution replay.

**Decision:** do not create V9/V10 by mining the same historical cache. The next rule changes, if any, must come from new prospective evidence rather than threshold rescue on V3-V8 outcomes.

## Immutable historical evidence ledger

Frozen V3 selector source SHA-256:

`5c98837cc96ad7c692d45b0bafff6a025f04f52599985cc6e85af734f6917607`

| Study | GitHub run | Artifact | Digest |
| --- | ---: | ---: | --- |
| V3 recovery-leg risk | 32680827139 | 9504115854 | `sha256:e94b9c6a6aacf828c9c8ad19ffe3ef82cdd7552afbee80fe08f5a9a2dc10c94c` |
| V3 March sealed holdout | 32681695579 | 9504341288 | `sha256:d4dab73d54899ab0d759bf78c0100bfa0da9e3856acf5ac1ea31ec6220a0e4dc` |
| V3 March diagnostic | 32681788652 | 9504363577 | `sha256:535ca19502e40e9568e788dfb1d5a9dbcf1ca4019ff2dd1e3ecb4b2f66b58a10` |
| V4 confirmed recovery | 32683941105 | 9505077902 | `sha256:25e4660880bf5b06d4e534e5bf4a9507e537b318156e8001b0558c603489621d` |
| V5 recovery headroom development | 32684400816 | 9505250788 | `sha256:83de58fed356b60ab030819a31922b2c4fef12f765b387d82b123a001dbcb6a7` |
| V5 repaired independent validation | 32685787401 | 9505613713 | `sha256:febc51f91b058dcb06d8b8e0b2d903349b4347f63c1e58e71f196701d7446b01` |
| V5 expanded backward validation | 32685922430 | 9505989927 | `sha256:a1fe46e7197d55444e64d49dea45b1d2c5000669b3cfce41d9696e45c993cca0` |
| V6 micro-acceptance | 32687151132 | 9506244689 | `sha256:c4d819bb5e153861fca6976a1007f3090dd88a3458ddcf1e6488978328c30981` |
| V6 path diagnostic | 32687978885 | 9506335347 | `sha256:288f6f572d631bf956fa5a1f63e22133e7b17fd007e94018a29bb87570870d41` |
| V7 economic-label census | 32688214491 | 9506426345 | `sha256:bf4d21cf5df3ad806713fa557a8a31c07b92b8b8412eb8f0b85e71561640ca98` |
| V7 bounded economic precision search | 32688553510 | 9506527935 | `sha256:0e393572e50095a82c9211baebecbddfe523ffc7fba80d29ed18d4b0c14d5447` |
| V8 earlier economic geometry | 32688855478 | 9506664781 | `sha256:1a0bc073f9547ff33c621a54704275ff9254b2a8ec3b54feb9ae4e6ff7e4e11b` |

The March 31-April 28, 2026 block was **not opened** by V4, V5, V6, V7 or V8. It remains an untouched sealed historical confirmation block for a future prospectively frozen profile.

## Frozen prospective profile

Policy version: `prospective-economic-shadow-v1`.

The profile fingerprint includes:

- this policy version and prospective start date;
- the existing isolated deep-recovery SHADOW setup/rule version used as the prospective source stream;
- the exact frozen V2 profile fingerprint;
- the economic first-passage label and 1-minute resolution semantics;
- the end-to-end evidence-completion definition below;
- all collection, one-shot evaluation, holdout and soak thresholds below.

Changing any of these creates a **new profile**. Evidence from different fingerprints must not be pooled for promotion.

### Unbiased candidate diagnostics

The recorder mirrors every causal `deep_recovery_state` transition for the exact frozen source/profile into a `prospective_economic_candidate` event. This preserves the full watch/reject/advance population needed for future winner/loser and regime analysis rather than retaining only good-looking signals.

Candidate diagnostic events preserve the source event ID, setup/rule/profile, source state/reason, full causal evaluation payload, universe identity/source and finalized-bar count. They are always marked:

- `diagnostic_only=true`;
- `promotion_metric_eligible=false`;
- `execution_authority=false`.

They **never** count toward matched outcomes, win rate, expectancy, confidence bounds, drawdown, sample-size gates or the economic evidence fingerprint. A regression test verifies that inserting candidate diagnostics leaves promotion metrics and the evidence fingerprint unchanged.

### Signal and outcome capture

For every eligible prospective SHADOW signal, persist immutable decision-time evidence:

- source event/setup/rule IDs and fingerprints;
- signal/session timestamp;
- actual IEX execution eligibility and quote/book evidence;
- executable long entry price (`ask`, falling back to `last` only when needed by captured evidence);
- structural stop already known at the source signal;
- risk per share and +0.5R / +0.75R / +1R levels;
- prospective signal features available at decision time;
- `execution_authority=false`.

Outcome resolution uses the first **60 full finalized 1-minute bars whose start time is at or after the signal timestamp**. A bar that began before the signal is excluded. Within one bar, if stop and target are both touched, the stop wins pessimistically.

Persist:

- first passage for +0.5R, +0.75R and +1R versus -1R;
- primary boolean label `+1R before -1R`;
- 15/30/60-full-bar R marks;
- 60-bar result: +1R if target first, -1R if stop first, otherwise the 60-bar close mark clipped to [-1R,+1R];
- MFE and MAE in R;
- explicit incomplete/unmatched evidence rather than silently dropping it.

Event storage is append-only. The recorder has no paper repository, order request, broker adapter or order-placement call.

### End-to-end evidence completion

The API field retained for compatibility as `execution_match_rate` is frozen to mean:

`completed matched economic outcomes / all frozen prospective signals`

This is deliberately stricter than quote/execution eligibility. Execution-ineligible signals, data-incomplete outcomes and signals whose 60-bar outcome is still pending all remain in the denominator until they have a complete matched economic outcome. They cannot be censored out to make win rate, expectancy or confidence bounds appear cleaner than the signal stream actually was.

## Stage 1 — collect prospective evidence

Before a one-shot evaluation may be recorded, require at least:

- **30 matched completed outcomes**;
- **20 distinct sessions**;
- **15 distinct symbols**.

The quantitative gate then requires:

- end-to-end evidence completion >= **90%**;
- `+1R before -1R` win rate >= **65%**;
- mean 60-bar result >= **+0.20R**;
- one-sided 90% expectancy lower confidence bound **> 0R**;
- max drawdown <= **5R**.

These thresholds and the evidence-completion denominator are frozen before prospective results accumulate.

## Stage 2 — evaluate exactly once

Once the minimum sample exists, the operator may record exactly one evaluation event for the profile.

- The event freezes the current evidence fingerprint, metrics, thresholds and PASS/FAIL.
- A **FAIL retires the profile**. Later winning observations cannot rescue it.
- Later observations after a PASS are not used to rewrite the evaluation; they become subsequent soak evidence.

No endpoint or UI action can open the sealed historical holdout before this recorded PASS.

## Stage 3 — sealed historical holdout

Only a prospective one-shot PASS unlocks the ability to record results for the untouched **2026-03-31 through 2026-04-28** block. Run exactly the frozen profile; no parameter search or fallback is permitted.

Verdicts:

- `<5` trades: **UNDERPOWERED**
- **GOLD**: >=5 trades, >=75% wins, >=+0.20R expectancy, <=3R drawdown
- **ROBUST**: >=5 trades, >=60% wins, >0R expectancy, <=5R drawdown
- otherwise **FAIL**

Only GOLD or ROBUST may continue. Any recorded holdout review is one-shot: `FAIL` and `UNDERPOWERED` are terminal for that profile and cannot be replaced by a second result. The review event records the artifact/run reference and the operator's confirmation that the block was not opened before the prospective PASS.

## Stage 4 — fresh SHADOW soak

After a successful holdout review, collect **new** prospective evidence. Only events observed after that holdout review count toward soak.

Minimum soak:

- >=10 matched completed outcomes;
- >=8 distinct sessions;
- >=8 distinct symbols;
- end-to-end evidence completion >=90%;
- win rate >=55%;
- expectancy >0R;
- max drawdown <=5R.

The soak remains orderless and `execution_authority=false`.

## Stage 5 — economic research review and final V2 AUTO PAPER review

After soak passes, the operator may approve the exact economic pipeline fingerprint. That approval is a prerequisite for V2 qualification, **not a replacement for V2's own exact evidence review**.

AUTO PAPER therefore requires both:

1. an approved `prospective-economic-shadow-v1` pipeline bound to the frozen V2 profile; and
2. the existing V2 prospective execution qualification (matched trades/sessions/symbols, execution match, expectancy, positive LCB and drawdown) plus its explicit review bound to the current V2 evidence fingerprint.

If later V2 replay/execution evidence changes the V2 evidence fingerprint, the V2 review must be performed again even though the economic research chain remains approved.

No historical research, LLM output, dashboard action or economic recorder event can directly create a paper order.

## Anti-overfit rules

1. Do not change thresholds after seeing prospective results for this fingerprint.
2. Do not repeat the one-shot evaluation for a failed fingerprint.
3. Do not open the sealed holdout before a recorded prospective PASS.
4. Do not search multiple holdout variants or rescue a failed/underpowered holdout.
5. Do not count pre-review observations toward the post-holdout soak.
6. Do not pool events from different profile fingerprints.
7. Do not reinterpret incomplete market/execution evidence as a loss, win or no-trade without an explicit recorded state.
8. Do not censor incomplete, ineligible or pending signal outcomes from the end-to-end evidence-completion denominator.
9. Do not allow candidate diagnostics to enter promotion metrics or evidence fingerprints.
10. Do not allow any research component, LLM or UI to become execution authority.
