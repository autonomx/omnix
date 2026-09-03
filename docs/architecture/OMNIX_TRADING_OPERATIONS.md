# Omnix Trading Operations Runbook

## Runtime ownership

Trading runs inside the shared Omnix gateway and web application. Do not start a separate prototype FastAPI or Vite workstation.

Gateway lifecycle services:

- Trading market-data REST and WebSocket routes
- server alert monitor
- bounded scanner manager
- replay/backtest routes
- paper simulation monitor
- deterministic strategy monitor
- Alpaca IEX trading-status monitor when credentials are configured
- read-only AI research route
- catalyst evidence and shadow classification routes
- shadow-only statistical-model training/scoring/validation routes

## Environment controls

### Alert monitor

- `OMNIX_TRADING_ALERT_MONITOR=0` disables production alert monitoring.
- `OMNIX_TRADING_ALERT_INTERVAL_SECONDS` controls the polling interval with a five-second minimum.
- In `legacy_test` mode, enable only with `OMNIX_TRADING_ALERT_MONITOR_IN_TESTS=1`.

### Paper monitor

- `OMNIX_TRADING_PAPER_MONITOR=0` disables paper-order monitoring.
- `OMNIX_TRADING_PAPER_INTERVAL_SECONDS` controls the polling interval with a five-second minimum.
- In `legacy_test` mode, enable only with `OMNIX_TRADING_PAPER_MONITOR_IN_TESTS=1`.

The paper monitor owns market observations and manual paper stop/target protection. Browser observations are not execution authority.

### Strategy monitor

- `OMNIX_TRADING_STRATEGY_MONITOR=0` disables deterministic strategy monitoring.
- `OMNIX_TRADING_STRATEGY_INTERVAL_SECONDS` controls the polling interval with a five-second minimum.
- In `legacy_test` mode, enable only with `OMNIX_TRADING_STRATEGY_MONITOR_IN_TESTS=1`.
- Strategy runtime modes are `off`, `shadow`, and `auto_paper`. There is no live-broker mode.

### Provider configuration

Market-data providers and the optional research model use Omnix provider configuration. Do not place credentials, tokens, or base URLs in Trading workspace records, scanner definitions, research requests, or browser storage.

US-equity data uses a split-source architecture:

- **Yahoo** is discovery/history/chart research only and can never authorize a paper fill.
- **Alpaca IEX** is the authoritative real-time US-equity paper-execution quote source. It is explicitly partial-market IEX data, not consolidated SIP/NBBO.

Within this paper-only system, **execution-grade** means an observation that satisfies Omnix's explicit execution-data contract; it does not mean IEX is equivalent to consolidated SIP/NBBO or a live brokerage fill.

Configure Alpaca Paper Only / market-data credentials with:

```text
OMNIX_ALPACA_API_KEY_ID=<key>
OMNIX_ALPACA_API_SECRET_KEY=<secret>
```

`APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` are accepted fallbacks. `OMNIX_ALPACA_DATA_URL` can override the REST data URL for controlled testing.

The optional IEX trading-status channel is enabled by default when credentials exist. Set `OMNIX_ALPACA_STATUS_STREAM=0` to disable it, or `OMNIX_ALPACA_STREAM_URL` to use a controlled alternate endpoint.

Execution data is stricter than chart/research data. An observation must pass source-time freshness and future-clock-skew checks, recurring US-equity session classification, bid/ask and spread policy, and known-halt rejection before it can drive a paper fill. Missing Alpaca credentials or provider failures fail closed. Never route Yahoo/reference prices into `PaperExecutionService` to make a simulation fill.

## Provider outage procedure

1. Open the Trading **Data** tab and record provider/stream diagnostics.
2. Confirm the selected feed, official/unofficial status, usage scope, and terms reference in the Trading footer.
3. Disable affected background monitors if repeated failures could consume rate limits.
4. Preserve the exact instrument, requested binding, resolved binding, provider, dataset fingerprint, source time, displayed bid/ask size and error.
5. Do not merge partial data from two providers. A fallback replaces the complete requested research dataset; execution does not fall back from Alpaca IEX to Yahoo.
6. Restore the provider or select an allowed compatible binding.
7. Re-enable monitors and verify that retries do not duplicate alert triggers, paper fills, ledger entries, scanner results, strategy events, or protections.
8. Attach the outage/recovery evidence to the release certification record.

Missing, stale, future-dated, cached, fallback, unknown-session, bookless, over-wide, closed-session, or known-halted execution data must produce no paper fill. `reference_price` is reservation evidence only and is never a market-observation fallback.

## Streaming recovery

