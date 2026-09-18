# Yahoo Evidence & Recovery Hardening

## Purpose

This phase makes substantially better use of the free Yahoo data Omnix already
consumes without weakening execution or consolidated-volume authority.

Yahoo is authorized for:

- finalized Yahoo OHLC observations;
- deterministic 1m-derived higher timeframes;
- Yahoo same-feed premarket volume and dollar volume;
- Yahoo-relative TOD RVOL;
- exact-range repair of Yahoo price/bar gaps.

Yahoo is **not** authorized for:

- consolidated SIP volume;
- NBBO/live bid-ask authority;
- fill/execution authority;
- halt/no-trade proof by itself.

## Recovery order

For Yahoo-backed US equities the shared market-data service now uses:

1. bounded ordinary Yahoo acquisition/retry;
2. durable locally persisted Yahoo 1m observations;
3. fresh exact-range Yahoo 1m recovery over the unresolved window;
4. deterministic aggregation of repaired 1m bars to coarser timeframes;
5. Alpaca IEX partial-market fallback;
6. explicit unresolved gaps if evidence is still missing.

No synthetic OHLCV values are created.

## Persistent evidence

Finalized Yahoo 1m bars are stored under
`resources/trading/yahoo_evidence` by default. The location can be changed with
`OMNIX_TRADING_YAHOO_EVIDENCE_DIR`.

The evidence store is independent of the disposable market-data cache. Once a
finalized minute has been observed it can be reused after process restarts and
during a later Yahoo outage.

## Provider-relative volume

Yahoo TOD RVOL is versioned as
`market-evidence-yahoo-relative-v1`. Both numerator and historical denominator
come from Yahoo at the same clock cutoff. It must never be presented as
consolidated US-market RVOL.

A ready Yahoo provider-relative observation may rescue incomplete Alpaca IEX
premarket evidence. This does not promote Yahoo to SIP or execution authority.

## Feature-local validity

The legacy `candidate.market_data_complete` Boolean is now diagnostic rather
than a live trade-wide veto. Strategies still fail closed on inputs they
actually require:

- missing/low premarket dollar volume;
- missing/low same-feed RVOL when required;
- invalid price range/gap;
- missing live spread/execution observation;
- strategy-specific bar/feature coverage.

Unrelated candidate enrichment no longer blocks a strategy whose required
feature certificates are valid.

Stoch RSI is treated as recursive state. After an old unresolved gap it may
resume only after an explicit 30-clean-5m-bar reseed, and the evaluator receives
only the latest contiguous suffix.

## Diagnostics

`GET /api/trading/market-data/yahoo-evidence/diagnostics` exposes:

- persisted/load counts;
- exact-repair attempts and successes;
- repaired bar count;
- unresolved repair count;
- Yahoo RVOL baseline hit/miss counts;
- strategy-level Yahoo-repaired candidate evaluation count;
- strategy-level Yahoo-unresolved candidate evaluation count;
- explicit consolidated-volume/execution authority flags.

These metrics make it possible to distinguish provider failures from policy
vetoes and quantify how often Yahoo hardening rescues live evaluations.
