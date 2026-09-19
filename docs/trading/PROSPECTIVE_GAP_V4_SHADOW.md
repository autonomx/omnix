# Prospective Gap v4 Shadow Challenger

Status: **frozen shadow-challenger architecture / forward validation begins with sessions after 2026-09-17**

Champion remains: `prospective-gap-v3`.

Challenger: `prospective-gap-v4-shadow`.

The September 15–17 prospective sessions are design evidence for v4. They must not be counted as forward-validation evidence for v4. Once this architecture is merged, later changes to the v4 predictive definition require a new versioned challenger (for example v4.1 or v5).

## Core invariants

### Canonical truth is not live knowledge

Recovered market data may repair the canonical historical tape, data-quality reports, and later training/replay datasets. It may never rewrite what a prior live forecast is deemed to have known.

Every market-state feature carries event/observation/ingestion/recovery provenance and an explicit `available_to_live_forecaster` bit. The 09:29 forecast may fingerprint only the live-eligible subset.

### Forecast authority is not action authority or execution authority

```text
09:29 immutable forecast
        ↓ independently scored
post-open confirmation/actionability
        ↓ independently scored
notional-aware execution economics
        ↓
paper trade authorization
```

A `DEGRADED` forecast remains a forecast and is still scored. `ACT/WATCH/ABSTAIN` cannot selectively remove probabilities from Brier/log-loss/calibration. `INSUFFICIENT` is reserved for cases where the specified v4 feature contract cannot produce a defined forecast.

## Implemented contracts

Implementation lives in `src/app/trading/prospective_prediction_v4.py`.

### Frozen cohort identity

`FinvizFrozenCohort` stores:

- cohort ID;
- discovery cutoff;
- frozen time;
- immutable symbol list;
- cohort fingerprint.

The cohort fingerprint propagates into v4 forecasts and paired v3/v4 observations.

### Causal premarket market-state snapshot

`build_premarket_market_state` derives features only from finalized RAW one-minute premarket bars that:

- belong to one instrument;
- use one provider;
- have event windows before the prediction cutoff;
- have actually been received before the cutoff for live use;
- are revision-resolved before feature derivation.

The first v4 market-state contract derives:

- gap from prior close;
- premarket move since first catalyst;
- distance from premarket VWAP;
- distance from premarket low;
- premarket range position;
- prior one-day return;
- prior three-day return;
- float turnover;
- late-premarket acceleration;
- late-premarket volume share.

Bars that occurred before cutoff but arrived after cutoff remain visible only through recovery diagnostics. They do not enter the live feature fingerprint.

### Per-feature provenance and evidence quality

`PremarketFeature` records:

- value/unit;
- event time;
- observed time;
- ingested time;
- recovered time;
- source;
- freshness;
- quality;
- availability;
- live-forecast eligibility;
- provenance fingerprint.

`PredictionEvidenceQuality` summarizes critical-feature state as:

- `COMPLETE`;
- `DEGRADED`;
- `INSUFFICIENT`.

Evidence quality is separate from `V4ForecastAttempt.model_state`:

- `PRODUCED`;
- `FAILED`;
- `NOT_APPLICABLE`.

This distinguishes a model crash from insufficient evidence.

### Catalyst decomposition

`CatalystDecomposition` keeps v4 catalyst inference explicit:

- strength;
- finality;
- freshness;
- surprise;
- economic materiality.

These are derived inferences tied to source evidence IDs. They are not raw market observations.

### Extension/exhaustion model

`ExtensionComponents` stores raw observed components. `derive_extension_exhaustion_risk` creates a versioned `extension-exhaustion-risk-v1` score while retaining exactly which components were present or missing.

Missing fields are not silently filled with neutral values.

### Regime tags and mechanism scores

Regime tags are descriptive at first:

- `FUNDAMENTAL_REPRICE`;
- `SQUEEZE_MOMENTUM`;
- `STALE_MULTI_DAY`;
- `DISTRESS_SPECULATION`;
- `UNEXPLAINED_TECHNICAL`;
- `SUPPLY_OVERHANG`;
- `LOW_LIQUIDITY`;
- `HIGH_EXTENSION`.

