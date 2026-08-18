# Alpaca IEX paper-execution feed

Omnix uses a split-source equity-data architecture:

- **Yahoo** remains the discovery, charting, and historical-bar source.
- **Alpaca IEX** is the authoritative real-time quote source for US-equity paper execution.
- **Yahoo is never allowed to authorize a paper fill.** If Alpaca credentials are absent, unavailable, stale, future-dated, bookless, over-wide, session-ineligible, or carrying a known trading halt, paper execution fails closed.

## Why IEX

Alpaca Basic / Paper Only accounts provide free real-time IEX market data. IEX is only a partial view of US equity trading and must not be represented as consolidated SIP/NBBO coverage. Omnix records the execution provider as `alpaca_iex` so paper results can be distinguished from future full-market feeds.

This feed is suitable for free real-time paper-execution testing, not for claiming live-fill equivalence. Low-float and fast-moving gappers can trade materially differently on the consolidated market.

## Credentials

Create an Alpaca Paper Only account and generate market-data API credentials. Configure the Omnix process with:

```text
OMNIX_ALPACA_API_KEY_ID=<paper API key>
OMNIX_ALPACA_API_SECRET_KEY=<paper API secret>
```

The standard Alpaca environment names are also accepted as fallbacks:

```text
APCA_API_KEY_ID=<paper API key>
APCA_API_SECRET_KEY=<paper API secret>
```

Do not commit either credential to the repository.

The data API base URL defaults to:

```text
https://data.alpaca.markets
```

For controlled testing it may be overridden with:

```text
OMNIX_ALPACA_DATA_URL=<alternate base URL>
```

The optional IEX trading-status WebSocket defaults to:

```text
wss://stream.data.alpaca.markets/v2/iex
```

It may be disabled with `OMNIX_ALPACA_STATUS_STREAM=0` or redirected in a controlled test environment with `OMNIX_ALPACA_STREAM_URL`.

## Runtime behavior

For an equity whose chart or frozen strategy universe uses a Yahoo binding, `ProviderRegistry.execution_observation(...)` resolves the execution request to the corresponding Alpaca IEX binding. The returned observation preserves the requested paper-order binding for compatibility while the `provider` field is `alpaca_iex`, proving where the executable quote came from.

The adapter requests Alpaca's stock snapshot endpoint with `feed=iex` and normalizes:

- best bid and ask;
- displayed bid and ask size, converted from round lots to shares;
- latest trade;
- quote/trade timestamps;
- current minute high/low/volume and start time when present;
- cumulative daily volume for diagnostics only;
- recurring US-equity session classification, including standard holidays and early closes;
- trading-halt evidence from the Alpaca IEX status stream when observed.

`execution-data-v1` then applies. Missing bid/ask, stale data, source timestamps beyond the future-skew tolerance, excessive spreads, closed sessions, or known halts reject the observation. No Yahoo/reference-price fallback is permitted.

## Liquidity model

Cumulative daily volume is **never** treated as immediately executable liquidity.

For a live paper fill, `paper-execution-v2` uses the displayed size on the side that the order would consume:

- buy → displayed ask size;
- sell → displayed bid size.

The configured participation percentage is applied to that displayed size. When running a historical backtest, where a real-time quote book is unavailable, the same fill engine falls back to the individual one-minute bar's volume.

This is deliberately conservative and keeps live and historical volume evidence semantically distinct.

## Protection triggers

The snapshot's current-minute range can help observe a fast stop/target touch between monitor polls. Manual paper protection, automated strategy protection and backtests call the same pessimistic stop-before-target helper.

A live minute high/low is used only when the minute began at or after protection activation. If the entry filled during the current minute, the bar may contain pre-entry prices, so Omnix falls back to the current executable price until a fully post-entry minute exists.

## Trading status

When credentials are configured, the gateway can subscribe to Alpaca's IEX trading-status channel. A known halt makes the execution observation ineligible. A known halt remains fail-closed across a stream disconnect. A previously observed resume is treated as affirmative only while the stream is connected, because a later halt could otherwise have been missed.

The recurring US-equity calendar handles ordinary holidays and standard early closes; the provider status stream handles symbol-specific trading halts and other provider status events. Neither mechanism turns missing evidence into permission to bypass normal quote freshness checks.

## Yahoo discovery

`POST /api/trading/strategies/universes/discover-yahoo` performs current-only Yahoo top-gainer discovery and immediately freezes the resulting point-in-time universe. The server will not use that route to reconstruct a prior day's screener after the fact.

Discovery records observation timestamps and calculates premarket/current gap evidence plus time-of-day relative volume using prior sessions truncated at the same New York clock minute. Missing secondary evidence is retained as missing rather than removing a candidate from the universe.

## Rate-limit considerations

Execution quotes currently use REST snapshots because the existing paper monitor consumes one normalized observation at a time. Keep the number of simultaneously open paper orders/protections bounded. The trading-status channel is a separate low-volume WebSocket used for halt/resume evidence.

A future optimization can batch quote snapshots or consume Alpaca's quote/trade WebSocket while preserving the same normalized `ExecutionObservation` contract.

## Upgrade path

A future consolidated SIP provider can replace the `alpaca_iex` execution binding without changing strategy logic or the paper fill engine. Comparative paper results should retain provider identity so IEX-vs-SIP execution differences can be measured rather than assumed.
