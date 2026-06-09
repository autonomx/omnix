# Phase 13.42 — manual turn summary error primitives

## Context

ZIP 30 already ran on the Phase 13.41 code. The runtime-result probe showed the normalized failed result includes `manual_turn_summary` with an `error` key, but did not expose the error value. The last trace markers were also exit/cleanup markers, so the previous trace item is needed to find the inner stage just before normalization.

## Change

This slice keeps diagnostics on the existing reliable runtime-result console probe and adds:

- `manual_stage_trace_prev`
- `turn_perf_trace_prev`
- `manual_turn_summary_error_type`
- `manual_turn_summary_error_tail`

The loader also drops the now-dead source-injected payload snapshot helper from the test surface. Diagnostics remain primitive-only: no nested state walks and no extra hot-path artifact file writes.

## Verification target

The next operator run should expose the actual normalized manual-turn summary error and the previous trace item before the final exit marker. That should identify the precise inner runtime boundary that catches the recursion failure.

This is evidence capture only; it does not claim the runtime issue is fixed.
