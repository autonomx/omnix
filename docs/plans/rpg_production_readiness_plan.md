# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-06

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.13 — rerun 100-turn evidence review after recursion guard and manual-stage timing**.

Next recommended slice after Phase 13.13: **Phase 13.14 — production evidence package or runtime/performance follow-up**.

Latest source-of-truth SHA before Phase 13.13: `47be44de3f4d1da96164de817cb19d4d530c8dd6`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #363 Phase 13.7 validated performance path gate | `b0b3f0c9d3557babc0406e084e955dc1d4e25886` | Phase 13.7 | Complete | Records that no latency-reduced matrix evidence is attached and blocks speculative broadening. |
| #364 Phase 13.8 autoplay report size guard | `71ace2fffe1ba593462516c30fe36859f5ac2c59` | Phase 13.8 | Complete | Caps oversized autoplay report JSON/HTML files and ZIP members after run completion. |
| #365 Phase 13.9 force-exit report size guard | `1daa97a00393816f1b7053c3dc49ec064cb0330b` | Phase 13.9 | Complete | Installs the size guard before runtime so forced finalization also caps reports. |
| #366 Phase 13.10 HTML turn-contract marker guard | `0c42263ffd6d7998458bb93c41b66603b79eca54` | Phase 13.10 | Complete | Suppresses the exact turn-contract metadata marker false positive while preserving failures for unapproved markers. |
| #367 Phase 13.11 report materialization guard and manual metrics | `47be44de3f4d1da96164de817cb19d4d530c8dd6` | Phase 13.11 | Complete | Caps report artifacts when materialized and adds manual-turn blocking breakdown metrics. |
| Phase 13.12 recursion guard and manual-stage timing | `pending-pr-merge` | Phase 13.12 | In review | Raises first-call runtime recursion budget and emits manual-stage timing from the turn path. |

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
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; recursion/timing hardening in review**.

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

Status: **Current; recursion/timing hardening in review.**

Completed:

- [x] Phase 13.1 — reopen operator evidence backfill unless accepted evidence is attached.
- [x] Phase 13.2 — first accepted hardening target implementation after evidence attachment.
- [x] Phase 13.3 — production readiness evidence review after first hardening target.
- [x] Phase 13.4 — bounded latency reduction for provider-backed intent paths.
- [x] Phase 13.5 — production readiness evidence review after latency reduction.
- [x] Phase 13.6 — apply latency-reduction follow-up from live matrix evidence.
- [x] Phase 13.7 — broaden validated performance path or continue operator evidence backfill.
- [x] Phase 13.8 — production readiness evidence checkpoint or validated performance promotion.
- [x] Phase 13.9 — operator evidence package or first validated promotion.
- [x] Phase 13.10 — rerun 100-turn evidence review after force-exit report-size guard.
- [x] Phase 13.11 — report materialization guard and manual-turn metrics.
- [x] Phase 13.12 — recursion guard and manual-stage timing.

Current:

- [ ] Phase 13.13 — rerun 100-turn evidence review after recursion guard and manual-stage timing.

Next:

- [ ] Phase 13.14 — production evidence package or runtime/performance follow-up.

Phase 13.13 scope:

- Rerun or inspect the 100-turn command after the recursion guard and manual-stage timing patch is merged.
- Confirm that `RecursionError` lines are absent from the console log and provider-error classification summary.
- Confirm that `autoplay-performance-summary.json` includes populated manual-turn sub-stage fields.
- If recursion errors persist, select one bounded runtime-state follow-up target.
- If timing sub-stages remain missing, select one bounded artifact extraction follow-up target.
- If artifacts are manageable and errors are gone, continue operator evidence packaging or performance optimization review.

## Remaining risks

- The 100-turn command must be rerun after the recursion/timing patch to confirm deterministic turn errors are gone.
- Manual-turn sub-stage fields must be verified in the next performance summary.
- The Phase 13.4 latency-reduced matrix runner still needs live/operator evidence.
- No latency-reduction improvement has been confirmed yet.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
