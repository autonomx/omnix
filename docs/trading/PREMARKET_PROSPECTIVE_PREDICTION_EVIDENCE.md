# Premarket prospective prediction evidence architecture

Status: **frozen research architecture v1**

This architecture improves measurement, causality, scoring, and scientific learning for the scheduled premarket Top-10 prediction experiment. It deliberately does **not** change `prospective-gap-v3` coefficients, probability thresholds, catalyst weights, RETO-specific interaction penalties, or the current confidence/risk multipliers.

## Authority chain

```text
CAUSALLY AVAILABLE EVIDENCE
        ↓
IMMUTABLE EVIDENCE SNAPSHOT
        provenance + published/effective/observed/ingested/frozen timestamps
        prediction_cutoff_at leakage gate
        ↓
FROZEN FEATURE VECTOR
        feature_schema_version
        ↓
FROZEN FORECAST
        predictor_version
        P(close_above_open)
        P(persistent_uptrend)
        optional return quantiles / MAE-MFE buckets / uncertainty
        ↓
FROZEN RESEARCH PORTFOLIOS
        A equal-weight bullish
        B confidence/risk weight
        C excess-probability weight
        D cash
        ↓
AUTHORITATIVE SAME-SESSION SIP OUTCOME
        price_contract_version
        selected event provenance
        PROVISIONAL → FINAL reconciliation
        ↓
CONTINUOUS OUTCOME MEASUREMENTS
        ↓
VERSIONED LABELS
        close_above_open_v1
        persistent_uptrend_v1
        session_regime_v1 (diagnostic initially)
        ↓
FORECAST / PORTFOLIO EVALUATION
        Brier, log loss, calibration inputs, precision/recall, Brier skill
        ↓
ATTRIBUTION
        ↓
HYPOTHESIS REGISTRY
        ↓
FORWARD VALIDATION
        ↓
SHADOW CHALLENGER
        ↓
PROMOTION
```

The code contracts live in `src/app/trading/prospective_prediction_evidence.py`.

## Causal evidence contract

Every premarket evidence proposition must be attributable to an immutable snapshot. The snapshot carries:

- `published_at` when known;
- `effective_at` when meaningful;
- `observed_at`;
- `ingested_at`;
- `frozen_at`;
- source locator/fingerprint;
- immutable `prediction_cutoff_at`.

The mechanical leakage gate requires every evidence item's `observed_at`, `ingested_at`, and `frozen_at` to be no later than the prediction cutoff. A historical replay is valid only when the exact frozen evidence snapshot can be reconstructed without later information.

## Same-session price authority

`PRICE_CONTRACT_VERSION = sip-analysis-prices-v1`.

The analysis open and close are selected from consolidated SIP regular-session trade events under a versioned eligibility policy:

```text
analysis_open_price_v1
    = first eligible consolidated SIP trade in [09:30:00 ET, 16:00:00 ET)

analysis_close_price_v1
    = last eligible consolidated SIP trade in [09:30:00 ET, 16:00:00 ET)
```

Eligibility explicitly excludes cancellations/corrections, duplicates, out-of-sequence reports, late reports, auctions, special-condition trades, and odd lots by default. LULD-related prints remain eligible by default. Provider-native condition codes must be decoded into the provider-neutral semantic flags before the policy is applied.

The selected event is stored with price, event timestamp, received timestamp, exchange, SIP feed, condition codes, provider event ID/sequence, and policy version. Daily adjusted OHLC is never allowed to override this contract.

Auction open/close values may be stored separately when a provider identifies them reliably, but they are not silently substituted into this analysis contract.

Outcomes may transition from `PROVISIONAL` to `FINAL` after SIP correction reconciliation; the frozen forecast never changes.

## Raw vs adjusted data

Same-session scoring and portfolio P&L use raw prices. Historical context may use separately adjusted series for corporate actions, gap calculations, or long-window indicators. The two series must not be mixed in one return calculation.

## Continuous outcome authority

The raw measurements are the durable truth. Labels are versioned deterministic views.

`OutcomeMeasurementsV1` records:

- analysis open and close;
- open-to-close return;
- normalized OLS slope of regular-session closes;
- cumulative-session VWAP occupancy;
- observed-bar occupancy above the open;
- wall-clock observed occupancy above the open;
- session coverage;
- directional efficiency;
- MAE and MFE from the open;
- closing-range position;
- session high/low;
- observed-bar count;
- halt/gap minutes.

