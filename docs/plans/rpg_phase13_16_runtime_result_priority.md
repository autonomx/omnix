# RPG Phase 13.16 Runtime Result Diagnostics Priority

Phase 13.16 addresses the rerun after Phase 13.15.

Latest source-of-truth SHA before this Phase 13.16 slice:

- `0d03c702dc103da4f7b43ec888b47e3b4aa43203`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(8).zip`

The evidence showed:

- report-size hardening remains fixed;
- per-run performance output remains present;
- `autoplay-turn-error-diagnostics.json` is present;
- the diagnostics artifact filled with generic failure objects before surfacing the real runtime result payload;
- most captured events had no runtime trace keys.

## Bounded target

Phase 13.16 selects this bounded target:

- prioritize trace-bearing runtime result payloads over generic failure objects in `autoplay-turn-error-diagnostics.json`.

## Implementation

This slice updates:

- `src/tests/rpg/autoplay/result_path_diagnostics.py`
- `src/tests/rpg/test_ci_phase13_15_result_path_diagnostics.py`
- `docs/plans/rpg_production_readiness_plan.md`

This slice adds:

- `docs/plans/rpg_phase13_16_runtime_result_priority.md`
- `docs/plans/rpg_phase13_16_completion_note.md`

## Runtime result priority

The diagnostics scanner now classifies events into:

- `runtime_result_events`
- `generic_failure_events`

Runtime result events are detected when a failed payload carries fields such as:

- `runtime_name`
- `manual_harness_trace`
- `manual_harness_trace_summary`
- `manual_stage_trace`
- `manual_stage_trace_summary`
- `manual_turn_summary`
- `provider_trace`
- `turn_contract`
- `turn_perf_trace`
- `turn_perf_trace_summary`

Runtime events are sorted ahead of generic events and have a separate event cap, so generic report-level failures cannot crowd them out.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- trace-bearing failed payloads are marked as runtime result events;
- diagnostic output contains separate runtime and generic event lists;
- runtime events are retained even when generic failures exceed the generic cap;
- generic failure events remain bounded;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostics labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.16, continue with:

- Phase 13.17 — rerun 100-turn evidence review after runtime-result diagnostics priority.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect `autoplay-turn-error-diagnostics.json`, especially `runtime_result_events`.
