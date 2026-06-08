# Phase 13.30 — format_exc traceback capture

## Context

Phase 13.29 preserved the turn-error hook payload, but the latest operator ZIP still had no preserved hook events. The generated source map shows the caught runtime error path calls `traceback.format_exc()` near the runtime-result emission path, so the print-hook path is not sufficient.

## Change

This slice patches `traceback.format_exc` through the existing turn-error diagnostics hook. When generated error handling formats an active exception, the hook writes a bounded event to `autoplay-exception-tracebacks.json` with traceback frames, repeated-frame summary, formatted text tail, and any turn index found in traceback frame locals.

## Verification target

The next operator rerun should include `autoplay-exception-tracebacks.json`. Useful fields:

- `events[].turn_index`
- `events[].active_exception.traceback_frames`
- `events[].active_exception.repeated_frames`
- `events[].formatted_text_tail`

This is an evidence slice only; it does not claim the runtime error is fixed.
