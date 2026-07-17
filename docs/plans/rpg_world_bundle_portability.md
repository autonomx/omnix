# RPG World Bundle Portability

Status: complete — reusable worlds, maps, scenarios, publication history, and images can be exported and imported as one validated archive

Related architecture and roadmap:

- `docs/architecture/ADR-0003-rpg-world-scenario-map-architecture.md`
- `docs/plans/rpg_world_scenario_map_roadmap.md`

Implementation evidence:

- implementation PR: `#1410`;
- implementation merge SHA: `0110c9dccff0e6f51c54d24a1521dcde7fd54888`;
- exact implementation head verified by GitHub Actions: `d36b1436ee5a7b38287cf3be0beb6d3513e48dc3`;
- the exact head passed RPG Phase 0 architecture compliance, RPG deterministic PR gates, PostgreSQL persistence gates, and Live Chat hardening gates.

## Objective

Make reusable RPG worlds portable between Omnix installations without weakening immutable publication authority, semantic map identity, asset integrity, or campaign isolation.

## Portable archive

World export produces a versioned `.omnix-world.zip` archive containing:

- a canonical manifest and canonical world payload;
- the World Project;
- current topic drafts;
- append-only topic history;
- World Forge generation-run lineage and historical status;
- every immutable World Revision;
- every immutable World Release;
- every Scenario Project and Scenario Revision owned by the world;
- every map-blueprint revision;
- every compiled authoritative Map Definition owned by the world;
- image assets referenced by exported world/map/scenario data;
- image assets explicitly tagged to the exported world or one of its maps.

Campaign-owned mutable authority is intentionally excluded:

- campaigns and campaign state;
- Campaign Map Instances;
- campaign map events and geometry overlays;
- turns, interactions, snapshots, and saves;
- observer knowledge and campaign-owned NPC spatial state.

This keeps the archive a reusable authoring and publication resource rather than a campaign-save transfer format.

## Integrity and security

Delivered safeguards:

- canonical JSON encoding;
- SHA-256 payload and image checksums;
- explicit archive format and version validation;
- safe archive-path validation with traversal rejection;
- compressed and uncompressed size limits;
- per-entry, entry-count, and image-count limits;
- supported-image MIME validation;
- rejection of missing referenced images;
- rejection of missing or empty physical image files;
- validation of the complete archive before durable world writes begin;
- cleanup of newly installed image assets when the database import transaction fails.

## Import semantics

Import behavior:

- never overwrites an existing target World Project;
- imports under the source world ID when that ID is unused;
- accepts an optional target world ID for portable clone creation;
- deterministically remaps conflicting world, map, scenario, generation-run, and image IDs;
- rewrites nested references consistently across world, map, scenario, release, topic, and asset metadata;
- rebuilds map-blueprint content and semantic-interface hashes;
- rebuilds immutable World Revision hashes;
- rebuilds compiled Map Definition and semantic-interface hashes;
- rebuilds Scenario Revision hashes;
- rebuilds topic content and input hashes;
- certifies each imported release against the exact `(map_id, definition_revision)` pinned by that release;
- rebuilds World Release certification and release hashes;
- preserves historical generation lineage without restoring generic execution jobs;
- converts exported planned or running generation runs into canceled historical records so they cannot resume against missing execution leases.

## APIs and user interface

Delivered surfaces:

- hidden raw-ZIP export API: `GET /api/rpg/worlds/{world_id}/export`;
- hidden raw-ZIP import API: `POST /api/rpg/worlds/import`;
- optional `target_world_id` query parameter for clone import;
- Worlds & Campaigns overlay controls for browser export download;
- archive selection and optional clone-world ID controls for import;
- visible success and failure feedback including imported map and image counts.

Raw ZIP request bodies are used so world import does not depend on multipart form parsing.

## Verification

Deterministic verification covers:

- archive build and parse round trips;
- checksum rejection;
- unsafe archive-path rejection;
- deterministic clone-ID remapping;
- rebuilt world, map, release, scenario, and topic hashes;
- hidden and idempotent gateway route registration;
- browser export download behavior;
- browser clone-import behavior.

PostgreSQL verification covers a published source world containing:

- a current topic and topic-history snapshot;
- a ready map blueprint;
- a compiled authoritative grid Map Definition;
- a World Revision and certified World Release;
- a Scenario Project and Scenario Revision;
- a real PNG byte payload in the shared asset store.

The golden round trip proves that the archive imports as a separate clone with remapped identifiers, valid immutable hashes, intact image bytes, and unchanged source-world state. A repeated import into the same target world is rejected without adding new image assets.

## Completion condition

World portability is complete when a reusable published world can move between installations with its authoring history, maps, scenarios, releases, and images intact; imported authority validates under the destination identifiers; existing worlds are never overwritten; and campaign-owned mutable state remains outside the bundle.

That condition is met.
