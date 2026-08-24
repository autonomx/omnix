# Trading V3 research hypothesis — adaptive multi-timeframe exit

Status: **REJECTED ON DEVELOPMENT GATE; research only; no execution authority**.

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

## Development replay result

Final execution-qualified replay: Actions run **`32628370002`**, artifact **`9490338143`** (`trading-v3-adaptive-exit-research`).

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
- Profit factor in R: **1.29790**.
- Maximum drawdown: **3.51698R**.
- Average hold: **59.74 minutes**.
- Average full-session MFE capture: **16.10%**.
- Same-entry-size P&L from a $100k baseline: **+$702.08**.
- Exit mix: **15 stop / 8 target / 12 time**.

### Policy B — adaptive trend exit

- Wins / losses: **15 / 20** (42.86% win rate).
- Expectancy: **+0.20050R**.
- One-sided 90% LCB: **-0.13774R**.
- Median trade: **-0.18025R**.
- Average winner: **+1.27737R**.
- Average loser: **-0.60715R**.
- Profit factor in R: **1.57791**.
- Maximum drawdown: **5.52935R**.
- Average hold: **64.94 minutes**.
- Average full-session MFE capture: **13.05%**.
- Same-entry-size P&L from a $100k baseline: **+$1,379.27**.
- Exit mix: **12 stop / 21 indicator / 2 force-flat**.

### Paired management effect

- Mean `B - A`: **+0.08326R/trade**.
- Median `B - A`: **0R**.
- One-sided 90% LCB of paired delta: **-0.16803R**.
- B better / same / worse: **16 / 5 / 14**.

The point estimate therefore improved, mainly by making winning trades larger and losing trades smaller on average, but the improvement is not statistically credible on this development sample and drawdown became worse.

### Concentration / stability diagnostic

The raw mean improvement is not robust:

- best paired improvement: **CRCG on 2026-02-25**, about **+5.717R** versus policy A, exiting through force-flat;
- removing only that best trade changes mean paired `B - A` from **+0.083R to about -0.082R**;
- monthly mean paired effects were approximately **Oct -0.116R, Nov +0.231R, Dec -0.199R, Jan -0.403R, Feb +1.288R**.

That is substantial regime/outlier concentration rather than stable improvement.

Of the **21 indicator exits**, every one included the 5m trend-break + 1m EMA weakness + 1m bearish MACD combination; only one also used the 5m-below-EMA20 strong confirmation. **Stochastic RSI did not become a contributing exit reason in this sample.** It remained part of the frozen rule but never supplied the extra warning/confirmation that determined one of these exits.

## Decision

**Development exit-effect gate FAILED.** Specifically:

- paired trade-count floor: pass;
- mean paired delta > 0: pass on the raw point estimate;
- one-sided 90% LCB of paired delta > 0: **fail** (`-0.16803R`);
- policy-B max drawdown <=5R: **fail** (`5.52935R`).

Therefore:

- **reject this exact adaptive full-position exit policy on development**;
- **do not tune EMA/MACD/Stoch-RSI periods, vote counts, force-flat timing, or deterioration thresholds on this sample**;
- **do not open March 2026 for this rejected policy**;
- do not treat the +0.20050R B expectancy as established edge, because its own LCB is negative and the paired improvement is concentrated;
- frozen `gap_pullback_v1 2.0.0` and its prospective SHADOW qualification remain unchanged.

A future exit hypothesis must be separately formulated before replay. For example, partial-profit + runner management would be a new management hypothesis rather than a rescue of this exact full-position policy.

## Holdout and data boundaries

- March 2026: **sealed / not loaded**.
- Provider calls during replay: **none**; immutable 103-session cache only.
- Historical reconstruction uses current listings and Alpaca IEX partial-market bars, so survivorship/listing bias remains.
- Historical catalyst/supply/float facts and authoritative halt state are not reconstructed with hindsight.
- Policy B held the same entry sizes fixed instead of recomputing portfolio capacity under longer holding periods, so B P&L is a paired exit-management counterfactual, not a complete portfolio simulation.

The result is research evidence, not proof of future profitability.
