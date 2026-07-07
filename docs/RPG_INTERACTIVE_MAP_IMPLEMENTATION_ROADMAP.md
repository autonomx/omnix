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
- `src/app/rpg/world_runtime.py` adapts saved runtime state into the world graph and exposes report-oriented map metadata.
- `apps/web/src/features/rpg/RpgWorldRail.tsx` has a compact map card, but live sessions currently expose only a location placeholder rather than an interactive map.
- `apps/web/public/rpg/glimmerdeep-pass-map.svg` proves that static SVG map art is already supported.
- The shared Image Generation Workspace can create and persist image assets that a later map-art pipeline can reuse.

The missing layer is a canonical renderable map document and a frontend renderer bound to authoritative RPG state.

## Primary technical decision

### Use React + SVG for the first production map renderer

The first renderer should use an SVG scene inside the existing React application, not PixiJS immediately.

SVG is the better first fit because the initial settlement and region maps will contain tens or low hundreds of interactive objects, and SVG provides:

- native paths for roads, borders, rivers, labels, and explicit hit polygons;
- simple pointer, focus, and keyboard events;
- DOM-based accessibility and testability;
- deterministic screenshots and straightforward Vitest/Playwright coverage;
- no new rendering dependency for the MVP;
- easy composition with regular HTML tooltips and action panels.

The scene is still structured like a game renderer. A single transformed viewport contains background, terrain, routes, props, structures, labels, and overlays. Zooming and panning transform the parent viewport rather than moving every object independently.

PixiJS remains an explicit later performance option. It should be adopted only if measured production scenes exceed the SVG budget, such as more than roughly 500 simultaneously visible sprites, sustained animation layers, particles, or unacceptable frame times on supported hardware.

## Architecture boundaries

### Simulation owns truth

The deterministic simulation owns:

- locations and their relationships;
- route state and travel eligibility;
- discovery and visibility;
- ownership, services, occupants, damage, closure, and danger state;
- current player location;
- map revision and save/load state.

The frontend never mutates world state because an icon was clicked. A map action submits an intent to the authoritative RPG flow. Safe travel can reuse the current deterministic route gate. Unsafe travel, unknown routes, and location expansion continue through the normal resolver and narration path.

### AI owns presentation assistance, not authority

AI may generate or suggest:

- map and settlement names;
- descriptions and hover-card prose;
- visual style prompts;
- background or object artwork;
- high-level settlement themes and candidate landmarks.

AI must not directly decide authoritative coordinates, travel success, discovery, route state, or object existence on each turn. Any optional AI-authored layout proposal must pass a typed schema and a deterministic placement/validation step before persistence.

## Canonical data split

The map should be separated into three independently cacheable state groups.

### 1. Map definition

Stable geometry and visual references:

- logical bounds and coordinate system;
- background asset reference;
- object positions, anchors, hitboxes, and render order;
- route and river paths;
- labels and map hierarchy;
- parent/child map relationships.

### 2. Map overlay snapshot

Session-specific dynamic state:

- current player marker;
- discovered and visible objects;
- quest, NPC, enemy, resource, and event markers;
- open, blocked, dangerous, or unknown routes;
- building status such as open, closed, damaged, burned, or occupied;
- fog-of-war masks;
- weather, season, light, and hazard presentation hints.

### 3. Viewport state

Browser-local presentation state:

- zoom;
- pan offset;
- selected object;
- open layer filters;
- last viewed map level.

Viewport state must not be written into authoritative RPG saves unless a future user-preference feature explicitly requires it.

## Coordinate model

Use integer logical coordinates independent of image resolution. A map can define bounds such as `10000 x 6000`, while the browser scales those coordinates into any viewport size.

This avoids coupling saved world state to a particular PNG or screen resolution and gives deterministic layout, route, hitbox, and replay behavior.

Pseudo-isometric visuals remain ordinary 2D sprites. Each object uses a bottom-center anchor, an explicit footprint or hit polygon, and a stable `z_index` derived from layer and vertical position.

## Proposed contracts

