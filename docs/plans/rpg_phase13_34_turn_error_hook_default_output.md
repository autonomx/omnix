# Phase 13.34 — turn hook default output

## Context

The latest operator run used the current branch and still did not write the expected diagnostics. The generated source rewrite was present, but the live line hook also had no saved events because it only wrote when an explicit output directory was configured.

## Change

This slice gives the live turn-error hook the same standard result-directory fallback used by the runtime source capture path. When no explicit output directory is configured, the hook writes under:

```text
resources/data/test-results/autoplay-100-n82-travel-location-progression
```

The hook source is bumped to `autoplay_turn_error_diagnostics_hook_v4`.

## Verification target

The next operator run should preserve live turn failure line events in `autoplay-turn-error-diagnostics.json` and should also allow format-capture events to write to the standard result directory.

This is evidence capture only; it does not claim the runtime issue is fixed.
