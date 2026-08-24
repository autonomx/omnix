# Omnix Trading V2 Prospective Evidence Runbook

This runbook covers the frozen `gap_pullback_v1` `2.0.0` prospective evidence path beginning **2026-08-24**. It is an operations checklist, not a strategy-tuning document. Do not change the frozen profile, reinterpret historical reconstruction as prospective evidence, or expose a sealed holdout to repair a weak result.

## Authority boundary

- V2 begins in `shadow` and has no paper-order authority from prospective telemetry alone.
- The morning archive, SHADOW execution observation, indicator-entry telemetry, prospective signal-feature row, and post-session replay are evidence-only.
- AI/LLM research and prospective feature analysis cannot place or authorize an order.
- AUTO PAPER remains fail-closed until the quantitative qualification floors pass and an operator explicitly reviews the exact evidence fingerprint.
- Alpaca IEX is partial-market evidence, not consolidated SIP/NBBO.

## Before the session

1. Run the normal Omnix web gateway. Do not launch a separate Trading service.
2. Save and enable the exact frozen V2 strategy in `shadow` mode.
3. Confirm Alpaca IEX credentials are configured without exposing the secret in browser state. The halt-status stream uses the same environment-or-protected-store credential resolution as the execution provider.
4. In **Trading → Strategies → Prospective indicator entry evidence**, confirm all three runtime cards are healthy:
   - **Morning archive** — configured and RUNNING.
   - **SHADOW evaluator** — configured and RUNNING.
   - **Post-session replay** — configured and RUNNING.
5. Treat STOPPED, NOT REGISTERED, DISABLED, or a reported monitor error as an evidence-capture incident. Fix the runtime; do not later reconstruct the missed point-in-time observation and call it prospective evidence.
6. Confirm the frozen profile fingerprint shown by qualification matches the canonical V2 profile.

The runtime status API is read-only:

```text
GET /api/trading/strategy-operations/status
```

It reports configured/running state, polling interval, last completed run, last reported error, and monitor counters. Its response carries `execution_authority=false`.

## Morning archive

The enabled strategy-owned archive monitor checks frequently but may capture only inside the configured morning scan/grace window. The frozen V2 profile uses **09:20 ET** with a bounded grace period.

- The archive is immutable and independent of `active_universe_id`.
- A genuine zero-candidate scan is persisted as an empty archive rather than treated as missing data.
- A provider error is not converted into an empty archive unless the provider explicitly reports that no listed equities qualified.
- The archiver never backfills hours later and pretends the data existed at 09:20 ET.

After the scan window, verify the Morning archive counter advanced or inspect the audit log for `daily_universe_archived` / `daily_universe_archive_error`.

## Intraday SHADOW evidence

The deterministic strategy monitor evaluates the strategy-owned raw archive during the normal entry window. For a structural V2 SHADOW signal:

- execution evidence comes from the authoritative Alpaca IEX path;
- indicator context uses same-day Alpaca IEX one-minute bars beginning at **04:00 ET**;
- the hard causal cutoff is the execution observation's `source_time`;
- a one-minute bar is included only if its close was knowable by that cutoff;
- 5-minute indicator values are aggregated only from finalized causal one-minute bars;
- the persisted event records the indicator verdict as confirmed, vetoed, or unavailable plus warm-up coverage and reason codes.

The indicator verdict is research telemetry. It must not be retroactively inserted into frozen V2 execution/qualification authority.

The UI should display the persisted 1m/5m EMA9, EMA20, MACD/signal/histogram, Stoch-RSI K/D, finalized-bar count, source, cutoff, warm-up completeness, and veto reasons. Do not recompute a different rule later and substitute it for the stored verdict.

## Prospective win-rate feature record

Each persisted `shadow_execution` event now carries an immutable `v2-prospective-signal-features-1` record at the execution observation cutoff. The record is deliberately descriptive and has `execution_authority=false`.

It captures the following causal feature families without applying a new entry gate:

