# Omnix Trading Terminal — Final Implementation Roadmap

**Status:** Final roadmap, ready for implementation review  
**Target route:** `/trading`  
**Target module name:** `Trading`  
**Roadmap branch:** `agent/trading-terminal-roadmap`  
**Reference prototype:** `autonomxDeveloper/tradingview-mcp`  
**Primary chart renderer candidate:** TradingView Lightweight Charts  
**Product posture:** local-first market research and paper simulation; no live brokerage execution

## 1. Program objective

Build a native Omnix market-analysis workspace that provides a credible TradingView-style experience for stocks and crypto while remaining consistent with Omnix architecture, persistence, design, diagnostics, and provider governance.

The product must support a dense multi-chart workspace, live crypto data, historical candles, linked charts, real drawing tools, indicators, watchlists, saved workspaces, alerts, replay, backtesting, paper simulation, and optional local-LLM research. These capabilities are delivered incrementally; the first useful release is intentionally smaller than the final workstation.

The existing `tradingview-mcp` repository is a validated prototype and code donor. It is not a runtime dependency. Omnix owns the UI, API contracts, PostgreSQL persistence, provider lifecycle, cache policy, streaming behavior, tests, diagnostics, and release qualification.

## 2. Final product decisions

1. **Native Omnix module.** Trading uses the existing React application, Omnix shell, TanStack Router, Mantine appearance system, TanStack Query, Zustand conventions, typed OpenAPI client, gateway, diagnostics, PostgreSQL authority, and test infrastructure.
2. **No MCP runtime dependency.** Do not embed the MCP server, standalone FastAPI workstation, standalone Vite application, Claude/OpenClaw integration, or direct LM Studio calls from the prototype.
3. **Charting feasibility comes first.** A disposable but production-shaped spike must prove multi-chart rendering, panes, drawing interaction, streaming recovery, and lifecycle cleanup before the full architecture is frozen.
4. **PostgreSQL is authoritative.** Workspaces, watchlists, drawings, indicator presets, alerts, backtest metadata, and paper state must not use mutable JSON files as production authority.
5. **Caches are disposable.** A bounded `resources/cache/trading/` directory may hold fetched market data and recovery snapshots, but cached candles are never authoritative user data.
6. **Provider-neutral contracts.** The frontend consumes normalized instruments, bars, quotes, and stream events. It never parses raw Yahoo, Binance, Coinbase, Kraken, Hyperliquid, or other provider payloads.
7. **Instrument identity is explicit.** A display symbol such as `BTCUSDT` is not a canonical identifier. Venue, instrument type, provider symbol, currencies, session policy, price scale, and minimum tick are first-class fields.
8. **Real features only.** Unsupported chart styles, indicators, drawing tools, live labels, or order controls are hidden or marked `Planned`; they are never simulated as functional.
9. **Research before execution.** Initial releases support charting, alerts, replay, backtesting, and paper simulation. Live broker execution requires a separate reviewed program.
10. **Provider use is an executable policy.** Personal-use, internal-use, external-display, official API, redistribution, authentication, delay, and terms metadata are exposed by each provider adapter and surfaced in the UI.
11. **No silent provider mixing.** A fallback may replace an entire requested dataset, but bars from different providers are never spliced into one series without an explicit reconciliation design.
12. **Drawings are instrument-scoped by default.** Major levels survive timeframe changes unless an optional interval visibility mask restricts them.
13. **Indicator definitions are versioned.** Frontend and backend implementations must share formula specifications and golden fixtures before indicators are used by alerts, scanners, replay, or backtesting.
14. **Incremental delivery.** Every phase is independently reviewable and testable. The charting beta is a hard gate before alerts, scanning, replay, paper trading, or AI research.
15. **Attribution and licensing are preserved.** Lightweight Charts attribution remains compliant, and substantial MIT-licensed code migrated from the prototype retains the required notice.

## 3. Delivery milestones

### Milestone A — Architecture proven

Phases `OTT-0` and `OTT-1` prove the chart renderer, drawing interaction model, live-data lifecycle, Omnix integration points, persistence ownership, and canonical contracts.

### Milestone B — Charting Beta

Phases `OTT-2` through `OTT-7` deliver the first useful product:

