# Phase 13.23 — live timing exact wrapper guard

## Context

The Phase 13.22 operator rerun reached turn 100 and no longer showed the previous multi-minute post-background-LLM turn-commit stall. A remaining artifact-writing delay still appeared, and the uploaded live timing artifact was filled with 5,000 `repair_ms` entries from a generated private bundle helper rather than an intended runtime stage.

## Change

This slice keeps the Phase 13.22 report-scan exclusions and adds stricter wrapper selection:

- private helper names are not wrapped
- generated bundle/static-action helper names are not wrapped
- known public stage helper names remain eligible

## Verification target

The next operator rerun should verify that `autoplay-live-manual-turn-substage-timing.json` is no longer dominated by generated bundle helper events. RecursionError remains unresolved unless a live run proves otherwise.