- Symbol, interval, or binding changes must close the prior subscription before opening the replacement.
- Sequence gaps require deterministic REST repair before live updates continue.
- Repeated duplicate or out-of-order events should be recorded with binding and provider sequence metadata.
- The Alpaca status channel retains a known halt across disconnect. A prior resume is no longer affirmative while disconnected because a later halt could have been missed.
- Stop the Trading gateway if sockets or reconnect attempts become unbounded; do not leave a degraded reconnect loop unattended.

## PostgreSQL migrations and rollback

Trading migrations are under `src/app/persistence/migrations` and must be applied through the existing Omnix migration process.

Before upgrade:

1. Back up the database and BlobStore root.
2. Record the application commit SHA and latest applied migration.
3. Confirm sufficient disk space for datasets, scanner results, backtest evidence, paper ledger history, strategy events, evidence records, model artifacts, and artifacts.

After upgrade:

1. Verify Trading tables and constraints.
2. Restart the gateway.
3. Reload a representative workspace, alert, scanner, dataset, backtest, paper account, frozen universe, and strategy configuration.
4. Verify backtest artifact checksums.
5. Confirm monitor diagnostics and absence of duplicate state changes.
6. Confirm strategy/model migrations preserve `shadow_only` and paper-only constraints.
7. With Alpaca configured, verify the execution provider reports `alpaca_iex`; do not accept Yahoo as execution authority.

Rollback must preserve Trading records and BlobStore artifacts unless a reviewed data migration explicitly removes them. Do not invent legacy signal/fill indices; pre-index backtests retain NULL sequencing evidence.

## BlobStore artifacts

Complete legacy backtest result JSON is stored through `LocalBlobStore`. Relational PostgreSQL rows retain queryable summaries, trades, equity points, and logs. The gap-pullback portfolio backtester additionally freezes its candidate universe and per-symbol bars in a deterministic session dataset fingerprint.

Artifact metadata includes:

- storage provider
- storage key
- SHA-256 checksum
- byte size

On read, checksum mismatch is an integrity failure. Do not serve the corrupted artifact as valid evidence.

### Corrupt or missing artifact

1. Record the run ID, storage key, expected checksum, and error.
2. Keep relational summaries and evidence read-only.
3. Quarantine the corrupt file; do not overwrite it without preserving evidence.
4. Re-run the backtest from the same frozen dataset and strategy/execution policy.
5. Compare the new deterministic result to relational evidence.
6. Link the replacement run; do not silently mutate the original run identity.

### Orphan artifact cleanup

A BlobStore write can succeed before a database transaction fails. The runtime attempts to delete artifacts it created during a failed save. Periodic cleanup may remove unreferenced Trading artifact keys only after comparing them with PostgreSQL run metadata and preserving an audit log.

## Cache and disk cleanup

- Never delete active PostgreSQL authority records as a cache-clearing shortcut.
- Cached/fallback market data must remain distinguishable from live/polled data through provenance.
- Scanner, strategy-event, evidence, model-score, and backtest history are evidence, not disposable browser cache.
- Before deleting local artifacts, verify that no run metadata references their storage key.

## Scanner and gapper discovery operations

Legacy scanner limits remain:

- Maximum allowlist: 200 unique instruments.
- Maximum history: 500 bars per instrument.
- Maximum concurrency: 8.
- Maximum request timeout: 30 seconds.
- Maximum run timeout: 300 seconds.
- Default formulas are versioned as `omnix-indicators-v2`.

Cancel scans that exceed provider policy or operational expectations. Do not broaden the legacy scanner universe dynamically beyond the stored allowlist.

Gap-pullback discovery is a separate point-in-time flow. Two current-only discovery adapters are available:

- `POST /api/trading/strategies/universes/discover-finviz` uses Finviz Top Gainers only to establish the ordered source cohort, then independently enriches prices/volume/instrument identity from Yahoo before freezing the universe.
- `POST /api/trading/strategies/universes/discover-yahoo` retains the legacy Yahoo Day Gainers discovery path.

Neither adapter reconstructs a historical screener later. Each provider/scanner candidate requires an observation timestamp, and field-level evidence timestamps later than the universe freeze are rejected. Finviz archives additionally retain the source locator plus the exact ordered source-symbol cohort so missing enrichment cannot silently erase the original discovery population.

`GapPullbackConfig.universe_discovery_source` selects the automatic morning archive source. Finviz is recommended for the microcap/top-gainer research experiment; Yahoo remains available for legacy/canonical V2 qualification and fallback research.

Time-of-day RVOL compares current cumulative volume with prior sessions truncated at the same New York clock minute. Missing secondary evidence remains explicit rather than causing the candidate to disappear from the denominator.

When `intraday_learning_enabled=true`, the deterministic strategy monitor also writes research-only `intraday_learning` snapshots from finalized one-minute regular-session bars. The snapshots dynamically rank the frozen morning cohort across independent squeeze, failed-selloff, trend, gap-hold and risk dimensions. These events always carry `execution_authority=false` and cannot replace deterministic `entry_ready`, server risk, or Alpaca IEX execution eligibility.

