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

## P0 — execution correctness

### Execution-grade market-data contract

`ExecutionObservation` separates chart/research prices from execution evidence. Paper execution requires source timestamp, receipt timestamp, session, bid/ask book, spread, freshness class and explicit eligibility. Missing/stale/cached/fallback/unknown or over-wide observations fail closed.

The current Yahoo equity endpoint is retained for research/diagnostics but is explicitly marked `PROVIDER_NOT_EXECUTION_GRADE`. That means US-equity `auto_paper` will safely refuse to fill until an approved execution-grade equity provider is configured. This is intentional; the implementation does not pretend an unofficial delayed/polled source is equivalent to broker-quality execution data.

### Paper execution v2

`paper-execution-v2` is the shared deterministic fill policy used by paper monitoring and the gap-pullback portfolio backtester. It models:

- bid/ask-side market pricing;
- deterministic slippage;
- worse-price stop gap-through behavior;
- observation latency;
- stale and halted-market rejection;
- maximum volume participation;
- partial fills;
- commissions and transactional ledger/position/order updates.

Caller `reference_price` is reservation evidence only. Browser observations are non-authoritative and cannot produce fills.

### Server-authoritative protection and risk

Manual paper take-profit/stop-loss state is persisted in PostgreSQL, not `localStorage`. The paper monitor implements OCO-style first-trigger behavior. Strategy entries have separate persisted strategy protections so automated stop/target/force-flat state survives browser reloads.

Server strategy risk includes risk per trade, daily loss, open risk, max positions, max trades/day, max notional, one trade/symbol/day, spread, entry window, force-flat time and kill switch. Reset/archive operations cancel protection and turn related strategy automation off.

## P1 — deterministic research and backtesting

### Point-in-time gapper universe

`GapperUniverseSnapshot` is immutable and fingerprinted. It records the discovery timestamp/source and every candidate that was eligible at that time, including eventual failures and fades. Candidate evidence supports previous close, premarket price/gap, premarket volume/dollar volume, time-of-day RVOL, spread, market cap, float, catalyst evidence IDs, dilution flags and discovery rank.

The terminal can freeze normalized imported candidate JSON server-side. Historical tests must reuse the exact frozen universe; they must not reconstruct a universe from later winners.

### Causal gap_pullback_v1

The strategy runs on finalized one-minute regular-session bars. Regular-session VWAP resets at 09:30 America/New_York. Confirmed pivots require both left and right bars. The implementation exposes deterministic state and reason codes rather than an opaque score.

The causality gate is **prefix invariance**: evaluation results for any historical prefix must be identical regardless of bars appended later. Tests also verify that L1 is not visible until its required right-side confirmation exists.

### Multi-symbol portfolio backtest

A morning gapper strategy selects among multiple simultaneous candidates, so backtesting is session/portfolio based rather than only single-symbol. Frozen session datasets include the universe and per-symbol bars in one fingerprint. Entry uses the next bar after the trigger. The same `paper_fill_decision` engine used by paper monitoring controls simulated execution.

Reported evidence includes trigger/trade counts, R multiple, expectancy, profit factor, MFE, MAE, hold duration and candidate-to-trigger conversion. Walk-forward split support separates sequential training/test sessions.

Replay gap validation is session aware: normal overnight/weekend exchange closures are not reported as missing intraday bars, while missing bars inside one continuous session are.

## P2 — automated paper runner and terminal

The gateway owns a deterministic strategy monitor with bounded polling and environment controls. The runner loads active configurations and the attached frozen universe, evaluates each candidate, checks execution eligibility, applies server risk, creates idempotent paper orders, persists state/rejection events and reconciles server stop/target protection.

The Strategies workspace provides:

- strategy mode/account/universe selection;
- server risk controls and kill switch;
- point-in-time universe JSON import/freeze;
- candidate state/rejection visibility;
- active server protection visibility;
- explicit paper-only and shadow-only safety messaging.

## P3 — catalyst evidence and AI shadow classification

Catalyst context is stored as timestamped immutable evidence, not an ungrounded LLM opinion. Evidence carries source type/locator, publication/capture timestamps, text hash, structured facts, deterministic dilution flags and an immutable fingerprint.

The shadow classifier receives only selected stored evidence and must cite exactly those evidence IDs in its structured output. Classification includes catalyst class, directional bias, novelty, dilution risk and confidence. `shadow_only=true` is enforced by contract. The deterministic strategy does not consume this output.

Source acquisition is intentionally separated from the evidence boundary so SEC/company/news adapters can respect environment-specific licensing and credentials without weakening immutability or causality.

## P4 — statistical bounce model

The model label is `P(+2R before -1R within 90 minutes)`. Same-bar stop/target ambiguity resolves pessimistically to the stop.

The feature contract includes gap %, premarket dollar volume, TOD RVOL, float/market cap logs, spread, opening impulse, HOD distance, pullback depth/volume, L2/L1, VWAP distance/slope, breakout volume, ATR %, time since open, catalyst flags and dilution evidence.

A transparent standardized logistic-regression fitter now produces persisted versioned artifacts containing coefficients, intercept, normalization statistics, training metadata, log loss and an immutable fingerprint. Model versions cannot be silently overwritten with different payloads. Scores are persisted for out-of-sample comparison and remain shadow-only; they do not gate paper orders.

A boosted-tree model is deliberately not added until the logistic baseline has enough frozen out-of-sample sessions to justify more complexity.

## Release gates

1. **Execution correctness:** caller/reference prices cannot fill; stale/unavailable/ineligible data fails closed; spread/slippage/stop-gap/latency/partial-fill behavior is deterministic.
2. **Strategy causality:** right-side pivot confirmation and prefix invariance pass.
3. **Backtest/paper parity:** both use `paper-execution-v2` / `paper_fill_decision`.
4. **Automated paper only:** strategy monitor has no broker adapter and no AI/model execution dependency.
5. **AI/model shadow:** catalyst and model results remain evaluative until a separate reviewed change demonstrates incremental out-of-sample value.
6. **Lifecycle safety:** resetting or archiving a paper account disables associated automation and cancels protection state.
7. **Operational data:** a real execution-grade US-equity feed must be configured before US-equity AUTO PAPER can produce fills.

Paper or historical results are research evidence, not a profitability guarantee.
