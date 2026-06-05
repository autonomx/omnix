# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-04

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 10 — production packaging, stability, and release readiness**.

Current slice: **Phase 10.3 — persistence and diagnostics evidence envelope**.

Next recommended slice after Phase 10.3: **Phase 10.4 — player-safe error handling evidence envelope**.

Latest source-of-truth SHA before Phase 10.3: `c1b0dd46b318bd28560e3bea2acdb436fabe0851`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #313 Phase 9.9 completion note | `447648e05ee32ef8ed63af10f9b90a2209d7f6bf` | Phase 9.9 | Complete | Closed Phase 9 as deterministic evidence framework. |
| #314 Phase 10.1 action coverage | `154c8076a59d9fa82f40e76ba08310f0e52dee21` | Phase 10.1 prep | Complete | Added exact Phase 10.1 workflow path coverage. |
| #315 Phase 10.1 production readiness baseline | `12efbe0baa16bed4c5336fdf76ff6422081a910f` | Phase 10.1 | Complete | Added production readiness baseline and packaging evidence plan. |
| #316 Phase 10.1 completion note | `c158b80e77768f819c8405dc14976eeaf42c2169` | Phase 10.1 | Complete | Added Phase 10.1 completion note and cleanup guard. |
| #317 Phase 10.2 install/run evidence envelope | `1957d9da2cc505ba04247b92dabef0c614238759` | Phase 10.2 | Complete | Added install/run configuration evidence envelope and deterministic guard. |
| #318 Phase 10.2 completion note | `c1b0dd46b318bd28560e3bea2acdb436fabe0851` | Phase 10.2 | Complete | Added Phase 10.2 completion note and cleanup guard. |

## Roadmap Principles

1. Keep deterministic runtime authoritative.
2. Keep LLM advisory/presentation-only.
3. Keep harnesses out of gameplay routing.
4. Every fallback, repair, provider decision, and state-facing claim needs a source.
5. Production readiness means player experience, not only tests passing.

## Phase Status Summary

- Phase 8 — UI/UX Production Pass: **Closed as provider-free UI/UX foundation**.
- Phase 9 — 1000-Turn Endurance Systems: **Complete as deterministic evidence framework; live/operator validation remains pending**.
- Phase 10 — Production Packaging, Stability, and Release Readiness: **In progress; Phase 10.3 current**.

## Phase 9 — 1000-Turn Endurance Systems

Status: **Complete as deterministic evidence framework; live/operator validation remains pending.**

Phase 9.1 through Phase 9.9 are complete. These slices established deterministic repo-side baselines, artifact contracts, checkpoint/replay taxonomy, progress-quality taxonomy, performance evidence envelopes, concrete-evidence hardening intake rules, operator evidence intake, long-run continuity evidence envelopes, and a hardening decision gate. They did not run or prove a live/provider 1000-turn campaign in CI.

## Phase 10 — Production Packaging, Stability, and Release Readiness

Status: **In progress.**

Completed:

- [x] Phase 10.1 — production readiness baseline and packaging evidence plan.
- [x] Phase 10.2 — install/run configuration evidence envelope.

Current:

- [ ] Phase 10.3 — persistence and diagnostics evidence envelope.

Next:

- [ ] Phase 10.4 — player-safe error handling evidence envelope.

Phase 10.3 scope:

- Add `docs/plans/rpg_phase10_3_persistence_diagnostics_evidence_envelope.md`.
- Add deterministic source guards proving persistence and diagnostics readiness requires concrete artifacts.
- Define persistence evidence fields for save/session/data paths, roundtrip checks, replay/package artifacts, and migration/rollback expectations.
- Define diagnostics evidence fields for logs, error reports, artifact bundles, operator collection steps, and sensitive-data redaction.
- Keep the slice documentation/test-only and provider-free unless concrete persistence/diagnostics evidence identifies a narrow failure.
- Do not claim release readiness until concrete persistence and diagnostic evidence exists.

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
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Full package/disk replay evidence remains pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- No Phase 9 targeted runtime hardening was performed because no concrete operator evidence was attached.
- Phase 10 still needs concrete install/run/package/persistence/diagnostic evidence before external release readiness can be claimed.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
