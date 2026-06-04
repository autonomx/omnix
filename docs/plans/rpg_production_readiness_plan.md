# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-04

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 9 — 1000-Turn Endurance Systems**.

Current slice: **Phase 9.7 — operator evidence intake contract**.

Next recommended slice after Phase 9.7: **Phase 9.8 — long-run continuity evidence envelope**.

Latest source-of-truth SHA before Phase 9.7: `21d658a01877d8e735819dc3a727e4d8e8137eb9`.

Latest completed Phase 9 work:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #296 Phase 9.1 endurance baseline | `69b48f60c0b55ab6784c7ccafdfb4ea8f1a0ee99` | Phase 9.1 | Complete | Added source-backed endurance harness baseline, taxonomy, runtime wrapper authority guard, and CI/operator evidence split. |
| #297 Phase 9.1 completion note | `ee1e20d37aae0592125f7e2c0b27212e085cb6d6` | Phase 9.1 | Complete | Added Phase 9.1 completion note and guard. |
| #298 Phase 9.2 artifact contract guard | `a72952ca26a33648230bdbf6f3a6a04ec5e2701a` | Phase 9.2 | Complete | Added deterministic artifact contract checks for summary, transcript, ZIP, summary fields, artifact path keys, and ZIP members. |
| #299 Phase 9.2 completion note | `036fedee91850e21cc7483c5605cbca01547f035` | Phase 9.2 | Complete | Added Phase 9.2 completion note and guard. |
| #300 Phase 9.3 checkpoint/replay taxonomy guard | `71d8ba3a0f2d0ee181fb0b525b7db3e9b7ce663b` | Phase 9.3 | Complete | Added checkpoint/replay taxonomy documentation and guards for save/load checkpoint, artifact contract, and operator evidence gaps. |
| #301 Phase 9.3 completion note | `eef332e0ad954e18172a8ae8ff531bf7cf63b28e` | Phase 9.3 | Complete | Added Phase 9.3 completion note and guard. |
| #302 Phase 9.4 progress-quality taxonomy guard | `a50978c140a333983fef93cf49d8115ef94d43e7` | Phase 9.4 | Complete | Added progress-quality taxonomy documentation and guards for false progress, weak progress, repeated no-op loops, turn execution, and operator evidence gaps. |
| #303 Phase 9.4 completion note | `3dd2fb3060d5158817b652a36ea205c0b3bf1160` | Phase 9.4 | Complete | Added Phase 9.4 completion note and guard. |
| #304 Phase 9.5 performance evidence envelope | `a6bb22007976dca1c0f3f92899cc05846588adf1` | Phase 9.5 | Complete | Added performance evidence envelope docs and guards for timing, drain, background job, production resource, and operator evidence labels. |
| #305 Phase 9.5 completion note | `08eda228111ac5482e16e06712ae89fe878cde47` | Phase 9.5 | Complete | Added Phase 9.5 completion note and guard. |
| #306 Phase 9.6 targeted endurance hardening plan | `90aaf03214071d93b693bc5c41b484350b89d2fb` | Phase 9.6 | Complete | Added concrete-evidence hardening intake rules and refreshed this production readiness plan. |
| #307 Phase 9.6 completion note | `21d658a01877d8e735819dc3a727e4d8e8137eb9` | Phase 9.6 | Complete | Added Phase 9.6 completion note and guard. |

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
| 1000-turn readiness | 3.5 | 8.0+ | 1000-turn run completes with bounded reports, replay/checkpoint evidence, progress-quality evidence, performance evidence, compression, memory aging, and no collapse. |
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

## Phase Status Summary

- Phase 0 — Architecture Compliance and Baseline Hardening: **Mostly complete / guardrail active**.
- Phase 1 — Combat Lifecycle v2: **Materially complete enough to proceed; polish/depth remains**.
- Phase 2 — Economy, Inventory, Services, and Survival v2: **Materially complete**.
- Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2: **Complete enough to proceed**.
- Phase 4 — Travel Graph, Locations, Time, and Encounters v2: **Materially complete; Phase 4.1 through 4.16 merged**.
- Phase 5 — NPC Profiles, Memory, Relationships, Schedules, and Evolution v2: **Pending**.
- Phase 6 — Vertical Slice: Rusty Flagon Production Loop: **Pending / partially covered by earlier systems**.
- Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate: **Materially complete; remaining live/replay risks routed forward**.
- Phase 8 — UI/UX Production Pass: **Closed as provider-free UI/UX foundation**.
- Phase 9 — 1000-Turn Endurance Systems: **In progress; Phase 9.1 through Phase 9.6 complete; Phase 9.7 current**.
- Phase 10 — Production Packaging, Stability, and Release Readiness: **Pending**.

## Phase 8 — UI/UX Production Pass

Status: **Closed.**

Final closeout/handoff document: `docs/plans/rpg_phase8_final_closeout_handoff.md`.

Final completion note: `docs/plans/rpg_phase8_35_completion_note.md`.

Phase 8 completed as a provider-free UI/UX foundation pass. It should not be extended unless a required gate exposes a concrete regression in Phase 8 closeout artifacts. Future UI/UX work should either be routed into a new explicit UI phase with a bounded checklist or handled as a targeted fix required by Phase 9 endurance evidence.

## Phase 9 — 1000-Turn Endurance Systems

Status: **In progress.**

Phase 9.1 through Phase 9.6 are complete. These slices established deterministic repo-side baselines, artifact contracts, checkpoint/replay taxonomy, progress-quality taxonomy, performance evidence envelopes, and concrete-evidence hardening intake rules. They did not run or prove a live/provider 1000-turn campaign in CI.

Completed:

- [x] Phase 9.1 — endurance harness baseline and failure taxonomy.
- [x] Phase 9.2 — deterministic endurance artifact contract guard.
- [x] Phase 9.3 — endurance checkpoint and replay taxonomy guard.
- [x] Phase 9.4 — endurance progress-quality loop taxonomy guard.
- [x] Phase 9.5 — endurance performance/evidence envelope.
- [x] Phase 9.6 — targeted endurance hardening from concrete evidence.

Current:

- [ ] Phase 9.7 — operator evidence intake contract.

Next:

- [ ] Phase 9.8 — long-run continuity evidence envelope.
- [ ] Phase 9.9 — targeted endurance hardening from concrete evidence.

Phase 9.7 scope:

- Add `docs/plans/rpg_phase9_7_operator_evidence_intake_contract.md`.
- Add deterministic source guards proving required operator evidence sections, artifact references, timing/checkpoint/replay/transcript review fields, and missing-evidence classifications.
- Keep the slice documentation/test-only and provider-free.
- Make clear that CI source guards do not prove live/provider 1000-turn performance.

Do not start runtime hardening until a concrete evidence source identifies the target failure mode.

## Active Phase 9 taxonomy

1. `harness_entrypoint_failure`
2. `runtime_authority_failure`
3. `turn_execution_failure`
4. `save_load_checkpoint_failure`
5. `artifact_contract_failure`
6. `progress_quality_failure`
7. `performance_budget_failure`
8. `provider_boundary_failure`
9. `world_continuity_failure`
10. `operator_evidence_gap`

## Remaining risks

- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for live/provider endurance, wall-clock timing, blocking or human-equivalent turn timing, final drain timing, background job drain behavior, production resource limits, and long-run narrative quality review.
- Full package/disk replay evidence remains pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- Long-run continuity risks remain across combat, NPC memory, party, travel, time, weather, quest/reward state, save/load, replay, progress-quality interpretation, and performance interpretation.
- Phase 8 UI work was a provider-free foundation pass, not a full visual/gameplay UI overhaul.

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
