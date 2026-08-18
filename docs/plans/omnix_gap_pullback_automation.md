# Omnix gap-pullback automation

## Thesis

**Don't predict the bottom. Detect a failed continuation downward, prove that detection is causal, and only trade it when realistic execution still leaves positive expectancy.**

The target setup is a volatile overnight gapper that establishes an opening impulse, sells off, then demonstrates that sellers have failed to continue the move lower. The automated strategy is deliberately narrower than “buy a dip”:

`gap / opening impulse → L1 first confirmed pullback low → B1 confirmed bounce high → L2 confirmed higher low → regular-session VWAP reclaim → B1 break → breakout-volume confirmation`

A signal is not valid until L2 is confirmed. Pivot confirmation uses configured right-side bars; the system never labels a pivot at a time when those bars did not yet exist.

## Safety boundary

The implementation has three execution modes only:

- `off`: no strategy evaluation/execution work beyond persisted configuration.
- `shadow`: evaluate and persist deterministic state/reason evidence, but create no orders.
- `auto_paper`: submit only to Omnix paper trading after execution-data and server-risk gates pass.

There is no live-broker mode. AI catalyst classification and statistical model scores are shadow-only and are intentionally absent from `strategy_monitor.py`.

## Data-source boundary

US-equity research and execution deliberately use different providers:

- **Yahoo** supplies symbol discovery, historical/chart bars and the current top-gainer research universe. Yahoo can never authorize a paper fill.
- **Alpaca IEX** supplies the authoritative real-time bid/ask/trade observation for US-equity paper execution. IEX is explicitly recorded as a **partial-market** feed and is never described as consolidated SIP/NBBO coverage.
- If Alpaca credentials are missing, a quote is stale/future-dated/bookless/over-wide, the recurring US-equity calendar says the session is closed, or provider trading-status evidence says the symbol is halted, execution fails closed.

The provider identity is retained with execution evidence so future IEX-vs-SIP comparisons can quantify feed effects rather than assuming equivalence.

## P0 — execution correctness

### Execution-data contract

`ExecutionObservation` separates chart/research prices from execution evidence. Paper execution records source timestamp, receipt timestamp, session, bid/ask, displayed sizes, latest trade, optional current-minute range/volume, freshness class, halt evidence and explicit eligibility.

Execution rejects:

- stale observations;
- source timestamps beyond the allowed future clock-skew tolerance;
- missing bid/ask;
- excessive spread;
- cached/fallback/unknown freshness;
- closed recurring US-equity sessions, including standard holidays and early closes;
- a known provider trading halt.

Unscheduled exchange closures remain provider-status events. Loss of the optional status stream never turns unknown status into a positive “not halted” assertion; a previously known halt remains fail-closed until resume evidence is observed.

Yahoo remains research/diagnostic only. `ProviderRegistry` overlays an equity Yahoo/Stooq chart binding onto the corresponding Alpaca IEX execution binding while preserving the requested persisted binding ID for existing paper orders.

### Paper execution v2

`paper-execution-v2` is the shared deterministic fill policy used by paper monitoring and the gap-pullback portfolio backtester. It models:

- bid/ask-side market pricing;
- deterministic slippage;
- worse-price stop gap-through behavior;
- observation latency;
- stale and halted-market rejection;
- maximum liquidity participation;
- partial fills;
- commissions and transactional ledger/position/order updates.

**Liquidity is not inferred from cumulative daily volume.** Live Alpaca observations prefer side-specific displayed top-of-book size (`ask_size` for buys, `bid_size` for sells). Historical observations fall back to the individual bar's volume. This prevents a million-share daily total from being treated as immediately executable size.

Caller `reference_price` is reservation evidence only. Browser observations are non-authoritative and cannot produce fills.

### Shared protection semantics

Manual paper protection, automated strategy protection and historical backtesting use the same pessimistic stop-before-target trigger helper. A minute range is trusted only when its bar started at or after the position/protection activation time; this prevents a pre-entry low/high in the same minute from being misclassified as a post-entry stop/target touch.

