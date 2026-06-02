# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-02

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate**.

Next recommended slice: **Phase 7.5 — critical warning severity and 100-turn readiness report integration**.

Latest completed PRs:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #184 Phase 4.16 optional season/weather expansion | `74409e87ad5fffabf4f894bfa246aa5596616daa` | Phase 4 | Complete | Replaced the deterministic weather placeholder with source-backed season/weather helpers, surfaced weather fields in time/map/report/UI payloads, added weather narration guardrails, and both required RPG checks passed. |
| #186 Phase 7.1 save load replay checkpoint foundation | `2e73cdd29b40d023e88e777514ec1c14b4552f81` | Phase 7 | Complete | Added deterministic replay checkpoint helpers, canonical session digests, restore validation, drift comparison, exports, and the Phase 7 replay checkpoint foundation gate; both required RPG checks passed. |
| #188 Phase 7.2 replay turn sequence validation | `468463f545b4069b755eb73002516260cc50a59c` | Phase 7 | Complete | Added deterministic replay turn-sequence helpers that restore from checkpoints, apply provider-free command steps through canonical runtime command helpers, compare per-turn/final checkpoint digests, cover rejected commands without hidden mutation, and added the Phase 7 replay turn sequence gate; both required RPG checks passed. |
| #190 Phase 7.3 save load replay persistence roundtrip | `f3b2255973f305cc2e8e471b7a6e00b33a36b27f` | Phase 7 | Complete | Added provider-free package/disk save-load replay roundtrip validation using existing package bridge, durable store, checkpoint, and replay sequence paths; surfaced digest drift details; exported Phase 7.3 helpers; added the Phase 7 save load replay roundtrip gate; both required RPG checks passed. |
| #192 Phase 7.4 100-turn readiness loop progress report gate | `767b40863b30ad0d05e651ce26c6b81e48bfcda9` | Phase 7 | Complete | Added provider-free advisory 100-turn readiness analysis for loop, progress, and report-budget signals; classified incomplete turn counts and report/transcript growth as blockers; surfaced repeated action/location/no-progress risks as advisory warnings; exported Phase 7.4 helpers; added the Phase 7 100-turn readiness gate; both required RPG checks passed. |

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

Status: **Materially complete. Phase 4.1 through 4.16 are merged; deeper discovery, encounter, and location-history polish can continue as follow-up work.**

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
- [x] Session-level travel command routing through the canonical runtime wrapper.
- [~] Local world-event state and derived location history.
- [~] Location history report model and escaped HTML.
- [x] Deterministic map/location panel payload and escaped report HTML.
- [x] Campaign report map/location panel integration using deterministic map/location helpers.
- [x] Frontend map/location UI panel wiring using deterministic runtime map/location payloads.
- [x] Deterministic time-of-day/day-count hooks with source-backed season/weather state.

Follow-up polish:

- [~] Discovery state and route block helper depth.
- [~] Random/seeded encounter payload and log gameplay depth.
- [~] Broader location history report usage.

## Phase 4.14 — Campaign Report Map/Location Panel Integration

Status: **Complete.**

Completed in PR #180 (`f9b46b4a8ff09a73e577cdee08eb2b43c742ad2c`):

- Wired deterministic map/location panel payloads into the campaign/main report flow.
- Reused `app.rpg.locations.build_map_location_panel_payload` and `render_map_location_report_html` instead of duplicating map/report logic.
- Kept rendering provider-free, source-backed, escaped, and non-mutating.
- Preserved map guardrails: do not reveal undiscovered locations as known and do not claim blocked routes are passable.
- Added deterministic tests for map/location panel visibility, route-block display, current-location display, time display, hidden undiscovered locations, idempotent append behavior, and no gameplay mutation during report rendering.
- Added the `RPG CI Phase 4 campaign report map location gate`.

## Phase 4.15 — Frontend Map/Location UI Panel Wiring

Status: **Complete.**

Completed in PR #182 (`f112d8db632e69416cc6823e033757330d0497fd`):

- Added a visible frontend map/location section by wiring a browser renderer into the existing RPG minimap panel.
- Surfaced deterministic map/location panel payloads through runtime travel turn responses, resolved results, and narration context.
- Reused `app.rpg.locations.build_map_location_panel_payload` rather than duplicating canonical graph logic in JavaScript.
- Showed current location, description, time labels, visible exits, blocked route status/reason, and guarded undiscovered destination labels.
- Preserved guardrails: hidden or undiscovered locations are not exposed as known, and blocked routes are not described as passable.
- Kept rendering escaped, provider-free, and non-mutating.
- Added the `RPG CI Phase 4 frontend map location UI panel gate`.

