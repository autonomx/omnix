# RPG AI RPG Parity Phase 22 — Quest Runtime

Phase 22 adds deadline and lead-aware quest runtime reporting.

## Landed

- Added `src/app/rpg/quest_runtime.py`.
- Converts rumors/leads into report-facing quest entries with objectives, clues, NPCs, and locations.
- Adds deadline status metadata: none, active, due_now, expired.
- Surfaces expired quest IDs and journal/chronicle payloads.
- Adds tests for lead conversion, deadline expiration, and unknown-quest deadline validation.

## Verification

Pending GitHub Actions for the Phase 22 PR.
