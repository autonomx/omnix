# Yahoo Evidence & Recovery Hardening

## Purpose

This work makes materially better use of the free Yahoo data Omnix already
consumes without weakening execution, NBBO, halt, or consolidated-volume
authority.

The goal is **fault-tolerant continuity**, not a promise that any remote market
data vendor is always available.

Yahoo is authorized for:

- finalized Yahoo OHLC observations;
- deterministic higher-timeframe bars derived from canonical Yahoo 1m evidence;
- Yahoo same-feed premarket volume and dollar volume;
- coverage-qualified Yahoo-relative TOD RVOL;
- exact-range repair of Yahoo price/bar gaps;
- proactive factual capture for active trading universes.

Yahoo is **not** authorized for:

- consolidated SIP volume;
- NBBO/live bid-ask authority;
- fill/execution authority;
- halt/no-trade proof by itself.

Alpaca IEX remains execution/partial-market evidence only. Independent trading
status evidence is required before a missing interval can be classified as a
confirmed halt/no-trade interval.

## Frozen strategy policy during validation

Trading thresholds, entry/exit rules, minimum-R geometry, and Stoch parameters
remain frozen while the data layer is being validated. Data-infrastructure
changes must not be mixed with strategy tuning when evaluating whether the
hardening improves prospective results.

## Phase 0 — authority invariants

**Implemented.**

Yahoo and Alpaca IEX carry explicit provider-relative authority. Yahoo cannot
authorize consolidated volume, live bid/ask, or fills. Tests fail closed on any
attempt to promote those evidence types.

**Exit gate:** authority tests prove Yahoo cannot acquire SIP/execution
authority.

## Phase 1 — causal evidence model

**Implemented.**

Market time and knowledge time are separate. Recovery and feature certificates
support:

- `live`
- `causal_replay`
- `retroactive_research`

A causal replay excludes a bar whose `received_at` is later than the decision
clock. A later repair may still be used for explicitly retroactive research, but
cannot rewrite what the strategy knew prospectively.

**Exit gate:** tests prove a late-learned bar is absent from causal replay and
available only to retroactive research.

## Phase 2 — proactive Yahoo acquisition

**Implemented.**

`TradingYahooAcquisitionMonitor` captures Yahoo 1m evidence independently of
strategy evaluation. It watches today's frozen universes plus non-expired
dynamic-discovery candidates and persists extended-hours evidence locally.

This inverts the normal dependency:

```
Yahoo acquisition -> durable local tape -> strategy evaluation
                                  |
                                  +-> exact repair only when necessary
```

**Exit gate:** active-universe capture succeeds without invoking a strategy
monitor.

## Phase 3 — canonical Yahoo 1m tape

**Implemented.**

For Yahoo intraday evidence the order is:

1. ordinary Yahoo 1m response;
2. durable Yahoo 1m evidence already observed;
3. fresh exact-range Yahoo 1m repair when causally permitted;
4. deduplicate/revision-resolve the complete Yahoo 1m union;
5. aggregate the canonical 1m tape once to 3m/5m/15m/1h;
6. only then consider partial-market fallback for still-missing buckets.

Complementary 1m evidence is therefore allowed to complete one higher-timeframe
bucket before aggregation.

No synthetic OHLCV values are created.

**Exit gate:** a 5m candle can be reconstructed from complementary factual Yahoo
1m observations without invoking IEX or fabricating bars.

## Phase 4 — shared recovery service

**Implemented.**

The shared `TradingMarketDataService.recovered_bars()` is the provider-recovery
authority for live U.S.-equity strategy consumers.

The main strategy monitor, Stoch, AI Shadow v3, legacy/v2/deep shadow consumers,
post-entry protection indicators, and prospective outcome scoring route through
the shared boundary. Lightweight legacy test doubles may still fall back to
their historical `bars()` interface.

Post-horizon outcome scoring explicitly uses `retroactive_research`; live
protection and strategy decisions use `live`.

**Exit gate:** production market-service consumers no longer own independent
Yahoo->IEX recovery ladders.

## Phase 5 — feature-local qualification

**Implemented.**

The legacy `candidate.market_data_complete` Boolean is diagnostic rather than a
trade-wide authority gate.

Feature requirements declare dependency classes:

- point-in-time;
- rolling window;
- session cumulative;
- session extrema;
- baseline dependent;
- recursive;
- event sequence.

Old gaps can heal once they leave a rolling window. Recursive state can only
resume under an explicit reseed policy. Session-wide features remain invalid
when an unresolved dependency crosses their required window.

Gap-pullback deliberately remains session-sensitive because its opening
structure, session VWAP, and volume sequence genuinely depend on session
evidence. It is now blocked by an explicit session OHLCV certificate rather than
a generic day-level completeness Boolean.

**Exit gate:** a strategy is blocked only when one of its declared feature
certificates is invalid.

## Phase 6 — recursive and strategy migration

**Implemented.**

Stoch RSI uses explicit recursive qualification and may resume only after its
declared clean reseed interval. AI v3 trigger features continue to use their own
session/rolling certificates. Shared recovery feeds the remaining shadow arms.

