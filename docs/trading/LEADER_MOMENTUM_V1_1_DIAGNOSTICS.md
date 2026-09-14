# Leader Momentum v1.1 — Instrumentation-Only Replay

Status: **research / SHADOW only**  
Frozen policy: `leader-momentum-continuation-v1.1`

This phase exists to explain the v1.1 replay before any strategy tuning. The
trading evaluator remains frozen. Diagnostics are produced by
`strategy_leader_momentum_diagnostics.py` after the normal evaluator runs and
have no execution authority.

## Why this phase exists

The 105-winner replay showed one Leader Momentum trade and a negative normalized
return. That result is not enough to decide whether `MIN_LEADER_SCORE = 70`, the
setup geometry, or execution gates are the dominant bottleneck.

The current policy also has two architectural questions that must be measured
before v1.2:

1. Leadership scoring is evaluated from the 3-minute setup loop, whose current
   scan starts at index 9. That creates a substantial early-session timing
   handicap.
2. The v1.1 score mixes market-leadership evidence with immediate execution
   properties such as spread and dollar volume.

This branch instruments those questions without changing their behavior.

## Frozen baseline

`agent/trading-last-month-winners` remains the historical v1.1 baseline. This
branch was created from current `main`, and the v1.1 strategy and focused v1.1
tests were ported byte-for-byte before the diagnostics layer was added.

Do not change any of these policy thresholds during this phase:

- leader score threshold;
- minimum session return;
- impulse / runaway impulse thresholds;
- pullback retracement bounds;
- pullback / breakout volume ratios;
- EMA / ATR extension limits;
- maximum entry risk;
- partial-profit or exit rules;
- leader latch TTL;
- re-entry cooldown.

## Per-symbol diagnostic trace

Call:

```python
from app.trading.strategy_leader_momentum_diagnostics import (
    diagnose_leader_momentum_continuation,
)

trace = diagnose_leader_momentum_continuation(bars, context=context)
```

The trace contains the original v1.1 `strategy_snapshot` plus research-only
instrumentation.

### Leader-score milestones

The trace preserves first, maximum, last, first-confirmed, and last-confirmed
3-minute score breakdowns. Each breakdown decomposes:

- price-strength points;
- trend points;
- HOD points;
- volume points;
- market-leadership subtotal;
- base/context points;
- TOD-RVOL points;
- relative-strength points;
- spread penalty;
- dollar-volume penalty;
- volume-acceleration points;
- context HOD points.

This allows a replay to distinguish, for example, a stock whose market behavior
was leader-like from one whose total score was suppressed by execution-quality
penalties.

### Research-only 1-minute cadence

The trace also records first, maximum, and first-confirmed score observations on
a research-only 1-minute cadence when the source tape is 1-minute data.

This is **not** trading authority and does not change v1.1. It measures how much
of the observed detection latency comes from evaluating leadership inside the
3-minute setup loop. A future v1.2 may use a separate 1-minute leader detector,
but only after the instrumented winner/control benchmarks support that change.

### Leader state history

The trace records:

- first leader confirmation;
- last leader confirmation;
- confirmation refreshes;
- latch expiry;
- observed structural invalidation and recovery;
- bars spent in confirmed-leader state.

Structural invalidation events are diagnostic observations in v1.1; they do not
change the frozen latch behavior.

### Setup diagnostics

For both `controlled_pullback` and `momentum_compression`, diagnostics preserve
the best candidate window and aggregate pass/fail counts across evaluated
windows.

Candidate diagnostics include actual values, thresholds, and distance-to-pass
for the relevant gates, including:

- continuity;
- current trend structure;
- EMA9 extension percent;
- EMA9 extension in ATR;
- impulse percent;
- pullback retracement bounds;
- pullback volume contraction;
- compression width;
- close location;
- breakout volume ratio;
- HOD breakout where applicable;
- proposed entry-risk percent.

The trace also records:

- `first_setup_candidate_at`;
- `first_setup_valid_at`;
- `first_execution_valid_at`;
- leader-confirmation to first-candidate delay;
- leader-confirmation to first-valid-setup delay.

## Winner and control cohorts

Outcome labels are applied only after the strategy trace exists.

Use `LeaderMomentumCohortObservation` with cohort `winner` or `control`, then
aggregate with `build_leader_momentum_cohort_report(...)`.

The report currently exposes:

- winner observations;
- control observations;
- winner/control leader confirmations;
- winner/control trades;
- leader recall on eventual winners;
- leader false-positive rate on controls;
- precision of `LEADER_CONFIRMED`;
- trade precision.

The control cohort should be built from the actual historical causal scanner
universe, not from hindsight-selected losers.

## Required replay sequence

1. Rerun the exact 105 historical top-five winners with diagnostics enabled.
2. Export the diagnostic trace for every symbol, including non-trades.
3. Build the historical causal scanner/control cohort for the same sessions.
4. Run the exact frozen v1.1 policy and diagnostics on that cohort.
5. Compare leader timing, score decomposition, setup-gate failure rates, and
   execution-gate failure rates between winners and controls.
6. Only then design v1.2.

The key v1.2 decision should be based on whether the evidence points to leader
detection latency, score composition, setup geometry, execution gating, or a
combination of those factors. Do not choose a new `MIN_LEADER_SCORE` from the
winner cohort alone.
