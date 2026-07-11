# RPG Response Generation Implementation Progress

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Base: `main` at `6514942c618e353ffe06020dec6abae77a211b88`

## Phase status

| Phase | Status | Scope | Validation |
|---:|---|---|---|
| 0 | complete | labeled deterministic corpus, metrics, holdout manifest, opt-in live benchmark, CI test entry point | exact-head GitHub Actions passed at `7bf797d1cd4953b12042662d3ded5f3f81cac952` |
| 1 | complete | core contracts, thin orchestrator, response modes, field-aware renderer, legacy shadow adapters | exact-head GitHub Actions passed at `2170a2a80309c94583bd9caf621eb56d98b724b9` |
| 2 | complete | hard gates, eligible-only ranking, final quality repair, rewrite revalidation | exact-head GitHub Actions passed after repair at `363a1fad0b43196240deba26fdf58e6747493fb1` |
| 3 | implemented, CI pending | compact current-turn context, typed claim ledger, semantic claim validation | exact-head GitHub Actions pending |
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

## Phase 1 implementation notes

- Added stable `ResponseRequest`, `SemanticResponsePlan`, `ResponseCandidate`, and `RenderedResponse` contracts.
- Added response modes and centralized visible word budgets.
- Added `RpgResponseGenerator.generate()` as the canonical ownership boundary.
- Added compatibility adapters for runtime narration and world-scene payload shapes.
- Added field-aware rendering with mode ordering, semantic deduplication, delivery-unit extraction, and authoritative delta separation.
- Added shadow comparison reports that cannot mutate simulation state.

## Phase 2 implementation notes

- Added hard gates for allowed state claims, hidden information, speaker knowledge, proposals, player agency, semantic references, and direct mutation attempts.
- Candidate ranking now receives only eligible candidates; prose quality cannot compensate for a failed gate.
- Added grounded-safe and stale-prior tie-break metadata.
- Added final-visible quality evaluation for meta language, low-value phrases, duplicate sentences, and repeated openings.
- Added deterministic section repair and one bounded rewrite attempt.
- Every rewrite is fully re-evaluated by the hard gates; failed rewrites preserve the last eligible candidate.

## Phase 3 implementation notes

- Added `ClaimLedger` and `ClaimRecord` contracts with typed visibility, provenance, speakers, persistence, and prohibited claims.
- Added deterministic claim derivation for location, currency, inventory, combat, quests, relationships, discovered facts, and approved proposals.
- Production RPG grounding cannot be disabled by a false runtime flag.
- Added compact, current-turn-first `NarrationContext` with scene, entity, speaker, evidence, continuity, agency, style, budget, and truncation traces.
- Hidden evidence is excluded before prompt payload construction.
- Added semantic-plan validation requiring factual sections to reference ledger claims or explicitly allowed soft truth.
