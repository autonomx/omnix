# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-05

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.7 — broaden validated performance path or continue operator evidence backfill**.

Next recommended slice after Phase 13.7: **Phase 13.8 — production readiness evidence checkpoint or validated performance promotion**.

Latest source-of-truth SHA before Phase 13.7: `e118f182d3fc2ad91b1f42a74035d3eec1564dcd`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #357 Phase 13.1 operator evidence backfill bundle | `2f15aba2e4ceefcb29aca0a1e13e8d49842d6c27` | Phase 13.1 | Complete | Bundled evidence backfill reopen gate, completion note, tests, and roadmap advancement by request. |
| #358 Phase 13.2 autoplay performance artifacts | `58d1a7c0b3106a90d639828e292067692a56345d` | Phase 13.2 | Complete | Adds structured autoplay performance artifacts from accepted 5-turn smoke evidence. |
| #359 Phase 13.3 interactive matrix performance review | `426c9a9ca762df7e64cf5d57f2caab6124fa1711` | Phase 13.3 | Complete | Adds structured matrix performance review artifacts from accepted interactive matrix evidence. |
| #360 Phase 13.4 provider-backed intent latency reduction | `6cbd349cbf4b6bd515736729eeb4b271df80d392` | Phase 13.4 | Complete | Adds opt-in latency-reduced matrix runner for accepted provider-backed intent categories. |
| #361 Phase 13.5 latency reduction evidence review | `e118f182d3fc2ad91b1f42a74035d3eec1564dcd` | Phase 13.5 | Complete | Adds deterministic review helper for latency-reduced matrix evidence; no new live evidence attached. |
| Phase 13.6 latency reduction evidence backfill | `pending-pr-merge` | Phase 13.6 | In review | Records that latency-reduced matrix evidence is still missing and blocks speculative follow-up. |

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
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; latency-reduction evidence backfill in progress**.

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

Status: **Current; latency-reduction evidence backfill in progress.**

Completed:

- [x] Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached.
- [x] Phase 13.2 — first accepted hardening target implementation after evidence attachment.
- [x] Phase 13.3 — production readiness evidence review after first hardening target.
- [x] Phase 13.4 — bounded latency reduction for provider-backed intent paths.
- [x] Phase 13.5 — production readiness evidence review after latency reduction.
- [x] Phase 13.6 — apply latency-reduction follow-up from live matrix evidence.

Current:

- [ ] Phase 13.7 — broaden validated performance path or continue operator evidence backfill.

Next:

- [ ] Phase 13.8 — production readiness evidence checkpoint or validated performance promotion.

Phase 13.7 scope:

- Inspect newly attached latency-reduced matrix evidence if available.
- If latency-reduced matrix evidence confirms improvement, broaden the validated performance path only within the accepted evidence boundary.
- If no latency-reduced matrix evidence is attached, continue evidence backfill rather than implementing speculative changes.
- Preserve runtime authority, state mutation boundaries, provider call boundaries, deferred narration boundaries, and deterministic fast paths.

## Remaining risks

- The Phase 13.4 latency-reduced matrix runner still needs live/provider operator evidence.
- No latency-reduction improvement has been confirmed yet.
- This Phase 13.6 slice records evidence backfill, not runtime or routing changes.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
