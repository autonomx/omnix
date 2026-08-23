# Trading V3 research hypothesis — delayed-base entry quality confluence

Status: **PREDECLARED DEVELOPMENT REPLAY; research only; no execution authority**.

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

Require **at least 4 of the 5** checks to pass. These values are frozen and are not swept.

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

## Metrics

Report baseline and Policy D:

- trades, wins/losses, win rate;
- expectancy R and one-sided 90% LCB;
- max drawdown R;
- same-risk-model P&L;
- exit mix;
- median/mean MFE and MAE when available;
- quality-score distribution and rejection reasons.

Also report the delta in win rate, expectancy, trade count and drawdown versus the delayed-base baseline.

## Interpretation boundary

Because the thresholds were formulated from the same Oct-Feb losers/winners, even a large improvement is **not validation**. The replay only answers whether the frozen recommendation reproduces its intended in-sample effect when implemented causally.

A future authoritative successor would require untouched/prospective point-in-time evidence, including richer premarket structure, catalyst/supply facts, authoritative halt state and fully warmed multi-timeframe indicators. No same-sample threshold rescue is allowed after this replay.
