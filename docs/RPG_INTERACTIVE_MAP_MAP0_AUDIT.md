# RPG Interactive Map MAP-0 — Architecture audit

Status: complete

This audit establishes the source-of-truth boundaries and adoption points required before implementing the interactive RPG map contracts. MAP-0 intentionally changes no runtime behavior.

## 1. Canonical session shape

A persisted RPG session is a top-level package with distinct state groups:

- `manifest`: session identity, schema version, title, timestamps, status, and source template;
- `state`: the current playable campaign state used by the typed RPG session routes and web workspace;
- `simulation_state`: lower-level deterministic/presentation/memory state retained by the session service and portable package bridge;
- `runtime_state`: bounded operational state such as active job/error/ambient runtime data;
- `setup_payload`: deterministic campaign genesis input;
- `installed_packs`: normalized by the session service.

`src/app/rpg/session/service.py` is the persistence boundary. It migrates and normalizes sessions before save/load, guarantees `manifest`, `simulation_state`, `runtime_state`, and `installed_packs`, and delegates disk persistence to `durable_store`.

The current new-game path creates both `state` and `simulation_state`. The map feature must not assume that the lower-level `simulation_state` already contains the live world graph. For current sessions, the user-facing campaign truth is primarily in `session["state"]`; the future canonical map/world groups must be added explicitly and migrated rather than inferred from display strings.

## 2. Current location truth

The current new-game state writes both:

- `state.location`: display label;
- `state.current_location`: display label.

It does not currently write a canonical `current_location_id` or `player.location_id` for the standard new-game state.

`src/app/rpg/world_runtime.py` is a report adapter and currently searches several possible fields before falling back to the alphabetically first graph location. That fallback is unsuitable for production projection.

MAP production rule:

1. A canonical location ID must be present in an explicitly versioned authoritative state field.
2. Display labels such as `state.location` and `state.current_location` are not IDs and must not select a map object by name matching.
3. Missing, blank, or unresolved canonical location state produces a typed overlay state such as `current_location_unavailable`.
4. The definition may still render, but no live player marker is fabricated.
5. Preview/demo-only UI data must never be substituted into a live overlay.

MAP-1 must define the canonical field and migration compatibility policy. MAP-3 must expose typed unavailable metadata.

## 3. Current world and map state

The current playable `state` includes user-facing groups such as:

- `player`;
- `world`;
- `party`;
- `quests`;
- `relationships`;
- `encounter`;
- `timeline` and `journal`;
- `quick_actions`;
- `features`;
- turn counters and timestamps.

The standard new-game `world` group currently contains environment/economy-facing values such as time, weather, temperature, reputation, and activity. It is not yet a canonical renderable map definition or route graph.

The existing deterministic graph foundation is in `src/app/rpg/world_graph.py`. The report adapter in `src/app/rpg/world_runtime.py` accepts `state.map`, `state.world_map`, or `state.world` as candidate graph payloads, but this permissive parsing is compatibility/report behavior—not an authoritative storage contract.

MAP production rule:

- map definitions are versioned repository resources keyed by `map_id`;
- session overlays reference stable map object, location, and route IDs;
- environment data may decorate an overlay but cannot create map topology;
- discovery, visibility, route state, and current position must be persisted/migrated as explicit deterministic state.

## 4. Route identity and status audit

`RpgRoute` currently has:

- `from_id` and `to_id`;
- `status` supporting `open`, `blocked`, and `locked`;
- `safe`, `known`, and tags.

Current limitations:

- no canonical route ID;
- endpoint pairs are treated as unordered identity;
- `with_route()` replaces by endpoint pair;
- parallel routes and distinct one-way passages cannot be represented safely;
- `world_runtime._route()` converts every non-`open` status to `blocked`, losing `locked`.

MAP-1B must add stable route IDs and explicit direction, replace routes by ID, preserve statuses losslessly, support parallel routes, and reject unknown status values with a typed compatibility error. Map geometry and overlays must reference the same canonical route ID.

## 5. Typed RPG session API

`src/app/gateway/rpg_session_routes.py` provides the current typed gateway surface:

- `GET /api/rpg/sessions`;
- `GET /api/rpg/sessions/{session_id}`;
- `POST /api/rpg/sessions/{session_id}/turn`;
- campaign creation/continue/rename/delete and loadout operations.

The session read route loads the durable session and returns both `session` and `game = session.state`. The foreground turn route applies the deterministic turn runtime, saves the returned session, and returns the normal session/result envelope.

Map API adoption point:

- add modular route registration beside `rpg_session_routes`;
- load sessions through `app.rpg.session.service.load_session`;
- project definitions and overlays without mutating the loaded session;
- keep map mutations behind one `POST /api/rpg/sessions/{session_id}/map-actions` entry point;
- return the existing authoritative turn/session mutation envelope plus map revision metadata.

The frontend must not decide whether an action uses instant travel or a narrated turn. That decision remains server-side.

## 6. Browser refresh and mutation flow

`src/apps/web/src/features/rpg/RpgWorkspace.tsx` uses React Query for:

