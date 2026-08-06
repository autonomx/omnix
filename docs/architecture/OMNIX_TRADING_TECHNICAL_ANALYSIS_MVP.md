# Omnix Trading Technical Analysis MVP

OTT-9 qualifies the Technical Analysis MVP on top of the provider-neutral charting foundation.

## Included

- One, horizontal split, vertical split, and four-chart layouts.
- Candlestick, OHLC bar, line, area, and baseline chart types.
- Versioned `omnix-indicators-v2` formulas for SMA, EMA, RSI, MACD, Bollinger Bands, Wilder ATR, and anchored VWAP.
- Shared TypeScript/Python golden fixtures for every advanced formula.
- Horizontal, vertical, trend, ray, rectangle, Fibonacci, text, and measurement drawings.
- Time/price authority, snapping, styling, locking, hiding, selection, delete, undo, and redo.
- Revisioned PostgreSQL indicator presets.
- Per-chart PNG snapshots and portable JSON workspace export.

## Qualification gates

- Indicator outputs match the same checked-in fixtures in TypeScript and Python.
- Saved pre-OTT-9 workspaces migrate without losing instrument, binding, interval, chart, or link ownership.
- Drawing tests reject pixel authority and verify lock, visibility, style, snapping, and history behavior.
- Export tests verify that runtime functions, sockets, and provider payloads are excluded.
- Trading-only frontend tests and TypeScript compilation must pass on the exact PR head.
