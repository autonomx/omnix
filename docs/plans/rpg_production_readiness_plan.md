# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-02

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 2 — Economy, Inventory, Services, and Survival v2**.

Next recommended slice: **Phase 2.6 — inventory persistence through save/load**.

Latest completed PRs:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #141 Phase 0 provider boundary static gate | `9ccca09d9636dc8d035c640c3ec1ef9955c6a08f` | Phase 0 | Complete | Provider-boundary static scan, runtime manifest hardening, Phase 0 and deterministic gates passed. |
| #142 Phase 2 starter loadout economy gate | `792451adabda3bdf96f18b41d135052b91285eac` | Phase 2 | Complete | Starter loadout, canonical starting 15 silver, starter items, idempotency/preservation, Phase 2 CI gate. |
| #143 Phase 2.2 merchant commerce runtime | `ab26de192e8f3536756b42a218135e1fdb2a8834` | Phase 2 | Complete | Merchant inventory, deterministic buy/sell runtime, player currency/inventory changes, transaction logs. |
| #144 Phase 2.3 economy report guardrails | `de8d2e06713b57e7eeceef116d11ebc4e7bf1340` | Phase 2 | Complete | Economy transaction report rows, campaign report injection, deterministic price/merchant-state presentation guardrails. |
| #145 Phase 2.4 inn room rest services | `8b472d9511ed752a51e793eb61cfb5123722dfb8` | Phase 2 | Complete | Deterministic inn room/rest runtime, Bran/Rusty Flagon 5 silver room price, HP/fatigue/rest state effects, insufficient-funds rejection, Phase 2 economy gate passed. |
| #146 Phase 2.5 ration water survival pressure | `6f4b9200bd79e27ad32473d959034bcd43dffc20` | Phase 2 | Complete | Deterministic ration/water consumption, canonical survival items, survival pressure state, source-backed survival log, Phase 0 and deterministic gates passed. |

After every merged PR:

- [ ] Update this handoff section with PR number, merge SHA, and validation result.
- [ ] Mark completed phase checklist items below.
- [ ] Update the next recommended slice.
- [ ] Keep this planning doc on `rpg` so future sessions can resume from source control.

## Target Scorecard

| Category | Current | Target | Production Gate |
|---|---:|---:|---|
| Architecture / system design | 8.3 | 8.5+ | Runtime modularized enough that systems are maintainable and not harness-dependent. |
| LLM grounding / hallucination control | 7.9 | 8.5+ | Final visible state-claim validator passes matrix/autoplay with zero critical state contradictions. |
| Runtime performance architecture | 7.0 | 8.5+ | Fast buckets <0.15s; first-call average <2.5s; p95 bounded and explained. |
| Testability / diagnostics | 8.5 | 9.0+ | Matrix, manual, autoplay, save/load, and report gates run predictably with source-backed failures. |
| Core gameplay mechanics | 6.2 | 8.0+ | Combat, economy, travel, quests, party, inventory, XP, and survival all have complete loops. |
| Game design / player experience | 5.2 | 8.0+ | 30-60 minute vertical slice is coherent, fun, visible, and replayable. |
| NPC roleplay potential | 6.5 | 8.5+ | NPC profiles, memory, relationships, schedules, and evolution persist and affect play. |
| 100-turn readiness | 6.0 | 8.0+ | 100-turn run completes with zero critical warnings and useful progression. |
| 1000-turn readiness | 2.5 | 8.0+ | 1000-turn run completes with bounded reports, compression, memory aging, and no collapse. |
| Production readiness | 3.4 | 8.0+ | Install/run/config/save/load/error handling are player-safe. |
| Commercial/game-quality readiness | 2.9 | 8.0+ | Enough content, polish, UX, stability, and onboarding for external users. |

## Roadmap Principles

1. Deepen existing systems before adding broad systems.
2. Keep deterministic runtime authoritative.
3. Keep LLM advisory/presentation-only.
4. Keep harnesses out of gameplay routing.
5. Every fallback, repair, and provider decision needs a source.
6. Every phase must end with tests, matrix run, and report review.
7. Build toward one strong vertical slice first, then scale.
8. Production readiness means player experience, not only tests passing.

## Phase 0 — Architecture Compliance and Baseline Hardening

Status: **Mostly complete / guardrail active**.

### Scope

- [x] Add architecture compliance checks.
- [ ] Assert all interactive/manual matrix turns use `interactive_first_call_runtime.apply_turn` unless explicitly marked legacy.
- [ ] Assert no harness-owned fast gameplay routing returns.
- [ ] Assert source fields exist for fallbacks and repairs.
- [ ] Assert stateful first-call visible responses cannot mutate state.
- [ ] Add final-result hard-state-claim audit scaffolding.
- [x] Add deterministic provider-boundary static scan for RPG deterministic roots.
- [x] Harden runtime wrapper manifest/combat contract module checks.

