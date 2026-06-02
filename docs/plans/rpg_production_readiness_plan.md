# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-02

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 4 — Travel Graph, Locations, Time, and Encounters v2**.

Next recommended slice: **Phase 4.5 — local world events and location history report**.

Latest completed PRs:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #141 Phase 0 provider boundary static gate | `9ccca09d9636dc8d035c640c3ec1ef9955c6a08f` | Phase 0 | Complete | Provider-boundary static scan, runtime manifest hardening, Phase 0 and deterministic gates passed. |
| #142 Phase 2 starter loadout economy gate | `792451adabda3bdf96f18b41d135052b91285eac` | Phase 2 | Complete | Starter loadout, canonical starting 15 silver, starter items, idempotency/preservation, Phase 2 CI gate. |
| #143 Phase 2.2 merchant commerce runtime | `ab26de192e8f3536756b42a218135e1fdb2a8834` | Phase 2 | Complete | Merchant inventory, deterministic buy/sell runtime, player currency/inventory changes, transaction logs. |
| #144 Phase 2.3 economy report guardrails | `de8d2e06713b57e7eeceef116d11ebc4e7bf1340` | Phase 2 | Complete | Economy transaction report rows, campaign report injection, deterministic price/merchant-state presentation guardrails. |
| #145 Phase 2.4 inn room rest services | `8b472d9511ed752a51e793eb61cfb5123722dfb8` | Phase 2 | Complete | Deterministic inn room/rest runtime, Bran/Rusty Flagon 5 silver room price, HP/fatigue/rest state effects, insufficient-funds rejection, Phase 2 economy gate passed. |
| #146 Phase 2.5 ration water survival pressure | `6f4b9200bd79e27ad32473d959034bcd43dffc20` | Phase 2 | Complete | Deterministic ration/water consumption, canonical survival items, survival pressure state, source-backed survival log, Phase 0 and deterministic gates passed. |
| #147 Phase 2.6 inventory persistence save load | `06771ed584f42479674f617d9591bc54c27baea6` | Phase 2 | Complete | Deterministic Phase 2 persistence snapshot and session package export/import gate for inventory, currency, merchant/service/survival economy state, rest state, and survival state; Phase 0 and deterministic gates passed. |
| #148 Phase 2.7 economy price modifiers | `0848197d9b02c5c0a19c52f0968e1083f3ec9414` | Phase 2 | Complete | Deterministic charisma, relationship, reputation, and scarcity price modifiers for merchant buy/sell transactions; source-backed modifier logs; Phase 0 and deterministic gates passed. |
| #149 Phase 3.1 quest schema and giver state | `f810404a995308042fbc4fb9bd27b71e97320981` | Phase 3 | Complete | Deterministic quest template normalization, starter quest template, quest-giver offer registration/listing/acceptance, and Phase 3 CI gate; Phase 0 and deterministic gates passed. |
| #150 Phase 3.2 objective lifecycle | `dd22a5e77e863f7bd5befe7494ff60c3dc803d80` | Phase 3 | Complete | Deterministic objective creation/progress/completion/failure lifecycle, duplicate event suppression, quest completion/failure derivation, source-backed responses, and Phase 3 objective lifecycle CI gate; Phase 0 and deterministic gates passed. |
| #151 Phase 3.3 quest journal report | `621d02da216d252d4e746fa5d3fdcafaf2d7e582` | Phase 3 | Complete | Deterministic quest journal entries for what happened/learned/next objective, objective-result journal bridge, grouped journal summary, escaped journal report HTML, and Phase 3 journal report CI gate; Phase 0 and deterministic gates passed. |
| #152 Phase 3.4 rumor quest conversion | `591792ba7298d3b7bab6cbab5e8da25b7899420a` | Phase 3 | Complete | Deterministic rumor registration, evidence backing, backed-rumor propagation, backed-rumor quest-offer conversion, and Phase 3 rumor quest CI gate; Phase 0 and deterministic gates passed. |
| #153 Phase 3.5 work inquiry objective suggestions | `991e0b03df19a6ea73a988c599d58ee5d50d26d4` | Phase 3 | Complete | Deterministic work inquiry classification/routing, quest-giver offer registration, active objective suggestions, source-backed narration claim contract, and Phase 3 work objective CI gate; Phase 0 and deterministic gates passed. |
| #154 Phase 3.6 deterministic quest reward rules | `d7d866523d8199d4bb64a534dccd250caf265b0a` | Phase 3 | Complete | Deterministic completed-quest reward claiming, idempotent reward grants, currency/item/relationship effects, source-backed reward logs, and Phase 3 quest reward CI gate; Phase 0 and deterministic gates passed. |
| #155 Phase 3.7 quest persistence save-load coverage | `bc69af0225b821a8cb373ad6b67d8a07e9804bf7` | Phase 3 | Complete | Deterministic quest/giver/journal/rumor/reward persistence snapshots, restore/roundtrip verification, source/version validation, and Phase 3 quest persistence CI gate; Phase 0 and deterministic gates passed. |
| #156 Phase 3.8 quest report matrix coverage | `521676dc75ec790bdc66e825a6619e8a6ead45f6` | Phase 3 | Complete | Source-backed Phase 3 quest report model, escaped HTML report rendering, matrix lifecycle payload coverage, and Phase 3 quest report matrix CI gate; Phase 0 and deterministic gates passed. |
| #157 Phase 3.9 quest return report flow | `b1831eb237a32818486b84ef61371781bd81d383` | Phase 3 | Complete | Deterministic quest return/report-result helpers, idempotent reward claiming, source-backed report logs, journal closure entries, and Phase 3 quest return flow CI gate; Phase 0 and deterministic gates passed. |
| #158 Phase 3.10 completion audit and scorecard refresh | `07f2c1c2c6a3277c4fc42949d807c0c5a7a888f6` | Phase 3 | Complete | Deterministic Phase 3 completion audit helpers, audit doc, runtime-matrix evidence, advisory scorecard refresh, and Phase 3.10 CI gate; Phase 0 and deterministic gates passed. |
| #159 Phase 4.1 canonical location graph foundation | `3e72a19b7255e32af3ffe323fed79cedd169d154` | Phase 4 | Complete | Deterministic Rusty Flagon, market, old road, old mill, and nearby wilderness graph helpers; source-backed location metadata, exits, map payload, narration contract, and Phase 4 location graph CI gate passed. |
| #160 Phase 4.2 deterministic travel time and fatigue costs | `d23f1ec7e00c45d797466d0cfe4f32c37e7b089d` | Phase 4 | Complete | Deterministic route travel minutes, fatigue deltas, resource-cost accounting, risk flags, travel-state mutation, narration guardrails, and Phase 4 travel costs CI gate passed. |
| #161 Phase 4.3 location discovery and route blocking | `cc8d025aee8976312b7ef1579ed74ea1e32d6962` | Phase 4 | Complete | Deterministic starter discovery state, old mill route blocking/unblocking, route-access validation, accessible map payloads, narration guardrails, and Phase 4 discovery route blocking CI gate passed. |
| Phase 4.4 seeded travel and location encounters | `pending PR merge` | Phase 4 | In review | Deterministic seeded route/location encounter tables, source-backed encounter logs, narration guardrails, and Phase 4 seeded encounters CI gate. |

