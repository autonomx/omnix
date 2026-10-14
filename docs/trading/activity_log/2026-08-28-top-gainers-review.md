---
date: 2026-08-28
record_type: day_trading_activity_review
market: US
universe_source: Omnix Top Gainers screenshot
premarket_snapshot_time_et: "~09:25"
prediction_time_et: "~09:25"
status: retrospective_complete_with_market_data_reconciliation_notes
methodology_version: manual_watchlist_v0.2
prior_record: 2026-08-27
strategy_context:
  reference_strategy: gap_pullback_v1
  reference_version: 2.0.0
  automated_trade: false
tickers:
  - PSQL
  - FNGR
  - QNRX
  - WHLR
  - XLAB
  - AEMD
  - ESTC
---

# Day Trading Activity Record — 2026-08-28

## Purpose

This is the second prospective **prediction → market outcome → lesson** record in the Omnix day-trading research journal.

The premarket snapshot and prediction below are intentionally preserved as they existed before the regular session. The retrospective does not rewrite the morning thesis. Its job is to identify where the ranking was useful, where it was wrong, and which hypotheses deserve further prospective testing.

This day's analysis explicitly incorporated lessons from the 2026-08-27 record:

- premarket watch priority is not trade authorization;
- extreme gap extension should receive a nonlinear risk penalty;
- active or unresolved supply risk deserves separate treatment;
- enormous volume is not automatically bullish;
- large-cap earnings continuation should be considered separately from microcap failed-selloff setups;
- the tape must prove seller failure through causal structure before a failed-selloff entry is considered.

No strategy rule is promoted from this record. This remains research evidence only.

---

## 1. Frozen premarket snapshot

Approximate capture time: **09:25 ET**.

| Ticker | Premarket last | Change vs prior close | Premarket volume |
|---|---:|---:|---:|
| PSQL | $17.67 | +80.49% | 1.69M |
| FNGR | $0.30 | +73.01% | 280.92M |
| QNRX | $7.40 | +43.47% | 14.12M |
| WHLR | $1.52 | +35.71% | 34.07M |
| XLAB | $6.28 | +33.06% | 3.99M |
| AEMD | $2.86 | +31.80% | 16.84M |
| ESTC | $104.41 | +24.68% | 361.38K |

These are point-in-time values from the Omnix Top Gainers view, not full premarket OHLC statistics.

---

## 2. Frozen premarket prediction

### Morning ranking

| Rank | Ticker | Predicted setup | Morning view |
|---:|---|---|---|
| **1** | **ESTC** | Continuous trend | **Highest-quality continuous-growth candidate** |
| **2** | **QNRX** | Failed selloff → rebound | **Best failed-selloff watch** |
| **3** | **PSQL** | Low-float squeeze / rebound | Strong raw upside, high risk |
| **4** | **XLAB** | Low-float squeeze | Strong raw upside, very high risk |
| **5** | **WHLR** | Squeeze only | Low methodological quality |
| **6** | **FNGR** | Possible flush/rebound | High distribution concern |
| **7** | **AEMD** | Momentum squeeze | Weakest catalyst quality |

### Category calls made before the open

- **Highest-quality continuous trend:** ESTC
- **Best failed-selloff watch:** QNRX
- **Highest raw squeeze upside:** PSQL
- **Most extreme low-float wildcard:** XLAB
- **Highest distribution concern:** FNGR
- **Most structurally dangerous:** WHLR
- **Weakest catalyst quality:** AEMD

### ESTC thesis

ESTC was treated as the day's closest analogue to the prior day's OKTA setup: a liquid, institutionally relevant earnings/guidance gap rather than a microcap squeeze.

The desired confirmation was:

`opening pullback → VWAP hold/reclaim → higher low → break of opening high`

The morning call was stronger than simply "gap retention": ESTC was explicitly ranked as the best candidate for **continuous intraday growth**.

### QNRX thesis

QNRX had a strong same-day clinical catalyst, but also a same-day financing:

- approximately 6.305M ADSs at **$4.88**;
- warrants for approximately 3.153M ADSs;
- warrant exercise price **$6.10**.

