# Phase 13 — Campaign Templates: Fixup Pass

**Date:** 2026-04-06 15:48
**Scope:** Restore missing exports, normalize character seeds, add `build_pack_bootstrap_payload`

## Issues Fixed

### 1. Missing creator package exports (`src/app/rpg/creator/__init__.py`)

**Problem:** The `__init__.py` was missing the module docstring, `from __future__ import annotations`, and all existing creator system exports (schema types, GM state types, validation, presenters). Only the Phase 13.2 pack authoring functions were exported.

**Fix:** Restored the full `__init__.py` with:
- Module docstring and `from __future__ import annotations`
- All existing creator system exports (schema, canon, gm_state, startup_pipeline, recap, commands, defaults, validation, presenters)
- Phase 13.2 additions (`build_pack_draft_export`, `build_pack_draft_preview`, `validate_pack_draft`)
- Complete `__all__` list with both existing and new exports

### 2. Missing `build_pack_bootstrap_payload` function (`src/app/rpg/modding/content_packs.py`)

**Problem:** The `build_pack_bootstrap_payload` function was referenced by `rpg_presentation_routes.py` (lines 1214, 1226) but was not defined in `content_packs.py`.

**Fix:** Added `build_pack_bootstrap_payload` function that:
- Calls `build_pack_application_preview` to get the pack preview
- Extracts manifest, scenario, world_seed, visual_defaults, and characters
- **Normalizes character seeds**: sorts by canonical name then format, caps at `_MAX_PACK_CHARACTERS` (64)
- Returns a deterministic bootstrap payload with title, summary, opening, world_seed, character_seeds, visual_defaults, and source_pack metadata

### 3. Character seed normalization in bootstrap payload

**Problem:** Character seeds from content packs were not sorted or bounded, leading to non-deterministic ordering and potential overflow.

**Fix:** In `build_pack_bootstrap_payload`, character seeds are now:
- Filtered to only dict items
- Sorted by `(canonical_seed.name.lower(), source_meta.format)`
- Capped at `_MAX_PACK_CHARACTERS` (64)

## Test Results

All 22 tests pass:
- **15 unit tests**: `test_pack_authoring.py` (3), `test_campaign_templates.py` (3), `test_content_packs.py` (9)
- **7 regression tests**: `test_phase129_packaging_modding_regression.py` (7)

## Files Changed

1. `src/app/rpg/creator/__init__.py` — Restored full module exports
2. `src/app/rpg/modding/content_packs.py` — Added `build_pack_bootstrap_payload` with character seed normalization