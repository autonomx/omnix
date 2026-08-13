# Omnix Trading Server Alerts

OTT-10 introduces persisted, backend-evaluated alerts for normalized Trading datasets.

## Authority

Alert definitions live in `omnix_trading_alerts`. Trigger history lives in `omnix_trading_alert_triggers`. Generic module records, browser storage, and open chart sessions are not alert authority.

Each alert owns:

- canonical `instrument_id`;
- optional requested provider `binding_id`;
- condition type and bounded parameters;
- interval, partial/final-bar policy, and formula version;
- threshold, cooldown, revision, last observed condition value, and last trigger time.

## Supported conditions

- price above or below;
- percent change above or below over a bounded bar lookback;
- indicator threshold/crossing above or below for SMA, EMA, RSI, MACD, Bollinger Bands, ATR, or anchored VWAP;
- volume above or below.

All conditions use restart-safe crossing semantics. The first usable observation establishes a baseline and does not trigger. A later value must cross the threshold from the opposite side. Cooldown is evaluated against server evaluation time.

Finalized bars are the default authority. Partial bars are ignored unless `allow_partial_bars` is explicitly enabled on the alert. Indicator alerts are pinned to `omnix-indicators-v2`, the same formula version used by charts, replay, and backtests.

## Transaction and deduplication

Evaluation locks matching alert rows and writes each trigger plus the new observed state in one transaction. Every trigger has a deterministic idempotency key derived from alert, condition, source time, and observed condition value. Retries and concurrent gateway workers cannot create duplicate trigger records.

Trigger records and UI notifications identify:

- instrument and condition;
- observed value, observed price, and threshold;
- actual provider and resolved feed binding;
- requested binding when fallback occurred;
- source timestamp and evaluation timestamp;
- formula and evaluation policy metadata.

## Backend monitor

The Omnix gateway starts a Trading alert monitor during startup and stops it during shutdown. It groups enabled alerts by instrument, requested feed, and interval; requests one bounded normalized bar dataset per group; computes percent change and versioned indicators; and evaluates all matching alerts server-side. Closing the browser does not stop evaluation.

The default interval is 30 seconds and can be changed with `OMNIX_TRADING_ALERT_INTERVAL_SECONDS` (minimum 5 seconds). `OMNIX_TRADING_ALERT_MONITOR=0` disables production monitoring. In `legacy_test` persistence mode the monitor is disabled unless `OMNIX_TRADING_ALERT_MONITOR_IN_TESTS=1` is explicitly set.

## API

- `GET /api/trading/alerts`
- `POST /api/trading/alerts`
- `PUT /api/trading/alerts/{alert_id}` with `If-Match`
- `DELETE /api/trading/alerts/{alert_id}` with `If-Match`
- `GET /api/trading/alerts/triggers`
- `POST /api/trading/alerts/evaluate` for controlled ingestion and deterministic tests

The browser manages definitions and reads trigger history. It never decides whether a condition fired.
