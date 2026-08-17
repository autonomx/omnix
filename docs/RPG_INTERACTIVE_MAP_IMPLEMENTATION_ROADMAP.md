# RPG Interactive Map implementation roadmap

## Goal

Deliver a deterministic, data-driven RPG map that supports smooth pan and zoom, hover and keyboard focus details, selectable buildings and landmarks, route visualization, live world-state overlays, fog of war, and drill-down from region to settlement to interior maps.

The target interaction is the reference behavior reviewed for Frost Haven:

- a parchment or terrain background;
- independently rendered buildings, trees, landmarks, labels, and roads;
- smooth zooming and panning of one shared scene container;
- hover/focus cards for map objects;
- click-to-select and explicit actions such as **Travel**, **Inspect**, or **Enter**;
- a larger full-map view in addition to the compact RPG world rail;
- dynamic markers and state changes without regenerating the entire map image.

## Current foundation

The RPG already has useful pieces that should be extended rather than replaced:

- `src/app/rpg/world_graph.py` defines deterministic location nodes, routes, discovery stubs, and safe-route instant-travel decisions.
- `src/app/rpg/world_runtime.py` adapts saved runtime state into the world graph and exposes report-oriented map metadata. It is a report adapter, not yet a production-authoritative map projection.
- `src/apps/web/src/features/rpg/RpgWorldRail.tsx` has a compact map card, but live sessions currently expose only a location placeholder rather than an interactive map.
- `src/apps/web/public/rpg/glimmerdeep-pass-map.svg` proves that static SVG map art is already supported.
- The shared Image Generation Workspace can create and persist image assets that a later map-art pipeline can reuse.

The missing layer is a canonical renderable map document, a lossless authoritative projection, cacheable definition and overlay resources, and a frontend renderer bound to current RPG state.

## Primary technical decision

### Use React + SVG for the first production map renderer

The first renderer should use an SVG scene inside the existing React application, not PixiJS immediately.

SVG is the better first fit because the initial settlement and region maps will contain tens or low hundreds of interactive objects, and SVG provides:

- native paths for roads, borders, rivers, labels, footprints, and explicit hit polygons;
- simple pointer, focus, and keyboard events;
- DOM-based accessibility and testability;
- deterministic screenshots and straightforward Vitest/Playwright coverage;
- no new rendering dependency for the MVP;
- easy composition with regular HTML tooltips and action panels.

The scene is still structured like a game renderer. A single transformed viewport contains background, terrain, routes, props, structures, labels, and overlays. Zooming and panning transform the parent viewport rather than moving every object independently.

Use the existing frontend stack intentionally:

- React Query for definition and overlay retrieval and revision-aware invalidation;
- local component state or a small Zustand store keyed by `map_id` for viewport restoration;
- one SVG `viewBox` and one transformed scene group;
- HTML for hover cards and persistent selected-object action panels;
- a parallel accessible object/action list for keyboard and screen-reader use.

PixiJS remains an explicit later performance option. It should be adopted only if measured production scenes exceed the SVG budget, such as more than roughly 500 simultaneously visible sprites, sustained animation layers, particles, or unacceptable frame times on supported hardware.

## Architecture boundaries

### Simulation owns truth

The deterministic simulation owns:

- locations and their relationships;
- canonical route identity, direction, state, and travel eligibility;
- discovery and visibility;
- ownership, services, occupants, damage, closure, and danger state;
- current player location;
- map revision and save/load state.

The frontend never mutates world state because an icon was clicked. Selection and mutation remain separate.

All map mutations use one authoritative entry point:

```text
POST /api/rpg/sessions/{session_id}/map-actions
```

The server converts the typed map action into the normal authoritative RPG intent/mutation flow. Internally, the server may resolve a known safe route without narration, but it still returns the normal turn/session mutation envelope. The frontend never chooses between a fast travel resolver and a normal RPG turn.

### AI owns presentation assistance, not authority

AI may generate or suggest:

