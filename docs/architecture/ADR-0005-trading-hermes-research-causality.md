# ADR-0005 — Trading Hermes research causality and authority

**Status:** Accepted for PR #1494 implementation

## Decision

Hermes is a proposal-only research planner. Omnix owns retrieval, durable evidence, knowledge timestamps, fact extraction, feature projection, strategy state, risk, and paper execution.

A research record is visible to a strategy decision only when `omnix_known_at <= decision_at`. Source publication or public-availability time never grants retroactive visibility. Historical research is replayed only from records actually captured by Omnix; present-day SEC/web research may not be injected into an exact historical decision.

`gap_pullback_v1` 1.0.0 and 1.1.0 retain legacy catalyst/dilution semantics. New research semantics are independently pinned by `research_policy_version`, `fact_schema_version`, `extractor_version`, and `feature_projection_version`. A strategy consumes only `StrategyResearchFeatures`, never Hermes prose, raw filings, snippets, or LLM rationale.

Research facts and AI annotations remain non-authoritative until an HTR-14 validation report explicitly approves promotion. If authorization semantics change, the execution strategy version must advance rather than silently changing 1.1.0.

## Forbidden dependencies

`app.trading.research` must not import paper order-placement repositories/APIs. Hermes/research code may emit evidence, reports, facts, features, outcomes, and validation artifacts only.

## Consequences

Research may continue after the entry window opens. Later evidence can influence later decisions but cannot rewrite earlier state. Logs and durable records retain the exact policy/schema/projection versions used for every projected feature and decision context.
