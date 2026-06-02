# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-02

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 4 — Travel Graph, Locations, Time, and Encounters v2**.

Next recommended slice: **Phase 4.13 — runtime session travel command integration / entry-point wiring**.

Latest completed PRs:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #141 Phase 0 provider boundary static gate | `9ccca09d9636dc8d035c640c3ec1ef9955c6a08f` | Phase 0 | Complete | Provider-boundary static scan, runtime manifest hardening, Phase 0 and deterministic gates passed. |
| #142 Phase 2 starter loadout economy gate | `792451adabda3bdf96f18b41d135052b91285eac` | Phase 2 | Complete | Starter loadout, canonical starting 15 silver, starter items, idempotency/preservation, Phase 2 CI gate. |
| #143 Phase 2.2 merchant commerce runtime | `ab26de192e8f3536756b42a218135e1fdb2a8834` | Phase 2 | Complete | Merchant inventory, deterministic buy/sell runtime, player currency/inventory changes, transaction logs. |
| #144 Phase 2.3 economy report guardrails | `de8d2e06713b57e7eeceef116d11ebc4e7bf1340` | Phase 2 | Complete | Economy transaction report rows, campaign report injection, deterministic price/merchant-state presentation guardrails. |
| #145 Phase 2.4 inn room rest services | `8b472d9511ed752a51e793eb61cfb5123722dfb8` | Phase 2 | Complete | Deterministic inn room/rest runtime, Bran/Rusty Flagon 5 silver room price, HP/fatigue/rest state effects, insufficient-funds rejection, Phase 2 economy gate passed. |
| #146 Phase 2.5 ration water survival pressure | `6f4b9200bd79e27ad32473d959034bcd43dffc20` | Phase 2 | Complete | Deterministic ration/water consumption, canonical survival items, survival pressure state, source-backed survival log, Phase 0 and deterministic gates passed. |
| #147 Phase 2.6 inventory persistence save load | `06771ed584f42479674f617d9591bc54c27baea6` | Phase 2 | Complete | Deterministic Phase 2 persistence snapshot and session package export/import gate for inventory, currency, merchant/service/survival economy state, rest state, and survival state. |
| #148 Phase 2.7 economy price modifiers | `0848197d9b02c5c0a19c52f0968e1083f3ec9414` | Phase 2 | Complete | Deterministic charisma, relationship, reputation, and scarcity price modifiers for merchant buy/sell transactions. |
| #149 Phase 3.1 quest schema and giver state | `f810404a995308042fbc4fb9bd27b71e97320981` | Phase 3 | Complete | Deterministic quest template normalization, starter quest template, quest-giver offer registration/listing/acceptance. |
| #150 Phase 3.2 objective lifecycle | `dd22a5e77e863f7bd5befe7494ff60c3dc803d80` | Phase 3 | Complete | Deterministic objective creation/progress/completion/failure lifecycle and source-backed responses. |
| #151 Phase 3.3 quest journal report | `621d02da216d252d4e746fa5d3fdcafaf2d7e582` | Phase 3 | Complete | Deterministic quest journal entries, objective-result journal bridge, grouped summary, escaped report HTML. |
| #152 Phase 3.4 rumor quest conversion | `591792ba7298d3b7bab6cbab5e8da25b7899420a` | Phase 3 | Complete | Deterministic rumor registration, evidence backing, propagation, and quest-offer conversion. |
| #153 Phase 3.5 work inquiry objective suggestions | `991e0b03df19a6ea73a988c599d58ee5d50d26d4` | Phase 3 | Complete | Deterministic work inquiry routing, quest-giver offers, objective suggestions, and narration claim contract. |
| #154 Phase 3.6 deterministic quest reward rules | `d7d866523d8199d4bb64a534dccd250caf265b0a` | Phase 3 | Complete | Deterministic completed-quest reward claiming, idempotent rewards, and source-backed reward logs. |
| #155 Phase 3.7 quest persistence save-load coverage | `bc69af0225b821a8cb373ad6b67d8a07e9804bf7` | Phase 3 | Complete | Deterministic quest/giver/journal/rumor/reward persistence snapshots and roundtrip verification. |
| #156 Phase 3.8 quest report matrix coverage | `521676dc75ec790bdc66e825a6619e8a6ead45f6` | Phase 3 | Complete | Source-backed Phase 3 quest report model, escaped HTML, and matrix lifecycle coverage. |
| #157 Phase 3.9 quest return report flow | `b1831eb237a32818486b84ef61371781bd81d383` | Phase 3 | Complete | Deterministic quest return/report-result helpers, reward claiming, journal closure entries. |
| #158 Phase 3.10 completion audit and scorecard refresh | `07f2c1c2c6a3277c4fc42949d807c0c5a7a888f6` | Phase 3 | Complete | Deterministic Phase 3 completion audit helpers, audit doc, runtime-matrix evidence, advisory scorecard refresh. |
| #159 Phase 4.1 canonical location graph foundation | `3e72a19b7255e32af3ffe323fed79cedd169d154` | Phase 4 | Complete | Deterministic Rusty Flagon, market, old road, old mill, and nearby wilderness graph helpers. |
| #160 Phase 4.2 deterministic travel time and fatigue costs | `d23f1ec7e00c45d797466d0cfe4f32c37e7b089d` | Phase 4 | Complete | Deterministic route travel minutes, fatigue deltas, resource-cost accounting, risk flags, travel-state mutation, guardrails. |
| #161 Phase 4.3 location discovery and route blocking | `cc8d025aee8976312b7ef1579ed74ea1e32d6962` | Phase 4 | Complete | Deterministic starter discovery state, old mill route blocking/unblocking, route-access validation, accessible map payloads. |
| #162 Phase 4.4 seeded travel and location encounters | `cab3a9d5dc48f352f3a8992319937bd82ce15357` | Phase 4 | Complete | Deterministic seeded route/location encounter tables, source-backed encounter logs, and narration guardrails. |
| #163 Phase 4.5 local world events and location history | `b01bc18629d7ca26c5e8bf528b80a717a03d5816` | Phase 4 | Complete | Deterministic local world-event state, derived history rows, escaped location-history report HTML. |
| #164 Phase 4.6 runtime travel access integration | `1b2f4d3892a11dc8311c9ef07c841079048ea547` | Phase 4 | Complete | Runtime travel wrapper validates discovery/route blocking before applying travel. |
| #166 Phase 4.7 time of day and day count hooks | `38f166e0de82720cb806805c0d8144c3271d2848` | Phase 4 | Complete | Deterministic time state, day count, clock labels, travel-time application, and weather placeholder. |
| #168 Phase 4.8 map location report payload | `d04ab19e3f6fcb29dfef6a249590452df9763f49` | Phase 4 | Complete | Deterministic map/location panel payload, escaped report HTML, discovery/block/time/history integration. |
| #170 Phase 4.9 travel resource consumption | `7f46aca92bbc56fe99ae3bdc7ca42b08027260ba` | Phase 4 | Complete | Guarded runtime travel resource preflight, deterministic ration/water requirements from route costs, missing-resource rejection before travel-state mutation, reuse of canonical survival APIs `consume_food` and `consume_water`, source-backed travel resource logs, narration guardrails, and Phase 4 travel resource consumption CI gate passed. |
| #172 Phase 4.10 encounter combat world event bridge | `a62c0be5296ee33d05f0d08ac6316815c61749de` | Phase 4 | Complete | Deterministic encounter runtime bridge, source-backed local world-event recording for non-combat/evidence encounters, source-backed combat candidate payloads for combat-capable encounters when no canonical combat-start API is invoked, narration guardrails, and Phase 4 encounter combat events CI gate passed. |
| #174 Phase 4.11 runtime travel encounter routing | `4ac5c5357b1ce0097a585733b431111ca0d219b4` | Phase 4 | Complete | Deterministic runtime travel command-routing bridge, canonical destination alias resolution, guarded travel/resource helper use, seeded encounter roll/record after successful travel, encounter runtime routing, combat-candidate preservation, and Phase 4 runtime travel encounter routing CI gate passed. |
| #176 Phase 4.12 command routing session integration | `d34761b661b6972cb363276553fd561788e65956` | Phase 4 | Complete | Exported Phase 4.11 command-routing helpers through `app.rpg.locations`, added deterministic facade/session follow-up tests, added the Phase 4 command routing facade session CI gate, and both required RPG checks passed. |

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
5. Every fallback, repair, provider decision, and state-facing claim needs a source.
6. Every phase must end with tests, matrix run, and report review.
7. Build toward one strong vertical slice first, then scale.
8. Production readiness means player experience, not only tests passing.

