# Phase 3 — Map, Region, and Location Stub System Progress

## Status

Implemented as a deterministic backend foundation on 2026-06-24.

## Added

- `RpgLocationNode` for expanded locations and lightweight stubs.
- `RpgRoute` for known/unknown, safe/unsafe, open/blocked/locked exits.
- `RpgRegionGraph` with pure helpers for known exits, discoverable stubs, route lookup, and immutable updates.
- `can_instant_travel` for deterministic safe-route decisions without a heavy LLM call.
- `map_debug_payload` for report/UI-friendly graph state.
- Regression tests for known exits, stubs, instant travel, unsafe-route gating, pure updates, and debug payloads.

## Determinism Boundary

The graph helper decides only whether a route can resolve instantly from known deterministic state. Unsafe routes, unknown routes, blocked routes, or stub targets return a blocked/unknown result that requires a resolver or narration path; the LLM does not create authoritative travel state.

## Verification

Pending GitHub Actions for this phase PR.
