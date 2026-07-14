# Unified RPG Narrative Engine Completion Evidence

Status: Milestones A–F implementation complete; pull request remains draft for review  
ADR: `docs/architecture/ADR-0002-unified-rpg-narrative-engine.md`  
Roadmap: `docs/plans/rpg_unified_narrative_engine_roadmap.md`  
Pull request: #1366  
Branch: `agent/rne-milestones-a-d`

## Delivered milestones

| Milestone | Phases | Delivered capability |
|---|---:|---|
| A | 0–8 | isolated contracts, evidence broker, scene detection, beat planning, structured writing, validation, canonical repository, and delivery coordination |
| B | 9–10 | shadow comparison and direct-dialogue canonical cutover |
| C | 11–12 | scene, observation, investigation, travel, stateful action, service, commerce, combat, quest, and failure cutover |
| D | 13–15 | revisioned PostgreSQL Campaign Bible, World Forge approval/audit pipeline, and bounded cited Hermes research |
| E | 16–19 | canonical consumer convergence, save/load and delivery certification, single-publisher enforcement, and fail-closed production certification |
| F | 20–24 | pre-launch Campaign Genesis graph, parallel World Forge generation, audited canon compilation, complete opening dossiers, first-turn readiness enforcement, bounded turn research, and player-safe Lore UX |

## PostgreSQL migrations

- `0017_rpg_campaign_bible.sql`
- `0018_rpg_world_forge.sql`
- `0019_rpg_hermes_narrative_research.sql`
- `0020_rpg_narrative_responses.sql`
- `0021_rpg_campaign_genesis.sql`

## Production ownership

The foreground RPG gateway now performs the following sequence:

1. load the selected session and enforce Campaign Genesis launch readiness when World Forge is enabled;
2. execute the authoritative simulation turn;
3. retrieve at most five permitted Campaign Bible topics for the active scene, speaker, and entities without mutating campaign truth;
4. create or adopt one canonical narrative response;
5. derive UI, transcript, TTS, journal, recap, report, and replay views from the canonical blocks;
6. publish through `unified_narrative_engine_v1` only;
7. reject alternate visible publishers;
8. replace compatibility fields from canonical projections only;
9. certify response identity, content hash, block order, save/load, replay, and blocking/deferred equivalence before persistence and response construction.

Legacy compatibility fields remain temporarily available to existing consumers, but they no longer own or generate visible prose.

## Campaign Genesis and World Forge evidence

Milestone F adds a deterministic pre-generation control plane before any generated prose is accepted:

- Campaign Genesis compiles a validated topic dependency graph and clamps World Forge concurrency;
- quick, standard, and epic depth profiles define bounded targets for lore pages, major NPCs, locations, and factions;
- dependency-ready topics may generate in parallel while launch-required ordering remains deterministic;
- cross-domain relationships are compiled from approved dossiers rather than invented by the narrator;
- contradiction audit emits structured repair patches for date, visibility, knowledge-owner, and relationship defects;
- canon compilation produces revisioned lore documents, atomic facts, relationships, retrieval cards, lexical indexes, and a stable content hash;
- opening NPC and location dossiers are materialized into session state with explicit completeness status;
- the first turn fails closed while launch-required canon, retrieval indexes, opening materialization, or required dossiers are incomplete;
- imported legacy sessions remain compatible, but any explicit dossier is validated and cannot bypass completeness checks;
- Campaign Genesis plans, jobs, audit artifacts, compilation records, and materialization receipts persist through the PostgreSQL `0021` schema when PostgreSQL authority is available.

## Campaign Bible research and Lore evidence

Turn-time research and player-facing Lore use the same revisioned Campaign Bible projection:

- Hermes selects no more than five relevant topics per turn;
- every source carries a Campaign Bible revision citation;
- research is read-only and declares that it may not mutate campaign truth;
- private NPC knowledge is available only when the permitted speaker/knower context allows it;
- canonical generation records the Campaign Bible revision, cited-topic count, and grounding status;
- the Lore list and document APIs filter hidden, private, narrator-only, and game-master pages before returning player data;
- Lore discovery changes are explicit validated transitions persisted into session discovery state;
- the RPG workspace exposes a Lore tab with category browsing, page status, full visible document text, canon revision, known/hidden counts, and World Forge generation evidence;
- new-campaign UI exposes quick, standard, and epic World Forge depth selection while preserving settings-derived defaults.

## Deterministic evidence

The final Milestone F implementation head `d1c91bd347bcc35438b2cf1777f5845b0638ffec` passed all four associated GitHub Actions workflows:

- RPG Phase 0 architecture compliance;
- PostgreSQL persistence gates;
- Live Chat hardening gates;
- RPG deterministic PR gates, including web typecheck, web unit tests, 324 provider-free response-generation tests, representative deterministic smoke coverage, and the 1,000-turn public apply-turn endurance job.

A Phase 22 regression initially exposed that explicit incomplete dossiers in legacy-shaped sessions were being treated as not required. The readiness policy was corrected so legacy sessions without dossiers remain compatible while any explicit dossier must satisfy its required completeness contract.

A later exact-head run exposed a short-request timing flake at 94.95% attribution. The response-header finalizer now recalculates the measured framework remainder through bounded passes rather than relying on one fixed margin. The exact patched head above passed every workflow, including the previously flaky full-path instrumentation assertion.

## Release invariants certified

- one visible publication owner;
- one response ID and content hash per interaction;
- deterministic ordered blocks;
- evidence-backed factual claims;
- pre-generation visibility and knowledge filtering;
- no simulation mutation by narrative code;
- scene changes create required beats;
- blocking and deferred delivery preserve canonical meaning and hash;
- save/load and replay preserve response identity, block order, text, and recomputed hash;
- all downstream presentation views derive from canonical blocks;
- alternate publisher attempts fail closed;
- compatibility fields are projection-only;
- production certification runs before session persistence and response construction;
- World Forge generation follows a validated deterministic dependency graph;
- launch-required canon and opening dossiers are complete before the first turn;
- explicit incomplete dossiers fail readiness checks;
- Campaign Bible research is bounded, cited, visibility-filtered, and read-only;
- player Lore APIs do not expose hidden or game-master canon;
- discovery state changes are explicit and persisted separately from objective canon.

## Live-provider boundary

GitHub Actions intentionally remain provider-free. Live-provider prose quality and latency must be evaluated locally against the same canonical request, evidence, Campaign Bible research, validation, and publication contracts; no hosted CI result claims live-provider execution.
