# Trading V3 research hypothesis — delayed-base entry quality confluence

Status: **REJECTED ON DEVELOPMENT REPLAY; research only; no execution authority**.

This hypothesis was frozen before the first replay. It does not modify frozen `gap_pullback_v1 2.0.0`, prospective SHADOW qualification, AUTO PAPER authority, or the sealed March 2026 holdout.

## Question

Can the low win rate of the rejected delayed-base cohort be improved by rejecting weak/chased breakouts using causal entry-quality information, while keeping the same delayed-base structure and frozen V2 trade management?

The thresholds below were derived from descriptive review of the existing Oct-Feb development cohort. Therefore a replay on that same block is **in-sample hypothesis checking only**, not independent validation. No result from this replay may promote a strategy or justify opening March.

## Structural prerequisite

A candidate must first satisfy the already-declared delayed-base setup:

- observe the 09:30-10:00 opening range;
- use a prior 15-minute post-10:00 base;
- base range must remain narrower than the opening range;
- current finalized 1m close must be above regular-session VWAP;
- current finalized 1m close must break the prior 15-minute base high;
- current 1m volume must exceed the prior 15-minute base mean volume;
- entries remain bounded by the existing frozen V2 entry window;
- stop remains 15 bps below the base low;
- execution remains the next eligible 1m bar under `paper-execution-v2`.

## Policy D — quality confluence + 5m trend

After the delayed-base structural prerequisite is satisfied, calculate five causal quality checks at that exact finalized signal bar:

1. **Gap strength:** point-in-time gap >= **30%**.
2. **Base compression:** prior 15-minute base range <= **8%**.
3. **Breakout participation:** signal-bar volume / prior 15-minute base mean volume >= **2.0x**.
4. **Anti-chase candle:** signal-bar close/open body gain <= **3%**. Red/flat bodies pass this upper-bound check only if the delayed-base breakout prerequisite itself remains valid.
5. **VWAP extension:** signal close is no more than **5% above** regular-session VWAP.

Require **at least 4 of the 5** checks to pass. These values were frozen and were not swept.

A separate finalized 5m trend prerequisite is mandatory:

- 5m EMA9 must be causally warmed;
- finalized 5m close > EMA9;
- EMA9 must be rising versus the previous finalized 5m bar.

The 5m bar is built only from complete finalized 1m bars. Partial 5m buckets are invisible. EMA20/MACD/Stoch-RSI are not mandatory in this historical experiment because the old regular-session-only cache cannot warm them consistently early enough; prospective SHADOW continues to record those richer indicators for future independent research.

If the first structural signal fails Policy D, the candidate is not permanently blacklisted. A later finalized minute may qualify only if it independently satisfies the full delayed-base structure plus Policy D at that later decision time.

## Management held constant

To isolate entry selection, accepted trades use unchanged frozen V2 management:

- structural stop;
- +0.75R profit-protection trigger;
- protected stop at +0.25R on subsequent observations;
- full target at +1.5R;
- 60-minute max hold;
- deterministic 15:55 ET force-flat boundary.

No adaptive-exit or partial-runner policy is mixed into this test.

## Development block

Replay only the immutable causal cache covering **2025-10-01 through 2026-02-27**.

- provider calls: prohibited;
- March 2026: prohibited / sealed;
- compare against the unchanged delayed-base baseline on the same cache;
- report coverage and exact dataset fingerprints.

## Replay result

One-shot Actions run: **`32663139084`**. Artifact: **`9499276127`** (`trading-v3-entry-quality-confluence`).

Coverage and safety:

- period: **2025-10-01 through 2026-02-27**;
- coverage: **103/103 sessions**;
- provider calls: **0**;
- March loaded: **no**;
- frozen V2 changed: **no**;
- production/AUTO PAPER authority changed: **no**.

### Baseline delayed-base

- trades: **35** (**19W / 16L**);
- win rate: **54.29%**;
- expectancy: **+0.11724R**;
- one-sided 90% LCB: **-0.11687R**;
- max drawdown: **3.51698R**;
- P&L: **+$702.08**;
- exit mix: **15 stop / 8 target / 12 time**.

### Policy D

- trades: **13** (**7W / 6L**);
- win rate: **53.85%**;
- expectancy: **+0.08070R**;
- one-sided 90% LCB: **-0.29502R**;
- max drawdown: **3.88400R**;
- P&L: **+$350.28**;
- exit mix: **6 stop / 3 target / 4 time**.

### Policy D minus baseline

- trades: **-22**;
- win rate: **-0.44 percentage points**;
- expectancy: **-0.03654R/trade**;
- max drawdown: **+0.36702R**;
- P&L: **-$351.79**.

The causal implementation therefore **did not reproduce** the descriptive same-sample 4-of-5 filter's apparent win-rate improvement. It reduced trade count sharply without improving the win rate and worsened expectancy, uncertainty, drawdown and P&L.

### Signal diagnostics

Across the causal replay there were **103 delayed-base structural signal evaluations** before Policy D:

- Policy D pass evaluations: **26**;
- Policy D fail evaluations: **77**;
- 5m EMA9 unwarmed: **43** evaluations;
- 5m EMA9 not rising: **9**;
- 5m price below EMA9: **9**;
- quality-confluence score below 4/5: **56**.

Individual failed quality checks across structural signal evaluations:

- VWAP extension >5%: **44**;
- breakout volume <2x: **38**;
- gap <30%: **35**;
- base range >8%: **35**;
- breakout candle body >3%: **22**.

The historical IEX cache is sparse enough that many otherwise-valid structural decisions do not contain nine complete finalized 5m buckets, so the mandatory 5m EMA9 trend prerequisite materially reduces historical coverage. That is a data-fidelity limitation, but it is not a reason to remove or relax the predeclared requirement after seeing the result.

## Decision

**Reject this exact Policy D on the development replay.**

Do not rescue the same-sample result by:

- dropping the 5m trend prerequisite;
- changing the 4-of-5 vote;
- moving the gap/base/volume/body/VWAP thresholds;
- substituting a different EMA period;
- opening March 2026.

The discrepancy between the descriptive post-filter and the causal strategy replay is itself useful evidence: outcome-filtered trade tables can materially overstate an entry filter when they do not reproduce the actual minute-by-minute decision process, later qualifying opportunities, sparse-bar warm-up, execution and portfolio arbitration.

## Interpretation boundary

This replay was already in-sample because the thresholds were formulated from the same Oct-Feb losers/winners. Its negative causal result is therefore sufficient to stop this exact hypothesis, but a positive result would not have been independent validation.

The next authoritative successor should rely on untouched/prospective point-in-time evidence rather than another same-sample threshold combination. Prospective SHADOW should continue collecting premarket structure, catalyst/supply facts, authoritative halt state, NBBO/spread context when available, and fully warmed 1m/5m indicators at the exact decision time.
