---
date: 2026-08-27
record_type: day_trading_activity_review
market: US
universe_source: Omnix Top Gainers / Finviz-style top-gainers snapshot
premarket_snapshot_time_et: "~09:25"
prediction_time_et: "~09:25"
status: retrospective_complete
strategy_context:
  reference_strategy: gap_pullback_v1
  reference_version: 2.0.0
  automated_trade: false
tickers:
  - PPCB
  - VNRX
  - WNW
  - MIMI
  - OKTA
  - BTCT
---

# Day Trading Activity Record — 2026-08-27

## Purpose

This is the first manually curated **prediction → market outcome → lesson** record for the Omnix day-trading research workflow.

The goal is not to rewrite history after the close. The premarket snapshot and forecast below preserve what was actually visible and predicted before the regular session. The retrospective section then scores those predictions against the completed session.

Over time, records in this format should become a prospective research dataset that can be used to:

- identify which premarket attributes actually predict continuation, failed selloffs, or all-day distribution;
- distinguish useful watchlist ranking from actual trade authorization;
- test changes to the deterministic strategy against accumulated out-of-sample days;
- eventually feed a versioned Omnix trading strategy without allowing hindsight or an LLM to authorize orders.

This record is research material, not a trade recommendation.

---

## 1. Premarket snapshot

Approximate capture time: **09:25 ET**, shortly before the regular-session open.

These values are transcribed from the Omnix Top Gainers screenshot used for the prediction. They are a point-in-time snapshot, not full-session premarket high/low statistics.

| Ticker | Premarket last | Change vs prior close | Premarket volume | Signal |
|---|---:|---:|---:|---|
| PPCB | $3.63 | +239.25% | 33.13M | Top Gainers |
| VNRX | $0.66 | +93.60% | 201.19M | Top Gainers |
| WNW | $3.26 | +31.45% | 7.63M | Top Gainers |
| MIMI | $2.19 | +21.67% | 4.77M | Top Gainers |
| OKTA | $161.93 | +20.47% | 520.14K | Top Gainers |
| BTCT | $2.12 | +17.34% | 4.93M | Top Gainers |

### Morning setup context

The manual analysis separated the list into two different setup families:

1. **Failed selloff / rebound:** a gapper sells off after the open, proves seller exhaustion, forms a higher low, reclaims VWAP, and breaks the first bounce high.
2. **Sustained trend / continuation:** the gap is held and buyers continue to control the tape for most of the session.

That distinction matches the current Omnix V2 failed-selloff structure conceptually: **L1 → B1 → higher L2 → VWAP/B1 break**. Premarket ranking alone was not intended to authorize an entry.

---

## 2. Premarket prediction

### Ranking made before the open

| Ticker | Failed selloff → rebound view | Continuous trend view | Premarket conclusion |
|---|---|---|---|
| **MIMI** | High | Medium | **Preferred cleaner failed-selloff/rebound candidate** |
| **VNRX** | Very high raw upside, but high risk | Medium | **Largest raw rebound potential, but supply/dilution risk was a major concern** |
| **OKTA** | Low/medium | **Very high** | **Best sustained trend-day candidate** |
| **WNW** | Medium | Low/medium | Secondary candidate; capital-structure/supply concerns |
| **PPCB** | High volatility, but low-quality rebound | Low | **Extremely extended; major blow-off/selloff risk** |
| **BTCT** | Medium | Low/medium | Secondary; already extended over multiple sessions |

### Specific premarket calls

#### MIMI
The preferred failed-selloff candidate. The desired pattern was:

`open/spike → controlled selloff → L1 → rebound → higher L2 → VWAP reclaim → B1 break`

The mistake, in retrospect, was assigning too much confidence to MIMI *before* the tape proved that sequence.

#### VNRX
Expected to have the greatest raw potential for a violent flush-and-recovery because of extraordinary volume and volatility. At the same time, active financing/supply risk was explicitly treated as a serious reason to reject or downgrade it.

#### OKTA
Predicted to be the strongest candidate for sustained intraday continuation because the move was driven by a large-cap earnings/guidance catalyst rather than a microcap squeeze dynamic.

#### WNW
Ranked below MIMI/VNRX. It had a real catalyst, but supply/capital-structure concerns reduced confidence.

#### PPCB
Predicted to have one of the highest probabilities of a major post-gap selloff. At +239% premarket, the main concern was blow-off behavior. A rebound was only considered acceptable if the tape later proved a higher-low / reclaim structure.

#### BTCT
Considered secondary because the name was already extended from previous sessions and did not fit the cleanest version of the fresh-gap setup.

---

## 3. Completed-session results

Regular-session outcome data below was checked after the August 27 close. Data vendors can occasionally revise final consolidated prints, so the source URLs are retained.

