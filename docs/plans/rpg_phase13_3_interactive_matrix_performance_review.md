# RPG Phase 13.3 Interactive Matrix Performance Evidence Review

Phase 13.3 reviews the uploaded interactive intent matrix run and adds structured performance review artifact parity for matrix outputs.

Latest source-of-truth SHA before this Phase 13.3 slice:

- `58d1a7c0b3106a90d639828e292067692a56345d`

## Accepted evidence

The accepted evidence is the uploaded matrix bundle:

- `interactive-intent-matrix(36).zip`

The run showed:

- 8 scenarios passed;
- 23 completed turns;
- overall average turn time of about 3.14 seconds;
- p95 turn time of about 6.36 seconds;
- max turn time of about 7.45 seconds;
- 0 turns above 10 seconds;
- deterministic fast paths around 0.10 seconds per turn;
- provider-backed scenarios averaging about 5.42 seconds per turn;
- runtime-apply time dominating total turn time.

## Bounded target

Phase 13.3 selects this bounded target:

- add an interactive intent matrix performance review artifact pair so matrix evidence has explicit JSON/HTML review parity with the autoplay performance summary surface.

This is measurement/review hardening, not runtime latency reduction.

## Implementation

This slice adds:

- `src/app/rpg/interactive_matrix_performance_review.py`
- `src/tests/rpg/interactive_intent_matrix_performance_review_cli.py`
- `src/tests/rpg/test_ci_phase13_3_interactive_matrix_performance_review.py`
- `docs/plans/rpg_phase13_3_interactive_matrix_performance_review.md`
- `docs/plans/rpg_phase13_3_completion_note.md`

The new review helper reads the existing `interactive-intent-matrix-performance.json` shape and emits:

- `interactive-intent-matrix-performance-review.json`
- `interactive-intent-matrix-performance-review.html`

## Review classifications

The review emits warning classifications for:

- `matrix_avg_turn_seconds_above_target`
- `matrix_p95_turn_seconds_above_target`
- `matrix_max_turn_seconds_above_target`
- `provider_backed_avg_turn_seconds_above_target`
- `deterministic_fast_path_avg_turn_seconds_above_target`
- `runtime_apply_share_dominates_turn_time`

For the uploaded evidence shape, the selected next target is:

- `bounded_latency_reduction_for_provider_backed_intent_paths`

## Acceptance criteria

The implementation is accepted when:

- deterministic tests prove the uploaded matrix evidence shape produces the expected advisory review;
- the helper writes JSON and HTML review artifacts;
- the CLI can build review artifacts from an existing matrix performance JSON file;
- the review remains advisory-only and does not decide simulation truth;
- runtime, provider, gameplay, UI authority, live provider calls, and package building are unchanged.

## Deterministic boundary

This slice does not add provider calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, package building in CI, or external release claims.

Simulation/runtime remains authoritative. Matrix performance review labels are advisory evidence surfaces only and must not decide gameplay truth.

## Recommended next slice

After Phase 13.3, continue with:

- Phase 13.4 — bounded latency reduction for provider-backed intent paths.
