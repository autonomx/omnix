# Prospective Gap End-to-End Runtime

Status: implemented on the prospective-gap end-to-end runtime branch.

## Goal

Move the daily Top-10 prospective experiment from a Markdown-first reporting
workflow to a machine-readable Omnix authority pipeline while preserving the
existing scientific baselines.

The authority order is:

1. external/Finviz research discovers and researches the frozen Top-10 cohort;
2. the scheduler publishes one lightweight typed research handoff;
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

The direct premarket freeze API remains available for operator/in-process use.
The cloud scheduler normally publishes `prospective-gap-scheduler-handoff-v1`;
the background monitor converts it into the strict runtime freeze. Confirmation
and post-close finalization remain owned by Omnix after the session exists.

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

The cloud/scheduled research workflow and Omnix are joined by:

`resources/trading/prospective_gap_inbox/YYYY-MM-DD.json`

The cloud payload is a `SchedulerPremarketHandoff`, not a full
`PremarketFreezeRequest`. That distinction prevents the scheduler from
inventing runtime-owned market objects merely to satisfy an internal schema.

Transport order:

1. prefer the local inbox file when the checkout is current;
2. otherwise read the same file from GitHub `main` with the authenticated
   `gh api` client;
3. never auto-pull, merge, or mutate the working tree as part of market
   authority.

The monitor waits until **09:24 ET** so late premarket demand is represented,
but stops initiating new handoffs after **09:27:59 ET**. The runtime must finish
provider recovery by the handoff's formal cutoff (normally 09:29 ET).

Causality uses separate timestamps for cohort discovery, scheduler research
freeze, provider receipt, and runtime completion. Data fetched after the formal
cutoff cannot be admitted by assigning it an earlier timestamp. Invalid or late
payloads fail closed and increment `scheduler_handoff_error_count`.

## v4.2 complete-evidence challenger

After the 2026-09-22 outcome was observed, any changes motivated by that session were versioned as a new challenger rather than modifying v4.1.

`prospective-gap-v4.2-shadow` begins forward validation on 2026-09-23. September 15, 16, 17, 18, 21, and 22 are design evidence only for v4.2.

v4.2 requires verified sparse-event premarket evidence, explicit remaining-upside modeling, nonlinear extension/supply/liquidity/finality interactions, mechanism-specific continuation heads, and a full economic return distribution. See `docs/trading/PROSPECTIVE_GAP_V42_SHADOW.md`.


## Scheduler handoff v1

The cloud scheduler no longer constructs runtime-owned market objects.

It writes a lightweight `prospective-gap-scheduler-handoff-v1` manifest containing only:
- immutable Finviz cohort/rank order;
- `discovered_at`;
- `research_frozen_at`;
- formal prediction cutoff;
- frozen v3 probabilities;
- frozen v4 raw/calibrated probability, extension-risk score, and evidence-quality label;
- numeric catalyst/mechanism research outputs;
- optional causal float/market-cap/RVOL/supply/regime fields;
- latest confirmed climatology through-session plus counts.

At Omnix ingestion time, the runtime reconstructs:
- previous close;
- premarket price;
- canonical RAW one-minute extended-hours tape;
- premarket volume/dollar volume;
- gap;
- prior-session returns;
- VWAP/range/late-demand features;
- full `GapperCandidate`, `FrozenForecast`, and identity-calibrator runtime objects.

The earlier `research_frozen_at` remains the paired v3 **and frozen-v4**
research boundary. The runtime must persist those exact scheduler-time
probabilities rather than recomputing v4 from the later tape. Only v4.2 consumes
the runtime-enriched late premarket state. The runtime completion timestamp is
the v4.2 market-state freeze boundary. Provider
`received_at` timestamps are retained, and both the provider evidence and the
runtime completion must be no later than the formal cutoff.

The monitor checks the local inbox first and then uses read-only authenticated
`gh api` fallback when needed. Repository/ref may be configured with
`OMNIX_TRADING_PROSPECTIVE_GAP_GITHUB_REPOSITORY` and
`OMNIX_TRADING_PROSPECTIVE_GAP_GITHUB_REF`; remote fallback can be disabled
with `OMNIX_TRADING_PROSPECTIVE_GAP_REMOTE_INBOX=0`. Authentication remains
owned by the installed GitHub CLI.

## Machine-readable climatology

`resources/trading/prospective_gap_state/climatology.json` carries the confirmed prospective baseline between sessions using `prospective-gap-climatology-state-v1`.

Post-close automation advances this state only from FINAL, causally valid, scorable `close_above_open_v1` outcomes. Premarket automation must use the newest state rather than copying an older morning baseline. The lightweight scheduler handoff also carries `baseline_through_session` plus the counts. Authority is chosen by through-session recency: a newer handoff checkpoint may supersede a stale local checkout, a newer local state supersedes an older handoff, and equal-date count conflicts fail closed.
