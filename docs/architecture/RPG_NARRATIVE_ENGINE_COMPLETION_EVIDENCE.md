# Unified RPG Narrative Engine Completion Evidence

Status: implementation complete; pull request remains draft for review  
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

## PostgreSQL migrations

- `0017_rpg_campaign_bible.sql`
- `0018_rpg_world_forge.sql`
- `0019_rpg_hermes_narrative_research.sql`
- `0020_rpg_narrative_responses.sql`

## Production ownership

The foreground RPG gateway now performs the following sequence:

1. execute the authoritative simulation turn;
2. create or adopt one canonical narrative response;
3. derive UI, transcript, TTS, journal, recap, report, and replay views from the canonical blocks;
4. publish through `unified_narrative_engine_v1` only;
5. reject alternate visible publishers;
6. replace compatibility fields from canonical projections only;
7. certify response identity, content hash, block order, save/load, replay, and blocking/deferred equivalence before persistence and response construction.

Legacy compatibility fields remain temporarily available to existing consumers, but they no longer own or generate visible prose.

## Deterministic evidence

The Phase 19 implementation head `67c51cfdb4b335fa273e45eec3b35583cf34135c` passed:

- RPG Phase 0 architecture compliance;
- PostgreSQL persistence gates;
- Live Chat hardening gates;
- RPG deterministic PR gates, including the provider-free 1,000-turn public apply-turn endurance job.

A prior instrumentation run exposed a timing-boundary flake at 94.87% attribution. The framework-overhead finalization margin was corrected and the exact patched head passed all four workflows.

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
- production certification runs before session persistence and response construction.

## Live-provider boundary

GitHub Actions intentionally remain provider-free. Live-provider prose quality and latency must be evaluated locally against the same canonical request, evidence, validation, and publication contracts; no hosted CI result claims live-provider execution.
