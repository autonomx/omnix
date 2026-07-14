# Unified RPG Narrative Engine Implementation Roadmap

Status: active implementation source of truth  
ADR: `docs/architecture/ADR-0002-unified-rpg-narrative-engine.md`  
Branch: `agent/rne-milestones-a-d`

## Program objective

Replace fragmented RPG presentation orchestration with one isolated engine that produces ordered, evidence-backed canonical blocks for every player interaction.

## Milestones

### Milestone A — Engine proven in isolation

- Phase 0: ADR, inventory, baseline fixtures, and telemetry
- Phase 1: core contracts and prohibited-import boundary
- Phase 2: ordered renderer and compatibility projections
- Phase 3: evidence broker and handcrafted Bran/Vexira fixtures
- Phase 4: deterministic scene-change detector
- Phase 5: beat planner and adaptive profiles
- Phase 6: structured writer and deterministic writer
- Phase 7: validation, repair, and deterministic fallback
- Phase 8: canonical response repository and delivery coordinator

### Milestone B — First visible replacement

- Phase 9: shadow integration and comparison telemetry
- Phase 10: direct-dialogue cutover

### Milestone C — All turn modes unified

- Phase 11: environmental, observation, investigation, and travel cutover
- Phase 12: stateful actions, services, commerce, party, combat, quests, and failures

### Milestone D — Rich campaign grounding

- Phase 13: PostgreSQL Campaign Bible MVP
- Phase 14: World Forge proposal and contradiction-audit pipeline
- Phase 15: bounded Hermes narrative research

## Required release invariants

- one presentation request per interaction;
- one canonical response ID and content hash;
- explicit block sequence is preserved;
- factual claims reference permitted evidence;
- authority and visibility remain separate;
- knowledge filtering happens before planning and writing;
- narration cannot mutate simulation state;
- no alternate direct-dialogue publisher;
- environment changes create required beats;
- delivery mode does not alter canonical meaning;
- compatibility fields are projections only;
- Narrative Engine imports no legacy prose generators;
- Campaign Bible authority is PostgreSQL-backed and revisioned.

## Phase progress

| Phase | Status | Evidence |
|---:|---|---|
| 0 | in progress | ADR and roadmap added |
| 1 | pending | |
| 2 | pending | |
| 3 | pending | |
| 4 | pending | |
| 5 | pending | |
| 6 | pending | |
| 7 | pending | |
| 8 | pending | |
| 9 | pending | |
| 10 | pending | |
| 11 | pending | |
| 12 | pending | |
| 13 | pending | |
| 14 | pending | |
| 15 | pending | |

## Validation policy

Each phase is committed independently. After each phase, GitHub Actions must complete. Failures caused by the phase are fixed on the same branch before the next phase begins.

Hosted CI remains provider-free. Live-provider prose and latency evaluation is local operational evidence and must not be fabricated in GitHub Actions.

## Legacy deletion follow-up

Milestones A-D establish the replacement and cut over production modes. Full consumer convergence and deletion of legacy generation remain the next milestone and require zero verified production publisher calls, save/load and replay evidence, blocking/deferred hash equivalence, and local provider-backed quality evidence.