- map and settlement names;
- descriptions and hover-card prose;
- visual style prompts;
- background or object artwork;
- high-level settlement themes and candidate landmarks.

AI must not directly decide authoritative coordinates, travel success, discovery, route state, or object existence on each turn. Any optional AI-authored layout proposal must pass a typed schema and a deterministic placement/validation step before persistence.

## Route identity prerequisite

The current endpoint-pair route identity is insufficient for production maps. Before authoritative map actions are implemented, `RpgRoute` must gain a canonical stable ID and explicit direction.

Target shape:

```python
@dataclass(frozen=True)
class RpgRoute:
    id: str
    from_id: str
    to_id: str
    direction: Literal["both", "forward"] = "both"
    status: Literal["open", "blocked", "locked"] = "open"
    safe: bool = True
    known: bool = True
    tags: tuple[str, ...] = ()
```

Requirements:

- route identity is `route.id`, not an unordered endpoint pair;
- `with_route()` replaces by route ID;
- parallel routes between the same locations are allowed;
- one-way routes are represented without inventing duplicate reverse records;
- route overlays, route geometry, actions, logs, save/load, and replay reference the same canonical route ID;
- route statuses are parsed and projected losslessly, including `locked`;
- unknown future statuses must produce a typed compatibility error rather than silently becoming `blocked`.

## Production projection correctness

Report-oriented convenience behavior must not leak into the production map projection.

The map projection must never:

- collapse `locked` or unknown route states into `blocked`;
- fall back to the alphabetically first graph location when current location is missing;
- place the player marker from preview data in a live session;
- infer discovery, visibility, ownership, or accessibility from presentation labels;
- expose undiscovered descriptions, quest internals, or hidden NPC state.

Missing or invalid authoritative location state returns a typed unavailable/error projection. The map may still render a definition without a player marker, but the response must state why the live overlay is unavailable.

## Canonical data split

The map is separated into three independently cacheable state groups.

### 1. Map definition

Stable geometry and visual references:

- logical bounds and coordinate system;
- background asset reference and exact coordinate mapping;
- object positions, anchors, footprints, hitboxes, and render order;
- route and river paths;
- labels and map hierarchy;
- parent/child map relationships.

### 2. Map overlay snapshot

Session-specific dynamic state:

- current player marker;
- discovered and visible objects;
- quest, NPC, enemy, resource, and event markers;
- open, blocked, locked, dangerous, or unknown routes;
- building status such as open, closed, damaged, burned, or occupied;
- fog-of-war masks;
- weather, season, light, and hazard presentation hints;
- action capabilities and disabled reasons.

### 3. Viewport state

Browser-local presentation state:

- zoom;
- pan offset;
- selected object;
- open layer filters;
- last viewed map level.

Viewport state must not be written into authoritative RPG saves unless a future user-preference feature explicitly requires it.

## Cacheable resource model

Use two canonical conceptual resources:

```text
GET /api/rpg/maps/{map_id}
GET /api/rpg/sessions/{session_id}/maps/{map_id}/overlay
```

A combined convenience response is allowed, but it must preserve independent revision semantics:

```json
{
  "map_id": "settlement:frost_haven",
  "definition_revision": "sha256:4bfe...",
  "overlay_revision": 184,
  "session_turn_index": 73,
  "definition": null,
  "overlay": {}
}
```

Rules:

- `definition_revision` is content-addressed or otherwise stable for identical deterministic serialization;
- `overlay_revision` is monotonic within the session/map projection;
- `session_turn_index` identifies the authoritative turn used to build the overlay;
- the definition may be omitted when the client declares that it already has the same revision;
- overlay refreshes after a turn must not repeatedly return static buildings, paths, and labels;
- stale or mismatched definition/overlay revisions produce typed recovery metadata;
- cache headers and ETags should be used where the gateway architecture permits them.

## Coordinate and geometry model

Use integer logical coordinates independent of image resolution. A map can define bounds such as `10000 x 6000`, while the browser scales those coordinates into any viewport size.

This avoids coupling saved world state to a particular PNG or screen resolution and gives deterministic layout, route, hitbox, and replay behavior.