When `intraday_llm_enabled=true`, the monitor uses an event-driven bounded batch of the configured default LLM. Deterministic learning still evaluates every candidate every finalized minute; the LLM normally sees the top 5 only when material state/rank/VWAP/turnover/score changes occur, plus a 10-minute heartbeat for quiet top names during the configured entry window. `entry_ready` candidates are always included. Most calls send compact deltas plus the prior assessment, with a periodic 30-minute full-context refresh. Ordinary event batches are capped at one call per five minutes; a new `entry_ready` transition may bypass that cooldown. Batch events persist trigger reasons and normalized token usage: provider-reported prompt/completion/total tokens when available, otherwise a clearly labeled character/4 estimate fallback. LLM output remains interpretation-only, always `execution_authority=false`, and provider/model failures never block or authorize deterministic paper execution.

### Finviz V2 prospective AUTO PAPER qualification

Finviz V2 has an isolated promotion contract beginning **2026-08-31**. It
cannot inherit canonical Yahoo V2 evidence. The V2 qualification monitor
recognizes two exact replay contracts and writes separate event families for
them. For Finviz it writes `finviz_v2_shadow_replay_trade` and
`finviz_v2_shadow_replay_session`; the operations status exposes
`finviz_replay_count` separately.

Finviz AUTO PAPER remains fail-closed until the exact frozen profile has at
least 20 matched trades across 15 sessions and 10 symbols, at least 90%
execution match, at least +0.20R expectancy, a positive one-sided 90% lower
confidence bound, no more than 5R maximum drawdown, and an explicit operator
review bound to the current evidence fingerprint. Pre-policy history cannot
satisfy these floors.

Once approved, the runtime resolves that day's strategy-owned 09:20 ET Finviz
archive directly; a manually attached universe is rejected for this promoted
profile. The archive must itself have `discovery_source=finviz`. Every AUTO
PAPER entry still passes deterministic strategy state, server risk, fresh
Alpaca IEX execution eligibility, paper fill policy and protection management.
The LLM remains research-only.

After approval, qualification continues to ingest both live SHADOW execution
observations and qualified AUTO PAPER entry observations. New replay evidence
updates the metrics continuously. The profile remains authorized while every
quantitative floor continues to pass; if a floor deteriorates, new AUTO PAPER
entries pause automatically. A strategy execution-profile or qualification
policy-version change invalidates the approval and starts a new prospective
evidence line rather than reusing old results.

## Paper simulation operations

Paper simulation is not brokerage execution.

- Market, Limit, and Stop only.
- Long and short accounting use the same relational paper ledger; automated `gap_pullback_v1` entries are long-only.
- Reset and archive require the current account revision.
- Reset deletes simulated state, records a new explicit deposit, cancels protections, and turns related strategy automation off.
- Archive disables the account, releases reservations, cancels open orders/protections, and turns related strategy automation off without deleting evidence.
- Fill, cash, position, order, and ledger changes commit together under row locks.
- `paper-execution-v2` applies deterministic spread-side pricing, slippage, stop gap-through behavior, observation latency, max liquidity participation, partial fills, stale-data rejection, and halt rejection.
- Manual take-profit/stop-loss protection is PostgreSQL authority. Browser `localStorage` is not a protection source of truth.

For **live** Alpaca IEX observations, liquidity participation uses the displayed size on the side being consumed: ask size for buys and bid size for sells. Alpaca round-lot sizes are normalized to shares. Cumulative daily volume is diagnostic only and must never be interpreted as immediately executable size. Historical backtests fall back to the individual one-minute bar volume because no real-time book exists.

If duplicate fills or ledger entries are suspected, stop the paper monitor and inspect idempotency keys before resuming.

## Gap-pullback automation

The thesis is **buy the first failed sell-off**, not the first sell-off. `gap_pullback_v1` is a deterministic state machine built around confirmed opening structure: opening impulse → confirmed first pullback low (L1) → confirmed bounce high (B1) → confirmed higher second low (L2) → regular-session VWAP reclaim → B1 break → breakout-volume confirmation.

Operational sequence:

1. Before trading, freeze a point-in-time daily gapper universe through the configured Finviz/Yahoo discovery API or **Trading → Strategies → Freeze point-in-time gapper universe**. Preserve every candidate captured at that time, including eventual fades/failures. Finviz learning experiments preserve the raw ordered source cohort separately from the enriched/qualified candidate subset.
2. Candidate evidence should include previous close, premarket/current price and gap, premarket volume/dollar volume, time-of-day RVOL, spread when available, market cap/float when available, catalyst evidence IDs, dilution flags, discovery rank, and observation timestamps when provider/scanner sourced.
3. Any referenced catalyst evidence must have both publication and capture timestamps no later than the universe evaluation time.
4. Start new configurations in `shadow`. Inspect candidate state/reason codes and rejected candidates before enabling `auto_paper`.
5. Run the frozen multi-symbol strategy backtest with `POST /api/trading/strategies/backtest/gap-pullback`. Entry is next-bar.
6. Backtest portfolio arbitration uses `(entry_time, discovery_rank, instrument_id)` and calls the same `size_strategy_entry`, `paper_fill_decision`, and shared protection-trigger policy used by paper automation.
7. Validate prefix invariance/causality: a pivot is unknown until its configured right-side bars exist. Future bars must never alter an already evaluated prefix.
8. `auto_paper` may submit only to the existing paper repository. It additionally requires an execution-eligible Alpaca IEX observation and server risk approval.
9. Risk gates include account-risk sizing, daily loss, aggregate open risk, max positions, max trades/day, one trade/symbol/day, max notional, spread, entry window, force-flat time, and kill switch.
10. Every automated entry receives persisted strategy stop/target protection. Manual paper protection, strategy protection and backtests use the same pessimistic stop-before-target helper. A live whole-minute range is used only when the minute started at or after protection activation.
11. At force-flat time the strategy submits a paper exit only when execution data remains eligible.

If AUTO PAPER is unexpectedly active, set the strategy kill switch and mode to `off`, or set `OMNIX_TRADING_STRATEGY_MONITOR=0` and restart the gateway. Do not use data/research model failures as a reason to bypass execution eligibility.

## Catalyst and AI shadow operations

Catalyst context is an evidence pipeline, not an LLM opinion field.

- Capture timestamped immutable evidence with source type (`sec`, `company`, `news`, `manual`), source locator, publication/capture timestamps, text hash, deterministic facts, and dilution evidence.
- Dilution flags such as ATM, warrants, convertible securities, shelf/resale registration, and equity lines are extracted from supplied evidence and retained with the immutable fingerprint.
- `classify-shadow` can ask the configured model to classify only the supplied evidence IDs. It must cite exactly those IDs and returns `shadow_only=true`.
- Catalyst/AI output is not imported by `strategy_monitor.py` and cannot authorize an order.

Use only sources whose access, retention, and redistribution terms are appropriate for the configured environment. Source acquisition adapters may be added separately; the evidence boundary must remain immutable and timestamped.

## Statistical model operations

The bounce model label is `P(+2R before -1R within 90 minutes)`. Same-bar stop/target ambiguity resolves pessimistically to the stop.

- The transparent baseline score remains shadow-only.
- `POST /api/trading/models/bounce/train` fits a standardized logistic regression from explicit labeled examples and persists coefficients, intercept, feature means/scales, training metadata, log loss, and a SHA-256 artifact fingerprint.
- A model version is immutable: reusing a version with a different fingerprint is rejected.
- `POST /api/trading/models/bounce/score-shadow` persists a shadow score for later out-of-sample evaluation.
- `POST /api/trading/models/bounce/validate-shadow` evaluates a locked artifact on dated OOS examples and reports log loss vs base-rate log loss, Brier score, calibration error/bins, example count and independent-session count.
- Default sufficiency thresholds are 100 OOS examples across at least 20 sessions. Sufficiency is not a profitability claim; it only marks when model metrics begin to have a minimally interpretable evidence volume.
- Model artifacts, validation and scores are deliberately absent from the deterministic strategy monitor. Promotion into any strategy gate requires a separate reviewed change and incremental OOS evidence.

Before interpreting strategy expectancy, review the approximate 95% expectancy interval and adverse spread/slippage/latency stress cases rather than only the point estimate.

Do not interpret training fit, paper results, or a historical backtest as proof of future profitability.

## Research operations

Research is optional and read-only.

- It uses the configured Omnix provider registry.
- It accepts no credentials in requests.
- It uses at most 200 finalized bars and a bounded context.
- Invalid model JSON is rejected; no generic narrative fallback is saved.
- It cannot place orders, create alerts, or mutate scanner/backtest/paper state.

Provider/model errors should not block charting, alerts, scanner use, replay, or paper simulation. Execution-provider failures, however, intentionally block US-equity paper fills.

## Incident record

For Trading incidents record:

- commit SHA and environment;
- workspace/user scope;
- canonical instrument and binding;
- provider and policy scope;
- source/evaluation timestamps and future-skew assessment;
- bid/ask plus displayed sizes when execution-related;
- recurring session classification and known provider halt status;
- frozen universe/dataset fingerprint or artifact checksum;
- candidate/evidence observation timestamps;
- strategy ID/version/mode and candidate reason code when relevant;
- model/evidence fingerprints when relevant;
- relevant revision/idempotency key;
- diagnostics output;
- remediation and validation result.
