# Omnix Trading Operations Runbook

## Runtime ownership

Trading runs inside the shared Omnix gateway and web application. Do not start a separate prototype FastAPI or Vite workstation.

Gateway lifecycle services:

- Trading market-data REST and WebSocket routes
- server alert monitor
- bounded scanner manager
- replay/backtest routes
- paper simulation monitor
- read-only AI research route

## Environment controls

### Alert monitor

- `OMNIX_TRADING_ALERT_MONITOR=0` disables production alert monitoring.
- `OMNIX_TRADING_ALERT_INTERVAL_SECONDS` controls the polling interval with a five-second minimum.
- In `legacy_test` mode, enable only with `OMNIX_TRADING_ALERT_MONITOR_IN_TESTS=1`.

### Paper monitor

- `OMNIX_TRADING_PAPER_MONITOR=0` disables paper-order monitoring.
- `OMNIX_TRADING_PAPER_INTERVAL_SECONDS` controls the polling interval with a five-second minimum.
- In `legacy_test` mode, enable only with `OMNIX_TRADING_PAPER_MONITOR_IN_TESTS=1`.

### Provider configuration

Market-data providers and the optional research model use Omnix provider configuration. Do not place credentials, tokens, or base URLs in Trading workspace records, scanner definitions, research requests, or browser storage.

## Provider outage procedure

1. Open the Trading **Data** tab and record provider/stream diagnostics.
2. Confirm the selected feed, official/unofficial status, usage scope, and terms reference in the Trading footer.
3. Disable affected background monitors if repeated failures could consume rate limits.
4. Preserve the exact instrument, requested binding, resolved binding, provider, dataset fingerprint, source time, and error.
5. Do not merge partial data from two providers. A fallback replaces the complete requested dataset.
6. Restore the provider or select an allowed compatible binding.
7. Re-enable monitors and verify that retries do not duplicate alert triggers, paper fills, ledger entries, or scanner results.
8. Attach the outage/recovery evidence to the release certification record.

## Streaming recovery

- Symbol, interval, or binding changes must close the prior subscription before opening the replacement.
- Sequence gaps require deterministic REST repair before live updates continue.
- Repeated duplicate or out-of-order events should be recorded with binding and provider sequence metadata.
- Stop the Trading gateway if sockets or reconnect attempts become unbounded; do not leave a degraded reconnect loop unattended.

## PostgreSQL migrations and rollback

Trading migrations are under `src/app/persistence/migrations` and must be applied through the existing Omnix migration process.

Before upgrade:

1. Back up the database and BlobStore root.
2. Record the application commit SHA and latest applied migration.
3. Confirm sufficient disk space for datasets, scanner results, backtest evidence, paper ledger history, and artifacts.

After upgrade:

1. Verify Trading tables and constraints.
2. Restart the gateway.
3. Reload a representative workspace, alert, scanner, dataset, backtest, and paper account.
4. Verify backtest artifact checksums.
5. Confirm monitor diagnostics and absence of duplicate state changes.

Rollback must preserve Trading records and BlobStore artifacts unless a reviewed data migration explicitly removes them. Do not invent legacy signal/fill indices; pre-index backtests retain NULL sequencing evidence.

## BlobStore artifacts

Complete backtest result JSON is stored through `LocalBlobStore`. Relational PostgreSQL rows retain queryable summaries, trades, equity points, and logs.

Artifact metadata includes:

- storage provider
- storage key
- SHA-256 checksum
- byte size

On read, checksum mismatch is an integrity failure. Do not serve the corrupted artifact as valid evidence.

### Corrupt or missing artifact

1. Record the run ID, storage key, expected checksum, and error.
2. Keep relational summaries and evidence read-only.
3. Quarantine the corrupt file; do not overwrite it without preserving evidence.
4. Re-run the backtest from the same frozen dataset and strategy/execution policy.
5. Compare the new deterministic result to relational evidence.
6. Link the replacement run; do not silently mutate the original run identity.

### Orphan artifact cleanup

A BlobStore write can succeed before a database transaction fails. The runtime attempts to delete artifacts it created during a failed save. Periodic cleanup may remove unreferenced Trading artifact keys only after comparing them with PostgreSQL run metadata and preserving an audit log.

## Cache and disk cleanup

- Never delete active PostgreSQL authority records as a cache-clearing shortcut.
- Cached/fallback market data must remain distinguishable from live/polled data through provenance.
- Scanner and backtest history are evidence, not disposable browser cache.
- Before deleting local artifacts, verify that no run metadata references their storage key.

## Scanner operations

- Maximum allowlist: 200 unique instruments.
- Maximum history: 500 bars per instrument.
- Maximum concurrency: 8.
- Maximum request timeout: 30 seconds.
- Maximum run timeout: 300 seconds.
- Default formulas are versioned as `omnix-indicators-v2`.

Cancel scans that exceed provider policy or operational expectations. Do not broaden the universe dynamically beyond the stored allowlist.

## Paper simulation operations

Paper simulation is not brokerage execution.

- Market, Limit, and Stop only.
- Long positions only.
- Reset and archive require the current account revision.
- Reset deletes simulated state and records a new explicit deposit.
- Archive disables the account and cancels open orders without deleting evidence.
- Fill, cash, position, order, and ledger changes commit together under row locks.

If duplicate fills or ledger entries are suspected, stop the paper monitor and inspect idempotency keys before resuming.

## Research operations

Research is optional and read-only.

- It uses the configured Omnix provider registry.
- It accepts no credentials.
- It uses at most 200 finalized bars and a bounded context.
- Invalid model JSON is rejected; no generic narrative fallback is saved.
- It cannot place orders, create alerts, or mutate scanner/backtest/paper state.

Provider/model errors should not block charting, alerts, scanner use, replay, or paper simulation.

## Incident record

For Trading incidents record:

- commit SHA and environment;
- workspace/user scope;
- canonical instrument and binding;
- provider and policy scope;
- source and evaluation timestamps;
- dataset fingerprint or artifact checksum;
- relevant revision/idempotency key;
- diagnostics output;
- remediation and validation result.
