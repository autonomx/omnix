# RPG AI RPG Parity Phase 17 — Runtime Integration Report Surface

## Goal

Phase 17 begins the real runtime integration hardening pass by moving the Phase 16 readiness audit from an isolated helper into report-facing surfaces. The slice keeps simulation state authoritative and uses the audit only as a deterministic debug/report payload.

## Implemented

- Added `src/app/rpg/runtime_integration_report.py`.
- Added `build_turn_runtime_integration_report` for resolved turn results.
- Added `attach_runtime_integration_to_row` for transcript rows.
- Added `attach_runtime_integration_to_autoplay_summary` for autoplay summary/transcript artifacts.
- Added `src/tests/rpg/autoplay_llm_campaign_parts/zz_phase17_runtime_integration.pyfrag` to decorate autoplay campaign summaries and persist updated JSON artifacts.
- Added tests in `src/tests/rpg/test_runtime_integration_report.py`.
- Updated the stale Phase 16 verification note.

## Determinism and Safety

- The runtime integration report does not mutate authoritative game state.
- The report wraps resolved `turn_result` data and derives a replay snapshot only for validation/reporting.
- Autoplay artifact decoration happens after the turn result is produced.
- Narration rewrite requests remain presentation-only contracts from Phase 1/16.

## What This Wires

- Phase 1 narration quality and rewrite contracts become visible on transcript rows.
- Phase 2 prompt profile debug payloads become part of the per-turn report.
- Phase 12 path classification becomes part of the per-turn report.
- Phase 13 strict snapshot validation becomes visible in report issues.
- Phase 14 world-pack overlay validation remains available through the composite report.
- Phase 15 director suggestion/readiness audit becomes available in report payloads.

## Remaining Runtime Wiring

Follow-up slices still need to wire the underlying gameplay systems directly into their live resolvers/UI:

- provider dispatch should consume Phase 2 profiles directly;
- travel/save/load/UI map should consume Phase 3 graph data;
- NPC dialogue/memory should consume Phase 4-6 relationship/social helpers;
- shop/inn actions should consume Phase 7 economy helpers;
- combat runtime should expand Phase 8 outcomes and skill growth;
- quests should add Phase 9 deadlines/leads;
- images should add Phase 11 portrait persistence;
- CI should add explicit replay gates beyond this report surface.

## Verification

Pending GitHub Actions for the Phase 17 PR.
