# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg-v1.36`
Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, system design, long-run readiness, production readiness, and commercial/game-quality readiness.

## 1. Target Scorecard

| Category | Current | Target | Production Gate |
|---|---:|---:|---|
| Architecture / system design | 8.0 | 8.5+ | Runtime modularized enough that systems are maintainable and not harness-dependent. |
| LLM grounding / hallucination control | 7.5 | 8.5+ | Final visible state-claim validator passes matrix/autoplay with zero critical state contradictions. |
| Runtime performance architecture | 7.0 | 8.5+ | Fast buckets <0.15s; first-call average <2.5s; p95 bounded and explained. |
| Testability / diagnostics | 8.0 | 9.0+ | Matrix, manual, autoplay, save/load, and report gates run predictably with source-backed failures. |
| Core gameplay mechanics | 4.5 | 8.0+ | Combat, economy, travel, quests, party, inventory, XP, and survival all have complete loops. |
| Game design / player experience | 4.0 | 8.0+ | 30-60 minute vertical slice is coherent, fun, visible, and replayable. |
| NPC roleplay potential | 6.5 | 8.5+ | NPC profiles, memory, relationships, schedules, and evolution persist and affect play. |
| 100-turn readiness | 5.0 | 8.0+ | 100-turn run completes with zero critical warnings and useful progression. |
| 1000-turn readiness | 2.5 | 8.0+ | 1000-turn run completes with bounded reports, compression, memory aging, and no collapse. |
| Production readiness | 3.0 | 8.0+ | Install/run/config/save/load/error handling are player-safe. |
| Commercial/game-quality readiness | 2.5 | 8.0+ | Enough content, polish, UX, stability, and onboarding for external users. |

## 2. Roadmap Principles

1. Deepen existing systems before adding new broad systems.
2. Keep deterministic runtime authoritative.
3. Keep LLM advisory/presentation-only.
4. Keep harnesses out of gameplay routing.
5. Every fallback, repair, and provider decision needs a source.
6. Every phase must end with tests, matrix run, and report review.
7. Build toward one strong vertical slice first, then scale.
8. Production readiness means player experience, not only tests passing.

## 3. Phase 0 — Architecture Compliance and Baseline Hardening

Goal: lock the current architecture so future work does not regress CE.2.12/CE.2.13.

### Scope

- Add architecture compliance checks.
- Assert all interactive/manual matrix turns use `interactive_first_call_runtime.apply_turn` unless explicitly marked legacy.
- Assert no harness-owned fast gameplay routing returns.
- Assert source fields exist for fallbacks and repairs.
- Assert stateful first-call visible responses cannot mutate state.
- Add final-result hard-state-claim audit scaffolding.

### Exit Criteria

- CE.2.12 tests pass.
- CE.2.13 tests pass.
- Architecture compliance tests pass.
- Interactive matrix remains 8/8.
- No `fast_direct_canonical_runtime` traces.

### Target Score Impact

- Architecture: 8.0 -> 8.3
- Grounding: 7.5 -> 7.8
- Diagnostics: 8.0 -> 8.3

## 4. Phase 1 — Combat Lifecycle v2

Goal: turn combat from a fast scenario mechanic into a real RPG loop.

### Scope

- Initiative and turn order.
- Enemy turns.
- Hit/miss/crit rules.
- Weapon damage and armor/defense.
- Player actions: attack, block, dodge, parry, use item, flee.
- Companion combat participation.
- Multiple enemies.
- Downed/defeated/dead states.
- Escape/surrender/social resolution hooks.
- XP and loot hooks.
- Combat log payload and UI/report section.
- Deterministic combat seed support.
- Fast-mode provider skip remains intact.

### Tests

- Unit tests for hit/miss/crit/damage.
- Combat lifecycle manual scenarios.
- Matrix combat scenario expanded from repeated attack to full lifecycle.
- Report validates HP before/after, actor, target, enemy turn, defeat, XP/loot.

### Exit Criteria

- Combat scenario remains <0.25s average in fast mode.
- No combat narration provider calls in fast mode.
- Combat has enemy turns and final victory/defeat outcome.
- XP/loot hooks are deterministic.
- Combat log is visible in report/UI payload.

### Target Score Impact

