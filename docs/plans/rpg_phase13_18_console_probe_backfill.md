# RPG Phase 13.18 Console Probe Runtime Result Backfill

Phase 13.18 addresses the rerun after Phase 13.17.

Latest source-of-truth SHA before this Phase 13.18 slice:

- `6be4bf921be3832897dd11584705c6405167937d`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(10).zip`

The evidence showed:

- report-size hardening remains fixed;
- per-run performance output remains present;
- `autoplay-turn-error-diagnostics.json` remains present;
- `autoplay-runtime-turn-results.json` was missing;
- the runtime result probe lines are present in `console-log.txt`.

The live stdout/stderr hook did not see the generated harness console stream, so the persisted console log is the authoritative source for this diagnostic artifact.

## Bounded target

Phase 13.18 selects this bounded target:

- parse `console-log.txt` after the run and backfill `autoplay-runtime-turn-results.json` before diagnostics and performance summaries are generated.

## Implementation

This slice updates:

- `src/tests/rpg/autoplay/runtime_turn_result_capture_hook.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `src/tests/rpg/test_ci_phase13_17_runtime_result_emitter.py`
- `docs/plans/rpg_production_readiness_plan.md`

This slice adds:

- `docs/plans/rpg_phase13_18_console_probe_backfill.md`
- `docs/plans/rpg_phase13_18_completion_note.md`

## Console probe backfill

The runtime result capture helper now supports:

- `parse_console_log_runtime_turn_results(path)`
- `backfill_runtime_turn_results_from_console_log(output_dir)`

The backfill searches for:

- `console-log.txt`
- `autoplay-console-log.txt`
- `autoplay-campaign-results-unzipped/console-log.txt`

When a line contains `event=runtime_turn_execution.result`, the parser stores:

- original line;
- timestamp when present;
- parsed turn index when present;
- parsed `ok` value when present;
- emitted result keys;
- detected trace keys;
- capture source `console_log`.

## Hook order

The post-run artifact hook now runs console-log backfill before:

1. collecting runtime result rows;
2. writing result-path diagnostics;
3. writing performance summaries.

That makes the backfilled runtime result artifact available to both diagnostics and performance bridge generation in the same run.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- console-log runtime probe lines are parsed;
- timestamps, turn index, `ok`, result keys, and trace keys are retained;
- `autoplay-runtime-turn-results.json` is created from console-log backfill;
- the post-run hook backfills before diagnostics;
- diagnostics then expose runtime result events from the backfilled artifact;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostics and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.18, continue with:

- Phase 13.19 — rerun 100-turn evidence review after console probe backfill.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect:

- `autoplay-runtime-turn-results.json`
- `autoplay-turn-error-diagnostics.json`
- `autoplay-performance-summary.json`
