# Phase 4 — NPC Disposition and Relationship Axes Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- `NpcDisposition` with explicit relationship axes: trust, respect, friendship, fear, loyalty, suspicion, romantic interest, debt, and resentment.
- `DispositionDelta` for resolved-event-driven relationship changes.
- `apply_disposition_deltas` with immutable updates and before/after reports.
- Clamped axis values to keep relationship state bounded.
- Deterministic companion eligibility helper.
- Deterministic merchant price adjustment helper based on trust, resentment, and fear.
- Compact NPC-facing disposition memory summary.
- Regression tests for neutral state, pure delta application, clamping, companion eligibility, price modifiers, and memory summaries.

## Determinism Boundary

Disposition deltas are accepted only as resolved event inputs. LLM narration may reflect disposition state, but it may not invent relationship changes or directly mutate NPC state.

## Verification

Pending GitHub Actions for this phase PR.
