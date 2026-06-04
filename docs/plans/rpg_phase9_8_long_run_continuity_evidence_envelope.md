# RPG Phase 9.8 Long-Run Continuity Evidence Envelope

Phase 9.8 records the deterministic evidence envelope for long-run world continuity review.

Latest source-of-truth SHA before this Phase 9.8 slice:

- `979414346a99a635916875455447bfe59e81202e`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 100-turn or 1000-turn campaign in CI and does not change runtime behavior.

Phase 9.8 defines the continuity evidence categories and required review fields that live/operator endurance artifacts should provide before future targeted hardening. CI source guards can prove that the continuity evidence envelope exists, but they do not prove live 1000-turn continuity.

## Required continuity evidence categories

Every long-run continuity review should explicitly evaluate these categories:

1. `combat_continuity`
2. `npc_memory_continuity`
3. `party_continuity`
4. `travel_continuity`
5. `time_continuity`
6. `weather_continuity`
7. `quest_continuity`
8. `reward_continuity`
9. `economy_inventory_continuity`
10. `save_load_continuity`
11. `replay_continuity`
12. `progress_quality_continuity`
13. `provider_boundary_continuity`
14. `runtime_authority_continuity`
15. `taxonomy_classification`

## Required evidence fields

The continuity evidence summary should record concrete values for:

- run metadata reference;
- source artifact bundle reference;
- reviewed turn range;
- transcript excerpts or row references for each continuity category;
- starting and ending location state;
- travel transitions and blocked-route handling;
- time/day/season/weather observations;
- combat entry, action, defeat, reward, and exit observations;
- NPC memory or relationship observations;
- party join, leave, and membership observations;
- quest objective, completion, failure, and journal observations;
- reward, XP, currency, item, and inventory observations;
- save/load checkpoint artifact references;
- replay or package/disk replay artifact references;
- rejected, invalid, or non-player-turn action handling;
- provider-boundary or unsupported state-claim observations;
- selected Phase 9 taxonomy category.

## Continuity drift classification rules

Use `world_continuity_failure` when evidence shows inconsistent long-run state across continuity categories:

- combat state or reward drift should classify as `world_continuity_failure`;
- NPC memory, relationship, or persona drift should classify as `world_continuity_failure`;
- party membership drift should classify as `world_continuity_failure`;
- travel, location, route, time, season, or weather drift should classify as `world_continuity_failure`;
- quest, objective, reward, XP, currency, item, or inventory drift should classify as `world_continuity_failure`;
- save/load or replay mismatch should classify as `save_load_checkpoint_failure` unless the evidence points to a malformed artifact contract;
- malformed or missing artifact references should classify as `artifact_contract_failure`;
- repeated no-op loops, false progress, or invalid action success claims should classify as `progress_quality_failure`;
- unsupported provider-facing state claims should classify as `provider_boundary_failure` or `runtime_authority_failure` based on the source of the claim.

## Missing-evidence classification rules

Use `operator_evidence_gap` when continuity cannot be reviewed from concrete artifacts:

- missing transcript evidence should classify as `operator_evidence_gap`;
- missing reviewed turn range should classify as `operator_evidence_gap`;
- missing save/load checkpoint or replay evidence should classify as `operator_evidence_gap`;
- missing continuity category review notes should classify as `operator_evidence_gap`;
- missing artifact bundle references should classify as `operator_evidence_gap`.

Do not treat absent continuity evidence as a passing result. Do not infer long-run continuity from CI source guards.

## Taxonomy classification

A long-run continuity review should map the observed result to at least one active Phase 9 taxonomy category:

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

If the run completes but continuity evidence is incomplete, classify the gap explicitly as `operator_evidence_gap` before claiming endurance readiness.

## Deterministic boundary

Phase 9.8 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Continuity evidence summaries, labels, and transcript reviews are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 9.8 is complete when the repository has CI-gated documentation/tests proving that long-run continuity evidence has a stable envelope, missing required continuity evidence maps to `operator_evidence_gap`, observed continuity drift maps to the appropriate Phase 9 taxonomy categories, and CI source guards do not claim live/provider 1000-turn continuity.

## Recommended next slice

After Phase 9.8, continue with:

- Phase 9.9 — targeted endurance hardening from concrete evidence.