Pseudo-isometric visuals remain ordinary 2D sprites. Each object uses a declared anchor, normally bottom-center.

### Render order

Do not persist a free-form `z_index` that can disagree with `y`.

Use a stable render-order tuple:

```json
{
  "render_order": {
    "layer": "structures",
    "sort_y": 4310,
    "offset": 0
  }
}
```

Default ordering is:

```text
(layer priority, sort_y, offset, object_id)
```

`sort_y` defaults to the anchor's logical Y coordinate. `offset` is reserved for exceptional overlaps and must remain bounded.

### Background mapping

The background must map exactly to logical bounds or declare explicit source-crop metadata. A CSS-like `cover` mode is forbidden for authoritative geometry because cropping would desynchronize the image from object coordinates.

Supported forms:

- exact stretch/map to the declared logical bounds; or
- explicit `source_crop` plus destination logical bounds.

### Footprint and hitbox

Each placed object may define two different local-coordinate polygons:

- `footprint`: layout, parcel spacing, route clearance, and future collision constraints;
- `hitbox`: pointer, focus, and selection interaction.

Both are object-local coordinates relative to the declared anchor.

Polygon rules:

- points use integer logical coordinates;
- polygons are normalized to clockwise winding during validation;
- self-intersections are rejected;
- duplicate closing points are removed during normalization;
- points on an edge count as inside for hit testing;
- empty or degenerate polygons are rejected for interactive objects;
- a generated sprite's transparent pixels never define authoritative interaction geometry.

## Proposed contracts

```json
{
  "schema_version": 1,
  "map_id": "settlement:frost_haven",
  "level": "settlement",
  "definition_revision": "sha256:4bfe...",
  "seed": 824193,
  "parent_map_id": "region:northern_pass",
  "bounds": { "width": 10000, "height": 6000 },
  "background": {
    "asset_id": "asset_map_frost_haven_base",
    "destination_bounds": { "x": 0, "y": 0, "width": 10000, "height": 6000 },
    "source_crop": null
  },
  "objects": [
    {
      "id": "building:frost_haven_inn",
      "location_id": "frost_haven_inn",
      "kind": "building",
      "x": 2870,
      "y": 4310,
      "anchor": "bottom_center",
      "render_order": {
        "layer": "structures",
        "sort_y": 4310,
        "offset": 0
      },
      "sprite": {
        "asset_id": "asset_sprite_timber_inn_01",
        "width": 620,
        "height": 540
      },
      "footprint": {
        "kind": "polygon",
        "points": [[-240, -95], [240, -95], [240, 90], [-240, 90]]
      },
      "hitbox": {
        "kind": "polygon",
        "points": [[-270, -180], [270, -180], [250, 80], [-250, 80]]
      },
      "child_map_id": "interior:frost_haven_inn"
    }
  ],
  "route_geometry": [
    {
      "route_id": "route:west_gate_to_market:main_road",
      "points": [[650, 4480], [2100, 4210], [4050, 3560]],
      "style": "road"
    }
  ],
  "labels": [
    {
      "id": "label:frost_haven",
      "text": "FROST HAVEN",
      "x": 5250,
      "y": 2870,
      "priority": 100
    }
  ]
}
```

The map definition references the canonical route ID. It does not create a second map-only identity from route endpoints.

The dynamic overlay is returned separately and references stable map-object and canonical route IDs.

## Asset delivery prerequisite

Asset listing or JSON content records are not sufficient proof of an efficient browser image-serving path.

MAP-0 must confirm or add a raw binary route such as:

```text
GET /api/assets/{asset_id}/raw
```

Required behavior:

- return raw bytes with the authoritative MIME type;
- expose no local filesystem path;
- support `ETag`, `Cache-Control`, and `Content-Length` where available;
- use safe inline disposition for browser-renderable map assets;
- reject unsupported or mismatched MIME types;
- support conditional requests;
- add range/streaming behavior when measured asset sizes justify it;
- preserve the existing stable asset-ID security and retention boundaries.