- Core mechanics: 4.5 -> 5.8
- Game design: 4.0 -> 4.8
- 100-turn readiness: 5.0 -> 5.7

## 5. Phase 2 — Economy, Inventory, Services, and Survival v2

Goal: make shops, inns, food, water, rest, and inventory function as coherent systems.

### Scope

- Canonical item database.
- Item IDs, display names, tags, stackability, value, weight if used.
- Merchant stock and quantities.
- Buy/sell rules.
- Room/rest service effects.
- Food/water consumption effects.
- Currency normalization: gold/silver/copper.
- Price modifiers from charisma, reputation, relationship, scarcity.
- Transaction logs.
- Inventory UI/report table.
- Starter loadout and starting currency.
- Survival pressure tuning.

### Tests

- Buy/sell success/failure.
- Insufficient funds.
- Stock depletion.
- Inn room purchase and rest effect.
- Ration/water consumption.
- Currency normalization.
- Inventory persistence through save/load.

### Exit Criteria

- Player can buy food, rent a room, rest, consume food/water, sell item, and see inventory/currency changes.
- Economy report shows transactions and deltas.
- No LLM-invented prices or stock.

### Target Score Impact

- Core mechanics: 5.8 -> 6.5
- Game design: 4.8 -> 5.6
- 100-turn readiness: 5.7 -> 6.2

## 6. Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2

Goal: support complete quest chains rather than only inquiry/no-backed-state behavior.

### Scope

- Quest template schema.
- Quest giver state.
- Objective creation, update, completion, and failure.
- Journal entries: what happened, what I learned, next objective.
- Reward rules.
- Rumor-to-quest conversion.
- Backed rumor propagation.
- Work inquiry routing.
- Objective suggestions.
- Quest report section.

### Tests

- Ask for quest when none exists: no-backed-state.
- Ask for quest when backed quest exists: quest offered.
- Accept quest.
- Advance objective.
- Complete quest.
- Receive reward.
- Rumor creates lead without inventing quest.
- Journal updates correctly.

### Exit Criteria

- One complete quest chain can be played end-to-end.
- Quest state survives save/load.
- Journal clearly shows current objective.
- Matrix includes at least one backed quest path in addition to no-backed-state.

### Target Score Impact

- Core mechanics: 6.5 -> 7.0
- Game design: 5.6 -> 6.4
- 100-turn readiness: 6.2 -> 6.8

## 7. Phase 4 — Travel Graph, Locations, Time, and Encounters v2

Goal: make the world navigable and stateful rather than scenario-only.

### Scope

- Canonical location graph.
- Location IDs, names, descriptions, services, NPCs, hazards, exits.
- Travel time and fatigue/resource costs.
- Discovery state.
- Random/seeded encounters.
- Route blocking/unblocking.
- Local world events by location.
- Location history in report.
- Map/location UI payload.
- Time of day, day count, optional season/weather hooks.

### Tests

- Valid route travel.
- Invalid route rejection.
- Route discovery.
- Encounter trigger from seeded travel.
- Location services/NPC presence update.
- Save/load preserves location and travel state.

### Exit Criteria

- Player can traverse at least 5 connected locations in the vertical slice.
- Travel has visible costs/consequences.
- Location report shows where the player went and what happened.

### Target Score Impact

- Core mechanics: 7.0 -> 7.4
- Game design: 6.4 -> 6.9
- 100-turn readiness: 6.8 -> 7.2
- 1000-turn readiness: 2.5 -> 3.5

## 8. Phase 5 — NPC Profiles, Memory, Relationships, Schedules, and Evolution v2

Goal: make NPCs feel persistent and alive.

### Scope

- File-backed profiles for major NPCs: Bran, Elara, Aldric, bandit leader, companion candidates.
- Biography, personality, voice, speech examples, secrets, values, fears.
- Relationship scoring.
- Memory aging and importance scoring.
- Memory summarization.
- NPC schedules and location movement.
- NPC goals/agency basics.
- NPC-to-NPC conversation hooks.
- Evolution arcs: Bran tavern loss -> companion/adventurer path.
- Companion personality state changes.

### Tests

