# Omnix Trading Replay and Backtest

OTT-12 introduces immutable replay datasets and deterministic strategy backtests.

## Frozen dataset contract

A dataset snapshot contains finalized normalized bars plus:

- canonical instrument;
- requested and resolved provider binding;
- provider;
- dataset fingerprint and source `as_of` time;
- adjustment mode;
- session calendar and exchange timezone;
- explicit `fail` or `skip` gap policy;
- interval and immutable bar sequence.

The fingerprint is recomputed during model validation. Changed metadata or bars invalidate the snapshot. Replay and backtest modules accept `FrozenDatasetSnapshot`; neither imports a provider or market-data service.

## Replay

`ReplayClock` provides pause, play, speed, reset, and deterministic step operations. Every event has a stable sequence number, replay timestamp, and frozen bar. The clock cannot accept live bars or provider corrections.

## Backtest

The initial strategy is an SMA cross using `omnix-indicators-v2`. Execution policy is explicit:

- decisions are evaluated after a finalized bar closes;
- orders fill only at the next bar open;
- commission and slippage are deterministic basis-point inputs;
- position sizing is bounded by available cash;
- short selling is rejected;
- no provider or network access exists in the run path.

Every run exposes and persists the economic ending state:

- `ending_cash`;
- `ending_position`;
- `ending_mark_price`;
- `realized_pnl`;
- `unrealized_pnl`;
- `final_equity` and return/drawdown metrics;
- `mark_to_market_policy`;
- `economic_result_fingerprint`.

The current mark-to-market policy is `final_finalized_bar_close`. Any open long position at the end of the frozen dataset is valued at the close of the final finalized bar. Realized P&L includes entry and exit commissions for completed round trips. Unrealized P&L is the final marked value of an open position minus its remaining commission-inclusive cost basis. Therefore `realized_pnl + unrealized_pnl` reconciles to `final_equity - initial_cash` for a completed run.

The economic-result fingerprint is SHA-256 over deterministic economic evidence: dataset fingerprint, strategy parameters, execution policy, formula version, economic ending state, aggregate metrics, trade economics, and equity-curve economics. It deliberately excludes run IDs, dataset storage IDs, wall-clock run timestamps, artifact paths, and BlobStore metadata. Two economically identical runs therefore produce the same fingerprint even when executed as separate runs.

Every run persists the dataset fingerprint, strategy parameters, execution policy, formula version, status, economic ending state, return, drawdown, trades, equity curve, and logs in dedicated PostgreSQL tables. Large immutable run output may also be stored in BlobStore with checksum verification.

## API

- `POST /api/trading/replay/datasets`
- `GET /api/trading/replay/datasets`
- `GET /api/trading/replay/datasets/{dataset_id}`
- `POST /api/trading/replay/backtests`
- `GET /api/trading/replay/backtests`
- `GET /api/trading/replay/backtests/{run_id}`

Provider access occurs only while freezing a new dataset. A backtest loads an already persisted snapshot and cannot request market data.

## Qualification

The phase gate validates fingerprint tamper detection, immutable bars, fail/skip gap policies, replay pause/speed/step lifecycle, next-bar fill timing, complete persistence tables, and structural absence of provider/network dependencies in the backtest engine.

Backtest economics qualification additionally requires:

- ending cash and position equal the final equity-curve state;
- the disclosed ending mark equals the final finalized bar close;
- realized plus unrealized P&L reconciles to total economic P&L;
- repeated runs with different run IDs/wall-clock timestamps produce the same economic-result fingerprint when economic inputs/results are identical;
- changing commission, slippage, strategy parameters, or the frozen dataset changes the fingerprint when it changes economic evidence.
