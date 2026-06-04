# RPG Phase 9.4 Progress-Quality Loop Taxonomy Guard

Phase 9.4 records the deterministic progress-quality loop evidence envelope for 1000-turn endurance work.

Latest source-of-truth SHA before this Phase 9.4 slice:

- `eef332e0ad954e18172a8ae8ff531bf7cf63b28e`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 1000-turn campaign in CI.

Phase 9.4 guards how endurance progress-quality failures are classified when a long run appears to continue but produces weak, false, or repeated no-op progress.

## Required taxonomy categories

Phase 9.4 keeps these Phase 9.1 categories active for progress-quality loop evidence:

- `progress_quality_failure`
- `turn_execution_failure`
- `operator_evidence_gap`

Progress-quality failures must not be collapsed into generic turn execution failures when the run keeps executing turns but objective, quest, or world-state evidence shows no meaningful progress.

## CI-gated evidence

CI-gated Phase 9.4 evidence should remain deterministic/provider-free and may cover:

- source-backed documentation that names the progress-quality taxonomy categories;
- guards that distinguish false progress and repeated no-op loops from turn crashes;
- guards that ensure rejected or non-player-turn actions are not treated as successful progress;
- guards that keep progress-quality evidence separate from live/operator narrative review;
- guards that preserve the next-slice handoff for performance/evidence envelope work.

## Operator/manual evidence

Operator/manual evidence may cover:

- live/provider review of 100-turn or 1000-turn transcripts;
- long-run objective, quest, travel, combat, party, and economy coverage review;
- manual judgment of narrative quality and repeated presentation loops;
- production-like resource and wall-clock observations that contextualize progress quality.

## Classification rules

Use these rules when reading an endurance result:

1. If a run completes turns but repeatedly reports no objective, quest, travel, combat, party, economy, or world-state movement, classify the result as `progress_quality_failure`.
2. If repeated rejected, invalid, or non-player-turn actions are counted as successful state changes, classify the result as `progress_quality_failure` unless the turn crashed first.
3. If a turn crashes or cannot return a valid runtime result, classify the result as `turn_execution_failure` before progress quality.
4. If progress quality requires live/provider transcript review and that evidence has not been supplied, classify the gap as `operator_evidence_gap`.
5. If CI source guards pass but no live/operator transcript review exists, keep progress-quality evidence incomplete.

## Deterministic boundary

Phase 9.4 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Suggested actions, narration, transcript review, and progress-quality labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 9.4 is complete when the repository has CI-gated documentation/tests proving that progress-quality loop evidence has explicit taxonomy coverage without requiring live/provider endurance execution.

## Recommended next slice

After Phase 9.4, continue with:

- Phase 9.5 — endurance performance/evidence envelope.
