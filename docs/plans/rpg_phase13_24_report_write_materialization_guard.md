# Phase 13.24 — report write materialization guard

## Context

The Phase 13.23 rerun proved the live timing wrapper flood was fixed: the timing artifact contained only two events and no generated bundle helper flood. The remaining visible pause moved to post-run artifact generation. The run wrote an `autoplay-campaign-report.json` file that was about 995 MB before the post-run size guard replaced it with a compact payload.

## Change

This slice extends the report materialization guard to cover file-handle writes through `open(...).write(...)` for known autoplay report JSON/HTML artifact names. Oversized report output is compacted while the file is being written, instead of only after a huge file has already been materialized.

## Verification target

The next operator rerun should verify that `autoplay-report-size-guard-summary.json` records `materialization_guard_source` and an `open.write` capped event for oversized report output. The post-run gap after `pipeline_shutdown.end` should shrink if the oversized report path was dominated by disk materialization.

This does not claim the RecursionError is fixed.
