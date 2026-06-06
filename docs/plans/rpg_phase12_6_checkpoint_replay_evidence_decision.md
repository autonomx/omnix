# RPG Phase 12.6 Checkpoint Replay Evidence Decision

Phase 12.6 is the checkpoint/replay evidence capture or hardening slice.

Latest source-of-truth SHA before this Phase 12.6 slice:

- `f063a53996d3e2c5801c84220172f4b8d580e533`

## Scope

This slice is source/test/documentation only because no accepted checkpoint/replay evidence bundle is attached.

Phase 12.6 must not implement checkpoint, replay, save/load, package/disk replay, determinism, artifact-integrity, runtime, provider, UI, or gameplay hardening unless accepted checkpoint/replay evidence identifies a concrete bounded target.

## Accepted checkpoint/replay evidence requirements

Before Phase 12.6 may implement a hardening fix, the evidence packet must include:

1. `accepted_checkpoint_replay_evidence_source_path`
2. `source_checkout`
3. `checkpoint_capture_context`
4. `checkpoint_artifact_manifest`
5. `save_load_roundtrip_reference`
6. `replay_command`
7. `replay_result`
8. `package_disk_replay_reference`
9. `determinism_notes`
10. `artifact_integrity_notes`
11. `failure_category`
12. `hardening_handoff`
13. `affected_component`
14. `player_or_operator_impact`
15. `deterministic_runtime_boundary_impact`
16. `proposed_bounded_fix_target`
17. `explicit_non_targets`
18. `acceptance_criteria`
19. `required_verification_checks`
20. `redaction_review`

## Decision classifications

Use one or more of these classifications:

- `phase12_6_checkpoint_replay_evidence_not_started`
- `operator_evidence_backfill_required`
- `checkpoint_replay_evidence_incomplete`
- `checkpoint_context_gap`
- `checkpoint_artifact_manifest_gap`
- `save_load_roundtrip_reference_gap`
- `replay_command_gap`
- `replay_result_gap`
- `package_disk_replay_reference_gap`
- `determinism_notes_gap`
- `artifact_integrity_gap`
- `failure_classification_gap`
- `hardening_handoff_gap`
- `redaction_review_gap`
- `checkpoint_replay_target_ready`
- `phase12_6_implementation_allowed`
- `phase12_6_implementation_blocked`

## Decision rules

Use `phase12_6_checkpoint_replay_evidence_not_started` when no accepted checkpoint/replay evidence packet is attached.

Use `operator_evidence_backfill_required` when the next action is still collecting checkpoint context, artifact manifest, save/load roundtrip, replay command, replay result, package/disk replay, determinism, artifact integrity, failure classification, hardening handoff, or redaction evidence.

Use `checkpoint_replay_evidence_incomplete` when evidence is attached but missing any accepted checkpoint/replay evidence requirement.

Use category-specific `*_gap` classifications when the matching requirement is missing, ambiguous, malformed, not reproducible, or not tied to the exact source checkout.

Use `checkpoint_replay_target_ready` only when checkpoint/replay evidence identifies a bounded checkpoint, save/load, replay, package/disk replay, determinism, artifact-integrity, redaction, or handoff failure and supplies all accepted evidence requirements.

Use `phase12_6_implementation_allowed` only when `checkpoint_replay_target_ready` is present and all accepted checkpoint/replay evidence requirements are complete.

Use `phase12_6_implementation_blocked` when evidence is missing, incomplete, not redacted, not reproducible, not source-backed, or does not identify a bounded checkpoint/replay fix target.

## No-evidence decision for this slice

Because this Phase 12.6 slice does not attach an accepted checkpoint/replay evidence packet, the current decision state is:

- classification: `phase12_6_checkpoint_replay_evidence_not_started`
- secondary classification: `operator_evidence_backfill_required`
- implementation state: `phase12_6_implementation_blocked`
- selected checkpoint/replay fix target: none
- allowed changes: documentation and deterministic source guards only
- disallowed changes: checkpoint implementation, replay implementation, save/load behavior changes, package/disk replay behavior changes, determinism behavior changes, artifact-integrity behavior changes, runtime behavior changes, gameplay mutation, provider calls, LLM calls, live endurance execution in CI, package building in CI, UI authority changes, speculative hardening, and external release-readiness claims

## Implementation allowed checklist

A Phase 12.6 hardening PR may be opened only when all accepted evidence requirements are complete and both `checkpoint_replay_target_ready` and `phase12_6_implementation_allowed` are present.

If any checklist item is missing, Phase 12.6 remains blocked and the next action is checkpoint/replay evidence backfill or target-selection clarification, not implementation.

## Deterministic boundary

Phase 12.6 must not add provider calls, LLM calls, network calls, live 100-turn or 1000-turn CI execution, gameplay mutation, UI authority changes, speculative hardening, package building in CI, checkpoint/replay implementation without accepted evidence, or external release claims without evidence.

Simulation/runtime remains authoritative. Phase 12.6 decision labels are evidence surfaces only and must not decide gameplay truth.

## Stop condition

Phase 12.6 is complete when the repository has CI-gated documentation/tests proving that checkpoint/replay implementation remains blocked without accepted evidence, accepted checkpoint/replay evidence requirements are explicit, and any future checkpoint/replay hardening implementation must be tied to a bounded source-backed target.

## Recommended next slice

After Phase 12.6, continue with:

- Phase 12.7 — accepted evidence intake closeout or implementation handoff.
