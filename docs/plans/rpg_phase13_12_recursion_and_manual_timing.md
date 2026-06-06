# RPG Phase 13.12 Recursion Guard and Manual-Turn Timing

Phase 13.12 addresses the 100-turn rerun after the report materialization guard.

Latest source-of-truth SHA before this Phase 13.12 slice:

- `47be44de3f4d1da96164de817cb19d4d530c8dd6`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(5).zip`

The evidence showed:

- report-size hardening worked;
- `autoplay-report-size-guard-summary.json` was present;
- `autoplay-performance-summary.json` was present;
- `manual_turn_breakdown` was present;
- deterministic runtime errors started at turn 59 with `RecursionError: maximum recursion depth exceeded`;
- manual-turn breakdown still only populated total manual time and deferred enqueue time.

## Bounded targets

Phase 13.12 selects two bounded targets:

1. Raise the runtime recursion budget before the interactive first-call runtime executes a turn.
2. Emit real sub-stage timing from the interactive first-call runtime so `manual_turn_breakdown` can explain blocking time.

## Implementation

This slice updates:

- `src/app/rpg/session/interactive_first_call_runtime.py`
- `src/app/rpg/autoplay_performance_artifacts.py`
- `docs/plans/rpg_production_readiness_plan.md`

This slice adds:

- `src/tests/rpg/test_ci_phase13_12_recursion_and_timing.py`
- `docs/plans/rpg_phase13_12_recursion_and_manual_timing.md`
- `docs/plans/rpg_phase13_12_completion_note.md`

## Runtime recursion guard

The first-call runtime now ensures the recursion limit is at least 10000 before it executes the turn path. This targets the observed long-run recursion failure without changing gameplay decisions or state authority.

## Manual-turn sub-stage timing

The first-call runtime now attaches `manual_turn_stage_timing` to turn results, including:

- `manual_turn_ms`
- `pre_runtime_intent_llm_ms`
- `deterministic_runtime_apply_ms`
- `grounding_validation_ms`
- `repair_ms`
- `state_snapshot_ms`
- `deferred_enqueue_ms`

The autoplay performance summary now reads `manual_turn_stage_timing` from top-level rows, nested `turn_result`, and nested runtime maps.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- the recursion budget is raised when below the floor;
- manual-stage timing attaches to top-level and nested turn results;
- performance summaries read and average `manual_turn_stage_timing` values;
- deferred enqueue timing can be read from nested aliases;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.12, continue with:

- Phase 13.13 — rerun 100-turn evidence review after recursion guard and manual-stage timing.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and verify that the `RecursionError` lines are gone and the manual-turn breakdown has populated sub-stage fields.
