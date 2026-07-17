# RPG World, Scenario, and Spatial Runtime Roadmap

Status: phases 0-9 complete; final closure work remains in measured performance profiling and renderer escalation

ADR: `docs/architecture/ADR-0003-rpg-world-scenario-map-architecture.md`

Implementation evidence:

- phases 0-5 foundation implementation PR: `#1382`;
- phases 0-5 foundation merge SHA: `25a971e30946e5b93f5b2a202214f4c5fe5dd215`;
- phases 0-5 exact foundation head verified by GitHub Actions: `9a58145631fb0b7d677ac36ff9edd7901e2f2c0a`;
- Phase 6.1 implementation PR: `#1384`;
- Phase 6.1 merge SHA: `f695cbc50bc04339b730d394dc0c05ea40127f86`;
- Phase 6.1 exact implementation head verified by GitHub Actions: `b14eb99921338aaa1f85cb62163ee4560d5adeb1`;
- release certification and scenario initialization PR: `#1386`;
- release certification and scenario initialization merge SHA: `601266fc87114b286d24310a6fadf7e1de77d35c`;
- exact PR `#1386` implementation head verified by GitHub Actions: `8c1376fa4a28411472bbe2d6614d2fe2785ee29f`;
- Phase 0 lifecycle implementation PR: `#1388`;
- Phase 0 lifecycle merge SHA: `62272bcde8fe760b409ec1540aee1a1a09b9216f`;
- exact PR `#1388` implementation head verified by GitHub Actions: `6eb132f6d527cb7dd65d9d284f9250c5a15fd1d1`;
- Phase 1 legacy Campaign Bible import PR: `#1390`;
- Phase 1 legacy import merge SHA: `9d84c69a0ce94376caa84e9e7a53bc169c5820bf`;
- exact PR `#1390` implementation head verified by GitHub Actions: `52f5fc31cb65f1ff35e0e6601d6b29b1c32bd9ac`;
- Phase 3 topic history and generation lineage PR: `#1392`;
- Phase 3 history/lineage merge SHA: `63d939afbbbe58f0f1b01f015f4bb12d9e2e7ea1`;
- exact PR `#1392` implementation head verified by GitHub Actions: `8326e37d3586d056a3720d984b3fa97ac58913b4`;
- Phase 4 blueprint authoring and lifecycle UI PR: `#1394`;
- Phase 4 implementation merge SHA: `97cbba1d132dfebab041544e9218b48406ecde9e`;
- exact PR `#1394` implementation head verified by GitHub Actions: `2c02c2a4411032e5490d17cef177bd397f412171`;
- Phase 5 durable progressive materialization PR: `#1396`;
- Phase 5 implementation merge SHA: `0dc5c2bd9ef2d54d6162e15c54c21a26ffdc977a`;
- exact PR `#1396` implementation head verified by GitHub Actions: `2cd47ffba2d65250b20598f6bb89480b5755e456`;
- Phase 6 durable campaign spatial runtime PR: `#1398`;
- Phase 6 implementation merge SHA: `a660732f4485816b8de0f50defdd3ffbc9ec1ab5`;
- exact PR `#1398` implementation head verified by GitHub Actions: `97a41239322771022d7d9242f4e868ca6450a9cf`;
- Phase 7 observer knowledge, detection, and LOS PR: `#1400`;
- Phase 7 implementation merge SHA: `7db2f438c7ab958ff1b77e6a306701d98f3762d2`;
- exact PR `#1400` implementation head: `2bbb010b3947adae5719440cd5d2591f28000808`;
- Phase 8 campaign geometry patch PR: `#1401`;
- Phase 8 implementation merge SHA: `6630f947577d962cd18c76ad5b21606538618493`;
- exact PR `#1401` implementation head verified by GitHub Actions: `55076c46b0178a03f511bde43127a58b26bf1dcb`;
- Phase 9.1 multi-cell footprint authority PR: `#1404`;
- Phase 9.1 implementation merge SHA: `06108d526ce6e755de1f97b69b78a874be70b909`;
- exact PR `#1404` implementation head verified by GitHub Actions: `7905ecff4a7f15af904f109eb20b0a3b4f720606`;
- Phase 9.2 tactical movement, cover, and reactions PR: `#1406`;
- Phase 9.2 implementation merge SHA: `8760df8dca1bffa7891ff353b801fb4b86f3d843`;
- exact PR `#1406` implementation head verified by GitHub Actions: `98dbd87e9770d4e0ca97cdbe1b24b8116213be0a`;
- PR `#1400` passed architecture, PostgreSQL, and Live Chat workflows; its missing deterministic `GridZone.name` test fixture was corrected and the complete observer suite was revalidated on exact PR `#1401` head;
- exact PR `#1401`, `#1404`, and `#1406` heads passed RPG Phase 0 architecture compliance, RPG deterministic PR gates, PostgreSQL persistence gates, and Live Chat hardening gates.