| Ticker | Day high | Day low | Close | Volume | Premarket snapshot → close | Close location in day range |
|---|---:|---:|---:|---:|---:|---:|
| **PPCB** | $4.13 | $1.98 | $2.24 | 95.19M | **-38.29%** | **12.09%** |
| **VNRX** | $0.7200 | $0.5101 | $0.5104 | 346.60M | **-22.67%** | **0.14%** |
| **WNW** | $3.69 | $3.06 | $3.31 | 15.81M | **+1.53%** | **39.68%** |
| **MIMI** | $3.29 | $1.26 | $1.28 | 49.88M | **-41.55%** | **0.99%** |
| **OKTA** | $174.85 | $156.50 | $172.91 | 16.21M | **+6.78%** | **89.43%** |
| **BTCT** | $2.44 | $2.03 | $2.28 | 14.37M | **+7.55%** | **60.98%** |

**Close location** is calculated as:

`(close - low) / (high - low)`

A value near 100% means the stock finished near the session high. A value near 0% means it finished near the session low.

### Outcome by ticker

#### PPCB — prediction largely correct
PPCB reached $4.13, fell as low as $1.98, and closed at $2.24. It finished only ~12% of the way up from the session low to the high and ~38% below the premarket reference price.

This strongly matched the **extreme-extension / blow-off-risk** thesis.

**Grade: A**

#### VNRX — supply caution was right; rebound thesis was not
VNRX traded to $0.72 but closed at $0.5104, essentially the session low. Its close-location value was ~0.14%.

The warning about supply/distribution risk was useful. The expectation that its enormous volume could create the best raw rebound opportunity was too optimistic.

**Grade: C- / mixed**

#### WNW — underestimated
WNW closed at $3.31, slightly above the premarket reference and well above its $3.06 low. It did not produce a spectacular trend day, but it retained its gap much better than MIMI or VNRX.

The morning ranking placed it too low.

**Grade: C+**

#### MIMI — largest miss
MIMI reached $3.29 but later fell to $1.26 and closed at $1.28 — only ~1% of the way up from the session low.

The premarket designation as the preferred failed-selloff candidate was wrong. The name showed that a real catalyst, acceptable initial gap, and active volume are not sufficient evidence that sellers will fail.

**Grade: F**

#### OKTA — strongest hit
OKTA traded down to $156.50, recovered, reached $174.85, and closed at $172.91 — ~89% of the way up its session range.

The prediction that it was the best sustained trend candidate was strongly validated.

**Grade: A**

#### BTCT — reasonable secondary call, but continuation was stronger than expected
BTCT reached $2.44 and closed at $2.28, ~61% of the way up its daily range and ~7.6% above the premarket snapshot.

It was correctly treated as a secondary setup, but its actual retention/continuation was better than the morning ranking implied.

**Grade: B**

---

## 4. What was learned

### 4.1 Watchlist priority must not be confused with rebound probability

The most important mistake was treating:

> "This ticker has the ingredients for a failed-selloff rebound"

as too close to:

> "This ticker is likely to rebound."

Those are not equivalent.

For MIMI and VNRX, the better premarket description would have been:

**high-priority watch candidate; bullish probability remains unproven until the tape demonstrates seller failure.**

That is consistent with the current deterministic Omnix V2 concept. The strategy should continue to wait for actual structure rather than entering because a premarket ranking is favorable.

### 4.2 Extreme extension should carry a nonlinear penalty

PPCB is the clearest example. A +239% premarket move can still trade higher briefly, but the probability and magnitude of distribution become materially different from a +20% to +40% gap.

A future ranking model should test explicit nonlinear extension bands, for example:

- 20–40%: normal candidate range;
- 40–60%: elevated extension;
- 60–100%: high extension;
- 100–200%: extreme;
- >200%: blow-off regime.

These bands are **hypotheses to test**, not strategy changes justified by one day.

### 4.3 Huge volume is not automatically bullish

VNRX traded hundreds of millions of shares and still closed essentially at the low.

Volume needs context:

- accumulation vs distribution;
- buying volume vs selling volume;
- ability to reclaim and hold VWAP;
- higher-low formation;
- whether each bounce is sold into;
- active supply, ATM, warrants, convertibles, or resale registrations.

"More volume" should not simply increase a rebound score.

### 4.4 Supply/dilution evidence deserves heavy weighting

The VNRX result supports keeping supply facts separate from general catalyst quality.

For future research, the record should distinguish:

- active ATM;
- active registered offering;
- warrants;
- convertible debt/securities;
- shelf capacity;
- resale registration;
- exhausted/terminated/redeemed supply;
- unresolved supply status.

The existing Omnix typed supply-fact approach is preferable to a generic bearish keyword flag.

### 4.5 Large-cap earnings continuation is a different strategy family

OKTA behaved fundamentally differently from the microcap gappers.

It should not be forced into the same model as PPCB, VNRX, MIMI, or WNW. A future Omnix strategy catalog should likely contain a separate setup such as:

**earnings_gap_continuation**

with different expectations for:

- price range;
- institutional liquidity;
- spread;
- float;
- catalyst quality;
- opening pullback depth;
- VWAP behavior;
- holding period.

The current microcap failed-selloff strategy should not be weakened just to make OKTA eligible.