The morning analysis treated **$6.10** as an important structural reference and **$4.88** as a deeper failure level.

The desired failed-selloff sequence was:

`opening flush → absorption near/above $6.10 → L1 → B1 → higher L2 → VWAP reclaim → B1 break`

No blind dip-buy was recommended.

### PSQL thesis

PSQL was beginning its first Nasdaq session after a high-redemption SPAC combination. The morning analysis treated it as a potentially explosive low-public-float squeeze, but applied a substantial extension penalty because it was already up about 80% in the premarket.

The prediction was **high convexity, low directional reliability**.

### XLAB thesis

XLAB was also beginning its first session after a very high-redemption de-SPAC. It was classified as an extreme low-float wildcard where the first 5–10 minutes could be misleading.

The prediction was primarily about **variance and squeeze potential**, not direction.

### WHLR thesis

WHLR combined a recent reverse split, extremely high turnover relative to its apparent share count, and a difficult capital structure.

It was classified as:

**tradable volatility, low methodological quality.**

### FNGR thesis

FNGR had enormous premarket turnover but a weaker-quality AI/HPC narrative and financing/supply overhang. The morning analysis warned that the volume could represent distribution and ranked FNGR near the bottom.

This became the largest error of the day.

### AEMD thesis

AEMD had very high turnover, a tiny effective share structure, financing/warrant history, and no comparably strong fresh catalyst identified in the morning research.

It was ranked last as a lower-quality momentum squeeze.

---

## 3. Post-close evidence and scorecard

### Market-data reconciliation note

This review was written immediately after the August 28 close. Several of the microcap and first-day-listing feeds were still reconciling or returning inconsistent final prints at review time.

For research integrity:

- the premarket snapshot is frozen and will never change;
- post-close values that have a reliable final print are recorded as final;
- values supported only by late-session observations are explicitly marked **provisional/observed**;
- later reconciliation may correct an OHLC/volume field, but must not alter the prediction grade or hindsight analysis without an explicit revision note.

This is preferable to silently inventing precision.

### Summary scorecard

| Ticker | Premarket reference | Post-session evidence | Result vs morning thesis | Grade |
|---|---:|---|---|---|
| **QNRX** | $7.40 | ~$6.20 observed late morning near the $6.10 warrant level; reported close **$7.71**, ~19.3M shares | **Strong hit**: meaningful selloff/absorption followed by recovery above premarket reference | **A-** |
| **ESTC** | $104.41 | post-close quote around **$100.64**, still about +20% vs prior close | **Partial hit**: excellent gap retention, but not continuous growth from the premarket/opening reference | **B-** |
| **PSQL** | $17.67 | first-day range observed roughly **$13.08–$17.45**; late/final feeds around the mid-$13s | **Good risk call**: extension penalty was justified; it did not simply continue upward | **B+** |
| **XLAB** | $6.28 | first-day trading produced an extremely wide range; observations included roughly **$4.25/$5.25 to $11.00**, later returning toward the mid-$5s/$6s | **Strong classification hit**: low-float de-SPAC predicted variance, not direction | **A-** |
| **WHLR** | $1.52 | high near ~$1.55 followed by material fade; late observations roughly $1.20–$1.30 | **Good caution call**: unstable squeeze, poor clean continuation | **B+** |
| **FNGR** | $0.30 | traded as high as about **$0.71**; >600M shares traded by mid-morning and >800M in later observations; still around $0.43–$0.54 late in the session | **Major miss**: strongest intraday squeeze was ranked near the bottom | **D** |
| **AEMD** | $2.86 | observed high around **$3.29** and mid/late-session values near the high-$2s | **Reasonable caution**: active momentum, but no evidence it became the cleanest sustained leader | **B** |

### QNRX — best call of the day

The central morning thesis was not "QNRX is bullish." It was:

> QNRX is the best failed-selloff watch **if the tape proves that the financing/supply can be absorbed**, with special attention to $6.10.

