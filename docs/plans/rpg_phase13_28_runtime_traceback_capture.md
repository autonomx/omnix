# Phase 13.28 — runtime traceback capture

## Context

The remaining high human-playable blocking time is in the runtime turn path. Current diagnostics capture the print-site stack for caught turn errors, but that does not identify the original failing function path.

## Change

This slice records the active exception traceback from `sys.exc_info()` when a caught turn-error line is printed. The event payload includes bounded traceback frames, a formatted traceback tail, and repeated-frame counts.

## Verification target

The next operator rerun should inspect `autoplay-turn-error-diagnostics.json` and confirm late-turn events include:

- `active_exception_available: true`
- `active_exception.traceback_frames`
- `active_exception.repeated_frames`
- `active_exception.formatted_traceback_tail`

This is an evidence slice only; it does not claim the runtime error is fixed.
