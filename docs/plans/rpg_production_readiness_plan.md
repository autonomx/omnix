# RPG Production Readiness Plan

Date: 2026-05-30
Branch: `rpg`
Last updated: 2026-06-05

Goal: reach 8/10 or better across architecture, grounding, performance, mechanics, game design, long-run readiness, production readiness, and commercial/game-quality readiness.

## Current Handoff Status

Current phase focus: **Phase 12 — concrete evidence-backed production hardening**.

Current slice: **Phase 12.2 — package/install/run evidence capture or hardening**.

Next recommended slice after Phase 12.2: **Phase 12.3 — persistence/diagnostics evidence capture or hardening**.

Latest source-of-truth SHA before Phase 12.2: `c3a18b28d612eeaf5d0b8229f7cd693ebe22cc1e`.

## Latest completed work

| PR | Merge SHA | Phase | Status | Notes |
|---|---|---|---|---|
| #341 Phase 11.7 live provider 1000 turn runbook | `70d10433f38d9549a4422fd2091404d041f85b2c` | Phase 11.7 | Complete | Added live/provider 1000-turn evidence runbook and deterministic guard. |
| #342 Phase 11.7 completion note | `641e3aac839413ba3fc54f44055acb3871483d25` | Phase 11.7 | Complete | Added Phase 11.7 completion note and cleanup guard. |
| #343 Phase 11.8 checkpoint replay runbook | `bb8d3e3a257be6b34bd174181b797d3006c3ca9b` | Phase 11.8 | Complete | Added checkpoint/replay evidence runbook and deterministic guard. |
| #345 Phase 11.9 hardening target selection gate | `764eccb922229c6b0045f77e63bc219f62948fee` | Phase 11.9 | Complete | Added evidence-backed hardening target selection gate and deterministic guard. |
| #347 Phase 12.1 evidence decision gate | `71c82ae6500f674f90ebe57b345f3ed78cb4f04d` | Phase 12.1 | Complete | Added evidence-decision gate proving implementation remains blocked without accepted evidence. |

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
- Phase 12 — Concrete Evidence-Backed Production Hardening: **Current; blocked until accepted evidence identifies a bounded target**.

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

Status: **Current; blocked until accepted evidence identifies a bounded target.**

Completed:

- [x] Phase 12.1 — concrete hardening implementation from accepted evidence.

Current:

- [ ] Phase 12.2 — package/install/run evidence capture or hardening.

Next:

- [ ] Phase 12.3 — persistence/diagnostics evidence capture or hardening.

Phase 12.2 scope:

- Inspect accepted package/install/run evidence if attached.
- Implement bounded package/install/run hardening only if accepted evidence identifies a concrete failure with reproduction steps, affected component, player/operator impact, deterministic/runtime boundary impact, non-targets, acceptance criteria, and required verification checks.
- If no accepted package/install/run evidence is attached, keep Phase 12.2 blocked by `operator_evidence_backfill_required` and select no packaging, runtime, provider, UI, or gameplay hardening.
- Add a deterministic package evidence decision record and guard proving implementation is blocked without accepted evidence.
- Do not implement speculative packaging hardening without accepted package/install/run evidence.

## Remaining risks

- Live/provider 1000-turn execution remains pending.
- Operator/manual evidence is still needed for endurance timing, final drain, background drain, production resource limits, and long-run narrative quality review.
- Package artifacts, install/run transcripts, persistence smoke, diagnostic bundles, player-safe error evidence, release notes, redaction review, and operator signoff remain pending.
- Live/provider save/load checkpoint evidence remains pending.
- Progress-quality and continuity judgments still require live/operator transcript review.
- Phase 12 implementation must remain evidence-driven and narrow.

## Definition of 8/10 Production Readiness

The project reaches the target when install, run, config, save/load, logging, diagnostics, player-safe error handling, and operator evidence are stable enough for external users.
