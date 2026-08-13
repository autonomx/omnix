# Omnix Trading Terminal — Final Implementation Roadmap

**Status:** Final roadmap, maintained as the implementation and qualification contract  
**Target route:** `/trading`  
**Target module name:** `Trading`  
**Roadmap branch:** `agent/trading-terminal-roadmap`  
**Reference prototype:** `autonomxDeveloper/tradingview-mcp`  
**Primary renderer candidate:** TradingView Lightweight Charts  
**Product posture:** local-first market research and paper simulation; no live brokerage execution

## 1. Program objective

Build a native Omnix market-analysis workspace that provides a credible TradingView-style experience while remaining consistent with Omnix architecture, PostgreSQL persistence, design system, diagnostics, provider governance, and test infrastructure.

The final product may support crypto and stocks, multi-chart workspaces, real drawings, indicators, alerts, replay, backtesting, paper simulation, and optional local-LLM research. These capabilities are delivered incrementally. The first qualified release is intentionally crypto-only so the charting, synchronization, drawing, streaming, persistence, and lifecycle architecture can be proven before equity calendars, adjusted prices, polling, and unofficial provider behavior are introduced.

The existing `tradingview-mcp` repository is a validated prototype and code donor. It is not a runtime dependency. Omnix owns the UI, API contracts, PostgreSQL persistence, provider bindings, cache policy, streaming behavior, tests, diagnostics, and release qualification.

## 2. Final product decisions

1. **Native Omnix module.** Trading uses the existing React application, Omnix shell, TanStack Router, Mantine appearance system, TanStack Query, Zustand conventions, generated OpenAPI types, gateway, diagnostics, PostgreSQL authority, and test infrastructure.
2. **No MCP runtime dependency.** Do not embed the MCP server, standalone FastAPI workstation, standalone Vite application, Claude/OpenClaw integration, or direct LM Studio calls from the prototype.
3. **Charting feasibility comes first.** A disposable but production-shaped spike must prove multi-chart rendering, panes, drawing interaction, streaming recovery, and lifecycle cleanup before production architecture is accepted.
4. **PostgreSQL is authoritative.** Workspaces, watchlists, drawings, indicator presets, alerts, backtest metadata, and paper state must not use mutable JSON files as production authority.
5. **Caches are disposable.** A bounded `resources/cache/trading/` directory may hold fetched market data and recovery snapshots, but cached candles are never authoritative user data.
6. **Instrument identity is provider-independent.** Canonical instruments identify the traded asset at a venue. Yahoo, Stooq, Binance REST, Binance WebSocket, or another API are provider/feed bindings to that instrument, not part of its identity.
7. **Provider-neutral frontend contracts.** The frontend consumes canonical instruments, normalized bars, quotes, and stream events. It never parses raw provider payloads.
8. **Real features only.** Unsupported chart styles, indicators, drawing tools, live labels, or order controls are hidden or marked `Planned`; they are never simulated as functional.
9. **Research before execution.** Initial releases support charting, alerts, replay, backtesting, and paper simulation. Live broker execution requires a separate reviewed program.
10. **Provider use is executable policy.** Personal-use, internal-use, external-display, official API, redistribution, authentication, delay, and terms metadata are exposed by each adapter and surfaced in the UI.
11. **No silent provider mixing.** A fallback may replace an entire requested dataset, but bars from different providers are never spliced into one series without an explicit reconciliation design.
12. **Drawings are instrument-scoped by default.** Major levels survive timeframe and provider changes unless an optional interval visibility mask restricts them.
13. **Indicator definitions are versioned.** Frontend and backend implementations share formula specifications and golden fixtures before indicators are used by alerts, scanners, replay, or backtesting.
14. **Charting Beta is crypto-only.** Equity support begins only after the charting foundation passes qualification.
15. **Incremental delivery.** Every phase is independently reviewable and testable. Alerts, scanning, replay, paper trading, and AI research remain blocked until their prerequisite gates pass.
16. **Attribution and licensing are preserved.** Lightweight Charts attribution remains compliant, and substantial MIT-licensed code migrated from the prototype retains the required notice.
17. **Layout capacity is adaptive, not a fixed preset model.** Workspaces may add or remove charts within the supported capacity and reflow automatically or by an explicit column choice. One-, two-, and four-chart arrangements are qualification/examples, not the only product layouts.

## 3. Delivery milestones

### Milestone A — Architecture proven

Phases `OTT-0` and `OTT-1` prove the renderer, drawing interaction model, live-data lifecycle, Omnix integration points, persistence ownership, canonical instrument contracts, and provider-binding contracts.

### Milestone B — Charting Beta

Phases `OTT-2` through `OTT-7` deliver the first useful release:

