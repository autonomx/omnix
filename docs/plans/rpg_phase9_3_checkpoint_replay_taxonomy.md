# RPG Phase 9.3 Checkpoint and Replay Taxonomy Guard

Phase 9.3 records the deterministic checkpoint and replay evidence envelope for 1000-turn endurance work.

Latest source-of-truth SHA before this Phase 9.3 slice:

- `036fedee91850e21cc7483c5605cbca01547f035`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 1000-turn campaign in CI.

Phase 9.3 guards how endurance checkpoint and replay failures are classified and what evidence must exist before operator/live results can be treated as complete.

## Required taxonomy categories

Phase 9.3 keeps these Phase 9.1 categories active for checkpoint and replay evidence:

- `save_load_checkpoint_failure`
- `artifact_contract_failure`
- `operator_evidence_gap`

Checkpoint/replay failures must not be collapsed into generic turn execution failures when the evidence indicates one of these specific causes.

## CI-gated evidence

CI-gated Phase 9.3 evidence should remain deterministic/provider-free and may cover:

- source-backed documentation that names the checkpoint/replay taxonomy categories;
- guards that ensure checkpoint/replay evidence is classified separately from generic turn failures;
- guards that ensure completion notes distinguish CI-gated evidence from operator/manual evidence;
- guards that keep the compatibility runner artifact contract connected to checkpoint/replay evidence.

## Operator/manual evidence

Operator/manual evidence may cover:

- live/provider save/load checkpoints from 100-turn or 1000-turn campaigns;
- package/disk replay artifacts from a target machine;
- final replay/determinism review of long-run transcripts and saved bundles;
- wall-clock and final-drain timing from production-like environments.

## Classification rules

Use these rules when reading an endurance result:

1. If a save/load checkpoint hook fails, classify the result as `save_load_checkpoint_failure`.
2. If the checkpoint cannot be evaluated because required files are missing, classify the result as `artifact_contract_failure`.
3. If checkpoint/replay evidence requires a live/provider or operator environment and has not been supplied, classify the gap as `operator_evidence_gap`.
4. If the runner continues after a rejected or non-player-turn action and reports a successful state change, do not classify that as replay success.
5. If package/disk replay is absent, keep the replay evidence incomplete even when CI source guards pass.

## Deterministic boundary

Phase 9.3 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Replay/checkpoint evidence is observational and must not decide gameplay truth.

## Stop condition

Phase 9.3 is complete when the repository has CI-gated documentation/tests proving that checkpoint and replay evidence has explicit taxonomy coverage without requiring live/provider endurance execution.

## Recommended next slice

After Phase 9.3, continue with:

- Phase 9.4 — endurance progress-quality loop taxonomy guard.
