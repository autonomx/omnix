# Omnix Trading Terminal Implementation Roadmap

**Status:** Proposed for review  
**Target route:** `/trading`  
**Target module name:** `Trading`  
**Roadmap branch:** `agent/trading-terminal-roadmap`  
**Reference prototype:** `autonomxDeveloper/tradingview-mcp`  
**Reference UI direction:** Omnix-native dark multi-chart workstation with chart tools, watchlist, side panels, and an optional bottom activity drawer

## Program objective

Build a native Omnix market-analysis workspace that provides a credible TradingView-style charting experience for stocks and crypto using free or openly accessible market-data sources.

The first production milestone must support multiple charts, synchronized navigation, real chart drawings, core technical indicators, watchlists, saved workspaces, historical candles, and live crypto updates. The feature must be implemented as an Omnix module rather than embedding or running the existing `tradingview-mcp` application.

The implementation should reuse validated data-provider and normalization ideas from `tradingview-mcp`, but Omnix must own the UI, API contracts, persistence, provider lifecycle, tests, and release gates.

## Product decisions

1. **Native Omnix module.** Trading uses the existing Omnix React application, app shell, routing, appearance system, query client, Zustand conventions, typed gateway, diagnostics, and test infrastructure.
2. **No MCP runtime dependency.** MCP tools, Claude/OpenClaw integration, the standalone Vite app, and the standalone FastAPI workstation are not part of the Trading module.
3. **Research first.** The initial releases are for charting, market research, alerts, replay, and paper simulation. They do not place live broker orders.
4. **Provider-neutral contracts.** The frontend consumes normalized symbols, bars, quotes, trades, and order books without knowing provider-specific response formats.
5. **Real features only.** Do not expose chart styles, indicators, drawing tools, live status, or order controls that are only visual mockups.
6. **Local-first persistence.** Watchlists, layouts, drawings, indicator presets, and paper state are stored under `resources/data/trading/` through backend-owned repositories.
7. **Visible provenance.** Every chart and quote surface shows source, market session, delay or live status, timestamp, and fallback state.
8. **Incremental delivery.** Each phase should be independently reviewable, testable, and usable. Large UI and backend migrations should be split into narrow PRs.
9. **No silent licensing assumptions.** Free personal-use providers may support a local Omnix installation, but the application must not imply external redistribution rights.
10. **Preserve attribution.** Lightweight Charts attribution and any required notices must remain visible and compliant. Substantial migrated MIT-licensed code must retain its copyright and permission notice.

## Scope

### Initial production scope

- Stocks and crypto
- Yahoo/yfinance stock candles with direct Yahoo and Stooq fallback paths
- Binance, Coinbase, and Kraken crypto candles
- Real-time crypto streaming where supported
- Stock polling with explicit source and delay status
- One-, two-, and four-chart layouts
- Independent or linked chart symbols and intervals
- Synchronized crosshair and visible time range
- Candlestick, bar, line, area, baseline, and volume displays
- Watchlists and symbol search
- Saved workspaces and chart settings
- Core indicators: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, and VWAP
- Real drawing tools: horizontal line, vertical line, trend line, ray, rectangle, Fibonacci retracement, text note, and measurement
- Persistent drawings per symbol and interval
- Provider health, cache status, and degraded-data diagnostics

### Later scope

- Alerts
- Market scanner
- Replay mode
- Backtesting
- Paper portfolio and simulated orders
- News and fundamentals
- Economic calendar
- Local-LLM market research through Omnix's existing provider registry
- Optional premium or licensed data-provider adapters
- Multi-monitor workspaces

### Explicit non-goals for the first release

- Pine Script compatibility
- Live brokerage execution
- Options chains
- Futures market depth
- Full real-time consolidated US equities
- Full real-time TSX/TSXV redistribution
- Social trading
- Copy trading
- Automated AI order placement
- Pixel-for-pixel duplication of TradingView

