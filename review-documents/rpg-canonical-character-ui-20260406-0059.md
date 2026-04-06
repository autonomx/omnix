# RPG Canonical Character UI — Review Document

**Date:** 2026-04-06 00:59
**Status:** Implemented, tested, and lint-clean
**Design Reference:** `rpg-design.txt` (Parts 1-6, excluding frontend CSS/HTML which was out of scope for backend-only implementation)

## Summary

This implementation adds a **canonical, deterministic, read-only character UI state** to the RPG presentation layer. The feature extracts character data from simulation state (speaker cards, personality profiles, social state, AI state) and produces a predictable, bounded character list suitable for frontend character panels.

### Design Invariants Maintained
- No LLM calls added
- No mutation of simulation truth (read-only projection)
- No new persistent character state
- Speaker cards not replaced or mutated
- Backward-compatible with missing `presentation_state`, `personality_state`, `social_state`, `ai_state`
- Deterministic output guaranteed

## Files Changed

### New Files Created
1. **`src/app/rpg/ui/__init__.py`** — Package init for canonical UI builders
2. **`src/app/rpg/ui/character_builder.py`** — Core character UI state extraction logic
3. **`src/tests/unit/rpg/test_character_builder.py`** — 20 unit tests
4. **`src/tests/functional/test_character_ui_functional.py`** — 5 functional tests
5. **`src/tests/regression/test_character_ui_regression.py`** — 8 regression tests

### Files Modified
1. **`src/app/rpg/presentation/personality_state.py`** — Added import and integration of `build_character_ui_state` into `ensure_personality_state`
2. **`src/app/rpg/api/rpg_presentation_routes.py`** — Added `_extract_character_ui_state` helpers, updated 3 existing endpoints, added 1 new `/api/rpg/character_ui` endpoint

## Code Diff

```diff
diff --git a/src/app/rpg/api/rpg_presentation_routes.py b/src/app/rpg/api/rpg_presentation_routes.py
--- a/src/app/rpg/api/rpg_presentation_routes.py
+++ b/src/app/rpg/api/rpg_presentation_routes.py
@@ -4,6 +4,7 @@ Provides read-only builders for presentation payloads:
 - Scene presentation
 - Dialogue presentation
 - Speaker cards
+- Character UI state (canonical)
 - Setup flow (product layer A1)
 - Intro scene (product layer A2)
 - Save/load UX (product layer A5)
@@ -16,6 +17,7 @@ from typing import Any, Dict
 from flask import Blueprint, jsonify, request

 from app.rpg.player import ensure_player_state, ensure_player_party
+from app.rpg.presentation.personality_state import ensure_personality_state
 from app.rpg.presentation import (
     build_scene_presentation_payload,
     build_dialogue_presentation_payload,
@@ -39,11 +41,30 @@ def _safe_dict(v: Any) -> Dict[str, Any]:
     return dict(v) if isinstance(v, dict) else {}


+def _safe_character_ui_state(v: Any) -> Dict[str, Any]:
+    if not isinstance(v, dict):
+        return {"characters": [], "count": 0}
+    return {
+        "characters": list(v.get("characters", [])),
+        "count": int(v.get("count", 0)),
+    }
+
+
 def _get_simulation_state(setup_payload: Dict[str, Any]) -> Dict[str, Any]:
     setup_payload = _safe_dict(setup_payload)
     return _safe_dict(setup_payload.get("simulation_state"))


+def _extract_character_ui_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
+    """Extract character_ui_state from simulation state, ensuring it exists."""
+    simulation_state = _safe_dict(simulation_state)
+    presentation_state = simulation_state.get("presentation_state") or {}
+    if not isinstance(presentation_state, dict):
+        presentation_state = {}
+    character_ui_state = presentation_state.get("character_ui_state") or {"characters": [], "count": 0}
+    return _safe_character_ui_state(character_ui_state)
+
+
 @rpg_presentation_bp.post("/api/rpg/presentation/scene")
 def presentation_scene():
     """Build a presentation-ready scene payload."""
@@ -82,6 +103,7 @@ def presentation_scene():
     return jsonify({
         "ok": True,
         "presentation": payload,
+        "character_ui_state": _extract_character_ui_state(simulation_state),
     })


@@ -130,6 +152,7 @@ def presentation_dialogue():
     return jsonify({
         "ok": True,
         "presentation": payload,
+        "character_ui_state": _extract_character_ui_state(simulation_state),
     })


@@ -239,4 +262,26 @@ def presentation_narrative_recap():
     return jsonify({
         "ok": True,
         "presentation": payload,
-    })
+        "character_ui_state": _extract_character_ui_state(simulation_state),
+    })
+
+
+@rpg_presentation_bp.get("/api/rpg/character_ui")
+def presentation_character_ui():
+    """Return canonical character UI state for current simulation.
+
+    This endpoint provides a deterministic, read-only projection of
+    character data derived from presentation state.
+    """
+    data = request.get_json(silent=True) or {}
+    setup_payload = _safe_dict(data.get("setup_payload"))
+    simulation_state = ensure_player_state(_get_simulation_state(setup_payload))
+    simulation_state = ensure_player_party(simulation_state)
+    simulation_state = ensure_personality_state(simulation_state)
+
+    character_ui_state = _extract_character_ui_state(simulation_state)
+
+    return jsonify({
+        "ok": True,
+        "character_ui_state": character_ui_state,
+    })

diff --git a/src/app/rpg/presentation/personality_state.py b/src/app/rpg/presentation/personality_state.py
--- a/src/app/rpg/presentation/personality_state.py
+++ b/src/app/rpg/presentation/personality_state.py
@@ -7,6 +7,8 @@ from __future__ import annotations

 from typing import Any, Dict, List

+from app.rpg.ui.character_builder import build_character_ui_state
+

 _MAX_TRAITS = 8
 _MAX_STYLE_TAGS = 8
@@ -49,7 +51,8 @@ def _normalize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
 def ensure_personality_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
     """Ensure simulation_state has normalized personality state.

-    Returns the mutated simulation_state with normalized profiles.
+    Returns the mutated simulation_state with normalized profiles
+    and canonical character UI state.
     """
     if not isinstance(simulation_state, dict):
         simulation_state = {}
@@ -70,6 +73,10 @@ def ensure_personality_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]
         profiles_out[str(actor_id)] = normalized

     personality_state["profiles"] = profiles_out
+
+    # Add canonical character UI state (additive, read-only projection)
+    presentation_state["character_ui_state"] = build_character_ui_state(simulation_state)
+
     return simulation_state
```

