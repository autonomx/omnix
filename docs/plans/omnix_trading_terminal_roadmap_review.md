# Omnix Trading Terminal Roadmap Review

**Reviewed:** 2026-08-06  
**Roadmap:** `docs/plans/omnix_trading_terminal_roadmap.md`  
**Implementation PR:** #1488

## Conclusion

The original OTT-0 through OTT-15 sequence is technically coherent and correctly orders architecture, data, streaming, charting, persistence, technical analysis, providers, alerts, scanning, replay/backtesting, paper simulation, read-only research, and release hardening.

The review found one roadmap wording problem and several implementation gaps:

1. The roadmap mixed **code completion** with **release certification**. Deterministic tests can prove contracts and algorithms, but they cannot prove real PostgreSQL migrations, browser accessibility, heap stability, long-duration streams, provider outages, or host-specific performance without an executed environment run.
2. OTT-11, OTT-12, and OTT-13 initially existed as source files but were not registered in the shared gateway or reachable from the Trading workspace.
3. OTT-12 originally lacked explicit signal/fill bar indices, win rate, exposure, and BlobStore output for the complete result artifact.
4. OTT-13 initially lacked gateway lifecycle evaluation, explicit reset/archive semantics, a product UI, and qualification tests.
5. OTT-14 had not been implemented.
6. OTT-15 lacked functional side tabs, a diagnostics panel, visible chart attribution, retained Trading notices, and an honest release evidence matrix.

Those code gaps are addressed on the implementation branch. Environment-dependent evidence remains explicitly separate.

## Corrected interpretation of completion

### Code-complete

A phase is code-complete when:

- its production routes and UI are reachable;
- its persistent authority and migrations exist;
- deterministic unit/contract/parity tests pass;
- TypeScript compiles;
- failure, cancellation, revision, and idempotency behavior is encoded;
- displayed controls perform their advertised action;
- safety and legal boundaries are visible and testable.

### Release-certified

A milestone is release-certified only after the required environment evidence is attached and reviewed, including where applicable:

- real PostgreSQL migration and restart tests;
- real provider outage/recovery drills;
- real WebSocket reconnect and long-duration soak evidence;
- real browser keyboard, screen-reader, contrast, and reduced-motion review;
- browser heap/resource measurements;
- host-specific chart performance evidence;
- operator rollback and artifact-cleanup rehearsal.

A green deterministic workflow does not silently substitute for those checks.

## Correctness clarifications

### Next-bar execution evidence

Consecutive normalized bars may legitimately satisfy `signal_bar.end_time == fill_bar.start_time`. Therefore strict timestamp inequality is not a correct no-lookahead proof. Backtests now persist:

- `signal_bar_index`
- `fill_bar_index`
- a contract requiring `fill_bar_index = signal_bar_index + 1`
- the accurate signal and fill timestamps

Legacy runs created before bar-index evidence retain NULL indices rather than fabricated history.

### Large result persistence

Backtest summaries, trades, equity points, and logs remain queryable in PostgreSQL. The complete validated run result is additionally stored through Omnix `LocalBlobStore`, with storage key, SHA-256 checksum, and byte size persisted on the run record. Reads verify the artifact checksum.

### Provider and execution boundaries

- Canonical instruments own positions, drawings, alerts, scanner results, and paper state.
- Provider bindings describe one source for an instrument and may change without changing canonical ownership.
- Read-only research resolves through the existing Omnix provider registry and cannot create alerts, backtests, paper orders, fills, or live orders.
- Paper simulation has no brokerage client or live execution route.

## Phase status matrix

| Phase | Code status | Review result |
|---|---|---|
| OTT-0 | Complete | ADR, inventory, feasibility spike, and dedicated Trading workflow exist. Host benchmark evidence remains release evidence. |
| OTT-1 | Complete | Canonical instrument, provider-binding, bar, provenance, persistence, and API contracts exist. |
| OTT-2 | Complete | Binance historical adapter and normalized provenance path exist with deterministic tests. |
| OTT-3 | Complete | Stream ownership, duplicate/out-of-order/gap logic, backfill, and lifecycle tests exist. Long-duration live soak remains release evidence. |
| OTT-4 | Complete | Native route, workspace, chart grid, loading/error/empty states, theme handling, and cleanup contracts exist. |
| OTT-5 | Complete | PostgreSQL authority for workspaces/watchlists/drawings/presets and revision conflicts exists. Real PostgreSQL restart drill remains release evidence. |
| OTT-6 | Complete | Versioned SMA/EMA/RSI parity exists across Python and TypeScript. |
| OTT-7 | Complete | Multi-chart layouts, linking, lifecycle ownership, keyboard/focus semantics, and performance fixtures exist. Browser heap measurement remains release evidence. |
| OTT-8 | Complete | Provider registry, policy metadata, fallback semantics, binding-aware bars/quotes/streams, and provider tests exist. Real outage drill remains release evidence. |
| OTT-9 | Complete | Chart types, Bollinger/ATR/MACD/VWAP, drawings, presets, snapshots, and export exist with parity/history tests. |
| OTT-10 | Complete | Persisted server alerts cover price, percentage change, indicators, and volume with explicit bar policy, cooldown, idempotency, monitor lifecycle, UI, and provenance. |
| OTT-11 | Complete | Bounded allowlisted scanner, persistence, ranking, cancellation, timeout, formulas, API, UI, and 50-instrument fixture exist. |
| OTT-12 | Complete | Frozen datasets, replay clock, no-lookahead indices, commission/slippage, equity, drawdown, return, win rate, exposure, logs, trades, PostgreSQL summaries, and BlobStore artifact evidence exist. |
| OTT-13 | Complete | Paper accounts, balances, positions, Market/Limit/Stop orders, fills, ledger, P&L, idempotency, monitor, reset/archive, UI, and no-live-execution tests exist. |
| OTT-14 | Complete | Bounded read-only research uses the Omnix provider registry, strict JSON validation, exact source metadata, UI evidence, failure isolation, and no mutation dependency. |
| OTT-15 | Automated hardening complete; environment certification pending | Functional tabs, diagnostics, reduced motion, attribution, notices, operator/security/release documents, and final invariant tests are present. Real browser/PostgreSQL/provider/soak evidence must still be attached before release certification. |

## Explicitly deferred beyond OTT-15

The following are not silently implied by this roadmap and require a separately reviewed roadmap or phase:

- live brokerage execution;
- AI-autonomous order placement;
- options, futures, margin, shorting, tax lots, or multi-currency accounting;
- news ingestion, fundamentals, earnings, or economic calendars;
- exchange-grade market-data redistribution;
- unrestricted or provider-wide scanner universes;
- multi-monitor desktop orchestration;
- collaborative shared Trading workspaces;
- advanced order types such as bracket, OCO, trailing stop, or partial-fill simulation;
- portfolio optimization or investment advice.

## Remaining release decision

PR #1488 should remain draft until the environment evidence in `OMNIX_TRADING_RELEASE_CERTIFICATION.md` is executed and attached. Automated code completion is necessary but not sufficient for a production release decision.
