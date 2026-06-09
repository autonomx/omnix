# Phase 13.41 — manual harness trace primitive diagnostics

## Context

The latest runtime-result probe now proves the failed turn result is already normalized before the outer runtime-result probe:

- `ok=False`
- `has_error=False`
- `has_traceback=False`
- `runtime_error_tail=`
- result keys are the manual harness trace/summary containers

That means the raw `RecursionError` is caught inside the inner manual/runtime harness and converted into a 14-key fallback result.

## Change

This slice keeps diagnostics on the reliable `_probe_log("runtime_turn_execution.result", ...)` console path and adds only cheap primitive fields derived from the existing 14-key result:

- `manual_harness_trace_count`
- `manual_stage_trace_count`
- `turn_perf_trace_count`
- `manual_harness_summary_keys`
- `manual_turn_summary_keys`
- `turn_perf_summary_keys`
- `manual_harness_trace_last`
- `manual_stage_trace_last`
- `turn_perf_trace_last`

The helpers only inspect lengths, summary keys, and last trace item tokens. They do not walk authoritative state, write extra hot-path files, or serialize nested payloads.

## Verification target

The next operator run should show these fields in `autoplay-runtime-turn-results.json` / `console-log.txt` for failed turns. Those fields should identify which inner manual harness trace or stage recorded the recursion failure before normalization.

This is evidence capture only; it does not claim the runtime issue is fixed.
