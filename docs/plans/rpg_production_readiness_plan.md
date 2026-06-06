# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-05

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.4 — bounded latency reduction for provider-backed intent paths**.

Next recommended slice after Phase 13.4: **Phase 13.5 — production readiness evidence review after latency reduction**.

Latest source-of-truth SHA before Phase 13.4: `58d1a7c0b3106a90d639828e292067692a56345d`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #354 Phase 12.5 endurance evidence gate bundle | `f063a53996d3e2c5801c84220172f4b8d580e533` | Phase 12.5 | Complete | Bundled endurance evidence-decision gate, completion note, tests, and roadmap advancement by request. |
| #355 Phase 12.6 checkpoint replay evidence gate bundle | `aedd4be8e82d7f428d5df2e964ef31007384cd87` | Phase 12.6 | Complete | Bundled checkpoint/replay evidence-decision gate, completion note, tests, and roadmap advancement by request. |
| #356 Phase 12.7 evidence intake closeout bundle | `fa0cee3ae42ab26be49eb00d3d17d3c7d13ed604` | Phase 12.7 | Complete | Bundled evidence intake closeout, completion note, tests, and roadmap advancement by request. |
| #357 Phase 13.1 operator evidence backfill bundle | `2f15aba2e4ceefcb29aca0a1e13e8d49842d6c27` | Phase 13.1 | Complete | Bundled evidence backfill reopen gate, completion note, tests, and roadmap advancement by request. |
| #358 Phase 13.2 autoplay performance artifacts | `58d1a7c0b3106a90d639828e292067692a56345d` | Phase 13.2 | Complete | Adds structured autoplay performance artifacts from accepted 5-turn smoke evidence. |
| Phase 13.3 interactive matrix performance review | `pending-pr-merge` | Phase 13.3 | In review | Adds structured matrix performance review artifacts from accepted interactive matrix evidence. |

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
- Phase 11 — Evidence-Driven Production Hardening: **Complete as target-selection gate; operator evidence remains pending**.
- Phase 12 — Concrete Evidence-Backed Production Hardening: **Complete as evidence intake framework; implementation remains blocked without accepted evidence**.
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; structured performance evidence review in progress**.

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

Status: **Complete as deterministic evidence and target-selection framework; operator evidence remains pending.**

Completed:

- [x] Phase 11.1 — evidence-driven production hardening triage.
- [x] Phase 11.2 — operator evidence backfill or narrow hardening from concrete failures.
- [x] Phase 11.3 — operator runbook for first package/install/run evidence capture.
- [x] Phase 11.4 — first persistence and diagnostics evidence capture runbook.
- [x] Phase 11.5 — first player-safe error and redaction evidence capture runbook.
- [x] Phase 11.6 — first live/provider 100-turn evidence capture runbook.
- [x] Phase 11.7 — first live/provider 1000-turn evidence capture runbook.
- [x] Phase 11.8 — first checkpoint/replay evidence capture runbook.
- [x] Phase 11.9 — first hardening target selection from attached evidence.

## Phase 12 — Concrete Evidence-Backed Production Hardening

Status: **Complete as evidence intake framework; implementation remains blocked without accepted evidence.**

Completed:

- [x] Phase 12.1 — concrete hardening implementation from accepted evidence.
- [x] Phase 12.2 — package/install/run evidence capture or hardening.
- [x] Phase 12.3 — persistence/diagnostics evidence capture or hardening.
- [x] Phase 12.4 — player-safe error/redaction evidence capture or hardening.
- [x] Phase 12.5 — live/provider endurance evidence capture or hardening.
- [x] Phase 12.6 — checkpoint/replay evidence capture or hardening.
- [x] Phase 12.7 — accepted evidence intake closeout or implementation handoff.

## Phase 13 — Evidence Backfill or First Accepted Hardening Implementation

Status: **Current; structured performance evidence review in progress.**

Completed:

- [x] Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached.
- [x] Phase 13.2 — first accepted hardening target implementation after evidence attachment.
- [x] Phase 13.3 — production readiness evidence review after first hardening target.

Current:

- [ ] Phase 13.4 — bounded latency reduction for provider-backed intent paths.

Next:

- [ ] Phase 13.5 — production readiness evidence review after latency reduction.

Phase 13.4 scope:

- Use the accepted interactive matrix evidence and matrix performance review artifacts to reduce latency for provider-backed intent paths.
- Target bounded paths first: rumor/news no-backed-state, commerce food purchase, party companion recruitment, quest no-backed-state, and dialogue persona.
- Keep deterministic fast paths, runtime authority, state mutation, provider call boundaries, and deferred narration boundaries unchanged.
- Do not implement speculative latency changes outside the accepted provider-backed performance target.

## Remaining risks

- This Phase 13.3 slice adds structured review parity, not runtime latency reduction.
- Provider-backed intent paths remain the next confirmed latency target.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
