# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-02

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 8 — UI/UX Production Pass**.

Next recommended slice: **Phase 8.1 — player-visible state and objective HUD foundation**.

Latest completed PRs:

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #184 Phase 4.16 optional season/weather expansion | `74409e87ad5fffabf4f894bfa246aa5596616daa` | Phase 4 | Complete | Added source-backed deterministic season/weather state and weather/report/UI hooks; both required RPG checks passed. |
| #186 Phase 7.1 save load replay checkpoint foundation | `2e73cdd29b40d023e88e777514ec1c14b4552f81` | Phase 7 | Complete | Added deterministic replay checkpoint helpers, canonical session digests, restore validation, drift comparison, exports, and checkpoint gate; both required RPG checks passed. |
| #188 Phase 7.2 replay turn sequence validation | `468463f545b4069b755eb73002516260cc50a59c` | Phase 7 | Complete | Added deterministic replay turn-sequence helpers through canonical runtime command helpers and replay drift checks; both required RPG checks passed. |
| #190 Phase 7.3 save load replay persistence roundtrip | `f3b2255973f305cc2e8e471b7a6e00b33a36b27f` | Phase 7 | Complete | Added provider-free package/disk save-load replay roundtrip validation and drift details; both required RPG checks passed. |
| #192 Phase 7.4 100-turn readiness loop progress report gate | `767b40863b30ad0d05e651ce26c6b81e48bfcda9` | Phase 7 | Complete | Added provider-free advisory 100-turn readiness analysis for turn count, loops, progress, and report/transcript budgets; both required RPG checks passed. |
| #194 Phase 7.5 100-turn readiness report integration | `687cb8cd2d519f5ab2d8c19bc82cd8371e0c51eb` | Phase 7 | Complete | Added deterministic readiness report payloads, severity categories, escaped HTML, idempotent report append helpers, and advisory certification guardrails; both required RPG checks passed. |
| #196 Phase 7.6 full 100-turn autoplay certification gate | `79adb4326f896c44ab9544b27786aca762211c95` | Phase 7 | Complete | Added deterministic full 100-turn artifact certification helpers with exact turn count, readiness critical blocker, and optional state/checkpoint digest mismatch enforcement; both required RPG checks passed. |
| #198 Phase 7.7 real autoplay certification artifact wiring | `fe4d6d8ae20981199c0799d338301a1dfd8e50fc` | Phase 7 | Complete | Added deterministic saved artifact normalization into the Phase 7.6 certification shape, escaped/idempotent certification report rendering, session exports, and CI gate; both required RPG checks passed. |
| #200 Phase 7.8 saved certification artifact writer integration | `d369b3ced3cdd622f3865165f271b2fafee95e6b` | Phase 7 | Complete | Added deterministic saved 100-turn certification artifact writer helpers, emits `phase7_100_turn_certification.json` next to manual/autoplay-style result artifacts, optionally appends escaped/idempotent certification HTML, and added the saved certification artifact writer gate; both required RPG checks passed. |
| #202 Phase 7.9 saved autoplay digest source integration | `047fb0a6e9ca27e800188ea7f171101829c5cec7` | Phase 7 | Complete | Added provider-free saved autoplay/manual checkpoint and state digest source capture, threaded source metadata into saved certification payloads, separated checkpoint/state mismatch blockers, and added the saved autoplay digest source gate; both required RPG checks passed. |
| #204 Phase 7.10 real saved state certification integration | `39f24306418e8d7127e24e32ad6936609ed424ba` | Phase 7 | Complete | Added deterministic real saved/loadable state certification bridge for manual/autoplay output directories, computes provider-free checkpoint/state digests from tiny persisted JSON fixtures, feeds the saved certification writer path, and added the real saved state certification gate; both required RPG checks passed. |
| #206 Phase 7.11 real autoplay progress metrics integration | `a17dbbe404d5dcf58ed1cb1460e6df415bac0db7` | Phase 7 | Complete | Added deterministic saved output progress metrics bridge, normalizes real transcript/report rows into readiness analysis, threads progress/loop/budget diagnostics into saved certification artifacts, and added the real autoplay progress metrics gate; both required RPG checks passed. |
| #208 Phase 7.12 saved certification report diagnostics visibility | `002ca914930f48ea966536e428dd193687bf64a4` | Phase 7 | Complete | Added source-backed saved certification report diagnostics in JSON/HTML for readiness, progress, loop, budget, state/checkpoint checks, blockers, and warnings; both required RPG checks passed. |
| #210 Phase 7.13 live/manual saved artifact emission hook integration | `17dd28758b18bb25db7ff6c2757056e039f4fda3` | Phase 7 | Complete | Added deterministic completion-path emission hooks for manual/autoplay output directories, source-backed skipped/missing artifact diagnostics, saved certification JSON/HTML emission, and the live manual saved artifact emission hooks gate; both required RPG checks passed. |
| #212 Phase 7.14 saved artifact bundle ZIP verification | `02e8f8519d3b81bc1ae922f53001575461adc253` | Phase 7 | Complete | Added deterministic saved artifact bundle and ZIP verification helpers for certification JSON, transcript rows, final/loadable state artifacts, report HTML bundle presence, source-backed missing artifact diagnostics, and the saved artifact bundle ZIP verification gate; both required RPG checks passed. |
| #214 Phase 7.15 saved certification operator runbook | `e4d33ec2ac06946bc8199d060976f60c044419c9` | Phase 7 | Complete | Added operator-facing saved certification runbook guidance, deterministic source guards for helper names/artifact filenames/workflow gate names/source constants/JSON fields, documented provider-free CI versus optional live-provider local runs, and added the saved certification operator runbook gate; both required RPG checks passed. |
| #216 Phase 7.16 end-to-end saved 100-turn fixture certification | `a8e3d5d6c7a3a67bc0a3107e7ac8686cdf930790` | Phase 7 | Complete | Added a provider-free end-to-end saved 100-turn fixture helper and gate that writes manual/autoplay-shaped outputs, emits saved certification JSON, appends report diagnostics, verifies disk bundle and ZIP inclusion, and covers digest drift blockers; both required RPG checks passed. |
| #218 Phase 7.17 real completion path smoke integration | `5a974b237325443c802fa5dbc36551924585b061` | Phase 7 | Complete | Added provider-free real completion path smoke integration, wired manual CLI saved certification emission before ZIP creation with an opt-out flag, covered skipped/missing artifact diagnostics and complete saved-output emission, and added the real completion path smoke gate; both required RPG checks passed. |
| #220 Phase 7.18 real artifact discovery hardening | `a8660c7f32af4647c0e2cba0c21b76b605eb0333` | Phase 7 | Complete | Added provider-free hardened saved artifact discovery for flat/nested manual/autoplay output layouts, wired progress/state/emission/bundle helpers through shared discovery diagnostics, preserved saved-state metadata compatibility, and added the real artifact discovery hardening gate; both required RPG checks passed. |
| #222 Phase 7.19 saved artifact operator UX diagnostics | `b244b9e47e4790b860656f7b748e73786cdc6767` | Phase 7 | Complete | Added operator-facing nested artifact layout guidance, duplicate/partial-output diagnostics guidance, provider-free nested discovery and ambiguity source guards, and the saved artifact operator UX diagnostics gate; both required RPG checks passed. |
| #224 Phase 7.20 closeout planning | `18041ebf17b51ed05940b91c4b502802a62863ef` | Phase 7 | Complete | Added Phase 7 closeout planning, routed remaining live/replay risks forward without overstating live-provider coverage, added the closeout planning gate, and kept required PR coverage provider-free; both required RPG checks passed. |

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