### 4.6 Ranking should update after the open

The 09:25 ranking should be treated as **watchlist ordering**, not a static all-morning forecast.

A dynamic post-open rank could incorporate:

- premarket price retention;
- first 5–15 minute direction;
- first pullback depth;
- red-volume contraction/expansion;
- VWAP position;
- L1/B1/L2 state;
- bounce failure count;
- spread expansion;
- halt behavior;
- new supply/catalyst evidence.

Had the ranking updated from the opening tape, MIMI and VNRX should have fallen quickly while WNW and OKTA should have moved higher.

### 4.7 Close-location and premarket-retention are useful retrospective labels

Two simple outcome labels separated today's names well:

**Premarket snapshot → close return**
- PPCB: -38.29%
- VNRX: -22.67%
- WNW: +1.53%
- MIMI: -41.55%
- OKTA: +6.78%
- BTCT: +7.55%

**Close location**
- PPCB: 12.09%
- VNRX: 0.14%
- WNW: 39.68%
- MIMI: 0.99%
- OKTA: 89.43%
- BTCT: 60.98%

These should be stored routinely, but they are retrospective labels — never inputs to the same day's prediction.

---

## 5. Research hypotheses generated by this day

Do **not** promote any of these to live/auto-paper rules from this single observation. Accumulate prospective records first, then test them on a frozen dataset.

1. Add a nonlinear premarket-extension penalty to candidate ranking.
2. Penalize or veto unresolved active supply more heavily.
3. Separate "watch priority" from "probability of successful rebound."
4. Re-rank candidates continuously from 09:30–10:30 based on causal tape evidence.
5. Treat very high volume with weak price retention as possible distribution rather than strength.
6. Maintain a separate large-cap earnings-gap continuation strategy family.
7. Measure prediction calibration explicitly instead of only winner/loser outcomes.
8. Preserve the current failed-selloff requirement that the tape prove L1 → B1 → higher L2 → reclaim/break before entry.

---

## 6. Suggested fields for future daily records

For this journal to become useful strategy-research data, future daily files should preserve the same broad schema.

### Premarket evidence
- snapshot timestamp;
- ticker;
- previous close;
- premarket last/high/low;
- gap %;
- premarket volume;
- premarket dollar volume;
- TOD RVOL;
- float;
- market cap;
- spread;
- catalyst class and timestamp;
- catalyst evidence IDs/URLs;
- typed supply facts;
- halt/news anomalies.

### Prediction
- predicted setup family;
- watchlist rank;
- continuation probability band;
- failed-selloff probability band;
- confidence;
- key bullish evidence;
- key bearish evidence;
- invalidation criteria;
- model/methodology version.

### Causal intraday structure
- regular-session open;
- L1 time/price;
- B1 time/price;
- L2 time/price;
- VWAP reclaim time;
- B1/lower-high break time;
- breakout volume ratio;
- spread at signal;
- halts;
- whether deterministic entry criteria were ever satisfied.

### Outcome
- high;
- low;
- close;
- regular-session volume;
- close location;
- premarket-reference → close return;
- maximum favorable excursion from the premarket reference;
- maximum adverse excursion;
- first-hour outcome;
- 11:30 ET outcome;
- end-of-day outcome.

### Review
- prediction grade;
- error category;
- what evidence was overweighted;
- what evidence was underweighted;
- new hypothesis;
- whether the hypothesis is merely observational or has enough samples to test.

---

## 7. Data provenance

### Premarket snapshot
Manual Omnix Top Gainers screenshot captured shortly before the August 27, 2026 open.

### Completed-session price data
- PPCB: https://stockscan.io/stocks/PPCB/price-history
- VNRX: https://stockscan.io/stocks/VNRX/price-history
- WNW: https://stockscan.io/stocks/WNW/price-history
- MIMI: https://stockscan.io/stocks/MIMI/price-history
- OKTA: https://stockscan.io/stocks/OKTA/price-history
- BTCT: https://stockscan.io/stocks/BTCT/price-history

For OKTA, an additional Nasdaq-real-time-derived reference was checked:
- https://prostockcharts.com/stock/OKTA

### Omnix implementation context
Relevant deterministic strategy files at the time of this record:

- `src/app/trading/strategies/failed_selloff_v2.py`
- `src/app/trading/strategies/gap_pullback.py`
- `src/app/trading/strategies/models.py`
- `src/app/trading/catalyst_evidence.py`

---

## 8. Journal rule going forward

Each trading day should be treated as an immutable prospective experiment:

1. **Freeze the premarket snapshot and prediction before the open.**
2. Never edit that prediction because of later price action.
3. Append or complete the post-close outcome separately.
4. Record errors explicitly, including failed predictions.
5. Generate hypotheses from repeated patterns.
6. Only modify a strategy after sufficient prospective samples and a separate validation step.
7. Version every promoted methodology so results remain attributable to the rules that actually produced them.

The objective is not to make the journal look accurate. The objective is to make it useful enough that Omnix can become measurably more accurate over time.