By approximately 11:08 ET, QNRX was observed around **$6.20**, strikingly close to the **$6.10 warrant exercise price** highlighted before the open. Later reporting showed a **$7.71 close**, above the $7.40 premarket reference.

Premarket-reference to reported close:

`($7.71 / $7.40 - 1) × 100 ≈ +4.19%`

More importantly, the path mattered: a sizable selloff toward the known supply reference was followed by substantial recovery.

This is directionally consistent with the failed-selloff thesis.

**Important limitation:** public end-of-day snippets are not enough to prove that Omnix V2's exact causal `L1 → B1 → higher L2 → VWAP/B1 break` sequence occurred. That requires the actual 1-minute bar prefix and deterministic evaluator. The journal therefore records this as a successful **setup thesis**, not a verified V2 signal.

**Grade: A-**

### ESTC — high-quality gap retention, but the wording "continuous growth" was too strong

ESTC remained one of the strongest liquid names in the market and retained a very large portion of its earnings gap. Post-close market data showed it around **$100.64**, roughly +20% from the prior close.

However, the frozen premarket reference was **$104.41**.

Premarket-reference to post-close quote:

`($100.64 / $104.41 - 1) × 100 ≈ -3.61%`

So the fundamental/catalyst-quality assessment was useful, but the directional label was not precise enough. ESTC was better described as a **high-quality gap hold / relative-strength candidate** than as a guaranteed continuous-growth name.

The broader Nasdaq weakened during the session, which makes the retained +20% earnings gap notable, but it does not turn a premarket-to-close fade into continuous growth.

**Grade: B-**

### PSQL — extension penalty worked

PSQL's debut produced exactly the type of instability the morning analysis warned about.

The premarket reference was **$17.67**. Yahoo's intraday data showed:

- open around $16.98;
- high around $17.45;
- low around $13.08;
- first-day volume above 3M shares in later snapshots.

The stock ultimately finished well below the $17.67 premarket reference according to post-close reporting.

The important point is not the exact last print while first-day feeds reconcile. It is that **+80% premarket did not justify extrapolating continued upside**.

Yesterday's nonlinear extension lesson helped here.

The one miss inside the PSQL call is relative ranking: it was labelled the highest raw squeeze-upside candidate, but **FNGR delivered the much larger actual intraday squeeze**.

**Grade: B+**

### XLAB — variance prediction was better than a directional prediction would have been

XLAB demonstrated why high-redemption de-SPACs should not be handled as ordinary gappers.

Public observations for the first session showed prices ranging from the mid-$4s/low-$5s to as high as **$11.00**, before returning toward the premarket region.

The frozen premarket reference was only **$6.28**.

That means XLAB could move tens of percent in both directions while still ending up near the original reference.

This validates a key methodological distinction:

> Extremely low effective float predicts **variance and market-impact risk** much more reliably than it predicts direction.

That should affect execution/risk sizing and candidate classification, but it should not automatically add bullish points.

**Grade: A-**

### WHLR — caution was justified

WHLR's premarket reference was **$1.52**. During the session, public active-stock data showed a high around **$1.55**, followed by lower prices in the $1.20s later in the day.

That is consistent with the morning description:

**squeeze-capable, but structurally dangerous and low-quality as a clean methodology candidate.**

Its massive turnover did not create a clean all-day continuation.

**Grade: B+**

### FNGR — biggest miss and most valuable lesson

FNGR is the most important error in today's record.

The morning analysis correctly identified real weaknesses:

- the AI/HPC announcement was more strategic than contractual;
- no new signed site/customer/power/project-financing agreement was identified;
- the company had meaningful financing/supply overhang;
- 280M+ premarket shares of turnover could have represented distribution.

But those facts were used too aggressively to suppress **intraday squeeze probability**.

FNGR then traded from the **$0.30 premarket reference to roughly $0.71 intraday**, while volume exploded beyond 600M shares by mid-morning and above 800M in later observations.

Reference-to-intraday-high move:

`($0.71 / $0.30 - 1) × 100 ≈ +136.7%`

Even after a substantial late fade, FNGR remained dramatically above the prior close and above the premarket reference in late-session quotes.