## Phase Status Summary

- Phase 0 — Architecture Compliance and Baseline Hardening: **Mostly complete / guardrail active**.
- Phase 1 — Combat Lifecycle v2: **Materially complete enough to proceed; polish/depth remains**.
- Phase 2 — Economy, Inventory, Services, and Survival v2: **Materially complete**.
- Phase 3 — Quest, Journal, Rumor, and Objective Lifecycle v2: **Complete enough to proceed**.
- Phase 4 — Travel Graph, Locations, Time, and Encounters v2: **Materially complete; Phase 4.1 through 4.16 merged**.
- Phase 5 — NPC Profiles, Memory, Relationships, Schedules, and Evolution v2: **Pending**.
- Phase 6 — Vertical Slice: Rusty Flagon Production Loop: **Pending / partially covered by earlier systems**.
- Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate: **Materially complete; remaining live/replay risks routed forward**.
- Phase 8 — UI/UX Production Pass: **Next**.
- Phase 9 — 1000-Turn Endurance Systems: **Pending**.
- Phase 10 — Production Packaging, Stability, and Release Readiness: **Pending**.

## Phase 7 — Save/Load, Replay, Determinism, and 100-Turn Gate

Status: **Materially complete for provider-free PR gate coverage.**

Scope: save/load checkpoint validation, replay determinism, state diff validation, loop detection, progress metrics, report growth budget enforcement, critical warning severity categories, and 100-turn readiness/certification reporting.

