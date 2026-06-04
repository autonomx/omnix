# RPG Phase 9.7 Operator Evidence Intake Contract

Phase 9.7 records the deterministic intake contract for live/operator endurance evidence.

Latest source-of-truth SHA before this Phase 9.7 slice:

- `21d658a01877d8e735819dc3a727e4d8e8137eb9`

## Scope

This slice is source/test/documentation only. It does not run a live/provider 100-turn or 1000-turn campaign in CI and does not change runtime behavior.

Phase 9.7 exists to define how operator evidence should be attached, summarized, and classified before future endurance hardening. CI source guards can prove that the intake contract exists, but they do not prove live 1000-turn performance.

## Required operator evidence sections

Every live/provider endurance evidence summary should include these sections:

1. `run_metadata`
2. `provider_model_config`
3. `command_used`
4. `artifact_bundle_paths`
5. `autoplay_summary`
6. `autoplay_transcript`
7. `autoplay_campaign_results_zip`
8. `timing_metrics`
9. `final_drain_behavior`
10. `background_job_behavior`
11. `save_load_checkpoint_evidence`
12. `package_disk_replay_evidence`
13. `progress_quality_review`
14. `continuity_review`
15. `taxonomy_classification`

## Required evidence fields

The evidence summary should record concrete values for:

- run date and operator;
- git SHA and branch;
- requested turn count and executed turn count;
- provider, model, endpoint type, and relevant configuration;
- exact command used;
- path or archive reference for `autoplay-summary.json`;
- path or archive reference for `autoplay-transcript.json`;
- path or archive reference for `autoplay-campaign-results.zip`;
- blocking or human-equivalent turn timing;
- autoplay wall-clock timing;
- final drain duration and timeout status;
- background job count and drain behavior;
- save/load checkpoint artifact reference;
- package/disk replay artifact reference;
- progress-quality review notes;
- continuity review notes;
- selected Phase 9 taxonomy category.

## Missing-evidence classification rules

Use `operator_evidence_gap` when any required live/operator evidence is absent:

- missing live/provider run evidence should classify as `operator_evidence_gap`;
- missing timing evidence should classify as `operator_evidence_gap`;
- missing save/load checkpoint or replay evidence should classify as `operator_evidence_gap`;
- missing transcript review should classify as `operator_evidence_gap`;
- missing artifact bundle references should classify as `operator_evidence_gap`;
- missing provider/model/config metadata should classify as `operator_evidence_gap`.

Do not treat absent evidence as a passing result. Do not infer timing, replay, checkpoint, or transcript quality from CI source guards.

## Taxonomy classification

An operator evidence summary should map the observed result to at least one active Phase 9 taxonomy category:

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

If the run completes but evidence is incomplete, classify the gap explicitly as `operator_evidence_gap` before claiming endurance readiness.

## Deterministic boundary

Phase 9.7 must not add:

- provider calls;
- LLM calls;
- network calls;
- live 100-turn or 1000-turn CI execution;
- gameplay mutation;
- UI authority changes;
- command execution paths outside existing runtime validation.

Simulation/runtime remains authoritative. Operator evidence summaries, labels, and transcript reviews are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 9.7 is complete when the repository has CI-gated documentation/tests proving that live/operator endurance evidence has a stable intake contract, missing required evidence maps to `operator_evidence_gap`, and CI source guards do not claim live/provider 1000-turn performance.

## Recommended next slice

After Phase 9.7, continue with:

- Phase 9.8 — long-run continuity evidence envelope.