### Exit Criteria

- [ ] CE.2.12 tests pass.
- [ ] CE.2.13 tests pass.
- [x] Architecture compliance tests pass.
- [ ] Interactive matrix remains 8/8.
- [ ] No `fast_direct_canonical_runtime` traces.

## Phase 1 — Combat Lifecycle v2

Status: **Materially complete enough to proceed to Phase 2; remaining items are polish/depth.**

### Scope

- [x] Initiative and turn order.
- [x] Enemy turns / NPC combat turn support exists in current combat modules.
- [~] Hit/miss/crit rules. Hit/miss and damage are present; crit coverage remains to verify/complete.
- [x] Weapon damage and armor/defense.
- [~] Player actions: attack, block, dodge, parry, use item, flee. Attack/gating/flee/defense hooks exist; full action depth remains to verify.
- [x] Companion combat participation support exists.
- [x] Multiple enemies support exists through encounter/enemy list inputs.
- [~] Downed/defeated/dead states. Defeated and end-state handling exist; downed/dead depth remains to verify.
- [~] Escape/surrender/social resolution hooks. Flee/social hooks exist but need vertical-slice validation.
- [x] XP and loot hooks.
- [x] Combat log payload and report/contract visibility.
- [x] Deterministic combat seed support.
- [x] Fast-mode provider skip remains intact.

### Remaining Phase 1 backlog

- [ ] Add/verify crit-specific deterministic gate.
- [ ] Add/verify full enemy-turn automation gate.
- [ ] Add/verify player combat action variety beyond attack in manual/matrix scenarios.

## Phase 2 — Economy, Inventory, Services, and Survival v2

Status: **In progress. Starter loadout, merchant commerce, economy report guardrails, inn/rest services, and survival consumption/pressure are merged.**

### Scope

- [x] Canonical item database.
- [x] Item IDs, display names, tags, stackability, value, weight if used.
- [x] Merchant stock and quantities.
- [x] Buy/sell rules.
- [x] Room/rest service effects.
- [x] Food/water consumption effects.
- [x] Currency normalization: gold/silver/copper.
- [ ] Price modifiers from charisma, reputation, relationship, scarcity.
- [x] Transaction logs.
- [~] Inventory UI/report table. Economy transaction report rows are present; full inventory UI/report remains.
- [x] Starter loadout and starting currency.
- [x] Survival pressure tuning.

### Tests

- [x] Buy/sell success/failure.
- [x] Insufficient funds.
- [x] Stock depletion.
- [x] Inn room purchase and rest effect.
- [x] Ration/water consumption.
- [x] Currency normalization.
- [ ] Inventory persistence through save/load.
- [x] Starter loadout grants canonical starting currency/items and is idempotent.
- [x] Starter loadout preserves existing inventory/currency.
- [x] Economy report shows deterministic transaction rows.
- [x] Economy report includes deterministic price/merchant-state presentation guardrails.

### Exit Criteria

- [~] Player can buy food, rent a room, rest, consume food/water, sell item, and see inventory/currency changes. Commerce/report/rest/consumption deltas are covered; save/load persistence remains.
- [x] Economy report shows transactions and deltas.
- [x] No LLM-invented prices or stock in economy report guardrails.

### Completed Phase 2 slices

- Phase 2.1 / PR #142 — deterministic starter loadout runtime and CI gate.
- Phase 2.2 / PR #143 — merchant inventory and commerce runtime.
- Phase 2.3 / PR #144 — economy transaction report rows and deterministic presentation guardrails.
- Phase 2.4 / PR #145 — deterministic inn room/rest service effects.
- Phase 2.5 / PR #146 — deterministic ration/water consumption and survival pressure tuning.

### Next Phase 2 slices

1. Phase 2.6 — inventory persistence through save/load.
2. Phase 2.7 — price modifiers from charisma/reputation/relationship/scarcity.

## Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2

Status: **Pending.**

- [ ] Quest template schema.
- [ ] Quest giver state.
- [ ] Objective creation, update, completion, and failure.
- [ ] Journal entries: what happened, what I learned, next objective.
- [ ] Reward rules.
- [ ] Rumor-to-quest conversion.
- [ ] Backed rumor propagation.
- [ ] Work inquiry routing.
- [ ] Objective suggestions.
- [ ] Quest report section.

## Phase 4 — Travel Graph, Locations, Time, and Encounters v2

Status: **Pending.**

- [ ] Canonical location graph.
- [ ] Location IDs, names, descriptions, services, NPCs, hazards, exits.
- [ ] Travel time and fatigue/resource costs.
- [ ] Discovery state.
- [ ] Random/seeded encounters.
- [ ] Route blocking/unblocking.
- [ ] Local world events by location.
- [ ] Location history in report.
- [ ] Map/location UI payload.
- [ ] Time of day, day count, optional season/weather hooks.

