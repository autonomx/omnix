# Finviz Intraday Learning Loop

## Purpose

The intraday learning loop turns each U.S. trading session into a prospective,
causal experiment without giving research scores order authority.

The loop has two distinct jobs:

1. **Freeze the morning population** from Finviz Top Gainers before the regular
   session.
2. **Re-evaluate that same frozen population from finalized one-minute bars**
   throughout the day so Omnix can learn how the morning prior changes once the
   tape supplies evidence.

The loop is intentionally separate from deterministic execution authorization.
An `intraday_learning` event can rank a candidate highly and still cannot place
an order. AUTO PAPER remains governed by the versioned strategy state machine,
server risk, and execution-eligible Alpaca IEX evidence.

## Discovery boundary

Primary research discovery source:

`https://finviz.com/screener?v=340&s=ta_topgainers`

Finviz contributes only the ordered symbol cohort. Omnix does not use a Finviz
quote as execution evidence.

For each discovered symbol, Omnix independently enriches the point-in-time
candidate with Yahoo chart/search evidence:

- current premarket/reference price;
- normalized previous close;
- premarket volume;
- cumulative time-of-day RVOL;
- market cap/float when Yahoo exposes them;
- bid/ask-derived research spread when available.

The frozen universe persists:

- `discovery_source = finviz`;
- the Finviz source locator;
- the exact ordered source symbol list;
- the filtered/enriched candidates and their original Finviz discovery ranks;
- observation timestamps;
- an immutable fingerprint covering the captured provenance.

The raw source cohort remains preserved even when an individual Finviz symbol
cannot be enriched sufficiently to become a strategy candidate.

## Morning archive

`GapPullbackConfig.universe_discovery_source` is now:

- `yahoo` — legacy behavior;
- `finviz` — Finviz Top Gainers cohort plus Yahoo enrichment.

At the configured `universe_scan_time_et` (09:20 ET by the Finviz learning
preset), `strategy_universe_archiver` freezes exactly one evidence-only
archive.

The archive:

- does not mutate `active_universe_id`;
- does not authorize a trade;
- is not reconstructed later from an end-of-day screener;
- remains available for prospective research, replay and SHADOW evaluation.

## Intraday cadence

The existing deterministic strategy monitor remains the runtime owner. When
`intraday_learning_enabled=true`, every newly finalized one-minute bar can
produce a research-only learning snapshot for every candidate in the frozen
universe.

The monitor fetches enough one-minute history to preserve the full regular
session rather than evaluating only a rolling first-hour fragment.

The learning layer consumes the same causal prefix available at that point in
time. It cannot see future bars.

## Independent dimensions

The learning snapshot does not collapse the market into a single bullish score.
It records separate 0–10 dimensions:

- catalyst quality;
- supply/dilution risk;
- float/market-structure risk;
- premarket extension risk;
- squeeze probability;
- failed-selloff probability;
- trend-continuation probability;
- gap-retention probability;
- execution-quality proxy.

It also records a derived `opportunity_score` only for research ranking. The
component scores remain first-class evidence.

The current deterministic feature model deliberately keeps catalyst/supply
scores conservative when evidence is missing. Absence of a dilution flag is
not treated as proof of clean supply.

## Tape evidence

Each snapshot stores causal tape observations including:

- current price;
- regular-session open/high/low;
- regular-session VWAP;
- close location inside the observed range;
- remaining gap relative to the frozen premarket gap;
- current price versus the frozen premarket reference;
- session return;
- regular-session turnover relative to float when float is known;
- the simultaneous deterministic strategy state/reason.

These features implement the lessons from the first manual journal days:

- huge volume alone is neither bullish nor bearish;
- huge turnover plus sustained price acceptance can identify squeeze momentum;
- huge turnover plus weak retention can identify distribution;
- extreme premarket extension is a prior/risk dimension, not an automatic veto;
- low effective float predicts variance more reliably than direction;
- gap retention is different from trend continuation;
- a failed-selloff watch is different from a verified deterministic entry.

## Pattern labels

The research layer can classify the current causal prefix as:

- `unresolved`;
- `trend_continuation`;
- `gap_hold`;
- `opening_fade_recovery`;
- `failed_selloff_watch`;
- `squeeze_momentum`;
- `distribution_fade`;
- `high_variance`.

These labels are descriptive research states. They are not strategy signals.

## LLM intraday analyst

When `intraday_llm_enabled=true`, Omnix adds a second, explicitly
non-authoritative interpretation layer on top of the deterministic learning
snapshot.

The LLM does not receive raw broker authority or permission to trade. It receives
only structured causal evidence that Omnix has already observed:

- frozen morning gap/price/volume/float/supply/catalyst facts;
- deterministic strategy state, reason code, transitions and features;
- the current deterministic intraday-learning snapshot;
- the current live research rank;
- the previous LLM assessment for that same instrument, when one exists.

The runtime uses the application's configured **default LLM provider/model**.
This means LM Studio, ChatGPT Codex, OpenRouter, Cerebras, llama.cpp, or another
configured provider can supply the interpretation without creating a
trading-specific provider configuration.

To avoid calling the model for every stock on every bar, Omnix uses an
**event-driven bounded batch**:

- deterministic learning still evaluates every candidate on every finalized
  one-minute prefix;
- the default LLM cohort is reduced to the top **5** research candidates;
- a candidate can be pulled into the LLM batch immediately when material
  evidence changes, including a deterministic state transition, VWAP-side
  change, turnover crossing 1×/2×/5× float, a material score/rank improvement,
  a new high-opportunity regime, or `entry_ready`;
- any deterministic `entry_ready` candidate is included even when it falls
  outside the top-N research rank;