Manual paper take-profit/stop-loss state is persisted in PostgreSQL, not `localStorage`. The paper monitor implements OCO-style first-trigger behavior. Strategy entries have separate persisted strategy protections so automated stop/target/force-flat state survives browser reloads.

### Server-authoritative risk

Server strategy risk includes risk per trade, daily loss, open risk, max positions, max trades/day, max notional, one trade/symbol/day, spread, entry window, force-flat time and kill switch. Reset/archive operations cancel protection and turn related strategy automation off.

## P1 — deterministic research, discovery and backtesting

### Point-in-time Yahoo gapper discovery

`POST /api/trading/strategies/universes/discover-yahoo` performs **current-only** Yahoo top-gainer discovery and immediately freezes the result. The server rejects attempts to use this route as a historical screener reconstruction because doing so later would introduce hindsight/survivorship bias.

For each qualifying listed equity, the discovery path records the observation time and computes point-in-time evidence including normalized previous close, observed premarket/current price, gap %, premarket volume/dollar volume, time-of-day relative volume, spread when available, market cap/float when available and discovery rank. Time-of-day RVOL compares the current cumulative volume only with historical sessions truncated at the same New York clock minute.

Missing secondary evidence does not silently remove a candidate. The candidate is retained and the deterministic strategy can reject it explicitly (for example `TOD_RVOL_MISSING`). This preserves eventual failures/fades in the denominator.

### Immutable universe provenance

`GapperUniverseSnapshot` is immutable and fingerprinted. Candidate snapshots may carry `observed_at` plus field-level `evidence_observed_at` timestamps. Provider/scanner freezes require a candidate observation timestamp, and any candidate evidence occurring after `evaluation_time` is rejected.

If a candidate cites catalyst evidence IDs, the strategy API resolves those immutable records and rejects a freeze/backtest when either publication or capture occurred after the universe evaluation time. Direct immutable-universe uploads are re-fingerprinted by the server before persistence.

Manual/imported candidate JSON remains supported for externally captured datasets, but historical tests must reuse the exact frozen universe rather than reconstructing one from later winners.

### Causal gap_pullback_v1

The strategy runs on finalized one-minute regular-session bars. Regular-session VWAP resets at 09:30 America/New_York. Confirmed pivots require both left and right bars. The implementation exposes deterministic state and reason codes rather than an opaque score.

The causality gate is **prefix invariance**: evaluation results for any historical prefix must be identical regardless of bars appended later. Tests also verify that L1 is not visible until its required right-side confirmation exists.

### Portfolio backtest and paper parity

A morning gapper strategy selects among multiple simultaneous candidates, so backtesting is session/portfolio based rather than only single-symbol. Frozen session datasets include the universe and per-symbol bars in one fingerprint. Entry uses the next bar after the trigger.

Parity is defined across the full decision path, not merely by calling the same fill helper:

`signal → chronological candidate arbitration → server risk sizing → execution observation → paper_fill_decision → shared protection trigger → exit fill`

Backtests therefore:

- use `paper-execution-v2` / `paper_fill_decision`;
- call the same `size_strategy_entry` server-risk function as AUTO PAPER;
- track virtual account cash/equity, realized daily PnL, open risk and open positions;
- use `(entry_time, discovery_rank, instrument_id)` as the deterministic simultaneous-trigger tie-break, matching the frozen universe priority;
- rerun the fill engine with the actual risk-sized quantity so liquidity/partial-fill effects apply to the requested trade size;
- use the same pessimistic stop-before-target trigger helper as paper monitors.

Reported evidence includes trigger/trade counts, risk-rejection reasons, R multiple, expectancy, approximate 95% expectancy interval, profit factor, MFE, MAE, hold duration, slippage and candidate-to-trigger conversion. Walk-forward split support separates sequential training/test sessions.

Replay gap validation is session aware: normal overnight/weekend exchange closures are not reported as missing intraday bars, while missing bars inside one continuous session are.

## P2 — automated paper runner and terminal

The gateway owns a deterministic strategy monitor with bounded polling and environment controls. The runner loads active configurations and the attached frozen universe, evaluates each candidate, checks Alpaca IEX execution eligibility, applies server risk, creates idempotent paper orders, persists state/rejection events and reconciles server stop/target protection.