So:

- the **fundamental-quality / supply-risk warning** was defensible;
- the **opportunity ranking** was wrong.

This exposes a flaw in using one blended score.

**Grade: D**

### AEMD — acceptable low-priority classification

AEMD had active momentum and public active-stock reports showed it trading as high as approximately **$3.29**, versus the $2.86 premarket reference.

However, it did not invalidate the core morning concern that this was a more difficult, lower-quality setup from a catalyst/supply perspective than QNRX or ESTC.

The main lesson is similar to FNGR, but less dramatic: catalyst quality and supply quality should not be treated as direct substitutes for tape/momentum probability.

**Grade: B**

---

## 4. What was learned

### 4.1 We need separate scores for "quality" and "opportunity"

Today's largest methodological improvement is to stop compressing several different questions into one ranking.

FNGR demonstrates why.

A candidate can simultaneously have:

- weak fundamental/catalyst specificity;
- high dilution/supply risk;
- poor long-duration holding quality;

and still have:

- exceptional intraday momentum;
- strong squeeze probability;
- enough price acceptance to produce a very large tradable move.

Future Omnix research should maintain independent dimensions such as:

1. **Catalyst quality**
2. **Supply/dilution risk**
3. **Float/market-structure risk**
4. **Premarket extension risk**
5. **Momentum/squeeze probability**
6. **Failed-selloff probability**
7. **Trend/gap-retention probability**
8. **Execution quality / spread / halt risk**

A single "best stock" score hides too much information.

### 4.2 Yesterday's volume lesson needs refinement

The 2026-08-27 lesson was:

> Huge volume is not automatically bullish.

That remains correct.

Today's refinement is:

> Huge volume **plus sustained price acceptance** can be highly bullish intraday even when fundamental quality is weak.

The useful variable is not raw volume alone.

A better causal feature set is:

- turnover relative to float/free float;
- price change during that turnover;
- ability to hold above VWAP;
- higher-high / higher-low persistence;
- red-volume vs green-volume behavior;
- bounce failure count;
- distance from premarket high;
- spread and halt behavior.

VNRX yesterday and FNGR today are valuable opposite examples:

- **VNRX:** extraordinary turnover + poor retention → distribution.
- **FNGR:** extraordinary turnover + sustained price expansion for much of the session → squeeze/momentum.

The same raw feature — huge volume — produced opposite outcomes because the **price response** differed.

### 4.3 Supply risk can provide a map, not only a veto

QNRX is especially useful.

The $6.10 warrant strike was identified before the open. The stock later traded around $6.20 and recovered strongly.

This suggests a research hypothesis:

> Known supply levels can be treated as structural reference zones. If price reaches the zone and the tape demonstrates absorption, that information may increase the quality of a failed-selloff setup rather than merely disqualify the stock.

This must not be implemented as an automatic bullish rule. It needs prospective testing.

A future state might distinguish:

- `active_supply_unresolved`
- `active_supply_price_above_reference`
- `supply_reference_tested`
- `supply_reference_absorbed`
- `supply_reference_failed`

Only causal market evidence could transition from "risk" to "apparently absorbed."

### 4.4 Gap retention is not the same target as continuous growth

ESTC was a good **gap-retention / relative-strength** call but only a partial **continuous-growth** call.

The journal should therefore stop using one vague "continuation" label.

Candidate outcome families should be separated into at least:

- **trend_continuation** — higher highs / higher lows with sustained trend;
- **gap_hold** — retains most of the gap but does not trend monotonically higher;
- **opening_fade_recovery** — sells off materially, then recovers;
- **failed_selloff_breakout** — the specific L1/B1/L2/VWAP/B1-break setup;
- **squeeze_momentum** — price discovery driven by float/short/turnover dynamics;
- **distribution/fade** — gap fails and closes weak.

This will make prediction calibration far more meaningful.

### 4.5 Low-float/de-SPAC characteristics predict volatility better than direction

PSQL and XLAB reinforce this.

High redemptions and tiny public supply can create:

- rapid upside;
- violent downside;
- multiple halts;
- very wide spreads;
- enormous intraday ranges.

That is useful information, but it should primarily influence:

- expected variance;
- maximum position size;
- allowable slippage;
- halt risk;
- entry-confirmation strictness;

rather than a simple bullish score.

### 4.6 Extension penalties need to be conditional

PSQL supports the nonlinear extension penalty: +80% premarket preceded a material fade.

FNGR shows why extension alone cannot become a hard rejection: it was already +73% in the premarket and still produced an enormous additional squeeze.

A better formulation to test is:

**premarket extension reduces prior probability of clean continuation, but post-open price acceptance can override the prior.**

In other words:

`premarket prior + causal tape evidence → updated probability`

not:

`premarket extension > threshold → reject`.

### 4.7 Dynamic re-ranking is essential

A static 09:25 ranking cannot capture what happened today.

A useful Omnix research ranking should be recomputed at causal checkpoints such as:

- 09:35;
- 09:45;
- 10:00;
- 10:30;
- 11:00.

Had we re-ranked after the open:

- FNGR should have moved sharply upward as price continued to expand on extraordinary turnover;
- QNRX should have remained high if the $6.10 area showed absorption;
- ESTC should have shifted from "continuous growth" to "gap hold / relative strength" as it failed to extend from the premarket reference;
- PSQL/XLAB should have remained in a separate high-variance bucket.

### 4.8 One letter grade is no longer enough

Beginning with future records, each candidate should receive separate retrospective grades:

- **Setup classification grade** — did we understand what kind of ticker/setup it was?
- **Opportunity ranking grade** — did we rank its actual intraday opportunity correctly?
- **Risk classification grade** — did we identify the major failure modes?
- **Deterministic-signal grade** — when Omnix has the 1-minute bars, did the actual strategy signal occur and what happened afterward?

For example, FNGR was:

- decent risk classification;
- poor opportunity ranking.

Calling both simply "D" loses that distinction.

---

## 5. Cross-day comparison: 2026-08-27 vs 2026-08-28

Two days already give us useful paired examples, although this is nowhere near enough evidence to change a live strategy.

| Pattern / question | 2026-08-27 example | 2026-08-28 example | Research implication |
|---|---|---|---|
| Huge turnover | VNRX → closed very weak | FNGR → enormous squeeze | Volume requires price-response context |
| High-quality earnings gap | OKTA → strong trend/close | ESTC → strong gap hold, less clean trend | Separate trend continuation from gap retention |
| Extreme premarket extension | PPCB → blow-off/fade | PSQL → material fade | Nonlinear extension penalty remains useful |
| Supply overhang | VNRX → distribution | QNRX → test near known supply level then recovery | Supply needs state/context, not only binary veto |
| Tiny/de-SPAC float | — | PSQL / XLAB → extreme variance | Float predicts volatility/risk more reliably than direction |
| Premarket "best rebound" | MIMI → failed badly | QNRX → recovery thesis worked | Waiting for causal seller-failure evidence improves robustness |

The strongest cross-day lesson is that **static descriptive facts are not enough**.

The methodology needs two layers:

1. **Premarket prior:** catalyst, supply, extension, float, liquidity, structure.
2. **Post-open Bayesian-style update:** price retention, VWAP, pivots, volume response, spread, halts, and seller-failure evidence.

---

## 6. Research hypotheses generated by this day

These are hypotheses for testing, not strategy changes.

1. Split candidate scoring into independent quality, risk, squeeze, failed-selloff, and trend dimensions.
2. Model turnover jointly with price acceptance rather than treating high volume as bullish or bearish by itself.
3. Add known financing/warrant prices as structural reference levels.
4. Research a causal `supply_reference_absorbed` state rather than treating all active supply as equivalent.
5. Separate `gap_hold` from `trend_continuation` labels.
6. Treat high-redemption de-SPACs as a distinct high-variance regime.
7. Make the extension penalty a premarket prior that can be overcome by post-open causal evidence.
8. Add fixed intraday re-ranking checkpoints.
9. Store both premarket and intraday ranks so we can evaluate whether dynamic ranking actually adds value.
10. Add multi-dimensional retrospective grades instead of one letter grade.
11. Require actual 1-minute bar data before claiming that a V2 L1/B1/L2 signal occurred.
12. Do not promote any of these changes to AUTO PAPER based on two journal days.

