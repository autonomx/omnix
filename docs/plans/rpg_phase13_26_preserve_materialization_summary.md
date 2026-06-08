# Phase 13.26 — preserve materialization summary evidence

## Context

The latest operator rerun showed the report artifact is now capped at an original size of about 64.7 MB instead of the earlier ~995 MB, but `autoplay-report-size-guard-summary.json` still only showed the post-run size guard source. The likely cause is that the post-run size guard overwrote the summary emitted by the materialization guard.

## Change

This slice preserves existing materialization summary fields and capped file events when `cap_oversized_autoplay_reports` writes the final size-guard summary.

## Verification target

The next operator rerun should show whether the report write was caught by `autoplay_report_materialization_guard_v3`, including `guarded_api: open.write` if the file-handle path is used.

This does not claim the RecursionError is fixed.