- Binance crypto data and streaming
- one- and four-chart layouts
- synchronized crosshair and visible range
- watchlists and saved workspaces
- candlestick, line, and volume
- SMA, EMA, and RSI
- horizontal and trend lines
- provider provenance and reconnect recovery

### Milestone C — Technical Analysis MVP

Phases `OTT-8` and `OTT-9` add experimental stocks, more providers, advanced indicators, panes, drawing tools, chart styles, and stronger data fallback.

### Milestone D — Market Research Suite

Phases `OTT-10` through `OTT-13` add alerts, scanner, replay, deterministic backtesting, and paper simulation.

### Milestone E — Omnix Intelligence and release hardening

Phases `OTT-14` and `OTT-15` add optional local-LLM research, accessibility, performance certification, provider documentation, licensing checks, and final release gates.

## 4. Scope

### 4.1 Charting Beta scope

- Native `/trading` Omnix module
- Sidebar navigation entry
- Dedicated focus mode that can collapse the Omnix shell for maximum chart area
- Binance spot historical and live candles
- One experimental Yahoo-derived stock adapter, visibly labeled personal/local use
- One-chart and four-chart layouts
- Candlestick, line, and volume displays
- Symbol, venue/provider, and timeframe selection
- Explicit active chart
- Crosshair and visible-range synchronization
- Watchlists and saved workspaces
- Live crypto reconnect and gap repair
- SMA, EMA, and RSI
- Horizontal line and trend line
- PostgreSQL persistence with revisions
- Provider, source, delay, freshness, cache, and fallback status
- Playwright, API, lifecycle, reconnect, and performance qualification

### 4.2 Technical Analysis MVP scope

- Two-horizontal and two-vertical layouts
- Coinbase, Kraken, and optionally Hyperliquid adapters
- Broader Yahoo/Stooq stock coverage
- Bar, area, and baseline chart types
- MACD, Bollinger Bands, ATR, and explicitly anchored VWAP
- Indicator panes and presets
- Vertical line, ray, rectangle, Fibonacci retracement, text, and measurement tools
- Drawing selection handles, snapping, locking, hiding, delete, undo, and redo
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
- Symbol search, provider/venue selector, timeframe selector, chart type selector, indicator menu, layout selector, link-group controls, undo/redo, snapshot, and fullscreen controls
- Vertical drawing-tools rail beside the chart grid
- One-, two-, and four-chart layouts as milestones permit
- Right drawer with Watchlist, Indicators, Data, and Layout tabs
- Bottom drawer added only when Alerts, Replay, Backtests, Paper, or Logs are implemented
- Clear active-chart focus and keyboard shortcuts
- Dense but readable dark-mode presentation that remains compatible with Omnix appearance settings
- Every chart visibly identifies instrument, venue, provider, freshness, delay, market session, adjustment mode, cache status, and fallback state

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
  TradingSymbolSearch.tsx
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

- Resolve canonical instruments and provider symbols
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
- backtest runs and trade records
- paper accounts, orders, fills, positions, balances, and ledger entries

#### BlobStore

Use BlobStore for:

- chart snapshots
- exported research packets
- immutable backtest reports
- large equity curves or trade-log artifacts

#### Disposable cache

Use a bounded cache such as:

```text
resources/cache/trading/
```

for provider responses and recovery snapshots only. Cache entries have TTL, provider identity, dataset fingerprint, and explicit stale state. They are safe to delete at any time.

## 7. Canonical contracts

### 7.1 Instrument identity

```text
instrument_id
asset_class
instrument_type
venue
provider
provider_symbol
display_symbol
base_currency
quote_currency
exchange_timezone
session_calendar
price_scale
minimum_tick
status
```

Examples of distinct instruments:

```text
crypto:BINANCE:spot:BTCUSDT
crypto:BINANCE:perpetual:BTCUSDT
crypto:HYPERLIQUID:perpetual:BTC
stock:NASDAQ:equity:AAPL
```

Aliases may resolve to canonical instruments, but aliases are never stored as authority.

