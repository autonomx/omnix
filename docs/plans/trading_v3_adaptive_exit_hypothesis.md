# Trading V3 research hypothesis — adaptive multi-timeframe exit

Status: **FROZEN BEFORE DEVELOPMENT REPLAY; research only; no execution authority**.

This experiment isolates exit management. It does not change frozen `gap_pullback_v1 2.0.0`, does not change entry selection, does not open the March 2026 holdout, and cannot authorize AUTO PAPER.

## Question

For the **same causal entries, fills, quantities, structural stops and position sizes**, does replacing the fixed 1.5R/60-minute exit with a multi-timeframe trend-deterioration exit improve realized R?

The paired entry cohort is the already-declared delayed-base acceptance development cohort from 2025-10-01 through 2026-02-27. That entry hypothesis was previously rejected. It is reused only because its 35 trades provide a larger fixed cohort for an exit-only paired comparison. A positive exit result cannot revive or promote the rejected entry.

## Policy A — control

Use the current frozen V2 management unchanged:

- initial structural stop;
- profit protection arms after +0.75R and raises the protected stop to +0.25R on subsequent bars;
- full-position 1.5R target;
- 60-minute maximum hold;
- end-of-day protection remains authoritative.

## Policy B — frozen adaptive runner

Entry price, fill price, filled quantity and initial structural stop are copied exactly from policy A.

Risk protection is retained:

- same initial structural stop as A;
- same causal +0.75R arm -> +0.25R protected stop as A;
- a stop always has priority over a later indicator decision.

The fixed profit/time exits are removed:

- **no fixed 1.5R take-profit**;
- **no 60-minute maximum-hold exit**;
- force-flat decision at **15:55 ET** if the adaptive exit has not fired.

There are no intentional partial-profit rules in this first experiment. Execution-model partial fills are still honored when historical bar liquidity cannot fill the entire exit order at once.

### Indicator deterioration rule

Indicators use finalized causal bars only. A signal observed on a finalized bar is executed as a market exit at the **next 1-minute bar open**. The signal bar cannot retroactively exit itself.

A one-minute warning is never enough by itself. Policy B requires a five-minute trend break first:

- 5m close is below EMA9; and
- 5m EMA9 is falling.

Once that anchor is true, exit when either **two tactical 1m warnings** agree or a **strong 5m confirmation** is present.

Tactical 1m warnings:

1. 1m close below EMA9 while EMA9 is falling;
2. 1m MACD is at/below signal with a negative histogram;
3. 1m Stochastic RSI makes a bearish `%K < %D` cross after the prior finalized 1m `%K` was at least 80 and `%K >= %D`.

Strong 5m confirmation, when causally available:

- 5m close below EMA20; or
- 5m MACD bearish **and** 5m Stochastic RSI bearish.

`Stoch RSI > 80` by itself is explicitly **not** an exit. Sustained overbought momentum is allowed to continue while the trend remains intact.

If a longer-warmup indicator is unavailable, it is not fabricated and does not count as bearish evidence. The structural/protected stop and 15:55 ET force-flat remain available regardless.

## Paired replay semantics

This is deliberately a paired trade experiment rather than a new portfolio backtest:

- discover/select the policy-A cohort with the existing delayed-base evaluator and deterministic paper engine;
- preserve every selected A entry time, entry fill, entry quantity and initial stop;
- replay only the post-entry path under B;
- do **not** resize later B positions or reject later B entries because B may hold an earlier trade longer.

That keeps the comparison focused on exit quality. It also means aggregate B P&L is a same-sized paired counterfactual, **not** a claim that the altered holding periods would satisfy the original portfolio-capacity path.

### Execution-model clarification discovered during dry-run qualification

The indicator rule, entry cohort and statistical gate above were frozen before reading development performance. Two dry-run execution issues were found while qualifying the replay harness; neither changes the indicator hypothesis:

1. Sparse historical IEX bars can have no trade exactly at 15:55. The force-flat **decision** therefore becomes irrevocable using the last finalized observation known by the cutoff rather than waiting to make a new decision on a later bar.
2. `paper-execution-v2` permits partial market fills when historical bar volume is smaller than the remaining position. A force-flat/indicator/triggered-stop order therefore remains active until its residual quantity is filled. Later bars may supply execution for that already-issued order, but they cannot cancel it or introduce a new indicator/discretionary decision.

The replay reports the volume-weighted average exit price and final fill time for multi-fill exits. This is execution realism, not a partial-profit strategy. The predeclared EMA/MACD/Stoch-RSI conditions and development gate are unchanged. The earlier dry-run artifacts are engineering diagnostics and are not treated as the scientific development result.

## Metrics

Report for A and B:

- expectancy and one-sided 90% lower confidence bound;
- win rate;
- average winner and loser;
- profit factor in R;
- maximum drawdown in R;
- average hold time;
- P&L using the exact baseline-sized entries;
- realized-R capture as a percentage of the same entry-to-15:55 full-session MFE.

Also report the paired `B - A` R delta for every trade, its mean, median and one-sided 90% lower confidence bound, plus B-better/same/worse counts.

## Predeclared development exit-effect gate

Before seeing the replay, policy B is considered to show a development-stage management improvement only if all are true:

- at least **20 paired trades**;
- mean paired `B - A` R delta **> 0**;
- one-sided 90% lower confidence bound of the paired delta **> 0R**;
- policy-B maximum drawdown **<= 5R**.

This gate measures **exit effect only**. Passing it would justify a separately declared validation experiment; it cannot promote frozen V2 or the rejected delayed-base entry. Failing it means this exact adaptive rule is rejected on development without threshold/vote-count/indicator-period rescue.

## Holdout and data boundaries

- Development range: **2025-10-01 through 2026-02-27**.
- March 2026: **sealed and must not be loaded by this run**.
- Provider calls during replay: **prohibited**; use the immutable 103-session cache only.
- Historical reconstruction uses current listings and Alpaca IEX partial-market bars, so survivorship/listing bias remains.
- Historical catalyst/supply/float facts and authoritative halt state are not reconstructed with hindsight.

The result is research evidence, not proof of future profitability.
