# RPG World, Scenario, and Spatial Runtime Roadmap

Status: phases 0-3 complete; Phase 6.1 complete; closure work remains in phases 4, 5, 6, and later phases

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
- passing workflows for all implementation heads: RPG Phase 0 architecture compliance, RPG deterministic PR gates, PostgreSQL persistence gates, and Live Chat hardening gates.

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

Status: in progress

Delivered:

- full-page Worlds and Campaigns library;
- world cards, scenario cards, and campaign cards;
- world/topic authoring surface;
- scenario editor;
- generation progress and validation findings;
- map-blueprint requirements summary;
- release history;
- fast launch from a certified published scenario into an initialized starting map.

Remaining:

- editable map-blueprint authoring with validation and persistence;
- visual reconciliation of semantic IDs used by scenarios;
- lifecycle controls for archive and restore.

## Phase 5 — Starter bubble and progressive maps

Status: in progress

Delivered:

- world topology and deferred location slots;
- starting region, settlement, interior, and one neighboring destination;
- simulation and presentation readiness axes;
- deterministic predictive materialization candidate queue;
- explicit deferred-map materialization;
- navigable placeholder rendering while optional art is pending;
- campaign pinning of progressively materialized definitions;
- explicit promotion into a future World Revision.

Remaining:

- durable background materialization jobs created from predictive candidates;
- automatic scheduling based on campaign proximity or route intent;
- retry, failure, and operational telemetry for background materialization.

## Phase 6 — Living NPC spatial goals and level-of-detail simulation

Status: in progress

### Phase 6.1 — Deterministic scheduling foundation

Status: complete

Delivered:

- immutable move-to-cell NPC spatial goal contracts;
- stable goal arbitration by actor, priority, issue tick, and goal ID;
- active, coarse, and dormant map-instance simulation tiers;
- explicit per-tier cadence and actor budgets;
- authoritative movement through existing commands and resolved events;
- typed moved, completed, deferred, dormant, blocked, and already-applied decisions;
- replay proof using recorded movement events without rerunning the scheduler.

Exit condition met: a simulation tick can deterministically schedule living NPC movement at different levels of detail while preserving the existing event and replay authority boundary.

Remaining Phase 6 work:

- durable campaign ownership and persistence of NPC spatial goals;
- campaign clock and tick-loop integration;
- cross-map goals and explicit portal transitions;
- schedule or routine authoring hooks;
- operational metrics and measured budget tuning.

## Later phases

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