- quiet top-ranked names receive a heartbeat every
  `intraday_llm_interval_minutes` (**10 minutes by default**) during the
  configured entry window;
- outside the entry window, deterministic learning continues every minute but
  quiet heartbeat calls stop; material changes can still trigger LLM analysis;
- ordinary event batches use a short two-minute debounce so several adjacent
  one-minute changes collapse into one model call, while a new `entry_ready`
  transition can bypass that debounce.

Each model assessment returns:

- current market regime;
- squeeze probability;
- failed-selloff probability;
- trend-continuation probability;
- distribution probability;
- confidence;
- whether the thesis strengthened, weakened, flipped or stayed unchanged;
- concise bull case;
- concise bear case;
- explicit evidence that would change the model's mind.

The prompt forbids execution instructions. The schema hard-codes
`execution_authority=false`. Unknown symbols, malformed JSON, missing requested
assessments, unavailable providers and provider errors all fail open for trading:
Omnix logs the research error and continues using the deterministic strategy
only.

The model output is persisted as `intraday_llm` events. A separate
`intraday_llm_batch` event records the completed batch, trigger reasons,
heartbeat/cooldown policy, payload mode and an approximate input-token estimate.

Most calls use a compact **delta payload** containing only stable context,
current high-value features, materially changed fields and the previous LLM
assessment. A **full context refresh** is sent at first assessment and then at
least every 30 minutes when that candidate is evaluated again. This preserves
rolling context without retransmitting the complete deterministic feature dump
on every call. The next batch therefore reasons longitudinally rather than
reclassifying each snapshot in isolation.

Runtime counters expose LLM call count, assessment count, errors and token
usage. When the configured provider returns prompt/completion/total token usage,
Omnix records those provider-reported values. Providers that do not expose usage
fall back to a clearly labeled character/4 estimate for input and output. This
makes the learning loop's actual token footprint measurable instead of inferred
from call count alone.

## Dynamic rank

After all candidates have been evaluated for the current finalized-bar prefix,
Omnix persists a deterministic research ranking. Tie-breaking is stable:

1. higher opportunity score;
2. higher execution-quality proxy;
3. lower frozen morning discovery rank;
4. instrument ID.

Every persisted `intraday_learning` event includes:

- live research rank;
- frozen morning rank;
- frozen universe ID/source;
- independent learning dimensions;
- pattern;
- deterministic strategy state/reason;
- `research_only=true`;
- `execution_authority=false`.

This makes it possible to answer questions such as:

- which candidate moved from rank 12 at the open to rank 2 at 09:47?
- did squeeze probability rise before or after the large move?
- which high-ranked names never became deterministic `entry_ready`?
- which deterministic entries came from poor-quality dynamic ranks?
- did a rejected name subsequently produce a large counterfactual move?

## V2 qualification boundary

The canonical frozen V2 profile predates this Finviz experiment and uses the
legacy Yahoo discovery population.

The `intraday_learning_enabled` toggle is observational and does not alter the
canonical V2 execution-profile fingerprint.

Changing V2 discovery from Yahoo to Finviz *does* create a non-canonical
fingerprint. Existing Yahoo prospective evidence therefore cannot authorize
AUTO PAPER for the Finviz experiment.

The Trading UI exposes a dedicated **Load Finviz learning V2** action that:

- selects the frozen V2 causal geometry;
- switches discovery to Finviz;
- enables intraday learning;
- forces SHADOW;
- clears `active_universe_id`.

This provides a clean prospective learning cohort without weakening the
existing AUTO PAPER promotion boundary.

## UI

Trading → Strategies now exposes:

- Discovery source: Finviz Top Gainers or Yahoo Day Gainers.
- Intraday learning toggle.
- **Scan Finviz Top Gainers & freeze** as the preferred manual scan.
- Yahoo fallback.
- A compact live-learning cell per candidate showing:
  - current learning rank;
  - current pattern;
  - squeeze score;
  - failed-selloff score;
  - trend score;
  - gap-hold score.

The original deterministic state and deterministic quality score remain
separate columns.

## What this implementation does not do

It does **not**:

- scrape Finviz repeatedly throughout the session;
- replace the frozen morning cohort with later winners;
- let an LLM place an order;
- let the learning rank authorize AUTO PAPER;
- use Yahoo or Finviz as paper-fill authority;
- claim a V2 L1/B1/L2 signal merely because the research layer labels a name
  `failed_selloff_watch`;
- promote a hypothesis into a new strategy rule.

New intraday movers discovered after the open should eventually be modeled as a
separate timestamped cohort/strategy family rather than being silently inserted
into the frozen premarket experiment.

## Operational flow

```text
09:20 ET
Finviz Top Gainers
    ↓
ordered raw cohort + capture timestamp
    ↓
Yahoo point-in-time enrichment
    ↓
immutable morning universe + fingerprint
    ↓
SHADOW strategy monitor

09:30–16:00 ET
finalized 1m bars
    ↓
deterministic gap/failed-selloff evaluator
    +
research-only learning features
    ↓
dynamic candidate ranks + pattern history
    ↓
StrategyEvent persistence

If deterministic entry_ready
    ↓
existing SHADOW/AUTO PAPER path only
    ↓
Alpaca IEX execution evidence + server risk
```

## Validation expectations

Before using the Finviz learning cohort for a promoted strategy:

1. accumulate prospective sessions;
2. preserve all candidates, including fades and failures;
3. compare morning rank with time-indexed intraday rank;
4. measure false-positive and missed-opportunity rates;
5. derive counterfactual outcomes from the frozen cohort;
6. test proposed rule changes against a frozen out-of-sample dataset;
7. create a separately versioned strategy/profile before allowing any new
   learning-derived rule into AUTO PAPER.