- Binance spot historical and live crypto data
- adaptive multi-chart grid, Beta-qualified through four active charts
- synchronized crosshair and visible range
- watchlists and saved workspaces
- candlestick, line, and volume
- SMA, EMA, and RSI
- horizontal and trend lines
- provider/feed provenance
- reconnect and exact gap recovery
- measurable performance and lifecycle qualification

**Charting Beta is crypto-only.** Yahoo, Stooq, equity calendars, adjustment modes, and stock polling are not part of the Beta definition of done.

### Milestone C — Technical Analysis MVP

Phases `OTT-8` and `OTT-9` add experimental stocks, more crypto providers, advanced indicators, panes, chart types, drawing tools, flexible multi-panel arrangements, and stronger provider fallback.

### Milestone D — Market Research Suite

Phases `OTT-10` through `OTT-13` add alerts, restart-safe scanner execution, replay, deterministic backtesting, and paper simulation.

### Milestone E — Omnix Intelligence and release hardening

Phases `OTT-14` and `OTT-15` add optional local-LLM research, accessibility, performance certification, provider documentation, licensing checks, and final release gates.

## 4. Scope

### 4.1 Charting Beta scope

- Native `/trading` Omnix module
- Sidebar navigation entry
- Dedicated focus mode that can collapse the Omnix shell for maximum chart area
- Binance spot historical and live candles
- Adaptive multi-chart grid, with one through four active charts covered by Beta qualification
- Candlestick, line, and volume displays
- Instrument, venue, provider/feed, and timeframe selection
- Explicit active chart
- Crosshair and visible-range synchronization
- Watchlists and saved workspaces
- Live reconnect and exact gap repair
- SMA, EMA, and RSI
- Horizontal line and trend line
- Drawing create, select, drag/resize, delete, persist, undo, and redo
- PostgreSQL persistence with revisions
- Provider, feed, freshness, cache, and fallback status
- Playwright, API, lifecycle, reconnect, accessibility, and performance qualification

### 4.2 Technical Analysis MVP scope

- Experimental Yahoo-derived equity adapter with personal/local-use labeling
- Stooq whole-dataset fallback for eligible daily equity data
- Coinbase, Kraken, and optionally Hyperliquid adapters
- Flexible multi-chart and multi-panel arrangements, including horizontal and vertical splits
- Bar, area, and baseline chart types
- MACD, Bollinger Bands, ATR, and explicitly anchored VWAP
- Indicator panes and presets
- Vertical line, ray, rectangle, Fibonacci retracement, text, and measurement tools
- Advanced snapping, styles, locking, hiding, and drawing management
- More robust provider fallback and diagnostics
- Snapshot/export support

### 4.3 Later scope

- Alerts
- Market scanner
- Historical replay
- Strategy backtesting
- Paper portfolio and simulated orders
- News and fundamentals
- Economic calendar
- Local-LLM market research through the Omnix provider registry
- Optional licensed market-data adapters
- Multi-monitor layouts

### 4.4 Explicit non-goals for the first program

- Pine Script compatibility
- Pixel-for-pixel TradingView duplication
- Live brokerage execution
- Automated AI order placement
- Options chains
- Futures market depth
- Full real-time consolidated US equities
- Full real-time TSX/TSXV redistribution
- Social or copy trading
- An API endpoint without a current UI consumer or approved near-term dependency

The order-book endpoint is deferred until an actual order-book panel is approved.

## 5. Target user experience

The Trading workspace follows the approved Omnix visual direction:

- Existing Omnix sidebar with `Trading` selected
- Trading is not added to the compact top mode switch initially
- Dedicated focus-mode control for collapsing global navigation and maximizing chart space
- Compact trading toolbar below the global Omnix top bar
- Instrument search, venue/provider selector, timeframe selector, chart type selector, indicator menu, layout selector, link-group controls, undo/redo, snapshot, and fullscreen controls
- Vertical drawing-tools rail beside the chart grid
- Adaptive chart grid that reflows as charts are added/removed and supports explicit column arrangements within the supported capacity
- Right drawer with Watchlist, Indicators, Data, and Layout tabs
- Bottom drawer added only when Alerts, Replay, Backtests, Paper, or Logs are implemented
- Clear active-chart focus and keyboard shortcuts
- Dense but readable dark-mode presentation compatible with Omnix appearance settings
- Every chart visibly identifies canonical instrument, venue, resolved provider/feed, freshness, delay, market session, adjustment mode, cache status, and fallback state

Changing a provider or fallback source reloads and relabels the dataset but does not change the canonical instrument, watchlist entry, drawing ownership, alert target, or paper position identity.

The module must not add a second application header, router, query client, theme system, or navigation shell.

