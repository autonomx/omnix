# Trading V3 research hypothesis — partial profit + adaptive runner

Status: **FROZEN BEFORE DEVELOPMENT REPLAY; research only; no execution authority**.

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

The 50% / +1.0R values are frozen before replay. They will not be swept on this development sample.

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

The deterioration rule is allowed to exit **all currently open quantity even before +1R is reached**. If the +1R partial has already filled, it exits only the remaining runner. This avoids forcing a weakening trade to wait for the profit target merely to qualify as a runner.

Indicator decisions use finalized causal bars and execute on the next one-minute bar. No same-bar retrospective execution is allowed.

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

The leave-one-out and monthly requirements are predeclared specifically to prevent a single runner or one isolated regime from manufacturing a pass.

Passing this gate would justify a **separately frozen validation experiment only**. It cannot authorize production, change frozen V2, revive the rejected entry cohort, or automatically open March.

Failing the gate rejects this exact 50%-at-1R + adaptive-runner policy on development. Do not rescue it by sweeping partial percentage, target R, EMA/MACD/Stoch periods, vote counts, or force-flat timing on the same sample.

## Data boundary

- Development: **2025-10-01 through 2026-02-27**.
- March 2026: **sealed / must not be loaded by this replay**.
- Provider calls: **prohibited**; immutable 103-session cache only.
- Historical reconstruction remains current-listing / Alpaca IEX partial-market evidence and therefore carries survivorship/listing bias.
- Historical catalyst/supply/float facts and authoritative halt state are not reconstructed with hindsight.

This is research evidence, not proof of profitability.
