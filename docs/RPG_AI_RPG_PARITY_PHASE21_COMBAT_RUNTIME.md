# RPG AI RPG Parity Phase 21 — Combat Runtime

Phase 21 expands combat lifecycle reporting around deterministic combat results.

## Landed

- Added `src/app/rpg/combat_runtime.py`.
- Resolves report-facing combat actions through the deterministic combat lifecycle helper.
- Adds expanded defeat outcome metadata for capture, retreat, rescue-style, robbery-style, and reputation-loss outcomes.
- Keeps XP gated to kill, quest, and milestone sources.
- Adds usage-skill progress metadata.
- Adds tests for defeat/XP/loot, rejected XP source, and non-loot defeat outcomes.

## Verification

Pending GitHub Actions for the Phase 21 PR.
