# Omnix Trading Provider Expansion

OTT-8 adds provider/feed bindings without changing canonical instrument identity.

- Binance remains the live REST/WebSocket provider for Binance spot instruments.
- Yahoo-derived equities are experimental, unofficial, personal/local-use only, and availability is not guaranteed.
- Stooq is an eligible whole-dataset fallback for daily equity history; datasets are never spliced across providers.
- Coinbase, Kraken, and Hyperliquid use venue-specific normalized REST adapters.
- Watchlists, drawings, alerts, and later paper positions remain owned by canonical `instrument_id`; selecting a feed changes only `binding_id` and dataset provenance.
- WebSocket streaming is enabled only for bindings that declare `websocket_and_rest`; other bindings use bounded polling.

The OTT-8 gate includes fixture-driven provider normalization, complete-dataset fallback, binding validation, API routing, and frontend persistence tests.