The map JSON contains asset IDs and dimensions, never data URLs or encoded image bytes.

## Canonical runtime flow

```text
Authoritative RPG session state
  -> canonical RpgRegionGraph with route IDs
  -> versioned map definition repository
  -> lossless deterministic overlay projection
  -> GET /api/rpg/maps/{map_id}
  -> GET /api/rpg/sessions/{session_id}/maps/{map_id}/overlay
  -> React Query definition + overlay caches
  -> SVG scene layers
  -> HTML hover card / selected-object panel
  -> POST /api/rpg/sessions/{session_id}/map-actions
  -> authoritative RPG intent and normal mutation envelope
  -> updated session, turn index, and overlay revision
```

Large generated image bytes are served by asset ID through the raw binary route, not embedded in session JSON or returned as filesystem paths.

## Map action contract

All object and travel actions use the same endpoint.

Example request:

```json
{
  "action_id": "map-action:8bbd...",
  "map_id": "settlement:frost_haven",
  "definition_revision": "sha256:4bfe...",
  "overlay_revision": 184,
  "type": "travel",
  "target_object_id": "gate:frost_haven_west",
  "target_location_id": "frost_haven_west_gate",
  "route_id": "route:market_to_west_gate:main_road"
}
```

Rules:

- the server validates map, definition, overlay, object, location, and route identity;
- stale revisions return a typed conflict with the newest projection metadata;
- `action_id` provides idempotency within the normal mutation boundary;
- the server determines whether narration is required;
- the response is the normal authoritative RPG turn/session mutation envelope plus refreshed map projection metadata;
- the frontend never performs optimistic travel or locally moves the authoritative player marker;
- decorative, hidden, unavailable, or disabled objects cannot create mutation intents.

## Rendering layers

Render layers in a stable order:

1. background plate;
2. terrain masks and water;
3. roads, trails, rivers, and borders;
4. ground props and vegetation;
5. buildings and landmarks;
6. NPC, party, enemy, resource, quest, and event markers;
7. labels;
8. fog of war and discovery masks;
9. selection, hover, route preview, and accessibility overlays.

Each layer can be toggled without changing authoritative state.

## Hover, focus, and click behavior

- Every interactive object has an explicit hitbox; transparent sprite pixels are not used as authoritative hit detection.
- Pointer hover and keyboard focus show the same HTML detail card.
- The detail card is anchored to the object's projected screen position and clamped inside the viewport.
- Clicking selects an object and opens a persistent details/action panel.
- Selection never immediately changes location.
- **Travel**, **Inspect**, **Talk**, **Trade**, and **Enter** are explicit actions governed by server-projected capabilities and disabled reasons.
- A non-visual list of visible locations and actions is available for keyboard and screen-reader users.

## Multi-scale map hierarchy

Use the same contracts and renderer for three map levels:

```text
World / region map
  -> settlement or dungeon map
    -> building, room, or encounter map
```

A building can reference `child_map_id`. Selecting **Peek inside** or **Enter** loads the child map without inventing a second interaction system. Interior maps may use background artwork with hotspot objects first; they do not need a full tactical grid in the MVP.

## Image-generation strategy

Image generation should enhance the map without owning its runtime structure.

### First release

Use a small curated starter asset pack:

- parchment and terrain textures;
- house, inn, smithy, shop, shrine, tower, ruin, gate, and camp sprites;
- tree and rock clusters;
- player, quest, danger, NPC, and event markers.

This keeps the renderer and world-state integration testable before introducing art-generation variability.

### Generated art phase

Use the existing shared image job and asset system to create persistent visual assets:

- region background plates;
- settlement terrain plates;
- building and landmark variants;
- interior scene plates;
- optional portrait and item art already used by RPG surfaces.

Generated art is created once, stored as an asset, and referenced by stable asset ID. It is not regenerated because an NPC moves or a quest changes.

