# TradingView parity roadmap: feature gaps and the plan to close them

Date: 2026-10-08. Baseline branch: `architecture-hardening` (commit `08cae4129`). Revision 3: applies two code reviews and the owner's decisions D-1 and D-2 (see §11).

Goal:

> **A trader who knows TradingView can do the same analysis, alerting, replay, scripting and paper-trading work in Omnix, with the same tools, shortcuts and workflow, without missing a feature they use daily.**

TradingView features come from its public documentation (features page, plan comparison, Advanced Charts and Trading Platform docs, Help Center) and from inspecting the TradingView Desktop 3.4.1 package (see §10). Omnix status comes from a code search of `web/src/features/trading` and `src/app/apps/trading` on the baseline branch, checked a second time by a review. Rows still marked *verify* need a hands-on check in the running app, done in TVP-0.1.

TradingView is a reference for **features and behaviour only**. No TradingView code, assets, icons or text are copied into Omnix. Omnix implements each feature its own way, on its own stack (lightweight-charts 5, React, FastAPI, PostgreSQL).

---

## Contents

1. [What parity means here](#1-what-parity-means-here)
2. [Gap inventory](#2-gap-inventory)
3. [Architecture constraints found during the audit](#3-architecture-constraints-found-during-the-audit)
4. [Rules of engagement](#4-rules-of-engagement)
5. [Program structure](#5-program-structure)
6. [Work packages](#6-work-packages)
   - [TVP-0 — Foundations](#phase-tvp-0--foundations)
   - [TVP-1 — Alerts](#phase-tvp-1--alerts)
   - [TVP-2 — Keyboard and chart workflow](#phase-tvp-2--keyboard-and-chart-workflow)
   - [TVP-3 — Drawing tools](#phase-tvp-3--drawing-tools)
   - [TVP-4 — Multi-chart, tabs and windows](#phase-tvp-4--multi-chart-tabs-and-windows)
   - [TVP-5 — Watchlists](#phase-tvp-5--watchlists)
   - [TVP-6 — Indicators](#phase-tvp-6--indicators)
   - [TVP-7 — Paper trading and chart trading](#phase-tvp-7--paper-trading-and-chart-trading)
   - [TVP-8 — Bar Replay](#phase-tvp-8--bar-replay)
   - [TVP-9 — Screener and heatmaps](#phase-tvp-9--screener-and-heatmaps)
   - [TVP-10 — Research data](#phase-tvp-10--research-data)
   - [TVP-11 — User scripts](#phase-tvp-11--user-scripts)
7. [Decisions](#7-decisions)
8. [Out of scope](#8-out-of-scope)
9. [Progress](#9-progress)
10. [Sources](#10-sources)
11. [Revision history](#11-revision-history)

---

## 1. What parity means here

**In scope:** everything a single trader uses inside the TradingView app: charts, drawings, indicators, scripts, alerts, watchlists, screeners, replay, paper and chart trading, research panels, layouts, tabs, windows and shortcuts.

**Parity level per feature:**

| Level | Meaning |
|---|---|
| **Equivalent** | Same capability and same interaction model (shortcut, gesture, menu location). Default target. |
| **Functional** | Same capability, Omnix-native interaction. Used when copying the interaction would conflict with Omnix UX or authority rules. |
| **Excluded** | Not pursued (§8): social network, community script library, broker marketplace, data we can't license. |

**Usage tier per feature** (used to prioritise and to report progress, §9):

| Tier | Meaning | Examples |
|---|---|---|
| **Daily** | Most active traders use it every session | Trend line, parallel channel, long/short position, price alerts, watchlist sections, hotkeys |
| **Weekly** | Common but not constant | Fib extension, pitchfork, multi-condition alerts, replay, screener |
| **Rare** | Specialist or niche | Fib spiral, Gann square, stickers, on-chain metrics, options strategy builder |

**Where Omnix deliberately differs:**

- **Live order authority.** TradingView lets any user trade live from the chart. In Omnix, live execution belongs to deterministic strategies through the order gateway (AGENTS.md). Chart trading parity applies to **paper** accounts. Manual live trading from the chart is decision D-7 and is not in this roadmap.
- **User scripts never gain order authority.** Scripts produce indicators, alerts and backtest evidence only. Strategy scripts can drive paper accounts at most.
- Omnix's own strengths (Hermes research, automated trade review, trade journal, strategy evidence, kill switches, execution observation) stay. Parity work must not regress them.

---

## 2. Gap inventory

Status key: **Have** · **Partial** · **Missing**. The WP column says which work package closes the gap.

### 2.1 Summary

| Area | Omnix today | TradingView | Main WPs |
|---|---|---|---|
| Chart types | 21 | 21 | — |
| Charts per tab | 16 (12 tabs) | 16 | — |
| Drawing tools | 14 | 110+ | TVP-3 |
| Built-in indicators | 125 of 208 tracked | ~208 + community | TVP-6 |
| User scripts | Read-only source viewer | Pine Script IDE, strategies, screener | TVP-11 |
| Alert conditions | 15 condition types, 3 frequencies, 3 channels (sound plays nothing); none fire on the baseline (§2.6) | 13 operators on any source, 4 frequencies, push/email/webhook, watchlist and multi-condition | TVP-1 |
| Keyboard shortcuts | Command layer (TVP-0.3) with drawing undo/redo/delete; Escape/Enter; watchlist keys | ~70 | TVP-2 |
| Watchlists | Multiple lists, add/remove/reorder, sections, colour flags, columns and sorting, `.txt` import/export, keyboard navigation | Sections, flags, columns, import/export, advanced view | TVP-5 |
| Screener fields | 7 metrics × 4 operators | 400+ fields, 6 screeners, heatmaps | TVP-9 |
| Replay | Start bar, step, one 9-speed control, one replay clock for all charts, jump to bar, trading | 9 speeds, sub-bar update interval, synced multi-chart | TVP-8 |
| Paper trading | Market, limit, stop, stop-limit, trailing stop, DAY/GTC/GTD, long-side brackets, commission/slippage bps, server-side shorting (nothing can turn it on) | + shorting, leverage, margin calls, drag-to-modify | TVP-7 |
| Research data | News (no economic calendar, see §2.12) | + economic calendar, financials, options, seasonals, macro, heatmaps | TVP-10 |
| Windows | Tabs in one browser tab | Tabs, multiple windows, colour link groups | TVP-4 |

### 2.2 Charts and layouts

**Have:** all 21 chart types (`TRADING_CHART_TYPE_OPTIONS` in `chart/chartAdapter.ts`); 16 charts per tab and 12 tabs; symbol, interval, crosshair and visible-range sync (`links` in `tradingStore.ts`); tick, second, minute, hour, day, week, month and range intervals; compare and spread/formula symbols; log, percent and inverted scales; timezone selector; PNG snapshot download; undo/redo; object tree; indicator presets; save, load, rename and delete layouts; workspace JSON export. `TradingCommandCenter` is a strategy operations panel, not a command palette (TVP-0.3 finding).

| Gap | Tier | Status | WP |
|---|---|---|---|
| Selective link groups (some charts linked, by colour), across tabs | Daily | Missing | TVP-4.1 |
| Click-to-sync time across charts | Weekly | Partial | TVP-4.2 |
| Drawing sync toggle (drawings already shared per symbol) | Weekly | Partial | TVP-3.8 |
| Custom intervals (type any value, e.g. `7m`, `3h`) | Weekly | Missing | TVP-2.5 |
| Countdown to bar close on the price scale | Daily | Missing | TVP-2.5 |
| Go to date (jump to a bar) | Weekly | Partial | TVP-2.5 |
| Copy chart image; copy snapshot link | Weekly | Missing | TVP-2.5 |
| Duplicate layout | Weekly | Missing | TVP-2.5 |
| Maximise / collapse pane by double-click | Daily | Partial (a header button focuses one chart and panes have fullscreen/minimise buttons; no double-click gesture) | TVP-2.5 |
| Pre/post-market toggle and price line | Daily | Partial | TVP-2.5 |
| Chart templates | Weekly | Partial | TVP-2.5 |
| Market status and data-delay marker in legend | Daily | Partial (feed-status dot; freshness only in a tooltip; no market open/closed status) | TVP-2.5 |
| Command palette (quick search) | Daily | Missing | TVP-2.1 |
| Workspace JSON import (export exists) | Rare | Missing | unassigned |

### 2.3 Drawing tools

**Have (14):** trend line, ray, horizontal line, horizontal ray, vertical line, cross line, arrow, rectangle, circle, ellipse, fib retracement, text, measurement, dot. Also eraser, lock/hide, magnet snapping (time/price/OHLC), colour, undo, trendline alerts. Width and dash styles are stored and drawn but have no editor (Partial, TVP-0.4). All rendering is in one 649-line SVG component (`drawings/TradingDrawingOverlay.tsx`).

| Missing group | Tools | Tier | WP |
|---|---|---|---|
| Lines and channels | Info line, extended line, trend angle, parallel channel, regression trend, flat top/bottom, disjoint channel, anchored VWAP | Daily | TVP-3.1 |
| Positions and measurement | Long position, short position, position forecast, bars pattern, ghost feed, sector, date range, price range, date and price range, fixed range volume profile | Daily (long/short, ranges); rest weekly | TVP-3.6 |
| Fibonacci | Trend-based fib extension, fib channel, fib time zone, trend-based fib time, fib speed resistance fan, fib speed resistance arcs, fib circles, fib spiral, fib wedge | Weekly (extension, time zone); rest rare | TVP-3.2 |
| Annotations | Note, anchored note, callout, comment, signpost, price label, price note, arrow mark up/down/left/right, arrow marker, flag mark, icons, emojis | Weekly (note, price note, callout); rest rare | TVP-3.5 |
| Shapes and freehand | Brush, highlighter, path, polyline, curve, double curve, triangle, rotated rectangle, arc | Weekly (brush, highlighter, path); rest rare | TVP-3.4 |
| Pitchforks and Gann | Pitchfork, Schiff, modified Schiff, inside pitchfork, pitchfan, Gann box, Gann square fixed, Gann square, Gann fan | Weekly (pitchfork); rest rare | TVP-3.3 |
| Patterns and cycles | XABCD, Cypher, ABCD, triangle pattern, three drives, head and shoulders, Elliott impulse/correction/triangle/double combo/triple combo, cyclic lines, time cycles, sine line | Rare | TVP-3.7 |
| Tool behaviour | Drawing templates, favourites toolbar, multi-select, copy/paste/clone, hide all, lock all, per-interval visibility, Shift to constrain angle, keyboard nudge | Daily | TVP-3.8, TVP-2.2 |

### 2.4 Indicators

`indicators/tradingViewBuiltIns.ts` tracks 208 TradingView built-ins. **125 are available:**

- **100 calculated from bars in the browser:** 9 native aliases plus 91 `SUPPORTED` entries. Standard technical analysis is covered.
- **25 backed by external data** (`indicators/externalIndicatorData.ts`, served by `metric_data.py` through `/metrics`):
  - 14 Binance futures series: open interest, funding, basis, mark/index price, premium, long/short ratios, liquidations;
  - 3 Yahoo equity series: analyst forecast, price target, dividend yield;
  - 8 Bitcoin on-chain series from blockchain.info.

These external-data indicators exist only in the browser path. The server's alerts and scanner can't use them yet (see §3).

**83 are not available yet:** 1 partial, 28 missing and 54 waiting on a decision.

| Missing group | Count | Data available? | Tier | WP |
|---|---|---|---|---|
| OHLCV-only, wrongly listed as data-dependent: Rob Booker ADX Breakout, Knoxville Divergence, Intraday Pivot Points, Missed Pivot Points, Reversal, Ziv Ghost Pivots; Relative Volume at Time; Correlation Coefficient; 24-hour Volume | 9 | Yes | Weekly | TVP-6.1 |
| Need a chart renderer: Auto Fib Retracement/Extension, Auto Pitchfork, Auto Trendlines (Partial: the Auto Trend Detector chart pattern draws one trend), Auto key levels, Bollinger Bars, Chop Zone, Trading Sessions, Seasonality, Visible Average Price, VWAP Auto Anchored, Multi-Time Period Charts, Moon Phases | 13 | Yes | Weekly | TVP-6.2 |
| Intrabar volume: Volume Delta, Cumulative Volume Delta | 2 | Needs a new intrabar loader (none exists; footprint is synthetic) | Weekly | TVP-6.4 |
| Market breadth: Advance/Decline Line, Advance/Decline Ratio, Advance/Decline Ratio (Bars), Cumulative Volume Index | 4 | Derived from Alpaca SIP (§7.2) | Weekly | TVP-6.6 |
| Seasonals guide ("Learn using seasonals"), delivered by the Seasonality indicator and the seasonals panel | 1 | Yes | Weekly | TVP-6.2, TVP-10.3 |
| Other crypto data: Ethereum staking and deposits, address balances, UTXO detail, gas, SOPR, realized cap, RVT, stock-to-flow, power-law model, ETF flows and balances, El Salvador balance | 54 | Needs an on-chain provider (pending D-4) | Rare | TVP-6.7 |

Also missing: candlestick pattern recognition (TVP-6.3, weekly) and indicator-on-indicator (TVP-6.5, weekly).

### 2.5 User scripts (Pine Script equivalent)

| Gap | Tier | Status | WP |
|---|---|---|---|
| Write and run your own indicators | Daily | Missing (`TradingPinePanel` is read-only) | TVP-11.1–11.3 |
| Editor: autocomplete, inline errors, hints | Daily | Missing | TVP-11.2 |
| Script versions | Weekly | Missing | TVP-11.3 |
| Script alerts (`alertcondition`, `alert()`) | Daily | Missing | TVP-11.4 |
| Strategy tester for scripts | Weekly | Missing (Omnix strategies are Python with their own backtester) | TVP-11.5 |
| Script screener | Rare | Missing | TVP-11.6 |
| Profiler and logs | Weekly | Missing | TVP-11.2 |

### 2.6 Alerts

**Have:** price above/below, percent change, volume above/below; indicator above/below/cross for 8 indicators; trendline crossing/up/down/above/below; frequencies `once`, `once_per_bar`, `every_time` plus cooldown; expiration; custom message; in-app and toast delivery; alert manager and log. Alerts are evaluated server-side (`alerts_monitor.py`), but nothing leaves the process. On the baseline they never fire: the lifecycle trigger from `0027_trading_alert_lifecycle_history.sql` reverts the evaluator's own state update, so the condition types count as partial in the ledger until the TVP-1.2 fix merges.

| Gap | Tier | Status | WP |
|---|---|---|---|
| Webhook delivery | Daily | Missing | TVP-1.2 (channel schema), TVP-0.5a |
| Frequency: once per bar close | Daily | Missing | TVP-1.1 |
| Frequency: once per minute | Weekly | Partial (cooldown) | TVP-1.1 |
| Entering / exiting / inside / outside channel | Weekly | Missing | TVP-1.2 |
| Moving up/down by amount or % within N bars | Weekly | Partial | TVP-1.2 |
| Alerts on any indicator and any output line | Daily | Partial (8) | TVP-1.3 |
| Alerts on horizontal lines/rays, rectangles, channels, fib levels | Daily | Missing | TVP-1.4 |
| Message placeholders (`{{ticker}}`, `{{close}}`, …) | Daily | Missing (messages are stored and shown verbatim) | TVP-1.5 |
| Sound delivery | Daily | Partial (the channel can be chosen, but no code plays a sound) | TVP-1.5 |
| Email and browser/OS push delivery | Weekly | Missing | TVP-0.5b, TVP-0.5c, TVP-1.5 |
| Multi-condition alerts (up to 5) | Weekly | Missing | TVP-1.2 (schema), TVP-1.6 |
| Watchlist alerts (one alert over a whole list) | Weekly | Missing | TVP-1.7 |
| Alerts on script conditions | Daily | Missing | TVP-11.4 |

### 2.7 Keyboard shortcuts

The command layer exists (TVP-0.3: command catalogue, dispatcher, key overrides, conflict checks) and runs drawing undo (Ctrl+Z), redo (Ctrl+Shift+Z) and delete. Dialogs bind Escape/Enter, and the watchlist grid binds its own navigation keys (TVP-5.3). Most shortcuts are still missing (TVP-2), all daily tier:

- **Chart:** type to change symbol; digits to change interval; `/` indicators; Ctrl+K quick search; Ctrl+S save layout; `.` load layout; Ctrl+Y redo; ←/→ one bar; Ctrl+←/→ further; Ctrl+↑/↓ zoom; Alt+G go to date; Alt+S snapshot; Alt+R reset; Alt+I invert; Alt+L log; Alt+P percent; Alt+A add alert; Ctrl+/ shortcut list.
- **Drawing:** Alt+T, Alt+H, Alt+V, Alt+C, Alt+F, Alt+Shift+R; Ctrl+C/V; Ctrl+drag clone; Ctrl+click multi-select; Ctrl+Alt+H hide all; arrows nudge; Shift constrains.
- **Layout:** Tab/Shift+Tab switch chart; Alt+Enter maximise; Alt+W add to watchlist.
- **Watchlist (Have, TVP-5.3):** ↑/↓ or Space/Shift+Space move; Shift+↑/↓ extend selection; Ctrl+A select all.
- **Tabs:** Ctrl+T new; Ctrl+U duplicate; Ctrl+Tab / Ctrl+PgDn next; Ctrl+1–8 go to tab; Ctrl+9 last; Ctrl+Shift+T reopen closed.
- **Trading:** Shift+B / Shift+S market buy/sell; Shift+Alt+B/S limit.

Notes from the TVP-0.1 verification:
- Alt+R, Alt+I, Alt+L, Alt+P, Alt+A and the drawing keys Alt+T, Alt+H, Alt+J, Alt+V, Alt+C, Alt+F, Alt+Shift+R are shown as hints in menus, but nothing binds them.
- Ctrl+Y redo is partial: redo is bound to Ctrl+Shift+Z.

### 2.8 Watchlists

**Have:** multiple watchlists; add, remove and reorder; logos; symbol intelligence panel.

| Gap | Tier | Status | WP |
|---|---|---|---|
| Sections (named, collapsible) | Daily | Have | TVP-5.1 |
| Colour flags (7) and flagged lists | Daily | Have (flagging from the chart and screener is a follow-up) | TVP-5.1 |
| Column choice and sorting | Daily | Have (indicator columns are a follow-up) | TVP-5.2 |
| Import/export `.txt` | Weekly | Have | TVP-5.3 |
| Keyboard navigation | Daily | Have | TVP-5.3 |
| Advanced view (overview, earnings, dividends, news tabs) | Weekly | Partial | TVP-5.4 |
| Sync across tabs and windows | Daily | Missing | TVP-4.1, TVP-4.3 |

### 2.9 Screener

| Gap | Tier | Status | WP |
|---|---|---|---|
| Metrics beyond close, % change, volume, SMA, EMA, RSI, ATR | Daily | Missing | TVP-9.1 |
| Fundamental fields | Weekly | Missing | TVP-9.1 |
| Result columns, sorting, saved screens | Daily | Partial | TVP-9.1 |
| Auto-refresh (10 s / 1 min) | Daily | Missing | TVP-9.2 |
| Heatmaps (stocks by sector, crypto) | Weekly | Missing | TVP-9.3 |
| Natural-language screener | Weekly | Missing | TVP-9.4 |

### 2.10 Bar Replay

**Have:** select start, step forward/back, autoplay, reset, exit, trading during replay.

| Gap | Tier | Status | WP |
|---|---|---|---|
| One consistent speed control (9 speeds) | Weekly | Have | TVP-8.1 |
| Multi-chart sync (one replay clock for all charts) | Weekly | Have | TVP-8.1 |
| Update interval (sub-bar playback, down to 1 s) | Weekly | Missing | TVP-8.1 |
| Jump to bar during playback; jump to real time | Weekly | Have | TVP-8.1 |
| Replay shortcuts | Weekly | Missing | TVP-8.1 |

### 2.11 Paper trading and chart trading

**Have:**
- multiple paper accounts with custom starting cash;
- market, limit and stop orders (`paper.py`);
- commission, slippage and stop slippage in basis points per account (`paper.py`);
- OCO stop-loss/take-profit protection for long positions (`paper_protection.py`);
- server-side short positions (`0036_trading_paper_short_positions.sql`, the `allow_short` account column from `0121_trading_order_gateway.sql`, buy-covers-short logic in `paper_repository.py`);
- order ticket with risk-based sizing;
- Depth of Market;
- positions drawn on the chart;
- order history CSV export.

| Gap | Tier | Status | WP |
|---|---|---|---|
| Turning shorting on: `allow_short` is not in `PaperAccountCreate` (`paper.py`) or the paper API, and the web sends only `initial_cash` (`tradingPaperApi.ts`), so nothing writes the column | Daily | Partial | TVP-7.2a |
| Short-side stop-loss/take-profit (`paper_protection.py` has no short handling) | Daily | Missing | TVP-7.2a |
| Shorting in replay backtests: `backtest.py` supports `allow_short`, but the web hardcodes `allow_short: false` in the backtest `execution_policy` (`tradingReplayApi.ts`) | Weekly | Missing | TVP-7.2a |
| Leverage per asset class and margin % for longs and shorts | Weekly | Missing | TVP-7.2b |
| Margin calls (forced partial or full liquidation) | Weekly | Missing | TVP-7.2b |
| Fixed-amount commission per order (only % today) | Weekly | Missing | TVP-7.2b |
| Stop-limit orders | Daily | Have | TVP-7.1 |
| Trailing stop | Daily | Have | TVP-7.1 |
| Time in force (DAY / GTC / GTD) | Weekly | Have | TVP-7.1 |
| Drag orders and brackets on the chart | Daily | Missing | TVP-7.3 |
| Price-scale "+" menu to place orders | Daily | Missing | TVP-7.3 |
| Buy/sell buttons in the chart legend | Daily | Missing | TVP-7.3 |
| Trading hotkeys | Daily | Missing | TVP-7.4 |
| Trading notifications on chart and notifications log | Weekly | Partial (the ticket shows a confirmation toast for its own orders; fills, rejects and protective exits are not announced on the chart; no notifications log) | TVP-7.4 |

### 2.12 Research data

**Have:** news; analyst targets and dividend yield (Yahoo); SEC filings in research (`research/adapters/sec_edgar.py`).

| Gap | Tier | Status | WP |
|---|---|---|---|
| Economic calendar | Weekly | Missing (none exists; the "prospective" side tab is the prospective economic-SHADOW strategy panel) | TVP-10.5 |
| Earnings and dividends calendar, chart markers | Weekly | Partial | TVP-10.1 |
| Financial statements and ratios panel | Weekly | Missing | TVP-10.2 |
| Seasonals | Rare | Missing | TVP-10.3 |
| Options chain, Greeks, volatility curves, strategy builder | Rare | Excluded pending D-6 | TVP-10.4 |
| Macro: yield curves, economic indicators, maps | Rare | Missing | TVP-10.5 |

### 2.13 Tabs, windows and app shell

| Gap | Tier | Status | WP |
|---|---|---|---|
| Open a layout in a new window | Weekly | Missing | TVP-4.3 |
| Full multi-window (pop out tabs, move them between windows) | Rare | Missing | TVP-4.6 |
| Reopen closed tab; duplicate tab | Weekly | Missing | TVP-4.4 |
| New-tab launcher (open a saved layout or tool) | Weekly | Missing | TVP-4.4 |
| Unsaved-changes prompt on close | Weekly | Partial | TVP-4.4 |
| Installable app (own window, taskbar icon, OS notifications) | Weekly | Missing | TVP-4.5 |

---

## 3. Architecture constraints found during the audit

These shape the foundations phase. Ignoring them would mean building the same thing several times.

1. **Three indicator paths.**
   - About 100 indicators are calculated in the browser (`indicators/*.ts`, in a worker), using JavaScript 64-bit floats.
   - 25 data-backed indicators are fetched in the browser from `/metrics`.
   - The server has 8 indicators in `src/app/apps/trading/indicators/engine.py`, using `Decimal`. Server-side alerts, the scanner and strategies use only those.

   Alerts on any indicator (TVP-1.3), screener metrics (TVP-9.1) and script `ta.*` functions (TVP-11.1) all need server-side values that match the chart. → **TVP-0.2.** `engine.py` is part of strategy evidence and stays unchanged; the new server registry is separate.
2. **Drawings are one hand-written SVG component.** Adding ~95 tools as more branches would not scale, and SVG DOM per point would hurt freehand tools. lightweight-charts 5 has canvas series and pane primitives. → **TVP-0.4** builds a tool registry with renderer-agnostic geometry and decides the renderer with a spike.
3. **Alert conditions and notification channels are closed lists** (a database `CHECK` constraint and `Literal`s in `alerts.py`). `0036_trading_trendline_alerts.sql` is the precedent for replacing the constraint. TVP-1.2 makes the one schema change that serves TVP-1.2, 1.3, 1.4, 1.6 and the new delivery channels (TVP-0.5a–c, 1.5).
4. **No notification delivery at all.** There is no service worker, web push, email or webhook sender in the repo. Credential encryption (`app.security.provider_secret_store`) and outbound URL policy (`app.security.url_policy`) exist and are reused. → **TVP-0.5a–c.**
5. **Watchlists, drawings, layouts and indicator presets are versioned JSON documents** (`register_documents` in `api.py`). Most watchlist and drawing features need no migration, but they do need payload schema versions and upgrade functions.
6. **No keyboard command layer anywhere in `web/src`.** `@mantine/hooks` 9 is already a dependency. → **TVP-0.3.**
7. **Live execution authority is narrow by design** (AGENTS.md). All new order features target paper accounts.
8. **No intrabar data on the web side.** The volume footprint is synthesised from bars (`syntheticBar` in `chartAdapter.ts`). Volume delta, sub-bar replay and bar-close alert accuracy need a lower-timeframe loader that respects the provider request budget. → **TVP-0.6.**
9. **Yahoo endpoints are unofficial.** They already back fundamentals, analyst targets and search. Parity work should not add new Yahoo dependencies (§7.2).
10. **One script runtime.** D-1 (Pine-compatible scripts) needs scripts on the server for alerts with the browser closed. Writing the interpreter twice is the most expensive option, so scripts run only on the server (D-9). The browser keeps its fast built-in indicators, and the server's registry is shared by alerts, the screener and scripts.

---

## 4. Rules of engagement

1. **AGENTS.md invariants hold.**
   - Research and scripts never gain trading execution authority.
   - LLM output is a proposal; deterministic code decides.
   - PostgreSQL is authoritative for alert, delivery and order state.
   - Schema changes need a forward migration under `src/app/apps/trading/migrations` plus persistence tests. Two existing migrations share the number `0036`. This roadmap's migrations use the reserved range 0140–0179, assigned per WP and checked again before merge; the doc cites migrations by full filename.
   - Order work changes paper behaviour only. A WP that touches `order_gateway.py` or `execution*.py` is out of scope unless D-7 is decided.
   - Changing defaults must not change the behaviour of existing paper accounts, especially strategy-owned ones.
2. **Clean-room implementation.** Use TradingView's public docs and the app's visible behaviour as the spec. Do not copy TradingView code, icons, images, sounds or help text. Name things in Omnix terms where a TradingView name is a trademark: the product is "Omnix Scripts", described as Pine-compatible.
3. **One source of truth per calculation.** An indicator, alert condition or drawing level is defined once and verified on every engine that computes it, with shared golden fixtures (TVP-0.2).
4. **Generated contracts stay in sync.** Regenerate OpenAPI types when backend models change (`npm --prefix web run api:check`).
5. **Validation is local.** For each WP run:
   - focused pytest files and `ruff check` on changed Python paths;
   - `npm --prefix web run test -- <focused tests>`, `typecheck` and `build` for web changes;
   - the indicator golden suites (TVP-0.2) whenever indicator, alert or script maths changes;
   - a manual check of the feature in the running app for UI work.

   Do not wait on GitHub Actions.
6. **Ratchet the ledger.** Each WP updates the parity ledger (TVP-0.1). The count of missing **daily and weekly** items never goes up.
7. **PR size.** About 1,500 changed lines or fewer, excluding generated files and fixtures. Tool batches (TVP-3) and indicator ports (TVP-0.2) split into several PRs.
8. **Log decisions** in [DECISIONS.md](../roadmap/DECISIONS.md), in its "TradingView parity roadmap" section, under their `TVP-` or `D-` id.

**Size key:** S ≈ 1–3 days, M ≈ 1–2 weeks, L ≈ 3–5 weeks, XL ≈ 6+ weeks, for one engineer with agent help.

---

## 5. Program structure

```
TVP-0.1 ledger ─────────────────────────────────────────────────────────────────────────► (every WP updates it)
TVP-0.2 server indicator registry ─► TVP-1.3 indicator alerts ─► TVP-9.1 screener metrics
          (first batch: ~20)        └► TVP-6.5 indicator-on-indicator    └► TVP-11.1 script ta.* functions
TVP-0.3 command/hotkey layer ─► TVP-2 shortcuts ─► TVP-7.4 trading hotkeys, TVP-8.1 replay keys
TVP-0.4 drawing registry + renderer spike ─► TVP-3.1 … TVP-3.8 ─► TVP-1.4 drawing alerts
                                                               └► TVP-6.2 indicators that draw
TVP-1.2 (condition + channel schema) ─► TVP-0.5a outbox + webhook ─► TVP-1.5 channel UI ◄─ TVP-0.5b email, TVP-0.5c web push ─► TVP-4.5 installable app
                                     └► TVP-1.6 multi-condition ─► TVP-1.7 watchlist alerts (also needs TVP-5.1)
TVP-0.6 intrabar loader ─► TVP-6.4 volume delta, TVP-8.1 sub-bar replay
TVP-1.1 (no deps)
TVP-4.1 link groups ─► TVP-4.3 open in new window ─► TVP-4.6 full multi-window (deferred)
TVP-7.1 orders ─► TVP-7.2a shorting ─► TVP-7.2b leverage/margin calls
                                   └► TVP-7.3 chart trading (needs a chart-handle primitive, not the drawing registry)
TVP-11.0 spike (needs TVP-0.2 first batch) ─► TVP-11.1 interpreter ─► 11.2 editor, 11.3 storage ─► 11.4 alerts, 11.5 strategies ─► 11.6 screener
```

**Waves (by daily-use value per unit of effort):**

| Wave | WPs | Why |
|---|---|---|
| 1 | TVP-0.1, 0.3, 1.2 → 0.5a, 0.2 (first batch), 1.1, 2.1, 2.3–2.5, 5.1–5.3, 7.1, 8.1 (speed and sync part) | Small, used every day; webhooks make server alerts useful; 0.2 is the longest pole and starts now |
| 2 | TVP-0.2 (rest), 0.4, 0.5b, 0.6, 1.3, 1.5, 1.6, 2.2, 3.1, 3.6, 3.8, 4.1, 6.1, 7.2a, 9.4, 11.0 | Foundations, the most-used drawing tools, shorting, cheap Hermes screener, script spike |
| 3 | TVP-0.5c, 1.4, 1.7, 3.2–3.5, 3.8, 4.2–4.5, 7.2b, 7.3, 7.4, 8.1 (rest), 9.1, 9.2, 11.1–11.3 | Fill out drawings, alerts and chart trading; margin modelling; scripts on charts |
| 4 | TVP-3.7, 5.4, 6.2–6.6, 9.3, 10.1–10.3, 11.4, 11.5 | Depth: auto-drawings, intrabar, breadth, research panels, script alerts and strategies |
| 5 | TVP-4.6, 6.7, 10.4, 10.5, 11.6 | Rare-tier or vendor-gated |

**Wave 1 is not fully parallel.** It holds about six M-sized items for one engineer, and two chains are serial:

- **TVP-0.3 → TVP-2.1, 2.3, 2.4.** The shortcuts need the command layer first. TVP-2.5 doesn't depend on it except for its Alt+G binding.
- **TVP-1.2 → TVP-0.5a.** Webhooks need the channel schema.

The rest of wave 1 (0.1, 0.2 first batch, 1.1, 5.1–5.3, 7.1, 8.1 speed and sync) can run alongside those chains. TVP-2.2 moved to wave 2 because it needs the drawing registry (TVP-0.4).

---

## 6. Work packages

### Phase TVP-0 — Foundations

#### TVP-0.1 — Parity ledger and verification pass

- **Goal:** a machine-readable ledger of every TradingView feature in §2, its Omnix status, usage tier and WP, so progress is measurable.
- **Steps:**
  1. Create `docs/trading/tradingview-parity.json`. Each entry has:
     - `area`, `feature`;
     - `tier`: `daily`, `weekly` or `rare`;
     - `status`: `have`, `partial`, `missing`, `excluded`, or `excluded-pending-decision` for items gated on D-4, D-6 or another vendor decision;
     - `level`: `equivalent` or `functional`;
     - `wp`;
     - `evidence` (file or test).
  2. Do the hands-on *verify* pass for every *verify* row in §2 in the running app, and correct the statuses.
  3. Add `scripts/tradingview_parity_report.py`. It prints counts per area and tier, and fails if a `have` entry has no evidence.
  4. Rename the "Pine Script source" label in `TradingPinePanel.tsx` to "Script source (Pine-compatible)", in line with the naming rule in §4.
- **Acceptance:** the report matches §2 after verification. §9 shows the counts by tier.
- **Size:** S.

#### TVP-0.2 — Server indicator registry with shared goldens

- **Goal:** the server computes chart indicators with the same results as the browser, so alerts, the screener and scripts can use them.
- **Design decisions:**
  - **Runtime:** Python on the server, no Node sidecar (D-9). The same answer applies to scripts (TVP-11).
  - **Numbers:** the registry uses plain Python `float`, the same IEEE 754 doubles as JavaScript, and follows the browser's order of operations, so results match the chart. Vectorised numpy (already a dependency in `requirements/gateway.in`) would change the order of operations, so it isn't used for these calculations. `engine.py` (`Decimal`) stays as it is for strategies.
  - **Goldens:** fixtures in `resources/trading/indicator_goldens/` (bar series with gaps, flat bars, zero volume and short histories), generated from the TypeScript engine and checked by both test suites. Tolerance by class:
    - non-recursive (SMA, WMA, Bollinger, Donchian, …): 1e-12 relative;
    - recursive or smoothed (EMA, RSI, ATR, Wilder-smoothed, adaptive): 1e-9 relative, compared after a warm-up of 3 × period bars;
    - transcendental (`exp`, `log`, `pow`): 1e-12 relative, because platform maths libraries may differ in the last bit.
  - **Registry:** `src/app/apps/trading/indicators/registry.py` maps an indicator id to inputs, outputs and the compute function, using the same ids as `TRADINGVIEW_BUILTIN_DEFINITIONS`. External-data indicators register an adapter that calls `metric_data.py`, so server alerts can use them too. `CORE_INDICATOR_FORMULA_VERSION` becomes a shared constant checked by both sides.
- **Steps:**
  1. Golden generator (TypeScript, run with the web test tooling) and the fixture format.
  2. **First batch (wave 1):** the ~20 indicators most used in alerts and screens (SMA, EMA, WMA, VWMA, RSI, MACD, Stochastic, Stoch RSI, Bollinger, ATR, ADX/DMI, CCI, MFI, OBV, VWAP, Supertrend, Parabolic SAR, Williams %R, ROC, Ichimoku).
  3. Switch `alerts_monitor._indicator_value` and `scanner.py` to the registry.
  4. Remaining indicators in batches of about 20, one PR each with goldens.
- **Tests:** web and Python golden suites; a test that lists which `available: true` indicators have a server implementation (the list may only grow).
- **Acceptance (first batch):** goldens pass on both engines for the first batch, and existing alert and scanner tests pass unchanged. **Acceptance (complete):** every available indicator has a server implementation.
- **Size:** L in total; the first batch is M.

#### TVP-0.3 — Command and shortcut layer

- **Goal:** every user action is a named command that can be bound to keys, listed in a shortcut dialog and run from the command center.
- **Design:**
  - The layer lives in `web/src/features/trading/commands/`. It moves to `web/src/shared` when a second app needs it.
  - Built on `@mantine/hooks` (`useHotkeys`, `getHotkeyHandler`) for key parsing and platform keys (Ctrl vs ⌘).
  - A registry of commands: `id`, `label`, `defaultKeys`, `when` context (chart focused, drawing selected, watchlist focused, dialog open) and `run`.
  - One dispatcher resolves the active context and ignores text inputs.
  - User overrides are stored in the trading settings document.
- **Tests:** dispatch by context; inputs ignored; overrides win; a test fails if two commands share a key in the same context.
- **Acceptance:** the existing undo and command-center handlers run through the layer with no behaviour change.
- **Size:** M.

#### TVP-0.4 — Drawing tool registry and renderer decision

- **Goal:** adding a drawing tool means adding one definition file, and the renderer suits 110+ tools including freehand.
- **Design:** a `DrawingToolDefinition` per tool:
  - anchor count and creation gesture (click-click, click-drag, freehand, N points);
  - renderer-agnostic geometry (anchors → lines, polygons, arcs, text, fills in time/price space), used for rendering, hit-testing and alert levels;
  - property schema (colours, levels, extend left/right, labels, text) driving a generic settings dialog;
  - optional `alertLevels()` for TVP-1.4.

  `TradingDrawingOverlay.tsx` becomes a generic host for input, selection, handles, snapping and undo. The drawing document payload gets a `schemaVersion` and an upgrade for existing drawings.
- **Renderer spike:** while migrating the 14 existing tools, build two of them (trend line and a brush prototype) as lightweight-charts 5 series primitives (canvas). Compare frame time with 500 drawings and 5,000-point freehand strokes against the current SVG. Record the choice in DECISIONS.md. Switching now is cheapest, before 95 more tools exist.
- **Tests:** per-tool geometry and hit-test unit tests; a document upgrade test from the current payload; visual check of all 14 tools.
- **Acceptance:** existing drawings load and look the same; the host has no tool-specific code; the renderer decision is logged.
- **Size:** L.

#### TVP-0.5a — Notification outbox and webhooks

- **Depends on:** TVP-1.2, whose migration adds the `webhook` channel and per-channel settings to alerts.
- **Goal:** triggered alerts leave the process reliably, starting with webhooks (Discord, Slack, Telegram bots, automation tools).
- **Design:**
  - **Outbox:** a delivery table (`omnix_trading_notification_deliveries`) with one row per trigger × channel: status, attempts, next attempt time, last error and an idempotency key. A delivery monitor sends with retries and exponential backoff. Triggers stay authoritative, and delivery is at-least-once.
  - **Storage:** webhook URL and secret come from the provider secret store by the alert's key (TVP-1.2). That store is DPAPI-encrypted, which ties webhooks to one Windows user and host; decide before deploying elsewhere whether to move alert credentials to a portable encrypted store.
  - **Webhook rules:**
    - HTTPS only;
    - destinations checked with `app.security.url_policy` after DNS resolution, rejecting private, loopback and link-local addresses unless `OMNIX_ALLOWED_PRIVATE_NETWORKS` allows them;
    - 5 s timeout, no redirects;
    - optional HMAC-SHA256 signature header, with the secret stored through `provider_secret_store`;
    - the body is the alert message, sent as `application/json` when it parses as JSON.
  - **Port:** sending goes behind a `NotificationSender` port so delivery can move to the platform tier later.
- **Tests:** outbox state transitions; retry and backoff; idempotency across restart; URL policy (private IP, DNS rebinding to a private address, redirect refused); signature header; secrets never returned by the API.
- **Acceptance:** a test alert reaches a webhook endpoint, and a failing endpoint is retried and then marked failed.
- **Size:** S–M.

#### TVP-0.5b — Email delivery

- **Goal:** alert emails through user-configured SMTP, with the password encrypted through `provider_secret_store`. Uses the 0.5a outbox.
- **Size:** S.

#### TVP-0.5c — Web push

- **Goal:** browser and OS notifications when Omnix isn't the focused tab.
- **Design:**
  - service worker in `web/public`;
  - VAPID keys from settings;
  - subscriptions stored per user and device;
  - push payloads with no sensitive content beyond the alert name and message;
  - works with sign-in on (authenticated subscription endpoints).
- **Size:** M.

#### TVP-0.6 — Intrabar data loader

- **Goal:** fetch lower-timeframe bars for a range (for example 1 m bars inside a 1 h bar, 1 s inside 1 m), cached, within the provider request budget (`providers/request_budget.py`).
- **Design:** a server endpoint `GET /bars/intrabar?instrument&interval&lower&from&to` that reuses the provider registry and aggregation. A bounded range per request. A browser cache keyed by instrument and lower interval.
- **Used by:** TVP-6.4 (volume delta), TVP-8.1 (sub-bar replay), TVP-1.1 (more accurate bar-close evaluation), and later a real footprint chart.
- **Size:** M.

---

### Phase TVP-1 — Alerts

#### TVP-1.1 — Once per bar close and once per minute

- **Goal:** match TradingView's frequencies: only once, every time, once per bar (intrabar), once per bar close, once per minute.
- **Design:**
  - `trigger_policy` gains `once_per_bar_close` and `once_per_minute`;
  - a bar-close alert is evaluated when the bar for the alert's interval is final (provider bar semantics in `providers/bar_semantics.py`), and the condition must still hold at close;
  - cooldown stays for existing alerts.
- **Migration:** shared with TVP-1.2 if both land together, otherwise its own.
- **Tests:**
  - a condition true intrabar but false at close does not fire;
  - fires once at close;
  - the once-per-minute rate limit holds;
  - no double fire after restart.
- **Size:** S–M.

#### TVP-1.2 — Condition model: operators and child table

- **Goal:** all 13 TradingView operators, on a schema that also serves indicator, drawing and multi-condition alerts with **one** migration.
- **Design:**
  - **Operators:** crossing, crossing up, crossing down, greater than, less than, entering channel, exiting channel, inside channel, outside channel, moving up, moving down, moving up %, moving down %.
  - **Condition shape:** `source`, `operator`, `target`.
    - The source is price, an indicator output (registry id, inputs, output) or a drawing level.
    - The target is a value, a second source, or a channel of two values or sources.
    - Moving operators take an amount and a bar count.
  - **Child table:** conditions live in `omnix_trading_alert_conditions` (ordered, at most 5 per alert).
  - **Channels in the same migration:** `notification_channels` accepts `webhook`, `email` and `push` as well as `app`, `toast` and `sound`. Message, channels and delivery settings live in their own `notification_settings` column, so editing them doesn't reset trigger state. A webhook's URL and signing secret are credentials: both are stored together in the provider secret store under a versioned key, and the alert row keeps only that key, a masked URL and `has_secret`. The API rejects a channel whose sender isn't deployed yet, so TVP-0.5a–c each switch theirs on without another migration.
  - **Migration:** existing alerts become one-condition rows, following the `0036_trading_trendline_alerts.sql` constraint-replacement precedent. The old `condition_type` column stays readable until a later cleanup.
- **Tests:** a truth table per operator, including touches and gaps across a boundary; migration of every existing condition type and channel list; channel settings validation; round-trip through the API.
- **Size:** M.

#### TVP-1.3 — Alerts on any indicator output

- **Depends on:** TVP-0.2 (first batch), TVP-1.2.
- **Goal:** any indicator in the server registry, any output line, with its inputs, as an alert source or target. The dialog lists the indicators on the chart and their outputs. As TVP-0.2 adds indicators, they become alertable without further work.
- **Tests:** create and evaluate for each registered category; invalid input rejected; an indicator the server doesn't have is greyed out with the reason.
- **Size:** M.

#### TVP-1.4 — Drawing alerts

- **Depends on:** TVP-0.4, TVP-1.2.
- **Goal:** alerts from horizontal line, horizontal ray, trend line, ray, extended line, parallel channel, rectangle and fib levels.
- **Design:**
  - the drawing's `alertLevels()` is serialised into the condition (anchor points plus geometry type), so the server computes the level at each bar without the browser;
  - moving a drawing updates its alerts, and deleting it disables them after a prompt.
- **Tests:** server level computation matches the web geometry (shared fixtures); edits propagate.
- **Size:** M.

#### TVP-1.5 — Delivery channels and message placeholders

- **Depends on:** TVP-1.2 (channel schema), TVP-0.5a (webhook); email and push join when TVP-0.5b and 0.5c land.
- **Goal:** per-alert channel selection in the alert dialog (in-app, toast, sound with a choice of sound, webhook, email, push) and message placeholders.
- **Design:**
  - no migration: TVP-1.2 already widened `notification_channels` and added channel settings;
  - placeholders: `{{ticker}}`, `{{exchange}}`, `{{interval}}`, `{{open}}`, `{{high}}`, `{{low}}`, `{{close}}`, `{{volume}}`, `{{time}}`, `{{timenow}}`, `{{plot_N}}` and `{{plot("name")}}` for indicator outputs, and `{{alert_name}}`;
  - unknown placeholders are left as they are.
- **Size:** M.

#### TVP-1.6 — Multi-condition alerts

- **Depends on:** TVP-1.2 (schema already in place).
- **Goal:** up to 5 conditions combined with AND, one frequency and one message.
- **Scope:** evaluator AND logic and the dialog UI only; no migration.
- **Tests:** fires when all are true and not when any is false; once-per-bar-close evaluates all conditions at close.
- **Size:** S–M.

#### TVP-1.7 — Watchlist alerts

- **Depends on:** TVP-1.6, TVP-5.1.
- **Goal:** one alert definition evaluated on every symbol of a watchlist, with per-symbol trigger state.
- **Design:**
  - the alert references the watchlist document id, and membership is read at evaluation time;
  - per-symbol state lives in a child table;
  - bars are fetched with multi-symbol endpoints (Alpaca multi-symbol bars and snapshots; batched crypto requests);
  - the symbol cap is derived from the request budget for the alert's interval and the provider. The default is 100, with a hard maximum computed per provider and shown in the dialog. TradingView's 1,000 is not a target on per-symbol fetches.
- **Tests:** membership changes; per-symbol once semantics; the budget is never exceeded; cap enforcement.
- **Size:** M–L.

---

### Phase TVP-2 — Keyboard and chart workflow

All TVP-2 WPs depend on TVP-0.3.

#### TVP-2.1 — Chart shortcuts

- **Goal:** the chart shortcuts in §2.7.
- **Behaviour:**
  - typing opens symbol search with the typed character;
  - digits open an interval box (`5`, `15`, `1h`, `1D`, `3s`, `100t`);
  - `/` opens the indicator picker;
  - Ctrl+K opens the command center.
- **Tests:** one per command; typing in inputs doesn't trigger them.
- **Size:** M.

#### TVP-2.2 — Drawing shortcuts and editing

- **Depends on:** TVP-0.4.
- **Goal:**
  - the drawing hotkeys;
  - Ctrl+C/V copy and paste, also across charts;
  - Ctrl+drag clone;
  - Ctrl+click multi-select, with group move and delete;
  - arrow-key nudge;
  - Shift to constrain (45°, square, circle);
  - Ctrl+Alt+H hide all.
- **Size:** M.

#### TVP-2.3 — Layout, watchlist and tab shortcuts

- **Goal:** Tab/Shift+Tab chart focus, Alt+Enter maximise, Alt+W add to watchlist, watchlist navigation keys, and the tab shortcuts (new, duplicate, next/previous, go to N, reopen closed).
- **Note:** in a browser, Ctrl+T, Ctrl+W, Ctrl+N and Ctrl+Tab belong to the browser. Bind them only in the installed app (TVP-4.5), and offer Alt-based alternatives in the browser.
- **Size:** S–M.

#### TVP-2.4 — Shortcut dialog and rebinding

- **Goal:** Ctrl+/ opens a searchable list of all shortcuts by context. Keys can be rebound, and conflicts are shown.
- **Size:** S.

#### TVP-2.5 — Chart workflow items

- **Goal:** close the small chart gaps in §2.2:
  - custom intervals (any number with t/s/m/h/D/W/M/R, saved to favourites);
  - countdown to bar close on the price label;
  - go to date (Alt+G), loading history if needed;
  - copy chart image to the clipboard and copy a snapshot link;
  - duplicate layout;
  - double-click to maximise a pane, Ctrl+double-click to collapse;
  - pre/post-market toggle and price line;
  - chart templates (style and indicators without symbol);
  - market status and data-delay marker in the legend.
- **Size:** M (several small PRs).

---

### Phase TVP-3 — Drawing tools

All TVP-3 WPs depend on TVP-0.4. Each tool ships with geometry and hit-test tests and a settings schema, plus keyboard and alert support where they apply. The order follows usage tier.

#### TVP-3.1 — Lines and channels (daily)

- **Tools:** info line, extended line, trend angle, parallel channel, regression trend, flat top/bottom, disjoint channel, anchored VWAP.
- **Notes:** regression trend and anchored VWAP compute from bars. VWAP uses the same formula as the indicator (golden-tested).
- **Size:** M.

#### TVP-3.2 — Fibonacci tools

- **Tools:** trend-based fib extension and fib time zone (weekly); fib channel, trend-based fib time, fib speed resistance fan and arcs, fib circles, fib spiral and fib wedge (rare).
- **Retracement improvements:** editable levels, per-level colours, labels left/right, price or percent display, reverse, and extended lines.
- **Size:** M–L.

#### TVP-3.3 — Pitchforks and Gann

- **Tools:** pitchfork (standard, Schiff, modified Schiff, inside), pitchfan, Gann box (with Shift fixed increments), Gann square fixed, Gann square, Gann fan.
- **Size:** M.

#### TVP-3.4 — Shapes and freehand

- **Tools:** brush, highlighter, path, polyline, curve, double curve, triangle, rotated rectangle, arc.
- **Notes:** freehand strokes are stored as simplified point lists (Ramer–Douglas–Peucker) in time/price space so they stay attached on zoom. Renderer per the TVP-0.4 decision.
- **Size:** M.

#### TVP-3.5 — Annotations

- **Tools:** note, anchored note (fixed to the screen), callout, comment, signpost, price label, price note, arrow marks (up, down, left, right), arrow marker, flag mark, icons and emojis.
- **Notes:** icons and emojis come from an open-licence set (for example Twemoji, CC-BY 4.0, with attribution) or Omnix's own icons. TradingView's sticker artwork is not reproduced.
- **Size:** M.

#### TVP-3.6 — Positions and measurement (daily)

- **Tools:** long position, short position, position forecast, date range, price range, date and price range, bars pattern, ghost feed, sector, fixed range volume profile.
- **Long/short position tools:**
  - show entry, target, stop, risk/reward, quantity (from account size and risk %) and P&L as price moves through;
  - an action pre-fills the paper order ticket with the same entry, stop and target, and the user confirms.
- **Fixed range volume profile:** reuses the existing volume profile computation.
- **Size:** M.

#### TVP-3.7 — Patterns, Elliott waves and cycles (rare)

- **Tools:** XABCD, Cypher, ABCD, triangle pattern, three drives, head and shoulders, Elliott impulse (12345), correction (ABC), triangle (ABCDE), double combo (WXY), triple combo (WXYXZ), cyclic lines, time cycles, sine line.
- **Notes:** harmonic tools show ratio labels between legs.
- **Size:** M–L.

#### TVP-3.8 — Tool behaviour (daily)

- **Goal:**
  - drawing templates per tool;
  - favourites toolbar;
  - "stay in drawing mode";
  - lock all and hide all;
  - per-interval visibility;
  - a drawing sync toggle per layout;
  - object tree grouping, rename and reorder.
- **Size:** M.

---

### Phase TVP-4 — Multi-chart, tabs and windows

#### TVP-4.1 — Colour link groups

- **Goal:** each chart can join one of several colour groups, or none. Charts in a group share symbol and, optionally, interval, across all tabs. The existing whole-tab sync stays as "link all".
- **Design:**
  - the group is stored on the chart in the workspace document;
  - a group bus in the store broadcasts symbol and interval changes;
  - the watchlist and screener send symbols to the focused chart's group;
  - colours come from the Omnix design system.
- **Tests:** a change propagates to group members only, across tabs; no loops; persisted per chart.
- **Size:** M.

#### TVP-4.2 — Time sync

- **Goal:** clicking a bar with time sync on scrolls all linked charts to that time, even when they use different intervals.
- **Size:** S.

#### TVP-4.3 — Open a layout in a new window

- **Depends on:** TVP-4.1.
- **Goal:** "Open in new window" for any layout or tab. Each window is an ordinary Omnix page on that layout.
- **Design:**
  - link groups and watchlists stay consistent through the server documents they already use, by revision polling or the existing stream;
  - alert sounds and toasts play only in the most recently focused window, tracked with `BroadcastChannel`;
  - no window management beyond that.
- **Size:** S.

#### TVP-4.4 — Tab management

- **Goal:**
  - duplicate tab;
  - reopen closed tab (the last 10 in the session);
  - a new-tab launcher listing saved layouts and tools (chart, screener, replay, paper dashboard);
  - an unsaved-changes prompt on close, using the existing draft recovery.
- **Size:** S–M.

#### TVP-4.5 — Installable app

- **Depends on:** TVP-0.5c.
- **Goal:** Omnix trading installs as a desktop app with its own window and taskbar icon, receives OS notifications, and can use the browser-reserved shortcuts (TVP-2.3).
- **Design:** a PWA manifest with a trading start URL, standalone display mode and Omnix icons. Must work with sign-in on, the existing SSE and WebSocket streams, and service-worker scope rules. No native wrapper (D-8).
- **Size:** M.

#### TVP-4.6 — Full multi-window (deferred)

- **Goal:** pop a tab out of a window and move it back, restoring window sets on reload.
- **Design:** `window.open` per popped tab, `BroadcastChannel` coordination, leader election, and reconciliation by document revision.
- **Note:** low value for the cost, because TVP-4.3 covers most of it. Revisit after wave 4.
- **Size:** L.

---

### Phase TVP-5 — Watchlists

#### TVP-5.1 — Sections and colour flags

- **Goal:** named, collapsible sections; 7 colour flags; a generated list per flag colour; flag from chart, watchlist or screener.
- **Design:** watchlist payload `schemaVersion` 2, with ordered items of type `symbol` or `section`; a user-level flags document; an upgrade from version 1.
- **Size:** S–M.

#### TVP-5.2 — Columns and sorting

- **Depends on:** TVP-0.2 for indicator columns.
- **Goal:** sort by any column. Columns can be chosen from:
  - last price, change, change %, volume, relative volume;
  - extended-hours price, high/low;
  - registry indicators.
- **Size:** M.

#### TVP-5.3 — Import, export and keyboard

- **Goal:** import and export `.txt` in `EXCHANGE:SYMBOL` comma-separated format with `###Section` markers, plus keyboard navigation and selection (§2.7).
- **Size:** S.

#### TVP-5.4 — Advanced view and details

- **Depends on:** TVP-10.1.
- **Goal:** a full-width view with overview, performance, earnings, dividends and news tabs, and a richer symbol details panel.
- **Size:** M.

---

### Phase TVP-6 — Indicators

#### TVP-6.1 — Quick-win OHLCV indicators

- **Goal:** the 9 indicators in §2.4 row 1. Correlation Coefficient takes a second-symbol input and loads it like a compare symbol.
- **Steps:** move them to `SUPPORTED` and implement them in the browser and in the server registry, with goldens.
- **Size:** S–M.

#### TVP-6.2 — Indicators that draw

- **Depends on:** TVP-0.4.
- **Goal:**
  - Trading Sessions (shading and labels);
  - Bollinger Bars and Chop Zone (bar and background colouring);
  - Auto Fib Retracement/Extension, Auto Pitchfork, Auto Trendlines and Auto key levels;
  - VWAP Auto Anchored and Visible Average Price (viewport-aware);
  - Multi-Time Period Charts;
  - Seasonality (with TVP-10.3);
  - Moon Phases.
- **Design:** an indicator can return drawing primitives and bar or background colours as well as series. Remove each `SPECIALIZED_REQUIREMENTS` entry as its indicator ships.
- **Size:** L.

#### TVP-6.3 — Candlestick pattern recognition

- **Goal:** detect common candlestick patterns (doji, hammer, engulfing, harami, morning/evening star, three soldiers/crows, …) as chart markers. Each pattern can be enabled on its own and used as an alert source.
- **Size:** M.

#### TVP-6.4 — Volume Delta and Cumulative Volume Delta

- **Depends on:** TVP-0.6.
- **Goal:** both indicators from lower-timeframe bars, with a configurable intrabar timeframe and limits shown when history is too long for the budget.
- **Size:** M.

#### TVP-6.5 — Indicator on indicator

- **Depends on:** TVP-0.2.
- **Goal:** any indicator's "source" input can be another indicator's output on the same chart (RSI of OBV, SMA of RSI), on the chart and in alerts.
- **Design:** a dependency graph per chart, topologically ordered in the worker and in the server evaluator; cycles are rejected.
- **Size:** M.

#### TVP-6.6 — Market breadth

- **Goal:** Advance/Decline Line, Advance/Decline Ratio, Advance/Decline Ratio (Bars) and Cumulative Volume Index for NYSE and Nasdaq, plus the matching breadth columns in the screener.
- **Design:** derived in-house from Alpaca SIP (§7.2):
  - daily breadth from daily bars over the listed universe, refreshed at the close;
  - intraday breadth from multi-symbol snapshots within the request budget;
  - stored as series so alerts and strategies can use them.
- **Size:** M–L.

#### TVP-6.7 — Remaining on-chain and crypto data

- **Gate:** D-4.
- **Goal:** the 55 crypto data series in §2.4, through the adapter pattern in `metric_data.py` and `externalIndicatorData.ts`.
- **Size:** L.

---

### Phase TVP-7 — Paper trading and chart trading

All TVP-7 WPs change **paper** behaviour only. Each includes a regression test that the live order gateway is untouched and that existing accounts behave the same unless their settings are changed.

#### TVP-7.1 — Order types and time in force

- **Goal:** stop-limit, trailing stop (by amount or %, with a server-tracked high/low water mark), and time in force (DAY, GTC, GTD), on standalone orders and as bracket legs.
- **Design:** extend `PaperOrderType` and the fill model in `paper.py`. Persist trailing state so it survives restarts. Add a forward migration for the new columns and constraint.
- **Tests:** fill semantics per type, including gaps through stop and limit; trailing updates; restart recovery; DAY expiry at session close (`us_equity_calendar.py`).
- **Size:** M.

D-2 decided that paper accounts behave like TradingView's paper trading: shorting any instrument; leverage per asset class (stocks, crypto, forex, futures); separate margin % for long and short positions; margin calls that force-close part or all of the positions; commission as % or a fixed amount per order; no borrow fees. It is split in two so the daily-tier part isn't held back by margin modelling.

#### TVP-7.2a — Shorting (daily tier)

- **Goal:** users can short in paper accounts and in replay backtests, with brackets that protect short positions.
- **Steps:**
  1. **Turn shorting on.** The server already holds short positions (`0036_trading_paper_short_positions.sql`), and the `allow_short` column exists (`0121_trading_order_gateway.sql`), but nothing writes it. Add `allow_short` to `PaperAccountCreate` and an account settings update model in `paper.py`, to the paper API, and to the account form (`tradingPaperApi.ts` sends only `initial_cash` today). The model and database default stay `False`, because strategies create paper accounts through the same model (`strategy_managed_finviz_shadow.py`). Only the account **form** defaults the checkbox to on, as in TradingView, and sends `allow_short: true` explicitly. Existing accounts keep their current value.
  2. **Short-side brackets.** Add short handling to `paper_protection.py`: the stop is above entry, the target below, and triggers are mirrored. A buy reduces or covers.
  3. **Replay backtests.** Add an "allow short" option to the replay backtest form, replacing the hardcoded `allow_short: false` in the backtest `execution_policy` (`tradingReplayApi.ts`). `backtest.py` already supports it.
- **Tests:**
  - create and update accounts with and without shorting;
  - a strategy-created account has shorting off;
  - short open, add, reduce and cover;
  - short brackets trigger correctly, including on gaps;
  - existing accounts unchanged;
  - a backtest with shorting on produces short trades.
- **Size:** S–M. **Wave:** 2.

#### TVP-7.2b — Leverage, margin calls and fixed commission (weekly tier)

- **Depends on:** TVP-7.2a.
- **Steps:**
  1. **Leverage and margin.**
     - New per-account settings: `margin_long_pct` and `margin_short_pct` per asset class. The default is 100%, meaning no leverage, so existing accounts are unchanged.
     - Buying power is checked against the margin requirement at order time.
  2. **Margin calls.**
     - On each price update in `paper_monitor.py`, when equity falls below the maintenance requirement, positions are closed by market order until it's met: largest margin use first, partial closes where enough.
     - Fills are recorded with reason `margin_call`, and a notification is sent through the outbox.
  3. **Fixed commission.** Add a commission type (`percent` or `fixed_per_order`) next to `commission_bps`.
- **Migration:** forward migration for the new account columns, with defaults that keep current behaviour.
- **Tests:**
  - leverage changes buying power;
  - margin call closes the minimum needed, in the right order, and is idempotent across restart;
  - strategy-owned accounts are unchanged by the defaults;
  - fixed commission is applied once per order.
- **Size:** M–L. **Wave:** 3.

#### TVP-7.3 — Trading from the chart

- **Depends on:** TVP-7.1, TVP-7.2a.
- **Goal:**
  - drag working orders and bracket legs on the chart to modify them;
  - drag a position's stop or target out of the position line;
  - a price-scale "+" menu to place limit or stop orders;
  - buy/sell buttons with bid/ask in the legend;
  - order and position labels with quantity and P&L.
- **Design:**
  - order and position lines use a thin shared **chart handle** primitive (draggable price line with label), not the drawing registry;
  - every chart action produces the same order request as the ticket, through the same validation;
  - an "instant order placement" setting is off by default; when off, a confirmation dialog shows first.
- **Size:** L.

#### TVP-7.4 — Trading hotkeys and notifications

- **Depends on:** TVP-0.3.
- **Goal:** Shift+B/S market and Shift+Alt+B/S limit at the default quantity, honouring the confirmation setting; on-chart fill, reject and margin-call notifications; a notifications log tab in the terminal dock.
- **Size:** S–M.

---

### Phase TVP-8 — Bar Replay

#### TVP-8.1 — Replay parity

- **Goal:**
  - **one speed control** replacing both current ones (footer select and replay-panel free text), with 9 fixed speeds tuned to feel like TradingView (for example 0.1×, 0.3×, 0.5×, 1×, 3×, 5×, 10×, 30×, 100×);
  - **multi-chart sync** with one replay clock for all charts in the layout, including charts on different intervals;
  - **update interval:** sub-bar playback from lower-timeframe bars (TVP-0.6), down to 1 s where data exists;
  - jump to a new start bar during playback, and jump to real time;
  - replay shortcuts (play/pause, step forward/back).
- **Design:** the replay cursor becomes a timestamp in the store, replacing the per-panel `replayCursorIndex`. Each chart derives its visible bars from the shared clock.
- **Split:** the speed unification and shared clock are wave 1 (M). Sub-bar playback waits for TVP-0.6 (wave 3, M).
- **Size:** L in total.

---

### Phase TVP-9 — Screener and heatmaps

#### TVP-9.1 — Screener fields, columns and saved screens

- **Depends on:** TVP-0.2.
- **Goal:**
  - any registry indicator and output as a filter or column;
  - price, performance (1D–1Y), volume and relative volume, gap %, distance from the 52-week high/low;
  - market cap and fundamental fields from TVP-10.2, and breadth from TVP-6.6;
  - sortable columns and saved screens;
  - send results to a watchlist or a link group.
- **Design:** scanner rules reference registry ids. `ScannerMetric` stops being a closed `Literal` and is validated against the registry.
- **Size:** L.

#### TVP-9.2 — Auto-refresh

- **Goal:** a screen re-runs every 10 s or 1 min while open, within the request budget, and highlights what changed since the previous run.
- **Size:** S–M.

#### TVP-9.3 — Heatmaps

- **Goal:** a stock heatmap (grouped by sector and industry, sized by market cap or volume, coloured by change) and a crypto heatmap, with click-through to the chart.
- **Data:** sector/industry from SEC SIC codes mapped to sectors (§7.2).
- **Size:** M.

#### TVP-9.4 — Natural-language screener

- **Goal:** the user describes a screen in words; Hermes (`hermes_research_api.py`) proposes a screen definition; the user sees and edits the rules before running it.
- **Rule:** the LLM output is only a proposed definition. The deterministic scanner runs it, and nothing runs without the user.
- **Note:** cheap because the research loop exists, and differentiating. Moved to wave 2.
- **Size:** S–M.

---

### Phase TVP-10 — Research data

#### TVP-10.1 — Earnings, dividends and splits

- **Goal:** a calendar view (by day, filterable by watchlist) and chart markers for earnings (E), dividends (D) and splits (S).
- **Data (§7.2):**
  - dividends and splits from Alpaca corporate actions;
  - past earnings dates from SEC 8-K item 2.02 filings;
  - upcoming earnings dates from the vendor chosen in D-5.
- **Size:** M.

#### TVP-10.2 — Financials panel

- **Goal:** income statement, balance sheet and cash flow (quarterly and annual), key ratios and valuation, and any fundamental metric charted as an indicator.
- **Data:** SEC XBRL company facts (§7.2), normalised from `us-gaap` concepts to a fixed set of line items.
- **Size:** L.

#### TVP-10.3 — Seasonals

- **Goal:** a seasonals panel comparing yearly performance curves across years, plus the Seasonality indicator (TVP-6.2).
- **Size:** S–M.

#### TVP-10.4 — Options

- **Gate:** D-6.
- **Goal:** options chain with Greeks and implied volatility; volatility smile per expiration; strategy builder with P&L and Greeks charts and what-if scenarios. Paper options trading is a separate decision.
- **Size:** XL.

#### TVP-10.5 — Macro

- **Goal:** the US Treasury yield curve and other economic series as chart symbols; an economic calendar of past and upcoming releases (weekly tier); plus a map of selected indicators for the countries covered.
- **Data:** FRED (series, and its release calendar `fred/releases/dates` for the economic calendar) and US Treasury (§7.2). Global calendar events need a vendor. Other countries' curves need a vendor and are rare tier.
- **Size:** L.

---

### Phase TVP-11 — User scripts

**Decided (D-1):** Omnix supports a TradingView-compatible subset of Pine Script, so users can paste existing scripts. The product name is "Omnix Scripts", described as Pine-compatible.

**Runtime (D-9, to be confirmed by the TVP-11.0 spike):** scripts run only on the server, in a Python interpreter. The chart sends the script and its inputs and receives plots, shapes and drawings, and the server pushes updates on each new bar through the existing stream. This writes the interpreter once and serves charts, alerts, the screener and strategies from the same code. The cost is server CPU: sign-in is on, so several users may run the same community script on the same symbol. Two controls keep that bounded:
- every run has CPU, memory and bar limits;
- results are cached by script hash, inputs, instrument, interval, last bar and formula version, so identical runs are computed once and new bars extend a cached run incrementally.

#### TVP-11.0 — Spike and language spec

**Done:** the supported subset, results and measurements are in [`OMNIX_SCRIPTS_SPEC.md`](OMNIX_SCRIPTS_SPEC.md).

- **Goal:** prove the runtime choice and fix the supported subset.
- **Steps:**
  1. Write a spec of the supported subset: Pine v5/v6 indicator scripts first; types, series semantics, `var`/`varip`, history references, `na`, the built-in namespaces, and `request.security` limits.
  2. Build a minimal interpreter for the spike.
  3. Use the scripts that `indicators/indicatorPine.ts` generates as a free test corpus. Only indicators with an entry in `indicatorPineTemplates` produce real code; the others produce a comment stub and are skipped. Run each through the interpreter and compare with the native indicator. Then run 20 popular open-source community scripts end to end.
  4. Measure:
     - server time per script per 5,000 bars;
     - incremental time per new bar;
     - the result cache's hit rate and memory with several users loading the same script on the same symbols.
- **Acceptance:**
  - every indicator with a Pine template matches its native indicator within TVP-0.2 tolerances;
  - 15 of the 20 community scripts run unchanged;
  - measured cost, with the cache, fits the per-user limits.

  D-9 is then confirmed or revisited, and the result is logged.
- **Size:** M.

#### TVP-11.1 — Interpreter core

- **Goal:**
  - parser and type checker for the subset;
  - bar-by-bar series execution;
  - built-in namespaces `ta.*`, `math.*`, `str.*`, `array.*`, `map.*` and `input.*`;
  - outputs: `plot`, `plotshape`, `plotchar`, `hline`, `fill`, `bgcolor`, `barcolor`, `label`, `line`, `box`, `table`;
  - `request.security` within the request budget.
- **Design:**
  - `ta.*` functions call the server indicator registry (TVP-0.2), so script and chart indicators agree;
  - incremental execution on new bars;
  - the shared result cache from TVP-11.0;
  - per-run CPU, memory and loop limits;
  - no file, network or OS access from scripts.
- **Size:** XL (several PRs).

#### TVP-11.2 — Editor

- **Goal:**
  - code editor (CodeMirror 6) with syntax highlighting, autocomplete, hover docs and inline errors from the server type checker;
  - add to chart, save, and save as;
  - a console for logs and runtime errors;
  - a simple profiler (time per line, from the server run).
- **Size:** L.

#### TVP-11.3 — Script storage and versions

- **Goal:** scripts as versioned trading documents with history, diff and restore. Scripts can be used in indicator templates and layouts, and exported and imported as text.
- **Size:** M.

#### TVP-11.4 — Script alerts

- **Depends on:** TVP-1.5, TVP-11.1.
- **Goal:** `alertcondition()` conditions appear in the alert dialog, and `alert()` calls trigger alerts with their message. Both are evaluated on the server with the browser closed.
- **Size:** M.

#### TVP-11.5 — Strategy scripts and strategy tester

- **Goal:**
  - `strategy.*` (entries, exits, OCA, pyramiding, commission, slippage);
  - a strategy tester panel (overview, performance summary, list of trades, equity curve, drawdown);
  - deep backtesting over the full stored history;
  - optionally, sending strategy signals to a **paper** account.
- **Rule:** strategy scripts never reach the live order gateway. A script that should trade live has to be re-implemented as a deterministic Omnix strategy through the normal qualification process.
- **Size:** XL.

#### TVP-11.6 — Script screener

- **Depends on:** TVP-9.1, TVP-11.4.
- **Goal:** run an indicator script's condition across a watchlist and list the matches.
- **Size:** M.

---

## 7. Decisions

### 7.1 Decision register

| Id | Decision | Status | Outcome |
|---|---|---|---|
| D-1 | Script language and runtime | **Decided 2026-10-08** | TradingView-compatible (Pine) subset so users can paste existing scripts; product name "Omnix Scripts" |
| D-2 | Paper shorting model | **Decided 2026-10-08** | Like TradingView: short any instrument, leverage per asset class, long/short margin %, margin calls, % or fixed commission, no borrow fees (TVP-7.2a, TVP-7.2b) |
| D-3 | Breadth, classification and macro sources | **Decided 2026-10-09** | §7.2 as recommended: breadth computed from Alpaca SIP over the SEC ticker universe, sectors from SEC SIC codes, US macro and the economic calendar from FRED (a free key the owner enters in settings), US Treasury yield curves |
| D-4 | On-chain data provider | Recommended | Defer; §7.2 |
| D-5 | Fundamentals and earnings-date sources | **Decided 2026-10-09** | Free sources only: SEC XBRL company facts (statements, ratios, screener fundamentals), Alpaca corporate actions (dividends, splits), SEC 8-K item 2.02 (past earnings dates). Upcoming earnings dates wait for a paid calendar vendor the owner may choose later |
| D-6 | Options data source | Recommended | §7.2 |
| D-7 | Manual live trading from the chart | Not in this roadmap | Live execution stays with deterministic strategies |
| D-8 | Native desktop wrapper (Electron/Tauri) | Recommended | Not needed; PWA (TVP-4.5) |
| D-9 | Server runtime for indicators and scripts | **Confirmed 2026-10-09** by the TVP-11.0 spike | Python only, no Node sidecar; scripts run on the server with a shared result cache (§6, TVP-11). Measured on 5,000 bars: median 48 ms per full run (max 285 ms), 0.016 ms per new bar; conditions for TVP-11.1 in `OMNIX_SCRIPTS_SPEC.md` §4 |

### 7.2 Data source recommendations

Principle: **use what Omnix already integrates and licenses first, prefer official free sources next, and add a paid vendor only where nothing else exists.** No new dependencies on Yahoo's unofficial endpoints.

| Data | Recommendation | Already in Omnix? | Notes |
|---|---|---|---|
| US equity bars, quotes, multi-symbol snapshots | **Alpaca SIP** | Yes (`providers/alpaca_sip.py`) | Consolidated feed; base for watchlist alerts, screener and breadth |
| Market breadth (A/D line, A/D ratio, CVI) | **Compute from Alpaca SIP** over the listed universe (SEC ticker list) | Inputs yes | Daily at the close first; intraday from batched snapshots within the budget. No vendor needed |
| Sector and industry classification (heatmaps, screener) | **SEC SIC codes** from `data.sec.gov/submissions`, mapped to sectors | Yes (`research/adapters/sec_edgar.py`) | Free and official; coarser than GICS. Upgrade to a vendor only if users need GICS |
| Financial statements and ratios | **SEC XBRL company facts** (`data.sec.gov/api/xbrl/companyfacts`) | Same SEC adapter family | Free and official, full history for US filers; needs normalisation of `us-gaap` concepts. Non-US issuers would need a vendor |
| Analyst targets, dividend yield | **Keep Yahoo** as is (`metric_data.py`) | Yes | Unofficial; don't expand. Replace if it breaks |
| Dividends and splits | **Alpaca corporate actions API** | Alpaca integrated | Official, same credentials |
| Earnings dates | Past: **SEC 8-K item 2.02** filings. Upcoming: **a paid calendar vendor** (decide in D-5 when TVP-10.1 starts) | Past: SEC adapter | There is no official free source for future earnings dates |
| Crypto derivatives (OI, funding, basis, mark/index, liquidations) | **Keep Binance futures** (`metric_data.py`) and add **Hyperliquid** as a fallback | Binance yes; Hyperliquid for prices | `fapi.binance.com` refuses requests from US IP addresses; Hyperliquid's public `info` API has funding, open interest and mark prices without that restriction |
| Bitcoin on-chain | **Keep blockchain.info** | Yes (8 metrics live) | |
| Ethereum and other on-chain metrics (D-4) | **Defer.** If needed later, evaluate Coin Metrics (check its licence: the community tier is non-commercial) or a paid provider | No | Rare tier; 55 indicators, low daily use |
| Options chains, Greeks, IV (D-6) | **Alpaca options market data** first; **IBKR** as fallback | Alpaca and IBKR integrated | Alpaca option snapshots include Greeks and implied volatility; real-time OPRA needs the paid data plan. Check the account's plan before starting TVP-10.4 |
| US macro series | **FRED API** (free key) | No | Official; thousands of US series |
| US Treasury yield curve | **US Treasury daily par yield curve rates** | No | Official, free |
| Other countries' yield curves and macro maps | **Defer** (rare tier); vendor if needed | No | |
| Economic calendar | **None today.** US releases from FRED's release calendar (`fred/releases/dates`); global events need a vendor | No | Weekly tier |
| News | **Keep the existing source** | Yes | |

---

## 8. Out of scope

- Social network: ideas, profiles, following, chat, streams, contests, The Leap.
- The community script library (100,000+ scripts). Once TVP-11 exists, users can paste open-source scripts themselves.
- Broker marketplace and 100+ broker integrations.
- Exchange coverage of TradingView's 3.5 million instruments. Omnix covers what its providers deliver; adding exchanges is a data-licensing decision, not a feature gap.
- Mobile apps. The web app should stay usable on tablets; native mobile is a separate roadmap.
- Embeddable widgets and charting-library products.

---

## 9. Progress

**Status on 2026-10-09.** Merged into `tradingview-parity`: TVP-0.1, 0.2, 0.3, 0.4, 0.5a, 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.6, 5.1–5.3, 6.1, 7.1, 7.4, TVP-7.3, TVP-1.5, TVP-4.5, TVP-7.2a, TVP-4.1, TVP-1.3, TVP-9.1, TVP-9.2, TVP-1.4, TVP-11.0, TVP-3.2, TVP-3.3, TVP-4.2–4.4, TVP-3.4, 3.5, 3.7, TVP-1.6, TVP-6.2, TVP-6.3, TVP-0.6, 8.1 (wave 3), TVP-6.4, TVP-6.5, TVP-7.2b, TVP-1.7, TVP-11.1–11.3, TVP-11.4, TVP-11.5, TVP-0.5b, 0.5c, TVP-2.1/2.5 snapshot links, TVP-9.4, TVP-10.3 and 8.1 (wave 1). TVP-0.4 is done and the TVP-3 drawing tools have started (3.1 merged). TVP-0.5a (webhook delivery) is done. Missing daily- and weekly-tier features fell from 150 at the first ledger count to **8**. Nothing is on `main` yet; the integration branch merges there as one reviewed change when the owner decides.

**Completion.**

<!-- parity-completion:start -->
| Measure | Done |
|---|---|
| TradingView parity, all features in scope | 96% |
| TradingView parity, daily + weekly features | 97% |
| Roadmap work packages merged in full | 75% (50 of 67) |
| Daily + weekly gap closed since the first count | 95% (142 of 150) |

Features: have counts 1, partial 0.5, missing 0; features excluded or waiting for a decision are left out, and what Omnix had before this roadmap is included. Work packages: rows marked **Done** in the status table below, of every TVP work package in this roadmap (including the deferred TVP-4.6). Gap: missing daily + weekly features against 150 at the first ledger count. Refreshed by `python scripts/tradingview_parity_progress.py`.
<!-- parity-completion:end -->

Counts come from the parity ledger [`tradingview-parity.json`](tradingview-parity.json) (`python scripts/tradingview_parity_report.py`). The ledger was checked against the code in TVP-0.1 and updated after each merge; the running app was not available for a visual check.

<!-- parity-report:start -->
| Area | Have | Partial | Missing (daily / weekly / rare) | Pending decision | Excluded | Done |
|---|---|---|---|---|---|---|
| Charts and layouts | 32 | 0 | 0 / 0 / 1 | 0 | 0 | 97% |
| Drawing tools | 100 | 0 | 0 / 0 / 1 | 0 | 0 | 99% |
| Indicators | 151 | 1 | 0 / 4 / 0 | 54 | 0 | 97% |
| User scripts | 7 | 0 | 0 / 0 / 1 | 0 | 0 | 88% |
| Alerts | 24 | 0 | 0 / 0 / 0 | 0 | 0 | 100% |
| Shortcuts | 50 | 0 | 0 / 0 / 0 | 0 | 0 | 100% |
| Watchlists | 10 | 1 | 0 / 0 / 0 | 0 | 0 | 95% |
| Screener | 5 | 0 | 0 / 2 / 0 | 0 | 0 | 71% |
| Replay | 11 | 0 | 0 / 0 / 0 | 0 | 0 | 100% |
| Paper and chart trading | 22 | 0 | 0 / 0 / 0 | 0 | 0 | 100% |
| Research data | 3 | 1 | 0 / 2 / 2 | 1 | 0 | 44% |
| Tabs and windows | 6 | 0 | 0 / 0 / 1 | 0 | 0 | 86% |
| **Total** | 421 | 3 | 0 / 8 / 6 | 55 | 0 | 96% |

| Tier | Have | Partial | Missing | Pending decision | Excluded | Total | Done |
|---|---|---|---|---|---|---|---|
| Daily | 163 | 0 | 0 | 0 | 0 | 163 | 100% |
| Weekly | 199 | 3 | 8 | 0 | 0 | 210 | 95% |
| Rare | 59 | 0 | 6 | 55 | 0 | 120 | 91% |

Missing daily + weekly features: **8**

Done (have counts 1, partial 0.5, of the features in scope): **96%** overall, **97%** of daily + weekly.
<!-- parity-report:end -->

**How the work runs.**
- Integration branch `tradingview-parity`, checked out in the worktree `F:/LLM/omnix-tvp`.
- Each work package is built on its own `tvp/<wp>` branch in its own worktree, reviewed by a separate review agent, then merged into the integration branch.
- Since 2026-10-08 development happens in the main session only; subagents are used for code review (running many development agents cost too many tokens).
- Migrations for this roadmap use the reserved range **0140–0179**: 0140 is TVP-7.1, 0141 is TVP-1.2; the next ones are assigned at merge.
- PostgreSQL tests run against scratch databases in the `omnix-architecture-test` container, never the live database.
- `api:generate` needs the locked FastAPI 0.141.1 and Starlette 1.7.0 (`requirements/gateway.lock.txt`); the local interpreters have 0.133.1. Install the locked versions into a scratch directory (`pip install --target <dir> fastapi==0.141.1 starlette==1.7.0`) and put it first on `PYTHONPATH` for that command. Don't change shared environments.

| WP | Status | Branch / commit | Notes |
|---|---|---|---|
| TVP-0.2 | **Done** | scaffold `451eda57b`/`47b8b9aac`; batches `2f608d201`, `295483749`; consolidation and review fixes `f4545ca7d` | **All 100 available chart indicators have server implementations**, verified against browser goldens (8 datasets including empty, constant, gaps, negative prices; input variants; anchored VWAP). They are bit-exact except the transcendental ones (ALMA, Choppiness, Fisher, Historical Volatility, McGinley), which differ by at most a few hundred ulps through `exp`/`log`.<br>Two reviews:<br>• the scaffold review tightened the tests;<br>• the port review fuzzed 13,832 extra cases against the browser engine and found 3 indicators raising where JS yields Infinity/NaN, now fixed with `js_div`/`js_log`.<br>All 100 run in 0.7 s on 5,000 bars; the slowest is RCI Ribbon at 80 ms.<br>Follow-ups: cap periods in the alert/screener APIs; the alert monitor moves to the registry in TVP-1.2 and the scanner in TVP-9.1 |
| TVP-0.3 | **Done** | `41d5410a3`, `14af59bf62` | Command catalogue and dispatcher (text fields ignored, most specific scope wins, Alt by physical key, exact modifiers), key overrides, conflict detection; drawing undo/redo/delete moved onto it. Finding: `TradingCommandCenter` is a strategy operations panel, not a command palette, so TVP-2.1's Ctrl+K needs a new palette. Override persistence is decided in TVP-2.4 |
| TVP-0.1 | **Done** | merged `6996ba5832` | Ledger of 493 features (`docs/trading/tradingview-parity.json`) with evidence for every have/partial entry, a report script that fails on stale or missing evidence, verification of every *verify* row by code, "Omnix Scripts" naming (D-1), §2 corrected. The ledger caught 16 entries made stale by the TVP-0.4 merge |
| TVP-2.1 + 2.3 + 2.4 | **Done** | merged `d7e84f2f5d` | Chart shortcuts (type-to-search, interval box, `/`, Ctrl+K palette, Ctrl+S, `.`, arrows, zoom, Alt+R/I/L/P/S, Ctrl+Y), layout shortcuts (Tab between charts, Alt+Enter, Alt+W), tab shortcuts (Alt-based in the browser, TradingView's Ctrl keys for the installed app), closed-tab stack, shortcut dialog with rebinding and conflict checks. Own hotkey matcher for keyboard layouts (decision TVP-0.3 rev). Three review rounds. Alt+G bound with the TVP-2.5 merge. Follow-up: Alt+A (add alert) |
| TVP-2.2 | **Done** | merged (this commit) | Multi-select (Ctrl+click; group move and delete; locked drawings stay), Ctrl+drag clone with a ghost preview, Ctrl+C/V copy and paste (also onto another chart or symbol), arrow-key nudge (shadows the chart's arrows only while a movable drawing is selected), Alt+T/H/V/C/F and Alt+Shift+R tool keys, Ctrl+Alt+H hide all, Shift constrain (45 degrees, square, circle). One review round: undo left stale selection flags, no drag threshold, canvas mode ignored hide-all; all fixed. Decision TVP-2.2 (keys) |
| TVP-2.5 | **Done** | merged `a4275fd16c` | Custom intervals with favourites (the keyboard interval box uses the same parser), countdown, go to date (Alt+G), copy image, duplicate layout, double-click maximise/collapse, extended-hours toggle and price line, chart templates, market status and delay badges (new `/api/trading/market-status`). Review fixes: **clock-aligned chart aggregation** (`providers/clock_aggregation.py`; the strategy runner's count mode is unchanged and pinned by goldens), multi-day equity buckets count trading days, a bucket is final only when its last base bar is, comparison series and the data window use the chart's alignment and extended-hours setting. Two review rounds. Remaining: snapshot links (need a hosted snapshot service) |
| TVP-6.1 | **Done** | merged `fe21951c71` | 9 indicators in browser and server, bit-exact: Rob Booker ADX Breakout, Knoxville Divergence, Intraday Pivot Points, Missed Pivot Points, Reversal, Ziv Ghost Pivots; Relative Volume at Time; 24-hour Volume; Correlation Coefficient with a second series. Review fixes: definitions aligned with TradingView's help pages, sessions in the exchange timezone (futures roll at 18:00 ET despite the catalog's 24x7 tag), levels and markers rendering, compare-symbol loading. Two review rounds. Follow-ups: alerts pass `params`/session/compare bars (TVP-1.x); Intraday Pivot Points period as a 1/4/8 select; unlabelled US-equity bars count as regular |
| TVP-0.4 | **Done** | first part `e1a0dae44a`; readiness round merged (this commit) | Registry with renderer-agnostic geometry, creation gestures, generic properties dialog, gap-aware time index, safe document upgrades; SVG host pixel-identical; canvas behind a switch. Readiness round: bar-index alert-level contract shared with the server (`barTimeline.ts`, shared cases), handles that edit any anchor or property, `onCreate`, an action bus with source and error isolation, guarded tool callbacks. Decision TVP-0.4 (alerts): comparisons and indicator data on their own clock are plotted on the main series' bars, so a drawing and its alert share one bar index; brick charts and lines starting before the loaded bars offer only flat levels. Three review rounds. **The TVP-3 drawing tools can start** |
| TVP-1.1 + 1.2 | **Done** | merged `0331302776` | Server-side frequency (once / every time / once per bar / once per bar close / once per minute; intrabar derived from frequency); conditions child table (≤5, 13 operators, price/change/indicator/trendline sources, value/source/channel targets, RLS, `definition_revision`); bar-based evaluation on the server indicator registry; legacy adapter for all 15 types; channel schema with webhook URL and secret stored together in the protected store (write-only, masked URL, atomic with the row, advisory lock per alert); unreadable alerts reported, not fatal; migration `0141_trading_alert_conditions.sql`. Fixed pre-existing: server alerts never fired (0027 trigger); a decrypt failure made credential saves wipe all stored credentials; saves dropped other providers' keys after a failed read. Five review rounds. Follow-ups: monitor indicator cache and per-workspace limits; message placeholders and delivery senders (TVP-1.5/0.5); backfilling bars missed while the monitor is down |
| TVP-5.1–5.3 | **Done** | merged `cf37311dbc` | Payload v2 with sections (v2 keeps writing `instrumentIds` for stale old-client tabs; unknown versions read-only), colour flags (`watchlist_flag_set`), column choice and sorting, `.txt` import/export (1 MB / 2,000 symbols, exact-spelling preference, class-share symbols), keyboard navigation as an ARIA tree grid. Edits are saved one at a time per list as operations on the last server revision. Three review rounds. Follow-ups: flag from chart and screener; indicator columns (registry now available); incremental quote refresh for large lists; the TradingView-listed watchlist shortcuts join the command catalogue in TVP-2.3 (grid navigation keys stay local) |
| TVP-7.1 | **Done** | merged `8ea2f9bcf9` | Stop-limit, trailing stop (amount or %), DAY/GTC/GTD, `expired` status, trailing bracket stop-loss; migration `0140_trading_paper_order_types.sql`; live gateway untouched (empty diff, tested). Three review rounds:<br>• trailing stops trust only bars that start after their last move (`trail_moved_at` = later of quote time and bar start, `clock_timestamp()`), for orders and bracket legs, plain legs included;<br>• chart edits keep the trail;<br>• expired DAY entries cancel their bracket without market data;<br>• tick rounding against the trader;<br>• stop-through-market warning.<br>Follow-ups: DAY for futures/forex at venue close; new order types in replay; keep the bar low at move time to catch a real dip later in the same bar |
| TVP-7.4 | **Done** | merged (this commit) | Shift+B/S and Shift+Alt+B/S fill the paper order ticket (market, or limit at the crosshair price) while the ticket is open; the user places the order and the server's risk rules apply (decision TVP-7.4). Paper order notifications: fills, partial fills, rejections, cancellations and expiries as a toast and in the dock's Notifications tab, watched by the workspace. One review round: leaving replay flooded the log, notifications were lost while the dock was hidden, Shift+letters were taken from symbol typing; fixed. Follow-up: margin-call notifications with TVP-7.2b |
| Follow-ups batch 1 | **Done** | merged (this commit) | Alert sounds (chime, beep, alarm; Web Audio; picked and previewed in the alert dialog, saved in `delivery.sound`, unknown stored sounds kept); Alt+A opens the alert dialog at the last price (off in replay); line width and dash editor for the selected drawing; ledger corrected for the Ctrl+K command palette. One review round (stale progress, simultaneous triggers, suspended audio, replay Alt+A, unknown sounds; all fixed). |
| TVP-7.3 | **Done** | merged (this commit) | Working orders drawn on the chart (side, type, quantity), moved by drag plus a Move confirmation or cancelled from the line. A buy entry is re-priced by a new server route (`risk-orders/{id}/move`): it is re-sized to the original dollar risk and replaced with its pending stop re-pointed, all in one transaction with `manual_risk` authority. Sells use the existing reduce-only replace. Also: a shared chart handle primitive; a price-scale "+" menu (limit or stop toward or away from the market, Add alert); legend Sell/Buy with bid/ask. The "+" orders and the Buy/Sell buttons fill the paper ticket (decision TVP-7.3). Two review rounds (DAY expiry, protection re-pointing race, trails, triggered stop-limits, drag cleanup, reused order ids; all fixed). Follow-up: shorting (TVP-7.2a) |
| TVP-1.5 | **Done** | merged (this commit) | Message placeholders rendered by the server at trigger time and stored with the trigger: `{{ticker}}`, `{{exchange}}`, `{{interval}}`, `{{open}}`…`{{volume}}`, `{{time}}`, `{{timenow}}`, `{{alert_name}}`, `{{plot_N}}`, `{{plot("name")}}`. Unknown placeholders stay as written. The app, the toast and the webhook all show the same text. Also: alert names; Webhook channel in the alert dialog with a write-only URL and signing secret (a stored webhook shows only its host); sound picker kept from follow-ups batch 1. One review round (webhook edits with the channel unticked, legacy volume, ticker parsing; fixed). Email and push wait for TVP-0.5b/c |
| TVP-4.5 | **Done** | merged (this commit) | Web app manifest (Omnix Trading, start URL /trading, standalone, icons). In the app window (standalone or window-controls-overlay display mode) the trading commands use TradingView's browser-reserved keys (Ctrl+T/U/W, Ctrl+Tab, Ctrl+1…9, Ctrl+Shift+T). A claimed key with nothing to run is kept from the browser, so Ctrl+W never closes the window. The install prompt is captured from the first page and offered in the shortcut dialog. One review round (fall-through keys, fullscreen tabs, prompt capture; fixed). OS notifications wait for TVP-0.5c. Needs a check in an installed window |
| TVP-7.2a | **Done** | merged (this commit) | Paper shorting. Accounts have `allow_short`: off by default and for strategy accounts, on in the account form, changed in settings at the account's revision. Turning it off cancels working short entries. Shorts are risk entries: sized from a stop above the entry, `manual_risk` authority, kill switches and daily loss as for longs. Short brackets are mirrored. Shorts are unleveraged until TVP-7.2b: a working short holds cash like a buy, and an open short holds twice its buy-back cost, checked under the account lock. Shorts can be bought back by hand (a buy within the short, counting working buys, so a cover never flips long) and are never refused for cash. Replay backtest has Allow short (crosses reverse; long-only results unchanged). Correction: `backtest.py` refused shorts before. Two review rounds (manual cover, compounding buying power, shorting off, backtest sign, fill-time covers, rejected holds; all fixed) |
| TVP-4.1 | **Done** | merged (this commit) | Colour link groups: a chart joins one of six groups from its header (taking the group's symbol). A symbol change reaches every member in every tab in one store update. Groups and tab-wide instrument links reach each other both ways, bounded by the groups and tabs. Reopened tabs take their groups' current symbols. The group is saved with the chart. The watchlist and screener reach the group through the active chart. Groups share the symbol; the interval stays with the tab link (decision TVP-4.1). One review round (clipped menu and overridden styles, link interplay, reopened tabs, keyboard menu; fixed). The menu still needs a visual check |
| TVP-1.3 | **Done** | merged `3eff3c2743` | The chart's alert dialog offers the chart's indicators, with their output lines and a comparison against a value. The alert is a conditions alert that the server evaluates with the same inputs and line. A pane's alert starts on that pane's indicator. Indicators the server can't evaluate are greyed out with the reason: missing from `GET /api/trading/alerts/indicators`, session-based, extra parameters, or a compare symbol. Such alerts are drawn and dragged on their pane, and values aren't rounded. A cross-language contract (fixture written by a web test, checked by a server test) keeps every offered line a valid server output for the 109 server indicators, defaults and variants. Two review rounds (wrong indicator from a pane, stale selection fallback, sessions, drawing, rounding; fixed). Follow-ups: show the server's error text; worker-lag edge case |
| TVP-9.2 | **Done** | merged `47c15d23af` | A saved screen re-runs every 10 s or every minute while the screener is open. A new run starts only when none of the screen's runs is working: the server locks the screen and answers 409 while one runs, and an abandoned run neither locks it nor stays (runs pruned to the last 50). The panel backs off after three failures. Results new since the previous run are highlighted, with counts of new and dropped. PostgreSQL integration test for the lock and pruning. Two review rounds |
| TVP-9.1 | **Done** | merged `47c15d23af` | Screener rules can be filters or columns, and every rule is a sortable result column. New metrics: any server registry indicator and line, relative volume (against the N prior bars), gap %, and distance from the N-bar high or low; plus price, change %, volume, SMA, EMA, RSI, ATR. Indicator rules share one cached bar series per instrument and are evaluated off the event loop. A run's results show the columns of that run's own snapshot. Saved screens load into the editor and save back at their revision; a conflict keeps the edits and takes the new revision. A result opens on the active chart and its link group; results can be added to the open watchlist. Two review rounds. Follow-ups: fundamentals wait for TVP-10.2; tests for skipping an unreadable stored screen |
| TVP-1.4 | **Done** | merged `d2d32e8baf` | Line alerts from horizontal lines and rays, trend lines and rays, channels, rectangles (top and bottom) and fib levels; the dialog picks the level, and the server stores the drawing and level with the alert. An alert follows its drawing: once a moved drawing settles on the active live chart (not in replay, and only once the chart has bars), it takes the level's new line, compared as the server evaluates it so charts on other intervals agree. A failing update retries when the drawing moves again. Deleting the drawing, or a level that goes away (fib levels are keyed by value), asks on the active chart whether to disable its alerts; each is disabled at its current revision, and Keep is remembered on every chart until the page reloads. Three review rounds (sync loops, level identity, no-bars false orphans; fixed). Follow-ups: choosing the level in edit mode, and the editor writing back the line it opened with |
| TVP-11.0 | **Done** | merged `bdf44a540d` | Omnix Scripts spike: a Pine v5/v6 subset interpreted on the server (`src/app/apps/trading/scripts`: indentation-aware lexer, parser, compiler to closures, per-call-site series, incremental `ta.*` following the registry's order of operations). Every Pine template matches its chart indicator on the golden datasets within 1e-11 (one documented exception: Stochastic RSI on a flat window); ten `ta.*` functions match TradingView's reference implementations run through the interpreter; 17 of 20 community-idiom scripts run (the 3 others use request.security, strategy() and a user-defined type). Limits bound time, ints, strings, collections, alerts and nesting; every failure is a ScriptError with a line. Cost on 5,000 bars: median 52 ms per full run, 0.017 ms per new bar. D-9 confirmed with conditions (separate worker process with rlimits). Spec: `OMNIX_SCRIPTS_SPEC.md`. Two review rounds. Follow-ups: request.security, realtime rollback, const folding for v5 division, history only for referenced series, a real community-script corpus (owner-approved list) |
| TVP-3.2 + 3.3 | **Done** (inside pitchfork open) | merged `edcd9f11d5` | Seventeen tools: trend-based fib extension and time, fib time zone, channel, speed resistance fan and arcs, circles, spiral, wedge; Andrews, Schiff and modified Schiff pitchforks, pitchfan; Gann box, square, square fixed (a fixed price-per-bar scale) and fan. Extension, channel and pitchfork lines are built in bar index/price, so drawings and their alerts agree on any scale (alertable: extension levels, channel levels, median and tines). Retracement gains reverse, labels left or right, and levels, percents or prices. Two review rounds. Open: inside pitchfork (TradingView's construction to confirm), pitchfan level convention to verify; small follow-ups (Gann fixed handle at the corner, left labels with Extend left, adaptive spiral sampling) go with TVP-3.4/3.5/3.7 |
| TVP-3.4 + 3.5 + 3.7 | **Done** | merged (see log) | Thirty-eight tools. Shapes and freehand: brush and highlighter (simplified time/price strokes, drawn smoothed), path, polyline, curve, double curve, triangle, rotated rectangle, arc. Annotations: note, anchored note (fixed to the screen), price note, callout, comment, signpost, price label, flag mark, arrow marks (up, down, left, right), arrow marker, icons (Omnix's own shapes) and emojis (system font; no TradingView artwork). Patterns and waves: XABCD, Cypher, ABCD, triangle, three drives, head and shoulders (with ratios and neckline), five Elliott waves; cycles: cyclic lines, time cycles, sine line, counted from the view. Also fixed: the SVG renderer let the stylesheet override a text shape's own size and colour, and styled every circle as an edit handle. Two review rounds |
| TVP-1.6 | **Done** | merged (this commit) | Multi-condition alerts: up to 5 conditions combined with AND, one frequency and one message. The dialog edits each condition (price fields, change %, chart indicator lines; crossing, greater/less than, channels, moving by an amount or percent within bars) and adds conditions to price, volume, change and chart-indicator alerts, which become conditions alerts with their own condition first (its legacy meaning). Drawing alerts keep one condition. Errors are shown in the dialog; a stored indicator keeps its inputs when the chart has it with others. Server test: at bar close every condition reads the closed bar. Two review rounds. Open: source-to-source targets (SMA crossing EMA) in the dialog |
| TVP-4.2 + 4.3 + 4.4 | **Done** (visual check open) | merged (this commit) | Time link: clicking a bar scrolls the tab's other charts to its time (loading older history), whatever their interval. Workspaces and tabs open in new browser windows (?workspace=&tab=); windows talk on a BroadcastChannel: a window without edits reloads a workspace or watchlist another one saved (keeping its replay, closed tabs and shown tab; an edit made meanwhile meets the revision conflict), changes that leave the workspace as saved save nothing, and alert sounds and toasts play in the most recently focused shown window only (heartbeats expire closed, crashed or frozen windows). Tabs: a + launcher (new, duplicate, reopen, new window, saved layouts, tools), a tab menu (right-click or ...), duplicates carry their drawings, and leaving with unsaved edits asks first. Three review rounds. Open: a visual check in two real browser windows |
| TVP-6.2 | **Done** (Seasonality partial) | merged (this commit) | Thirteen indicators that draw, in `indicators/drawingIndicators.ts`: Auto Fib Retracement and Extension, Auto Pitchfork and Auto Trendlines from zigzag swings (depth, deviation x ATR); Auto key levels; VWAP Auto Anchored (highest high, lowest low or highest volume); Visible Average Price (a price line kept on the bars in view); Bollinger Bars (bar colours); Chop Zone; Moon Phases (Meeus); Trading Sessions (Tokyo, London, New York shading with labels); Multi-Time Period Charts; Seasonality (daily bars, earlier years up to today's date only). Indicator outputs gain per-point colours and labels and the kinds bar-colors, background and viewport-average. Browser-only, so not alertable. Shared goldens for all 13. |
| TVP-6.3 | **Done** | merged (this commit) | All Candlestick Patterns (`indicators/candlestickPatterns.ts`, server `candlestick_patterns.py`): TradingView's 44 built-in pattern definitions with trend SMA50, SMA50+SMA200 or none; labelled markers above or below the completing bar; a Patterns input for all, one direction or one pattern; listed under Patterns. Every pattern is an output and a server alert source through the new "Appears" comparison (stored as greater than -1e18; no overlay line); signal indicators declare their warm-up to alert validation. Shared goldens include a hand-built dataset that completes the rarer patterns. Williams Fractal is greyed out for alerts (confirmed bars later). |
| TVP-0.6 + 8.1 (wave 3) | **Done** | merged (this commit) | Intrabar data loader: `GET /api/trading/bars/intrabar` returns the lower-timeframe bars (1m and up) inside a range of chart bars from the latest 5,000 the provider serves, saying where its data starts; browser cache and helpers in `intrabarData.ts`. Sub-bar replay: an update interval (1m to 4h, where it fits) steps the shared clock, skipping the time between bars, and every chart draws its forming bar (and indicators on it) from intrabar chunks, in the sessions it shows; replay orders are placed at bar closes. Replay keys: Shift+Down play/pause, Shift+Right/Left step. |
| TVP-6.4 | **Done** (functional) | merged (this commit) | Volume Delta and Cumulative Volume Delta (`indicators/intrabarIndicators.ts`) from the TVP-0.6 intrabar loader on the chart's feed: each lower bar's volume is buying or selling by its close (unchanged bars by the previous close, else the previous direction); CVD restarts each day, week or month. Live the forming bar updates once per lower interval; in replay no lower bar after the clock is read; a 1m chart reads its own bars. Drawn as coloured histograms (TradingView: candles). Browser-only, computed off the worker like the external-data indicators. |
| TVP-6.5 | **Done** | merged (this commit) | Indicator on indicator (`indicators/indicatorSources.ts`, server `indicators/sources.py`): a Source input on the 30 close-only indicators picks another indicator's continuous line; the indicator runs on that series in the worker and in the server alert evaluator alike (shared fixture `indicator_goldens/sources.json`). Pane indicators keep their pane; overlays on a pane indicator join it. Alert inputs carry the source (`IndicatorSourceInputs.source`, one level). |
| TVP-7.2b | **Done** | merged (this commit) | Paper margin by asset class for longs and shorts (migration `0143_trading_paper_margin.sql`; 100% default, so existing long and strategy accounts are unchanged), set from the account dialog's leverage ratios: leveraged buys hold their margin share and borrow the rest; buying power (equity less margin and holds, at market) drives order placement and the risk preview. The paper monitor margin-calls accounts with leverage or shorts, closing the most margin-heavy positions only as far as needed with reducing market orders. Fixed commission once per order. **Behaviour change:** accounts already holding shorts are now margin-called at 100% short margin (D-2). Replay trading stays cash-only. |
| TVP-1.7 | **Done** | merged (this commit) | Watchlist alerts: an alert's "Applies to" picks a watchlist (instrument `watchlist:<record id>`); one definition runs on every member, read each pass, with per-symbol state (migration `0144_trading_alert_symbol_states.sql`, row-level secured) so once, cooldown and history apply per symbol and `{{ticker}}` names the symbol that fired. The monitor plans the list fetches against one request budget per pass (`alerts_watchlist.plan_watchlist_pass`: half each provider's budget, 25 a pass for Yahoo), sharing histories with ordinary alerts; diagnostics show each list alert's evaluated and skipped symbols. Review fixes: RLS, a message edit no longer re-fires once alerts, an orphaned list alert can be disabled. |
| TVP-11.1–11.3 | **Done** | merged (this commit) | Omnix Scripts you write and run. Server: scripts run in worker processes (`scripts_service.py`: 5 s limit, killed and replaced on overrun, two runs per person, shared result cache), `/api/trading/scripts` check, run and reference (names and signatures), scripts as trading documents with a version per save (migration `0145_trading_script_versions.sql`, written in the save's transaction). Web: a CodeMirror 6 editor replaces the read-only viewer (highlighting, completion, hover, inline problems, console, profiler, save as, import and export, history with diff and restore); saved scripts go on charts as `script-<id>` indicators run on the server, with plots, shapes, backgrounds, bar colours, levels, lines, boxes and labels mapped to chart outputs and their inputs in the indicator settings. Not drawn yet: fill, plotcandle, plotbar, table. Reviewed inline. |
| TVP-11.4 | **Done** | merged (this commit) | Script alerts: a `script` alert source (`alert_conditions.ScriptSource`) reads a script indicator's plot, `alertcondition()` or `alert()` calls from the script version saved when the alert was made; the alert monitor runs it in a script worker on its bars (`alerts_scripts.py`), with the browser closed. Signals have values only where they fire, so the dialog's Appears works on them; an alert without its own message takes the `alert()` or alertcondition message. The API rejects a missing version, a script that doesn't compile or lacks the call; watchlist alerts can't use scripts. Reviewed inline. |
| TVP-11.5 | **Done** | merged (this commit) | Strategy scripts and the strategy tester: `strategy()` with entry, order, exit (brackets, trailing stops), close, cancel, OCA, pyramiding, commission and slippage, filled like TradingView's broker emulator (`scripts/strategy.py`); a Strategy Tester tool (overview with equity, buy and hold and drawdown; performance summary for all, long and short; list of trades; properties); a deep backtest over up to 20,000 bars (`POST /api/trading/scripts/backtest`); fills drawn on the chart. Research only: a simulated account, never an order (the optional paper-signal link is not built). Reviewed inline. |
| TVP-0.5b, 0.5c | **Done** | merged (this commit) | Alert email and web push through the outbox: the workspace's SMTP server (STARTTLS/TLS, password in the protected secret store, server address checked like a webhook's) and web push to every device that allowed notifications (`webpush.py`: RFC 8291 encryption matching the RFC's test vector, RFC 8292 VAPID with a key made once in the secret store; subscriptions per user and device in migration `0146_trading_alert_email_and_push.sql`, row-level secured; gone subscriptions removed). The dialog sets both up inline with test sends; `/omnix-push-sw.js` shows OS notifications with Omnix open or closed, which completes TVP-4.5. Reviewed inline. |
| TVP-2.1, 2.5 (snapshot links) | **Done** | merged (this commit) | Chart snapshot links: PNGs stored per workspace (migration `0147_trading_chart_snapshots.sql`, row-level secured, newest 200 kept) behind random `/api/trading/snapshots/<id>.png` links that open for signed-in members of the workspace; Alt+S copies a link as TradingView's does, Ctrl+Alt+S downloads, a Link button sits beside Copy. Public links would be an owner decision. Reviewed inline. |
| TVP-9.4 | **Done** | merged (this commit) | Natural-language screener: describe a screen and the research provider proposes rules (`screener_words.py`, versioned prompt `trading.screener_from_words`; the model sees the description and the indicator catalog only). Every rule goes through the scanner's validation, what doesn't validate is reported, and the rules fill the editor for the user to change, save and run; nothing runs without the user. Reviewed inline. |
| TVP-10.3 | **Done** | merged (this commit) | Seasonals panel (a tool for the active symbol, `TradingSeasonals.tsx`, `seasonals.ts`): each calendar year's change from its first close on one January–December axis, the current year highlighted, the average of past years, and a monthly-returns table with each month's average and how often it rose. The chart's Seasonality indicator stays partial (it stops at today's date). Reviewed inline. |
| TVP-8.1 (wave 1 part) | **Merged** (wave 1 part) | merged `421e588670` | One speed control (9 speeds) and one replay clock for all charts; jump to bar during playback; one "Real time" exit; bars streamed during replay backfilled; charts redraw only when their visible bar count changes. Replay paper trading runs through a sequential per-session queue: every bar once and in order, flat bars without server calls, orders at the clock's bar on the session feed. Fixed older bugs: replay orders with a feed binding never filled; replay bars marked positions in other instruments. Three review rounds. Remaining: sub-bar playback (needs TVP-0.6) and replay shortcuts (TVP-2) |
| TVP-0.5a | **Done** | merged (this commit) | Outbox table (migration `0142_trading_notification_deliveries.sql`) written in the trigger's transaction; delivery monitor across workspaces (system operation `notifications.delivery`) with leases, fencing and backoff (30 s to 1 h, 8 attempts); webhook sender: HTTPS only, strict URL policy after DNS with the connection pinned to the checked address, one deadline per send, no redirects, proxies or body reads, URL never logged, HMAC-SHA256 signature; `GET /api/trading/alerts/deliveries` (status only). Two review rounds (the first found token logging, unbounded sends and CGNAT addresses; all fixed). Follow-ups: webhook editor and message placeholders (TVP-1.5); throughput is about 24 sends a minute |
| TVP-3.1 | **Done** | merged (this commit) | Eight tools: info line (price change, percent, bars, angle), extended line, trend angle, parallel channel (middle line, fill, width-keeping handles), flat top/bottom, disjoint channel, regression trend (least squares of closes on bar index, deviation bands), anchored VWAP (the indicator's formula). Channel lines are built in time/price and both drawn and alerted on, so drawings and alerts agree on a log scale too; alert levels on every line. One review round. Follow-ups: regression deviation is the population one (TradingView may use n-1); info line shows no time span or distance |
| TVP-3.6 | **Done** | merged (this commit) | Long and short position (one click; entry, stop and target zones with amounts, quantity from account size and risk %, risk/reward, P&L once a bar reaches the entry; "Create buy/sell order" fills the paper ticket, which the user places), date range and date-and-price range (TradingView's labels: change, percent, ticks; bars, span; volume), price range with ticks, position forecast, bars pattern, ghost feed, sector, fixed range volume profile. One review round: the ticket's limit price and protection were wrong (entry went to the stop-limit field; stop and target shown but not sent for sells and replay); fixed and tested against the real panel. Follow-ups: protection for sell and replay orders in the paper panel; the panel's risk % is used, not the drawing's |
| TVP-3.8 | **Done** | merged (this commit) | Drawing toolbar behaviour: stay in drawing mode, lock all, hide all, drawing sync between a tab's charts (off: each chart keeps its own), favourites toolbar; per-interval visibility (TradingView's Visibility tab, "only this interval"); each tool remembers its last style; named drawing templates per tool (saved with the preset documents). One review round: lock all didn't stop nudges, templates copied per-drawing data, duplicates lost per-chart drawings; fixed. Follow-ups: the favourites toolbar isn't draggable; object tree grouping, rename and reorder |


**Pre-existing issues found during this work** (outside any WP's scope unless noted):

| Issue | Status |
|---|---|
| Server alerts could never fire: the 0027 lifecycle trigger reverted the evaluator's own state update | Fixed in TVP-1.2 (migration 0141, merged) |
| A protected-store decrypt failure made the next credential save overwrite every stored provider and trading credential | Fixed in TVP-1.2 (strict reads; unreadable store never overwritten; merged) |
| Architecture inventory still named `TradingWatchlist.tsx` for `WatchlistPayload` after TVP-5.1 moved it, failing the architecture metrics scan | Fixed (`4cb7540f9d`) |
| Replay orders with a feed binding never filled; replay bars marked positions in other instruments | Fixed in TVP-8.1 (merged) |
| Drawings: anchor projection scanned every bar per anchor (~52 ms/frame); anchors between bars drew at x=0 | Fixed in TVP-0.4 (merged) |
| Drawing anchors resolve against the adapter's bar list, not the chart's time scale (comparison series with extra timestamps, Renko-type charts store wrong times) | Fixed in TVP-0.4 (merged) |
| **Count-mode bar aggregation splits sessions on the UTC date**, so in winter a group with missing minutes can absorb the next morning's pre-market bars (`aggregation.py` ~71-77). The **strategy runner** uses this path | **Open — owner decision needed**: fixing it changes strategy inputs and evidence, so it's not changed as a side effect. Charts use the separate clock-aligned mode since TVP-2.5 |
| Restored dynamic equities get the XNYS calendar for every venue (`catalog.py` ~484) | Market-status badge hides it for non-US venues (TVP-2.5, merged); the catalog itself is unchanged |

---

## 10. Sources

**TradingView public documentation:**

- Features: https://www.tradingview.com/features/
- Plan comparison: https://www.tradingview.com/pricing/
- Drawing tools list: https://www.tradingview.com/charting-library-docs/latest/ui_elements/drawings/Drawings-List/
- Indicators list: https://www.tradingview.com/charting-library-docs/latest/ui_elements/indicators/Indicators-List/
- Chart featuresets: https://www.tradingview.com/charting-library-docs/latest/customization/Featuresets/
- Keyboard shortcuts: https://www.tradingview.com/charting-library-docs/latest/configuration/Shortcuts/
- Desktop app shortcuts: https://www.tradingview.com/support/solutions/43000623399-hotkeys/
- Alert configuration: https://www.tradingview.com/support/solutions/43000763312-learn-how-to-configure-alerts/
- Alert frequencies: https://www.tradingview.com/support/solutions/43000474415-differences-between-alert-frequencies/
- Multi-chart sync: https://www.tradingview.com/support/solutions/43000629992-how-to-sync-the-charts-of-my-layout/
- Selective chart sync: https://www.tradingview.com/support/solutions/43000761094-how-to-sync-selected-charts/
- Watchlists: https://www.tradingview.com/support/solutions/43000745825-mastering-the-tradingview-watchlists/
- Bar Replay intervals: https://www.tradingview.com/support/solutions/43000739158-how-to-select-replay-interval-for-the-bar-replay/
- Bracket orders: https://www.tradingview.com/charting-library-docs/latest/trading_terminal/trading-concepts/brackets/
- Trailing stops: https://www.tradingview.com/support/solutions/43000501552-how-do-i-place-a-trailing-stop-order/
- Paper trading commissions: https://www.tradingview.com/blog/en/introducing-commissions-for-paper-trading-11222/

**Local inspection of the TradingView Desktop 3.4.1 package (2026-10-08).** The package's file layout and the module paths in its bundled source maps were listed to identify the desktop shell's features (tabs, windows, link groups, notifications). A few small shell source files were read for that purpose: IPC channel names, link-group colour names and API endpoint constants. The package contains no charting, indicator, script or trading code. Nothing from it is used, copied or adapted in Omnix; this roadmap uses only the resulting feature list.

---

## 11. Revision history

| Rev | Date | Changes |
|---|---|---|
| 1 | 2026-10-08 | First version: gap inventory and 54 WPs |
| 2 | 2026-10-08 | Applied the code review of rev 1 and the owner's decisions. **Corrections:**<br>• Indicators: 125 of 208 available, counting the 25 data-backed ones (the review's count of 97 was wrong; there are 91 `SUPPORTED` entries).<br>• Paper: shorting exists server-side; commission and slippage exist; TIF is missing.<br>• Replay: two speed controls and a per-panel cursor.<br>• No intrabar loader exists (new TVP-0.6).<br>• The constraint-replacement precedent is `0036`.<br>• DECISIONS.md gets its own section.<br>**Plan changes:**<br>• D-9 decided once, Python-only, scripts on the server (P1).<br>• TVP-0.2 uses Python `float` with per-class tolerances; first batch of ~20 (P2).<br>• TVP-1.2 owns the one condition-schema migration; TVP-1.6 needs none (P3).<br>• TVP-0.5 split into 0.5a webhook (wave 1), 0.5b email and 0.5c push; TVP-4.5 resized to M (P4).<br>• TVP-4.3 cut to "open in new window"; full multi-window deferred to TVP-4.6 (P5).<br>• TVP-0.4 includes a canvas renderer spike (P6).<br>• TVP-1.7 cap derived from the request budget, default 100 (P7).<br>• Usage tiers and `excluded-pending-decision` added to the ledger and progress (P8).<br>• "Pine Script source" label renamed in TVP-0.1, and the generated Pine scripts used as the TVP-11.0 test corpus (P9).<br>• TVP-0.3 built on `@mantine/hooks`; TVP-7.3 uses a chart-handle primitive; TVP-9.4 moved to wave 2; TVP-0.2 starts in wave 1.<br>• §10 states exactly what was read from the desktop package.<br>**Decisions:** D-1 (Pine-compatible scripts) and D-2 (TradingView-style paper shorting) decided; data-source recommendations added (§7.2). |
| 3 | 2026-10-08 | Applied the review of rev 2 (all checked against the code).<br>**Corrections:**<br>• The shorting gap is that nothing writes `allow_short`: it isn't in `PaperAccountCreate`, the paper API or the account form. The hardcoded `allow_short: false` in `tradingReplayApi.ts` is the replay backtest's `execution_policy`, now its own row.<br>• Two migrations share `0036`; the doc cites full filenames, and new migrations must check numbering.<br>• D-9 is "to be confirmed by" the spike.<br>• TVP-2.2 moved to wave 2 (needs TVP-0.4).<br>• TVP-1.2's migration now definitely widens `notification_channels` and adds channel settings; TVP-0.5a depends on it, and TVP-1.5 needs no migration.<br>• The numpy note now gives float parity as the reason.<br>• §9 replay and paper counts fixed.<br>• The TVP-11.0 corpus covers only indicators with a Pine template.<br>**Plan changes:**<br>• TVP-7.2 split into 7.2a shorting (daily, S–M, wave 2) and 7.2b leverage, margin calls and fixed commission (weekly, M–L, wave 3).<br>• Script result cache added to D-9, TVP-11.0 (measured) and TVP-11.1.<br>• The serial chains in wave 1 are shown explicitly.<br>**Follow-up from the review of rev 3:**<br>• Shorting defaults to on only in the account form; the model and database default stay off, because strategies create accounts through `PaperAccountCreate`. Added a test that a strategy-created account has shorting off, and updated D-2 in DECISIONS.md to match.<br>• §9 paper weekly missing count corrected to 5. |
