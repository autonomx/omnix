# RPG Response Generation Implementation Progress

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Base: `main` at `6514942c618e353ffe06020dec6abae77a211b88`

## Phase status

| Phase | Status | Scope | Validation |
|---:|---|---|---|
| 0 | implemented, CI pending | labeled deterministic corpus, metrics, holdout manifest, opt-in live benchmark, CI test entry point | exact-head GitHub Actions pending |
| 1 | pending | core contracts, thin orchestrator, response modes, renderer | pending |
| 2 | pending | hard gates, ranking, quality, repair, revalidation | pending |
| 3 | pending | compact context, claim ledger, semantic claim references | pending |
| 4 | pending | intent hypotheses, local retrieval, narrative affordances | pending |
| 5 | pending | forward strategies and deterministic fallbacks | pending |
| 6 | pending | proposal-only Hermes recovery | pending |
| 7 | pending | truth lifetimes and bounded proposal promotion | pending |
| 8 | pending | pipeline migration and fixup removal | pending |
| 9 | pending | authoritative profiles, validated delivery, performance | pending |
| 10 | pending | observability, regression, autoplay, staged rollout | pending |

## Phase 0 implementation notes

- Public fixture labels cover supported mechanics, unknown lore, invented entities, unsupported magic, impossible technology, ambiguous social intent, contradictory player claims, economy failure, invalid travel, combat boundaries, agency-sensitive recovery, and broad lore questions.
- The deterministic metric evaluator operates on structured observations and does not depend on exact live-model wording.
- Hidden holdout content is not committed; only a content-free hash manifest and use policy are present.
- The live-model benchmark is opt-in through `OMNIX_RPG_RESPONSE_LIVE_BENCHMARK=1` and remains informational.
- New roadmap tests are run by the required deterministic RPG workflow after every implementation update.