## Target experience

The Trading workspace should use the approved Omnix visual direction:

- Existing Omnix left navigation with `Trading` selected
- A compact trading toolbar below the global Omnix top bar
- Symbol search, exchange/provider selector, timeframe selector, chart type selector, indicator menu, layout selector, link-group controls, undo/redo, snapshot, and fullscreen controls
- A vertical drawing-tools rail beside the chart grid
- A responsive chart grid supporting one, two, and four charts initially
- A right drawer with Watchlist, Indicators, Data, and Layout tabs
- An optional bottom drawer for Alerts, Replay, Paper, Backtests, and Logs as those capabilities become available
- Clear active-chart focus and keyboard shortcuts
- Dense but readable dark-mode presentation that still supports Omnix appearance settings

The workspace should not add a second application header, theme system, or navigation shell.

## Target architecture

### Frontend

Suggested structure:

```text
apps/web/src/features/trading/
  TradingWorkspace.tsx
  TradingWorkspace.css
  TradingToolbar.tsx
  TradingChartGrid.tsx
  TradingChartPanel.tsx
  TradingToolsRail.tsx
  TradingRightDrawer.tsx
  TradingBottomDrawer.tsx
  TradingWatchlist.tsx
  TradingSymbolSearch.tsx
  TradingIndicatorManager.tsx
  TradingDataStatus.tsx
  tradingApi.ts
  tradingStore.ts
  tradingTypes.ts
  chart/
    chartAdapter.ts
    chartLifecycle.ts
    chartSynchronization.ts
    chartSeries.ts
    chartViewport.ts
  drawings/
    drawingTypes.ts
    drawingStore.ts
    drawingController.ts
    drawingRenderer.ts
    drawingHitTesting.ts
    tools/
  indicators/
    indicatorRegistry.ts
    indicatorEngine.ts
    indicatorWorker.ts
    builtins/
```

Frontend responsibilities:

- Render charts and overlays
- Coordinate active chart, layout, link groups, viewport synchronization, and keyboard shortcuts
- Calculate supported indicators locally or in a Web Worker
- Maintain draft UI state while persisting authoritative workspace state through the backend
- Reconcile historical snapshots with streaming bar updates
- Surface stale, delayed, cached, degraded, and disconnected data states

### Backend

Suggested structure:

```text
src/app/trading/
  __init__.py
  models.py
  service.py
  symbols.py
  intervals.py
  cache.py
  workspace_repository.py
  watchlist_repository.py
  drawing_repository.py
  alert_repository.py
  providers/
    base.py
    registry.py
    yahoo.py
    stooq.py
    binance.py
    coinbase.py
    kraken.py
  streaming/
    manager.py
    subscriptions.py
    bar_aggregator.py
    gap_recovery.py

src/app/gateway/trading_routes.py
src/tests/app/test_trading_routes.py
src/tests/unit/trading/
```

Backend responsibilities:

- Normalize provider-specific symbols and intervals
- Fetch and cache historical bars
- Stream or poll live data
- Detect and fill gaps after reconnection
- Persist workspaces, watchlists, drawings, alerts, and paper state
- Expose typed provider-neutral contracts
- Report source, freshness, fallback, and health information
- Enforce request limits and bounded concurrency

### API namespace

Initial API surface:

```text
GET    /api/trading/providers
GET    /api/trading/providers/status
GET    /api/trading/symbols/search
GET    /api/trading/bars
GET    /api/trading/quote
GET    /api/trading/order-book
GET    /api/trading/watchlists
POST   /api/trading/watchlists
PUT    /api/trading/watchlists/{watchlist_id}
DELETE /api/trading/watchlists/{watchlist_id}
GET    /api/trading/workspaces
POST   /api/trading/workspaces
GET    /api/trading/workspaces/{workspace_id}
PUT    /api/trading/workspaces/{workspace_id}
DELETE /api/trading/workspaces/{workspace_id}
GET    /api/trading/drawings
PUT    /api/trading/drawings
WS     /api/trading/stream
```

