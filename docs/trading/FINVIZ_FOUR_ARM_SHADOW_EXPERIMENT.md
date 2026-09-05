# Finviz Top-5 four-arm SHADOW experiment

Status: research-only. No paper-order or live-order authority.

The managed `finviz-learning-v2-shadow` strategy now runs four policies over
the same immutable 09:15 ET Finviz Top-5 cohort.

## Arms

### A — deterministic V2

The existing gap-as-impulse / failed-selloff V2 state machine remains unchanged.
It is the reproducible structural baseline.

### B — 3-minute Stoch trend capture

The existing Stoch RSI 14/14/3/3 SHADOW overlay remains unchanged. It uses
Stoch RSI for entry timing and price/EMA/VWAP structure for trend exits, with
spread/slippage-adjusted SHADOW accounting.

### C — AI every completed 1-minute bar

A stateful LLM policy receives every newly finalized 1-minute market state for
each available Top-5 symbol from 09:35 ET until the configured force-flat
boundary.

This is the **pure-AI arm**: it receives generic causal market structure,
morning-cohort facts, VWAP/session statistics, 1m/5m indicators, recent finalized
1m bars, current normalized SHADOW position and execution evidence. It does
**not** receive the canonical V2 state machine, V2 transitions/reason codes, or
the deterministic intraday-learning pattern/score interpretation.

All due symbols are batched into one model call per completed minute. The model
must return one strict action per symbol:

- `enter`
- `hold`
- `add`
- `reduce`
- `exit`
- `skip`

The previous AI decision, current normalized SHADOW position, morning cohort,
regular-session 1m/5m indicators, VWAP/session statistics, recent 20 finalized
regular-session 1m bars, volume, spread, halt state and execution eligibility
are supplied as causal context. The recent bars use a column schema plus compact
rows to avoid repeating field names on every minute and unnecessarily inflating
token usage.

### D — event-driven AI hybrid

The same stateful AI policy is called only when deterministic evidence changes
materially. Unlike Arm C, this is explicitly the **hybrid arm**: it also receives
the canonical deterministic V2 state/transitions and the intraday-learning
interpretation. Current triggers include:

- initial eligible state;
- deterministic V2 state change;
- intraday-learning pattern change;
- VWAP side change;
- new session high;
- volume spike;
- spread-tier transition;
- execution-eligibility change;
- halt/resume change;
- 1m Stoch RSI entering oversold/overbought;
- EMA9 direction change;
- normalized-position P&L threshold crossings;
- prior AI invalidation price reached.

There is no heartbeat. If nothing material changes, the model is not called and
the previous thesis persists.

Arms C and D are evaluated concurrently from the same causal poll snapshot so
the event-driven model call does not serially delay the every-minute arm. Once a
symbol is flat after its permitted trade, or remains flat after the entry cutoff,
Omnix stops spending LLM calls on that symbol; open positions continue to be
evaluated until exit or force-flat.

## Stateful normalized position

The experiment uses a normalized long-only position so the AI can be evaluated
without money authority:

- enter: 1.0 unit;
- add: +0.5 unit;
- maximum: 1.5 units;
- reduce: -0.5 unit;
- exit: all remaining units.

The model proposes the action. Deterministic code owns the transition and may
veto or normalize impossible/unsafe exposure changes. The common strategy
envelope still applies: new exposure stops after the configured 11:30 ET entry
cutoff, the kill switch blocks new exposure, the one-trade-per-symbol-per-day
rule is honored, max positions and max trades/day are enforced per AI arm, adds
cannot exceed 1.5 normalized units, and impossible model states such as HOLD
while flat are normalized before metrics are recorded. Dollar-risk, max-trade-
value and portfolio-risk percentages are intentionally not claimed by normalized
research units; those wait for cross-arm sizing harmonization.

## Execution accounting

Any entry/add/reduce/exit is simulated through the same
`paper-execution-v2` fill kernel used elsewhere in Omnix.

- buys consume ask + adverse slippage;
- sells consume bid - adverse slippage;
- stale/ineligible/halted observations do not become executable fills;
- new exposure requires a current bid/ask spread at or below the strategy risk
  ceiling;
- normalized research units use the shared fill-price semantics, but they are
  not a claim about dollar-sized liquidity or production partial-fill realism;
- no paper repository order is created.

At the configured force-flat boundary, ordinary AI calls stop. If a normalized
position remains open, deterministic force-flat retries take over.

## Evidence

The monitor persists:

- `ai_shadow_batch`: one model-call record with provider/model/token usage;
- `ai_shadow_decision`: strict stateful decision, feature snapshot, prior
  action and trigger reasons;
- `ai_shadow_fill`: execution-cost simulation and before/after normalized
  position;
- `ai_shadow_trade`: closed-trade outcome;
- `ai_shadow_session_summary`: per-policy daily summary.

Closed AI trades report:

- reference return;
- net execution-adjusted return;
- execution drag;
- MFE and MAE;
- hold time;
- fill count;
- trade decision count;
- action-change count;
- decision-stability score;
- allocated LLM token usage.

Session/comparison evidence additionally records all policy decisions (including
flat/no-trade symbols), all model calls and tokens, LLM batch failures, and
market-context gap events. Missing data is therefore explicit evidence rather
than a silently smaller sample.

The Trading Strategies UI shows both AI arms next to the deterministic/Stoch
evidence for each Top-5 candidate.

## Safety boundary

Both AI arms are hard SHADOW experiments.

The AI does not choose account risk, shares, cash allocation, broker route or
order type. It cannot create a paper order, protection or AUTO PAPER
qualification. Every AI record includes `execution_authority=false`.

Environment controls:

- `OMNIX_TRADING_AI_SHADOW_MONITOR=0` disables the experiment.
- `OMNIX_TRADING_AI_SHADOW_INTERVAL_SECONDS=15` changes monitor polling.
- legacy-test mode remains disabled unless
  `OMNIX_TRADING_AI_SHADOW_MONITOR_IN_TESTS=1`.

## Comparison goal

Do not optimize from a handful of sessions. Accumulate prospective evidence and
compare A/B/C/D on execution-adjusted outcomes, drawdown/adverse excursion,
churn, spread/slippage drag, MFE capture, hold time, decision stability, data
completeness and LLM cost. Arm A also surfaces its live V2 SHADOW entry spread
and execution eligibility. Its post-close canonical V2 result remains measured
in R with the replay's assumed spread, while B/C/D use point-in-time bid/ask
execution accounting; the comparison explicitly marks both return units and
execution-cost models as not yet harmonized. Do not rank the four arms until a
common risk-normalized return basis is added. The primary question is whether
the AI policies add durable execution-adjusted edge beyond the deterministic
baselines.
