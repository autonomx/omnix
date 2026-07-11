# RPG Response Generation Implementation Progress

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Base: `main` at `6514942c618e353ffe06020dec6abae77a211b88`

## Phase status

| Phase | Status | Scope | Validation |
|---:|---|---|---|
| 0 | complete | labeled corpus and metrics | passed `7bf797d1cd4953b12042662d3ded5f3f81cac952` |
| 1 | complete | contracts, orchestrator, renderer | passed `2170a2a80309c94583bd9caf621eb56d98b724b9` |
| 2 | complete | hard gates, ranking, repair, rewrite revalidation | passed `363a1fad0b43196240deba26fdf58e6747493fb1` |
| 3 | complete | compact context, claim ledger, semantic references | passed `12f2aad071a5ec42eb52a58da7bcc451fbf07fb2` |
| 4 | complete | intent, retrieval, speaker boundaries, affordances | passed `6e12ca5b6737f0ccdde76f44476ad6fbadb2d998` |
| 5 | complete | forward strategies, loop breaking, deterministic fallbacks | passed after repair `f8ea2a5762ca76d5448e6d8dbad104dc6e82369d` |
| 6 | implemented, CI pending | proposal-only bounded Hermes recovery | exact-head GitHub Actions pending |
| 7 | pending | truth lifetimes and bounded proposal promotion | pending |
| 8 | pending | pipeline migration and fixup removal | pending |
| 9 | pending | authoritative profiles, validated delivery, performance | pending |
| 10 | pending | observability, regression, autoplay, staged rollout | pending |

## Completed implementation notes

- Phase 0 established deterministic labeled evaluation and an opt-in live benchmark.
- Phase 1 established canonical response contracts, ownership, and field-aware rendering.
- Phase 2 made truth, visibility, speaker scope, proposal permissions, and agency hard gates.
- Phase 3 added current-turn context, typed claims, and semantic claim references.
- Phase 4 added deterministic affordance classification and ordered visible local retrieval.
- Phase 5 added agency-preserving forward strategies, loop breaking, and useful deterministic fallbacks.

## Phase 6 implementation notes

- Added an RPG-specific Hermes request and result schema.
- Hermes receives only the unresolved question, selected affordance, underlying goal, version keys, and bounded player-visible evidence.
- Requests are permanently proposal-only, review-required, non-executing, non-mutating, and forbidden from taking the player's choice.
- Result parsing rejects direct or nested state mutation and execution keys.
- Timeouts, cancellation, malformed output, unavailable service, cache behavior, and circuit breaking all fail closed to local recovery.
- Safe successful research is cached by normalized query, campaign version, and lore version.
