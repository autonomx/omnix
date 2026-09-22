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

The file must validate as `PremarketFreezeRequest`.

The prospective runtime monitor checks this inbox idempotently before concluding that no session exists. Once ingested, the durable `StrategyEvent` ledger becomes authority. The Markdown journal remains a projection/report.

Malformed or incomplete inbox payloads fail closed and increment the scheduler-handoff error counter.

Runtime health is visible in strategy operations under:

- `scheduler_handoff_ingest_count`
- `scheduler_handoff_error_count`
- `no_session_count`

## Promotion boundary

v4.2 remains a shadow challenger until forward evidence supports promotion. No single session, ticker, or post-hoc slice can change the frozen v4.2 coefficients or interaction definitions.

Any predictive change motivated by outcomes observed after v4.2 activation requires a new explicitly versioned challenger.
