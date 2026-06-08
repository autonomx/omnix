# Phase 13.29 — preserve turn-error traceback evidence

## Context

Phase 13.28 added active exception traceback capture for caught turn errors, but the latest operator ZIP showed `autoplay-turn-error-diagnostics.json` was later overwritten by result-path diagnostics. The final artifact therefore lost the print-hook traceback events.

## Change

This slice updates result-path diagnostics to preserve an existing turn-error hook payload when both diagnostics share `autoplay-turn-error-diagnostics.json`. Preserved events are copied into `turn_error_hook_events` with source and active-exception counts.

## Verification target

The next operator rerun should show these fields in `autoplay-turn-error-diagnostics.json`:

- `turn_error_hook_source`
- `turn_error_hook_event_count`
- `turn_error_hook_active_exception_event_count`
- `turn_error_hook_events[].active_exception.traceback_frames`

This is still an evidence slice; it does not claim the runtime error is fixed.
