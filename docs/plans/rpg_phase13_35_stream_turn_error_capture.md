# Phase 13.35 — stream turn error capture

## Context

The latest operator run confirmed the runtime-result console probe is reliably available in `console-log.txt`, while the print-hook artifacts still did not preserve the live turn failure lines. The generated console stream is therefore the most reliable evidence path.

## Change

This slice extends the runtime-result stream capture hook:

- uses the standard autoplay result directory when no explicit output directory is configured
- keeps runtime-result stream capture and console-log backfill behavior
- records turn failure console lines into `autoplay-stream-turn-error-events.json`
- backfills the same turn failure events from `console-log.txt` after the run

## Verification target

The next operator run should produce:

```text
resources/data/test-results/autoplay-100-n82-travel-location-progression/autoplay-stream-turn-error-events.json
```

That artifact should list the late failed turns, error type/message, and live stack tails when captured from the stream path.

This is evidence capture only; it does not claim the runtime issue is fixed.