## 6. Target architecture

### 6.1 Frontend

```text
apps/web/src/features/trading/
  TradingWorkspace.tsx
  TradingWorkspace.css
  TradingToolbar.tsx
  TradingFocusMode.tsx
  TradingChartGrid.tsx
  TradingChartPanel.tsx
  TradingToolsRail.tsx
  TradingRightDrawer.tsx
  TradingWatchlist.tsx
  TradingDataStatus.tsx
  TradingInstrumentSearch.tsx
  TradingIndicatorManager.tsx
  tradingApi.ts
  tradingStore.ts
  chart/
    chartAdapter.ts
    chartLifecycle.ts
    chartSynchronization.ts
    chartSeries.ts
    chartViewport.ts
  drawings/
    drawingController.ts
    drawingRenderer.ts
    drawingHitTesting.ts
    drawingCommands.ts
    drawingDraftRecovery.ts
    tools/
  indicators/
    indicatorRegistry.ts
    indicatorEngine.ts
    indicatorWorker.ts
    specifications/
    fixtures/
```

Frontend responsibilities:

- Render charts, series, panes, and drawing primitives
- Coordinate active chart, layout, link groups, viewport synchronization, and keyboard shortcuts
- Calculate interactive indicators locally or in a Web Worker
- Maintain transient drawing state during pointer interaction
- Persist drawing/workspace revisions after pointer release or debounce
- Use IndexedDB only for crash recovery of unsaved drafts
- Reconcile historical snapshots with partial and finalized streaming bars
- Surface stale, delayed, cached, fallback, degraded, and disconnected states
- Convert backend decimal/scaled values to chart-library JavaScript numbers only at the chart boundary

### 6.2 Backend

```text
src/app/trading/
  __init__.py
  models.py
  service.py
  instruments.py
  provider_bindings.py
  intervals.py
  sessions.py
  adjustment.py
  provider_policy.py
  cache.py
  repositories.py
  providers/
    base.py
    registry.py
    binance.py
    yahoo.py
    stooq.py
    coinbase.py
    kraken.py
    hyperliquid.py
  streaming/
    manager.py
    subscriptions.py
    bar_aggregator.py
    gap_recovery.py
  indicators/
    specifications.py
    engine.py

src/app/gateway/trading_routes.py
src/tests/app/test_trading_routes.py
src/tests/unit/trading/
```

Backend responsibilities:

- Resolve canonical instruments independently from provider/feed bindings
- Normalize intervals, sessions, timezones, adjustments, and numeric precision
- Fetch and cache historical bars
- Stream partial/final bars and recover gaps
- Coalesce identical upstream subscriptions
- Persist authoritative trading documents through PostgreSQL repositories and Unit of Work
- Expose typed provider-neutral OpenAPI contracts
- Report provider capabilities, usage policy, provenance, fallback, and health
- Enforce bounded concurrency, cancellation, throttling, and backoff

### 6.3 Persistence ownership

#### PostgreSQL authority

Use `PostgresModuleRecordRepository` initially for small revisioned documents:

- workspaces
- watchlists
- indicator presets
- drawing documents
- UI layout preferences

Every mutation uses optimistic concurrency through `revision` or `If-Match`. Multiple-tab conflicts return the current server revision rather than silently overwriting it.

Use dedicated relational schemas when query or transaction requirements justify them:

- alerts and alert evaluations
- scanner runs, incremental progress, and results
- backtest runs and trade records
- paper accounts, orders, fills, positions, balances, and ledger entries

#### BlobStore

Use BlobStore for chart snapshots, exported research packets, immutable backtest reports, and large equity-curve or trade-log artifacts.

#### Disposable cache

Use a bounded cache under:

```text
resources/cache/trading/
```

for provider responses and recovery snapshots only. Cache entries have TTL, provider/feed identity, dataset fingerprint, and explicit stale state. They are safe to delete at any time.

## 7. Canonical contracts

### 7.1 Canonical instrument

A canonical instrument identifies the traded asset at a venue and is independent of the API that supplies data.

```text
instrument_id
asset_class
instrument_type
venue
venue_symbol
display_symbol
base_currency
quote_currency
exchange_timezone
session_calendar
price_scale
minimum_tick
status
```

Examples:

```text
crypto:BINANCE:spot:BTC-USDT
crypto:HYPERLIQUID:perpetual:BTC-USD
equity:NASDAQ:AAPL
```

Aliases may resolve to canonical instruments, but aliases and provider symbols are never stored as canonical authority.

### 7.2 Provider/feed binding

A provider binding maps a canonical instrument to a specific market-data source.

