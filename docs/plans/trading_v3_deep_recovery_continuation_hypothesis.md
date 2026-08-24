# V3 deep-recovery continuation feasibility hypothesis

Status: **IN-SAMPLE FEASIBILITY ONLY — NO EXECUTION AUTHORITY**

This hypothesis is formulated after the frozen deep-recovery census identified a distinct family of liquid candidates that recovered >=30% by 11:30 ET but were usually missed by frozen V2's L1 -> B1 -> L2 timing geometry. It is therefore not an independent validation. The same development block may be used only to answer whether the causal implementation is mechanically/trading-economically plausible enough to justify prospective SHADOW collection.

Frozen V2 remains unchanged. March remains sealed.

## Motivation from the frozen census

The predeclared census reviewed every development candidate/day observation. The update direction is intentionally narrow:

- **retain frozen V2's hard universe/liquidity gates**;
- do **not** admit candidates merely because they later bounced;
- add a parallel continuation shape for strong V-shaped / slower-resolving recoveries that do not satisfy V2's exact L1/B1/L2 timing ownership.

## Causal feasibility rule

The evaluator sees finalized 1-minute prefixes only.

1. Apply the same frozen-V2 hard candidate gates: gap, price, premarket dollar volume, TOD RVOL, spread, catalyst/supply settings and float mode.
2. Wait until the first 15 regular-session minutes are finalized. Freeze the first attained maximum high from 09:30 through 09:44 ET as `opening_high`.
3. After that opening-high bar, maintain a causal running low. The setup is inactive until the running low is at least **5% below opening_high**.
4. The user-supplied strong-recovery threshold is not anticipated. A signal is possible only when a **finalized close is >=30% above the already-observed running low**.
5. Require the signal close to be above regular-session VWAP.
6. Require the signal close to break the **highest high of the prior three finalized 1-minute bars**. This prevents a 30% recovery reading from authorizing an entry while price is already rolling over.
7. Signal time must be between 09:45 and frozen V2's 11:30 ET last-entry cutoff.
8. The structural stop is **15 bps below the minimum low of the latest five finalized 1-minute bars including the signal bar**. This deliberately does not use the original deep trough as the stop; doing so would create an impractically wide risk distance after a 30% rebound.
9. Entry remains on the next eligible 1-minute execution bar. One trade per symbol/day and the existing deterministic portfolio/risk sizing remain authoritative.
10. For comparability, retain frozen V2 management: 1.5R target, +0.75R profit-protection trigger, protected stop +0.25R, 60-minute maximum hold and end-of-day controls.

No EMA/MACD/Stoch-RSI gate is added in this historical feasibility pass so entry-shape effects are isolated and the known historical warm-up limitation is not turned into another confound.

## Feasibility reporting

Compare the parallel deep-recovery branch with unmodified frozen V2 on the same development cache. Report:

- structural triggers and selected trades;
- symbols/session dates;
- expectancy R and one-sided 90% lower confidence bound;
- win/loss counts, max drawdown R and P&L;
- entry time, signal recovery %, selloff depth and risk distance %;
- overlap with frozen-V2 trades;
- MFE/MAE and exit reasons.

Because this hypothesis was derived after looking at the development census, **no result on this block can promote the strategy**. A positive feasibility result only permits adding this branch to prospective SHADOW evidence collection as a separately versioned research signal. AUTO PAPER remains forbidden until untouched/prospective qualification is defined and passed.

## No same-sample rescue

Do not sweep the 30% threshold, 5% selloff floor, 3-bar breakout, 5-bar stop, 09:45 opening anchor or exit parameters after seeing the result. If the feasibility rule fails, record the failure and use prospective evidence or a separately predeclared future hypothesis.