## Objective

Separate reusable world authoring from campaign launch, introduce revisioned scenarios and releases, and extend the deterministic map runtime with campaign-owned instances, grid movement, authoritative events, and observer-safe projections.

## Phase 0 — ADR and contracts

Status: complete

Delivered:

- ownership and revision terminology;
- event and snapshot authority;
- visibility and secret-data boundaries;
- generation job fingerprint rules;
- mandatory two-campaign tavern gate;
- explicit lifecycle, archival, retention, restoration, and administrative hard-deletion policy;
- idempotent World and Scenario project archive/restore services and gateway APIs;
- active-generation archive guard;
- authoritative write guards for topics, generation, publication, scenarios, bindings, and new campaign launches;
- PostgreSQL proof that immutable revisions, releases, campaign bindings, and campaigns survive archival unchanged.

Exit condition met: lifecycle behavior is explicit, reversible, auditable, and cannot silently delete or alter published authority or existing campaign pins.

## Phase 1 — World, release, and scenario boundary

Status: complete

Delivered:

- typed World Project, World Revision, World Release, Scenario Project, and Scenario Revision contracts;
- campaign world-binding and launch contracts;
- PostgreSQL migration and repositories;
- compatibility adapter for current Campaign Genesis payloads;
- read/create/publish/list APIs with deterministic hashes;
- persisted-definition verification for exact release revision, definition hash, and semantic-interface hash;
- semantic validation of scenario map, spawn, route, object, and hazard references;
- transactional published launch that creates the campaign, exact binding, and initialized starting Campaign Map Instance without World Forge;
- transactional import of a persisted Campaign Bible into an immutable World Revision, World Release, and Scenario Revision;
- preservation of the complete Bible canon, retrieval indexes, completeness and consistency evidence, source Bible revision/hash, generator provenance, source campaign revision/state hash, and source timestamps;
- deterministic, idempotent import identities without mutating or rebinding the legacy campaign;
- explicit non-launch-ready certification until legacy spatial artifacts are compiled and certified.

Exit condition met: manually authored and persisted legacy worlds can be separated from campaigns, published as immutable reusable resources, and either launched from certified spatial releases or held safely for explicit spatial promotion without World Forge during normal launch.

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
- stale-result rejection;
- partial regeneration and reconciliation;
- publication into immutable World Revisions and Releases;
- interruption recovery from persisted completed topics;
- append-only topic-draft snapshots capturing content, directives, dependency hashes, statuses, hashes, provenance, and timestamps;
- optimistic review and rollback that copies a historical draft into a fresh draft revision without mutating source history;
- active-run and stale-current-draft restore guards;
- deterministic parent/root lineage across generation runs for successive draft revisions;
- library and gateway read surfaces for history and lineage;
- PostgreSQL proof that draft 1 survives draft 2 edits, restores into draft 3, and run lineage remains reproducible.

Exit condition met: process interruption can resume without losing completed topics, changed inputs cannot reuse stale outputs, and every draft remains reviewable and restorable through an explicit auditable lineage.

## Phase 4 — Worlds & Campaigns UI

Status: complete

Delivered:

- full-page Worlds and Campaigns library;
- world cards, scenario cards, and campaign cards;
- world/topic authoring surface;
- scenario editor;
- generation progress, lineage, and validation findings;
- immutable map-blueprint draft revisions with content and semantic-interface hashes;
- structured map-blueprint editing with persistent validation;
- unique stable portal, route, spawn, zone, object, and hazard ID validation;
- scenario semantic-ID reconciliation with visible structured findings;
- exclusion of invalid blueprint drafts from immutable World publication;
- publication of ready authored blueprint requirements with exact revision/hash provenance;
- release history and certification status;
- reversible World and Scenario archive/restore controls;
- fast launch from a certified published scenario into an initialized starting map;
- PostgreSQL, semantic route, and web UI proof for invalid-to-corrected blueprint authoring and lifecycle controls.

Exit condition met: an author can create, validate, reconcile, and publish semantic map blueprints, review release and generation history, manage project lifecycle, and launch a certified scenario from one persistent Worlds & Campaigns surface.

## Phase 5 — Starter bubble and progressive maps

Status: complete

Delivered:

- world topology and deferred location slots;
- starting region, settlement, interior, and one neighboring destination;
- simulation and presentation readiness axes;
- deterministic predictive materialization candidate queue;
- explicit deferred-map materialization;
- navigable placeholder rendering while optional art is pending;
- campaign pinning of progressively materialized definitions;
- explicit promotion into a future World Revision;
- deterministic durable materialization jobs keyed by workspace, world revision, and deferred location;
- campaign-proximity scheduling and explicit route-intent signal promotion without duplicate work;
- a dedicated lease-backed internal worker that reuses the authoritative deferred-map materializer;
- non-blocking launch-time predictive scheduling from exact campaign bindings;
- bounded exponential retries, attempt history, terminal failure, and dead-letter recording;
- hidden world and campaign scheduling APIs plus operational counts, attempts, completion, and failure telemetry;
- PostgreSQL proof for duplicate suppression, stronger-signal priority promotion, future-release creation, retries, dead letters, and telemetry.

Exit condition met: deferred maps are predicted, scheduled, retried, materialized, and observed through durable generic jobs while current campaigns remain pinned and optional presentation work remains non-blocking.

## Phase 6 — Living NPC spatial goals and level-of-detail simulation

Status: complete

Delivered:

- immutable move-to-cell NPC spatial goal contracts and stable arbitration;
- active, coarse, and dormant campaign map-instance simulation tiers;
- explicit movement, coarse-cadence, portal-transfer, and blocked-attempt policies;
- PostgreSQL campaign spatial clocks with optimistic serialized ticks;
- durable campaign-owned current NPC goals with optimistic revisions and recorded outcomes;
- deterministic authored routines that emit durable goals at campaign ticks;
- authoritative movement through existing commands and `ActorMovedEvent` records;
- replayable `actor_exited_map` and `actor_entered_map` portal events;
- atomic cross-map source-exit/target-entry transfer across campaign-owned map instances;
- correlated portal transition records without replay-time AI or pathfinding;
- hidden goal, routine, policy, tick, and spatial-state APIs;
- per-tick and aggregate decision, tier, event, transition, routine-emission, and budget-utilization metrics;
- PostgreSQL golden proof for portal approach, atomic transfer, independent replay of both map streams, target-map routine movement, stale-tick rejection, and persisted metrics after reload.

Exit condition met: living NPC spatial intent is campaign-owned, durable, scheduled through a serialized clock, replayable across direct and cross-map movement, authorable as routines, and measurable against explicit level-of-detail budgets.

## Phase 7 — Observer knowledge, detection, and line of sight

Status: complete

Delivered:

- durable observer-owned map knowledge and deterministic observation-event history;
- supercover square-grid line of sight using authoritative terrain `blocks_sight` rules;
- explicit sight and detection radii;
- hidden actor and secret portal, spawn, and zone detection rules;
- remembered terrain and discovered features without retaining stale hidden actor positions;
- explicit unknown-terrain masking;
- complete hazard-authority exclusion from observer projections;
- optimistic knowledge revisions and observation sequences per campaign, map instance, and observer;
- idempotent repeat observations at unchanged map revision and policy;
- hidden observe and safe-projection APIs;
- routing of existing map projections through observer masking;
- deterministic and PostgreSQL proof for LOS, detection, memory, secret redaction, idempotency, observer movement, event history, stale/current map reporting, and hazard exclusion.

