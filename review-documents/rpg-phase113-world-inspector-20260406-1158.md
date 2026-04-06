# Phase 11.3 — World / Faction / Location Inspector Implementation

**Date:** 2026-04-06 11:58  
**Status:** Implemented

## Goal

Add canonical, read-only world inspector state using the same pattern as character UI/inspector:

- builder layer in `app.rpg.ui`
- ensure/extract helpers in route layer
- top-level payload fields on presentation responses
- frontend list + selected-detail inspector

## Design Constraints

- Deterministic
- Read-only
- Bounded
- Derived from authoritative simulation state
- No LLM calls
- No new persistent world state

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `src/app/rpg/ui/world_builder.py` | World inspector state builders |
| `src/tests/unit/rpg/test_world_builder.py` | Unit tests for world builders |
| `src/tests/regression/test_phase113_world_inspector_regression.py` | Regression tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/app/rpg/ui/__init__.py` | Export world builder functions |
| `src/app/rpg/api/rpg_presentation_routes.py` | Add world inspector helpers, route, and response fields |
| `src/static/rpg/rpgPresentationRenderer.js` | Add world inspector rendering |
| `src/static/rpg/rpgInspectorStyles.css` | Add world inspector styles |
| `src/tests/functional/test_character_ui_functional.py` | Add world inspector functional tests |

---

## Implementation Details

### 1. World Builder Layer (`src/app/rpg/ui/world_builder.py`)

**Functions:**
- `build_faction_inspector_state(simulation_state)` → Extracts faction data with members, relationships
- `build_location_inspector_state(simulation_state)` → Extracts location data with tags, actors
- `build_world_inspector_state(simulation_state)` → Combined world state with threads, factions, locations

**Bounding constants:**
- `_MAX_FACTIONS = 12`
- `_MAX_LOCATIONS = 16`
- `_MAX_WORLD_THREADS = 12`
- `_MAX_FACT_MEMBERS = 8`
- `_MAX_LOCATION_TAGS = 8`
- `_MAX_LOCATION_ACTORS = 8`
- `_MAX_FACTION_RELATIONSHIPS = 8`

### 2. Route Layer (`src/app/rpg/api/rpg_presentation_routes.py`)

**New route:**
```
POST /api/rpg/world_inspector
```

**Updated routes with `world_inspector_state`:**
- `POST /api/rpg/presentation/scene`
- `POST /api/rpg/presentation/dialogue`
- `POST /narrative-recap`

**Helpers:**
- `_safe_world_inspector_state(v)` → Validate/sanitize world inspector state
- `_ensure_world_inspector_state(simulation_state)` → Attach world state to presentation
- `_extract_world_inspector_state(simulation_state)` → Extract from simulation state

### 3. Frontend (`src/static/rpg/rpgPresentationRenderer.js`)

**New functions:**
- `renderWorldList(worldInspectorState)` → Render selectable list of factions/locations
- `renderWorldInspector(worldInspectorState)` → Render detail panel
- `bindWorldInspectorEvents(worldInspectorState)` → Handle selection clicks

**Integration:**
- `renderPresentation(payload)` now handles `world_inspector_state`

### 4. Styles (`src/static/rpg/rpgInspectorStyles.css`)

**New CSS classes:**
- `.inspector-world-button` → List item button
- `.inspector-world-button.is-selected` → Selected state
- `.inspector-world-name` → Item name
- `.inspector-world-kind` → Item type label
- `.inspector-tag` → Location tag chip

---

## Test Coverage

### Unit Tests (`src/tests/unit/rpg/test_world_builder.py`)

| Test | Coverage |
|------|----------|
| `test_build_world_inspector_state_empty` | Empty state handling |
| `test_build_faction_inspector_state_empty` | Empty factions |
| `test_build_location_inspector_state_empty` | Empty locations |
| `test_build_faction_inspector_state_basic` | Basic faction extraction |
| `test_build_location_inspector_state_basic` | Basic location extraction |
| `test_build_world_inspector_state_with_threads` | Thread extraction |
| `test_build_faction_inspector_state_bounds` | _MAX_FACTIONS (12) |
| `test_build_location_inspector_state_bounds` | _MAX_LOCATIONS (16) |
| `test_build_location_inspector_tag_bounds` | _MAX_LOCATION_TAGS (8) |
| `test_build_location_inspector_actor_bounds` | _MAX_LOCATION_ACTORS (8) |
| `test_build_faction_relationships_bounds` | _MAX_FACTION_RELATIONSHIPS (8) |
| `test_build_faction_members_bounds` | _MAX_FACT_MEMBERS (8) |
| `test_build_world_threads_bounds` | _MAX_WORLD_THREADS (12) |
| `test_build_faction_inspector_deterministic` | Determinism |
| `test_build_location_inspector_deterministic` | Determinism |
| `test_build_world_inspector_deterministic` | Determinism |

### Functional Tests (`src/tests/functional/test_character_ui_functional.py`)

| Test | Coverage |
|------|----------|
| `test_world_inspector_endpoint_returns_ok` | `/api/rpg/world_inspector` returns ok=True |
| `test_scene_presentation_includes_world_inspector_state` | Scene route includes world state |
| `test_dialogue_presentation_includes_world_inspector_state` | Dialogue route includes world state |

### Regression Tests (`src/tests/regression/test_phase113_world_inspector_regression.py`)

| Test | Coverage |
|------|----------|
| `test_scene_presentation_still_returns_character_state` | Backward compatibility |
| `test_dialogue_presentation_still_returns_character_state` | Backward compatibility |
| `test_world_inspector_state_shape_is_stable` | Response shape validation |
| `test_world_inspector_with_world_data` | Data reflection |
| `test_narrative_recap_still_returns_character_state` | Route backward compat |
| `test_character_inspector_still_works` | Character inspector unaffected |
| `test_character_ui_still_works` | Character UI unaffected |

---

## Acceptance Criteria

### Phase 11.3

- [x] World inspector builders exist and are exported
- [x] World inspector state is ensured/extracted via shared helpers
- [x] Normal presentation routes include `world_inspector_state`
- [x] Dedicated `/api/rpg/world_inspector` exists
- [x] Frontend renders selectable world list + detail inspector
- [x] Unit tests pass
- [x] Functional tests pass
- [x] Regression tests pass

---

## API Response Shape

### World Inspector State
```json
{
  "summary": {
    "current_location": "string",
    "current_region": "string",
    "threat_level": "number|null"
  },
  "threads": [
    {"id": "string", "title": "string", "status": "string", "pressure": "number|null"}
  ],
  "thread_count": 0,
  "factions": {
    "factions": [
      {
        "id": "string",
        "name": "string",
        "kind": "faction",
        "description": "string",
        "status": "string",
        "influence": "number|null",
        "members": ["string"],
        "relationships": [
          {"target_id": "string", "kind": "string", "score": "number|null"}
        ],
        "meta": {"source": "faction_state"}
      }
    ],
    "count": 0
  },
  "locations": {
    "locations": [
      {
        "id": "string",
        "name": "string",
        "kind": "location",
        "description": "string",
        "tags": ["string"],
        "actors": ["string"],
        "danger_level": "number|null",
        "meta": {"source": "world_state"}
      }
    ],
    "count": 0
  }
}