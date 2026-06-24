# RPG AI RPG Parity Phase 27 — Gameplay Closure

Phase 27 adds deterministic closure notes and next-action guidance for gameplay reports.

## Landed

- Added `src/app/rpg/gameplay_closure_runtime.py`.
- Surfaces travel readiness/expansion notes, expired quest IDs, memory hooks, NPC memory summaries, and grounded next actions.
- Adds an autoplay wrapper fragment that decorates transcript rows with closure metadata.
- Adds tests for next-action generation and missing-suggestion validation.

## Verification

Pending GitHub Actions for the Phase 27 PR.
