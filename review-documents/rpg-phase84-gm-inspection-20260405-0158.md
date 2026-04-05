# Phase 8.4 — Debug / Analytics / GM Inspection

**Date:** 2026-04-05 01:58 UTC
**Author:** Cline

## Summary

Implemented the Phase 8.4 diff spec from `rpg-design.txt`. This phase adds:

- **Timeline inspection API** — summarize world state as compact timeline rows
- **Tick diff engine** — compute compact differences between two simulation states
- **NPC reasoning inspector** — expose beliefs, goals, memories, decisions for any NPC
- **GM intervention hooks** — force NPC goals, faction trends, and attach debug notes

## Files Created

### Analytics Layer

| File | Purpose |
|------|---------|
| `src/app/rpg/analytics/__init__.py` | Package init; re-exports all analytics functions |
| `src/app/rpg/analytics/tick_diff.py` | `build_tick_diff(before, after)` — computes structured diff |
| `src/app/rpg/analytics/timeline.py` | `build_timeline_summary(state)`, `get_timeline_tick(state, tick)` |
| `src/app/rpg/analytics/npc_reasoning.py` | `inspect_npc_reasoning(state, npc_id)` — NPC inspector |
| `src/app/rpg/analytics/gm_hooks.py` | `gm_force_npc_goal`, `gm_force_faction_trend`, `gm_append_debug_note` |

### API Routes

| File | Purpose |
|------|---------|
| `src/app/rpg/api/rpg_inspection_routes.py` | Blueprint with 7 routes (timeline, tick diff, NPC reasoning, 3 GM hooks) |

### Tests

| File | Type | Tests |
|------|------|-------|
| `src/tests/unit/rpg/test_phase84_tick_diff.py` | Unit | 4 tests (basic, no changes, NPC changes, social changes) |
| `src/tests/unit/rpg/test_phase84_npc_reasoning.py` | Unit | 3 tests (basic, missing NPC, minimal state) |
| `src/tests/functional/test_phase84_inspection_routes.py` | Functional | 6 tests (all routes) |
| `src/tests/regression/test_phase84_inspection_regression.py` | Regression | 14 tests (safety, bounded outputs, API 200s) |

## Files Modified

| File | Change |
|------|--------|
| `src/app/__init__.py` | Registered `rpg_inspection_bp` blueprint |
| `src/app/rpg/creator/world_simulation.py` | Added `CURRENT_RPG_SCHEMA_VERSION`, `ENGINE_VERSION` imports; added `save_meta` and `timeline.ticks` tracking |
| `src/app/rpg/creator/world_debug.py` | Added `schema_version` field to `summarize_social_state()` output |

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/rpg/inspect/timeline` | Timeline summary from simulation state |
| POST | `/api/rpg/inspect/timeline_tick` | Get specific tick snapshot |
| POST | `/api/rpg/inspect/tick_diff` | Diff two state payloads |
| POST | `/api/rpg/inspect/npc_reasoning` | Inspect NPC reasoning |
| POST | `/api/rpg/gm/force_npc_goal` | Force NPC goal |
| POST | `/api/rpg/gm/force_faction_trend` | Force faction trend |
| POST | `/api/rpg/gm/debug_note` | Append GM debug note |

## Code Diff

Full diff available in: `review-documents/rpg-phase84-gm-inspection-20260405-0158.diff`

## Success Criteria

- [x] Timeline summary API returns structured data
- [x] Tick diff computes new events/consequences/NPC changes
- [x] NPC reasoning exposes beliefs, goals, memories, decisions
- [x] GM can force NPC goals and faction trends
- [x] GM can attach debug notes (bounded to 50)
- [x] Schema version visible in inspection surfaces
- [x] All unit tests pass
- [x] All functional tests pass
- [x] All regression tests pass