Completed:

- [x] Phase 7.1 — replay checkpoint foundation: canonical session JSON, deterministic checkpoint digests, restore validation, drift comparison, volatile runtime diagnostic filtering, exports, and `RPG CI Phase 7 replay checkpoint foundation gate`.
- [x] Phase 7.2 — replay turn sequence validation against checkpoint digests: restore from checkpoint inputs, apply provider-free command steps through canonical runtime command helpers, build per-turn checkpoint digests, compare final checkpoint digests, cover rejected commands without hidden mutation, and add the `RPG CI Phase 7 replay turn sequence gate`.
- [x] Phase 7.3 — save/load replay persistence roundtrip gate: use existing package bridge and durable store paths, validate package/disk checkpoint digest stability, replay from loaded checkpoint state, surface source-backed drift details, and add the `RPG CI Phase 7 save load replay roundtrip gate`.
- [x] Phase 7.4 — 100-turn readiness loop, progress, and report gate: add provider-free advisory analysis for turn count, loop risks, progress signals, report/transcript budgets, source-backed blockers/warnings, and add the `RPG CI Phase 7 100-turn readiness gate`.
- [x] Phase 7.5 — critical warning severity and 100-turn readiness report integration: add deterministic report-facing payloads, severity categories, escaped HTML, idempotent append helpers, advisory certification guardrails, and the `RPG CI Phase 7 100-turn readiness report gate`.
- [x] Phase 7.6 — full 100-turn autoplay certification gate: add deterministic artifact-shaped 100-turn certification helpers, exact turn count enforcement, readiness critical blocker enforcement, optional state/checkpoint digest mismatch enforcement, and the `RPG CI Phase 7 full 100-turn certification gate`.
- [x] Phase 7.7 — real autoplay certification artifact wiring: normalize saved report/transcript/checkpoint-shaped artifacts into the Phase 7.6 certifier, add saved payload helpers, render escaped/idempotent certification report sections, export helpers, and add the `RPG CI Phase 7 real autoplay certification artifact gate`.
- [x] Phase 7.8 — saved 100-turn certification payload emission and artifact writer integration: add deterministic writer helpers that emit `phase7_100_turn_certification.json` beside manual/autoplay-style result artifacts, optionally append safe certification HTML to saved reports, preserve ZIP inclusion for the JSON payload, and add the `RPG CI Phase 7 saved certification artifact writer gate`.
- [x] Phase 7.9 — saved autoplay checkpoint/state digest source integration: add deterministic digest source capture for saved autoplay/manual artifact shapes, thread captured metadata into Phase 7.7/7.8 certification payloads, report checkpoint and state digest mismatches separately, and add the `RPG CI Phase 7 saved autoplay digest source gate`.
- [x] Phase 7.10 — real saved/loadable campaign state certification integration: add deterministic manual/autoplay output-directory state discovery, compute provider-free checkpoint/state digests from persisted JSON state files, thread digests through the saved certification writer, report saved/loadable mismatches, and add the `RPG CI Phase 7 real saved state certification gate`.
- [x] Phase 7.11 — real autoplay progress and loop metrics certification integration: add deterministic saved output progress metrics extraction, normalize real transcript/report rows into Phase 7.4 readiness analysis, thread progress/loop/budget diagnostics through saved certification artifacts, and add the `RPG CI Phase 7 real autoplay progress metrics gate`.
- [x] Phase 7.12 — saved certification report diagnostics visibility integration: add escaped source-backed saved certification diagnostics in JSON and report HTML for digest mismatches, progress/loop warnings, readiness blockers, and report/transcript budget blockers, and add the `RPG CI Phase 7 saved certification report diagnostics gate`.
- [x] Phase 7.13 — live/manual saved artifact emission hook integration: add deterministic manual/autoplay completion-path hooks that discover output directories, report HTML, transcript rows, and final/loadable state artifacts; emit saved certification JSON and appended diagnostics HTML when artifacts are available; surface source-backed skipped/missing diagnostics; and add the `RPG CI Phase 7 live manual saved artifact emission hooks gate`.
- [x] Phase 7.14 — full saved artifact bundle and ZIP inclusion verification: add deterministic saved artifact bundle and ZIP verification helpers, verify certification JSON/transcript/final/loadable state artifacts in ZIPs, verify report HTML exists in saved bundles, surface source-backed missing artifact diagnostics, and add the `RPG CI Phase 7 saved artifact bundle ZIP verification gate`.
- [x] Phase 7.15 — saved certification operator runbook and live/manual invocation guidance: add operator-facing manual/autoplay saved certification guidance, document expected artifacts, ZIP/report behavior, important JSON fields, diagnostics/blockers, provider-free CI versus optional live-provider local runs, deterministic source guard tests, and the `RPG CI Phase 7 saved certification operator runbook gate`.
- [x] Phase 7.16 — end-to-end deterministic saved 100-turn fixture certification: add a canonical tiny saved output fixture builder, exercise transcript rows, report bytes, final/loadable state digests, progress/loop diagnostics, saved certification payload writing, report HTML append, emission hooks, and bundle/ZIP verification together, and add the `RPG CI Phase 7 end-to-end saved 100-turn fixture certification gate`.
- [x] Phase 7.17 — real completion path smoke integration: add a provider-free completion-path smoke bridge, wire manual CLI completion to attempt saved certification emission before results ZIP creation, skip without mutation when live artifacts are absent or incomplete, emit saved certification JSON/HTML when complete saved outputs exist, and add the `RPG CI Phase 7 real completion path smoke gate`.
- [x] Phase 7.18 — optional real artifact discovery hardening: add shared provider-free discovery for flat and nested saved artifact layouts, cover ambiguous/duplicate candidates with source-backed diagnostics, wire progress metrics/state certification/emission hooks/bundle verification through hardened discovery, preserve payload/report/ZIP guardrails, and add the `RPG CI Phase 7 real artifact discovery hardening gate`.
- [x] Phase 7.19 — optional saved artifact operator UX and diagnostics polish: update operator runbook guidance for nested saved output layouts, duplicate/ambiguous candidate diagnostics, partial-output behavior, provider-free CI boundaries, add nested discovery/ambiguity source guards, and add the `RPG CI Phase 7 saved artifact operator UX diagnostics gate`.
- [x] Phase 7.20 — Phase 7 closeout planning and remaining-risk routing: add `docs/plans/rpg_phase7_closeout_plan.md`, record provider-free Phase 7 coverage, route remaining live/replay risks forward, preserve architecture boundaries, recommend Phase 8 entry, and add the `RPG CI Phase 7 closeout planning gate`.

Remaining risks routed forward:

- Full live-provider 100-turn campaign execution is still not required in PR CI.
- Long multi-turn campaign replay, combat replay, quest reward replay, NPC memory replay, party/companion replay, and full package/disk replay of an actual 100-turn campaign still need broader coverage.
- Real saved/loadable campaign state diff validation in live completion paths needs more evidence.
- NPC file-backed profiles/persona/memory remain pending under Phase 5 or later follow-up.
- UI/UX production pass, 1000-turn endurance, and production packaging remain pending.

## Phase 8 — UI/UX Production Pass

Status: **Next.**

Suggested Phase 8.1 scope:

- Add player-visible state and objective HUD foundation.
- Keep deterministic runtime authoritative and source-backed.
- Show current location, active objective, player resources, party summary, major warnings, and relevant saved/certification status without allowing UI presentation to mutate simulation state.
- Add a provider-free deterministic CI guard for the HUD contract and source-backed state extraction.

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