Later namespaces may add:

```text
/api/trading/alerts
/api/trading/scanner
/api/trading/replay
/api/trading/backtests
/api/trading/paper
/api/trading/research
```

### Normalized bar contract

```json
{
  "symbol": "BTCUSDT",
  "asset_type": "crypto",
  "provider": "binance",
  "venue": "BINANCE",
  "interval": "5m",
  "currency": "USDT",
  "timezone": "UTC",
  "freshness": {
    "mode": "live",
    "as_of": 1785952800,
    "cached": false,
    "delayed_seconds": 0
  },
  "bars": [
    {
      "time": 1785952800,
      "open": 113420.5,
      "high": 113510.2,
      "low": 113300.1,
      "close": 113480.7,
      "volume": 125.42
    }
  ]
}
```

## Required invariants

- The frontend never parses raw Yahoo, Binance, Coinbase, or Kraken payloads.
- A bar series is strictly ordered by time and contains no duplicate timestamps.
- Historical and streaming updates use the same normalized bar model.
- A reconnect cannot silently skip completed bars; missing ranges are detected and repaired.
- The active chart is explicit and keyboard focus never changes it accidentally.
- Crosshair and range synchronization cannot create feedback loops.
- Drawings use stable IDs and chart coordinates, not screen pixels.
- Drawings remain aligned after zoom, pan, resize, interval change, and data refresh.
- Unsupported chart types and tools are hidden or marked `Planned`; they are never simulated as working.
- Cached or fallback data is visibly identified.
- Provider errors do not erase the last valid chart state.
- API keys and secrets never appear in browser payloads, logs, or diagnostics.
- Live broker execution remains disabled unless a separate reviewed program explicitly adds it.
- AI analysis is read-only with respect to market and portfolio state unless a later paper-trading contract explicitly permits simulation writes.

## Milestones

### Milestone A — Charting foundation

Phases OTT-0 through OTT-4 produce a usable Omnix charting terminal with stocks, crypto, saved workspaces, and multi-chart synchronization.

### Milestone B — Technical-analysis workstation

Phases OTT-5 through OTT-7 add real drawings, indicators, panes, and robust live-data behavior.

### Milestone C — Market research suite

Phases OTT-8 through OTT-11 add alerts, scanning, replay, backtesting, and paper simulation.

### Milestone D — Omnix intelligence and release hardening

Phases OTT-12 through OTT-14 add optional local-LLM research, operational hardening, accessibility, performance certification, and release documentation.

---

## Phase OTT-0 — Inventory, contracts, and architectural guardrails

### OTT-0.1 — Source migration inventory

Inventory reusable concepts from `autonomxDeveloper/tradingview-mcp` and classify each item as:

- migrate with attribution
- rewrite for Omnix
- reference only
- reject

At minimum, review:

- stock chart service
- crypto live service
- market-data cache service
- symbol and timeframe validators
- workstation API client
- chart component
- UI store
- workspace, watchlist, drawing, and paper repositories
- tests and fixtures

Acceptance:

- No runtime import from `tradingview-mcp` is planned.
- Every copied substantial code section has an attribution strategy.
- Mock-only chart features are explicitly rejected or scheduled for real implementation.

### OTT-0.2 — Trading domain contracts

Create provider-neutral backend and frontend contracts for:

- asset types
- symbols
- venues
- intervals
- bars
- quotes
- order books
- provider capability and health
- freshness and fallback state
- chart layout
- chart link groups
- indicator instances
- drawings

Acceptance:

- Contracts represent stocks and crypto without provider-specific fields in the core models.
- OpenAPI generation produces usable frontend types.
- Time units, timezone rules, and numeric precision are documented.

### OTT-0.3 — Architecture and ownership tests

