# ADR-0005 — Trading Hermes research causality and authority

**Status:** Accepted for PR #1494 implementation

## Decision

Hermes is a proposal-only research planner. Omnix owns retrieval, durable evidence, knowledge timestamps, fact extraction, feature projection, strategy state, risk, and paper execution.

A research record is visible to a strategy decision only when `omnix_known_at <= decision_at`. Source publication or public-availability time never grants retroactive visibility. Historical research is replayed only from records actually captured by Omnix; present-day SEC/web research may not be injected into an exact historical decision.

`gap_pullback_v1` 1.0.0 and 1.1.0 retain legacy catalyst/dilution semantics. New research semantics are independently pinned by `research_policy_version`, `fact_schema_version`, `extractor_version`, and `feature_projection_version`. A strategy consumes only `StrategyResearchFeatures`, never Hermes prose, raw filings, snippets, or LLM rationale.

Research facts and AI annotations remain non-authoritative until HTR-13/14 outcome evidence has been analyzed and an explicit operator review creates a promotion-enabled validation artifact. Automatic HTR-14 analysis is incapable of granting execution authority by itself.

## HTR-15 version choice

Research-authoritative execution is a new strategy version, not a silent reinterpretation of 1.1:

```text
strategy_kind           = gap_pullback_v1
strategy_version        = 1.2.0
research_policy_version = trading-research-1
feature_projection      = research-features-1
```

`1.0.0` and `1.1.0` never read authoritative HTR policy state and remain replay-compatible with their historical `legacy-1` research semantics. A `1.2.0` decision fails closed when the causal research projection is unavailable or when no reviewed promotion artifact exists.

A reviewed artifact may preserve or reduce the authority recommended by HTR-14; it may never strengthen an automatic recommendation. The **first reviewed promotion artifact is permanently pinned to its `research_policy_version`**. Further outcome analysis may continue, but changing authoritative recommendations requires a new research-policy version (and a new strategy version whenever authorization semantics differ); the existing policy is never silently redefined. The deterministic recommendation semantics are:

- `observe_only` — recorded for analysis, no decision effect;
- `score_only` — favorable/unfavorable evidence contributes `+1/-1` to the existing 0–10 setup-quality score;
- `soft_gate` — unfavorable or missing evidence contributes a stronger `-2` quality penalty, while favorable evidence adds no bonus;
- `hard_gate` — the required favorable state must be present or authorization fails immediately.

The adjusted quality score is clamped to the existing 0–10 range and compared with the strategy's existing minimum-quality threshold. AUTO PAPER and historical backtests call the same pure research-policy/quality evaluator. Hard gates fail closed on missing evidence. The LLM/Hermes planner never receives order, sizing, risk-state, or strategy-configuration authority.

## Forbidden dependencies

`app.trading.research` must not import paper order-placement repositories/APIs. Hermes/research code may emit evidence, reports, facts, features, outcomes, and validation artifacts only.

## Consequences

Research may continue after the entry window opens. Later evidence can influence later decisions but cannot rewrite earlier state. Logs and durable records retain the exact strategy, research-policy, fact/extractor, projection, and validation versions used for every projected feature and decision context.