Reference-image conditioning should be used to preserve a consistent map style. Generated object sprites should not enter production until the pipeline can reliably crop them, preserve transparency or an agreed mask color, record dimensions and anchors, and pass a visual validation step.

### Procedural assembly

The long-term living-world approach is modular:

```text
World graph + deterministic seed + style profile
  -> deterministic layout generator
  -> roads, parcels, zones, and object placements
  -> map definition revision
  -> curated or generated asset references
```

The simulation can then add a camp, replace an inn with ruins, close a gate, reveal a route, or expand a town without regenerating the entire background.

## Implementation phases

| Phase | Scope | Exit condition |
| --- | --- | --- |
| MAP-0 | Architecture audit, location truth, asset delivery, and canonical roadmap | Actual save groups, current-location truth, report-era coercions, session refresh behavior, asset raw delivery, and API adoption points are documented; no placeholder behavior is mistaken for live state. |
| MAP-1 | Typed map contracts, route identity, revisions, and geometry | Versioned definitions/overlays, canonical route IDs/direction, lossless statuses, deterministic serialization, footprints, hitboxes, render order, and hierarchy contracts exist with focused tests. |
| MAP-2 | Map repository and deterministic starter definitions | A repository loads definitions by map ID; one region and one settlement map use logical coordinates, stable IDs, and raw asset references. |
| MAP-3 | Cacheable definition and session overlay APIs | Separate bounded resources return definition and overlay revisions, turn index, capabilities, unavailable states, and asset IDs. |
| MAP-4 | React map shell and full-map surface | The RPG world rail opens a responsive full-map view with loading, empty, unavailable, stale, and error states grounded in live session data. |
| MAP-5 | Pan, zoom, reset, fit, keyboard, and touch controls | One transformed viewport supports wheel/pinch zoom, drag pan, keyboard controls, bounded zoom, fit-to-map, and reduced-motion behavior. |
| MAP-6 | Interactive objects, footprints, hitboxes, hover/focus cards, and selection | Buildings and landmarks render from data; hover, focus, click, tooltip clamping, selected state, and accessible object list are covered. |
| MAP-7 | Roads, labels, markers, and layer controls | Canonical route geometry, settlement labels, player position, quest/danger/event markers, and user layer filters render deterministically. |
| MAP-8 | Discovery, fog, environment, and live overlay refresh | Hidden/known/discovered/visible states, fog masks, lossless route status, weather/light hints, and turn-driven overlay refresh are wired to saved state. |
| MAP-9 | Single-entry authoritative map actions | `POST .../map-actions` handles travel and object actions through the normal mutation envelope; blocked, unsafe, unknown, locked, stale, and expansion-required cases are truthful. |
| MAP-10 | Region, settlement, and interior drill-down | Parent/child maps, breadcrumbs, **Peek inside**, **Enter**, back navigation, and per-level viewport restoration work without duplicating render logic. |
| MAP-11 | Curated asset pack and generated-art integration | Starter sprites are production-ready; generated backgrounds/sprites use raw shared asset delivery, style metadata, caching, validation, and safe fallbacks. |
| MAP-12 | Deterministic procedural settlement assembler | A seed and world graph produce stable roads, zones, parcels, labels, footprints, and placements; regeneration with the same inputs is byte-for-byte stable. |
| MAP-13 | Performance budget and PixiJS decision gate | Scene profiling records object count, frame time, memory, interaction latency, and texture cost; PixiJS is adopted only if the documented SVG budget is exceeded. |
| MAP-14 | Save/load, replay, accessibility, and release gate | Map revisions, discovery, canonical route state, hierarchy, and object changes survive save/load and deterministic replay; full end-to-end and accessibility gates pass. |

## Early vertical-slice delivery order

The first implementation work should produce a live screenshot before completing every repository and geometry feature.

### MAP-0 — Audit

- Inventory actual current map/world fields emitted by live RPG sessions.
- Document the authoritative source of current location, routes, discovered locations, environment snapshot, and save groups.
- Identify and isolate report-era fallback behavior, especially current-location fallback and route-status coercion.
- Confirm or design `GET /api/assets/{asset_id}/raw` with MIME, cache, conditional request, and path-redaction behavior.
- Record the current RPG query refresh and mutation envelope after a turn.
- Add no runtime behavior in this slice.