Add static or unit checks preventing:

- MCP imports in the Omnix Trading module
- standalone app or server ownership
- raw provider payload leakage into frontend contracts
- live broker execution routes

Acceptance:

- Violations fail automated tests.
- The module has one frontend owner and one Omnix gateway namespace.

---

## Phase OTT-1 — Data-provider foundation

### OTT-1.1 — Provider interface and registry

Implement a common provider interface for capability discovery, symbol search, bars, quotes, and optional order-book or stream support.

Acceptance:

- Providers declare supported asset types, intervals, history depth, live capability, and rate-limit policy.
- The service can select a configured provider or deterministic fallback.

### OTT-1.2 — Stock providers

Migrate or rewrite:

- yfinance history path
- direct Yahoo chart fallback
- Stooq daily fallback
- normalized error envelopes
- bounded cache

Acceptance:

- AAPL, SPY, NVDA, and at least one non-US Yahoo-format symbol return ordered OHLCV bars in supported intervals.
- Daily fallback works when Yahoo is unavailable.
- Responses expose source and freshness state.

### OTT-1.3 — Crypto providers

Migrate or rewrite Binance, Coinbase, and Kraken history, quote, and order-book adapters.

Acceptance:

- BTC, ETH, and SOL pairs resolve consistently across providers.
- Provider-specific symbol formats do not reach the frontend.
- Pagination returns stable ordered bars without duplicates.

### OTT-1.4 — Cache and resilience

Implement:

- memory and file-backed cache policy
- stale-while-error behavior
- provider throttling
- retry and backoff
- request cancellation
- response provenance

Acceptance:

- A provider outage returns the last valid cached result when permitted.
- Cached data is never labeled live.
- Concurrent requests for the same range are coalesced.

---

## Phase OTT-2 — Native Omnix module and single-chart vertical slice

### OTT-2.1 — Module registration

Add:

- `trading` module ID and `/trading` route
- sidebar navigation entry
- `TradingWorkspace`
- module capabilities
- Omnix theme integration

Acceptance:

- Trading loads inside the existing Omnix shell.
- No second header, router, query client, or appearance provider is created.

### OTT-2.2 — Lightweight Charts adapter

Add the current supported Lightweight Charts package and wrap it behind an Omnix chart adapter.

Acceptance:

- The chart lifecycle cleans up all series, subscriptions, observers, and event handlers.
- Attribution requirements are satisfied.
- The adapter supports candlestick, bar, line, area, baseline, and volume series.

### OTT-2.3 — Historical single-chart workflow

Implement symbol, interval, provider, chart type, loading, empty, cached, stale, and error states.

Acceptance:

- A user can switch between AAPL, SPY, BTCUSDT, and ETHUSDT.
- Chart state survives a recoverable provider error.
- Data source and timestamp are visible.

### OTT-2.4 — Frontend and API tests

Acceptance:

- Unit tests cover bar normalization and chart adapter lifecycle.
- API tests cover stock and crypto routes with provider fixtures.
- Playwright verifies symbol and interval switching.

---

## Phase OTT-3 — Multi-chart workspace and synchronization

### OTT-3.1 — Layout model

Support initial layouts:

- one chart
- two horizontal charts
- two vertical charts
- four-chart grid

Acceptance:

- Layout changes preserve chart state.
- The active chart is visually and semantically explicit.
- Charts resize without recreation loops.

### OTT-3.2 — Chart link groups

Allow charts to link independently by:

- symbol
- interval
- crosshair
- visible time range

Acceptance:

- Linking one property does not force the others.
- Synchronization is loop-safe.
- A chart can leave or join a link group without resetting its data.

### OTT-3.3 — Crosshair and viewport synchronization

Acceptance:

- Crosshair position is mapped by timestamp rather than pixel position.
- Missing timestamps do not throw or jump charts unexpectedly.
- Time-range sync tolerates different bar densities.