## Output Shape

Each `character_ui_state.characters[i]` exposes:

```json
{
  "id": "str",
  "name": "str",
  "role": "str",
  "kind": "character",
  "description": "str",
  "traits": ["str (max 8)"],
  "current_intent": "str",
  "recent_actions": ["str (max 5)"],
  "relationships": [{"target_id": "str", "kind": "str", "score": "float|null"} (max 8)],
  "personality": {"tone": "str", "archetype": "str", "style_tags": ["str"], "summary": "str"},
  "visual_identity": {"portrait_url": "str", "portrait_asset_id": "str", "seed": "int|null", "style": "str"},
  "meta": {"present": "bool", "speaker_order": "int", "source": "str"}
}
```

## Test Results

| Test Type | Count | Status |
|-----------|-------|--------|
| Unit | 20 | All passed |
| Functional | 5 | All passed |
| Regression | 8 | All passed |
| **Total** | **33** | **All passed** |

### Linting
- `ruff check`: Clean (0 errors after auto-fixing 3 unused imports)

## API Changes

### Existing Endpoints (Enhanced)
- `POST /api/rpg/presentation/scene` — Now includes `character_ui_state`
- `POST /api/rpg/presentation/dialogue` — Now includes `character_ui_state`
- `POST /narrative-recap` — Now includes `character_ui_state`

### New Endpoint
- `GET /api/rpg/character_ui` — Returns only `character_ui_state`

## Bounds Enforced
- `traits`: max 8
- `recent_actions`: max 5
- `relationships`: max 8

## Sorting
Characters are sorted by:
1. `meta.speaker_order` (ascending)
2. `name` (lowercase)
3. `id`

## Backward Compatibility
- Works with empty simulation state
- Works with missing `social_state`
- Works with missing `ai_state`
- Works with missing `personality_state`
- Does not modify existing speaker cards