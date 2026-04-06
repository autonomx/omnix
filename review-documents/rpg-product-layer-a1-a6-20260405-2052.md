# RPG Product Layer — Phases A1-A6 Implementation

**Date:** 2026-04-05 20:52
**Commit:** Product Layer implementation (Option A)

## Summary

Implemented the RPG Product Layer covering six phases (A1-A6) of player-facing presentation upgrades. All changes are read-only presentation helpers that do not mutate simulation truth.

## Phases Implemented

### Phase A1 — Session Entry / World Setup
- **File:** `src/app/rpg/presentation/setup_flow.py`
- **Function:** `build_setup_flow_payload()`
- Deterministic genre/tone/rules/role/seed prompt normalization
- 7 genres, 6 tones, 5 rule keys
- Wizard step definitions for frontend setup flow
- New route: `POST /api/rpg/presentation/setup-flow`
- New route: `POST /api/rpg/presentation/session-bootstrap`

### Phase A2 — First 60 Seconds Experience
- **File:** `src/app/rpg/presentation/intro_scene.py`
- **Function:** `build_intro_scene_payload()`
- Genre-specific intro scenes with opening NPC, tension hook, and actionable affordance
- Presets for all 7 genres (fantasy gate, cyberpunk alley, horror chapel, etc.)
- New route: `POST /api/rpg/presentation/intro-scene`

### Phase A3 — Dialogue UX Upgrade
- **File:** `src/app/rpg/presentation/dialogue_ux.py`
- **Function:** `build_dialogue_ux_payload()`
- 5 intent buttons (Ask, Threaten, Help, Observe, Leave)
- Hybrid input metadata (free text + intent buttons)
- Layered output (speaker, companion, system layers)
- Streaming hint based on provider mode
- Integrated into existing dialogue route

### Phase A4 — Player-safe Inspector Overlay
- **File:** `src/app/rpg/presentation/player_inspector.py`
- **Function:** `build_player_inspector_overlay_payload()`
- Tension band display (low/guarded/steady/rising/high)
- Scene, conversation, relationship, and system status overlay
- Integrated into scene and dialogue routes

### Phase A5 — Save/Load UX
- **File:** `src/app/rpg/presentation/save_load_ux.py`
- **Function:** `build_save_load_ux_payload()`
- Normalized save slot sorting (descending by tick)
- Rewind preview with tick delta computation
- New route: `POST /api/rpg/presentation/save-load-ux`

### Phase A6 — Narrative Recap / Codex Surfacing
- **File:** `src/app/rpg/presentation/narrative_recap.py`
- **Function:** `build_narrative_recap_payload()`
- Recent dialogue lines reconstruction (last 3 turns)
- Codex entry surfacing (top 5)
- New route: `POST /api/rpg/presentation/narrative-recap`

## New Route Endpoints

| Endpoint | Phase | Description |
|----------|-------|-------------|
| `POST /api/rpg/presentation/setup-flow` | A1 | Build setup wizard payload |
| `POST /api/rpg/presentation/session-bootstrap` | A1 | Build session bootstrap payload |
| `POST /api/rpg/presentation/intro-scene` | A2 | Build intro scene payload |
| `POST /api/rpg/presentation/save-load-ux` | A5 | Build save/load UX payload |
| `POST /api/rpg/presentation/narrative-recap` | A6 | Build narrative recap payload |

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `src/app/rpg/presentation/setup_flow.py` | NEW | A1 setup flow builder |
| `src/app/rpg/presentation/intro_scene.py` | NEW | A2 intro scene generator |
| `src/app/rpg/presentation/dialogue_ux.py` | NEW | A3 dialogue UX helpers |
| `src/app/rpg/presentation/player_inspector.py` | NEW | A4 player inspector overlay |
| `src/app/rpg/presentation/save_load_ux.py` | NEW | A5 save/load UX helpers |
| `src/app/rpg/presentation/narrative_recap.py` | NEW | A6 narrative recap builder |
| `src/app/rpg/presentation/__init__.py` | MODIFIED | Added 6 new exports |
| `src/app/rpg/api/rpg_presentation_routes.py` | MODIFIED | Added 5 new routes + integrated A3/A4 |
| `src/tests/unit/rpg/test_product_layer_a1_a6.py` | NEW | Unit tests (18 tests) |
| `src/tests/functional/test_product_layer_a1_a6_functional.py` | NEW | Functional tests (7 tests) |
| `src/tests/regression/test_product_layer_a1_a6_regression.py` | NEW | Regression tests (16 tests) |

## Test Results

**All 41 tests passed:**
- Unit tests: 18 passed
- Functional tests: 7 passed
- Regression tests: 16 passed

## Code Diff

See `review-documents/rpg-product-layer-a1-a6-20260405-2052.diff` for full diff.

## Pre-Merge Fixes Applied

1. **Route decorators** — Changed from full paths (`/api/rpg/presentation/setup-flow`) to blueprint-local short paths (`/setup-flow`)
2. **Duplicate imports** — Removed redundant direct imports of `build_dialogue_ux_payload` and `build_player_inspector_overlay_payload` (already imported via `__init__.py`)
3. **rpg-design.txt** — Restored to original state (was unintentionally overwritten)
4. **Payload nesting fix** — `inspector_overlay_payload` and `dialogue_ux_payload` are nested dicts; routes now extract `.get("player_overlay", {})` and `.get("dialogue_ux", {})` to avoid double-nesting in the final response payload

## Design Guarantees

1. **No simulation mutation** — all builders are read-only
2. **Deterministic output** — same inputs always produce same outputs
3. **Input safety** — no mutation of input dictionaries
4. **Clamping** — rule values clamped to [0, 1]