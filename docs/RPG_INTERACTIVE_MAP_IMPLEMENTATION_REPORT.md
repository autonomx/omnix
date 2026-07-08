# RPG Interactive Map — MAP-0 through MAP-14 Implementation Report

## Scope

This branch implements the complete interactive RPG map roadmap on top of `rpg`. The result is a deterministic, server-authoritative map system with versioned content, live session overlays, interaction and movement gating, map hierarchy, curated assets, procedural settlement assembly, performance budgets, and save/load/replay validation.

The simulation and persisted session remain the source of truth. The frontend renders projections and submits typed actions; it does not infer world state or move the player optimistically.

## Architecture delivered

### Definition layer

`MapDefinition` provides stable, revisioned map content:

- logical bounds and coordinate space;
- optional ID-addressed background asset;
- objects with anchors, sprites, footprints, hitboxes, labels, descriptions, tags, and child maps;
- route geometry keyed by canonical route ID;
- labels and hierarchy metadata;
- deterministic integer coordinates and canonical SHA-256 revisions.

Definitions live in a repository and are validated for duplicate IDs, invalid geometry, out-of-bounds anchors, hierarchy references, and background mapping.

### Session overlay layer

`MapOverlay` and the dynamic overlay projection provide session-specific truth:

- active map and canonical current location;
- definition, overlay, and turn revisions;
- discovered and visible object IDs;
- route state and reasons;
- player, quest, danger, event, NPC, and resource markers;
- projected capabilities and disabled reasons;
- object conditions and bounded presentation hints;
- fog polygons;
- allowlisted weather, time, light, temperature, season, and visibility values.

Missing map state or unresolved location produces an unavailable overlay. No fallback marker is fabricated.

### Mutation layer

All map mutations use:

`POST /api/rpg/sessions/{session_id}/maps/{map_id}/map-actions`

The action core validates:

- definition and overlay revisions;
- object existence, discovery, and visibility;
- action capability;
- route identity, known/safe/status state, and authoritative reason;
- idempotent client action ID.

Safe travel updates canonical map/player location and overlay revision. Inspect is read-only. Enter switches map hierarchy state. Narrated or service-oriented actions return typed turn guidance instead of bypassing the existing RPG turn pipeline.

### Rendering layer

The web workspace includes one reusable React/SVG renderer for region, settlement, and interior maps:

- mouse drag, wheel zoom, touch drag, and pinch zoom;
- keyboard pan and zoom;
- bounded fit/reset controls and per-map viewport memory;
- deterministic layers for background, routes, structures, markers, labels, environment, and fog;
- polygon hitboxes independent from sprite visuals;
- pointer/keyboard tooltip parity;
- selection details and projected action controls;
- accessible text mirror of map objects;
- layer filters that never modify simulation state;
- truthful loading, empty, unavailable, stale, and error states;
- no optimistic player movement.

### Hierarchy

The starter content includes:

- Northern Pass region;
- Frost Haven settlement;
- Frosted Flagon interior.

Objects can reference child maps. Users may peek without mutation, enter through the authoritative action endpoint, navigate back through breadcrumbs, and restore per-map overlay state. The same renderer and contracts are reused at every level.

### Assets

The curated map pack is exposed through the shared asset library using stable IDs. It contains repository-controlled SVG backgrounds, structures, gates, towers, landmarks, and interior props.

Browser delivery uses:

`GET /api/assets/{asset_id}/file`

Delivery includes authoritative MIME type, content length, range support, ETag, Last-Modified, cache policy, inline/download disposition, and `nosniff`. SVG is accepted inline only when the repository asset is explicitly marked trusted. Map JSON and frontend state carry asset IDs rather than local paths or encoded file data.

The renderer keeps deterministic vector fallbacks, so missing or slow assets do not remove object labels, hitboxes, selection, or actions.

### Procedural settlement assembly

The settlement assembler uses a fixed custom 64-bit PRNG and integer coordinates. The seed is mixed with stable sorted graph identities. It creates:

- four zones;
- sixteen non-overlapping parcels;
- service-informed building roles;
- graph-derived gates and exit roads;
- stable labels, assets, IDs, geometry, and revisions;
- validation for bounds, collisions, counts, and building/parcel alignment.

The same seed and equivalent graph produce byte-identical canonical output regardless of input dictionary or route ordering.

### Performance decision

SVG remains the production baseline. A deterministic server decision gate measures canonical definition bytes, objects, routes, route points, labels, markers, and fog polygons. It returns explicit reasons when content exceeds the versioned SVG budget and should be promoted to a separately verified PixiJS renderer.

The frontend includes logical viewport culling helpers with bounded overscan and stable source ordering. Renderer choice never changes simulation or action truth.

### Persistence and replay

MAP-14 adds deterministic release validation:

- cleaned persisted map-state snapshot;
- save-state SHA-256 digest;
- replay-projection SHA-256 digest;
- JSON save/load round-trip verification;
- package export/import preservation through the package simulation group;
- exclusion of viewport, hover, focus, selection, and layer-filter state;
- detection of missing schema/map/location, unknown definition, unresolved location, and player/map mismatch.

## API surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/rpg/maps/{map_id}` | Cacheable immutable definition and revision. |
| GET | `/api/rpg/sessions/{session_id}/maps/{map_id}/overlay` | Live no-store session overlay. |
| POST | `/api/rpg/sessions/{session_id}/maps/{map_id}/map-actions` | Single authoritative map mutation entry point. |
| GET | `/api/assets/{asset_id}/file` | Browser-safe shared image delivery. |

## Compatibility

Older sessions without explicit canonical map state remain playable through existing RPG routes. Their map surface reports unavailable rather than inventing a location. New campaigns with an explicit starting location receive versioned `map_state`. Portable packages preserve map state without storing browser viewport data.

Existing turn, save, loadout, autoplay, checkpoint, report, narration, and Hermes workflows remain separate from the renderer. Completed turns and successful map actions refresh the authoritative session/overlay while unchanged definitions remain cached.

## Verification model

The implementation follows the requested phase gate:

1. Implement one MAP phase on `tmp-rpg-map` against `rpg`.
2. Wait for both required workflows on the exact phase head.
3. Patch the same branch if a workflow fails.
4. Advance only after both pass.

Required workflows:

- `RPG Phase 0 architecture compliance`
- `RPG deterministic PR gates`

GitHub Actions is the merge source of truth. The final MAP-14 head must pass both checks before the PR is eligible for merge.

## Known boundaries

- SVG is retained until measured representative content crosses the documented decision gate; PixiJS is not bundled speculatively.
- The curated assets are intentionally compact repository-controlled SVGs. Higher-detail art can replace them through the same immutable asset IDs or revisioned definitions.
- Existing legacy sessions are not migrated from display labels because doing so would violate the authoritative-ID rule.
- Peek mode is read-only and may show a child definition with an unavailable live overlay until the player enters it.
- The map does not expose hidden NPC schedules, future quest targets, unrestricted graph nodes, or private filesystem information.

## Result

MAP-0 through MAP-14 form a complete production foundation: deterministic content, live state, authoritative actions, reusable rendering, hierarchy, assets, procedural assembly, performance governance, accessibility, security, persistence, and replay validation. Future map content can be added through definitions and stable asset IDs without changing the simulation boundary or frontend action contract.
