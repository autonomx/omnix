# RPG Phase 9.5 Performance Evidence Envelope

Phase 9.5 records the deterministic performance evidence envelope for 1000-turn endurance work.

Latest source-of-truth SHA before this Phase 9.5 slice:

- `3dd2fb3060d5158817b652a36ea205c0b3bf1160`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 1000-turn campaign in CI.

Phase 9.5 guards which performance evidence must exist before an endurance result can be interpreted as meeting blocking, wall-clock, final-drain, and resource-limit expectations.

## Required taxonomy categories

Phase 9.5 keeps these Phase 9.1 categories active for performance evidence:

- `performance_budget_failure`
- `operator_evidence_gap`
- `progress_quality_failure`

Performance-budget failures must not be treated as complete evidence when only CI source guards exist and no live/operator timing artifact has been supplied.

## CI-gated evidence

CI-gated Phase 9.5 evidence should remain deterministic/provider-free and may cover:

- source-backed documentation that names the performance taxonomy categories;
- guards that define required performance evidence labels and artifact fields;
- guards that keep performance evidence separate from live/provider endurance execution;
- guards that classify absent operator timing artifacts as `operator_evidence_gap`;
- guards that preserve the next-slice handoff for targeted endurance hardening.

CI source guards may verify that summary/transcript/report artifacts expose interpretable performance labels, but they do not prove live 1000-turn performance.

## Operator/manual evidence

Operator/manual evidence may cover:

- blocking or human-equivalent turn time from a live/provider 100-turn or 1000-turn campaign;
- autoplay wall-clock time for the complete run;
- final drain timing and background job drain behavior;
- production-like CPU, GPU, memory, disk, and model-resource limits;
- transcript/report context needed to distinguish slow progress from repeated no-op loops.

## Required performance evidence labels

Endurance artifacts or operator summaries should use stable labels for:

- `blocking_turn_time_ms`
- `human_equivalent_turn_time_ms`
- `autoplay_wall_clock_ms`
- `final_drain_ms`
- `background_jobs_started`
- `background_jobs_completed`
- `background_jobs_pending_at_shutdown`
- `production_resource_limits`
- `performance_budget_failure`
- `operator_evidence_gap`

These labels are evidence surfaces only. They must not decide gameplay truth or mutate runtime state.

## Classification rules

Use these rules when reading an endurance result:

1. If blocking or human-equivalent turn time exceeds the current budget in a live/operator run, classify the result as `performance_budget_failure`.
2. If autoplay wall-clock, final drain, or background job drain behavior exceeds the current budget in a live/operator run, classify the result as `performance_budget_failure`.
3. If timing evidence is absent because no live/provider or operator artifact was supplied, classify the gap as `operator_evidence_gap`.
4. If slow timing is caused by repeated no-op loops or false progress, also preserve `progress_quality_failure` context instead of treating the result as a pure performance problem.
5. If CI source guards pass but no operator timing artifact exists, keep performance evidence incomplete.

## Deterministic boundary

Phase 9.5 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Timing labels, resource notes, transcripts, and operator summaries are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 9.5 is complete when the repository has CI-gated documentation/tests proving that performance evidence has explicit taxonomy coverage without requiring live/provider endurance execution.

## Recommended next slice

After Phase 9.5, continue with:

- Phase 9.6 — targeted endurance hardening from concrete evidence.