### OTT-3.4 — Workspace keyboard behavior

Add keyboard support for active chart, interval shortcuts, drawing cancellation, undo/redo, fullscreen, and panel toggles.

Acceptance:

- Shortcuts do not fire while typing in inputs.
- Focus behavior is covered by tests.

---

## Phase OTT-4 — Watchlists and workspace persistence

### OTT-4.1 — Watchlist repository and API

Acceptance:

- Users can create, rename, reorder, and delete watchlists.
- Duplicate symbols are handled deterministically.
- Invalid symbols are reported without corrupting the list.

### OTT-4.2 — Workspace document

Persist:

- layout
- chart symbols and intervals
- providers and venues
- chart types
- link groups
- panel visibility and sizes
- indicator instances
- drawing references

Acceptance:

- Workspaces are versioned and migrated deterministically.
- Corrupt or unknown fields cannot destroy defaults.
- Writes are atomic.

### OTT-4.3 — Autosave and recovery

Acceptance:

- Changes are debounced and saved without excessive writes.
- Failed saves preserve the local draft and expose retry.
- The last valid workspace can recover after a malformed file.

---

## Phase OTT-5 — Real drawing engine

### OTT-5.1 — Drawing coordinate model

Represent drawings with stable IDs, timestamps, prices, style, lock state, visibility, and optional text.

Acceptance:

- Drawings do not store screen coordinates as authority.
- Serialization is deterministic and versioned.

### OTT-5.2 — Interaction controller

Implement selection, creation, drag, resize, delete, duplicate, lock, hide, undo, and redo.

Acceptance:

- Pointer capture prevents stuck drawing states.
- Pan and zoom are disabled only when the active tool requires it.
- Escape cancels the current operation.

### OTT-5.3 — Initial drawing tools

Implement real working versions of:

- horizontal line
- vertical line
- trend line
- ray
- rectangle
- Fibonacci retracement
- text note
- price/time measurement

Acceptance:

- Every exposed tool can be created, selected, edited, persisted, restored, and deleted.
- No static demonstration overlays remain.

### OTT-5.4 — Drawing persistence and scope

Support symbol-and-interval scope plus optional global-symbol scope.

Acceptance:

- Drawings remain aligned through resize, pan, zoom, refresh, and reload.
- Interval changes follow the documented visibility policy.

---

## Phase OTT-6 — Indicators and panes

### OTT-6.1 — Indicator registry

Create metadata for inputs, outputs, overlay/pane placement, defaults, validation, and display precision.

Acceptance:

- Unsupported indicators cannot be instantiated.
- Invalid settings return field-level errors.

### OTT-6.2 — Indicator engine

Implement built-ins:

- SMA
- EMA
- RSI
- MACD
- Bollinger Bands
- ATR
- VWAP

Acceptance:

- Results are deterministic against fixtures.
- Warm-up periods and missing values are handled explicitly.
- Heavy calculations do not block chart interaction.

### OTT-6.3 — Indicator panes and controls

Acceptance:

- Overlay indicators share the price scale correctly.
- Pane indicators support resize, hide, reorder, settings, and removal.
- Indicator state persists per chart.

---

## Phase OTT-7 — Live data and streaming resilience

### OTT-7.1 — Streaming manager

Implement shared subscriptions with reference counting so identical chart subscriptions do not create duplicate upstream connections.

Acceptance:

- Subscription teardown is reliable.
- Reopening a workspace does not multiply listeners.
- Provider connection state is visible.

### OTT-7.2 — Crypto streaming

Start with Binance and add Coinbase/Kraken where their contracts are stable.

Acceptance:

- The current candle updates in place.
- A completed candle is appended once.
- Trades arriving out of order cannot corrupt bar ordering.

### OTT-7.3 — Reconnect and gap repair

Acceptance:

- Disconnects use bounded exponential backoff.
- Missing completed candles are fetched after reconnection.
- The UI distinguishes connecting, live, delayed, reconnecting, stale, and cached states.