Exit condition met: player and NPC observers receive durable, reproducible knowledge projections derived from authoritative map state without receiving omniscient terrain, hidden actors, or hazard authority.

## Phase 8 — Campaign geometry patches

Status: complete

Delivered:

- campaign-owned terrain overrides and applied patch IDs on authoritative map-instance snapshots;
- a shared effective-terrain layer used by movement, weighted pathfinding, portal targets, NPC goal validation, observer LOS, and terrain projections;
- optimistic `ApplyGeometryPatchCommand` resolution and `map_geometry_patched` events;
- deterministic set and clear-to-definition terrain patch semantics;
- stale revision, duplicate command, duplicate patch, duplicate-cell, unknown-terrain, and occupied-actor safety guards;
- persistence through the existing map-event ledger and snapshot compare-and-swap boundary;
- deterministic replay across interleaved geometry and actor-movement events;
- hidden production gateway API for geometry patches;
- PostgreSQL proof that two campaigns sharing one immutable Map Definition remain isolated while only one campaign changes movement and LOS;
- proof that immutable Map Definitions remain unchanged while campaign overlays open and restore terrain.

Exit condition met: campaign-specific geometry can change movement and visibility through recorded optimistic events while shared release-owned definitions stay immutable, cross-campaign state remains isolated, and replay never reruns generation or pathfinding.

## Phase 9 — Tactical spatial systems

Status: complete

### Phase 9.1 — Multi-cell actor footprint authority

Status: complete

Delivered:

- shared rectangular footprint cells using the existing top-left anchor, width, and height actor fields;
- full-footprint map-instance creation validation for bounds, walkability, and actor overlap;
- pathfinder version 2 with full-footprint candidate bounds, effective terrain, occupancy, diagonal-clearance, and maximum-under-footprint terrain costs;
- destination and geometry-patch protection for non-anchor occupied cells;
- full-footprint cross-map portal entry validation;
- observer detection through any visible actor footprint cell;
- unchanged 1x1 actor behavior;
- deterministic proof for edge bounds, overlap, narrow and wide passages, non-anchor collisions, replay, and partial-footprint visibility;
- PostgreSQL proof that a persisted 2x2 actor moves through a valid opening, protects non-anchor cells, reloads unchanged, and replays exactly.

### Phase 9.2 — Tactical budgets, cover, and reactions

Status: complete

Delivered:

- normalized per-combat tactical round state preserved inside the existing campaign combat state;
- deterministic per-round movement, action, and reaction budgets;
- current-initiative actor enforcement for tactical commands;
- movement resolution through existing `MoveActorCommand` and `ActorMovedEvent` authority;
- exact movement-cost budget consumption with over-budget rejection;
- path-derived hostile reaction opportunities when a moving footprint leaves adjacency;
- deterministic reaction ordering by path index, initiative, and actor ID;
- reaction damage resolved through the existing deterministic attack and combat-apply pipeline;
- one reaction consumption per participant per round;
- directional half/full cover derived from effective campaign terrain;
- tactical attack defense modifiers and action-budget consumption;
- stale campaign and map revision guards;
- hidden tactical movement and attack APIs;
- atomic map-event and campaign-turn persistence in one PostgreSQL transaction;
- idempotent duplicate submissions before movement, damage, or budget consumption can rerun;
- deterministic and PostgreSQL proof for budgets, cover, reactions, exact revisions, cross-ledger persistence, and duplicate suppression.

Exit condition met: initiative, movement costs, cover, and reactions share authoritative map and combat state, commit atomically, remain idempotent, and replay without rerunning pathfinding or damage resolution.

## Final phase — Measured performance and renderer escalation

Status: pending audit

- profile spatial runtime and projection costs under representative active, coarse, and tactical workloads;
- persist or expose actionable latency and workload telemetry;
- define evidence-based thresholds for renderer escalation;
- retain the current renderer unless measured limits justify a more complex path.

## Release invariants

- no implicit campaign revision upgrades;
- no cross-campaign mutable map state;
- no secret authority data in player resources;
- no replay-time AI or pathfinding for resolved movement;
- no World Forge calls during normal launch from a ready release;
- no generated image authority over navigation or collision;
- all mutable writes are idempotent and revision checked.
