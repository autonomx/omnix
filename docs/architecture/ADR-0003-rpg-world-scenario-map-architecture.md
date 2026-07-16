# ADR-0003: Revisioned RPG Worlds, Scenarios, and Spatial Runtime

- **Status:** Accepted for implementation
- **Date:** 2026-07-16
- **Decision owners:** Omnix maintainers
- **Base:** `main`
- **Related:** `ADR-0001-centralized-postgresql-authority.md`, `ADR-0002-unified-rpg-narrative-engine.md`

## Context

RPG campaign creation currently combines protagonist setup, World Forge generation, opening-story materialization, campaign persistence, and launch gating. Generated canon is campaign-owned, so the same world cannot be authored once and reused by multiple campaigns. The existing interactive-map foundation separates definitions and overlays, but it does not yet define reusable world ownership, scenario starts, grid movement, campaign map instances, or event-authoritative spatial state.

## Decision

Omnix will use the following ownership chain:

```text
World Project
  -> World Revision
    -> World Release
      -> Scenario Revision
        -> Campaign
          -> Checkpoints
```

Spatial content uses this chain:

```text
Map Blueprint
  -> Map Definition Revision
    -> Campaign Map Instance
      -> Authoritative Map Events
        -> Reducer Snapshot
          -> Observer-Safe Projection
```

## World Project and World Revision

A World Project is the mutable authoring workspace. It owns the entity manifest, topic drafts, generation runs, directives, map blueprints, validation findings, and review state.

Publishing creates an immutable World Revision containing canon, topology, adventure seeds, stable semantic IDs, and map-blueprint requirements. Published revisions are never edited in place.

## World Release

A World Release certifies compiled artifacts for exactly one World Revision. It binds exact map-definition revisions and hashes, retrieval and relationship indexes, visual assets, compiler versions, completeness evidence, and consistency evidence.

- Canon or blueprint requirements changing creates a new World Revision.
- Geometry or compiler corrections that preserve semantic requirements create a new Map Definition Revision and World Release.
- A new release never silently changes an existing campaign.

## Scenario Revision

A Scenario Project publishes immutable Scenario Revisions. A Scenario Revision pins a World Revision and defines starting epoch, starting location, activated conflicts, initial NPCs, protagonist options, starting resources, opening seed options, and initial map-state operations.

Scenario initialization operations apply when Campaign Map Instances are created. They never modify reusable Map Definitions.

## Campaign binding

A campaign pins exact identities and hashes for:

- World Revision;
- World Release;
- Scenario Revision;
- every instantiated Map Definition Revision.

Campaigns never auto-upgrade. A migration or upgrade must be explicit, validated, and auditable.

## Map Blueprint and Map Definition

A Map Blueprint declares semantic requirements such as map level, navigation kind, required zones, portals, spawn points, terrain, services, architectural style, size profile, seed, and generation direction.

A Map Definition Revision is immutable compiled geometry and navigation truth. It stores logical bounds, grid transforms, terrain and collision, zones, objects, explicit portal endpoints, spawn points, render metadata, asset references, semantic-interface hash, and definition hash.

Generated imagery is presentation. It cannot define collision, portals, actor positions, route state, or authoritative object existence.

## Campaign Map Instance

A Campaign Map Instance binds one campaign and location to one exact Map Definition Revision. It owns a reducer snapshot and optimistic `map_state_revision`, while authoritative changes are persisted as simulation events.

The mutation flow is:

```text
validated command
  -> persisted event
    -> deterministic reducer
      -> snapshot update
        -> observer-safe projection
```

Replay applies persisted outcomes. It does not invoke AI, destination selection, or pathfinding again.

## Movement authority

AI may propose semantic movement goals or choose from simulation-generated candidate destinations. AI cannot invent or directly commit coordinates.

The simulation validates candidates, runs deterministic pathfinding, persists the resolved path and costs in an `actor_moved` event, and updates the snapshot using compare-and-swap on `map_state_revision`.

Internal grid coordinates are zero-based. Player-facing coordinates may use a declared display offset. Saved state never depends on screen pixels or image resolution.

## Observer-safe projection

Authoritative geometry and state may contain secret doors, traps, hidden rooms, invisible actors, GM-only labels, and undiscovered routes. Normal clients receive only an observer-safe projection derived from:

```text
authoritative definition
+ campaign map-instance state
+ observer knowledge
+ visibility and detection
= player-safe projection
```

Secret authority data is never exposed by the cacheable public definition resource.

## World Forge jobs

World generation is a durable dependency graph. Each topic uses the generic job infrastructure with a deterministic generation fingerprint covering topic input, dependencies, directives, entity-manifest hash, generator and prompt versions, provider route, model, seed, schemas, and relevant compiler versions.

A previous result is reusable only when the complete fingerprint matches.

## Readiness

Simulation and presentation readiness are independent.

Simulation readiness:

```text
stub | semantic | navigable | certified | failed
```

Presentation readiness:

```text
placeholder | assets_pending | ready | failed
```

Gameplay may enter a `navigable` location even while optional generated artwork is pending. World publication requires the starter area to be simulation-certified.

## Non-negotiable invariants

1. World creation creates no campaign or protagonist.
2. One World Revision may launch multiple independent campaigns.
3. Campaign launch from a ready release performs no World Forge calls.
4. Published World, Release, Scenario, and Map Definition revisions are immutable.
5. Campaigns pin exact revisions and content hashes.
6. Scenario operations initialize instances and never mutate definitions.
7. Events are authoritative; JSON map state is a reducer snapshot.
8. Map writes use idempotent command IDs and optimistic revisions.
9. Replay never calls AI or pathfinding to reconstruct resolved movement.
10. AI never directly mutates coordinates or geometry.
11. Observer projections cannot leak secret authority data.
12. Generated art never owns collision or navigation truth.
13. World and region travel use canonical graphs; local movement may use grids.
14. Durable topic results are reused only by exact generation fingerprint.
15. Existing campaigns remain compatible through explicit adapters.

## Mandatory architecture gate

Before AI world generation or the full library UI is considered complete, a manual vertical slice must prove:

- one published World Revision and World Release;
- one published Scenario Revision;
- two campaigns launched from the same revisions;
- one shared tavern Map Definition;
- independent Campaign Map Instances;
- movement in Campaign A does not affect Campaign B;
- save, load, and replay preserve the movement event and snapshot;
- newer World and Map Definition revisions do not alter either campaign.

## Consequences

The architecture adds explicit revision and binding layers, but removes campaign/world coupling, prevents cross-campaign mutation, supports resumable generation, preserves deterministic replay, and permits progressive maps without making image generation a gameplay dependency.