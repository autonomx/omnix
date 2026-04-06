# Phase 12 — Visual Identity System

**Date:** 2026-04-06 12:37
**Status:** Implemented

## Summary

Implements a visual identity layer for the RPG presentation system, providing:

1. **Character Portrait Management** — deterministic seed-based portrait requests with version tracking
2. **Scene Illustration Tracking** — bounded list (max 24) of scene illustrations with status lifecycle
3. **Image Request Queue** — bounded list (max 24) of pending/completed image generation requests
4. **API Endpoints** — four new routes for requesting and completing character portraits and scene illustrations

## Files Changed

### New Files
- `src/app/rpg/presentation/visual_state.py` — Core visual state module (248 lines)
- `src/tests/unit/rpg/test_phase12_visual_identity.py` — Unit tests (18 tests)

### Modified Files
- `src/app/rpg/api/rpg_presentation_routes.py` — Added 4 new API endpoints + visual state extraction

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/rpg/character_portrait/request` | POST | Create/update portrait generation request |
| `/api/rpg/character_portrait/result` | POST | Record completed portrait asset |
| `/api/rpg/scene_illustration/request` | POST | Create scene illustration request |
| `/api/rpg/scene_illustration/result` | POST | Record completed scene illustration |

## Key Design Decisions

- **Deterministic seeds** — `stable_visual_seed_from_text()` uses SHA-256 for reproducible image generation
- **Bounded lists** — scene_illustrations and image_requests capped at 24 items (FIFO eviction)
- **Version tracking** — character visual identities increment version on each update
- **Status lifecycle** — idle → pending → complete for all visual assets
- **Safe extraction** — `_safe_visual_state()` ensures malformed data is normalized to defaults

## Test Results

```
18 passed in 0.16s
```

All unit tests pass covering:
- `ensure_visual_state` normalization and idempotency
- `build_default_character_visual_identity` determinism
- Stable seed generation (deterministic, different for different text)
- Upsert character visual identity (create and overwrite)
- Bounded append for scene illustrations and image requests (max 24)
- Normalization defaults for all entry types
- Safe string/int helpers