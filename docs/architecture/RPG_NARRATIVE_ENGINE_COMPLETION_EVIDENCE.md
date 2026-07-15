# Unified RPG Narrative Engine Completion Evidence

Status: Milestones A–L implementation complete and merged to `main`  
ADR: `docs/architecture/ADR-0002-unified-rpg-narrative-engine.md`  
Roadmap: `docs/plans/rpg_unified_narrative_engine_roadmap.md`  
Milestones G–L completion: `docs/RPG_NARRATIVE_ENGINE_MILESTONES_G_L_COMPLETION.md`  
Merged pull requests: #1366 and #1367  
Program merge SHA: `dd1483894d1ea9fb22e2f37cf3b5b7c00ebdbf72`

## Delivered milestones

| Milestone | Phases | Delivered capability |
|---|---:|---|
| A | 0–8 | isolated contracts, evidence broker, scene detection, beat planning, structured writing, validation, canonical repository, and delivery coordination |
| B | 9–10 | shadow comparison and direct-dialogue canonical cutover |
| C | 11–12 | scene, observation, investigation, travel, stateful action, service, commerce, combat, quest, and failure cutover |
| D | 13–15 | revisioned PostgreSQL Campaign Bible, World Forge approval/audit pipeline, and bounded cited Hermes research |
| E | 16–19 | canonical consumer convergence, save/load and delivery certification, single-publisher enforcement, and fail-closed production certification |
| F | 20–24 | pre-launch Campaign Genesis graph, parallel World Forge generation, audited canon compilation, complete opening dossiers, first-turn readiness enforcement, bounded turn research, and player-safe Lore UX |
| G–L | 25–42 | typed semantic claims, production structured generation, durable PostgreSQL response authority, atomic persistence, provider-backed World Forge proposals, asynchronous Genesis, resumable delivery, retirement telemetry, legacy deletion audits, and final release certification |

## PostgreSQL migrations

- `0017_rpg_campaign_bible.sql`
- `0018_rpg_world_forge.sql`
- `0019_rpg_hermes_narrative_research.sql`
- `0020_rpg_narrative_responses.sql`
- `0021_rpg_campaign_genesis.sql`
- later Milestones G–L persistence migrations required by canonical responses, Genesis delivery, telemetry, and release certification

## Production ownership

The foreground RPG gateway now performs the following sequence:

1. load the selected session and enforce Campaign Genesis launch readiness when World Forge is enabled;
2. execute the authoritative simulation turn;
3. retrieve at most five permitted Campaign Bible topics for the active scene, speaker, and entities without mutating campaign truth;
4. create or adopt one canonical narrative response;
5. validate typed semantic claims, knowledge grants, visibility, and ordered blocks;
6. persist the authoritative turn and canonical narrative response atomically;
7. derive UI, transcript, TTS, journal, recap, report, replay, and resumed-delivery views from the canonical blocks;
8. publish through `unified_narrative_engine_v1` only;
9. reject alternate visible publishers;
10. replace compatibility fields from canonical projections only;
11. certify response identity, semantic hash, block order, save/load, replay, blocking/deferred equivalence, delivery resume, persistence, and retirement evidence before release.

Legacy compatibility fields remain temporarily available to existing consumers, but they no longer own or generate visible prose.

## Campaign Genesis and World Forge evidence

Milestones F, J, and K provide a deterministic control plane before generated prose becomes canon:

- Campaign Genesis compiles a validated topic dependency graph and clamps World Forge concurrency;
- quick, standard, and epic depth profiles define bounded targets for lore pages, major NPCs, locations, and factions;
- dependency-ready topics may generate in parallel while launch-required ordering remains deterministic;
- provider-backed World Forge output remains a proposal until deterministic validation and commit gates accept it;
- cross-domain relationships are compiled from approved dossiers rather than invented by the narrator;
- contradiction audit emits structured repair patches for date, visibility, knowledge-owner, and relationship defects;
- canon compilation produces revisioned lore documents, atomic facts, relationships, retrieval cards, lexical indexes, and a stable content hash;
- opening NPC and location dossiers are materialized into session state with explicit completeness status;
- asynchronous Genesis supports durable progress, cancellation, retry, recovery, and launch readiness;
- the first turn fails closed while launch-required canon, retrieval indexes, opening materialization, or required dossiers are incomplete;
- imported legacy sessions remain compatible, but any explicit dossier is validated and cannot bypass completeness checks.

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

## Exact-head deterministic evidence

The final Milestone F implementation head `d1c91bd347bcc35438b2cf1777f5845b0638ffec` passed the four associated provider-free GitHub Actions workflows before PR #1366 was reconciled and merged.

The final Milestones G–L implementation head `534ca58ef4abf3f25bdb29e5d72f930c3711357b` passed:

- RPG Phase 0 architecture compliance;
- PostgreSQL persistence gates;
- Live Chat hardening gates;
- RPG deterministic PR gates, including web typecheck, web unit tests, the Phase 25–42 response-generation suite, representative deterministic smoke coverage, and continuous 1,000-turn public apply-turn endurance.

PR #1366 merged as `2a1a4830efc3b4294702df9d960a0aaf42a96b92`. PR #1367 merged as `dd1483894d1ea9fb22e2f37cf3b5b7c00ebdbf72` after the exact validated head above passed all required workflows.

A Phase 22 regression initially exposed that explicit incomplete dossiers in legacy-shaped sessions were being treated as not required. The readiness policy was corrected so legacy sessions without dossiers remain compatible while any explicit dossier must satisfy its required completeness contract.

A later exact-head run exposed a short-request timing flake at 94.95% attribution. The response-header finalizer now recalculates the measured framework remainder through bounded passes rather than relying on one fixed margin. The patched head passed every workflow, including the previously flaky full-path instrumentation assertion.

The final G–L deterministic run also exposed an over-broad source guard that rejected legitimate test-path references containing `response_generation`. The guard was narrowed to reject actual legacy production imports rather than documentation and certification paths, then all required workflows passed on the exact final head.

## Release invariants certified

- one visible publication owner;
- one response ID and semantic hash per interaction;
- deterministic ordered blocks;
- typed evidence-backed factual and knowledge claims;
- pre-generation visibility and knowledge filtering;
- no simulation mutation by narrative code;
- scene changes create required beats;
- blocking and deferred delivery preserve canonical meaning and hash;
- save/load and replay preserve response identity, block order, text, and recomputed hash;
- reconnect resumes persisted delivery state without regenerating prose;
- all downstream presentation views derive from canonical blocks;
- alternate publisher attempts fail closed;
- compatibility fields are projection-only;
- production certification runs before session persistence and response construction;
- World Forge generation follows a validated deterministic dependency graph;
- provider output remains proposal-only until deterministic acceptance;
- launch-required canon and opening dossiers are complete before the first turn;
- explicit incomplete dossiers fail readiness checks;
- Campaign Bible research is bounded, cited, visibility-filtered, and read-only;
- player Lore APIs do not expose hidden or game-master canon;
- discovery state changes are explicit and persisted separately from objective canon;
- production-owner paths contain no legacy publisher imports or visible hooks;
- retirement telemetry records zero alternate publishers and zero deletion violations;
- final certification is bound to external exact-head workflow evidence.

## Live-provider boundary

GitHub Actions intentionally remain provider-free. Live-provider prose quality, browser visibility, and local latency must be evaluated against the same canonical request, evidence, Campaign Bible research, validation, persistence, and publication contracts; no hosted CI result claims live-provider execution.

The operator procedure and aggregate report command are documented in `docs/RPG_LOCAL_RELEASE_QUALIFICATION.md`.