Mechanism heads remain diagnostic scores, not calibrated probabilities:

- continuation score;
- opening-exhaustion score;
- squeeze-tail score;
- fade-risk score.

Future calibrated mechanism probabilities require separately frozen, falsifiable outcome labels.

### Initial v4 shadow score

The first v4 model is deliberately transparent and frozen rather than statistically fit to September 15–17.

`V4ModelSpec` exposes the intercept and every coefficient. `score_v4_raw_probability` combines catalyst decomposition, continuation, extension/exhaustion, fade risk, and squeeze-tail score into a bounded raw probability.

This is a shadow model only. Its coefficients must not be retuned against September 15–17 after merge.

### Calibration artifact

`CalibratorArtifact` is immutable and records:

- calibrator ID/version;
- method;
- training cutoff;
- training population fingerprint;
- exact training dataset fingerprint;
- sample count;
- population definition;
- feature-schema version;
- target-label version;
- parent calibrator;
- creation time;
- calibration-code version;
- calibration parameters.

The raw model output is preserved forever. The calibrated probability is a separate field.

The calibrator training cutoff must precede the forecast session.

**Initial forward-validation policy:** use an immutable `identity` calibrator for v4 until a separately pre-registered calibration dataset/method has enough prior prospective observations to justify a non-identity artifact. September 15–17 must not be used to fit a v4 calibrator because those sessions informed the challenger design. A future non-identity calibrator requires its own frozen artifact before the session it first scores.

### FrozenForecastV4

V4 uses a schema separate from v3 rather than expanding v3 with nullable challenger fields.

It stores:

- instrument/session/cohort identity;
- evidence and market-state snapshot identities;
- model-spec fingerprint;
- feature-vector fingerprint;
- raw probability;
- calibrated probability;
- gross return q10/q50/q90 when available;
- tail probabilities when available;
- MAE/MFE buckets;
- uncertainty;
- evidence quality;
- diagnostic mechanism scores;
- regime tags;
- calibrator identity/fingerprint.

`prospective-gap-v3` remains unchanged.

## Formal paired champion/challenger scoring

`prospective_prediction_scoring.bind_formal_v3_v4_pair` requires:

- one formally valid causal evidence snapshot;
- the v3 forecast to reference that exact snapshot;
- the v4 forecast to reference that exact snapshot;
- both forecasts to have been frozen by the snapshot cutoff;
- v4 session identity to match the evidence session.

Paired evaluation records per matched session/symbol:

- delta Brier (v4 minus v3);
- delta log loss;
- delta absolute probability error;
- standalone v3/v4 Brier.

Negative delta favors v4.

Promotion should primarily use paired evidence because both predictors face the same symbol/day difficulty.

## Post-open confirmation state machine

The v4 trading layer is event-driven rather than waiting for an arbitrary fixed clock time.

States:

```text
WAIT_OPEN
  ↓
OBSERVE_INITIAL_STRUCTURE
  ↓
OBSERVE_PULLBACK
  ├── CONFIRMED_LONG
  ├── INVALIDATED
  ├── WATCH
  ├── SUSPENDED_DATA_QUALITY
  └── EXPIRED
```

Every transition produces an immutable `ConfirmationTransitionReceipt` carrying:

- transition time;
- previous/new state;
- trigger;
- bar/evidence IDs;
- latest finalized bar time;
- reasons.

`CONFIRMED_LONG` requires finalized-bar evidence. Partial candles cannot authorize a setup whose definition requires finalized bars.

`SUSPENDED_DATA_QUALITY` is non-terminal. A temporary provider/data gap can suspend action authority and later return to observation when current data becomes qualified again.

## Actionability

`ActionabilityDecision` is separate from the forecast:

- `ACT`;
- `WATCH`;
- `ABSTAIN`.

Selective metrics report coverage independently from selective accuracy and bullish precision. Abstention does not remove the underlying forecast from unconditional probability scoring.

## Execution-cost transform

Gross alpha and execution economics are separate.

