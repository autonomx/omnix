# RPG Phase 13 — Campaign Templates & Pack Authoring

**Date:** 2026-04-06 15:34  
**Status:** Implemented & Tested

## Summary

This phase implements three sub-phases from the RPG design document:

### Phase 13.1 — Scenario Packs + Start-from-Pack Flow
- Added `build_pack_bootstrap_payload()` to `content_packs.py`
- Created `/api/rpg/packs/bootstrap` route for deterministic bootstrap payload generation
- Created `/api/rpg/packs/start` route for new-session setup from content pack

### Phase 13.2 — Creator Pack Authoring / Validation / Preview
- Created `src/app/rpg/creator/pack_authoring.py` with:
  - `validate_pack_draft()` — validates manifest id/title, character limits, visual defaults
  - `build_pack_draft_export()` — exports validated draft as content pack payload
  - `build_pack_draft_preview()` — previews draft with full application simulation
- Created `/api/rpg/creator/pack/validate` route
- Created `/api/rpg/creator/pack/preview` route
- Created `/api/rpg/creator/pack/export` route

### Phase 13.3 — Campaign Template / Adventure Bootstrap
- Created `src/app/rpg/templates/campaign_templates.py` with:
  - `build_campaign_template()` — creates reusable adventure templates
  - `build_template_start_payload()` — generates start-session payload from template
  - `list_campaign_templates()` — normalizes/sorts templates (max 32)
- Created `/api/rpg/templates/build` route
- Created `/api/rpg/templates/start` route
- Created `/api/rpg/templates/list` route

## Files Changed

### New Files
- `src/app/rpg/creator/pack_authoring.py` — Pack authoring validation, export, preview
- `src/app/rpg/templates/__init__.py` — Templates module init
- `src/app/rpg/templates/campaign_templates.py` — Campaign template builder
- `src/tests/unit/rpg/test_pack_authoring.py` — Unit tests for pack authoring (3 tests)
- `src/tests/unit/rpg/test_campaign_templates.py` — Unit tests for campaign templates (3 tests)

### Modified Files
- `src/app/rpg/modding/content_packs.py` — Added `build_pack_bootstrap_payload()`
- `src/app/rpg/creator/__init__.py` — Added pack_authoring exports
- `src/app/rpg/api/rpg_presentation_routes.py` — Added 6 new routes

## Test Results

All 6 unit tests passing:
```
test_pack_authoring.py::test_validate_pack_draft_requires_manifest_id_and_title PASSED
test_pack_authoring.py::test_build_pack_draft_export_includes_validation PASSED
test_pack_authoring.py::test_build_pack_draft_preview_contains_preview PASSED
test_campaign_templates.py::test_build_campaign_template_basic PASSED
test_campaign_templates.py::test_build_template_start_payload_basic PASSED
test_campaign_templates.py::test_list_campaign_templates_sorted PASSED
```

## API Routes Added

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/rpg/packs/bootstrap` | POST | Generate deterministic bootstrap payload from content pack |
| `/api/rpg/packs/start` | POST | Start new session from content pack |
| `/api/rpg/creator/pack/validate` | POST | Validate pack draft |
| `/api/rpg/creator/pack/preview` | POST | Preview pack draft |
| `/api/rpg/creator/pack/export` | POST | Export pack draft as content pack |
| `/api/rpg/templates/build` | POST | Build campaign template |
| `/api/rpg/templates/start` | POST | Start session from template |
| `/api/rpg/templates/list` | POST | List available templates |

## Diff File

See: `rpg-phase13-campaign-templates-20260406-1534.diff`