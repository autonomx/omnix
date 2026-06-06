# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-06

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 13 — evidence backfill or first accepted hardening implementation**.

Current slice: **Phase 13.11 — rerun 100-turn evidence review after HTML marker guard**.

Next recommended slice after Phase 13.11: **Phase 13.12 — production evidence package or report/assertion follow-up**.

Latest source-of-truth SHA before Phase 13.11: `1daa97a00393816f1b7053c3dc49ec064cb0330b`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #361 Phase 13.5 latency reduction evidence review | `e118f182d3fc2ad91b1f42a74035d3eec1564dcd` | Phase 13.5 | Complete | Adds deterministic review helper for latency-reduced matrix evidence; no new live evidence attached. |
| #362 Phase 13.6 latency evidence backfill | `17d7acb7fa7def1a8e57ecb85133ceb9e6c8f1a1` | Phase 13.6 | Complete | Records that latency-reduced matrix evidence is still missing and blocks speculative follow-up. |
| #363 Phase 13.7 validated performance path gate | `b0b3f0c9d3557babc0406e084e955dc1d4e25886` | Phase 13.7 | Complete | Records that no latency-reduced matrix evidence is attached and blocks speculative broadening. |
| #364 Phase 13.8 autoplay report size guard | `71ace2fffe1ba593462516c30fe36859f5ac2c59` | Phase 13.8 | Complete | Caps oversized autoplay report JSON/HTML files and ZIP members after run completion. |
| #365 Phase 13.9 force-exit report size guard | `1daa97a00393816f1b7053c3dc49ec064cb0330b` | Phase 13.9 | Complete | Installs the size guard before runtime so forced finalization also caps reports. |
| Phase 13.10 HTML turn-contract marker guard | `pending-pr-merge` | Phase 13.10 | In review | Suppresses the exact turn-contract metadata marker false positive while preserving failures for unapproved markers. |

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
- Phase 13 — Evidence Backfill or First Accepted Hardening Implementation: **Current; HTML marker guard in review**.

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

Status: **Current; HTML marker guard in review.**

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

Current:

- [ ] Phase 13.11 — rerun 100-turn evidence review after HTML marker guard.

Next:

- [ ] Phase 13.12 — production evidence package or report/assertion follow-up.

Phase 13.11 scope:

- Rerun or inspect the 100-turn command after the HTML marker guard is merged.
- Confirm that artifact generation completes without the `turn contract` marker failure.
- Confirm that `autoplay-report-size-guard-summary.json` is present.
- Confirm that report JSON, report HTML, and results ZIP remain shareable.
- If another report assertion fails, select one bounded follow-up target.
- If artifacts are manageable and assertions pass, continue operator evidence packaging or validated promotion review.

## Remaining risks

- The 100-turn command must be rerun after the HTML marker guard to confirm artifact generation completes.
- The report-size summary should be checked after the rerun.
- The Phase 13.4 latency-reduced matrix runner still needs live/operator evidence.
- No latency-reduction improvement has been confirmed yet.
- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
