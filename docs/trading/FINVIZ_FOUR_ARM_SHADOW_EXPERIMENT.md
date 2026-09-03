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

All due symbols are batched into one model call per completed minute. The model
must return one strict action per symbol:

- `enter`
- `hold`
- `add`
- `reduce`
- `exit`
- `skip`

The previous AI decision, previous feature snapshot, current normalized SHADOW
position, deterministic V2 state, intraday-learning state, 1m/5m indicators,
VWAP, recent 20 finalized 1m bars, volume, spread, halt state and execution
eligibility are supplied as causal context.

### D — event-driven AI hybrid

The same stateful AI policy is called only when deterministic evidence changes
materially. Current triggers include:

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

## Stateful normalized position

The experiment uses a normalized long-only position so the AI can be evaluated
without money authority:

- enter: 1.0 unit;
- add: +0.5 unit;
- maximum: 1.5 units;
- reduce: -0.5 unit;
- exit: all remaining units.

The model proposes the action. Deterministic code owns the transition and may
veto new exposure if current execution evidence is unsafe.

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
- decision count;
- action-change count;
- decision-stability score;
- allocated LLM token usage.

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
churn, spread/slippage drag, MFE capture, hold time, decision stability and LLM
cost. The primary question is whether the AI policies add durable
execution-adjusted edge beyond the deterministic baselines.