- replay/session inventory;
- the selected live session;
- shared jobs, assets, and reports;
- Hermes suggestions/readouts and related RPG support data.

RPG turns are normally queued as `rpg.turn` jobs. The workspace polls job state and, after the exact submitted or latest completed turn job finishes, refetches the selected session and inventory and invalidates dependent RPG queries.

Map adoption point:

- definition query key: `['feature', 'rpg', 'map-definition', mapId, definitionRevision]`;
- overlay query key: `['feature', 'rpg', 'map-overlay', sessionId, mapId]`;
- after a completed turn or successful map action, invalidate/refetch the overlay;
- do not invalidate/reload an unchanged definition revision;
- never update the authoritative player marker optimistically;
- viewport state remains local/Zustand state keyed by `map_id` and is not part of the session save.

## 7. Asset delivery audit

The repository already has browser-safe image delivery:

```text
GET /api/assets/{asset_id}/file
```

`src/app/gateway/image_asset_routes.py`:

- resolves an asset by stable ID;
- accepts only `AssetType.IMAGE` with GIF/JPEG/PNG/WebP MIME types;
- verifies that the referenced file exists;
- returns a `FileResponse` with authoritative MIME type;
- defaults to inline disposition and supports `?download=true`;
- does not expose the local storage path in the API contract.

The current focused tests verify successful ID-based inline delivery, download disposition, MIME response, and rejection of non-image assets.

MAP-0 conclusion: a new `/raw` route is not required merely to begin the map renderer. The existing `/file` route is the canonical current adoption point for image backgrounds and sprites.

Before MAP-11 declares production asset integration complete, tests/documentation must also confirm the behavior expected for map-scale assets:

- conditional requests and ETag/Last-Modified behavior supplied by the response stack;
- cache policy appropriate for immutable/content-revisioned assets;
- content length;
- range/streaming behavior if measured asset sizes justify it;
- safe failure for missing files, missing IDs, and unsupported MIME types;
- no storage path leakage in errors or map JSON.

Map definition JSON carries asset IDs and declared logical dimensions, not data URLs, encoded bytes, or filesystem paths.

## 8. Static preview and live UI audit

`src/apps/web/src/features/rpg/RpgWorldRail.tsx` currently:

- renders `/rpg/glimmerdeep-pass-map.svg` only for preview state;
- renders a non-interactive `Live location` placeholder for a live session;
- shows the selected session location below the card.

This is an honest placeholder and must remain distinguishable from live map truth until MAP-4A lands. The static preview asset is suitable as a development visual reference, not as a canonical live map definition.

MAP adoption point:

- retain the compact world-rail card;
- open a larger map surface from it;
- load definition and overlay independently;
- show loading, unavailable, stale, empty, and error states;
- only render a player marker when the overlay has a valid canonical current location.

## 9. Save/load and replay boundary

The session service normalizes and validates sessions before persistence. Portable package export/import currently preserves `simulation_state` and installed packs through the package bridge. The interactive map feature therefore needs an explicit persistence decision in MAP-1/MAP-2:

- stable map definition identity/revision belongs in repository/content data, not duplicated wholesale on every session turn;
- dynamic map overlay truth—current map/location, discovery, route states, object state, and map hierarchy position—must live in a deterministic persisted session group;
- any new group requires migration/default handling for older saves;
- deterministic serialization and hashes must exclude browser viewport state;
- replay must reproduce the same definition reference and overlay projection from the same authoritative turns.

MAP-14 is not complete until these fields survive save/load/package compatibility as applicable and replay projection is stable.

## 10. Security and redaction boundary

The map projection must not expose:

- local filesystem paths;
- undiscovered object descriptions;
- hidden NPC locations or internal schedules;
- hidden quest targets or future event state;
- unrestricted world graph nodes/routes;
- preview data in live responses.

Definition resources contain stable public geometry/art references. Session overlays contain only information currently visible or discovered by that session. Server-projected capabilities include disabled reasons without leaking hidden truth.

## 11. Confirmed implementation order

The implementation will advance on the long-lived `tmp-rpg-map` branch only after both required GitHub Actions workflows pass on each exact phase head SHA.

Early vertical slice:

1. MAP-1A: versioned definition/overlay contracts, revisions, deterministic serialization, typed unavailable states.
2. MAP-1B: canonical route IDs/direction and lossless status handling.
3. MAP-2A: deterministic 8–12-object settlement fixture.
4. MAP-3A: cacheable read-only definition and session overlay endpoints.
5. MAP-4A: live React/SVG shell and first screenshot milestone.
6. MAP-1C/MAP-2B: geometry hardening and expanded repository fixtures before later interaction phases.

## MAP-0 exit decision

MAP-0 is complete because the following are now explicit:

- authoritative session and persistence roots;
- current-location ambiguity and the prohibition on fallback placement;
- route identity/status deficiencies;
- current session read/turn mutation envelope;
- frontend post-turn refresh behavior;
- existing browser-safe asset file route and remaining cache validation work;
- UI adoption points and preview/live separation;
- save/load, replay, redaction, and security boundaries.

No production code or runtime behavior changed in MAP-0.
