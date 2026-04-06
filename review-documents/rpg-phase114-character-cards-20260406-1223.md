# Phase 11.4 — Character Cards + Portraits

**Date:** 2026-04-06 12:23  
**Status:** Implemented

## Goal

Upgrade canonical character UI objects into full card-ready entities with portrait metadata and UI rendering.

This phase does not generate images yet. It prepares:
- portrait slots
- visual identity projection
- richer card display
- stable future hook for image generation

---

## Files Changed

### Modified Files

| File | Changes |
|------|---------|
| `src/app/rpg/ui/character_builder.py` | Added `_normalize_card_meta()` helper and "card" field |
| `src/static/rpg/rpgPresentationRenderer.js` | Enhanced character card rendering with portrait, subtitle, badge, summary |
| `src/static/rpg/rpgInspectorStyles.css` | Added portrait, badge, summary CSS styles |
| `src/tests/unit/rpg/test_character_builder.py` | Added test for card metadata |

---

## Implementation Details

### 1. Card Metadata Helper (`src/app/rpg/ui/character_builder.py`)

**New function:**
```python
def _normalize_card_meta(entry: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subtitle": _first_non_empty(
            entry.get("title"),
            entry.get("role"),
            profile.get("archetype"),
        ),
        "summary": _first_non_empty(
            entry.get("description"),
            profile.get("summary"),
        ),
        "badge": _first_non_empty(
            entry.get("faction"),
            entry.get("group"),
        ),
    }
```

**Each character now has:**
```json
"card": {
    "subtitle": "string",
    "summary": "string",
    "badge": "string"
}
```

### 2. Frontend Rendering (`src/static/rpg/rpgPresentationRenderer.js`)

**Enhanced character card template:**
- Added portrait image slot (with placeholder support)
- Shows subtitle instead of plain role
- Renders badge when available
- Renders summary text when available
- Maintains existing intent display

### 3. CSS Styles (`src/static/rpg/rpgInspectorStyles.css`)

**New CSS classes:**
- `.inspector-character-portrait` → 64x64px portrait with rounded corners
- `.inspector-character-portrait--placeholder` → Subtle background placeholder
- `.inspector-character-badge` → Rounded pill with accent tint
- `.inspector-character-summary` → Secondary text for character summary

---

## Test Coverage

### Unit Tests

| Test | Coverage |
|------|----------|
| `test_build_character_ui_entry_includes_card_meta` | Verifies card field with subtitle, summary, badge |

---

## Acceptance Criteria

- [x] Canonical character UI includes card metadata
- [x] Character list renders portrait slot, subtitle, summary, badge
- [x] No image generation is required yet
- [x] Portrait placeholder is stable and ready for future image generation