# RPG Phase 9.6 Targeted Endurance Hardening Plan

Phase 9.6 records the deterministic intake contract for targeted endurance hardening.

Latest source-of-truth SHA before this Phase 9.6 slice:

- `08eda228111ac5482e16e06712ae89fe878cde47`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 1000-turn campaign in CI and does not change runtime behavior.

Phase 9.6 exists to prevent speculative hardening. Runtime or harness fixes should be selected from concrete evidence produced by the Phase 9.1 through Phase 9.5 envelopes.

## Evidence required before targeted hardening

A future hardening slice should name at least one concrete source:

- `autoplay-summary.json`
- `autoplay-transcript.json`
- `autoplay-campaign-results.zip`
- a save/load checkpoint or package/disk replay artifact
- an operator evidence summary
- a CI failure with source-backed logs
- a production-like resource/timing note

The selected hardening target should map to at least one Phase 9 taxonomy category:

- `harness_entrypoint_failure`
- `runtime_authority_failure`
- `turn_execution_failure`
- `save_load_checkpoint_failure`
- `artifact_contract_failure`
- `progress_quality_failure`
- `performance_budget_failure`
- `provider_boundary_failure`
- `world_continuity_failure`
- `operator_evidence_gap`

## Selection rules

Use these rules before implementing targeted hardening:

1. If the evidence points to missing or malformed artifacts, target `artifact_contract_failure` before changing runtime behavior.
2. If the evidence points to failed checkpoint, replay, or package/disk validation, target `save_load_checkpoint_failure` before narrative or UI changes.
3. If the evidence points to repeated no-op loops or false progress, target `progress_quality_failure` before performance tuning.
4. If the evidence points to blocking turn time, wall-clock time, final drain, or background drain budget misses, target `performance_budget_failure` with the operator timing artifact attached.
5. If the evidence points to combat, NPC memory, party, travel, time, weather, quest, or reward drift, target `world_continuity_failure` without moving truth into UI or provider code.
6. If the evidence is missing, classify the next action as `operator_evidence_gap` instead of guessing a runtime fix.

## Deterministic boundary

Phase 9.6 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Evidence labels, planning docs, transcript review, and operator summaries are evidence surfaces only and must not decide gameplay truth.

## Production readiness document update

This slice also refreshes `docs/plans/rpg_production_readiness_plan.md` so it no longer reports Phase 8 as in progress or Phase 9 as pending. The refreshed document should identify:

- Phase 8 as closed;
- Phase 9.1 through Phase 9.5 as complete;
- Phase 9.6 as the current focus;
- Phase 9.7 as the next recommended slice after this intake contract;
- live/provider 1000-turn execution, save/load checkpoint evidence, package/disk replay evidence, and operator performance evidence as remaining risks.

## Stop condition

Phase 9.6 is complete when the repository has CI-gated documentation/tests proving that targeted endurance hardening is driven by concrete evidence and the production readiness plan reflects the current Phase 9 state.

## Recommended next slice

After Phase 9.6, continue with:

- Phase 9.7 — operator evidence intake contract.
