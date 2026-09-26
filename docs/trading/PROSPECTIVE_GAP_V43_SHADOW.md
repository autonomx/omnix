# Prospective Gap v4.3 Shadow Challenger

Status: **forward shadow active for sessions beginning 2026-09-28**.

## Scientific boundary

`prospective-gap-v4.3-shadow` is a new forward-only challenger. It does not mutate:

- `prospective-gap-v3`;
- `prospective-gap-v4-shadow`;
- `prospective-gap-v4.1-shadow`;
- `prospective-gap-v4.2-shadow`;
- `prospective-gap-v4.2-action-v1`;
- Portfolio E or Portfolio F.

All observations through **2026-09-25** are design evidence only for v4.3. They are excluded from v4.3 forward validation.

The first eligible forward session is **2026-09-28**. No promotion review is allowed before at least:

- 10 forward sessions; and
- 100 forward observations.

## Why v4.3 exists

The September 25 retrospective replay reinforced a distinction already visible in earlier sessions:

> a strong catalyst and a large premarket move can coexist with very little remaining post-open upside.

The proxy Top-10 cohort on September 25 was strongly mean-reverting after the open. That observation is **not** admitted as prospective validation and does not alter v3 or v4.2. Instead it motivates a separately versioned hypothesis:

1. premarket extension saturation should be modeled from multiple raw components rather than one coarse score;
2. continuation probability should depend on remaining demand, not catalyst quality alone;
3. board-wide extension can represent a cohort-level gap-and-fade regime;
4. a probability should not become an action merely because it is above 50%;
5. unused research equity should remain cash when edge or confirmation is weak.

## v4.3 premarket extension/exhaustion overlay

v4.3 consumes the already-causal v4.2 forecast and canonical premarket state. It does **not** replace the v4.2 complete-demand gate.

The new extension overlay preserves the raw components used to estimate saturation:

- gap from the normalized prior close;
- distance above premarket VWAP;
- distance from the premarket low;
- position in the premarket range;
- prior 1-day / 3-day extension;
- float turnover;
- late-premarket acceleration/deceleration;
- late-premarket volume share.

It freezes separate outputs:

- `composite_exhaustion_score`;
- `demand_resilience_score`;
- `premarket_repricing_complete_score`;
- exact used/missing components;
- an immutable input fingerprint.

Missing observations are never silently replaced with zero.

## Cohort-level regime

v4.3 freezes one cross-sectional regime for the available v4.2 cohort:

- `NORMAL`
- `CAUTIOUS`
- `HIGH_EXHAUSTION`
- `INSUFFICIENT`

The regime uses only pre-open information and considers:

- median cohort gap;
- fraction of names with gap >= 50%;
- fraction with high opening-exhaustion state;
- fraction dominated by low-information/technical momentum;
- mean remaining-upside score.

The regime does not overwrite an instrument probability. It is a separately persisted input to the v4.3 overlay and later action policy.

## Forecast overlay

v4.3 starts from the frozen v4.2 probability and adds only preregistered deltas for:

- remaining upside;
- demand resilience;
- richer extension/exhaustion;
- premarket repricing completeness;
- cohort regime.

The v4.2 probability remains preserved as `base_v42_probability` and is bound by immutable fingerprint.

v4.3 also freezes:

- expected return;
- frozen climatology probability;
- probability edge over climatology;
- uncertainty;
- cohort regime;
- extension overlay.

The historical climatology is an action reference, not a tuning target. The model probability continues to be scored unconditionally.

## v4.3 action policy

The action layer is `prospective-gap-v4.3-action-v1`.

It consumes the causal `prospective-gap-v4.2-action-v1` snapshot instead of loading a second post-open tape. This keeps the two action experiments comparable and avoids duplicate market-data interpretation.

### Premarket action gate

A long candidate must have:

- direction probability at or above the frozen action floor;
- probability edge over the pre-open climatology;
- sufficient remaining-upside score;
- acceptable repricing-complete score;
- acceptable extension/exhaustion;
- positive expected return.

A forecast can therefore remain scientifically scoreable while being rejected for action.

### Post-open confirmation

v4.3 preserves the v4.2 timing windows but raises the action bar:

- v4.2 structure confirmation is required;
- **higher low is mandatory** for v4.3;
- VWAP hold/reclaim and pullback-high break remain inherited from the v4.2 structure snapshot;
- required confirmation strength increases in `CAUTIOUS` and `HIGH_EXHAUSTION` regimes.

This specifically tests whether waiting for a failed opening sell-off filters premarket names whose move was already exhausted.

## Portfolio G

`prospective-gap-portfolio-g-v1` is an independent $1,000 shadow portfolio.

It keeps:

- maximum 3 positions;
- maximum 20% base equity per position;
- unused capital in cash.

Unlike Portfolio F, the actual authorized size is reduced by:

1. cohort-regime multiplier; and
2. realized trade-quality multiplier.

Defaults:

- NORMAL regime: up to 100% of the per-position cap;
- CAUTIOUS: up to 60%;
- HIGH_EXHAUSTION: up to 35%.

A trade must also pass:

- minimum probability edge over climatology;
- minimum decision-price remaining-upside quality;
- regime-adjusted trade-quality threshold;
- minimum net expected return;
- acceptable net q10;
- available execution economics.

Portfolio G can therefore remain mostly or entirely cash on a stretched morning.

## Persistence

The StrategyEvent ledger persists independent v4.3 records:

- `v43_shadow_spec`
- `v43_action_spec`
- `v43_attempt`
- `v43_cohort_regime`
- `v43_forecast`
- `v43_watch`
- `v43_action`
- `v43_authorization`
- `portfolio_g`
- `portfolio_g_score`

The Markdown activity log remains a projection. Machine-readable ledger records remain authority.

## Post-close evaluation

Every PRODUCED v4.3 probability is scored unconditionally.

The daily scorecard reports:

- v4.3 Brier;
- v4.3 log loss / accuracy through the standard binary metric contract;
- matched v4.3-minus-v3 comparison;
- Portfolio G cost-adjusted return;
- action/authorization counts.

The intended research comparison is:

- v3: unchanged champion scientific baseline;
- v4.2: premarket remaining-upside challenger;
- Portfolio F: v4.2 timed confirmation;
- v4.3: richer exhaustion + cohort regime challenger;
- Portfolio G: v4.3 stricter confirmation + dynamic cash sizing.

## Promotion boundary

No single day, symbol, or retrospective replay can promote v4.3.

Promotion requires prospective evidence after 2026-09-28, adequate sample size, calibration quality, tail behavior, economic expectancy, and action coverage. Any later change to the v4.3 predictive definition requires another explicitly versioned challenger.
