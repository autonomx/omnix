# RPG Response Generation Implementation Progress

Source roadmap: `docs/RPG_RESPONSE_GENERATION_ROADMAP.md`  
Implementation branch: `agent/rpg-response-generation-0-10`  
Pull request: `#1325`

## Phase status

| Phase | Status | Scope |
|---:|---|---|
| 0 | complete | labeled corpus, opt-in live observation evaluation, deterministic metrics, holdout policy |
| 1 | complete | canonical contracts, orchestrator, response modes, field-aware renderer |
| 2 | complete | hard eligibility gates, eligible-only ranking, final quality and revalidation cycle |
| 3 | complete | compact context, typed claim ledger, strict semantic claim references |
| 4 | complete | intent hypotheses, ordered local retrieval, speaker knowledge boundaries |
| 5 | complete | agency-preserving forward strategies, loop breaking, specific deterministic fallbacks |
| 6 | complete | bounded proposal-only Hermes recovery after local retrieval |
| 7 | complete | ephemeral soft truth, deterministic promotion, budgets, persistence, expiry and replay |
| 8 | complete | canonical runtime/scene publication, explicit facade, fixup and bypass removal |
| 9 | complete | profiles resolved before generation, validation-first delivery, caching and latency policy |
| 10 | complete | traces, provider-free pipeline regression, replay coverage, 1000-turn public-runtime endurance, staged rollout controls |

## Required-changes integration pass

The post-review integration pass closes the gaps found after the initial Phase 0-10 implementation:

- every public `apply_turn()` return path routes through the canonical runtime publication boundary;
- `RpgProductionResponsePipeline` compiles context, derives a strict claim ledger, classifies intent, retrieves local evidence, selects forward motion, invokes Hermes only when justified, and applies proposal lifetime policy;
- production responses cannot disable strict claim references;
- hard-state prose with explicit values is checked against typed ledger values rather than family-level references alone;
- profile policy is resolved before provider generation and bound to provider calls;
- rollout stage is resolved before visible replacement or sentence/audio delivery, with shadow as the default;
- public `SceneNarrator`, `play_scene`, creator routes, and deferred narration publication are canonically validated;
- deterministic quality repair and candidate reselection guarantee a publishable model-outage fallback;
- a rejected provider rewrite cannot replace the last eligible candidate;
- stale narration cannot outrank a current grounded candidate;
- retrieval ordering is process-stable;
- unresolved high-risk proposals fail closed instead of entering visible soft truth;
- proposal stores are mirrored into returned session state and persisted through the runtime session boundary;
- developer trace data is attached before canonical publication;
- Phase 0 fixtures execute through the production response pipeline;
- continuous 1000-turn provider-free endurance exercises the public `apply_turn()` boundary, replay hash stability, hard gates, bounded state, and latency drift.

## GitHub Actions provider boundary

GitHub-hosted runners do not have access to the configured LM Studio or another live RPG prose provider. The required workflow therefore excludes live-LLM autoplay and runs only:

- deterministic backend, web, response-generation, and narration-queue regressions;
- provider-free continuous 1000-turn public `apply_turn()` endurance;
- the aggregate `RPG deterministic PR gates` check.

`src/tests/rpg/response_generation/test_ci_provider_boundaries.py` prevents live autoplay or provider-skip shims from being reintroduced into the hosted workflow.

Provider-backed 100-turn autoplay and prose/latency evaluation remain local operational evidence. The supported commands and interpretation are documented in `docs/RPG_RESPONSE_GENERATION_COMPLETION_NOTE.md`.

## Validation

The previous implementation head `e59ee6080a44aecaf7dc03d5412f848b7272c941` passed both required workflows exactly:

- `RPG Phase 0 architecture compliance`;
- `RPG deterministic PR gates`.

The final completion-documentation head must pass the same two workflows before PR `#1325` leaves draft.
