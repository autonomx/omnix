# Historical trading replay reliability contract

Historical strategy research must distinguish **market evidence** from **provider failure**. A benchmark that touched every session can still be unusable when many symbol/session observations failed to load.

This contract applies to deterministic SHADOW replays, including the historical Top-5 winner diagnostic and Leader Momentum winner/control experiments.

## Cache first

For large repeated experiments, populate/reuse the historical dataset cache before evaluating strategies. The same symbol/session tape should not be re-fetched independently for each arm.

Caching is the preferred path. The provider runtime described below is a fallback for uncached/missing entries, not a substitute for a reproducible cache.

## Provider failures are not market-data facts

Use `src/app/trading/strategy_replay_reliability.py` to preserve these distinctions:

- `provider_rate_limited` — transient/provider throttling; never interpret as a stock having no bars.
- `provider_unavailable` — transport or provider-side availability failure.
- `bars_unavailable` — the provider request succeeded but the required bar tape was genuinely unavailable/empty.
- `data_gap` — bars exist but strategy-required continuity is absent. This may include legitimate exchange halts and must be reviewed separately.
- `metadata_unavailable` — replay-required candidate/context metadata is absent.
- `provider_contract_error` — provider payload/adapter contract failure.
- `provider_cancelled` — cancelled research request.
- `unknown_failure` — unclassified failure; fail closed.
- `evaluated` — the strategy actually had the required observation and produced an evaluable result.

Legacy CSV rows can be normalized with `replay_observation_from_result(...)`. Provider exceptions can be normalized with `classify_provider_failure(...)`.

## Historical provider profile

When historical Alpaca research cannot use cached bars, use `historical_replay_http_runtime(...)` or a caller-supplied runtime with equivalent-or-stronger semantics.

The research profile intentionally uses:

- maximum concurrency: **2**
- maximum attempts: **6**
- initial exponential backoff: **1 second**
- existing shared `ProviderHttpRuntime` semantics for numeric `Retry-After`, HTTP 429, retryable 5xx, transport failures, and cancellation.

This profile is deliberately slower than latency-sensitive live paths.

## Observation-level completeness

A benchmark must define the expected observation key set before interpreting results. For the 21-session Top-5 winner benchmark this is the 105 `(session_date, instrument_id)` pairs.

For each requested arm:

```python
from app.trading.strategy_replay_reliability import (
    ReplayExpectedObservation,
    assess_replay_completeness,
    replay_observation_from_result,
    require_replay_valid_for_inference,
)

report = assess_replay_completeness(
    observations,
    expected_observations,
    arms=(
        "leader-momentum-continuation",
        "stoch-trend-capture",
    ),
)
require_replay_valid_for_inference(report)
```

The strict default policy requires **100% evaluated expected observations** and rejects:

- missing expected rows;
- duplicate authoritative rows;
- unexpected rows;
- provider throttling/unavailability;
- provider contract/cancellation/unknown failures;
- bars unavailable;
- data gaps;
- metadata unavailable.

Research that intentionally accepts a known class of genuine exchange/data absence must construct an explicit `ReplayCompletenessPolicy` override and preserve the resulting report with the artifacts. Provider failures remain blocking.

## Reporting requirements

Do not publish a replay as evidence for strategy comparison merely because the provider touched every session.

At minimum preserve per arm:

- expected observation count;
- recorded observation count;
- evaluated observation count and fraction;
- missing/duplicate/unexpected counts;
- provider-rate-limit and provider-unavailable counts;
- genuine bars-unavailable count;
- data-gap count;
- metadata-unavailable count;
- sessions with any record;
- **fully evaluable sessions**;
- `valid_for_strategy_inference` and reason codes.

If `valid_for_strategy_inference == false`, P/L may be retained as a debugging artifact but must be labeled **incomplete / not valid for strategy inference**. It must not replace the last complete benchmark.

## Strategy isolation

Replay reliability infrastructure must not alter:

- strategy thresholds;
- setup state machines;
- qualification logic;
- risk sizing;
- exits;
- execution authority.

For Leader Momentum v1.1 specifically, the frozen strategy remains the benchmark authority. Reliability changes affect only data acquisition, failure classification, and whether a run is eligible to support research conclusions.