## Phase 0 — Architecture Compliance and Baseline Hardening

Status: **Mostly complete / guardrail active**.

Remaining: assert manual/matrix runtime-wrapper usage, prevent harness-owned routing, require fallback/repair source fields, add visible-response no-mutation and final state-claim audit scaffolding.

## Phase 1 — Combat Lifecycle v2

Status: **Materially complete enough to proceed; polish/depth remains.**

Completed: initiative, turn order, enemy/NPC combat turn support, attack/gating/flee/defense hooks, weapon/armor, companion support, multiple enemy support, XP/loot hooks, combat log/report/contract visibility, deterministic combat seed support, and fast-mode provider skip.

Remaining: crit-specific deterministic gate, full enemy-turn automation gate, broader player combat action variety, and vertical-slice validation.

## Phase 2 — Economy, Inventory, Services, and Survival v2

Status: **Materially complete.**

Completed: canonical item database, starter loadout/currency, merchant stock, buy/sell runtime, inn room/rest effects, ration/water survival pressure, inventory/economy persistence, price modifiers, transaction logs, and deterministic economy guardrails.

Remaining: full inventory UI/report polish and broader vertical-slice integration.

## Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2

Status: **Complete enough to proceed to Phase 4.**

Completed: quest template schema, giver state, objective lifecycle, journal/report rows, reward rules, rumor-to-quest conversion, work inquiry routing, objective suggestions, persistence/save-load coverage, quest return/report-result flow, and completion audit.

