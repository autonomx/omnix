# Prospective Gap End-to-End Runtime

Status: implemented on the prospective-gap end-to-end runtime branch.

## Goal

Move the daily Top-10 prospective experiment from a Markdown-first reporting
workflow to a machine-readable Omnix authority pipeline while preserving the
existing scientific baselines.

The authority order is:

1. external/Finviz research discovers and researches the frozen Top-10 cohort;
2. the scheduler submits one typed premarket freeze to Omnix;
3. Omnix persists immutable v3/v4 evidence and forecasts;
4. Omnix advances post-open confirmation internally;
5. Omnix records execution-cost-qualified Portfolio E authorization receipts;
6. Omnix deterministically derives post-close outcomes from formal market data;
7. Markdown is rendered from the persisted ledger.

Markdown is never forecast, action, or outcome authority.

## Runtime API

The gateway exposes:

- `POST /api/trading/prospective-gap/premarket/freeze`
- `POST /api/trading/prospective-gap/confirmation/run`
- `POST /api/trading/prospective-gap/postclose/finalize`
- `GET /api/trading/prospective-gap/session/{YYYY-MM-DD}`
- `GET /api/trading/prospective-gap/session/{YYYY-MM-DD}/markdown`

The external scheduled research workflow should call only the premarket freeze in
normal operation. Confirmation and post-close finalization are owned by the
background monitor after the session exists. The explicit confirmation/finalize
endpoints remain available for recovery and deterministic operator replay.

## Durable authority

`ProspectiveGapRepository` stores the experiment in the existing durable
`StrategyEvent` persistence using strategy id:

`prospective-gap-experiment`

The ledger stores versioned records for:

- session manifest;
- submitted premarket model input and optional immutable evidence snapshot;
- causal premarket market state;
- v3 forecast;
- every v4 model attempt as PRODUCED / FAILED / NOT_APPLICABLE;
- frozen v4 forecast, catalyst decomposition, extension-risk head, calibrator artifact, and economic distribution;
- post-open confirmation transitions;
- trade authorization receipts;
- formal post-close outcomes;
- legacy A/B/C/D portfolio freeze and deterministic post-close scores;
- Portfolio E;
- daily data/model/trading scorecard;
- the inactive preregistered v4.1 research specification.

Every write is idempotent and bound to session, cohort, instrument, event type,
and payload fingerprint.

## Premarket evidence recovery

The shared market-data service now supports explicit bounded intraday windows.

For the prospective experiment the canonical premarket request is:

- session: `extended_pre`;
- interval: RAW 1-minute;
- start: 04:00 ET;
- end: the **actual forecast freeze time**, never later than the formal cutoff;
- provider authority: Yahoo;
- extended hours enabled;
- durable evidence first;
- one exact-range provider repair when permitted;
- no synthetic prices;
- late/recovered-after-freeze observations cannot enter the frozen forecast.

The runtime records:

- durable/fetched/canonical bar counts;
- coverage ratio;
- unresolved missing buckets;
- dataset fingerprint;
- provider failure reason.

Coverage below 90% cannot be silently called COMPLETE.

This is separate from the regular-session recovery contract because the prior
`recovered_bars()` path was intentionally regular-session oriented.

## Forecast integrity

`prospective-gap-v3` remains the champion scientific baseline.

`prospective-gap-v4-shadow` remains frozen. No coefficient, threshold, or
calibrator is changed by this implementation.

The runtime computes v4 from:

- the causal premarket market-state snapshot;
- submitted catalyst decomposition;
- existing mechanism scores;
- deterministic extension/exhaustion derivation;
- immutable calibrator artifact.

If critical evidence is unavailable, v4 cannot be produced. Missing noncritical
enrichment remains DEGRADED and scoreable.

## Post-open action authority

A premarket probability is not permission to allocate capital.

For each frozen v4 forecast, Omnix evaluates the existing deterministic
failed-selloff/gap-pullback authority and records:

`WAIT_OPEN -> OBSERVE_INITIAL_STRUCTURE -> OBSERVE_PULLBACK -> CONFIRMED_LONG`

or:

