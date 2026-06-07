# RPG Phase 13.15 Result-Path Diagnostics and Trace Timing Bridge

Phase 13.15 addresses the rerun after Phase 13.14.

Latest source-of-truth SHA before this Phase 13.15 slice:

- `9fac8bd905203493b282334c9bb5f21a1b2db422`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(7).zip`

The evidence showed:

- report-size hardening remains fixed;
- per-run performance summary exists;
- print-based turn diagnostics did not capture the remaining turn errors;
- copy-guard diagnostics did not appear;
- live timing bridge only exposed coarse harness timing;
- the actual live turn execution result path contains trace keys such as manual harness traces and turn performance traces.

## Bounded targets

Phase 13.15 selects two bounded targets:

1. Scan actual saved result payloads after the run and emit `autoplay-turn-error-diagnostics.json` from result objects, not console output.
2. Bridge trace timing summaries from actual result rows into the canonical performance summary.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/result_path_diagnostics.py`
- `src/tests/rpg/test_ci_phase13_15_result_path_diagnostics.py`
- `docs/plans/rpg_phase13_15_result_path_diagnostics.md`
- `docs/plans/rpg_phase13_15_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay/live_performance_bridge.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Result-path diagnostics

The post-run hook now writes:

- `autoplay-turn-error-diagnostics.json`

The result-path scanner inspects saved JSON artifacts and JSON members inside the latest results ZIP. It records objects that contain:

- `ok: false`;
- error or exception fields;
- failure status labels;
- result-path trace maps.

Each event includes:

- turn index when available;
- JSON path inside the artifact;
- source artifact path;
- bounded error fields;
- trace keys present;
- bounded trace payloads.

## Trace timing bridge

The live timing bridge now reads result-row timing summaries in addition to the live harness `stage_summary`. Supported result-row sources include:

- `turn_perf_trace_summary`
- `manual_stage_trace_summary`
- `manual_harness_trace_summary`
- `turn_perf_trace`
- `manual_stage_trace`
- `manual_harness_trace`

The bridge preserves available timing fields in `autoplay-performance-summary.json` while keeping missing sub-stages explicit.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- failed result payloads are extracted with trace keys;
- file and ZIP result payloads are scanned;
- trace-summary timing populates canonical manual timing fields;
- the post-run hook writes the result-path diagnostics artifact;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostics and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.15, continue with:

- Phase 13.16 — rerun 100-turn evidence review after result-path diagnostics.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect `autoplay-turn-error-diagnostics.json` if turn errors remain.