### MAP-1A — Definition and overlay contracts

Add versioned definition/overlay contracts, stable object IDs, definition and overlay revisions, session turn index, typed unavailable/error states, and deterministic serialization.

Suggested focused modules:

- `src/app/rpg/map_contracts.py`
- `src/app/rpg/map_serialization.py`
- `src/tests/rpg/test_map_contracts.py`
- `src/tests/rpg/test_map_serialization.py`

### MAP-1B — Canonical route upgrade

Upgrade `RpgRoute` and all direct consumers:

- stable route ID;
- explicit direction;
- lossless `open`, `blocked`, and `locked` status;
- replacement by ID rather than endpoint pair;
- parallel-route and one-way-route tests;
- save/load and runtime adapter compatibility;
- no alphabetical current-location fallback in production projection.

This slice is a prerequisite for mutable route overlays and map actions.

### MAP-2A — Tiny deterministic settlement fixture

Create one deliberately small settlement fixture containing roughly 8-12 objects:

- one background;
- one main road and one secondary path;
- four to six buildings;
- one gate or landmark;
- one settlement label;
- one player marker projection;
- one quest or danger marker.

Use curated SVG/PNG assets so runtime wiring does not depend on generated art.

### MAP-3A — Read-only live endpoints

Implement:

```text
GET /api/rpg/maps/{map_id}
GET /api/rpg/sessions/{session_id}/maps/{map_id}/overlay
```

Include definition/overlay revisions, turn index, typed unavailable states, redaction, and raw asset URLs or asset IDs. Do not implement mutation yet.

### MAP-4A — Live SVG shell

Open the tiny fixture from a live RPG session in a responsive full-map surface using React Query, one SVG `viewBox`, and one transformed scene group.

The initial shell should already demonstrate:

- live location truth;
- loading/unavailable/error states;
- background and object placement;
- stable layer ordering;
- current player marker only when authoritative state is valid.

This is the first screenshot milestone.

### MAP-1C — Geometry hardening

After the live shell exists, complete:

- footprint and hitbox normalization;
- polygon winding, edge, and degeneracy rules;
- render-order derivation and bounded overrides;
- exact background coordinate mapping;
- child-map and asset-reference validation;
- out-of-bounds and duplicate-ID rejection.

### MAP-2B — Expand the fixture and repository

Expand the settlement to roughly 20-40 objects, add the first region definition, and complete repository versioning, migration, lookup, and deterministic hashing.

## MAP-3 production API details

The browser must not receive:

- absolute local filesystem paths;
- hidden object descriptions the player has not discovered;
- unrestricted NPC or quest internals;
- image bytes or data URLs in map JSON;
- a fabricated current location;
- lossy route statuses.

The definition endpoint should be highly cacheable. The overlay endpoint should be small, bounded, and refreshed after authoritative mutations.

## MAP-4 through MAP-7 — Screenshot-equivalent MVP

These phases produce the reviewed reference interaction:

- compact preview in `RpgWorldRail`;
- full-screen or large workspace map;
- zoom and pan;
- independent building and landmark sprites;
- roads and labels;
- hover/focus cards;
- click selection;
- player and quest markers.

This milestone intentionally stops before click-to-travel so presentation can be validated independently of mutation flows.

## MAP-8 and MAP-9 — Living authoritative map

Bind the renderer to current session state:

- discovered objects appear;
- fog recedes;
- routes open, block, or lock without losing identity;
- temporary events and dangers appear and expire;
- damaged or destroyed buildings change visual state;
- map actions flow only through the single authoritative endpoint;
- the player marker moves only after the returned authoritative session mutation confirms travel.

## MAP-10 — Interior peeks

A building detail action loads an interior child map or scene plate. The first implementation can show hotspots for owner, service counter, exits, occupants, and interactable objects. Tactical movement is out of scope unless a separate combat-map roadmap adopts it.

