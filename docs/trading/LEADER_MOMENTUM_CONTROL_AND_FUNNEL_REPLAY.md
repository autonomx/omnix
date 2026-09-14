# Leader Momentum v1.1 — Control Cohort + Ordered Funnel Replay

Status: **research / SHADOW only**  
Frozen policy: `leader-momentum-continuation-v1.1`

This phase follows the 105-winner instrumentation replay. It does not tune the
strategy. It adds two missing pieces needed before v1.2 can be designed:

1. ordered/conditional setup-gate funnels that mirror `_setup_at` short-circuit
   behavior; and
2. a causal negative/control universe built from historical scanner/discovery
   observations rather than hindsight-selected losers.

## 1. Ordered setup funnels

The original `gate_counts` remain useful marginal statistics: every gate is
measured on every candidate window. They must not be interpreted as causal
funnel percentages because later gates are counted even when an earlier gate
would have stopped the frozen evaluator.

Use:

```python
from app.trading.strategy_leader_momentum_funnel_diagnostics import (
    diagnose_leader_momentum_funnel,
)

result = diagnose_leader_momentum_funnel(bars, context=context)
```

`result.base_trace` is the existing instrumentation trace and contains the
unchanged frozen v1.1 strategy snapshot.

`result.gate_funnel` records, for every gate in actual setup order:

- how many attempts reached the gate;
- how many passed;
- how many failed;
- how often it was the first failing gate; and
- the conditional pass rate among attempts that actually reached it.

The setup funnel covers the frozen `_setup_at` path and the immediate proposed
risk gate. It intentionally does not reinterpret later trade-management or
re-entry scheduling as setup geometry.

For Mode A the ordered window path is:

```text
continuity
  -> impulse_pct
  -> pullback_no_new_high
  -> pullback_retrace_min
  -> pullback_retrace_max
  -> pullback_volume_ratio
  -> breakout_close
  -> close_location
  -> breakout_volume_ratio
  -> proposed_risk_pct
```

For Mode B:

```text
continuity
  -> impulse_pct
  -> compression_width_ratio
  -> compression_above_ema20
  -> breakout_close
  -> hod_break
  -> close_location
  -> breakout_volume_ratio
  -> proposed_risk_pct
```

Common pre-window gates are counted once per bar before either mode:

```text
trend_volatility_ready
  -> entry_atr_ready
  -> trend_structure
  -> ema9_extension_pct
  -> ema9_extension_atr
```

Do not remove the existing marginal counts. Report both views:

- marginal failure rate answers "how often is this condition false?";
- ordered conditional failure answers "how often does this condition actually
  stop an otherwise surviving setup path?"

The second quantity should drive v1.2 design.

## 2. Causal control universe

Use the historical scanner observation stream that existed at each causal time.
Do not create a control cohort by selecting stocks that later lost.

Build a plan with:

```python
from app.trading.strategy_leader_momentum_control_replay import (
    build_leader_momentum_control_plan,
)

plan = build_leader_momentum_control_plan(
    session_date=session_date,
    observations=scanner_observations,
    winner_instrument_ids=winner_ids,
    discovery_result=discovery_replay,
    scope="observable_scanner",
)
```

Two scopes are supported:

### `observable_scanner`

Every symbol present in the captured causal scanner observation population.
This is the broad control universe and includes candidates that never passed
Omnix dynamic discovery.

### `discovered_candidates`

Only symbols that actually entered the dynamic-discovery state. This is the
narrower test of strategy selectivity after discovery has already done its job.
It requires the matching `DiscoveryReplayResult`.

For either scope, the causal universe is frozen first. Only then are the known
Top-5 winner IDs removed to create the negative/control set. The plan records a
fingerprint and the exact first/last observation times for reproducibility.

## 3. Run the same frozen strategy on controls

For every control spec:

1. fetch the same Alpaca SIP historical 1-minute bars used for winner replay;
2. construct context using only data available at the same causal time;
3. run `diagnose_leader_momentum_continuation(...)`;
4. optionally run `diagnose_leader_momentum_funnel(...)`;
5. retain traces for non-trades as well as trades.

Attach completed control traces with:

```python
from app.trading.strategy_leader_momentum_control_replay import (
    build_control_cohort_observations,
)

controls = build_control_cohort_observations(plan, traces_by_instrument)
```

Combine those with winner `LeaderMomentumCohortObservation` rows and call
`build_leader_momentum_cohort_report(...)`.

## 4. Required outputs before v1.2

Produce separate reports for `observable_scanner` and `discovered_candidates`.
At minimum compare:

- leader recall among eventual winners;
- control leader-confirmation rate;
- `LEADER_CONFIRMED` precision;
- winner/control trade counts;
- trade precision;
- 1m versus 3m confirmation timing;
- marginal gate failure rates;
- ordered first-failure counts;
- conditional pass rates among reached gates;
- proposed-risk rejection frequency;
- setup timing and P/L with the same execution-cost assumptions.

For any proposed rule change, show both sides. Example:

> Raising the allowed pullback depth captures N additional known winners, but
> also produces M additional confirmations/trades in the causal controls.

A winner-only improvement is not sufficient evidence for v1.2.

## 5. Interpretation boundary

Do not change `MIN_LEADER_SCORE`, pullback depth, compression width, risk limits,
entry volume requirements, exits, or latch semantics in this phase.

The next v1.2 architecture may ultimately separate early 1-minute leadership,
persistent/hysteretic state, 3-minute setup recognition, and execution gates.
Those changes should be selected only after the ordered funnels and causal
controls show which restrictions distinguish winners from false positives.