```text
GrossReturnDistribution
        ↓
ExecutionCostInput(notional, bid/ask, slippage, impact)
        ↓
NetReturnDistribution
```

The initial execution transform records:

- notional;
- reference price;
- observed bid/ask;
- spread bps;
- estimated slippage bps;
- estimated impact bps;
- gross/net return distribution.

`TradeAuthorizationReceipt` freezes the economics that were believed at decision time. A later cost model must not rewrite an old authorization.

A confirmed setup can still become `NO_TRADE` if expected net alpha is non-positive.

## Scoring layers

### Forecast quality — every valid forecast

- Brier;
- log loss;
- calibration;
- absolute probability error;
- paired v3/v4 deltas;
- return-distribution calibration as sufficient data accumulates.

### Selective/action quality

- action coverage;
- selective accuracy;
- bullish precision;
- reason/state attribution.

### Economic quality

- gross return;
- estimated net return;
- portfolio expectancy;
- drawdown;
- severe downside contribution;
- maximum notional with positive expected net alpha once the impact model can support that calculation.

## Promotion protocol

V4 remains a shadow challenger until prospectively promoted.

Pre-registered primary criterion:

- paired improvement in Brier versus v3.

Guardrails:

- no material paired log-loss deterioration;
- calibration not worse;
- no deterioration in severe-downside/tail forecasts;
- sufficient independent sessions, not merely symbol count.

Trading-layer criteria:

- positive net expectancy after causal cost evidence;
- acceptable drawdown/tail loss;
- minimum action coverage.

Robustness:

- improvement must not be entirely dependent on one symbol or one narrow regime tag;
- individual regime slices are diagnostic until their sample sizes are meaningful.

September 15–17 are excluded from promotion evidence for v4 because they informed the design.

## Implementation phases

### Phase 1A — market-data capture authority

Implemented in the v4 snapshot contract/build path:

- single-provider RAW premarket series;
- finalization checks;
- duplicate/revision resolution;
- event/receipt cutoff semantics;
- post-cutoff recovery exclusion from live knowledge;
- explicit recovery diagnostics.

The broader shared provider-recovery layer remains the canonical place for cross-strategy gap recovery. V4 consumes qualified canonical data; it does not create strategy-specific repair authority.

### Phase 1B — market-state feature derivation

Implemented for the first v4 feature set.

### Phase 2 — feature/catalyst/extension contracts and mechanism scores

Implemented.

### Phase 3 — immutable calibrator + FrozenForecastV4

Implemented.

### Phase 4 — paired v3/v4 forward-validation framework

Implemented at contract/evaluation level and wired into the formal scoring boundary.

### Phase 5 — event-driven post-open confirmation

Implemented as a deterministic, receipt-producing state machine.

### Phase 6 — versioned notional-aware execution costs and authorization

Implemented as a pure gross-to-net transform plus immutable authorization receipt.

## Required operational integration

The scheduled premarket workflow should run both predictors from the same frozen Finviz cohort/evidence snapshot:

```text
v3 champion ───────────────┐
                          ├── same session/symbol outcome
v4 shadow challenger ─────┘
```

The journal should persist both outputs, the v4 evidence-quality summary, calibrator/model fingerprints, and later the paired deltas.

No v4 output has live-money authority.


## Operational hardening after forward-validation day 1

The September 18 forward-validation session showed that forecast quality and
trading quality must remain separate. V4 modestly improved paired probability
metrics while fully-invested research portfolios still suffered large losses.

The following operational changes are implemented in
`src/app/trading/prospective_prediction_operational.py` without changing v3 or
the frozen v4 scoring coefficients.

### Causal premarket enrichment adapter

`load_operational_premarket_state` now connects the existing
`TradingMarketDataService` directly to the frozen v4 market-state builder.

It:

- requests finalized one-minute bars through the candidate's existing market-data binding;
- derives the canonical v4 premarket feature set when RAW causal bars are available;
- preserves the existing cutoff/receipt-time rules from v4;
- falls back to the point-in-time `GapperCandidate` evidence when the richer tape
  is unavailable;
- marks missing rich features as DEGRADED rather than fabricating neutral values.