After every merged PR:

- [x] Update this handoff section with PR number, merge SHA, and validation result.
- [x] Mark completed phase checklist items below.
- [x] Update the next recommended slice.
- [x] Keep this planning doc on `rpg` so future sessions can resume from source control.

## Target Scorecard

| Category | Current | Target | Production Gate |
|---|---:|---:|---|
| Architecture / system design | 8.3 | 8.5+ | Runtime modularized enough that systems are maintainable and not harness-dependent. |
| LLM grounding / hallucination control | 7.9 | 8.5+ | Final visible state-claim validator passes matrix/autoplay with zero critical state contradictions. |
| Runtime performance architecture | 7.0 | 8.5+ | Fast buckets <0.15s; first-call average <2.5s; p95 bounded and explained. |
| Testability / diagnostics | 8.8 | 9.0+ | Matrix, manual, autoplay, save/load, and report gates run predictably with source-backed failures. |
| Core gameplay mechanics | 6.8 | 8.0+ | Combat, economy, travel, quests, party, inventory, XP, and survival all have complete loops. |
| Game design / player experience | 5.7 | 8.0+ | 30-60 minute vertical slice is coherent, fun, visible, and replayable. |
| NPC roleplay potential | 6.5 | 8.5+ | NPC profiles, memory, relationships, schedules, and evolution persist and affect play. |
| 100-turn readiness | 6.0 | 8.0+ | 100-turn run completes with zero critical warnings and useful progression. |
| 1000-turn readiness | 2.5 | 8.0+ | 1000-turn run completes with bounded reports, compression, memory aging, and no collapse. |
| Production readiness | 3.8 | 8.0+ | Install/run/config/save/load/error handling are player-safe. |
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

