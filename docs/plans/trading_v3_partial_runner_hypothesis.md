# Trading V3 research hypothesis — partial profit + adaptive runner

Status: **REJECTED ON DEVELOPMENT GATE; research only; no execution authority**.

This is a new exit-management hypothesis. It is not a threshold rescue of the rejected full-position adaptive exit and it does not change frozen `gap_pullback_v1 2.0.0`, the entry policy, March holdout state, or AUTO PAPER authority.

## Question

For the **same causal entries, fills, quantities, initial structural stops and baseline position sizes**, does banking half the position at +1R while allowing the remaining position to run under the previously frozen causal deterioration exit improve realized R more robustly than the current frozen V2 exit?

The paired entry cohort remains the already-declared delayed-base acceptance development cohort from 2025-10-01 through 2026-02-27. That entry hypothesis is rejected. It is reused only because its 35 fixed trades provide a stable cohort for an exit-only experiment. A passing exit-management result cannot revive or promote that entry hypothesis.

## Policy A — control

Frozen V2 management remains unchanged:

- initial structural stop;
- causal profit protection arms after +0.75R and raises the protected stop to +0.25R on subsequent bars;
- full-position +1.5R target;
- 60-minute maximum hold;
- deterministic end-of-day protection.

## Policy C — 50% at +1R, adaptive runner

Entry time, entry fill, filled quantity, structural stop, and baseline position size are copied exactly from policy A.

### Risk protection

- same structural stop as A;
- same causal +0.75R -> +0.25R protected stop as A;
- stop-before-target ordering remains pessimistic when a single bar can reach both;
- a triggered stop remains authoritative for all unsold quantity.

### Partial target

- offer **50% of the original position at +1.0R**;
- the partial target is a deterministic sell-limit order;
- historical execution honors the existing `paper-execution-v2` liquidity/partial-fill rules;
- if the target tranche is only partially filled, the residual limit remains eligible on later bars while price still reaches the limit;
- there is no second fixed profit target.

The 50% / +1.0R values were frozen before replay and were not swept.

### Runner / deterioration exit

The remaining open quantity is managed by the **exact previously frozen adaptive deterioration rule**:

A finalized five-minute trend break is required:

- 5m close below EMA9; and
- 5m EMA9 falling.

Then either at least two tactical 1m warnings or a strong 5m confirmation must agree.

Tactical 1m warnings:

1. 1m close below EMA9 while EMA9 is falling;
2. 1m MACD at/below signal with negative histogram;
3. 1m Stoch RSI bearish `%K < %D` cross after the prior finalized `%K` was at least 80 and `%K >= %D`.

Strong 5m confirmation:

- 5m close below EMA20 when available; or
- 5m MACD bearish and 5m Stoch RSI bearish when both are available.

`Stoch RSI > 80` alone is not an exit.

The deterioration rule is allowed to exit **all currently open quantity even before +1R is reached**. If the +1R partial has already filled, it exits only the remaining runner. Indicator decisions use finalized causal bars and execute on the next one-minute bar.

### Time exit

- no 60-minute maximum hold;
- no fixed +1.5R target on the runner;
- force-flat decision at **15:55 ET** if no earlier exit owns the remaining quantity;
- once an indicator, stop, or force-flat exit becomes active, historical partial execution may complete on later observations but no later discretionary/indicator decision may reverse it.

## Paired replay semantics

This remains an exit-only counterfactual:

- discover/select policy-A trades with the existing delayed-base evaluator and deterministic paper engine;
- preserve every A entry timestamp, fill, quantity, and initial stop;
- apply policy C only after the entry is fixed;
- do not resize or reject later C trades because C may hold an earlier position longer.

Therefore policy-C aggregate P&L is a fixed-entry paired counterfactual, not a full portfolio-capacity simulation.

## Metrics

Report A and C:

- expectancy and one-sided 90% lower confidence bound;
- win rate;
- average winner / loser;
- profit factor in R;
- maximum drawdown in R;
- P&L using exact baseline-sized entries;
- average MFE capture;
- average hold time (quantity-weighted for C);
- exit mix;
- number of trades with any +1R partial and number completing the full 50% partial.

Paired effect:

- C - A R delta per trade;
- mean / median delta;
- one-sided 90% lower confidence bound;
- C-better / same / worse counts;
- leave-one-trade-out mean-delta minimum;
- monthly mean paired effects.

## Predeclared development exit-effect gate

Policy C shows a development-stage management improvement only if **all** are true:

- at least **20 paired trades**;
- mean paired `C - A` delta **> 0R**;
- one-sided 90% LCB of paired delta **> 0R**;
- policy-C maximum drawdown **<= 5R**;
- the mean paired delta remains **> 0R after removing any one trade**;
- at least **4 calendar months** contain paired trades and at least **3 months** have positive mean `C - A`.

