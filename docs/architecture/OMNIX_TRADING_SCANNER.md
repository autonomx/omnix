# Omnix Trading Bounded Scanner

OTT-11 adds a backend-owned, persisted scanner for explicit research universes.

## Hard bounds

A scanner definition is rejected unless it satisfies all of the following:

- 1–200 unique canonical instruments in an explicit allowlist;
- bindings only for instruments already in that allowlist;
- one explicit interval per definition;
- 2–500 finalized historical bars per instrument;
- 1–20 rules;
- 1–8 concurrent provider requests;
- 1–30 seconds per request;
- 1–300 seconds total runtime;
- `omnix-indicators-v2` formula version.

There is no whole-market or open-ended discovery mode.

## Supported metrics

- final close;
- percent change over a bounded bar lookback;
- final volume;
- SMA, EMA, RSI, and Wilder ATR.

All formulas use the same Python indicator engine and formula version as charts, alerts, replay, and backtests.

## Persistence and provenance

Dedicated PostgreSQL tables store scanner definitions, immutable run snapshots, run lifecycle/progress, and ranked results. Every result records:

- canonical instrument;
- requested and resolved provider binding;
- provider;
- dataset fingerprint and source `as_of` time;
- formula version;
- calculated metrics and matched rule IDs;
- deterministic rank and score.

The definition snapshot stored on each run contains the exact metric, period/lookback, operator, threshold, limits, and allowlist used to derive those results.

## Execution

Runs are started asynchronously by the gateway. A semaphore enforces definition concurrency, `asyncio.wait_for` enforces request and total deadlines, and each active run owns a cooperative cancellation token. Definitions, runs, and results remain queryable after the browser closes.

## API

- `GET /api/trading/scanners`
- `POST /api/trading/scanners`
- `PUT /api/trading/scanners/{scanner_id}` with `If-Match`
- `POST /api/trading/scanners/{scanner_id}/runs`
- `GET /api/trading/scanners/runs`
- `POST /api/trading/scanners/runs/{run_id}/cancel`
- `GET /api/trading/scanners/runs/{run_id}/results`

## Qualification

The phase gate scans 50 deterministic fixture instruments, verifies no more than four concurrent requests for a four-worker definition, rejects universes over 200 and invalid bindings, validates cancellation and timeout outcomes, and proves persisted API definitions/runs/results retain dataset provenance.