### OTT-7.4 — Stock refresh policy

Use provider-aware polling and market-session logic.

Acceptance:

- Polling pauses or slows outside the relevant session according to policy.
- The UI does not label polled Yahoo data as exchange real-time data.

---

## Phase OTT-8 — Alerts

Implement price, percentage move, crossing, indicator, and drawing-line alerts.

Acceptance:

- Alerts run in the backend and survive a closed browser tab.
- Alert triggers are deduplicated.
- Evaluation state persists across restart.
- Notifications link back to the relevant workspace, chart, symbol, and interval.

---

## Phase OTT-9 — Market scanner

Implement configurable scans over a bounded symbol universe using cached bars and locally calculated indicators.

Acceptance:

- Scans declare provider, universe, interval, freshness, and completion coverage.
- Partial provider failures are visible rather than silently omitted.
- Scans run through Omnix jobs and progress events.

---

## Phase OTT-10 — Replay and backtesting

### Replay

- deterministic historical cursor
- play, pause, step, speed, and jump controls
- chart, indicator, and drawing compatibility
- no future-bar leakage

### Backtesting

- versioned strategy inputs
- commission and slippage
- trades, equity curve, drawdown, and summary metrics
- deterministic fixtures

Acceptance:

- Repeated runs with the same data and settings produce identical results.
- Backtests record the exact data source and range.
- The UI clearly separates historical simulation from live conditions.

---

## Phase OTT-11 — Paper portfolio

Implement simulated balances, positions, orders, fills, P&L, stop loss, and take profit.

Acceptance:

- The feature is visibly labeled `Paper`.
- No broker credentials or live-order endpoint exists.
- Fill assumptions are explicit and deterministic.
- Portfolio state can be reset and exported.

---

## Phase OTT-12 — Omnix AI research integration

Use the existing Omnix provider and model registry rather than direct LM Studio calls.

Initial capabilities:

- summarize visible chart context
- identify observed trend and volatility regime
- describe marked levels and active indicators
- propose research questions or backtests
- compare selected timeframes
- produce a cited data snapshot used for the response

Acceptance:

- AI receives bounded structured market context rather than raw unbounded histories.
- Responses identify symbol, interval, data source, and as-of time.
- AI cannot submit live orders.
- Invalid structured output cannot create paper orders automatically.
- The UI labels generated analysis as informational and not financial advice.

---

## Phase OTT-13 — Performance, accessibility, and responsive behavior

### Performance gates

- Four visible charts with representative history remain interactive during pan, zoom, and crosshair movement.
- Streaming updates do not recreate charts or full series unnecessarily.
- Indicator work is incremental or off-main-thread where appropriate.
- Hidden charts and panels do not retain unnecessary subscriptions.
- Repeated workspace switching does not leak chart instances or listeners.

### Accessibility gates

- Keyboard navigation for toolbar, tools, tabs, layouts, and chart selection
- Visible focus states
- Accessible names for icon controls
- Color is not the only indicator of gain, loss, stale data, or active state
- Reduced-motion support
- Appropriate screen-reader summaries for chart metadata and active values

### Responsive policy

The full workstation targets desktop first. Smaller widths may collapse the right and bottom panels, reduce available layout presets, and preserve a single usable chart rather than compressing four unreadable charts.

---

## Phase OTT-14 — Release certification and documentation

Deliver:

- user guide
- provider and data-provenance guide
- cache and freshness behavior
- drawing and indicator guide
- troubleshooting and diagnostics guide
- attribution and license notices
- local release qualification procedure
- data-provider limitations and commercial-use warning

Release gates:

- frontend typecheck and unit tests
- backend unit and API tests
- Playwright critical-path suite
- provider-fixture tests without internet dependency
- local live-provider qualification for each enabled provider
- memory and subscription leak checks
- four-chart interaction benchmark
- accessibility review
- no exposed mock-only controls
- no live execution endpoint