The leave-one-out and monthly requirements were predeclared specifically to prevent a single runner or one isolated regime from manufacturing a pass.

## Development replay result

Final replay: Actions run **`32629379039`**, artifact **`9490600054`** (`trading-v3-partial-runner-research`).

- Development period: **2025-10-01 through 2026-02-27**.
- Coverage: **103/103 sessions**.
- Same paired entries/fills/sizes: **35**.
- Provider calls: **0**.
- March loaded: **no**.
- Frozen V2 / production authority changed: **no**.

### Policy A — frozen V2 exits

- Wins / losses: **19 / 16** (54.29% win rate).
- Expectancy: **+0.11724R**.
- One-sided 90% LCB: **-0.11687R**.
- Average winner: **+0.94097R**.
- Average loser: **-0.86093R**.
- Profit factor: **1.29790**.
- Maximum drawdown: **3.51698R**.
- Average hold: **59.74 minutes**.
- Average full-session MFE capture: **16.10%**.
- Same-entry-size P&L: **+$702.08**.

### Policy C — 50% at +1R, adaptive runner

- Wins / losses: **16 / 19** (45.71% win rate).
- Expectancy: **+0.10695R**.
- One-sided 90% LCB: **-0.12801R**.
- Median trade: **-0.18025R**.
- Average winner: **+0.99245R**.
- Average loser: **-0.63874R**.
- Profit factor: **1.30844**.
- Maximum drawdown: **4.39380R**.
- Quantity-weighted average hold: **49.20 minutes**.
- Average full-session MFE capture: **13.46%**.
- Same-entry-size P&L: **+$551.05**.
- Runner exit mix: **12 stop / 21 indicator / 2 force-flat**.
- Any +1R partial fill: **12/35 trades**.
- Full 50% partial completed: **12/35 trades**.

Policy C did improve average winner slightly and reduced average loser materially, but the lower win rate offset those benefits. Expectancy and P&L both finished below policy A, while drawdown increased.

### Paired management effect

- Mean `C - A`: **-0.01029R/trade**.
- Median `C - A`: **0R**.
- One-sided 90% LCB: **-0.15936R**.
- C better / same / worse: **15 / 5 / 15**.
- Minimum leave-one-trade-out mean delta: **-0.08620R**.
- Positive months: **3/5**.
- Monthly mean deltas: **Oct -0.09859R, Nov +0.04985R, Dec +0.07453R, Jan -0.36842R, Feb +0.63568R**.

The best paired improvement was again **CRCG on 2026-02-25**, about **+2.571R**. Removing that one trade makes the already-negative mean approximately **-0.086R/trade**, so the partial-runner result is not dependent on a hidden positive edge that merely failed the confidence interval; its central paired estimate is itself slightly worse than A.

Descriptive only: among the **12 trades that actually reached the +1R partial**, mean `C - A` was about **-0.0378R**. Among the **23 trades that never reached the partial**, mean `C - A` was about **+0.0041R**. This is not a new rule and must not be used to tune the partial threshold on this sample.

As in the previous adaptive-exit experiment, all **21 indicator exits** contained the 5m trend-break + 1m EMA weakness + 1m bearish MACD combination. The Stoch-RSI warning did not become a determining exit reason in this sample.

## Decision

**Development exit-effect gate FAILED.** Components:

- paired-trade floor: pass;
- mean paired delta > 0: **fail** (`-0.01029R`);
- one-sided 90% LCB > 0: **fail** (`-0.15936R`);
- policy-C max drawdown <=5R: pass (`4.39380R`);
- leave-one-trade-out mean always >0: **fail** (minimum `-0.08620R`);
- at least 4 months represented / 3 positive: pass (`5` / `3`).

Therefore:

- **reject this exact 50%-at-1R + adaptive-runner policy on development**;
- do not sweep partial percentage, target R, EMA/MACD/Stoch periods, vote counts, or force-flat timing on this sample;
- do not open March 2026 for this rejected policy;
- do not promote the rejected delayed-base entry cohort;
- frozen `gap_pullback_v1 2.0.0` and prospective SHADOW qualification remain unchanged.

The result suggests that simple profit splitting does not solve the more fundamental instability of this entry/exit cohort. Any future management hypothesis should add genuinely different causal information or structure rather than merely choosing another partial percentage or target.

## Data boundary

- March 2026: **sealed / not loaded**.
- Provider calls during replay: **none**; immutable 103-session cache only.
- Historical reconstruction remains current-listing / Alpaca IEX partial-market evidence and therefore carries survivorship/listing bias.
- Historical catalyst/supply/float facts and authoritative halt state are not reconstructed with hindsight.
- Policy C held the same entry sizes fixed instead of recomputing portfolio capacity under altered holding periods, so its P&L is an exit-management counterfactual rather than a complete portfolio simulation.

This is research evidence, not proof of profitability.