```json
{
  "schema_version": 1,
  "map_id": "settlement:frost_haven",
  "level": "settlement",
  "revision": 42,
  "seed": 824193,
  "parent_map_id": "region:northern_pass",
  "bounds": { "width": 10000, "height": 6000 },
  "background": {
    "asset_id": "asset_map_frost_haven_base",
    "fit": "cover"
  },
  "objects": [
    {
      "id": "building:frost_haven_inn",
      "location_id": "frost_haven_inn",
      "kind": "building",
      "x": 2870,
      "y": 4310,
      "z_index": 4310,
      "anchor": "bottom_center",
      "sprite": {
        "asset_id": "asset_sprite_timber_inn_01",
        "width": 620,
        "height": 540
      },
      "hitbox": {
        "kind": "polygon",
        "points": [[-270, -150], [270, -150], [250, 80], [-250, 80]]
      },
      "child_map_id": "interior:frost_haven_inn"
    }
  ],
  "routes": [
    {
      "id": "route:west_gate_to_market",
      "from_location_id": "frost_haven_west_gate",
      "to_location_id": "frost_haven_market",
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

The dynamic overlay is returned separately and references these stable IDs.

## Canonical runtime flow

```text
Authoritative RPG session state
  -> RpgRegionGraph and map definition repository
  -> deterministic map projection
  -> GET /api/rpg/sessions/{session_id}/maps/{map_id}
  -> map definition + overlay revision
  -> React map store
  -> SVG scene layers
  -> HTML tooltip / selected-object panel
  -> Travel, Inspect, or Enter intent
  -> authoritative RPG turn or deterministic safe-travel resolver
  -> updated session and overlay revision
