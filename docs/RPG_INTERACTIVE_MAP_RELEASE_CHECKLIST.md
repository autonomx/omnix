# RPG Interactive Map — Production Release Checklist

This checklist is the MAP-14 release gate for the interactive RPG map implementation on `tmp-rpg-map`, based against `rpg`.

## Phase completion

| Phase | Release evidence |
| --- | --- |
| MAP-0 | Architecture audit defines session truth, location-ID rules, route identity, asset delivery, replay, and redaction boundaries. |
| MAP-1 | Versioned definition/overlay contracts, canonical serialization, stable revisions, polygons, route IDs, direction, and lossless statuses. |
| MAP-2 | Deterministic curated region and settlement definitions with validated objects, routes, labels, and hierarchy references. |
| MAP-3 | Cache-aware definition endpoint and no-store session overlay endpoint with typed unavailable states. |
| MAP-4 | Live React/SVG renderer, dialog shell, truthful player marker, loading/error/unavailable states. |
| MAP-5 | Mouse, touch, pinch, wheel, keyboard pan/zoom, bounded transforms, per-map viewport memory. |
| MAP-6 | Authoritative polygon hitboxes, pointer/keyboard parity, tooltips, selection details, accessible object list. |
| MAP-7 | Routes, labels, player/quest/danger/event/NPC/resource markers, and presentation-only layer filters. |
| MAP-8 | Discovery, visibility, object state, fog, weather/light/visibility overlays, polling refresh, stale revision handling. |
| MAP-9 | Single authoritative map-action endpoint, revision checks, route gating, idempotency, no optimistic movement. |
| MAP-10 | Region/settlement/interior hierarchy, reusable renderer, peek/enter/back, overlay restoration, breadcrumbs. |
| MAP-11 | Curated shared asset pack, ID-only browser URLs, trusted SVG policy, ETag/Last-Modified/range delivery, vector fallbacks. |
| MAP-12 | Stable seeded settlement assembler, graph-derived gates/routes, parcels/zones, bounds and collision validation. |
| MAP-13 | Measured SVG budget decision gate, deterministic viewport culling helper, documented PixiJS promotion criteria. |
| MAP-14 | Save/load/package/replay digests, release validation, accessibility and final integration coverage. |

## Authoritative state and integrity

- [x] Current map and location use canonical IDs in `state.map_state`.
- [x] Display labels are never used to infer authoritative IDs.
- [x] Missing or unresolved position returns a typed unavailable overlay without a fabricated marker.
- [x] Definition and overlay revisions are validated before every mutation.
- [x] Route identity uses stable route IDs and preserves open, blocked, locked, unknown, safe, and known state.
- [x] Parallel and one-way route semantics are supported by the graph contract.
- [x] Browser viewport, hover, focus, selection, and layer-filter state are excluded from persisted map truth.
- [x] Map actions return the saved session/game envelope and a freshly projected overlay.
- [x] Repeated client action IDs are idempotent.

## Save, load, package, and replay

- [x] Durable JSON save/load preserves the deterministic map-state group.
- [x] Portable package export stores a cleaned map-state snapshot under the package simulation group.
- [x] Portable package import restores map state, canonical current location, and player location.
- [x] Save-state and replay-projection SHA-256 digests are deterministic.
- [x] Authoritative movement changes the persisted and replay digests.
- [x] UI-only viewport/selection changes do not change persisted digests.
- [x] Release validation detects missing schema, missing map/location IDs, unknown definitions, unresolved locations, and player/map mismatches.

## API and cache behavior

- [x] `GET /api/rpg/maps/{map_id}` returns immutable revisioned definitions.
- [x] Conditional definition requests support ETag and 304 responses.
- [x] `GET /api/rpg/sessions/{session_id}/maps/{map_id}/overlay` is session-specific and `no-store`.
- [x] `POST /api/rpg/sessions/{session_id}/maps/{map_id}/map-actions` is the only map mutation entry point.
- [x] `GET /api/assets/{asset_id}/file` delivers map images by stable asset ID.
- [x] Asset delivery provides MIME, content length, range support, ETag, Last-Modified, cache policy, and `nosniff`.
- [x] Inline SVG delivery is restricted to repository-curated assets marked `trusted_svg`.
- [x] API payloads do not expose local storage paths.

## UI states and interaction

- [x] Loading, definition error, overlay error, empty definition, empty overlay, unavailable, stale, and action-rejected states are visible.
- [x] The player marker is rendered only from a ready authoritative overlay.
- [x] Map actions do not optimistically move the player marker.
- [x] Pointer hover and keyboard focus expose the same object details.
- [x] Hitboxes are separate from visual sprite geometry.
- [x] Disabled capabilities expose a reason and cannot be submitted.
- [x] Peek is non-mutating; Enter uses the authoritative action route.
- [x] Parent/child map views reuse the same renderer and restore per-map overlays.
- [x] Layer toggles are presentation-only.
- [x] Asset failure retains vector fallback geometry and usable object labels.

## Accessibility

- [x] The map dialog has an accessible name and modal semantics.
- [x] Initial focus moves to the dialog close control.
- [x] Escape closes the dialog and focus returns to the prior opener on unmount.
- [x] The viewport is keyboard focusable and documents keyboard shortcuts.
- [x] Arrow keys pan; plus/minus zoom; Home/0 fits the map.
- [x] Interactive objects are focusable, named, and operable with Enter or Space.
- [x] A full text list mirrors visible/discovered map objects for screen-reader and keyboard navigation.
- [x] Reduced-motion media rules disable nonessential map transitions and event pulsing.
- [x] Selected objects and layer controls use native buttons, checkboxes, labels, and pressed/disabled states.

## Security and redaction

- [x] Undiscovered objects are absent from object-state projection.
- [x] Non-visible objects cannot be mutated.
- [x] Hidden schedules, future events, internal graph nodes, and unrestricted NPC state are not copied into map responses.
- [x] Map environment projection uses an explicit allowlist.
- [x] Object presentation hints are bounded.
- [x] Asset IDs reject paths, traversal strings, backslashes, and data URLs in the browser resolver.
- [x] Server file errors use typed identifiers and do not return filesystem paths.

## Performance and renderer decision

- [x] Canonical definition size, object, route, route-point, label, marker, and fog counts are measured.
- [x] Starter maps remain inside the versioned SVG budget.
- [x] Over-budget content receives explicit PixiJS recommendation reasons.
- [x] Culling uses inverse logical viewport bounds with deterministic overscan and preserves source ordering.
- [x] Renderer choice cannot affect simulation or action truth.
- [x] PixiJS remains deferred until representative measured content exceeds the documented promotion threshold.

## Verification and rollout

- [x] Each MAP phase advances only after both required GitHub Actions workflows pass on that exact phase head:
  - `RPG Phase 0 architecture compliance`
  - `RPG deterministic PR gates`
- [x] The final MAP-14 head must also pass both workflows before merge.
- [x] The PR remains reviewable as one branch against `rpg` with narrow phase commits.
- [x] No local verification is claimed unless it was actually executed; GitHub Actions is the required merge evidence.

## Rollback

The map feature is modular and can be rolled back without changing simulation truth:

1. Remove the live map launcher/dialog from the RPG world rail.
2. Leave session `map_state` untouched so saves remain forward-compatible.
3. Disable registration of `rpg_map_routes` while keeping ordinary RPG session and turn routes active.
4. Retain shared map assets; they are immutable, ID-addressed, and harmless when unused.
5. Re-enable the map with the same definition and overlay revisions after the defect is corrected.

A rollback must never rewrite canonical player location from display labels or delete persisted discovery/route/object state.
