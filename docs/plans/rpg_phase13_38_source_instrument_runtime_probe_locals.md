# Phase 13.38 — source-instrument runtime probe locals

## Context

The latest run still did not produce `autoplay-runtime-turn-result-payloads.json`. Wrapping `_probe_log` after the generated source is executed was not sufficient, even though the expanded source map proves the runtime-result probe block is present.

## Change

This slice instruments the generated source text directly. Immediately before the known `runtime_turn_execution.result` probe block, the loader injects:

```python
_capture_runtime_probe_locals(locals(), source_label="runtime_result_probe_source_instrumentation")
```

The helper delegates to the existing bounded runtime probe payload capture module, so the next run should persist caller locals at the exact probe emission point without relying on wrapping `_probe_log`.

## Verification target

The next operator run should produce `autoplay-runtime-turn-result-payloads.json` with `runtime_probe_locals` events for the failed turn path. Those events should include bounded `turn_result`, runtime error fields when present, trace summaries, and available local names.

This is evidence capture only; it does not claim the runtime issue is fixed.