## Phase 4.16 — Optional Season/Weather Expansion

Status: **Complete.**

Completed in PR #184 (`74409e87ad5fffabf4f894bfa246aa5596616daa`):

- Replaced the Phase 4.7 weather placeholder with deterministic source-backed season/weather state.
- Added provider-free weather profiles, season progression, deterministic weather selection, weather refresh logs, and weather narration guardrails.
- Surfaced weather/season fields through time state, map/location payloads, escaped report HTML, and the frontend map/location panel.
- Preserved report/UI non-mutation and hidden-state/route-block guardrails.
- Added the `RPG CI Phase 4 season weather expansion gate`.

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
- [~] Travel to old mill route: Phase 4.1 through 4.16 now cover deterministic route validation, travel time, discovery/blocking, seeded encounters, history/reporting, runtime travel access, time/day advancement, resource preflight, encounter routing, campaign report map payloads, frontend map/location UI, and source-backed season/weather state.
- [ ] Resolve the old mill combat route.
- [x] Return/report result.
- [ ] Recruit companion or deepen relationship.
- [x] See journal/objective updates.
- [~] Save/load without losing state. Phase 2 economy/inventory/rest/survival and Phase 3 quest persistence are covered; Phase 7.1 adds canonical checkpoint digest/restore comparison foundation; Phase 7.2 adds deterministic replay turn-sequence validation through canonical runtime command helpers; Phase 7.3 adds package/disk save-load replay persistence roundtrip validation for manifest/session identity, installed packs, simulation/runtime state, travel, quest, economy, and survival seeds; full combat/NPC persistence roundtrip gates remain.

## Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate

Status: **In progress.**

Scope: save/load checkpoint validation, replay determinism, state diff validation, loop detection, progress metrics, report growth budget enforcement, critical warning severity categories, and 100-turn readiness report.

Completed:

- [x] Phase 7.1 — replay checkpoint foundation: canonical session JSON, deterministic checkpoint digests, restore validation, drift comparison, volatile runtime diagnostic filtering, exports, and `RPG CI Phase 7 replay checkpoint foundation gate`.
- [x] Phase 7.2 — replay turn sequence validation against checkpoint digests: restore from checkpoint inputs, apply provider-free command steps through canonical runtime command helpers, build per-turn checkpoint digests, compare final checkpoint digests, cover rejected commands without hidden mutation, emit source-backed replay drift details, and add the `RPG CI Phase 7 replay turn sequence gate`.
- [x] Phase 7.3 — save/load replay persistence roundtrip gate: use existing package bridge and durable store paths, validate package/disk checkpoint digest stability, replay from loaded checkpoint state, surface source-backed drift details, export readiness/contract helpers, and add the `RPG CI Phase 7 save load replay roundtrip gate`.
- [x] Phase 7.4 — 100-turn readiness loop, progress, and report gate: add provider-free advisory 100-turn readiness analysis for turn count, loop risks, progress signals, report/transcript growth projections, source-backed blockers/warnings, exports, and the `RPG CI Phase 7 100-turn readiness gate`.

Next recommended slice: **Phase 7.5 — critical warning severity and 100-turn readiness report integration**.

Suggested Phase 7.5 scope:

- Integrate the Phase 7.4 readiness result into deterministic campaign/report-facing artifacts.
- Add critical, warning, and advisory severity categories for readiness blockers and warnings.
- Add a compact escaped/safe 100-turn readiness report section that surfaces turn count status, loop risks, progress metrics, report/transcript growth projections, and critical blockers vs advisory warnings.
- Keep report rendering provider-free, source-backed, escaped, and non-mutating.
- Ensure every blocker and warning entry carries a source field.
- Add source-backed guardrails that the report remains advisory until a full 100-turn autoplay gate passes.
- Add `src/tests/rpg/test_ci_phase7_100_turn_readiness_report.py`.
- Add an `RPG CI Phase 7 100-turn readiness report gate` after the Phase 7 100-turn readiness gate and before the runtime facade manifest gate.

## Phase 8 — UI/UX Production Pass

Status: **Pending.**

Scope: objective panel, combat panel/log, party panel, journal panel, map/location panel polish, NPC relationship/memory summary panel, save/load controls, provider/narration/media settings, error/retry/fallback user messages, accessibility/readability pass.

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