---

## 7. Fields to add to future records

The 2026-08-27 schema remains useful. Based on today's findings, add:

### Independent premarket scores

- catalyst_quality_score;
- supply_risk_score;
- float_structure_risk_score;
- extension_risk_score;
- squeeze_probability_score;
- failed_selloff_watch_score;
- trend_continuation_score;
- gap_retention_score.

### Supply reference fields

- financing_price;
- warrant_strike;
- convertible_reference_price;
- resale_effective_status;
- nearest_supply_reference_pct;
- supply_reference_test_time;
- supply_reference_result: `not_tested | held | absorbed | failed | unknown`.

### Dynamic ranking

- rank_0925;
- rank_0935;
- rank_0945;
- rank_1000;
- rank_1030;
- rank_1100;
- rank_change_reason.

### Tape response

- first_5m_return;
- first_15m_return;
- premarket_high_retention_pct;
- VWAP_state;
- higher_high_count;
- higher_low_count;
- bounce_failure_count;
- turnover_to_float;
- price_change_per_turnover;
- halt_count.

### Retrospective grades

- setup_classification_grade;
- opportunity_ranking_grade;
- risk_classification_grade;
- deterministic_signal_grade.

---

## 8. Data provenance

### Premarket snapshot

Manual Omnix Top Gainers screenshot captured shortly before the August 28, 2026 regular-session open.

### Public market/news references used for the retrospective

- Yahoo Finance market/quote data:
  - https://finance.yahoo.com/
  - https://finance.yahoo.com/quote/PSQL/
  - https://finance.yahoo.com/quote/ESTC/
  - https://finance.yahoo.com/quote/XLAB/
- Associated Press most-active market report distributed via Yahoo Finance:
  - https://finance.yahoo.com/markets/stocks/articles/bc-most-active-stocks-143017819.html
- QNRX post-close report:
  - https://tickerdaily.com/article/why-is-quoin-pharmaceuticals-ltd-american-depositary-shares-qnrx-stock-up-593percent-today
- FNGR intraday report:
  - https://ts2.tech/en/fingermotion-stock-soars-261-7-on-modular-ai-data-center-pivot/
- XLAB first-day report:
  - https://ts2.tech/en/exascale-labs-stock-rises-12-on-nasdaq-debut-as-300-million-pipeline-meets-12-million-cash-base/
- PSQL first-day report:
  - https://ts2.tech/en/pasqal-stock-jumps-54-7-in-nasdaq-debut-after-2-billion-quantum-merger/
- ESTC earnings-gap reporting:
  - https://ts2.tech/en/elastic-stock-jumps-17-4-as-1-85-billion-rpo-extends-visibility/

### Data-quality caveat

For thin microcaps and first-day listings, immediately post-close web feeds can disagree because of:

- delayed consolidated prints;
- first-day ticker mapping;
- split adjustments;
- quote-cache lag;
- after-hours prints mixed with the regular close.

Any later numerical correction must be recorded as a provenance/reconciliation update. It must not modify the frozen premarket prediction.

---

## 9. Journal rule reaffirmed

Each day remains an immutable prospective experiment:

1. Freeze the premarket universe, evidence, ranking, and thesis before the open.
2. Do not edit the frozen prediction after seeing the tape.
3. Capture causal post-open observations separately.
4. Record misses as prominently as hits.
5. Distinguish setup quality from opportunity ranking.
6. Accumulate enough days before testing a methodology change.
7. Validate proposed changes on a frozen out-of-sample dataset.
8. Only then consider integrating a versioned deterministic strategy into Omnix.

Today's most valuable result is not that QNRX was a good call. It is that **FNGR exposed a scoring flaw**: fundamental/supply quality and intraday squeeze probability are separate variables and must be modeled separately.
