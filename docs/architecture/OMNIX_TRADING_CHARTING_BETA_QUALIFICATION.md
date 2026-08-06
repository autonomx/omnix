# Omnix Trading Crypto Charting Beta Qualification

## Qualified scope

The Charting Beta is intentionally crypto-only:

- Binance spot historical and normalized live bars;
- one- and four-chart layouts;
- active-chart ownership and independent link controls;
- timestamp-based crosshair and visible-range synchronization;
- shared browser and backend stream ownership;
- revisioned PostgreSQL workspaces, watchlists, and drawings;
- SMA, EMA, and RSI using `omnix-indicators-v1` golden fixtures in TypeScript and Python;
- horizontal and trend lines with create, select, resize, delete, persistence, undo, and redo;
- exact reconnect gap detection and ingestion-revision correction ordering.

Yahoo, Stooq, equities, advanced drawings, and additional providers remain outside this gate.

## Automated evidence

The dedicated `Omnix Trading terminal gates` workflow validates on every exact PR head:

- provider-neutral architecture and no MCP/file-authority boundary;
- Binance pagination, duplicate removal, cache/coalescing, quotes, normalized WebSockets, and exact recovery ranges;
- four deterministic 5,000-bar datasets with three indicators each;
- synthetic crosshair fan-out p95 below 32 ms;
- ten reconnect/correction cycles without finalized-bar duplicates;
- one upstream socket/subscription for identical requests;
- lifecycle cleanup contracts;
- drawing coordinate and undo/redo invariants;
- PostgreSQL revision conflicts;
- Trading-only TypeScript compilation.

## Operational evidence

Long-duration browser heap snapshots, GPU/browser-specific rendering latency, live Binance outage behavior, and visual inspection remain local operator evidence. They are not fabricated in hosted CI. The exact-head workflow must be green before Beta is considered implementation-complete, and local release qualification is repeated before a packaged release.

## Release boundary

Passing OTT-7 unlocks experimental equities and the Technical Analysis MVP. Alerts, scanners, backtesting, paper simulation, and AI research remain gated by their later milestones. No live brokerage execution path exists.