Status: **Materially complete. Remaining work is full inventory UI/report polish and broader vertical-slice integration.**

### Scope

- [x] Canonical item database.
- [x] Item IDs, display names, tags, stackability, value, weight if used.
- [x] Merchant stock and quantities.
- [x] Buy/sell rules.
- [x] Room/rest service effects.
- [x] Food/water consumption effects.
- [x] Currency normalization: gold/silver/copper.
- [x] Price modifiers from charisma, reputation, relationship, scarcity.
- [x] Transaction logs.
- [~] Inventory UI/report table. Economy transaction report rows, persistence snapshots, and price modifier source details are present; full inventory UI/report remains.
- [x] Starter loadout and starting currency.
- [x] Survival pressure tuning.

### Tests

- [x] Buy/sell success/failure.
- [x] Insufficient funds.
- [x] Stock depletion.
- [x] Inn room purchase and rest effect.
- [x] Ration/water consumption.
- [x] Currency normalization.
- [x] Inventory persistence through save/load.
- [x] Starter loadout grants canonical starting currency/items and is idempotent.
- [x] Starter loadout preserves existing inventory/currency.
- [x] Economy report shows deterministic transaction rows.
- [x] Economy report includes deterministic price/merchant-state presentation guardrails.
- [x] Price modifiers from charisma, reputation, relationship, and scarcity.

### Exit Criteria

- [x] Player can buy food, rent a room, rest, consume food/water, sell item, and see inventory/currency changes.
- [x] Economy report shows transactions and deltas.
- [x] No LLM-invented prices or stock in economy report guardrails.

### Completed Phase 2 slices

- Phase 2.1 / PR #142 — deterministic starter loadout runtime and CI gate.
- Phase 2.2 / PR #143 — merchant inventory and commerce runtime.
- Phase 2.3 / PR #144 — economy transaction report rows and deterministic presentation guardrails.
- Phase 2.4 / PR #145 — deterministic inn room/rest service effects.
- Phase 2.5 / PR #146 — deterministic ration/water consumption and survival pressure tuning.
- Phase 2.6 / PR #147 — deterministic inventory/economy persistence through session package export/import.
- Phase 2.7 / PR #148 — deterministic price modifiers from charisma/reputation/relationship/scarcity.

## Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2

Status: **Complete enough to proceed to Phase 4. Quest lifecycle, reporting, persistence, return/report-result flow, and completion audit are merged.**