### 7.2 Bar contract

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
source_revision
received_at
```

Rules:

- Intraday timestamps are UTC internally.
- Daily equity bars retain exchange-session semantics.
- Raw, split-adjusted, and dividend-adjusted prices are never mixed.
- Partial streaming candles use `is_final: false`.
- Backend calculations use `Decimal` or scaled integers where precision matters.
- Cache keys include provider, canonical instrument, interval, adjustment mode, and session policy.
- Bars are strictly ordered and contain no duplicate start times.

### 7.3 Dataset provenance

Every historical response includes:

```text
requested_provider
resolved_provider
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

### 7.4 Provider policy

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

### 7.5 Drawing model

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

Drawings are instrument-scoped across intervals by default. `interval_visibility` is optional.

### 7.6 Indicator specification

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
- Historical and streaming updates use the same canonical bar model
- Partial and finalized bars are distinguishable
- Reconnect cannot silently skip finalized bars
- Identical chart subscriptions share one upstream subscription
- Crosshair and visible-range synchronization are timestamp-based and loop-safe
- Drawings use stable time/price coordinates
- Drawings survive zoom, pan, resize, reload, and allowed interval changes
- Pointer movement does not write to PostgreSQL on every frame
- Unsupported functionality is not presented as working
- Cached and fallback data are visibly identified
- Provider errors do not erase the last valid chart state
- Provider changes visibly reload and relabel the complete dataset
- Secrets never appear in browser payloads, logs, fixtures, or diagnostics
- AI research remains read-only unless a later paper-simulation contract explicitly allows writes

## 10. Implementation phases

---

## Phase OTT-0 — ADR, source inventory, and charting feasibility spike

### OTT-0.1 — Architecture decision record

Document:

- native Omnix ownership
- Lightweight Charts as renderer candidate rather than interaction framework
- PostgreSQL authority
- cache policy
- canonical instrument/bar identity
- no-live-execution boundary
- prototype migration and attribution policy

Acceptance:

- The ADR names the owner of every runtime concern.
- No standalone app or MCP dependency is planned.
- Production authority and disposable cache are explicitly separated.

### OTT-0.2 — Prototype migration inventory

Classify prototype code as:

- migrate with attribution
- rewrite for Omnix
- reference only
- reject

Review at minimum:

- stock and crypto services
- cache service
- symbol/timeframe validators
- React chart component
- UI store
- watchlist/workspace/drawing services
- tests and fixtures

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
- A written decision confirms the renderer and drawing approach are viable or selects an alternative.

The spike is a go/no-go gate. Provider expansion and advanced UI work do not begin until it passes.

---

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
- `npm run api:check` or equivalent drift validation passes.
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

Define experimental but typed contracts for instruments, bars, provider policy, provenance, streams, layouts, link groups, drawings, and indicator instances.

Acceptance:

- Spot and perpetual crypto instruments cannot collide.
- Raw and adjusted equity bars cannot be mixed.
- Partial/final bars are explicit.
- OpenAPI generation produces frontend types.
- Contract fixtures cover stocks and crypto.

---

## Phase OTT-2 — Binance provider and market-data foundation

### OTT-2.1 — Binance historical adapter

Migrate or rewrite the validated Binance candle logic.

Acceptance:

- BTC, ETH, and SOL spot instruments resolve canonically.
- Pagination returns ordered, duplicate-free bars.
- Responses contain provider policy and dataset provenance.
- Cancellation, timeout, throttling, and bounded retry are covered.

### OTT-2.2 — Cache and request coalescing

Implement bounded memory and disposable disk cache.

Acceptance:

- Concurrent identical requests share one upstream call.
- Cached data is never labeled live.
- Cache keys include provider, instrument, interval, adjustment, and session policy.
- Cache deletion does not remove user state.

### OTT-2.3 — Binance streaming

Implement shared subscriptions, partial/final bar updates, reconnect, and REST gap recovery.

Acceptance:

- Two charts requesting the same stream create one upstream subscription.
- Reconnect repairs every missing finalized bar.
- Out-of-order and duplicate events do not corrupt the series.
- Subscription status is visible in diagnostics.

---

## Phase OTT-3 — Single historical and live chart

### OTT-3.1 — Chart adapter and lifecycle

Wrap Lightweight Charts behind an Omnix adapter.

Acceptance:

- Candlestick, line, and volume are supported.
- All series, observers, listeners, and subscriptions are cleaned up.
- Ordinary updates do not recreate the chart.
- Required attribution is present.

