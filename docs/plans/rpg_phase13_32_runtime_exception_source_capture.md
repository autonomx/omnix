# Phase 13.32 — runtime exception source capture

## Context

The latest operator ZIP still showed 42 late-turn `RecursionError` lines and ~13.5s runtime-turn failures, but no `autoplay-exception-tracebacks.json`. The generated source map confirms the runtime-result error path includes `"traceback": traceback.format_exc()`, so module-level monkeypatching was not sufficient evidence capture in the live harness.

## Change

This slice instruments the combined generated source before execution. The loader replaces the exact runtime-result expression:

```python
"traceback": traceback.format_exc(),
```

with a helper call that records `autoplay-exception-tracebacks.json` and returns the original formatted traceback string unchanged.

The capture artifact includes:

- `turn_index`
- `error_type`
- `message`
- bounded traceback frames
- repeated-frame summary
- formatted text tail

## Verification target

The next operator rerun should include `autoplay-exception-tracebacks.json` with `event_class: runtime_exception_source_capture` for late-turn runtime failures. That should finally identify the recursive runtime frame path causing the blocking-time spike.

This is an evidence capture slice only; it does not claim the runtime error is fixed.
