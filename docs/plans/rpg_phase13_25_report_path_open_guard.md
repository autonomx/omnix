# Phase 13.25 — report Path.open guard

## Context

The Phase 13.24 rerun still produced a post-run capped `autoplay-campaign-report.json` around 995 MB before compaction. The materialization summary did not include the v2 guard source or an `open.write` event. That indicates the report writer path bypassed `builtins.open`, likely through `Path.open()` / `io.open`.

## Change

This slice extends the report materialization guard to install on `io.open` as well as `builtins.open`, and adds regression coverage that writes an oversized report through `Path.open()` after installing the guard.

## Verification target

The next operator rerun should show `autoplay-report-size-guard-summary.json` with `materialization_guard_source` set to `autoplay_report_materialization_guard_v3` and at least one capped file event with `guarded_api: open.write`.

This does not claim the RecursionError is fixed.
