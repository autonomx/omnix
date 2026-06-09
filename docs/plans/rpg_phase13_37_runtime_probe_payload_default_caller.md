# Phase 13.37 — runtime probe payload caller capture

## Context

The latest run produced the expanded source map and stream turn-failure artifact, but `autoplay-runtime-turn-result-payloads.json` was still absent. The probe payload wrapper did not write by default and did not wrap `_probe_log`, the helper used by the generated runtime-result emission.

## Change

This slice updates runtime probe payload capture so it:

- uses the standard autoplay result directory when no output directory is configured
- wraps `_probe_log` / `probe_log` helpers
- captures caller locals when the runtime-result probe is emitted
- preserves the existing bounded JSON safety for local objects

## Verification target

The next operator run should produce `autoplay-runtime-turn-result-payloads.json` with caller-local events around the runtime-result probe. Those events should include bounded `turn_result`, runtime error fields when present, and trace summaries at the exact emission point.

This is evidence capture only; it does not claim the runtime issue is fixed.
