# Phase 5 — NPC Schedules and Offscreen Activity Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- `NpcScheduleEntry` for deterministic NPC location/activity schedules by day part.
- `OffscreenEvent` for local/global activity with hidden-vs-known visibility.
- `OffscreenActivityState` for schedule, private event log, public event log, immutable event appends, and event discovery.
- `day_part_for_turn` to derive schedule windows deterministically from turn count.
- `generate_offscreen_events` for seedless deterministic schedule ticks.
- Public hint and report payload helpers that avoid leaking private event details.
- Regression tests for day-part selection, scheduled event generation, event discovery, public hints, report payloads, and grouping schedules by NPC.

## Determinism Boundary

Offscreen events are generated only from schedule, turn, NPC, and location state. Private events stay private until an explicit discovery method converts them into known events. LLM narration may describe known events and hints, but it cannot reveal or mutate private events directly.

## Verification

Pending GitHub Actions for this phase PR.
