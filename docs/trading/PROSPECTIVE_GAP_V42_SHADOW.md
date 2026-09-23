# Prospective Gap v4.2 Shadow Challenger

Status: **forward shadow active for sessions beginning 2026-09-23**.

## Scientific boundary

`prospective-gap-v4.2-shadow` is a new challenger. It does not mutate:

- `prospective-gap-v3`;
- `prospective-gap-v4-shadow`;
- the already preregistered `prospective-gap-v4.1-shadow`.

September 15, 16, 17, 18, 21, and 22 are **design evidence** for v4.2 and are excluded from its forward-validation sample. The first eligible forward session is **2026-09-23**.

No v4.2 promotion review is allowed before at least:

- 10 forward sessions; and
- 100 forward observations.

## Why v4.2 exists

The September 22 run exposed a recurring distinction:

> a strong catalyst can justify the premarket gap without implying that meaningful upside remains after the 09:30 open.

v4.2 therefore models **incremental continuation after premarket repricing**, rather than treating catalyst quality as a proxy for post-open continuation.

The model is deliberately transparent, deterministic, and shadow-only.

## Complete-demand evidence gate

v4.2 will not produce a forecast from candidate-level proxies alone.

The runtime requires canonical RAW 1-minute premarket evidence with:

- a verified extended-hours provider window;
- no unresolved provider failure;
- at least 12 real premarket bars;
- at least 3 real bars in the final 15 minutes;
- latest finalized premarket bar no more than 300 seconds old at freeze;
- all required demand features present:
  - distance from premarket VWAP;
  - position in premarket range;
  - float turnover;
  - late premarket acceleration;
  - late premarket volume share.

A quiet premarket minute is **not** automatically a data gap. Extended-hours recovery uses sparse-event semantics because trade-bar providers may omit minutes with no trades.

If the complete-demand contract is not satisfied, v4.2 records `NOT_APPLICABLE`; it never neutral-imputes the missing demand state.

## Mechanism heads

v4.2 separates these mechanism heads:

- `fundamental_reprice_score`
- `theme_squeeze_score`
- `low_information_technical_score`
- `continuation_demand_score`
- `remaining_upside_score`
- `opening_exhaustion_score`
- `supply_fade_score`

### Remaining upside

`remaining_upside_score` is explicitly different from catalyst strength.

It is high only when causal premarket demand remains strong after discounting measured opening-exhaustion risk. A high-quality catalyst with a fully saturated premarket repricing can therefore have high fundamental-reprice score but low remaining-upside score.

## Risk interactions

v4.2 introduces explicit nonlinear interaction penalties:

- `extension_x_supply`
- `extension_x_low_liquidity`
- `extension_x_weak_finality`

This prevents severe combinations such as `HIGH_EXTENSION + SUPPLY_OVERHANG + LOW_LIQUIDITY + weak catalyst finality` from being represented as several small independent penalties.

The interaction definitions and weights are frozen in `V42ModelSpec` before the first eligible forward session.

## Return distribution

Every PRODUCED v4.2 forecast contains a deterministic economic distribution:

- q10;
- q50;
- q90;
- expected return;
- expected shortfall at the 10% tail;
- P(return > +2%);
- P(return < -5%);
- expected MAE;
- expected MFE.

These outputs are shadow research forecasts. They do not authorize Portfolio E or live/paper execution.

## Evaluation

The daily scorecard evaluates v4.2 on two independent surfaces.

### Direction/calibration

- accuracy;
- Brier score;
- log loss;
- bullish precision/recall;
- frozen-climatology Brier skill;
- matched v4.2-minus-v3 Brier/log-loss/accuracy deltas.

A v4.2 forecast is compared with v3 only on the same matched symbol/session outcome.

### Economic distribution

- expected-return MAE;
- q10/q50/q90 pinball loss;
- Brier for P(return > +2%);
- Brier for P(return < -5%);
- q10 breach rate;
- mean predicted return vs mean realized return.

Directional accuracy alone is not a promotion criterion.

## Scheduler handoff

The scheduled premarket research task must persist a machine-readable request at:

`resources/trading/prospective_gap_inbox/YYYY-MM-DD.json`

The preferred file contract is `SchedulerPremarketHandoff`
(`prospective-gap-scheduler-handoff-v1`), not a scheduler-authored
`PremarketFreezeRequest`. The simplified handoff carries only research facts;
Omnix constructs internal candidate/forecast/calibrator objects and performs
live Yahoo one-minute recovery itself.

