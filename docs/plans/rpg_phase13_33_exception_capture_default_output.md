# Phase 13.33 — default output for runtime capture

## Context

The latest operator run showed that source-level capture was inserted into the generated autoplay runtime, but the expected diagnostic JSON was not written. The run uses the standard harness result directory even when no explicit `--output-dir` argument is present.

## Change

This slice makes the runtime capture helper fall back to the standard autoplay result directory when no output directory is configured:

```text
resources/data/test-results/autoplay-100-n82-travel-location-progression
```

## Verification target

The next operator run should produce the capture JSON in the standard result directory with the late-turn runtime frame details needed for the next functional fix.

This is evidence capture only; it does not claim the runtime issue is fixed.
