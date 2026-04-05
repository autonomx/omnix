# Phase 7 — Creator / GM Experience Review Document

**Date:** 2026-04-04 23:10  
**Phase:** 7  
**Status:** ✅ All 56 tests passing

## Summary

Implemented Phase 7 (Creator / GM Experience) which turns the RPG engine from internally rich but opaque to inspectable, steerable, debuggable, and replayable.

## Goal

After Phase 7, creator / GM tools support:
- Inspect NPC minds
- Inspect faction positions / rumors / alliances
- Step simulation manually
- Inject manual events
- Force alliances / rumors / betrayals
- View "why this happened"
- Replay snapshots and diffs

## New Modules Created

### 1. `src/app/rpg/creator/world_debug.py`
- **Purpose:** Collect compact inspector/debug views from simulation state, provide explainability surfaces
- **Functions:**
  - `summarize_npc_minds()` — bounded, deterministic NPC mind summaries
  - `summarize_social_state()` — alliances, rumors, group positions, reputation
  - `summarize_world_pressures()` — threads, factions, locations sorted by pressure
  - `explain_npc()` — explain why an NPC made their last decision
  - `explain_faction()` — faction stance, members, alliances
  - `summarize_tick_changes()` — diff between two simulation states

### 2. `src/app/rpg/creator/world_gm_tools.py`
- **Purpose:** Controlled GM intervention helpers, pure state mutation helpers
- **Functions:**
  - `inject_event()` — inject event with debug metadata
  - `seed_rumor()` — seed new rumor into social state
  - `force_alliance()` — force alliance into social state
  - `force_faction_position()` — force faction position and record as GM override
  - `force_npc_belief()` — force NPC's belief about another entity
  - `step_ticks()` — step simulation forward safely (clamped to 1-20)

### 3. `src/app/rpg/creator/world_replay.py`
- **Purpose:** Timeline/replay helpers using existing snapshot + diff system
- **Functions:**
  - `list_snapshots()` — sorted by tick, limited to 100
  - `get_snapshot()` — get specific snapshot by id
  - `rollback_to_snapshot()` — restore snapshot with debug meta
  - `summarize_timeline()` — timeline summary

## Patched Existing Modules

### 4. `src/app/rpg/creator/world_simulation.py`
- **Added import:** `from .world_debug import summarize_tick_changes`
- **Added before_state capture:** `before_state = copy.deepcopy(current)`
- **Added debug_meta tracking:**
  ```python
  history_state.setdefault("debug_meta", {})
  history_state["debug_meta"]["last_step_reason"] = ...
  history_state["debug_meta"]["last_step_tick"] = ...
  history_state["debug_meta"]["last_tick_changes"] = summarize_tick_changes(before_state, history_state)
  ```
- **Added GM overrides application:** Forced faction positions and NPC beliefs applied after social computation

### 5. `src/app/rpg/creator/world_scene_generator.py`
- **Added debug_context to scenes:**
  ```python
  scene["debug_context"] = {
      "tick": int(state.get("tick", 0) or 0),
      "source_id": source_id_for_debug,
      "active_rumor_count": len(state.get("active_rumors") or []),
      "has_social_state": bool(state.get("social_state")),
  }
  scene["debug_context"]["top_pressure_sources"] = {
      "threads": sorted([...])[:3],
      "factions": sorted([...])[:3],
      "locations": sorted([...])[:3],
  }
  ```

### 6. `src/app/rpg/ai/world_scene_narrator.py`
- **Added debug context to NPC reaction prompt:**
  ```python
  debug_context_info = f"Scene debug context: {scene.get('debug_context', {})}" if scene.get("debug_context") else ""
  ```

### 7. `src/app/rpg/creator/world_player_actions.py`
- **Added debug_reason to action_diff:**
  ```python
  action_diff["debug_reason"] = {
      "action_type": action_type,
      "target_id": target_id,
      "events_added_count": len(events),
      "consequences_added_count": len(action_diff.get("consequences_added") or []),
  }
  ```

## API Endpoints

These debug endpoints are available through functional test app (or register `rpg_debug_bp` blueprint):

| Endpoint | Description |
|----------|-------------|
| `POST /api/rpg/debug/state` | Get full debug state (npc_minds, social, pressures, timeline) |
| `POST /api/rpg/debug/npc` | Explain a specific NPC's state |
| `POST /api/rpg/debug/faction` | Explain a specific faction's state |
| `POST /api/rpg/debug/step` | Step simulation N ticks |
| `POST /api/rpg/debug/inject_event` | Inject a custom event |
| `POST /api/rpg/debug/seed_rumor` | Seed a rumor |
| `POST /api/rpg/debug/force_alliance` | Force an alliance |
| `POST /api/rpg/debug/force_faction_position` | Force faction position |
| `POST /api/rpg/debug/force_npc_belief` | Force NPC belief |
| `POST /api/rpg/debug/snapshots` | List snapshots |
| `POST /api/rpg/debug/snapshot` | Get specific snapshot |
| `POST /api/rpg/debug/rollback` | Rollback to snapshot |

## Test Results

All **56 tests** pass:

| Test File | Count | Description |
|-----------|-------|-------------|
| `test_phase7_debug_tools.py` | 33 | Unit tests for all debug tools |
| `test_phase7_debug_routes_functional.py` | 10 | Functional tests for API endpoints |
| `test_phase7_debug_regression.py` | 13 | Regression tests for determinism |

## Design Rules Applied

1. Did not break gameplay APIs
2. GM Changes go through simulation state, not narrator-only state
3. All new endpoints return structured JSON
4. Deterministic ordering everywhere
5. Bounded outputs for debug payloads (max 12 items)
6. Snapshots remain canonical source of replay state

## What Success Looks Like

The creator / GM can now:
- Inspect any NPC's beliefs, memories, goals, and last decision
- Inspect faction stance and alliances
- See active rumors
- Manually step the world
- Inject custom events
- Force or patch state for testing / storytelling
- Browse snapshots
- Roll back to prior state
- Understand why scenes and reactions happened