`INVALIDATED / EXPIRED / SUSPENDED_DATA_QUALITY`

The monitor runs during the configured early-session confirmation window.
Temporary current-data failures are nonterminal. Session-wide dependencies such
as cumulative VWAP remain blocked when unresolved gaps invalidate them.

## Portfolio E

A/B/C/D remain unchanged scientific baselines.

Portfolio E is a separate forward shadow policy:

`prospective-gap-portfolio-e-v1`

Default guardrails:

- v4 probability must be above 50%;
- deterministic `CONFIRMED_LONG` required;
- fresh execution observation with bid/ask required;
- frozen gross return distribution required;
- expected net return after spread/slippage/impact must be positive;
- net q10 must remain above the configured downside threshold;
- maximum three positions;
- maximum 20% of starting equity per position;
- unused capital remains cash;
- no redistribution merely to reach 100% invested.

If return economics or execution evidence is unavailable, the recorded result is
`NO_TRADE`. The runtime never invents an expected return.

If Omnix crashes after persisting `CONFIRMED_LONG` but before persisting its
authorization receipt, restart recovery does **not** query a later quote and
pretend it was available at the original decision time. It records a fail-closed
`NO_TRADE` with `AUTHORIZATION_WINDOW_MISSED_AFTER_CONFIRMATION`.

## Deterministic post-close authority

Post-close finalization routes through shared market-data recovery and then the
existing formal outcome derivation.

When direct SIP trade-event authority is unavailable, the already-versioned RAW
SIP 5-minute fallback requires both regular-session boundaries and computes:

- analysis open/close;
- normalized OLS slope;
- cumulative-session VWAP occupancy;
- observed/wall-clock occupancy above open;
- directional efficiency;
- MAE/MFE;
- closing-range position;
- session coverage/gap minutes;
- `close_above_open_v1`;
- `persistent_uptrend_v1`;
- `session_regime_v1`.

Thus `UNSCORABLE` should represent inadequate evidence rather than the
reporting agent lacking a calculation surface.

## Daily scorecard

The final machine-readable scorecard separates:

### Data

- COMPLETE / DEGRADED / INSUFFICIENT counts;
- unresolved premarket 1-minute bars.

### Model

- v3 Brier/log-loss/accuracy/precision/recall/climatology skill;
- v4 equivalents;
- paired v4-minus-v3 Brier/log-loss/absolute-error deltas;
- independently persisted v4 model-state attempts so missing forecasts cannot
  disappear from evaluation.

### Action/trading

- confirmation receipt count;
- confirmed-long count;
- LONG / NO_TRADE authorizations;
- A/B/C/D returns scored from the same formal post-close price authority;
- Portfolio E cost-adjusted return.

This separation is required so a provider failure, forecast miss, confirmation
failure, and sizing loss are not conflated.

## Background monitor

`ProspectiveGapMonitor` is enabled by default outside legacy tests.

After a session manifest exists it:

- evaluates confirmation once per monitor interval from 09:30-11:35 ET;
- finalizes the session once after 16:20 ET;
- records errors without silently rewriting prior state.

Runtime health is exposed in the Trading strategy-operations status endpoint
under `prospective_gap_monitor`.

## v4.1 preregistration

`prospective_prediction_v41.py` is deliberately inactive.

Version:

`prospective-gap-v4.1-shadow`

Activation state:

`PRE_REGISTERED_NOT_ACTIVE`

September 15, 16, 17, 18, and 21 are design evidence and are excluded from its
future validation set. The first eligible forward session is September 22,
2026.

The preregistered hypothesis introduces separate mechanism heads for:

- fundamental repricing;
- theme/squeeze momentum;
- low-information technical momentum;
- continuation demand;
- opening exhaustion;
- supply/fade risk.

Opening exhaustion is an explicit negative predictive input instead of only a
diagnostic field.

v4.1 also requires an economic return distribution for action:

- q10/q50/q90;
- expected return;
- expected shortfall;
- P(return > 2%);
- P(return < -5%);
- expected MAE/MFE when available.

No promotion review is allowed before at least 10 forward sessions and 100
forward observations.

## Scheduler contract

