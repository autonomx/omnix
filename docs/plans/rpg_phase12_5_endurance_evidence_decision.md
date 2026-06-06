# RPG Phase 12.5 Endurance Evidence Decision

Phase 12.5 is the live-run endurance evidence capture or hardening slice.

Latest source-of-truth SHA before this Phase 12.5 slice:

- `891822cedd5ceee44e8f2bc012b2f803bd8c57bd`

## Scope

This slice is source/test/documentation only because no accepted endurance evidence bundle is attached.

Phase 12.5 must not implement long-run, runtime, external-service, final-drain, background-job, timing, progress-quality, continuity, checkpoint/replay, UI, or gameplay hardening unless accepted endurance evidence identifies a concrete bounded target.

## Accepted endurance evidence requirements

Before Phase 12.5 may implement a hardening fix, the evidence packet must include:

1. `accepted_endurance_evidence_source_path`
2. `source_checkout`
3. `service_configuration`
4. `model_configuration`
5. `run_command`
6. `runtime_configuration_snapshot`
7. `requested_turn_count`
8. `turns_executed`
9. `run_exit_status`
10. `artifact_bundle_manifest`
11. `autoplay_summary_capture`
12. `autoplay_transcript_capture`
13. `autoplay_zip_capture`
14. `checkpoint_artifact_capture`
15. `replay_artifact_capture`
16. `timing_metrics_capture`
17. `final_drain_capture`
18. `background_job_capture`
19. `progress_quality_review`
20. `continuity_review`
21. `failure_category`
22. `hardening_handoff`
23. `affected_component`
24. `player_or_operator_impact`
25. `deterministic_runtime_boundary_impact`
26. `proposed_bounded_fix_target`
27. `explicit_non_targets`
28. `acceptance_criteria`
29. `required_verification_checks`
30. `redaction_review`

## Decision classifications

Use one or more of these classifications:

- `phase12_5_endurance_evidence_not_started`
- `operator_evidence_backfill_required`
- `endurance_evidence_incomplete`
- `service_configuration_gap`
- `model_configuration_gap`
- `run_command_gap`
- `runtime_configuration_gap`
- `turn_count_gap`
- `run_exit_status_gap`
- `artifact_bundle_gap`
- `autoplay_summary_gap`
- `autoplay_transcript_gap`
- `autoplay_zip_gap`
- `checkpoint_artifact_gap`
- `replay_artifact_gap`
- `timing_metrics_gap`
- `final_drain_gap`
- `background_job_gap`
- `progress_quality_review_gap`
- `continuity_review_gap`
- `failure_classification_gap`
- `hardening_handoff_gap`
- `redaction_review_gap`
- `endurance_target_ready`
- `phase12_5_implementation_allowed`
- `phase12_5_implementation_blocked`

## Decision rules

Use `phase12_5_endurance_evidence_not_started` when no accepted endurance evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting service, model, command, runtime configuration, artifact, timing, final-drain, background-job, transcript review, failure classification, handoff, checkpoint/replay, or redaction evidence.

Use `endurance_evidence_incomplete` when evidence is attached but missing any accepted endurance evidence requirement.

Use category-specific `*_gap` classifications when the matching requirement is missing, ambiguous, not reproducible, or not tied to the exact source checkout.

Use `endurance_target_ready` only when endurance evidence identifies a bounded long-run, external-service, final-drain, background-job, timing, resource-limit, progress-quality, continuity, checkpoint/replay, artifact, or handoff failure and supplies all accepted evidence requirements.

Use `phase12_5_implementation_allowed` only when `endurance_target_ready` is present and all accepted endurance evidence requirements are complete.

Use `phase12_5_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or does not identify a bounded endurance fix target.

## No-evidence decision for this slice

Because this Phase 12.5 slice does not attach an accepted endurance evidence packet, the current decision state is:

- classification: `phase12_5_endurance_evidence_not_started`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_5_implementation_blocked`
- selected endurance fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: endurance implementation, runtime behavior changes, external-service behavior changes, final-drain changes, background-job changes, timing behavior changes, progress-quality changes, continuity changes, checkpoint/replay changes, gameplay mutation, service calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.5 hardening PR may be opened only when all accepted evidence requirements are complete and both `endurance_target_ready` and `phase12_5_implementation_allowed` are present.

If any checklist item is missing, Phase 12.5 remains blocked and the next action is endurance evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.5 must not add service calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, speculative hardening, package building in CI, endurance implementation without accepted evidence, or external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.5 decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.5 is complete when the repository has CI-gated documentation/tests proving that endurance implementation remains blocked without accepted evidence, accepted endurance evidence requirements are explicit, and any future endurance hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.5, continue with:

- Phase 12.6 — checkpoint/replay evidence capture or hardening.
