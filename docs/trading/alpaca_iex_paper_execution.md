# Alpaca IEX paper-execution feed

Omnix uses a split-source equity-data architecture:

- **Yahoo** remains the discovery, charting, and historical-bar source.
- **Alpaca IEX** is the authoritative real-time quote source for US-equity paper execution.
- **Yahoo is never allowed to authorize a paper fill.** If Alpaca credentials are absent, unavailable, stale, or otherwise fail the execution policy, paper execution fails closed.

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

## Runtime behavior

For an equity whose chart or frozen strategy universe uses a Yahoo binding, `ProviderRegistry.execution_observation(...)` resolves the execution request to the corresponding Alpaca IEX binding. The returned observation preserves the requested paper-order binding for compatibility while the `provider` field is `alpaca_iex`, proving where the executable quote came from.

The adapter requests Alpaca's stock snapshot endpoint with `feed=iex` and normalizes:

- best bid;
- best ask;
- latest trade;
- quote/trade timestamps;
- current daily volume;
- regular / extended-hours session classification.

The normal `execution-data-v1` policy then applies. Missing bid/ask, stale data, closed sessions, excessive spreads, or unavailable credentials reject the observation. No Yahoo/reference-price fallback is permitted.

## Rate-limit considerations

The implementation currently uses REST snapshots because the existing paper monitor consumes one normalized observation at a time. Keep the number of simultaneously open paper orders/protections bounded. A future optimization can batch symbols or use Alpaca's WebSocket IEX stream while preserving the same normalized `ExecutionObservation` contract.

## Upgrade path

A future consolidated SIP provider can replace the `alpaca_iex` execution binding without changing strategy logic or the paper fill engine. Comparative paper results should retain provider identity so IEX-vs-SIP execution differences can be measured rather than assumed.