The fallback keeps forecasts available for scientific scoring while making their
reduced evidence quality explicit.

### Deterministic post-close outcome integration

`build_operational_formal_outcome` always invokes the existing deterministic
formal outcome code when finalized RAW consolidated-SIP 5-minute bars are
available.

It produces:

- normalized OLS slope;
- cumulative-session VWAP occupancy;
- observed-bar and wall-clock occupancy above open;
- session coverage / gap minutes;
- directional efficiency;
- MAE / MFE;
- closing-range position;
- versioned `close_above_open_v1`, `persistent_uptrend_v1`, and
  `session_regime_v1`.

When direct condition-filtered SIP trades are unavailable, the explicitly
versioned `sip-analysis-prices-raw-5m-fallback-v1` contract may use the first
and last finalized RAW SIP 5-minute session boundaries. The fallback requires
both regular-session boundaries and remains distinguishable from direct SIP
trade authority.

This prevents a recurrence of the September 18 situation where sufficient
5-minute data existed but deterministic derived measurements were left pending.

### Post-open confirmation uses the existing failed-selloff strategy

`evaluate_operational_confirmation` does not invent a second continuation
setup. It maps the existing deterministic `evaluate_gap_pullback` state machine
into the v4 confirmation authority:

- early structure -> `OBSERVE_INITIAL_STRUCTURE`;
- failed-selloff/pullback progression -> `OBSERVE_PULLBACK`;
- existing deterministic `entry_ready` -> `CONFIRMED_LONG / ACT`;
- deterministic rejection -> `INVALIDATED / ABSTAIN`;
- expired setup -> `EXPIRED / ABSTAIN`.

Current-data uncertainty enters the non-terminal
`SUSPENDED_DATA_QUALITY / WATCH` state and can resume when qualified current
data returns. It does not retroactively alter the premarket forecast.

### Cash-preserving net-alpha shadow portfolio

The legacy A/B/C/D portfolios remain unchanged scientific baselines.

A new independent shadow policy,
`confirmation-net-alpha-capped-v1`, consumes only immutable
`TradeAuthorizationReceipt` records.

Default research guardrails are:

- LONG authorization required;
- expected net return after costs must be positive;
- maximum three positions;
- maximum 20% of starting equity per position;
- respect any lower requested notional or `max_positive_alpha_notional`;
- never redistribute unused capital merely to reach 100% invested;
- remaining capital stays cash.

This policy is intentionally downstream of the forecast. A 51% or 64% forecast
does not by itself authorize capital.

### Frozen v4 remains frozen

Forward-validation day 1 highlighted that `opening_exhaustion_score` is stored
as a diagnostic mechanism score while the frozen v4 raw probability formula does
not consume that score directly.

That observation is a **future challenger hypothesis**, not permission to alter
`prospective-gap-v4-shadow`.

If explicit opening-exhaustion weighting is tested, it must be introduced under
a new versioned challenger (for example `prospective-gap-v4.1-shadow`) with a
pre-registered model spec before the first session used to evaluate it. September
18 may motivate the hypothesis but may not be used as forward-validation
evidence for that new coefficient.

## 2026-09-18 operational hardening

The action layer now includes a deterministic finalized-bar evaluator and a single
evaluate_prospective_gap_action_cycle entry point. The frozen 09:29 forecast
remains immutable; post-open confirmation and trade-time economics are separate
authorities.

Execution economics use execution-cost-v2-round-trip. Median return (q50) is no
longer mislabeled as expected return. Authorization requires an explicit
expected-return estimate, applies entry plus expected-exit spread/slippage/impact
semantics, and enforces a downside-tail guardrail.

freeze_cash_preserving_authorized_portfolio adds a new experimental allocator
without changing historical A/B/C/D. It caps each authorized position and leaves
unused risk budget as cash rather than renormalizing eligible names to 100
percent invested.

Formal whole-session outcome scoring now exposes explicit SCORABLE/UNSCORABLE
state. Confirmed halt/no-trade minutes may explain missing wall-clock bars;
unresolved provider gaps may not silently produce persistent_uptrend_v1.
