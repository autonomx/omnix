# RPG Phase 9.9 Targeted Endurance Hardening Decision Gate

Phase 9.9 records the decision gate for targeted endurance hardening from concrete evidence.

Latest source-of-truth SHA before this Phase 9.9 slice:

- `57660270175598e6c407727893fc9ae3e325947e`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 100-turn or 1000-turn campaign in CI and does not change runtime behavior.

No live/operator artifact bundle was attached for this slice. Because no concrete artifact, checkpoint, replay, performance, continuity, or CI failure evidence was attached, Phase 9.9 must classify the current hardening decision as `operator_evidence_gap` instead of changing runtime behavior.

## Required concrete evidence before runtime hardening

A future targeted hardening slice must cite at least one concrete evidence source before changing runtime, harness, gameplay, save/load, replay, UI, or provider-boundary code:

- `autoplay-summary.json`
- `autoplay-transcript.json`
- `autoplay-campaign-results.zip`
- save/load checkpoint artifacts
- package/disk replay artifacts
- operator evidence summary
- timing/performance evidence summary
- long-run continuity review
- progress-quality review
- CI failure logs with source-backed failure output

## Hardening decision states

A targeted hardening decision must resolve to one of these states:

1. `operator_evidence_gap`
2. `documentation_only_followup`
3. `harness_contract_fix`
4. `artifact_contract_fix`
5. `checkpoint_replay_fix`
6. `progress_quality_fix`
7. `performance_budget_fix`
8. `world_continuity_fix`
9. `provider_boundary_fix`
10. `runtime_authority_fix`

## Decision rules

Use `operator_evidence_gap` when no concrete evidence is attached.

Use `documentation_only_followup` when evidence identifies a documentation, runbook, or taxonomy clarification that does not require runtime behavior changes.

Use `harness_contract_fix` only when evidence shows a harness entrypoint, compatibility runner, or artifact-discovery contract failure.

Use `artifact_contract_fix` only when evidence shows malformed, missing, or inconsistent summary, transcript, ZIP, or artifact path contracts.

Use `checkpoint_replay_fix` only when evidence shows failed save/load checkpoint validation, replay mismatch, or package/disk replay mismatch.

Use `progress_quality_fix` only when evidence shows weak progress, false progress, repeated no-op loops, invalid action success claims, or rejected/non-player-turn actions counted as progress.

Use `performance_budget_fix` only when evidence shows timing, final-drain, background-job, or resource-budget failures.

Use `world_continuity_fix` only when evidence shows continuity drift across combat, NPC memory, party, travel, time, weather, quest, reward, economy, inventory, save/load, or replay state.

Use `provider_boundary_fix` only when evidence shows unsupported provider-facing state claims, provider-boundary leakage, or provider-dependent evidence interpretation.

Use `runtime_authority_fix` only when evidence shows runtime wrapper authority was bypassed or gameplay truth was decided outside authoritative runtime paths.

## No-evidence decision for this slice

Because this Phase 9.9 slice has no attached live/operator artifact bundle, no attached checkpoint/replay package, no attached continuity review, no attached performance evidence, and no failing CI log, the correct decision is:

- decision: `operator_evidence_gap`
- allowed changes: documentation and deterministic source guards only
- disallowed changes: runtime behavior, gameplay mutation, UI authority, provider calls, LLM calls, live endurance execution in CI, and command execution path changes

## Deterministic boundary

Phase 9.9 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Evidence classification and hardening labels are planning surfaces only and must not decide gameplay truth.

## Stop condition

Phase 9.9 is complete when the repository has CI-gated documentation/tests proving that targeted endurance hardening requires concrete evidence, absent evidence maps to `operator_evidence_gap`, and this slice did not change runtime behavior.

## Recommended next slice

After Phase 9.9, continue with:

- Phase 10 — production packaging, stability, and release readiness.