```text
binding_id
instrument_id
provider
provider_symbol
feed_type
realtime_scope
delay_seconds
adjustment_capabilities
supported_intervals
usage_scope
is_official_api
```

Examples:

```text
instrument_id: equity:NASDAQ:AAPL
provider: yahoo
provider_symbol: AAPL
feed_type: historical_polling
```

```text
instrument_id: equity:NASDAQ:AAPL
provider: stooq
provider_symbol: AAPL.US
feed_type: historical_daily
```

```text
instrument_id: crypto:BINANCE:spot:BTC-USDT
provider: binance
provider_symbol: BTCUSDT
feed_type: websocket_and_rest
```

Provider switching and fallback change the binding and dataset provenance, not the canonical instrument.

### 7.3 Bar contract

```text
instrument_id
interval
start_time
end_time
open
high
low
close
volume
is_final
adjustment_mode
session
provider
provider_event_id
provider_sequence
ingestion_revision
received_at
```

`provider_event_id` and `provider_sequence` are optional because many feeds expose neither. `ingestion_revision` is Omnix-owned and records local correction/replacement ordering.

Rules:

- Intraday timestamps are UTC internally.
- Daily equity bars retain exchange-session semantics.
- Raw, split-adjusted, and dividend-adjusted prices are never mixed.
- Partial streaming candles use `is_final: false`.
- Backend calculations use `Decimal` or scaled integers where precision matters.
- Cache keys include provider binding, canonical instrument, interval, adjustment mode, and session policy.
- Bars are strictly ordered and contain no duplicate start times.
- A corrected bar increments or replaces according to Omnix ingestion revision rules.

### 7.4 Dataset provenance

Every historical response includes:

```text
instrument_id
requested_binding
resolved_binding
fallback_reason
dataset_fingerprint
freshness_mode
as_of
received_at
delay_seconds
cached
history_complete
```

Provider fallback replaces the complete response dataset. It does not splice bars from different providers.

### 7.5 Provider policy

Each adapter declares:

```text
usage_scope
redistribution_allowed
authentication_required
is_official_api
realtime_scope
delay_seconds
terms_reference
supported_asset_classes
supported_intervals
history_depth
rate_limit_policy
```

Allowed `usage_scope` examples:

```text
personal_local
internal
external_display
licensed
```

Yahoo-derived data is labeled in the UI as personal/local, unofficial, and availability-not-guaranteed.

### 7.6 Drawing model

Drawings contain stable chart coordinates, never screen pixels:

```text
drawing_id
instrument_id
tool_type
points[]: { time, price }
interval_visibility
style
locked
hidden
revision
created_at
updated_at
```

Drawings are instrument-scoped across intervals and provider bindings by default. `interval_visibility` is optional.

### 7.7 Indicator specification

Every indicator definition includes:

```text
indicator_id
formula_version
parameters
warmup_behavior
missing_bar_behavior
numeric_tolerance
session_reset_policy
output_series
```

TypeScript and Python implementations must pass the same golden fixtures before a backend feature relies on that indicator. VWAP must declare its anchor/reset policy; the term `VWAP` alone is not sufficient.

## 8. Initial API surface

Only APIs with an initial consumer are included:

```text
GET    /api/trading/providers
GET    /api/trading/providers/status
GET    /api/trading/instruments/search
GET    /api/trading/bars
GET    /api/trading/quotes
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

Later namespaces:

```text
/api/trading/alerts
/api/trading/scanner
/api/trading/replay
/api/trading/backtests
/api/trading/paper
/api/trading/research
```

The OpenAPI schema is the source for frontend API types. Hand-maintained duplicate request/response types are prohibited where generated types are available.

## 9. Required invariants

- One frontend owner and one Omnix gateway namespace
- No MCP imports in the Trading module
- No standalone Trading server or application shell
- No raw provider payloads in frontend contracts
- No mutable JSON production authority
- No live broker execution routes
- Canonical instrument identity is independent of provider/feed identity
- Watchlists, drawings, alerts, and paper state reference canonical instruments
- Provider changes do not duplicate or detach instrument-owned state
- Historical and streaming updates use the same canonical bar model
- Partial and finalized bars are distinguishable
- Provider sequencing fields are optional; Omnix ingestion revision is authoritative for local ordering
- Reconnect cannot silently skip finalized bars
- Identical chart subscriptions share one upstream subscription
- Crosshair and visible-range synchronization are timestamp-based and loop-safe
- Drawings use stable time/price coordinates
- Drawings survive zoom, pan, resize, reload, timeframe changes, and provider changes
- Pointer movement does not write to PostgreSQL on every frame
- Unsupported functionality is not presented as working
- Cached and fallback data are visibly identified
- Provider errors do not erase the last valid chart state
- Provider changes visibly reload and relabel the complete dataset
- Secrets never appear in browser payloads, logs, fixtures, or diagnostics
- Scanner execution persists incremental progress and obeys shared global/provider budgets
- AI research remains read-only unless a later paper-simulation contract explicitly allows writes

## 10. Implementation phases

## Phase OTT-0 — ADR, source inventory, and charting feasibility spike

### OTT-0.1 — Architecture decision record

Document:

- native Omnix ownership
- Lightweight Charts as renderer candidate rather than interaction framework
- PostgreSQL authority
- cache policy
- canonical instrument versus provider-binding identity
- no-live-execution boundary
- prototype migration and attribution policy
- spike success, failure, and cleanup policy

Acceptance:

- The ADR names the owner of every runtime concern.
- No standalone app or MCP dependency is planned.
- Production authority and disposable cache are explicitly separated.
- The renderer decision is not considered final until spike evidence is recorded.

### OTT-0.2 — Prototype migration inventory

Classify prototype code as:

- migrate with attribution
- rewrite for Omnix
- reference only
- reject

Review at minimum stock and crypto services, cache service, symbol/timeframe validators, React chart component, UI store, watchlist/workspace/drawing services, tests, and fixtures.

Acceptance:

- Mock-only chart styles and decorative drawing overlays are rejected.
- Every substantial copied section has an attribution plan.

### OTT-0.3 — Feasibility spike

Build a disposable but realistic spike containing:

- four charts with 5,000 bars each
- synchronized crosshair across different intervals
- synchronized visible ranges
- one RSI pane
- one selectable, draggable, and resizable trend line
- drawing hit testing and selection handles
- one horizontal line
- resize and fullscreen behavior
- one live Binance stream
- simulated disconnect, reconnect, and exact gap recovery
- repeated mount/unmount and workspace-switch testing

Acceptance:

- Four charts remain interactive under the target load.
- The drawing remains aligned after resize, zoom, pan, and reload.
- Different-interval crosshair synchronization behaves predictably.
- No duplicate finalized bars appear after reconnect cycles.
- No material listener, observer, or chart-instance leak is detected.
- Benchmark evidence is saved with environment and methodology.
- A written ADR decision confirms the renderer and drawing approach are viable or selects an alternative.

### OTT-0.4 — Spike exit policy

After the spike:

- reusable adapter code may be retained only after the ADR explicitly accepts it;
- disposable UI and benchmark scaffolding is deleted or moved under a clearly named experimental path;
- benchmark evidence and the architecture decision are committed;
- a failed spike blocks production `/trading` implementation and triggers renderer/interaction reassessment;
- temporary shortcuts cannot silently become production contracts.

The spike is a go/no-go gate. Provider expansion and production UI work do not begin until it passes.

## Phase OTT-1 — Omnix module shell, persistence, and canonical contracts

### OTT-1.1 — Explicit frontend integration

Update:

- `apps/web/src/app/modules.ts`
- `apps/web/src/app/router.tsx`
- `apps/web/src/features/ModuleWorkspace.tsx`
- navigation icon/design primitive mapping
- module capabilities
- appearance integration

Add `TradingWorkspace` and focus mode.

Acceptance:

- `/trading` loads inside the existing Omnix shell.
- Trading appears in the sidebar but not the compact mode switch.
- Focus mode can restore the prior shell state.
- No second router, theme provider, query client, or header exists.

### OTT-1.2 — Gateway and diagnostics integration

Add and explicitly register the Trading router through the existing gateway installation pattern.

Acceptance:

- Routes appear in the gateway OpenAPI document.
- Generated TypeScript types are refreshed.
- API drift validation passes.
- Trading provider/cache/stream status appears in diagnostics.

### OTT-1.3 — PostgreSQL repositories

Create semantic repositories backed initially by `PostgresModuleRecordRepository` for workspaces, watchlists, drawings, and indicator presets.

Acceptance:

- All documents are workspace-scoped.
- Create and update operations enforce revisions.
- Conflicts return the latest revision.
- Restarting Omnix preserves state.
- No production JSON repository is introduced.

### OTT-1.4 — Canonical contracts and tests

Define experimental but typed contracts for canonical instruments, provider bindings, bars, provider policy, provenance, streams, layouts, link groups, drawings, and indicator instances.

Acceptance:

- Spot and perpetual instruments cannot collide.
- One canonical instrument may have multiple provider bindings.
- Switching bindings does not change watchlist or drawing identity.
- Raw and adjusted equity bars cannot be mixed.
- Partial/final bars are explicit.
- Optional provider sequence fields and Omnix ingestion revision are distinct.
- OpenAPI generation produces frontend types.

## Phase OTT-2 — Binance provider and market-data foundation

### OTT-2.1 — Binance historical adapter

Migrate or rewrite validated Binance candle logic.

Acceptance:

- BTC, ETH, and SOL spot instruments resolve canonically.
- REST and WebSocket bindings map to the same canonical instrument.
- Pagination returns ordered, duplicate-free bars.
- Responses contain provider policy and dataset provenance.
- Cancellation, timeout, throttling, and bounded retry are covered.

### OTT-2.2 — Cache and request coalescing

Acceptance:

- Concurrent identical requests share one upstream call.
- Cached data is never labeled live.
- Cache keys include binding, instrument, interval, adjustment, and session policy.
- Cache deletion does not remove user state.

### OTT-2.3 — Binance streaming

Implement shared subscriptions, partial/final bar updates, reconnect, and REST gap recovery.

Acceptance:

- Two charts requesting the same binding and stream create one upstream subscription.
- Reconnect repairs every missing finalized bar.
- Out-of-order, duplicate, and corrected events do not corrupt the series.
- Subscription status is visible in diagnostics.

## Phase OTT-3 — Single historical and live chart

### OTT-3.1 — Chart adapter and lifecycle

Wrap Lightweight Charts behind an Omnix adapter.

Acceptance:

- Candlestick, line, and volume are supported.
- All series, observers, listeners, and subscriptions are cleaned up.
- Ordinary updates do not recreate the chart.
- Required attribution is present.

### OTT-3.2 — Single-chart workflow

Implement instrument search, interval selection, provider/feed display, loading, empty, stale, cached, disconnected, and error states.

Acceptance:

- Users can move between canonical BTC-USDT, ETH-USDT, and SOL-USDT instruments.
- Live and historical bars reconcile without duplicates.
- A recoverable provider failure keeps the last valid chart visible.
- Provider/feed/freshness information is always readable.

## Phase OTT-4 — Flexible multi-chart layout and synchronization

### OTT-4.1 — Layout and active-chart model

Support an adaptive multi-chart grid for Beta and qualify one through four active charts without defining those counts as the only product layouts.

Acceptance:

- Charts can be added/removed within the supported capacity and the grid reflows without losing per-chart state.
- Explicit column arrangements preserve the same chart-state model.
- Active chart is visually and semantically explicit.
- Resize does not create chart recreation loops.

### OTT-4.2 — Link groups

Allow independent linking by instrument, interval, crosshair, and visible range.

Acceptance:

- Linking one property does not force the others.
- Synchronization is loop-safe.
- A chart may join or leave a group without losing local state.

### OTT-4.3 — Crosshair and range mapping

Acceptance:

- Crosshair mapping uses timestamp, not pixels.
- Different bar densities and missing timestamps do not throw.
- Range synchronization works across compatible different intervals.

## Phase OTT-5 — Watchlists, workspaces, revisions, and recovery

### OTT-5.1 — Watchlists

Acceptance:

- Create, rename, reorder, and delete watchlists.
- Watchlists reference canonical instruments, not provider symbols.
- Quotes display provider binding and freshness state.
- Switching a provider binding does not create a duplicate watchlist entry.
- Revision conflicts are recoverable.

### OTT-5.2 — Saved workspaces

Persist layout, chart instruments and bindings, intervals, link groups, chart types, panel visibility, indicators, and drawing references.

Acceptance:

- Reload restores the exact workspace.
- Autosave is debounced.
- Multiple tabs cannot silently overwrite each other.
- IndexedDB preserves only unsaved draft recovery state.

## Phase OTT-6 — Beta indicators

Implement SMA, EMA, and RSI using versioned specifications and frontend calculation.

Acceptance:

- Calculations run outside expensive render loops.
- Warm-up and missing-bar behavior are documented.
- Golden fixtures cover known inputs and expected outputs.
- RSI pane remains synchronized with the price chart.
- Changing a parameter updates without recreating the chart.

Before alerts or backend research consumes these indicators, add a Python implementation passing the same fixtures.

## Phase OTT-7 — Beta drawing engine and qualification

### OTT-7.1 — Horizontal and trend lines

Beta requires:

- create
- select
- drag and resize
- delete
- persist
- undo and redo

Advanced snapping, style management, locking, and hiding move to Technical Analysis MVP.

Acceptance:

- Pointer movement updates local draft state only.
- Persistence occurs on pointer release or debounce.
- Drawings survive reload, resize, zoom, pan, timeframe changes, and provider-binding changes.
- Instrument-scoped visibility is the default.
- Drawing revision conflicts are recoverable.

### OTT-7.2 — Charting Beta qualification

Required evidence:

- four charts × 5,000 bars × three indicators
- crosshair update p95 target below 32 ms, revised only with documented spike evidence
- no chart recreation during ordinary bar updates
- no finalized-bar duplicates after ten reconnect cycles
- exact gap recovery after simulated disconnects
- less than 10% retained-heap growth after fifty workspace switches, revised only with documented baseline evidence
- one upstream subscription for identical chart streams
- drawing coordinates unchanged after repeated resize/reload cycles
- visual regression coverage for selected drawings, handles, panes, and active-chart focus
- synthetic tests for duplicates, corrections, out-of-order events, and partial candles
- keyboard and screen-reader paths for core workflows
- PostgreSQL revision-conflict coverage

Passing OTT-7 produces **crypto-only Charting Beta**. Experimental stocks, alerts, scanners, replay, backtesting, paper simulation, and AI remain blocked until this gate passes.

## Phase OTT-8 — Experimental stocks and additional providers

### OTT-8.1 — Yahoo-derived equity adapter

Add yfinance/direct Yahoo paths with explicit personal/local and unofficial labeling.

Acceptance:

- AAPL, SPY, and NVDA resolve to provider-independent canonical equity instruments.
- Yahoo symbols are provider bindings, not instrument IDs.
- Session-correct bars are returned.
- Adjustment mode is visible and cannot silently change.
- Exchange timezone and calendar are retained.
- Stock polling never claims consolidated real-time coverage.

### OTT-8.2 — Stooq fallback

Fallback may replace a complete eligible dataset.

Acceptance:

- Yahoo and Stooq bind to the same canonical instrument where appropriate.
- Requested/resolved binding and fallback reason are visible.
- Dataset fingerprint changes when source changes.
- Drawings and watchlist ownership remain attached to the instrument.
- Yahoo and Stooq bars are never silently spliced.

### OTT-8.3 — Additional crypto providers

Add Coinbase, Kraken, and optionally Hyperliquid in narrow provider-specific PRs.

Acceptance:

- Canonical instruments prevent venue/type collisions.
- Each provider declares policy, capability, history, and rate limits.
- Provider-specific symbols do not reach the canonical instrument contract.

## Phase OTT-9 — Technical Analysis MVP

Add:

- flexible multi-chart and multi-panel arrangements, including horizontal and vertical splits
- bar, area, and baseline chart types
- MACD, Bollinger Bands, ATR, and anchored VWAP
- indicator presets
- vertical line, ray, rectangle, Fibonacci retracement, text, and measurement
- advanced snapping, style management, locking, hiding, and drawing management
- snapshots and exports

Acceptance:

- Every feature has a real implementation and tests.
- TypeScript/Python indicator parity exists before backend consumers use a formula.
- Advanced drawings pass the same coordinate-stability tests as Beta drawings.
- Unsupported prototype chart styles remain hidden.

Passing OTT-9 produces **Technical Analysis MVP**.

## Phase OTT-10 — Alerts

Create dedicated PostgreSQL alert and evaluation tables.

Support price crossing, percent change, indicator threshold/crossing, and volume conditions.

Acceptance:

- Alerts reference canonical instruments and explicit provider/evaluation policy.
- Alerts run server-side when the browser is closed.
- Alert state is deduplicated and restart-safe.
- Partial bars trigger only when policy explicitly allows them.
- Notifications identify instrument, condition, provider/feed, source time, and evaluation time.

## Phase OTT-11 — Scanner

Implement deterministic backend scans over normalized snapshots.

Acceptance:

- Scanner formulas reuse versioned indicator specifications.
- Incremental per-instrument progress and matched-result evidence are persisted while a run is executing.
- A queued/running scan survives gateway restart and resumes only instruments that do not already have persisted completion evidence.
- Cancellation is persisted and reconciled to a terminal cancelled state before or after restart.
- Per-run concurrency remains bounded and all runs share explicit process-wide/global and per-provider concurrency budgets.
- Duplicate retries or recovery cannot duplicate completed instrument progress or scanner results.
- Results show provider and freshness metadata.
- Rate limits and scan universe sizes are bounded.

## Phase OTT-12 — Replay and deterministic backtesting

### Replay

Acceptance:

- Replay uses a frozen ordered dataset.
- Pause, step, speed, and reset are deterministic.
- No future bars leak into indicator state.

### Backtesting

Create dedicated run/trade metadata tables and BlobStore artifacts for large outputs.

Acceptance:

- Strategies declare formula version and parameters.
- Commission, slippage, warm-up, fill timing, and position sizing are explicit.
- Ending cash, ending position, and the ending mark price are explicit.
- Open positions are marked under a disclosed deterministic mark-to-market policy.
- Realized and unrealized P&L reconcile to total economic P&L.
- Re-running economically identical input produces the same deterministic economic-result fingerprint independent of run ID, wall-clock run timestamps, or artifact storage identity.
- Trade log, equity curve, drawdown, win rate, and exposure are available.

## Phase OTT-13 — Paper simulation

Create dedicated transactional tables for accounts, orders, fills, positions, balances, and ledger entries.

Acceptance:

- Paper positions reference canonical instruments, not data providers.
- Paper state is separate from real brokerage concepts.
- Orders validate quantity, side, type, and optional prices.
- Open BUY orders reserve buying power and open SELL orders reserve position quantity so pending orders cannot double-spend either resource.
- Reusing an idempotency key with a different semantic order payload is rejected; an identical retry is harmless.
- Limit and stop simulation evaluates normalized observation high/low ranges when available and uses deterministic configured trigger-price fills.
- Cancellation, rejection, and fill release or consume reservations atomically with order/balance/position/ledger state.
- Fills and ledger updates are atomic.
- P&L is reproducible from persisted fills and marks.
- Reset/archive operations are explicit.
- No route can submit a live broker order.

## Phase OTT-14 — Omnix market research

Integrate optional read-only analysis through the existing Omnix provider/model registry.

Model context may include instrument metadata, current interval, bounded recent bars, indicator values, user-selected drawings/levels, and provider/freshness status.

Acceptance:

- No direct LM Studio-specific client is introduced.
- Structured outputs are validated.
- Prompt size is bounded.
- Claims identify source data and as-of time.
- Invalid model output cannot create an alert, backtest, or paper order without explicit user action and contract validation.

## Phase OTT-15 — Final hardening and release certification

### Accessibility

- keyboard access to toolbar, charts, drawers, watchlists, and drawing controls
- visible focus and active-chart state
- labels for icon-only controls
- reduced-motion support
- accessible non-visual summaries for critical values

### Performance and reliability

- long-running live stream qualification
- provider throttling and outage tests
- cache corruption recovery
- PostgreSQL revision-conflict tests
- listener/subscription leak testing
- bounded memory for inactive workspaces
- restart/recovery and shared-budget qualification for scanner execution

### Security and legal

- no secrets in frontend payloads or logs
- provider terms references and use-scope labels
- Lightweight Charts attribution verification
- retained MIT notices for migrated code
- no claims of redistribution rights unsupported by provider policy

### Release gate

The program is release-ready when:

- Charting Beta and Technical Analysis MVP gates have passed
- required frontend, backend, API, persistence, streaming, Playwright, accessibility, and performance suites pass on the exact immutable pull-request head
- PostgreSQL is the sole user-state authority
- provider source and freshness are visible throughout the product
- all displayed controls are functional
- no live-execution path exists
- operator documentation covers provider behavior, cache cleanup, diagnostics, known limitations, and local qualification

## 11. Recommended pull-request sequence

1. ADR, migration inventory, charting feasibility spike, benchmark evidence, and spike exit decision
2. Trading module shell, focus mode, gateway registration, and diagnostics
3. PostgreSQL repositories and canonical instrument/provider-binding OpenAPI contracts
4. Binance historical provider and cache/coalescing
5. Single historical/live chart
6. Binance shared streaming and exact gap recovery
7. Flexible multi-chart layout and synchronization
8. Watchlists, workspace revisions, and draft recovery
9. SMA, EMA, RSI, and golden fixtures
10. Beta horizontal/trend-line drawing engine
11. Crypto-only Charting Beta qualification and release notes
12. Experimental Yahoo equity adapter
13. Stooq fallback and provider provenance
14. Additional crypto providers
15. Advanced indicators, panes, chart types, and drawing management
16. Technical Analysis MVP qualification
17. Alerts
18. Scanner
19. Replay and backtesting
20. Paper simulation
21. Omnix market research
22. Final release certification

Each PR must be narrow, preserve existing Omnix gates, regenerate OpenAPI types when contracts change, and include tests for the behavior it introduces.

## 12. Success definition

The program succeeds when Omnix provides a reliable local-first trading research workstation in which users can:

- inspect canonical crypto and equity instruments with explicit data provenance
- switch provider bindings without duplicating watchlists or losing drawings
- use flexible synchronized multi-chart workspaces without instability
- receive and recover live crypto updates without gaps or duplicates
- save revisioned watchlists and workspaces
- calculate trustworthy indicators
- create and persist real chart drawings
- add advanced analysis features without changing underlying instrument truth
- run alerts, restart-safe scans, replay, backtests, and paper simulations deterministically
- optionally ask local models for bounded, read-only research

The product should feel visually comparable to a modern trading workstation while remaining honest about provider limitations, licensing scope, delayed data, and unsupported capabilities.