### OTT-3.2 — Single-chart workflow

Implement instrument search, interval selection, provider display, loading, empty, stale, cached, disconnected, and error states.

Acceptance:

- Users can move between BTCUSDT, ETHUSDT, and SOLUSDT.
- Live and historical bars reconcile without duplicates.
- A recoverable provider failure keeps the last valid chart visible.
- Provider/source/freshness information is always readable.

---

## Phase OTT-4 — Four-chart layout and synchronization

### OTT-4.1 — Layout and active-chart model

Support one-chart and four-chart layouts for Beta.

Acceptance:

- Layout changes preserve per-chart state.
- Active chart is visually and semantically explicit.
- Resize does not create chart recreation loops.

### OTT-4.2 — Link groups

Allow independent linking by:

- instrument
- interval
- crosshair
- visible range

Acceptance:

- Linking one property does not force the others.
- Synchronization is loop-safe.
- A chart may join or leave a group without losing its local state.

### OTT-4.3 — Crosshair and range mapping

Acceptance:

- Crosshair mapping uses timestamp, not pixels.
- Different bar densities and missing timestamps do not throw.
- Range synchronization works across compatible different intervals.

---

## Phase OTT-5 — Watchlists, workspaces, revisions, and recovery

### OTT-5.1 — Watchlists

Acceptance:

- Create, rename, reorder, and delete watchlists.
- Watchlist instruments use canonical IDs.
- Quotes display provider and freshness state.
- Revision conflicts are recoverable.

### OTT-5.2 — Saved workspaces

Persist:

- layout
- chart instruments and intervals
- link groups
- chart types
- panel visibility
- indicators
- drawings references

Acceptance:

- Reload restores the exact workspace.
- Autosave is debounced.
- Multiple tabs cannot silently overwrite each other.
- IndexedDB preserves only unsaved draft recovery state.

---

## Phase OTT-6 — Beta indicators

Implement SMA, EMA, and RSI using versioned specifications and frontend calculation.

Acceptance:

- Calculations run outside expensive render loops.
- Warm-up and missing-bar behavior are documented.
- Golden fixtures cover known inputs and expected outputs.
- RSI pane remains synchronized with the price chart.
- Changing a parameter updates without recreating the chart.

Before alerts or backend research consumes these indicators, add a Python implementation passing the same fixtures.

---

## Phase OTT-7 — Beta drawing engine and qualification

### OTT-7.1 — Horizontal and trend lines

Implement:

- creation
- selection
- handles
- drag and resize
- style edit
- lock/hide/delete
- undo/redo
- snap modes

Acceptance:

- Pointer movement updates local draft state only.
- Persistence occurs on pointer release or debounce.
- Drawings survive reload, resize, zoom, pan, and timeframe changes.
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

Passing OTT-7 produces **Charting Beta**. Alerts, scanners, replay, backtesting, paper simulation, and AI remain blocked until this gate passes.

---

## Phase OTT-8 — Experimental stocks and additional providers

### OTT-8.1 — Yahoo-derived stock adapter

Add yfinance/direct Yahoo paths with explicit personal/local and unofficial labeling.

Acceptance:

- AAPL, SPY, and NVDA return session-correct bars.
- Adjustment mode is visible and cannot silently change.
- Exchange timezone and calendar are retained.
- Stock polling never claims consolidated real-time coverage.

### OTT-8.2 — Stooq fallback

Fallback may replace a complete eligible dataset.

Acceptance:

- Requested/resolved provider and fallback reason are visible.
- Dataset fingerprint changes when source changes.
- Yahoo and Stooq bars are never silently spliced.

### OTT-8.3 — Additional crypto providers

Add Coinbase, Kraken, and optionally Hyperliquid in narrow provider-specific PRs.

Acceptance:

- Canonical instruments prevent venue/type collisions.
- Each provider declares policy, capability, history, and rate limits.
- Provider-specific symbols do not reach the UI contract.

---

## Phase OTT-9 — Technical Analysis MVP

Add:

- two-horizontal and two-vertical layouts
- bar, area, and baseline chart types
- MACD, Bollinger Bands, ATR, and anchored VWAP
- indicator presets
- vertical line, ray, rectangle, Fibonacci retracement, text, and measurement
- advanced snapping and drawing management
- snapshots and exports