## Phase 5 — NPC Profiles, Memory, Relationships, Schedules, and Evolution v2

Status: **Pending.**

- [ ] File-backed profiles for major NPCs: Bran, Elara, Aldric, bandit leader, companion candidates.
- [ ] Biography, personality, voice, speech examples, secrets, values, fears.
- [ ] Relationship scoring.
- [ ] Memory aging and importance scoring.
- [ ] Memory summarization.
- [ ] NPC schedules and location movement.
- [ ] NPC goals/agency basics.
- [ ] NPC-to-NPC conversation hooks.
- [ ] Evolution arcs: Bran tavern loss -> companion/adventurer path.
- [ ] Companion personality state changes.

## Phase 6 — Vertical Slice: Rusty Flagon Production Loop

Status: **Pending.**

Required player loops:

- [ ] Talk to Bran with persona-rich dialogue.
- [x] Buy food/water from merchant or tavern.
- [x] Rent room/rest.
- [ ] Ask for work/rumors.
- [ ] Accept quest.
- [ ] Travel to old mill route.
- [ ] Fight bandit.
- [ ] Return/report result.
- [ ] Recruit companion or deepen relationship.
- [ ] See journal/objective updates.
- [ ] Save/load without losing state.

## Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate

Status: **Pending.**

- [ ] Save/load checkpoint validation.
- [ ] Replay determinism checks.
- [ ] State diff validation.
- [ ] Loop detection.
- [ ] Progress metrics.
- [ ] Report growth budget enforcement.
- [ ] Critical warning severity categories.
- [ ] 100-turn readiness report.

## Phase 8 — UI/UX Production Pass

Status: **Pending.**

- [ ] Current objective panel.
- [ ] Suggested actions.
- [ ] Inventory/currency panel.
- [ ] Combat log and combat state panel.
- [ ] Party panel.
- [ ] Journal panel.
- [ ] Map/location panel.
- [ ] NPC relationship/memory summary panel.
- [ ] Save/load controls.
- [ ] Provider/narration/media settings.
- [ ] Error/retry/fallback user messages.
- [ ] Accessibility/readability pass.

## Phase 9 — 1000-Turn Endurance Systems

Status: **Pending.**

- [ ] World-state compression/summarization.
- [ ] Memory aging and importance compaction.
- [ ] Long-term economy/resource pressure.
- [ ] NPC schedules and agency expansion.
- [ ] Faction/reputation consequences.
- [ ] Story arc completion/failure rules.
- [ ] Campaign end-state detection.
- [ ] Long-run report segmentation.
- [ ] Automated evals for coherence and repetition.

## Phase 10 — Production Packaging, Stability, and Release Readiness

Status: **Pending.**

- [ ] Installation/run scripts.
- [ ] Environment validation.
- [ ] Provider setup wizard or clear settings UX.
- [ ] Model/provider fallback behavior.
- [ ] Crash recovery.
- [ ] Save backup/restore.
- [ ] Content versioning and migration.
- [ ] Privacy/security review for local files and provider calls.
- [ ] Performance profiles for local and remote providers.
- [ ] Player onboarding/tutorial.
- [ ] Mod/content authoring structure.
- [ ] Release checklist.

## Immediate Next Bundles

### Bundle PR.0 — Architecture Compliance Audit

- [x] Add provider-boundary static gate.
- [ ] Assert matrix/manual use `interactive_first_call_runtime`.
- [ ] Assert harness gameplay routing does not return.
- [ ] Assert fallback source fields exist.
- [ ] Add stateful visible-response no-mutation regression.

### Bundle PR.1 — Combat Lifecycle Foundation

- [x] Add initiative, enemy turn skeleton, combat log schema, XP/loot hooks.
- [x] Keep fast combat provider skip intact.
- [ ] Add/verify crit and full enemy-turn automation gates.

### Bundle PR.2 — Economy Item Database

- [x] Add canonical item database.
- [x] Add starter inventory/currency.
- [x] Add merchant stock and quantities.
- [x] Add deterministic commerce runtime.
- [x] Add economy report rows.
- [x] Add deterministic price and merchant-state presentation guardrails.
- [x] Add inn/rest service effects.
- [x] Add ration/water consumption.

### Bundle PR.3 — Vertical Slice Content Skeleton

- [ ] Define Rusty Flagon, road, old mill, market.
- [ ] Define Bran, Elara, Aldric, road bandit profiles.
- [ ] Define one quest chain and one rumor lead.

## Definition of 8/10 Production Readiness

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

## Revisit Process

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