## Phase 4 — Travel Graph, Locations, Time, and Encounters v2

Status: **In progress. Phase 4.1 through 4.12 are merged; Phase 4.13 runtime session travel command integration / entry-point wiring is next.**

Completed or materially completed:

- [x] Canonical location graph.
- [x] Location IDs, names, descriptions, services, NPCs, hazards, exits.
- [x] Deterministic route travel time, fatigue, and resource costs.
- [x] Runtime travel wrapper enforcing discovery/route blocking before travel.
- [x] Travel resource preflight and consumption using canonical survival APIs.
- [~] Discovery state and route block helpers.
- [~] Random/seeded encounter payloads and logs.
- [x] Encounter-to-world-event bridge and combat candidate payloads.
- [x] Runtime travel command-routing bridge for guarded travel, seeded encounters, and encounter runtime routing.
- [x] Command-routing helpers exported through the public `app.rpg.locations` facade.
- [~] Local world-event state and derived location history.
- [~] Location history report model and escaped HTML.
- [x] Deterministic map/location panel payload and escaped report HTML.
- [x] Deterministic time-of-day/day-count hooks and weather placeholder.

Pending:

- [ ] Phase 4.13 runtime session travel command integration / entry-point wiring.
- [ ] Broader campaign report integration for map/location panels if not already wired into the main report flow.
- [ ] Frontend map/location UI panel wiring.
- [ ] Optional season/weather hooks beyond placeholder, if desired later.