The Strategies workspace provides:

- strategy mode/account/universe selection;
- server risk controls and kill switch;
- point-in-time universe JSON import/freeze;
- candidate state/rejection visibility;
- active server protection visibility;
- explicit paper-only and shadow-only safety messaging.

Current-only Yahoo discovery is available through the strategy API and can be used by the terminal/automation layer to freeze the morning universe without reconstructing it later.

## P3 — catalyst evidence and AI shadow classification

Catalyst context is stored as timestamped immutable evidence, not an ungrounded LLM opinion. Evidence carries source type/locator, publication/capture timestamps, text hash, structured facts, deterministic dilution flags and an immutable fingerprint.

The shadow classifier receives only selected stored evidence and must cite exactly those evidence IDs in its structured output. Classification includes catalyst class, directional bias, novelty, dilution risk and confidence. `shadow_only=true` is enforced by contract. The deterministic strategy does not consume this output.

Source acquisition is intentionally separated from the evidence boundary so SEC/company/news adapters can respect environment-specific licensing and credentials without weakening immutability or causality.

## P4 — statistical bounce model

The model label is `P(+2R before -1R within 90 minutes)`. Same-bar stop/target ambiguity resolves pessimistically to the stop.

The feature contract includes gap %, premarket dollar volume, TOD RVOL, float/market cap logs, spread, opening impulse, HOD distance, pullback depth/volume, L2/L1, VWAP distance/slope, breakout volume, ATR %, time since open, catalyst flags and dilution evidence.

A transparent standardized logistic-regression fitter produces persisted versioned artifacts containing coefficients, intercept, normalization statistics, training metadata, log loss and an immutable fingerprint. Model versions cannot be silently overwritten with different payloads. Scores remain shadow-only.

`POST /api/trading/models/bounce/validate-shadow` evaluates a locked model on dated out-of-sample examples and reports:

- OOS log loss;
- base-rate log loss and improvement;
- Brier score;
- calibration bins and expected calibration error;
- independent session count and example count;
- an explicit evidence-volume sufficiency flag.

Default evidence-volume thresholds are 100 labeled OOS examples across at least 20 sessions. Meeting those counts is **not** proof of profitability; it only means the sample is large enough to start interpreting OOS metrics. A boosted-tree model remains deliberately deferred until the transparent baseline has enough frozen OOS evidence to justify added complexity.

## Release gates

1. **Execution correctness:** caller/reference prices cannot fill; stale/future-dated/unavailable/ineligible data fails closed; spread/slippage/stop-gap/latency/liquidity/partial-fill behavior is deterministic.
2. **Feed correctness:** Yahoo cannot authorize fills; Alpaca IEX is recorded as partial-market evidence; displayed book size rather than daily cumulative volume controls live participation; known halts reject execution.
3. **Session correctness:** recurring US-equity holidays/early closes and extended-session boundaries classify deterministically; provider status handles symbol-specific halts and exceptional status events.
4. **Strategy causality:** right-side pivot confirmation and prefix invariance pass.
5. **Backtest/paper parity:** both use the shared risk-sizing, fill and protection-trigger policies, with deterministic chronological candidate arbitration.
6. **Point-in-time research:** provider/scanner universes have observation timestamps; future candidate/catalyst evidence is rejected; historical tests reuse frozen universes.
7. **Automated paper only:** strategy monitor has no broker order adapter and no AI/model execution dependency.
8. **AI/model shadow:** catalyst and model results remain evaluative until a separate reviewed change demonstrates incremental out-of-sample value.
9. **Lifecycle safety:** resetting or archiving a paper account disables associated automation and cancels protection state.
10. **Operational data:** Alpaca IEX credentials must be configured for US-equity AUTO PAPER. IEX remains a partial-market paper-execution source; no result may be presented as SIP/NBBO or live-fill equivalence.
11. **Evidence before promotion:** parameter changes are locked before OOS evaluation; sequential walk-forward evidence, expectancy uncertainty and adverse spread/slippage/latency stress cases must be reviewed before any future promotion beyond experimental paper use.

Paper or historical results are research evidence, not a profitability guarantee.