Acceptance:

- Every feature has a real implementation and tests.
- TypeScript/Python indicator parity exists before backend consumers use the formula.
- Advanced drawings pass the same coordinate-stability tests as Beta drawings.
- Unsupported prototype chart styles remain hidden.

Passing OTT-9 produces **Technical Analysis MVP**.

---

## Phase OTT-10 — Alerts

Create dedicated PostgreSQL alert and evaluation tables.

Support:

- price crossing
- percent change
- indicator threshold/crossing
- volume conditions

Acceptance:

- Alerts run server-side when the browser is closed.
- Alert state is deduplicated and restart-safe.
- Partial bars trigger only when policy explicitly allows them.
- Notifications identify instrument, condition, provider, source time, and evaluation time.

---

## Phase OTT-11 — Scanner

Implement deterministic backend scans over normalized snapshots.

Acceptance:

- Scanner formulas reuse versioned indicator specifications.
- Progress and cancellation use Omnix jobs/events where appropriate.
- Results show provider and freshness metadata.
- Rate limits and scan universe sizes are bounded.

---

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
- Re-running the same strategy over the same dataset fingerprint produces the same result.
- Trade log, equity curve, drawdown, win rate, and exposure are available.

---

## Phase OTT-13 — Paper simulation

Create dedicated transactional tables for accounts, orders, fills, positions, balances, and ledger entries.

Acceptance:

- Paper state is separate from real brokerage concepts.
- Orders validate quantity, side, type, and optional prices.
- Fills and ledger updates are atomic.
- P&L is reproducible from persisted fills and marks.
- Reset/archive operations are explicit.
- No route can submit a live broker order.

---

## Phase OTT-14 — Omnix market research

Integrate optional read-only analysis through the existing Omnix provider/model registry.

Model context may include:

- instrument metadata
- current interval
- bounded recent bars
- indicator values
- user-selected drawings/levels
- provider and freshness status

Acceptance:

- No direct LM Studio-specific client is introduced.
- Structured outputs are validated.
- Prompt size is bounded.
- Claims identify the source data and as-of time.
- Invalid model output cannot create an alert, backtest, or paper order without explicit user action and contract validation.

---

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

### Security and legal

- no secrets in frontend payloads or logs
- provider terms references and use-scope labels
- Lightweight Charts attribution verification
- retained MIT notices for migrated code
- no claims of redistribution rights unsupported by provider policy

### Release gate

The program is release-ready when:

- Charting Beta and Technical Analysis MVP gates have passed
- required frontend, backend, API, persistence, streaming, Playwright, accessibility, and performance suites pass on the exact head
- PostgreSQL is the sole user-state authority
- provider source and freshness are visible throughout the product
- all displayed controls are functional
- no live-execution path exists
- operator documentation covers provider behavior, cache cleanup, diagnostics, known limitations, and local qualification

## 11. Recommended pull-request sequence

1. ADR, migration inventory, and charting feasibility spike
2. Trading module shell, focus mode, gateway registration, and diagnostics
3. PostgreSQL repositories and canonical OpenAPI contracts
4. Binance historical provider and cache/coalescing
5. Single historical/live chart
6. Binance shared streaming and exact gap recovery
7. Four-chart layout and synchronization
8. Watchlists, workspace revisions, and draft recovery
9. SMA, EMA, RSI, and golden fixtures
10. Horizontal/trend-line drawing engine
11. Charting Beta qualification and release notes
12. Experimental Yahoo stock adapter
13. Stooq fallback and provider provenance
14. Additional crypto providers
15. Advanced indicators, panes, chart types, and drawings
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

- inspect stocks and crypto with explicit data provenance
- use one or four synchronized charts without instability
- receive and recover live crypto updates without gaps or duplicates
- save revisioned watchlists and workspaces
- calculate trustworthy indicators
- create and persist real chart drawings
- add advanced analysis features without changing the underlying instrument/bar truth
- run alerts, scans, replay, backtests, and paper simulations deterministically
- optionally ask local models for bounded, read-only research

The product should feel visually comparable to a modern trading workstation while remaining honest about provider limitations, licensing scope, delayed data, and unsupported capabilities.