## Phase 4.13 — Runtime Session Travel Command Integration / Entry-Point Wiring

Recommended scope:

- Locate the actual deterministic session/runtime command entry point for player travel commands.
- Wire travel-command handling to `app.rpg.locations.apply_runtime_travel_command` only through runtime modules.
- Keep command routing provider-free and source-backed.
- Do not call LLM.
- Do not bypass discovery, route-block, resource, or encounter runtime guardrails.
- Preserve combat candidates without starting combat unless a canonical deterministic combat-start API is located and reused.
- Add narrow deterministic tests proving missing resources deny before mutation, successful travel records encounter/runtime results, and non-travel commands do not mutate travel or encounter state.
- If no safe entry point is found, document the blocker and keep gameplay routing out of harness shortcuts.

## Phase 5 — NPC Profiles, Memory, Relationships, Schedules, and Evolution v2

Status: **Pending.**

Scope: file-backed profiles for Bran, Elara, Aldric, bandit leader, and companion candidates; biography/personality/voice/speech examples; relationship scoring; memory aging/summarization; schedules; NPC agency; NPC-to-NPC conversation hooks; evolution arcs such as Bran tavern loss to companion/adventurer path.

## Phase 6 — Vertical Slice: Rusty Flagon Production Loop

Status: **Pending.**

Current coverage:

- [ ] Talk to Bran with persona-rich dialogue.
- [x] Buy food/water from merchant or tavern.
- [x] Rent room/rest.
- [x] Ask for work/rumors.
- [x] Accept quest.
- [~] Travel to old mill route. Phase 4.1 adds route validation; Phase 4.2 records deterministic travel time, fatigue, and resource-cost accounting; Phase 4.3 adds discovery/blocking gates; Phase 4.4 adds seeded encounter hooks; Phase 4.5 adds location-history/event reporting hooks; Phase 4.6 adds runtime travel access enforcement; Phase 4.7 adds deterministic time/day advancement hooks; Phase 4.8 adds map/location panel and report payloads; Phase 4.9 adds guarded ration/water preflight and survival API consumption after successful travel; Phase 4.10 adds encounter-to-world-event bridge and combat candidate payloads for combat-capable encounter hooks; Phase 4.11 adds deterministic command-level travel bridge for guarded travel, encounter rolling, encounter logging, and encounter runtime routing; Phase 4.12 exports command-routing helpers through the public locations facade.
- [ ] Fight bandit.
- [x] Return/report result.
- [ ] Recruit companion or deepen relationship.
- [x] See journal/objective updates.
- [~] Save/load without losing state. Phase 2 economy/inventory/rest/survival and Phase 3 quest persistence are covered; full combat/NPC/travel/time persistence remains.

## Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate

Status: **Pending.**

Scope: save/load checkpoint validation, replay determinism, state diff validation, loop detection, progress metrics, report growth budget enforcement, critical warning severity categories, and 100-turn readiness report.

## Phase 8 — UI/UX Production Pass

Status: **Pending.**

Scope: objective panel, combat panel/log, party panel, journal panel, map/location panel wiring, NPC relationship/memory summary panel, save/load controls, provider/narration/media settings, error/retry/fallback user messages, accessibility/readability pass.

## Phase 9 — 1000-Turn Endurance Systems

Status: **Pending.**

Scope: world-state compression/summarization, memory aging/importance compaction, long-term economy/resource pressure, NPC schedules and agency expansion, faction/reputation consequences, story arc completion/failure rules, campaign end-state detection, long-run report segmentation, automated coherence/repetition evals.

## Phase 10 — Production Packaging, Stability, and Release Readiness

Status: **Pending.**

Scope: install/run scripts, environment validation, provider setup wizard or clear settings UX, provider fallback behavior, crash recovery, save backup/restore, content versioning/migration, privacy/security review, performance profiles, player onboarding/tutorial, mod/content authoring structure, release checklist.

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