- [x] Quest template schema.
- [x] Quest giver state.
- [x] Objective creation, update, completion, and failure.
- [x] Journal entries: what happened, what I learned, next objective.
- [x] Reward rules.
- [x] Rumor-to-quest conversion.
- [x] Backed rumor propagation.
- [x] Work inquiry routing.
- [x] Objective suggestions.
- [x] Quest report section.
- [x] Quest persistence/save-load coverage.
- [x] Quest report matrix coverage.
- [x] Quest return/report-result flow.
- [x] Phase 3 completion audit and scorecard refresh.

### Completed Phase 3 slices

- Phase 3.1 / PR #149 — deterministic quest template schema and quest giver state.
- Phase 3.2 / PR #150 — deterministic objective lifecycle creation/update/completion/failure.
- Phase 3.3 / PR #151 — deterministic quest journal entries and escaped quest journal report section.
- Phase 3.4 / PR #152 — deterministic rumor-to-quest conversion and backed rumor propagation.
- Phase 3.5 / PR #153 — deterministic work inquiry routing and objective suggestions.
- Phase 3.6 / PR #154 — deterministic completed-quest reward claiming rules.
- Phase 3.7 / PR #155 — deterministic quest/giver/journal/rumor/reward persistence roundtrip coverage.
- Phase 3.8 / PR #156 — deterministic Phase 3 quest report model, escaped HTML, and matrix lifecycle coverage.
- Phase 3.9 / PR #157 — deterministic vertical-slice quest return/report-result flow.
- Phase 3.10 / PR #158 — deterministic Phase 3 completion audit and scorecard refresh.

### Next recommended Phase 4 slices

1. Phase 4.5 — local world events and location history report.
2. Phase 4.6 — travel/discovery/blocking integration into actual runtime travel commands.
3. Phase 4.7 — time of day/day count hooks.

## Phase 4 — Travel Graph, Locations, Time, and Encounters v2

Status: **In progress. Phase 4.1, 4.2, and 4.3 are merged; Phase 4.4 seeded encounters is in review.**

- [x] Canonical location graph. Phase 4.1 added deterministic Rusty Flagon, market, old road, old mill, and nearby wilderness graph helpers.
- [x] Location IDs, names, descriptions, services, NPCs, hazards, exits. Phase 4.1 defined source-backed metadata for the starter vertical slice.
- [~] Travel time and fatigue/resource costs. Phase 4.2 adds deterministic route costs, travel-state mutation, and source-backed narration contracts; inventory consumption wiring remains pending.
- [~] Discovery state. Phase 4.3 adds deterministic starter discovered locations/routes and discovery log helpers.
- [~] Random/seeded encounters. Phase 4.4 adds deterministic seeded encounter tables/results/logs and narration guardrails; combat/world-event integration remains pending.
- [~] Route blocking/unblocking. Phase 4.3 adds deterministic route block state, block/unblock helpers, and route-access validation.
- [ ] Local world events by location.
- [~] Location history in report. Phase 4.1 adds the map payload foundation; report history remains for Phase 4.5.
- [~] Map/location UI payload. Phase 4.1 adds source-backed map payload helpers; Phase 4.3 adds discovered/blocked visible-exit payloads; UI wiring remains pending.
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
- [x] Ask for work/rumors.
- [x] Accept quest.
- [~] Travel to old mill route. Phase 4.1 adds Rusty Flagon -> Old Road -> Old Mill route validation; Phase 4.2 records deterministic travel time, fatigue, and resource-cost accounting; Phase 4.3 adds discovery/blocking gates; Phase 4.4 adds seeded encounter hooks.
- [ ] Fight bandit.
- [x] Return/report result.
- [ ] Recruit companion or deepen relationship.
- [x] See journal/objective updates.
- [~] Save/load without losing state. Phase 2 economy/inventory/rest/survival package export/import is covered; Phase 3 quest/giver/journal/rumor/reward persistence is covered; full combat/NPC memory/save-load remains.

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
- [ ] Combat log and combat state panel.
- [ ] Party panel.
- [ ] Journal panel.
- [ ] Map/location panel.
- [ ] NPC relationship/memory summary panel.
- [ ] Save/load controls.