## MAP-11 and MAP-12 — Art and procedural growth

Only after the data-driven map is stable should image generation and procedural settlement growth become production dependencies.

The layout generator should use deterministic seeds and constraints such as:

- road connectivity;
- minimum footprint spacing;
- parcel and district boundaries;
- service distribution;
- gate and landmark placement;
- walkable route clearance;
- label collision reduction;
- stable ordering and IDs.

## Performance budgets

Initial target budgets for a desktop-first release:

- 60 FPS during normal pan and zoom on the reference settlement;
- pointer hover response under 50 ms;
- map-open interaction ready under 500 ms when definition and assets are cached;
- no full definition reload when only the dynamic overlay changes;
- no more than one active tooltip and one selected-object panel;
- bounded marker animation with reduced-motion support;
- no generated asset larger than the configured map texture budget.

The exact object-count and texture budgets should be finalized from measured scenes in MAP-13.

## Test strategy

### Backend

- schema and version migration tests;
- route-ID, direction, parallel-route, and lossless-status tests;
- geometry, footprint, and hitbox validation;
- deterministic ordering, serialization, and hashing;
- graph-to-map projection;
- typed missing/invalid current-location behavior;
- discovery and visibility redaction;
- travel and object-action capability mapping;
- stale revision and idempotent action behavior;
- save/load and replay stability;
- missing asset and missing child-map fallback behavior;
- raw binary asset MIME, caching, conditional request, and path-redaction behavior.

### Frontend

- definition and overlay cache behavior;
- layer ordering and stable keys;
- pan/zoom bounds and fit/reset behavior;
- hover, focus, pointer leave, selection, and tooltip clamping;
- keyboard and screen-reader object list;
- marker and fog rendering from overlays;
- parent/child navigation;
- stale revision and API error recovery;
- no player marker when authoritative location is unavailable;
- no action when an object is decorative, hidden, stale, or disabled;
- no optimistic authoritative movement.

### End to end

1. Open a live RPG session.
2. Open the full map.
3. Fit the map, zoom, and pan.
4. Hover and keyboard-focus a discovered building.
5. Select it and inspect truthful live details.
6. Select a safe known destination and submit a map action.
7. Verify the normal mutation envelope, current location, and marker update from authoritative state.
8. Select an unsafe, blocked, locked, stale, or unknown destination and verify no silent teleport occurs.
9. Enter a settlement or interior child map and return through breadcrumbs.
10. Save, reload, and confirm discovery, current location, canonical route state, and map revision persist.
11. Replay the same authoritative turns and confirm the same definition/overlay projection is produced.
12. Confirm a missing authoritative current location produces an unavailable overlay rather than a fabricated marker.

## MVP definition

The first production MVP is complete through MAP-9 when a live session can display a settlement map comparable to the reviewed reference, including:

- a styled background with exact logical-coordinate mapping;
- independently rendered structures and landmarks;
- canonical route geometry and labels;
- smooth pan and zoom;
- hover/focus details;
- click selection;
- player, quest, danger, and event markers;
- discovery/fog state;
- truthful single-entry authoritative map actions;
- independently cacheable definitions and overlays;
- raw asset delivery without filesystem path exposure.

Interior drill-down, generated visual assets, procedural town growth, and a possible PixiJS renderer are follow-on capabilities, not blockers for the first useful interactive map.

## Release principles

- Data first, art second.
- Canonical route IDs before route rendering or mutation.
- Static definition separate from dynamic overlay.
- Simulation truth separate from AI presentation.
- No report-era fallback in authoritative projection.
- Explicit actions instead of click-to-teleport.
- One authoritative map-action mutation entry point.
- Stable asset IDs and raw binary delivery instead of local paths or JSON image bytes.
- Deterministic logical coordinates instead of image pixels.
- Footprints for layout; hitboxes for interaction.
- SVG first; PixiJS only after profiling.
- Save/load and replay behavior are part of the map feature, not cleanup work.
