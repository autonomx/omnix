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

Every run persists the dataset fingerprint, strategy parameters, execution policy, formula version, status, return, drawdown, trades, equity curve, and logs in dedicated PostgreSQL tables.

## API

- `POST /api/trading/replay/datasets`
- `GET /api/trading/replay/datasets`
- `GET /api/trading/replay/datasets/{dataset_id}`
- `POST /api/trading/replay/backtests`
- `GET /api/trading/replay/backtests`
- `GET /api/trading/replay/backtests/{run_id}`

Provider access occurs only while freezing a new dataset. A backtest loads an already persisted snapshot and cannot request market data.

## Qualification

The phase gate validates fingerprint tamper detection, immutable bars, fail/skip gap policies, replay pause/speed/step lifecycle, repeated economic output equality, next-bar fill timing, complete persistence tables, and structural absence of provider/network dependencies in the backtest engine.