```

Large generated image bytes must be served through asset IDs, not embedded in session JSON or returned as filesystem paths.

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
- **Travel**, **Inspect**, **Talk**, **Trade**, and **Enter** are explicit actions governed by current capabilities and route state.
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
| MAP-0 | Architecture audit and canonical roadmap | Existing graph, runtime, UI, assets, save/load, and API adoption points are documented; no placeholder behavior is mistaken for live state. |
| MAP-1 | Typed map contracts and geometry helpers | Versioned map definition, overlay, object, route, label, hitbox, and hierarchy contracts exist with deterministic validation and unit tests. |
| MAP-2 | Map repository and deterministic starter definitions | A repository loads versioned definitions by map ID; one region and one settlement map use logical coordinates and stable IDs. |
| MAP-3 | Session map projection API | A bounded typed endpoint returns definition metadata, dynamic overlay state, capabilities, and asset IDs for a selected session. |
| MAP-4 | React map shell and full-map surface | The RPG world rail opens a responsive full-map view with loading, empty, unavailable, and error states grounded in live session data. |
| MAP-5 | Pan, zoom, reset, fit, keyboard, and touch controls | One transformed viewport supports wheel/pinch zoom, drag pan, keyboard controls, bounded zoom, fit-to-map, and reduced-motion behavior. |
| MAP-6 | Interactive objects, hitboxes, hover/focus cards, and selection | Buildings and landmarks render from data; hover, focus, click, tooltip clamping, selected state, and accessible object list are covered. |
| MAP-7 | Roads, labels, markers, and layer controls | Route paths, settlement labels, player position, quest/danger/event markers, and user layer filters render deterministically. |
| MAP-8 | Discovery, fog, environment, and live overlay refresh | Hidden/known/discovered/visible states, fog masks, route status, weather/light hints, and turn-driven overlay refresh are wired to saved state. |
| MAP-9 | Authoritative travel and object actions | Map actions reuse deterministic travel gates and normal RPG intents; blocked, unsafe, unknown, locked, and expansion-required cases are truthful. |
| MAP-10 | Region, settlement, and interior drill-down | Parent/child maps, breadcrumbs, **Peek inside**, **Enter**, back navigation, and per-level viewport restoration work without duplicating render logic. |
| MAP-11 | Curated asset pack and generated-art integration | Starter sprites are production-ready; generated backgrounds/sprites use shared asset IDs, style metadata, caching, validation, and safe fallbacks. |
| MAP-12 | Deterministic procedural settlement assembler | A seed and world graph produce stable roads, zones, parcels, labels, and placements; regeneration with the same inputs is byte-for-byte stable. |
| MAP-13 | Performance budget and PixiJS decision gate | Scene profiling records object count, frame time, memory, and interaction latency; PixiJS is adopted only if the documented SVG budget is exceeded. |
| MAP-14 | Save/load, replay, accessibility, and release gate | Map revisions, discovery, route state, hierarchy, and object changes survive save/load and deterministic replay; full end-to-end and accessibility gates pass. |

## Recommended narrow slices

### MAP-0 — Audit

- Inventory all current map/world fields emitted by live RPG sessions.
- Document the source of current location, routes, discovered locations, environment snapshot, and save groups.
- Confirm asset-ID serving and generated-image retention behavior.
- Record the current RPG query refresh path after a turn.
- Add no runtime behavior in this slice.

### MAP-1 — Contracts

Add focused modules rather than expanding `world_graph.py` indefinitely:

- `src/app/rpg/map_contracts.py`
- `src/app/rpg/map_geometry.py`
- `src/tests/rpg/test_map_contracts.py`
- `src/tests/rpg/test_map_geometry.py`

Validation must reject duplicate IDs, out-of-bounds points, invalid child-map references, malformed hitboxes, unresolved asset references where required, and non-deterministic ordering.

### MAP-2 — Repository and starter maps

Add a versioned map repository and two small fixtures:

- a northern region map connected to current RPG location IDs;
- a Frost Haven-style settlement map containing roughly 20-40 objects.

The starter map should use static SVG/PNG assets so runtime wiring can be verified without waiting for generated art.

### MAP-3 — Projection API

The API response should be bounded and split into definition and overlay revisions. Unchanged definitions can be cached while overlay state refreshes after turns.

The browser must not receive:

- absolute local filesystem paths;
- hidden object descriptions the player has not discovered;
- unrestricted NPC or quest internals;
- image bytes or data URLs in map JSON.

### MAP-4 through MAP-7 — Screenshot-equivalent MVP

These phases produce the first user-visible milestone:

- compact preview in `RpgWorldRail`;
- full-screen or large workspace map;
- zoom and pan;
- independent building and landmark sprites;
- roads and labels;
- hover/focus cards;
- click selection;
- player and quest markers.

This milestone intentionally stops before click-to-travel so presentation can be validated independently of mutation flows.

### MAP-8 and MAP-9 — Living authoritative map

Bind the renderer to current session state:

- discovered objects appear;
- fog recedes;
- routes open or close;
- temporary events and dangers appear and expire;
- damaged or destroyed buildings change visual state;
- travel actions resolve through the existing deterministic boundary.

### MAP-10 — Interior peeks

A building detail action loads an interior child map or scene plate. The first implementation can show hotspots for owner, service counter, exits, occupants, and interactable objects. Tactical movement is out of scope unless a separate combat-map roadmap adopts it.

### MAP-11 and MAP-12 — Art and procedural growth

Only after the data-driven map is stable should image generation and procedural settlement growth become production dependencies.

The layout generator should use deterministic seeds and constraints such as:

- road connectivity;
- minimum object spacing;
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
- geometry and hitbox validation;
- deterministic ordering and hashing;
- graph-to-map projection;
- discovery and visibility redaction;
- travel capability mapping;
- save/load and replay stability;
- missing asset and missing child-map fallback behavior.

### Frontend

- layer ordering and stable keys;
- pan/zoom bounds and fit/reset behavior;
- hover, focus, pointer leave, selection, and tooltip clamping;
- keyboard and screen-reader object list;
- marker and fog rendering from overlays;
- parent/child navigation;
- stale revision and API error recovery;
- no action when an object is decorative or undiscovered.

### End to end

1. Open a live RPG session.
2. Open the full map.
3. Fit the map, zoom, and pan.
4. Hover and keyboard-focus a discovered building.
5. Select it and inspect truthful live details.
6. Select a safe known destination and travel.
7. Verify current location and marker update from authoritative state.
8. Select an unsafe or blocked destination and verify no silent teleport occurs.
9. Enter a settlement or interior child map and return through breadcrumbs.
10. Save, reload, and confirm discovery, current location, route state, and map revision persist.
11. Replay the same authoritative turns and confirm the same map projection is produced.

## MVP definition

The first production MVP is complete through MAP-9 when a live session can display a settlement map comparable to the reviewed reference, including:

- a styled background;
- independently rendered structures and landmarks;
- roads and labels;
- smooth pan and zoom;
- hover/focus details;
- click selection;
- player, quest, danger, and event markers;
- discovery/fog state;
- truthful authoritative travel actions.

Interior drill-down, generated visual assets, procedural town growth, and a possible PixiJS renderer are follow-on capabilities, not blockers for the first useful interactive map.

## Release principles

- Data first, art second.
- Static definition separate from dynamic overlay.
- Simulation truth separate from AI presentation.
- Explicit actions instead of click-to-teleport.
- Stable asset IDs instead of local paths.
- Deterministic logical coordinates instead of image pixels.
- SVG first; PixiJS only after profiling.
- Save/load and replay behavior are part of the map feature, not cleanup work.
