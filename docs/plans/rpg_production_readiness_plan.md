# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-06

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.16 — rerun 100-turn evidence review after result-path diagnostics**.

Next recommended slice after Phase 13.16: **Phase 13.17 — runtime follow-up from result-path diagnostics or production evidence package**.

Latest source-of-truth SHA before Phase 13.16: `9fac8bd905203493b282334c9bb5f21a1b2db422`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #366 Phase 13.10 HTML turn-contract marker guard | `0c42263ffd6d7998458bb93c41b66603b79eca54` | Phase 13.10 | Complete | Suppresses the exact turn-contract metadata marker false positive while preserving failures for unapproved markers. |
| #367 Phase 13.11 report materialization guard and manual metrics | `47be44de3f4d1da96164de817cb19d4d530c8dd6` | Phase 13.11 | Complete | Caps report artifacts when materialized and adds manual-turn blocking breakdown metrics. |
| #368 Phase 13.12 recursion guard and manual-stage timing | `88ae8b7db5736260e5f7e88c9c4e224733124f7b` | Phase 13.12 | Complete | Raises first-call runtime recursion budget and emits manual-stage timing from the turn path. |
| #369 Phase 13.13 output-dir hook and guarded copy | `04b06df7f67b3ababf5720e52a0753c1ca7bded9` | Phase 13.13 | Complete | Passes explicit output dir to post-run artifact hook and bounds copy recursion failures. |
| #370 Phase 13.14 diagnostics and live timing bridge | `9fac8bd905203493b282334c9bb5f21a1b2db422` | Phase 13.14 | Complete | Adds turn-error diagnostics and bridges live harness timing into performance summaries. |
| Phase 13.15 result-path diagnostics and trace timing bridge | `pending-pr-merge` | Phase 13.15 | In review | Scans saved result payloads for failed turn objects and bridges result trace timing summaries. |

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
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; result-path diagnostics in review**.

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

Status: **Current; result-path diagnostics in review.**

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
- [x] Phase 13.13 — output-dir hook and guarded copy.
- [x] Phase 13.14 — non-copy recursion diagnostics and live timing bridge.
- [x] Phase 13.15 — result-path diagnostics and trace timing bridge.

Current:

- [ ] Phase 13.16 — rerun 100-turn evidence review after result-path diagnostics.

Next:

- [ ] Phase 13.17 — runtime follow-up from result-path diagnostics or production evidence package.

Phase 13.16 scope:

- Rerun or inspect the 100-turn command after Phase 13.15 is merged.
- Confirm that `autoplay-turn-error-diagnostics.json` exists and contains result-path events if turn errors persist.
- Inspect result JSON paths, source artifact paths, error fields, and trace keys to identify a bounded runtime component.
- Confirm that `autoplay-performance-summary.json` includes trace-derived manual timing when result traces provide it.
- If diagnostics identify a bounded runtime component, fix that component next.
- If artifacts are manageable and errors are gone, continue operator evidence packaging or performance optimization review.

## Remaining risks

- The 100-turn command must be rerun after Phase 13.15 to capture result-path diagnostics if errors persist.
- If result-path diagnostics remain empty while console errors persist, the next slice must wrap the concrete turn result emitter directly.
- The Phase 13.4 latency-reduced matrix runner still needs live/operator evidence.
- No latency-reduction improvement has been confirmed yet.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
