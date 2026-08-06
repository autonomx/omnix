# Omnix Trading Server Alerts

OTT-10 introduces persisted, backend-evaluated price alerts.

## Authority

Alert definitions live in `omnix_trading_alerts`. Trigger history lives in `omnix_trading_alert_triggers`. Generic module records, browser storage, and open chart sessions are not alert authority.

## Evaluation semantics

- Conditions are `price_above` and `price_below`.
- The first observation establishes a baseline and does not trigger.
- A trigger is emitted only when the price crosses the threshold from the opposite side.
- Cooldown is evaluated against the server observation timestamp.
- Evaluation locks matching alert rows and writes the trigger plus the new observation in one transaction.
- Every trigger has a deterministic idempotency key; retries and concurrent gateway workers cannot create duplicate trigger records.
- Alerts retain canonical `instrument_id` ownership and optionally pin a provider `binding_id`.

## Backend monitor

The Omnix gateway starts a Trading alert monitor during startup and stops it during shutdown. It groups enabled alerts by instrument/feed, requests one quote per unique group, and evaluates all matching alerts server-side. The default interval is 30 seconds and can be changed with `OMNIX_TRADING_ALERT_INTERVAL_SECONDS` (minimum 5 seconds).

`OMNIX_TRADING_ALERT_MONITOR=0` disables production monitoring. In `legacy_test` persistence mode the monitor is disabled unless `OMNIX_TRADING_ALERT_MONITOR_IN_TESTS=1` is explicitly set.

## API

- `GET /api/trading/alerts`
- `POST /api/trading/alerts`
- `PUT /api/trading/alerts/{alert_id}` with `If-Match`
- `DELETE /api/trading/alerts/{alert_id}` with `If-Match`
- `GET /api/trading/alerts/triggers`
- `POST /api/trading/alerts/evaluate` for controlled ingestion and deterministic tests

The browser manages definitions and reads trigger history. It never decides whether a condition fired.
