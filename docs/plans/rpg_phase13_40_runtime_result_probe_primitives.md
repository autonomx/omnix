# Phase 13.40 — runtime-result probe primitive diagnostics

## Context

The bounded snapshot source injection landed, but the uploaded artifact still did not include `autoplay-runtime-turn-result-payloads.json`. The reliable path remains the existing `_probe_log("runtime_turn_execution.result", ...)` line that survives in `console-log.txt` and backfills `autoplay-runtime-turn-results.json`.

## Change

This slice removes the source-injected snapshot call from the hot path and enriches the existing runtime-result probe with cheap scalar fields:

- `turn_result_key_count`
- `has_error`
- `has_traceback`
- `runtime_error_type`
- `runtime_error_tail`

These fields should appear in `console-log.txt` and the backfilled runtime-turn-results artifact without walking large local state or writing an extra hot-path file.

## Verification target

The next operator run should show the new scalar fields in the runtime-result probe lines for failed turns. This should reveal whether the probed `turn_result` actually has `error`/`traceback` at the emission point while avoiding the overhead from broad payload capture.

This is evidence capture only; it does not claim the runtime issue is fixed.
