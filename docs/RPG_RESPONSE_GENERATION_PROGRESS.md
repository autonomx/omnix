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
| 5 | complete | forward strategies, loop breaking, deterministic fallbacks | passed `f8ea2a5762ca76d5448e6d8dbad104dc6e82369d` |
| 6 | complete | proposal-only bounded Hermes recovery | passed `89272ea279766e85c3258917efc560fa56f71e81` |
| 7 | complete | ephemeral truth, budgets, deterministic promotion, replay-safe store | passed `509d44623e5493e3862ccf408b2366668781ee68` |
| 8 | complete | canonical publication bridge, explicit facade, fixup removal, source guards | passed after compatibility repair `79d57e9c9973cfe38a27a6bfeaf609e3cf11e1ec` |
| 9 | implemented, CI pending | authoritative profiles, validation-first delivery, caches and latency policy | exact-head GitHub Actions pending |
| 10 | pending | observability, regression, autoplay, staged rollout | pending |

## Completed implementation notes

- Phases 0-3 established deterministic evaluation, canonical response ownership, hard gates, compact context, and typed claims.
- Phases 4-5 added local affordance recovery, agency-preserving progression, loop breaking, and useful deterministic fallbacks.
- Phase 6 added bounded proposal-only Hermes research with fail-closed local recovery.
- Phase 7 added ephemeral-by-default truth, deterministic bounded promotion, replay-safe events, and garbage collection.
- Phase 8 moved final scene publication behind the canonical generator, removed import-order fixups, and preserved ambient narration through explicit exports.

## Phase 9 implementation notes

- Added one response profile authority backed by the existing RPG prompt-profile registry.
- Runtime attempts to override provider, model, temperature, tokens, timeout, retries, execution, or delivery settings are recorded and ignored.
- Utility responses are deterministic; normal supported turns never invoke Hermes; only unresolved investigation and recovery modes may permit bounded Hermes research.
- Added blocking-path decisions for deterministic, cache, generate, and recover paths with explicit budgets.
- Added versioned caches for entity, lore, and research context plus deterministic p50/p95 benchmark helpers.
- Legacy raw provider chunks are no longer forwarded. Complete text is validated, repaired, revalidated, and split into approved sentence or audio-phrase units before delivery.
- Added delivery validation tokens, checksums, ordered acknowledgements, interruption/cancellation checkpoints, and replay-safe restoration so unheard suffixes remain undelivered.
- Added first-approved-delivery and per-stage latency trace contracts.