- **Premarket structure:** finalized 04:00-09:30 ET IEX bar count, PM open/high/low/close, high/low timestamps, range, PM return, PM VWAP, close-vs-VWAP, close-vs-PM-high, PM volume/dollar volume, and the final 30-minute return.
- **Catalyst quality:** latest fact/report known by the cutoff, primary-source confirmation, same-day status, catalyst type, primary/secondary source counts, official filing/company-release presence, publication time/age, research status, coverage, and unresolved facts.
- **Supply/dilution:** point-in-time supply-resolution state, immediate-supply-risk flag, potential dilution, remaining ATM capacity, in-the-money warrant overhang, registered resale overhang, and typed supply facts with active/terminated/exhausted/etc. status.
- **Halt history:** Alpaca trading-status halt/resume events observed during the session, last halt/resume/status information, and whether the status stream was continuously connected from 04:00 ET. A disconnect makes session halt history incomplete rather than silently assuming no halt.
- **Multi-timeframe momentum:** the already persisted causal 1m/5m EMA9/EMA20, MACD/signal/histogram, Stoch-RSI K/D, and explicit full-warm-up state.

The record includes an immutable SHA-256 fingerprint plus per-family completeness flags. Missing research, sparse IEX bars, a status-stream disconnect, or insufficient indicator warm-up stays missing/partial forever for that signal; do not backfill it later and label it exact prospective evidence.

The Alpaca status cache is intentionally conservative for execution. Halt-history completeness is research metadata only and never converts an unknown execution halt state into an executable one.

## Post-session canonical replay

The V2 qualification monitor runs automatically; there is no manual replay step required for normal operation.

After the regular-session close plus the configured replay grace period, it:

1. looks back across recent prospective trading sessions;
2. resolves the immutable strategy-owned morning archive for each session;
3. loads Alpaca IEX historical session bars;
4. replays the exact frozen V2 configuration using deterministic paper/backtest semantics;
5. persists idempotent `v2_shadow_replay_trade` events for replayed trades;
6. persists one completed `v2_shadow_replay_session` event, including zero-trade sessions;
7. keeps `execution_authority=false` throughout.

If a finalized session has no immutable raw archive, the monitor must not reconstruct one and count it as prospective evidence.

## Prospective winner/loser attribution

`strategy_prospective_dataset.py` deterministically joins a captured SHADOW feature row to the canonical replay outcome only when symbol/session match and the signal is within the frozen V2 live-match window. One live feature row can be consumed only once. The joined row contains the exact feature fingerprint plus replay `R`, MFE, and MAE.

The reporting script is provider-free:

```text
python scripts/run_trading_strategy_v2_prospective_winrate_attribution.py \
  --strategy-id <saved-strategy-id>
```

Until at least **20 matched outcomes** with at least **5 winners and 5 losers** exist, the script reports `collecting_prospective_outcomes` and emits no winner/loser feature attribution. Once ready, it reports predeclared descriptive feature medians and Cliff's delta; it does not search thresholds or grant strategy authority.

Any pattern discovered from the first prospective attribution block is still hypothesis generation. Freeze a future successor rule before evaluating it on a later untouched/prospective validation block. Do not promote a threshold on the same outcomes used to discover it.

## Qualification review

Prospective qualification requires all frozen floors simultaneously:

- at least **20** matched eligible trades;
- at least **15** distinct sessions;
- at least **10** distinct symbols;
- execution-match rate at least **90%**;
- expectancy at least **+0.20R**;
- one-sided **90% lower confidence bound > 0R**;
- maximum drawdown no greater than **5R**.

A passing quantitative sample is still not AUTO PAPER authorization. The operator must review the exact profile/evidence fingerprint and record an explicit promotion note. Any evidence change invalidates that review and requires a new one.

Qualification is evidence about this prospective paper process, not proof of future profitability.

## Incident handling

If prospective capture is incomplete:

1. record the commit SHA, strategy ID/revision, profile fingerprint, session, monitor status and last error;
2. preserve existing events/universes/logs unchanged;
3. repair credentials/provider/runtime configuration;
4. verify monitors return to RUNNING and counters advance normally;
5. mark the missed evidence as missing rather than synthesizing it;
6. continue the prospective sample on later sessions.

Do not loosen qualification floors, change V2 parameters, retrospectively add filters, or expose sealed holdout data to compensate for an operational or statistical shortfall.
