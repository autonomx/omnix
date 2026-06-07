# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-07

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.19 — rerun 100-turn evidence review after console probe backfill**.

Next recommended slice after Phase 13.19: **Phase 13.20 — runtime follow-up from backfilled probe evidence or production evidence package**.

Latest source-of-truth SHA before Phase 13.19: `6be4bf921be3832897dd11584705c6405167937d`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #369 Phase 13.13 output-dir hook and guarded copy | `04b06df7f67b3ababf5720e52a0753c1ca7bded9` | Phase 13.13 | Complete | Passes explicit output dir to post-run artifact hook and bounds copy recursion failures. |
| #370 Phase 13.14 diagnostics and live timing bridge | `9fac8bd905203493b282334c9bb5f21a1b2db422` | Phase 13.14 | Complete | Adds turn-error diagnostics and bridges live harness timing into performance summaries. |
| #371 Phase 13.15 result-path diagnostics and trace timing bridge | `0d03c702dc103da4f7b43ec888b47e3b4aa43203` | Phase 13.15 | Complete | Scans saved result payloads for failed turn objects and bridges result trace timing summaries. |
| #372 Phase 13.16 runtime result diagnostics priority | `c60cc7984852252cf6dce47fd9ad25903078921e` | Phase 13.16 | Complete | Separates runtime-result diagnostic events from generic failure events so runtime traces are not crowded out. |
| #373 Phase 13.17 runtime result emitter capture | `6be4bf921be3832897dd11584705c6405167937d` | Phase 13.17 | Complete | Captures runtime result probe emissions into a dedicated runtime result artifact when the stream hook sees them. |
| Phase 13.18 console probe backfill | `pending-pr-merge` | Phase 13.18 | In review | Parses persisted console logs after the run to backfill runtime result artifacts before diagnostics. |

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
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; console probe backfill in review**.

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

Status: **Current; console probe backfill in review.**

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
- [x] Phase 13.16 — runtime result diagnostics priority.
- [x] Phase 13.17 — runtime result emitter capture.
- [x] Phase 13.18 — console probe parser and runtime-result artifact backfill.

Current:

- [ ] Phase 13.19 — rerun 100-turn evidence review after console probe backfill.

Next:

- [ ] Phase 13.20 — runtime follow-up from backfilled probe evidence or production evidence package.

Phase 13.19 scope:

- Rerun or inspect the 100-turn command after Phase 13.18 is merged.
- Confirm that `autoplay-runtime-turn-results.json` exists even when the live stream hook misses the probe stream.
- Confirm that the artifact records console-log backfill source, turn index, ok flag, result keys, trace keys, and timestamp when present.
- Confirm that `autoplay-turn-error-diagnostics.json` contains runtime result events from the backfilled artifact.
- Confirm that `autoplay-performance-summary.json` records the runtime emission bridge source when full timing values remain unavailable.
- If the backfilled probe line only contains keys and not payload values, identify the next concrete probe/emitter symbol to wrap.
- If artifacts are manageable and errors are gone, continue operator evidence packaging or performance optimization review.

## Remaining risks

- The 100-turn command must be rerun after Phase 13.18 to confirm console-log backfill works in the operator run.
- If the backfilled line only contains keys and not payload values, the next slice should wrap the concrete probe function or runtime result emitter symbol once identified.
- The Phase 13.4 latency-reduced matrix runner still needs live/operator evidence.
- No latency-reduction improvement has been confirmed yet.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