Halted/missing periods are **never interpolated**. Occupancy is therefore exposed in observed/tradable terms and in wall-clock terms. `interpolated_halt_minutes` is fixed at zero.

The existing labels remain stable:

- `close_above_open_v1`: analysis close > analysis open.
- `persistent_uptrend_v1`: close > open, normalized slope > 0, at least 60% of finalized regular-session bars above cumulative session VWAP, and closing-range position >= 60%.

`session_regime_v1` is initially a diagnostic derived view (`PERSISTENT_UP`, `VOLATILE_UP`, `FLAT`, `FADE`, `PERSISTENT_DOWN`). It must not become a primary model-selection target until its thresholds have been frozen independently of the evaluation sessions. If the definition changes later, create `session_regime_v2`; never rewrite v1 labels.

## Forecast evaluation

Direction accuracy is not sufficient. For every valid prospective day, record at least:

- accuracy at 50%;
- Brier score;
- log loss;
- bullish precision;
- bullish recall;
- realized base rate;
- Brier skill relative to the frozen official climatology baseline.

The official climatology benchmark for session `t` is one probability `q_t` estimated only from valid observations available before session `t`. Diagnostic baselines may exist, but there is exactly one official baseline to prevent benchmark shopping.

## Frozen portfolio experiment

The portfolio rules are frozen before the open and are independent $1,000 research portfolios:

### A — Equal-weight bullish (`equal-weight-bullish-v1`)

All names with frozen `P(close > open) > 0.50` receive equal weights. The full $1,000 is distributed among qualifying names. If none qualify, the portfolio stays in cash.

### B — Confidence/risk weight (`confidence-risk-weight-v1`)

Uses the already adopted frozen formula based on probability, catalyst, liquidity, opening-extension risk, supply risk, and squeeze risk. This formula is not tuned from one day's outcome.

### C — Excess-probability weight (`excess-probability-weight-v1`)

For qualifying names:

```text
weight_i ∝ max(P_i - 0.50, 0)
```

This avoids assigning substantial weight merely because a forecast is barely above 50%.

### D — Cash (`cash-v1`)

No positions; 0% gross benchmark.

All four portfolios are frozen before the open and scored against the same analysis-open/analysis-close contract. Historical allocations are never recomputed from outcomes.

## Hypothesis registry

The LLM may generate semantic hypotheses, but it has no authority to invent statistical effect size, significance, or promotion.

Lifecycle:

```text
PROPOSED
  ↓
OBSERVATIONAL
  ↓
FROZEN_CANDIDATE
  ↓
FORWARD_VALIDATION
  ↓
CANDIDATE_FOR_PROMOTION
  ↓
SHADOW_CHALLENGER
  ↓
PROMOTED
```

Once a hypothesis reaches `FROZEN_CANDIDATE`, its feature definition, expected direction, and evaluation criterion stop changing. Statistical evaluation should account for session clustering; same-day symbols are not IID observations.

A candidate should not graduate merely because it has N symbols. Promotion evidence should include distinct discovery sessions, distinct forward-validation sessions, category coverage, a session-clustered uncertainty estimate, direction stability, and forward metric improvement.

## Champion/challenger

Passing a hypothesis gate does not immediately mutate the champion predictor. The change becomes a shadow challenger and runs prospectively against exactly the same evidence snapshots.

Compare champion and challenger on:

- Brier score;
- log loss;
- calibration;
- persistent-uptrend discrimination;
- return-distribution calibration when available;
- portfolio return;
- drawdown;
- execution-adjusted return when causal execution evidence is available.

Historical forecasts are immutable. Running a new predictor against old evidence snapshots is a backtest, not prospective evidence.

## Implementation boundary

Implemented now:

- causal evidence timestamps and cutoff validation;
- immutable evidence/run fingerprints;
- versioned SIP price eligibility/selection contract;
- provisional/final outcome state;
- continuous raw outcome measurements;
- no-halt-interpolation semantics;
- stable existing labels plus diagnostic regime labels;
- A/B/C/D frozen portfolio contracts;
- Brier/log-loss/precision/recall/climatology skill evaluation;
- hypothesis lifecycle and frozen definitions;
- champion/challenger comparison contract.

Not changed by this architecture:

- `prospective-gap-v3` predictive coefficients;
- current catalyst weights;
- current probability threshold;
- RETO/MEDS/SNYR/WAFU-specific penalties;
- current B portfolio multipliers;
- execution authority.

A bad day therefore becomes scientific evidence without automatically becoming tomorrow's strategy.