- NPC profile loads into grounding packet.
- NPC remembers prior player action.
- Relationship changes after kindness/threat/purchase/quest/combat.
- NPC refuses unsupported/private knowledge.
- Evolution arc triggers only from backed event.
- Schedule changes NPC location.
- Save/load preserves profile evolution and memory.

### Exit Criteria

- At least 5 major NPCs have rich profiles.
- NPC memory affects dialogue in later turns.
- At least one NPC evolution arc works end-to-end.
- No fake environment memories.

### Target Score Impact

- NPC roleplay: 6.5 -> 8.0
- Game design: 6.9 -> 7.4
- 100-turn readiness: 7.2 -> 7.6
- 1000-turn readiness: 3.5 -> 4.8

## 9. Phase 6 — Vertical Slice: Rusty Flagon Production Loop

Goal: create a 30-60 minute coherent playable slice.

### Slice Content

```text
Rusty Flagon Tavern
  -> Bran innkeeper
  -> Elara merchant
  -> Captain Aldric / local authority
  -> road to old mill
  -> bandit encounter
  -> food + room service
  -> rumor lead
  -> quest offer
  -> travel route
  -> combat
  -> companion recruitment
  -> journal updates
  -> save/load checkpoint
```

### Required Player Loops

- Talk to Bran with persona-rich dialogue.
- Buy food/water from merchant or tavern.
- Rent room/rest.
- Ask for work/rumors.
- Accept quest.
- Travel to old mill route.
- Fight bandit.
- Return/report result.
- Recruit companion or deepen relationship.
- See journal/objective updates.
- Save/load without losing state.

### Exit Criteria

- Human can play 30-60 minutes without debug knowledge.
- No critical state hallucinations.
- No blocking turn above defined p95 budget without clear provider reason.
- Reports show coherent story, location, quest, combat, economy, party, and NPC state.

### Target Score Impact

- Game design: 7.4 -> 8.0
- Core mechanics: 7.4 -> 8.0
- Production readiness: 3.0 -> 5.0
- Commercial readiness: 2.5 -> 4.5

## 10. Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate

Goal: make 100-turn campaigns reliable.

### Scope

- Save/load checkpoint validation.
- Replay determinism checks.
- State diff validation.
- Loop detection.
- Progress metrics.
- Report growth budget enforcement.
- Critical warning severity categories.
- 100-turn readiness report.

### Tests

- Save/load after combat.
- Save/load after quest acceptance/completion.
- Save/load after companion recruitment.
- Save/load after NPC memory/evolution.
- Replay deterministic state deltas.
- 100-turn run with zero critical warnings.

### Exit Criteria

- 100-turn autoplay completes.
- No critical warnings.
- Save/load checkpoints pass.
- Report is bounded and readable.
- Progress metrics show meaningful gameplay coverage.

### Target Score Impact

- 100-turn readiness: 7.6 -> 8.2
- Production readiness: 5.0 -> 5.8
- Architecture: 8.3 -> 8.5

## 11. Phase 8 — UI/UX Production Pass

Goal: make the game playable without reading debug reports.

### Scope

- Current objective panel.
- Suggested actions.
- Inventory/currency panel.
- Combat log and combat state panel.
- Party panel.
- Journal panel.
- Map/location panel.
- NPC relationship/memory summary panel.
- Save/load controls.
- Provider/narration/media settings.
- Error/retry/fallback user messages.
- Accessibility/readability pass.

### Tests

- UI smoke tests for panels.
- Human-play transcript review.
- Save/load from UI.
- Combat UI flow.
- Journal/objective visibility.

### Exit Criteria

- Player can understand state and next choices without debug artifacts.
- UI exposes all major RPG state.
- Errors are recoverable and understandable.

### Target Score Impact

- Game design: 8.0 -> 8.4
- Production readiness: 5.8 -> 7.0
- Commercial readiness: 4.5 -> 6.0

## 12. Phase 9 — 1000-Turn Endurance Systems

Goal: make long-run play stable.

### Scope

- World-state compression/summarization.
- Memory aging and importance compaction.
- Long-term economy/resource pressure.
- NPC schedules and agency expansion.
- Faction/reputation consequences.
- Story arc completion/failure rules.
- Campaign end-state detection.
- Long-run report segmentation.
- Automated evals for coherence and repetition.

### Tests

