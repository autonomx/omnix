# RPG Response Generation Implementation Progress

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Base: `main` at `6514942c618e353ffe06020dec6abae77a211b88`

## Phase status

| Phase | Status | Scope |
|---:|---|---|
| 0 | complete | labeled corpus, live observation runner, deterministic metrics, holdout policy |
| 1 | complete | canonical contracts, orchestrator, response modes, field-aware renderer |
| 2 | complete | hard eligibility gates, eligible-only ranking, final quality and revalidation cycle |
| 3 | complete | compact context, typed claim ledger, strict semantic claim references |
| 4 | complete | intent hypotheses, ordered local retrieval, speaker knowledge boundaries |
| 5 | complete | agency-preserving forward strategies, loop breaking, specific deterministic fallbacks |
| 6 | complete | bounded proposal-only Hermes recovery after local retrieval |
| 7 | complete | ephemeral soft truth, deterministic promotion, budgets, persistence, expiry and replay |
| 8 | complete | canonical runtime/scene publication, explicit facade, fixup and bypass removal |
| 9 | complete | profiles resolved before generation, validation-first delivery, caching and latency policy |
| 10 | complete | traces, real pipeline regression, 100-turn replay, 1000-turn endurance and staged rollout |

## Required-changes integration pass

The post-review integration pass closes the gaps found after the initial Phase 0-10 implementation:

- the normal `apply_turn` narration import and final visible selection now route through the canonical runtime bridge;
- `RpgProductionResponsePipeline` compiles context, derives a strict claim ledger, classifies intent, retrieves local evidence, selects forward motion, invokes Hermes only when justified, and applies proposal lifetime policy;
- production responses cannot disable strict claim references;
- profile policy is resolved before provider generation and bound to provider calls;
- rollout stage is resolved before visible replacement or sentence/audio delivery, with shadow as the default;
- public `SceneNarrator` and `play_scene` outputs are canonically validated;
- deterministic quality repair and candidate reselection guarantee a publishable model-outage fallback;
- stale narration cannot outrank a current grounded candidate;
- retrieval ordering is process-stable;
- unresolved high-risk proposals fail closed instead of entering visible soft truth;
- proposal stores are mirrored into returned session state and persisted through the runtime session boundary;
- Phase 0 fixtures are executed through the actual pipeline;
- deterministic 100-turn and 1000-turn pipeline tests exercise generation, validation, recovery, rendering and bounded proposal state.

## Validation

Exact-head GitHub Actions are required before this pull request can leave draft:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

The final integration head remains pending until both workflows complete successfully.