**Exit gate:** tests cover recursive reseed, rolling-window recovery, and
session-wide fail-closed behavior.

## Phase 7 — coverage-qualified Yahoo-relative liquidity

**Implemented.**

Yahoo TOD RVOL is versioned provider-relative evidence. The feature is named
explicitly as `YAHOO_RELATIVE_VOLUME`; it is never presented as SIP or
consolidated U.S.-market volume. Numerator and historical denominator are Yahoo
observations at the same clock cutoff.

Historical sessions only enter the baseline when their premarket window meets
the configured minimum coverage ratio (default 90%). Incomplete historical
sessions are counted and rejected rather than silently depressing the
denominator.

This must never be presented as consolidated U.S.-market RVOL.

**Exit gate:** an incomplete historical session cannot inflate Yahoo-relative
RVOL.

## Phase 8 — provider resilience

**Implemented.**

The provider HTTP runtime includes:

- bounded concurrency;
- retry with exponential backoff;
- Retry-After handling;
- 429/5xx classification;
- provider circuit breaker/cooldown;
- identical-request single-flight/coalescing;
- cancellation;
- runtime health telemetry.

Yahoo acquisition and exact repair share this runtime, preventing multiple
strategy loops from multiplying one upstream outage.

**Exit gate:** concurrent identical Yahoo requests produce one upstream request;
repeated failures open the circuit and suppress amplification.

## Phase 9 — halt/no-trade semantics

**Implemented.**

Missing intervals are separated into:

- unresolved provider/data gaps;
- independently confirmed full-interval halts/non-trading;
- unresolved market state.

The Alpaca status stream may confirm a halt interval only when its status history
is authoritative for the interval. Yahoo absence alone can never prove a halt.

Confirmed halt intervals may satisfy a dependency without creating a fake
zero-volume candle.

**Exit gate:** confirmed halts disappear from the unresolved dependency set while
the canonical bar tape remains unchanged.

## Phase 10 — durable observability

**Implemented.**

Yahoo evidence diagnostics are persisted under the evidence root and survive
process restarts. Metrics include:

- persisted/load counts;
- acquisition attempts/success/failure/symbol counts;
- exact-repair attempts and successes;
- repaired bar count;
- unresolved repair count;
- Yahoo RVOL baseline hit/miss counts;
- causal replay rejection count;
- strategy-level repaired/unresolved evaluation counts;
- provider runtime circuit state.

Interprocess file locking protects evidence-file updates.

**Exit gate:** daily diagnostics can distinguish acquisition failure, recovery
failure, causal rejection, policy rejection, and successful rescue.

## Phase 11 — prospective soak and promotion gate

**Instrumentation implemented; prospective elapsed-session gate remains open.**

The runtime now persists one session-scoped soak record per U.S.-equity date
under `resources/trading/yahoo_evidence/sessions/YYYY-MM-DD.json`. It records
the number of Yahoo-primary evaluations observed, evaluations rescued by Yahoo
repair, evaluations that still passed, genuinely blocked evaluations, repairs
that were insufficient to unblock the feature, and blocked-reason counts. The
current session is embedded in the general diagnostics response and any stored
session can be retrieved from
`GET /api/trading/market-data/yahoo-evidence/diagnostics/{session_date}`.

This completes the instrumentation needed for tomorrow's measurement without
pretending that future prospective sessions have already occurred. Before
strategy conclusions or AUTO PAPER promotion, multiple prospective sessions
must still satisfy:

- no unexplained global `DATA_INCOMPLETE` veto may remain;
- every skipped evaluation must identify the exact invalid feature/provider
  dependency;
- causal replay must remain free of post-decision evidence;
- provider outages must degrade locally rather than create request storms;
- repaired evaluations and unresolved evaluations must be measurable separately;
- strategy parameters remain frozen during the soak.

Only after these data-layer gates are stable should trading-performance changes
be attributed to the strategies themselves.

## Persistent evidence

Finalized Yahoo 1m bars are stored under
`resources/trading/yahoo_evidence` by default. The location can be changed with
`OMNIX_TRADING_YAHOO_EVIDENCE_DIR`.

Writes use atomic replacement plus an interprocess advisory lock. Evidence is
independent of the disposable market-data cache.

## Diagnostics endpoints

`GET /api/trading/market-data/yahoo-evidence/diagnostics` exposes durable Yahoo
evidence/recovery metrics. Provider descriptors also expose retry/circuit health.

`GET /api/trading/strategy-operations/yahoo-acquisition-status` exposes the
live proactive-acquisition monitor state: enabled/registered/running, last run
and error, capture/error counts, active-symbol count, and its explicit
non-execution authority.

## Non-goals

This work does not:

- claim Yahoo is SIP;
- treat IEX volume as consolidated volume;
- weaken live spread/quote/fill checks;
- manufacture bars for halts;
- change strategy thresholds to create more trades;
- rewrite frozen prospective forecasts after the fact.
