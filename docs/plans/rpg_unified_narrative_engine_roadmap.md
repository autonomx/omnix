# Unified RPG Narrative Engine Implementation Roadmap

Status: Milestones A–F implementation complete; awaiting pull-request review  
ADR: `docs/architecture/ADR-0002-unified-rpg-narrative-engine.md`  
Completion evidence: `docs/architecture/RPG_NARRATIVE_ENGINE_COMPLETION_EVIDENCE.md`  
Branch: `agent/rne-milestones-a-d`

## Program objective

Replace fragmented RPG presentation orchestration with one isolated engine that produces ordered, evidence-backed canonical blocks for every player interaction, grounded in a generated and revisioned Campaign Bible before the first turn begins.

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

### Milestone E — Consumer convergence and legacy retirement

- Phase 16: UI, TTS, transcript, journal, recap, report, and replay projections converge on canonical blocks
- Phase 17: save/load, replay, and blocking/deferred content-hash certification
- Phase 18: zero-legacy-publisher telemetry and architecture enforcement
- Phase 19: retire alternate presentation ownership and certify the final production path

### Milestone F — Campaign Genesis, World Forge, and Lore experience

- Phase 20: Campaign Genesis topic graph, dependency ordering, and quick/standard/epic depth profiles
- Phase 21: parallel World Forge generation, cross-domain relationship compilation, contradiction audit, and canonical compilation
- Phase 22: session materialization, complete opening NPC/location dossiers, PostgreSQL genesis persistence, and first-turn launch gate
- Phase 23: bounded read-only Campaign Bible research for live turns with at most five cited topics and player-safe knowledge filtering
- Phase 24: live generation progress routes, player-safe Lore browser, full-page retrieval, and explicit discovery-state transitions

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
- Campaign Bible authority is PostgreSQL-backed and revisioned;
- every downstream presentation consumer derives from canonical blocks;
- persisted and replayed responses preserve response ID, block order, and content hash;
- production publishing records zero alternate legacy publisher calls;
- World Forge prose is generated only after a deterministic dependency graph is validated;
- first-turn execution is blocked until launch-required canon, indexes, and opening dossiers are audited and materialized;
- an explicit NPC or location dossier is never treated as ready while required fields are incomplete;
- turn-time Campaign Bible research is bounded, cited, read-only, and filtered by visibility and character knowledge;
- player Lore APIs never expose hidden, private, narrator-only, or game-master canon;
- Lore discovery transitions are explicit, validated, and persisted without rewriting objective canon.

## Phase progress

| Phase | Status | Evidence |
|---:|---|---|
| 0 | complete | ADR, roadmap, baseline inventory, and telemetry |
| 1 | complete | isolated contracts and prohibited-import architecture gate |
| 2 | complete | ordered renderer and compatibility projections |
| 3 | complete | evidence broker plus Bran/Vexira fixtures |
| 4 | complete | deterministic scene-change detector |
| 5 | complete | adaptive profiles and deterministic beat planner |
| 6 | complete | structured and provider-free deterministic writers |
| 7 | complete | fail-closed validation, bounded repair, and fallback |
| 8 | complete | canonical repository and blocking/deferred delivery |
| 9 | complete | sampled shadow generation and diagnostics |
| 10 | complete | direct-dialogue canonical cutover |
| 11 | complete | environment, observation, investigation, and travel cutover |
| 12 | complete | remaining stateful and resolved turn modes cut over |
| 13 | complete | revisioned PostgreSQL Campaign Bible and evidence adapter |
| 14 | complete | reviewable World Forge proposals and contradiction audit |
| 15 | complete | bounded cited read-only Hermes narrative research |
| 16 | complete | canonical consumer bundle and gateway/session publication |
| 17 | complete | PostgreSQL canonical response repository and replay/delivery certification |
| 18 | complete | guarded canonical publisher, zero-alternate telemetry, and static ownership audit |
| 19 | complete | fail-closed final path certification and projection-only compatibility retirement |
| 20 | complete | deterministic Campaign Genesis topic graph and generation-depth policy |
| 21 | complete | parallel World Forge generation, cross-linking, audit, and canonical compilation |
| 22 | complete | genesis persistence, session materialization, dossier readiness, and first-turn launch gate |
| 23 | complete | bounded cited Campaign Bible research integrated into canonical turn generation |
| 24 | complete | generation progress API, player-safe Lore browser, document retrieval, and discovery transitions |

## Validation policy

Each phase was committed independently. After every phase, GitHub Actions completed; failures caused by the phase were fixed on the same branch before work continued.

Hosted CI remains provider-free. Live-provider prose and latency evaluation is local operational evidence and must not be fabricated in GitHub Actions.

## Legacy retirement policy

Legacy compatibility fields may remain only as projections from the canonical response while downstream callers migrate. No legacy generator owns visible production prose. The production gateway rejects alternate publishers and certifies canonical response identity, hash, block order, replay, persistence, and delivery equivalence before publishing.

## Campaign Genesis launch policy

Campaigns without World Forge metadata remain compatible with the legacy launch path. Once World Forge or a Campaign Bible is present, the first turn fails closed until launch-required topics, consistency audit, retrieval indexes, opening materialization, and required dossiers are complete. Explicit dossiers are validated even when imported into an otherwise legacy session.
