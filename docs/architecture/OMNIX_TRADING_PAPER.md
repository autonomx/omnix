# Omnix Trading Paper Simulation

OTT-13 provides local paper simulation only. It does not contain a brokerage client, broker credentials, a live-order route, or an automated AI order path.

## Authority

PostgreSQL is authoritative through dedicated tables for:

- accounts
- balances
- canonical-instrument positions
- simulated orders
- fills
- ledger entries

Paper positions reference canonical `instrument_id` values. A provider binding may constrain how an open order is evaluated, but it does not own the position.

## Supported orders

The initial simulation supports:

- Market
- Limit
- Stop
- Buy and sell
- Positive quantities only
- Long positions only

Limit and stop prices are required only for their corresponding order type. Market orders reject limit or stop fields.

## Buying-power and position reservations

Open orders reserve resources transactionally so multiple pending orders cannot spend the same buying power or sell the same position twice.

- Limit and stop BUY orders reserve trigger-price notional plus the configured commission.
- A MARKET BUY has no authoritative placement price, so it conservatively reserves all currently free cash until the next normalized observation fills or rejects the order.
- SELL orders reserve their requested quantity from the canonical-instrument position.
- Cancellation, rejection, and successful fill release or consume the corresponding reservation atomically.
- Account snapshots expose free and reserved cash, while position snapshots expose reserved quantity.

An idempotency-key retry is accepted only when the semantic order payload matches the original order. Reusing a key with a different order ID, instrument, binding, side, type, quantity, limit price, or stop price fails with `paper_idempotency_payload_mismatch` instead of silently returning an unrelated prior order.

## Fill and accounting behavior

The gateway paper monitor groups open orders by instrument and requested feed, obtains one normalized observation per group, and evaluates all affected accounts while the browser is closed.

Market orders fill at the observation price. Limit and stop simulation uses the observation range when high/low values are available:

- BUY limit: triggered when `low <= limit_price`;
- SELL limit: triggered when `high >= limit_price`;
- BUY stop: triggered when `high >= stop_price`;
- SELL stop: triggered when `low <= stop_price`.

Triggered limit/stop orders fill deterministically at their configured limit/stop price. If high/low are unavailable, the current observation price is used as both ends of the evaluation range, preserving the previous quote-only behavior.

For a fill, the repository locks account, balance, position, and open-order rows. The fill, reservation release/consumption, cash balance, position, order status, and ledger entries commit in one transaction. Fill and ledger idempotency keys prevent duplicate accounting during retries or concurrent gateway workers.

Existing positions are marked to the latest normalized observation even when an open order does not fill. Realized and unrealized P&L use persisted fills, average cost, and persisted marks.

## Lifecycle

Reset and archive are explicit revisioned operations:

- Reset removes simulated orders, fills, positions, balances, and prior ledger state, creates a new starting balance, records an explicit reset deposit, re-enables the account, and increments its revision.
- Archive disables the account, cancels open orders, and increments its revision without deleting historical fills or ledger evidence.
- Stale reset or archive requests return a revision conflict.

## Runtime controls

- `OMNIX_TRADING_PAPER_MONITOR=0` disables production monitoring.
- `OMNIX_TRADING_PAPER_INTERVAL_SECONDS` controls the polling interval, with a five-second minimum.
- In `legacy_test` mode the monitor remains disabled unless `OMNIX_TRADING_PAPER_MONITOR_IN_TESTS=1` is set.

The UI labels this area **Paper simulation** and **No live brokerage execution**. All order actions use `/api/trading/paper/...`; no live execution namespace exists.