The existing scheduled premarket research job still owns qualitative catalyst
research and the same pre-open Top-10 cohort selection. It must submit its
machine-readable cohort/catalyst/v3 inputs to the premarket freeze endpoint
before the regular-session open.

The post-close scheduled report should read the finalized ledger/Markdown
projection rather than re-derive outcomes independently.

If the premarket submit never reaches a running Omnix instance, the monitor
records no session and does not fabricate one. This is intentionally fail-closed
and is visible through the `no_session_count` runtime counter.

## Scheduled inbox bridge

The cloud/scheduled research workflow and the local Omnix runtime are joined by:

`resources/trading/prospective_gap_inbox/YYYY-MM-DD.json`

The preferred payload is `SchedulerPremarketHandoff`
(`prospective-gap-scheduler-handoff-v1`). It intentionally contains only
research facts the scheduler can know safely: frozen Finviz rank/symbol,
premarket price/gap/volume, optional float/liquidity/supply facts, frozen v3
probabilities, catalyst decomposition, mechanism scores, regime tags and causal
timestamps.

The scheduler **must not** fabricate internal `GapperCandidate`,
`FrozenForecast`, calibrator or market-state objects. It does supply a required
prior-FINAL climatology checkpoint (`through_session_date`, `n`,
`positives`) so a day whose runtime session was unavailable does not disappear
from the next baseline. Omnix validates that checkpoint against its own ledger,
rejects stale/conflicting checkpoints, constructs the internal objects, applies
the immutable identity calibrator, and performs live Yahoo RAW one-minute
enrichment.

The monitor deliberately waits until **09:26–09:29 ET** to ingest a handoff
written earlier in the morning. The scheduler's original research timestamp
remains the frozen boundary for v3/v4. Only v4.2 receives a separate late
premarket state stamped at the **actual ingestion time**, never the future 09:29
cutoff. That makes late-premarket VWAP/range/turnover/acceleration/volume-share
evidence available to v4.2 without moving the older paired v3/v4 experiment
forward in time. If the handoff is first received after the cutoff, ingestion fails
closed; v4.2 is never backfilled after the open.

The older full `PremarketFreezeRequest` file remains supported for explicit
operator/API workflows.

### Official climatology migration

Machine authority no longer depends on copying the previous morning's text.
The versioned migration anchor through **2026-09-22** is:

- N = 40 confirmed prospective observations;
- positives = 17;
- q = 42.5%.

For later sessions, FINAL runtime outcomes advance those counts. When a prior
day had no runtime session, the scheduler may bridge that gap with the explicit
prior post-close FINAL `NEXT_BASELINE` checkpoint. A checkpoint can move the
sample forward but cannot roll back or conflict with runtime-known history.
This prevents a stale morning baseline such as N=30/13 from being reused after
a later post-close review has already finalized more observations.

Local inbox files take precedence. Because the scheduled research agent commits the
handoff to public GitHub `main`, the default Omnix runtime also has a
read-only remote fallback to:

`https://raw.githubusercontent.com/autonomx/omnix/main/resources/trading/prospective_gap_inbox/{session_date}.json`

This removes any requirement for the running Omnix checkout to have already
performed a `git pull`. The remote template can be overridden or disabled with
`OMNIX_TRADING_PROSPECTIVE_GAP_REMOTE_INBOX_URL_TEMPLATE`. The same schema,
timestamp and cutoff validation applies to local and remote payloads.

Invalid payloads fail closed and increment `scheduler_handoff_error_count`.

## v4.2 complete-evidence challenger

After the 2026-09-22 outcome was observed, any changes motivated by that session were versioned as a new challenger rather than modifying v4.1.

`prospective-gap-v4.2-shadow` begins forward validation on 2026-09-23. September 15, 16, 17, 18, 21, and 22 are design evidence only for v4.2.

v4.2 requires verified sparse-event premarket evidence, explicit remaining-upside modeling, nonlinear extension/supply/liquidity/finality interactions, mechanism-specific continuation heads, and a full economic return distribution. See `docs/trading/PROSPECTIVE_GAP_V42_SHADOW.md`.
