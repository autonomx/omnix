# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-05

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 11 — evidence-driven production hardening**.

Current slice: **Phase 11.1 — evidence-driven production hardening triage**.

Next recommended slice after Phase 11.1: **Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures**.

Latest source-of-truth SHA before Phase 11.1: `045a8755736535211848caa0950a888d3bca43c7`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #321 Phase 10.4 player-safe error evidence envelope | `39c3e78a78417f2cc3cd48ca4cf8db32c9c7a06d` | Phase 10.4 | Complete | Added player-safe error handling evidence envelope and deterministic guard. |
| #322 Phase 10.4 completion note | `ba12cfc91d7fed7743634ed86c5baadc01833749` | Phase 10.4 | Complete | Added Phase 10.4 completion note and cleanup guard. |
| #323 Phase 10.5 evidence contract | `801b075ad69b3d97a7e6cce7fac746c3bdfeec63` | Phase 10.5 | Complete | Added release-candidate packaging contract and deterministic guard. |
| #324 Phase 10.5 completion note | `fd246f2da905beb5b471f8888383655a06497ac8` | Phase 10.5 | Complete | Added Phase 10.5 completion note and cleanup guard. |
| #325 Phase 10.6 checklist | `9f0a9dbe65c3da5f7335e742a9740386cb338d46` | Phase 10.6 | Complete | Added operator release evidence intake checklist and deterministic guard. |
| #326 Phase 10.6 completion note | `d4eb75096f99abd36aee2989d1128764fdb8924d` | Phase 10.6 | Complete | Added Phase 10.6 completion note and cleanup guard. |
| #327 Phase 10.7 closeout gate | `045a8755736535211848caa0950a888d3bca43c7` | Phase 10.7 | Complete | Added production readiness closeout decision gate and deterministic guard. |

## Roadmap Principles

1. Keep deterministic runtime authoritative.
2. Keep LLM advisory/presentation-only.
3. Keep harnesses out of gameplay routing.
4. Every fallback, repair, provider decision, and state-facing claim needs a source.
5. Production readiness means player experience, not only tests passing.

## Phase Status Summary

- Phase 8 — UI/UX Production Pass: **Closed as provider-free UI/UX foundation**.
- Phase 9 — 1000-Turn Endurance Systems: **Complete as deterministic evidence framework; live/operator validation remains pending**.
- Phase 10 — Production Packaging, Stability, and Release Readiness: **Complete as deterministic evidence framework; operator evidence remains pending**.
- Phase 11 — Evidence-Driven Production Hardening: **Current**.

## Phase 10 — Production Packaging, Stability, and Release Readiness

Status: **Complete as deterministic evidence framework; operator evidence remains pending.**

Completed:

- [x] Phase 10.1 — production readiness baseline and packaging evidence plan.
- [x] Phase 10.2 — install/run configuration evidence envelope.
- [x] Phase 10.3 — persistence and diagnostics evidence envelope.
- [x] Phase 10.4 — player-safe error handling evidence envelope.
- [x] Phase 10.5 — release candidate packaging contract.
- [x] Phase 10.6 — operator release evidence intake checklist.
- [x] Phase 10.7 — production readiness closeout decision gate.

## Phase 11 — Evidence-Driven Production Hardening

Status: **Current.**

Current:

- [ ] Phase 11.1 — evidence-driven production hardening triage.

Next:

- [ ] Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures.

Phase 11.1 scope:

- Review Phase 10 evidence contracts and classify what concrete operator evidence is still missing.
- Do not make runtime, provider, packaging, UI, or gameplay changes without concrete evidence.
- Define the first hardening target only from attached operator evidence, CI failure logs, or source-backed diagnostics.
- Keep any initial Phase 11 slice documentation/test-only if no concrete failure evidence is attached.

## Remaining risks

- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- Phase 11 hardening must remain evidence-driven and narrow.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
