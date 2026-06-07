# RPG Phase 13.14 Non-Copy Recursion Diagnostics and Live Timing Bridge

Phase 13.14 addresses the 100-turn rerun after Phase 13.13.

Latest source-of-truth SHA before this Phase 13.14 slice:

- `04b06df7f67b3ababf5720e52a0753c1ca7bded9`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression (2).zip`

The evidence showed:

- report-size hardening works;
- `autoplay-performance-summary.json` now exists in the per-run directory;
- `autoplay-deepcopy-recursion-guard-summary.json` is missing;
- `RecursionError: maximum recursion depth exceeded` still appears from turn 59 through turn 100;
- the performance summary still only exposes coarse manual timing and deferred enqueue timing.

This means the recursion source is not confirmed as the guarded copy path, and the next evidence bundle must include a source stack for the emitted turn errors.

## Bounded targets

Phase 13.14 selects two bounded targets:

1. Capture emitted `TURN N ERROR` lines into a per-run diagnostic artifact with a bounded stack tail from the error handler.
2. Bridge the live harness `autoplay-performance.json` stage summary into the canonical `autoplay-performance-summary.json` so available live timing stages are preserved.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/turn_error_diagnostics_hook.py`
- `src/tests/rpg/autoplay/live_performance_bridge.py`
- `src/tests/rpg/test_ci_phase13_14_diagnostics_bridge.py`
- `docs/plans/rpg_phase13_14_noncopy_recursion_diagnostics.md`
- `docs/plans/rpg_phase13_14_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Turn-error diagnostics

The stable loader now installs `turn_error_diagnostics_hook` before generated runtime fragments load.

When a line matching `TURN N ERROR: ErrorType: message` is emitted, the hook writes:

- `autoplay-turn-error-diagnostics.json`

The artifact includes:

- turn index;
- error type;
- error message;
- the emitted line;
- a bounded Python stack tail from the error handler;
- source marker.

## Live timing bridge

The post-run hook now loads `autoplay-performance.json` from the per-run output directory or ZIP mirror and appends a synthetic advisory performance row with live harness timing.

The canonical performance summary can then preserve available live timing such as:

- `manual_turn_ms`
- `state_snapshot_ms` from `state_bounds_ms`
- `deferred_enqueue_ms` from `background_enqueue_ms`
- live stage summary details and unattributed manual blocking time

Unknown finer-grained stages remain unknown until the live turn path emits them directly.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- emitted turn-error lines create `autoplay-turn-error-diagnostics.json`;
- the diagnostic artifact includes turn index, error type, message, and stack tail;
- live harness timing builds a canonical advisory row;
- performance summaries read bridged manual, state, and enqueue timing;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostic and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.14, continue with:

- Phase 13.15 — rerun 100-turn evidence review after non-copy recursion diagnostics and live timing bridge.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect `autoplay-turn-error-diagnostics.json` if `RecursionError` lines remain.
