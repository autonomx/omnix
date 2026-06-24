# RPG AI RPG Parity Phase 16 — Integration Hardening

## Goal

Phase 16 turns the Phase 1-15 deterministic foundations into one auditable integration-readiness payload for a resolved RPG turn. It does not allow LLM output to mutate state. It composes existing helpers so runtime wiring can prove which pieces are ready, which pieces must remain blocking, and which pieces need follow-up before a turn is considered fully productized.

## Implemented

- Added `src/app/rpg/integration_hardening.py`.
- Added `Phase16IntegrationInput` and `Phase16IntegrationReport`.
- Added `build_phase16_integration_report` to compose:
  - Phase 1 narration quality and safe rewrite contracts;
  - Phase 2 prompt profile debug payloads and registry validation;
  - Phase 12 fast-action and blocking/deferred path classification;
  - Phase 13 replay snapshot validation;
  - Phase 14 world-pack validation;
  - Phase 15 director suggestions and loop/report payloads.
- Added `strict_validate_snapshot` to require the full runtime state groups promised by the roadmap: world, player, party, NPCs, quests, map, inventory, combat, memory, seed, and RNG counters.
- Added `strict_validate_world_pack` to reject forbidden state-mutation keys even when they are nested inside mod overlay payloads.
- Added tests in `src/tests/rpg/test_integration_hardening.py`.

## Determinism and Safety

- The Phase 16 helper is pure and side-effect free.
- Narration rewrites are represented as presentation-only contracts.
- Fast-action classification does not skip simulation resolution.
- Replay validation is stricter than the Phase 13 foundation helper.
- World-pack validation now catches nested attempts to mutate player state, currency, XP, combat HP, or quest status.

## Remaining Runtime Wiring

Phase 16 provides the audit layer needed for runtime integration, but follow-up slices should still wire the report into:

- the actual turn resolver response/debug payload;
- the 20-turn and 100-turn benchmark reports;
- save/load regression scenarios;
- browser debug panels;
- production runtime provider dispatch.

## Verification

Completed in PR #790. Required GitHub Actions passed before merge: `RPG Phase 0 architecture compliance` and `RPG deterministic PR gates`.
