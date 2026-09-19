# IBKR Market-Data Integration

Status: **implemented in zero-authority observation mode by default**.

## Authority boundaries

IBKR is a `LIVE_DATA` provider only. It does not expose order-placement methods and
an `ibkr:*` binding cannot be promoted to `EXECUTION` purpose. Brokerage/order
execution authority is absent from this integration phase.

Provider roles are intentionally independent:

- discovery: Finviz
- canonical historical 1-minute evidence: Yahoo durable/current evidence
- preferred live quotes: IBKR only when the contract is uniquely qualified, the Gateway is connected, the quote is fresh, market-data type is `LIVE`, live entitlement is explicitly proven, required quote fields are present, and the rollout gate is enabled
- live fallback: Alpaca IEX only when the requesting feature explicitly permits partial-market evidence
- factual gap repair: Yahoo exact-range, then IBKR exact-range when recovery authority is enabled, then IEX where feature semantics allow it
- halt/no-trade status: independent Alpaca status evidence
- paper-fill observation: existing execution-purpose Alpaca observation plane

## Omnix settings

Configure IBKR from **Settings -> Trading & Market Data -> Interactive Brokers
(IBKR)**. Omnix persists the non-secret connection settings and applies them to
the runtime without requiring manual environment variables or a restart:

- enabled, monitor enabled, Gateway host, socket port, and client ID
- live-data authority and recovery authority rollout switches (both off by default)

Omnix never stores an IBKR username, password, or API secret. Authentication
remains in the local IB Gateway session. The settings panel reports whether the
official `ibapi` package is installed, whether the socket is connected, the
effective settings source, and the last connection error.

Legacy environment variables remain a fallback until an Omnix IBKR settings
section is saved:

- `OMNIX_IBKR_ENABLED=1` enables the provider/runtime.
- `OMNIX_IBKR_LIVE_AUTHORITY=1` permits IBKR to become `LIVE_DATA` authority after every per-contract readiness condition passes.
- `OMNIX_IBKR_RECOVERY_AUTHORITY=1` permits IBKR historical bars to enter the canonical recovered tape. Without it, recovery is observation-only.
- `OMNIX_IBKR_MONITOR=1` enables the shared demand/quote monitor.

The default is fail-closed: provider enabled does not imply live authority, and a healthy Gateway does not imply per-contract entitlement.

The official IBKR Python client is installed in Omnix's virtual environment from
the official TWS API package. Verify it with:

`venv\\Scripts\\python.exe -m pip show ibapi`

## Feed semantics

Every recovered canonical bucket retains field-level source semantics. Mixed Yahoo/IBKR price evidence requires explicit feature permission. Mixed-provider volume is independently gated, and IBKR recovered volume is classified conservatively as `UNKNOWN` volume scope, so it cannot silently authorize RVOL, VWAP, cumulative-volume, or other feed-sensitive calculations.

Causal replay never performs fresh network repair. Retroactive repair therefore cannot rewrite a historical decision.

## Contract identity

Stocks are requested as SMART/USD templates but are qualified through contract details before use. A canonical cached identity retains `conId`, local symbol, primary exchange, currency, trading class, and resolved metadata. Ambiguous contracts fail closed.

## Streaming ownership

`TradingIbkrMarketDataMonitor` is the sole IBKR subscription owner. Demand is deduplicated through `SharedSubscriptionManager`; the execution-observation monitor owns only execution-purpose polling. IBKR snapshots are bridged into the existing causal observation plane with market-data type, entitlement, contract identity, and provider sequence preserved.

## Runtime diagnostics and pacing

The runtime serializes connection attempts, applies reconnect backoff, tracks Gateway reconnects, request-specific errors, entitlement denials, and IBKR farm health, and paces historical requests. Historical recovery coalesces adjacent missing ranges rather than requesting one minute at a time.

## Prospective acceptance

Do not enable either authority flag merely because a socket connects. Keep trading parameters frozen and observe multiple live sessions. Durable session records are written under:

`resources/trading/ibkr_evidence/sessions/YYYY-MM-DD.json`

Acceptance review should include:

- live vs delayed/frozen/unknown market-data state
- entitlement failures and missing quote events
- quote-age and spread distributions
- IBKR vs IEX last-price/spread differences when both are causally available
- contract qualification failures
- subscription counts and reconnect behavior
- a deliberate Gateway disconnect/restart
- Yahoo gaps recoverable by IBKR versus actually admitted after the recovery gate
- whether IBKR recovery reduced unresolved dependencies

The operator endpoints are:

- `/api/trading/market-data/providers/ibkr/diagnostics`
- `/api/trading/market-data/providers/ibkr/settings`
- `/api/trading/market-data/providers/ibkr/diagnostics/{session_date}`
- `/api/trading/market-data/providers/ibkr/authority/{instrument_id}`

Promotion remains a separate operational decision after the soak is reviewed.
