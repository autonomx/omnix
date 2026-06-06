# RPG Phase 13.12 Completion Note

Phase 13.12 is complete as a recursion guard and manual-turn timing implementation.

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(5).zip`

The evidence showed that report-size hardening worked, but deterministic turn errors began at turn 59 with `RecursionError: maximum recursion depth exceeded`, and the manual-turn breakdown still needed real sub-stage timing.

## What changed

Phase 13.12 updated:

- `src/app/rpg/session/interactive_first_call_runtime.py`
- `src/app/rpg/autoplay_performance_artifacts.py`
- `docs/plans/rpg_production_readiness_plan.md`

Phase 13.12 added:

- `src/tests/rpg/test_ci_phase13_12_recursion_and_timing.py`
- `docs/plans/rpg_phase13_12_recursion_and_manual_timing.md`
- `docs/plans/rpg_phase13_12_completion_note.md`

## Implementation summary

The interactive first-call runtime now raises the recursion budget before running a turn and attaches `manual_turn_stage_timing` to turn results.

The performance summary helper now reads `manual_turn_stage_timing` from top-level rows and nested `turn_result`/runtime maps, so future 100-turn runs can report the sub-stage timing needed to explain human-playable blocking time.

## Boundary confirmation

This slice did not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Timing labels remain advisory artifact surfaces only and do not decide gameplay truth.

## Remaining risks

- The 100-turn command must be rerun to confirm the recursion errors are gone.
- The manual-stage timing fields must be verified in the next `autoplay-performance-summary.json`.
- Live/provider 1000-turn execution remains pending.
- Production readiness is not claimable.

## Recommended next slice

Continue with:

- Phase 13.13 — rerun 100-turn evidence review after recursion guard and manual-stage timing.
