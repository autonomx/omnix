# RPG World, Scenario, and Spatial Runtime Roadmap

Status: phases 0-5 complete; later phases remain planned

ADR: `docs/architecture/ADR-0003-rpg-world-scenario-map-architecture.md`

Implementation evidence:

- merged implementation PR: `#1382`;
- merge SHA: `25a971e30946e5b93f5b2a202214f4c5fe5dd215`;
- exact implementation head verified by GitHub Actions: `9a58145631fb0b7d677ac36ff9edd7901e2f2c0a`;
- passing workflows: RPG Phase 0 architecture compliance, RPG deterministic PR gates, PostgreSQL persistence gates, and Live Chat hardening gates.

## Objective

Separate reusable world authoring from campaign launch, introduce revisioned scenarios and releases, and extend the deterministic map runtime with campaign-owned instances, grid movement, authoritative events, and observer-safe projections.

## Phase 0 — ADR and contracts

Status: complete

Exit conditions:

- ownership and revision terminology is fixed;
- event and snapshot authority is fixed;
- visibility and deletion boundaries are documented;
- generation job fingerprint rules are documented;
- the mandatory two-campaign tavern gate is documented.

## Phase 1 — World, release, and scenario boundary

Status: complete

Delivered:

- typed World Project, World Revision, World Release, Scenario Project, and Scenario Revision contracts;
- campaign world-binding and launch contracts;
- PostgreSQL migration and repositories;
- compatibility adapter for current Campaign Genesis payloads;
- read/create/publish/list APIs with deterministic hashes.

Exit condition met: one manually authored world and scenario can be published and a launch binding can be resolved without World Forge.

## Phase 2 — Minimum spatial foundation and golden slice

Status: complete

### Phase 2A

Delivered:

- square-grid schema and grid-to-visual transform;
- terrain walkability;
- explicit two-ended portals;
- spawn points and actor placements;
- independently revisioned Map Definitions;
- Campaign Map Instances;
- optimistic map-state revisions;
- authoritative movement commands and events;
- deterministic reducer snapshots;
- observer-safe projection boundary.

### Phase 2B

Golden proof completed:

1. Publish World Revision 1 and World Release 1 — completed.
2. Publish Scenario Revision 1 — completed.
3. Launch Campaign A and Campaign B — completed.
4. Bind both campaigns to one tavern Map Definition — completed.
5. Create independent Map Instances — completed.
6. Move Xylvanna only in Campaign A — completed.
7. Confirm Campaign B is unchanged — completed.
8. Save, load, and replay Campaign A — completed.
9. Publish a newer World Revision and corrected Map Definition/Release — completed.
10. Confirm existing campaigns remain pinned — completed.

## Phase 3 — Durable World Forge DAG

Status: complete

Delivered:

- entity-manifest planning;
- deterministic topic generation fingerprints;
- generic durable jobs per topic;
- dependency-hash scheduling;
- exact-result reuse;
- stale-state propagation;
- partial regeneration and reconciliation;
- publication into immutable World Revisions and Releases.

Exit condition met: process interruption can resume without losing completed topics, and changed inputs cannot reuse stale outputs.

## Phase 4 — Worlds & Campaigns UI

Status: complete

Delivered:

- full-page Worlds and Campaigns library;
- world cards, scenario cards, and campaign cards;
- world/topic authoring surface;
- scenario editor;
- generation progress and validation findings;
- map-blueprint summary/editor;
- release history;
- fast launch from a published scenario.

Exit condition met: the primary UI does not require World Forge during normal campaign launch from a certified release.

## Phase 5 — Starter bubble and progressive maps

Status: complete

Delivered:

- world topology and deferred location slots;
- starting region, settlement, interior, and one neighboring destination;
- simulation and presentation readiness axes;
- predictive background materialization;
- navigable placeholder rendering while optional art is pending;
- campaign pinning of progressively materialized definitions;
- explicit promotion into a future World Revision.

Exit condition met: a published world is immediately playable, deferred maps can materialize safely into explicit future revisions, existing campaigns remain pinned, and image-generation failure cannot block navigation-ready gameplay.

## Later phases

- living NPC spatial goals and level-of-detail simulation;
- observer knowledge, detection, and line of sight;
- campaign geometry patches;
- tactical movement, cover, reactions, and multi-cell actors;
- performance profiling and renderer escalation only when measured.

## Release invariants

- no implicit campaign revision upgrades;
- no cross-campaign mutable map state;
- no secret authority data in player resources;
- no replay-time AI or pathfinding for resolved movement;
- no World Forge calls during normal launch from a ready release;
- no generated image authority over navigation or collision;
- all mutable writes are idempotent and revision checked.