## Initial implementation slices

The first implementation program should be split into narrow PRs:

1. **Trading contracts and route skeleton** — module registration, typed models, empty workspace, architecture guards.
2. **Historical data providers** — Yahoo/yfinance/Stooq plus Binance history and normalized bars API.
3. **Single chart vertical slice** — Lightweight Charts adapter, data status, symbol and interval controls.
4. **Multi-chart layouts** — one/two/four chart grid and active-chart handling.
5. **Chart synchronization** — link groups, crosshair, and visible-range synchronization.
6. **Watchlists and saved workspaces** — repositories, APIs, autosave, and recovery.
7. **Core drawing engine** — coordinate model, renderer, hit testing, persistence, undo/redo.
8. **Core indicators** — SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP, and panes.
9. **Live crypto stream** — shared subscriptions, reconnect, and gap repair.
10. **MVP qualification** — Playwright flows, performance, accessibility, docs, and release evidence.

Alerts, scanner, replay, backtesting, paper state, and AI research should begin only after the charting MVP passes qualification.

## MVP definition of done

The first production-usable release is complete when a user can:

1. Open `/trading` inside Omnix.
2. Search and load supported stock and crypto symbols.
3. View one, two, or four charts.
4. Configure each chart independently or link selected properties.
5. Synchronize crosshairs and visible ranges without feedback loops.
6. Switch supported intervals and chart types.
7. Add, edit, persist, restore, hide, lock, undo, redo, and delete supported drawings.
8. Add and configure supported indicators and panes.
9. Create and manage watchlists.
10. Save, restore, rename, and delete workspaces.
11. Receive live crypto candle updates with reconnect and gap repair.
12. See provider, source, freshness, delay, cache, and degraded states.
13. Recover from provider errors without losing the last valid chart state.
14. Use critical controls by keyboard.
15. Complete the Playwright critical path with no mock-only controls or live execution routes.

## Major risks and mitigations

### Data terms and redistribution

**Risk:** Free data access does not necessarily permit redistribution or commercial external display.  
**Mitigation:** Keep initial use local-first, expose provider provenance, document terms, and preserve adapter boundaries for licensed feeds.

### Yahoo/yfinance fragility

**Risk:** Unofficial interfaces may change or throttle.  
**Mitigation:** Use direct and library paths, Stooq fallback, bounded caching, clear degraded states, and provider-neutral replacement boundaries.

### Drawing complexity

**Risk:** A production drawing engine is significantly harder than rendering decorative overlays.  
**Mitigation:** Start with a small real tool set, stable coordinate contracts, explicit interaction states, and exhaustive persistence/hit-testing tests.

### Multi-chart performance

**Risk:** Four charts, indicators, drawings, and live updates can cause event storms and memory leaks.  
**Mitigation:** Shared subscriptions, incremental updates, Web Workers, lifecycle ownership, loop guards, and performance gates from the first vertical slice.

### Feature overreach

**Risk:** Scanner, alerts, paper trading, backtests, AI, and broker controls can distract from chart reliability.  
**Mitigation:** Treat charting MVP qualification as a hard gate before later milestones.

### Misleading market status

**Risk:** Users may mistake cached, delayed, polled, or single-venue data for consolidated real-time data.  
**Mitigation:** Make source and freshness first-class typed data shown on every relevant surface.

## Issue creation policy

After this roadmap is approved:

- Create one umbrella tracking issue for the Trading Terminal program.
- Create one issue per implementation slice, not one issue per small component.
- Use dependencies and acceptance criteria from this document in each issue.
- Do not open later-milestone issues until the preceding milestone is near completion, except for architectural spikes that unblock the current phase.
- Keep `MVP`, `technical-analysis`, `market-research`, and `release-hardening` as milestone groupings rather than parallel unbounded workstreams.
