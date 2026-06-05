# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-05

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 11 — evidence-driven production hardening**.

Current slice: **Phase 11.4 — first persistence and diagnostics evidence capture runbook**.

Next recommended slice after Phase 11.4: **Phase 11.5 — first player-safe error and redaction evidence capture runbook**.

Latest source-of-truth SHA before Phase 11.4: `b444fdbc83f65a7ce7d18234752c2132227b3494`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #329 Phase 11.1 hardening triage | `33bc5ce073b027a213ba28eec56f198fd2e14d25` | Phase 11.1 | Complete | Added evidence-driven production hardening triage and deterministic guard. |
| #330 Phase 11.1 completion note | `bdcd7a4e12c9f38c0d8c2a5d041620f4d3fabaa2` | Phase 11.1 | Complete | Added Phase 11.1 completion note and cleanup guard. |
| #331 Phase 11.2 evidence backfill plan | `7ae0c7565f9ecd90a1909014ad45afa15cae429f` | Phase 11.2 | Complete | Added operator evidence backfill plan and deterministic guard. |
| #332 Phase 11.2 completion note | `475ee40de83017911a17ed12382b7a9ed7512abb` | Phase 11.2 | Complete | Added Phase 11.2 completion note and cleanup guard. |
| #333 Phase 11.3 package install runbook | `78bcba7fb8c6e9aef3966a7a661d55b157d70d62` | Phase 11.3 | Complete | Added package/install/run evidence runbook and deterministic guard. |
| #334 Phase 11.3 completion note | `b444fdbc83f65a7ce7d18234752c2132227b3494` | Phase 11.3 | Complete | Added Phase 11.3 completion note and cleanup guard. |

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

Completed:

- [x] Phase 11.1 — evidence-driven production hardening triage.
- [x] Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures.
- [x] Phase 11.3 — operator runbook for first package/install/run evidence capture.

Current:

- [ ] Phase 11.4 — first persistence and diagnostics evidence capture runbook.

Next:

- [ ] Phase 11.5 — first player-safe error and redaction evidence capture runbook.

Phase 11.4 scope:

- Convert Phase 11.2 evidence backfill ordering into the persistence and diagnostics operator runbook.
- Define save/session/data/report path capture, save/load roundtrip, replay/package artifact capture, diagnostic log capture, diagnostic bundle manifest, failure reproduction, redaction review, and evidence classification steps.
- Keep the slice documentation/test-only because no concrete operator evidence is attached.
- Do not select runtime, provider, packaging, UI, or gameplay hardening without concrete evidence.

## Remaining risks

- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- Phase 11 hardening must remain evidence-driven and narrow.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
