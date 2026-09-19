# Evolving Top-Gainers Replay Contract

## Purpose

The live interday SHADOW system does not operate from a single immutable morning
candidate set. Finviz live leaders are polled throughout the session and dynamic
discovery maintains an evolving candidate view. Historical Leader Momentum
research must reproduce that behavior.

The frozen morning universe remains useful as a benchmark and integrity artifact,
but it is not the authoritative candidate universe for an intraday leader strategy.

## Causal order

The historical experiment must preserve this order:

1. Select/freeze the **observable population** without using end-of-day winner labels.
2. At each historical evaluation timestamp, use only prices/evidence available at
   that timestamp.
3. Recompute the Top-N gainers ranking from current price versus previous close.
4. Admit a symbol when it first enters Top-N. Symbols may later fall out and re-enter.
5. Leader Momentum may use already-observed bars as indicator history, but it may
   not signal or trade before that symbol's first Top-N discovery timestamp.
6. Only after the ranking stream is frozen/fingerprinted may EOD labels be joined.

Never append hindsight winners to the candidate universe merely because they later
finished in the daily Top-5.

## Default parity with live Omnix

For Leader Momentum research, start with:

- Top-N: 20
- ranking cadence: 5 minutes
- first ranking: 09:35 ET
- last new-entry ranking relevant to the strategy: 15:30 ET
- price range: $0.10-$250
- minimum current gain: 0%

These defaults mirror the current live `FinvizLiveLeaderSource` count and dynamic
monitor cadence closely enough for a first historical parity test. Research may
also report Top-10 and Top-5 membership, but those are diagnostics; do not choose
which threshold to trade after seeing outcome labels.

## Population authority

The hardest part of a historical reconstruction is not the ranking formula. It is
the population from which the ranking is computed.

Preferred population authority, in order:

1. actual archived/captured Finviz live-leader or discovery-source observations;
2. a historical provider snapshot that can reconstruct the same source population;
3. a broad, predeclared exchange/security universe frozen before outcome labels.

A population made from `daily Top-5 winners + hand-picked controls` is not valid
for prospective inference because a symbol cannot enter a Top-20 ranking unless
all serious competitors were eligible to outrank it.

Record the population source, fingerprint, exclusions, and any reconstruction
limitations in the run manifest.

## Ranking semantics

At each evaluation timestamp:

`gain_pct(t) = current_price(t) / previous_close - 1`

Rank eligible symbols descending by gain percentage. The research helper uses
cumulative dollar volume and then instrument id only as deterministic tie-breakers.
No close price, EOD rank, session high, or future volume may influence membership.

Halts/no-print intervals should retain the latest causally known price unless the
source itself has an explicit stale-member removal rule. A halt is a market state,
not automatically a provider-data failure.

## Strategy evaluation

Use `evaluate_leader_momentum_after_discovery(...)` from
`strategy_evolving_top_gainers.py`.

The wrapper intentionally keeps bars before discovery available for causal EMA,
ATR, VWAP, and structure history while moving `entry_start_et` to the actual first
leaderboard discovery time. It asserts that no resulting signal predates discovery.

Use context values available at or before discovery. Do not reuse a later context
snapshot. If a context field cannot be reconstructed causally, mark it unavailable
or use a predeclared benchmark assumption rather than backfilling from future data.

## Required metrics

For each eventual Top-5 winner record:

- first Top-20 timestamp;
- first Top-10 timestamp;
- first Top-5 timestamp;
- best intraday rank;
- gain percentage at first discovery;
- Leader Momentum first confirmation;
- first signal/trade;
- additional MFE available after discovery;
- strategy return and capture ratio.

For every symbol that ever enters Top-N, record the same strategy evidence whether
or not it later becomes an EOD winner.

Primary metrics should include:

- percentage of eventual winners that entered Top-20 before the last entry cutoff;
- median discovery latency relative to the symbol becoming a meaningful mover;
- `P(trade | eventual winner that entered Top-N)`;
- `P(trade | Top-N entrant that was not an eventual winner)`;
- continuation precision: probability of an additional +10%, +20%, +30%, +50%
  move after a Leader Momentum signal;
- losing-trade rate among Top-N entrants;
- P/L and expectancy with realistic friction;
- runner capture rate and percentage of remaining post-discovery move captured.

The core economic question is not whether the strategy predicts the final daily
Top-5 label. It is whether, among stocks that become live market leaders, it enters
those with substantial continuation remaining and rejects leaders whose move is
mostly exhausted.

## Research-only authority

The evolving Top-Gainers replay and all diagnostics are SHADOW/research-only and
carry no execution authority. Do not tune Leader Momentum v1.2 as part of the
first corrected replay. Freeze its file hash and parameters before the run and
verify them again afterward.