- 250-turn endurance.
- 500-turn endurance.
- 1000-turn endurance.
- Memory compression validation.
- Report size budget validation.
- Long-run loop/repetition detection.

### Exit Criteria

- 1000-turn run completes.
- Report size is bounded.
- No runaway memory/transcript growth.
- Story/world progression remains coherent.
- NPC memory remains useful and non-bloated.

### Target Score Impact

- 1000-turn readiness: 4.8 -> 8.0
- Production readiness: 7.0 -> 7.6
- NPC roleplay: 8.0 -> 8.5

## 13. Phase 10 — Production Packaging, Stability, and Release Readiness

Goal: reach production-quality operation.

### Scope

- Installation/run scripts.
- Environment validation.
- Provider setup wizard or clear settings UX.
- Model/provider fallback behavior.
- Crash recovery.
- Save backup/restore.
- Content versioning and migration.
- Privacy/security review for local files and provider calls.
- Performance profiles for local and remote providers.
- Player onboarding/tutorial.
- Mod/content authoring structure.
- Release checklist.

### Tests

- Fresh install smoke test.
- Missing provider graceful fallback.
- Corrupt save recovery.
- Migration test.
- Performance profile tests.
- End-to-end vertical slice from fresh install.

### Exit Criteria

- New user can install, configure, start, save/load, and play vertical slice.
- Errors do not corrupt state.
- Settings are understandable.
- Release checklist passes.

### Target Score Impact

- Production readiness: 7.6 -> 8.2
- Commercial readiness: 6.0 -> 8.0

## 14. Phase Gates Summary

| Phase | Main Gate | Main Score Lift |
|---|---|---|
| 0 | Architecture compliance | Architecture/grounding |
| 1 | Combat lifecycle | Mechanics |
| 2 | Economy/inventory/survival | Mechanics/game loop |
| 3 | Quest/journal/rumor lifecycle | Game design/progression |
| 4 | Travel/location graph | World/game design |
| 5 | NPC memory/evolution | NPC roleplay |
| 6 | 30-60 min vertical slice | Game design/mechanics |
| 7 | 100-turn reliable run | Reliability/readiness |
| 8 | UI/UX production pass | Player experience |
| 9 | 1000-turn endurance | Long-run readiness |
| 10 | Packaging/stability/release | Production/commercial readiness |

## 15. Suggested Immediate Next Bundles

### Bundle PR.0 — Architecture Compliance Audit

- Assert matrix/manual use `interactive_first_call_runtime`.
- Assert harness gameplay routing does not return.
- Assert fallback source fields exist.
- Add stateful visible-response no-mutation regression.

### Bundle PR.1 — Combat Lifecycle Foundation

- Add initiative, enemy turn skeleton, combat log schema, XP/loot hooks.
- Keep fast combat provider skip intact.

### Bundle PR.2 — Economy Item Database

- Add canonical item database.
- Add merchant stock and starter inventory/currency.
- Add buy/sell transaction report rows.

### Bundle PR.3 — Vertical Slice Content Skeleton

- Define Rusty Flagon, road, old mill, market.
- Define Bran, Elara, Aldric, road bandit profiles.
- Define one quest chain and one rumor lead.

## 16. Definition of 8/10 Production Readiness

The project reaches the target when:

1. A new player can play a 30-60 minute vertical slice without debug knowledge.
2. Matrix and manual tests pass.
3. 100-turn autoplay passes with zero critical warnings.
4. 1000-turn endurance passes with bounded reports.
5. Save/load works across combat, quest, NPC memory, party, travel, and economy.
6. NPCs have persistent memory and evolving profiles.
7. Combat, economy, quest, travel, party, and survival loops are complete.
8. Final narration has no critical unsupported state claims.
9. UI clearly shows player state, objective, journal, combat, inventory, party, map, and settings.
10. Install/config/error handling is stable enough for external users.

## 17. Revisit Process

Every major milestone should update:

- `docs/rpg_evaluation_snapshot.md`
- `docs/rpg_architecture.md`
- this roadmap
- latest matrix report
- latest 100-turn report
- latest endurance report when available

Each revisit should answer:

```text
What improved?
What regressed?
Which score changed?
Which phase gate is now complete?
What is the next highest-leverage blocker?
```