The monitor ingests the handoff only during **09:26–09:29 ET**. v3/v4 retain
the scheduler's original research freeze; v4.2 alone receives a separate late
premarket state stamped at the actual ingestion time, not at a future cutoff.
This gives v4.2 a fresh demand window while leaving the older paired experiment
causally unchanged. Missing
scheduler-side RAW one-minute bars are therefore not grounds to omit the
handoff. Missing optional facts remain missing, and post-cutoff ingestion fails
closed.

The official baseline is also runtime-owned. The migration anchor through
2026-09-22 is N=40 / 17 positives / q=42.5%; later FINAL prior-session outcomes
advance it. The handoff includes a required prior-FINAL climatology checkpoint
so a day with no runtime session can still advance the next baseline. Omnix
rejects checkpoints that are stale relative to, or conflict with, runtime-known
history. The scheduler must not reuse an older morning baseline.

Once ingested, the durable `StrategyEvent` ledger becomes authority. The
Markdown journal remains a projection/report. Malformed or late payloads fail
closed and increment the scheduler-handoff error counter.

Runtime health is visible in strategy operations under:

- `scheduler_handoff_ingest_count`
- `scheduler_handoff_error_count`
- `no_session_count`

## Promotion boundary

v4.2 remains a shadow challenger until forward evidence supports promotion. No single session, ticker, or post-hoc slice can change the frozen v4.2 coefficients or interaction definitions.

Any predictive change motivated by outcomes observed after v4.2 activation requires a new explicitly versioned challenger.


## Post-open action experiment: Portfolio F

v4.2 premarket output is a **watch/reject forecast**, not an opening-print buy instruction.

The independent action policy `prospective-gap-v4.2-action-v1` uses finalized regular-session one-minute evidence and leaves the frozen premarket forecast unchanged.

Timing is frozen before the first forward action session:

- **09:30–09:35 ET:** observe only; no Portfolio F entry.
- **09:35–09:40 ET:** early confirmation is allowed only at the stricter early threshold.
- **09:40–09:45 ET:** primary decision window.
- **09:45–10:00 ET:** secondary window with a stronger confirmation requirement and declining timing quality.
- **10:00 ET:** the original premarket thesis expires. Any later trade requires a separately versioned intraday setup.

### Premarket watch classes

Every PRODUCED v4.2 forecast is classified independently as:

- `REJECT`
- `WATCH`
- `HIGH_PRIORITY_WATCH`

The classifier considers direction probability, expected return, and downside-tail probability. A `REJECT` never becomes a Portfolio F long from the original premarket thesis.

### Confirmation evidence

The post-open evaluator measures:

- higher-low structure;
- session VWAP hold/reclaim;
- break of the recent pullback high;
- opening-range support;
- current-vs-recent volume ratio;
- five-minute and ten-minute demand trajectory.

A structural failure below both the opening range and VWAP invalidates the original watch.

Confirmation strength is stored separately from authorization. A structurally confirmed stock may still be `NO_TRADE` if economics are poor.

### Remaining upside from the actual decision price

The premarket q10/q50/q90 and expected-return distribution is defined from the opening price.

At each decision time, Portfolio F converts those targets into the return still available from the **current executable reference price**. Therefore a stock that already made most of its predicted move can have strong confirmation but poor remaining expected return.

This avoids the error of treating greater certainty late in the move as greater trade value.

### Trade quality

Portfolio F freezes:

`trade_quality = confirmation_strength × remaining_upside_quality × execution_quality × timing_quality`

Execution quality uses the causal bid/ask spread plus configured slippage, impact, and commission assumptions. Late confirmation receives an explicit timing penalty.

Capital requires all of:

- structurally confirmed post-open setup;
- trade-quality threshold;
- positive minimum net expected return;
- acceptable net q10;
- acceptable premarket downside-tail probability;
- usable causal execution observation.

Missing execution economics fail closed.

### Portfolio F

`prospective-gap-portfolio-f-v1` is separate from legacy A/B/C/D and existing Portfolio E.

Default research limits are:

- $1,000 independent starting equity;
- maximum 3 positions;
- maximum 20% equity per position;
- unused equity remains cash.

Portfolio F is shadow-only. Its results cannot rewrite v3, v4, v4.1, v4.2, or Portfolio E.
